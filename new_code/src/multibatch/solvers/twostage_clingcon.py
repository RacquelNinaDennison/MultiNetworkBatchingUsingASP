"""Two-stage clingcon solver — ClingconTheory for CSP variables in both stages.

Stage 1: Network flow with CSP load variables + frequency assignment.
Stage 2: Per-trip bin packing with CSP tripLoad variables + diversification.

Uses multi-shot iterative bound tightening for stage 1.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory

from ..models import (
    TwoStageClingconConfig,
    TwoStageResult,
    Stage1Result,
    Stage2Result,
    SolveMetadata,
    RouteFreq,
    TripLoad,
)
from .base import BaseSolver


ENCODING_DIR = Path(__file__).resolve().parent.parent / "encodings" / "twostage" / "clingcon"


class ClingconTwoStageSolver(BaseSolver):
    """Clingcon two-stage solver using CSP variables for flow and packing.

    Stage 1 uses &dom/&sum constraints for load variables.
    Stage 2 uses &dom/&sum constraints for tripLoad variables.
    Often faster than pure ASP on larger instances due to propagation.
    """

    def __init__(
        self,
        instance_path: str | Path,
        config: TwoStageClingconConfig | None = None,
        stage1_encoding: str | Path | None = None,
        stage2_encoding: str | Path | None = None,
    ):
        super().__init__(instance_path)
        self.config = config or TwoStageClingconConfig()
        self.encoding_stage1 = (
            Path(stage1_encoding) if stage1_encoding
            else Path(self.config.stage1_encoding) if self.config.stage1_encoding
            else ENCODING_DIR / "stage_1_clingcon_flow.lp"
        )
        self.encoding_stage2 = (
            Path(stage2_encoding) if stage2_encoding
            else Path(self.config.stage2_encoding) if self.config.stage2_encoding
            else ENCODING_DIR / "stage_2_packing.lp"
        )

    # ─────────────────────────────────────────────────────────────────────
    # Stage 1: Clingcon network flow
    # ─────────────────────────────────────────────────────────────────────

    def _solve_stage1(self) -> Stage1Result | None:
        theory = ClingconTheory()
        clingo_args: list[str] = [
            "-c", f"cap_size_divide={self.config.cap_size_divide}",
            "-c", f"max_freq={self.config.max_freq}",
            "-c", f"weight={self.config.weight}",
            "-c", f"exposure_n={self.config.exposure_n}",
        ]
        if self.config.threads > 1:
            clingo_args += ["-t", str(self.config.threads)]
        if self.config.configuration:
            clingo_args += ["--configuration", self.config.configuration]

        ctl = clingo.Control(clingo_args)
        theory.register(ctl)

        with clingo.ast.ProgramBuilder(ctl) as builder:
            def on_rule(stm):
                theory.rewrite_ast(stm, builder.add)
            clingo.ast.parse_files(
                [str(self.encoding_stage1), str(self.instance_path)], on_rule
            )

        t0 = time.perf_counter()
        ctl.ground([("base", [])])
        theory.prepare(ctl)
        ground_time = time.perf_counter() - t0

        best: dict | None = None
        best_cost: int | None = None
        optimum = False
        trajectory: list[dict] = []

        # Multi-shot with iterative bound tightening
        num_rounds = max(1, self.config.time_limit // self.config.round_timeout)
        effective_timeout = self.config.round_timeout

        BOUND = (
            ":- #sum {{ V,F,T,TR : _transCost(F,T,TR,V) }} >= {bound}."
        )

        for round_num in range(1, num_rounds + 1):
            timer = threading.Timer(effective_timeout, ctl.interrupt)
            timer.start()

            found: dict | None = None
            found_cost: int | None = None

            try:
                with ctl.solve(yield_=True) as handle:
                    for model in handle:
                        theory.on_model(model)
                        found = self._extract_stage1(model, theory)
                        found_cost = model.cost[0] if model.cost else None
                        trajectory.append({
                            "cost": found_cost,
                            "time": round(time.perf_counter() - t0, 3),
                        })
                        if model.optimality_proven:
                            optimum = True
                            break
                    solve_result = handle.get()
            except RuntimeError:
                solve_result = None
            finally:
                timer.cancel()

            if optimum:
                best, best_cost = found, found_cost
                break

            if solve_result is not None and getattr(solve_result, 'unsatisfiable', False):
                optimum = True
                break

            if solve_result is not None and solve_result.exhausted:
                optimum = True
                if found is not None:
                    best, best_cost = found, found_cost
                break

            if found is None:
                break

            best, best_cost = found, found_cost

            # Tighten bound for next round
            bound_rule = BOUND.format(weight=self.config.weight, bound=best_cost)
            section = f"bound_{round_num}"
            ctl.add(section, [], bound_rule)
            ctl.ground([(section, [])])

        total_time = time.perf_counter() - t0
        solve_time = total_time - ground_time

        if best is None:
            return None

        # Extract solver stats
        choices = conflicts = restarts = atoms = 0
        try:
            s = ctl.statistics['solving']['solvers']
            choices = int(s['choices'])
            conflicts = int(s['conflicts'])
            restarts = int(s['restarts'])
        except (KeyError, IndexError, TypeError):
            pass
        try:
            atoms = int(ctl.statistics['problem']['lp']['atoms'])
        except (KeyError, IndexError, TypeError):
            pass

        route_freqs = [
            RouteFreq(
                origin=rf["from"],
                destination=rf["to"],
                transport=rf["tr"],
                frequency=rf["freq"],
                total_capacity=rf["total_cap"],
            )
            for rf in best["route_freqs"]
        ]

        return Stage1Result(
            metadata=SolveMetadata(
                ground_time=round(ground_time, 3),
                solve_time=round(solve_time, 3),
                total_time=round(total_time, 3),
                optimum=optimum,
                satisfiable=True,
                cost=best_cost,
                choices=choices,
                conflicts=conflicts,
                restarts=restarts,
                atoms=atoms,
                trajectory=trajectory,
            ),
            loads=best["loads"],
            route_freqs=route_freqs,
            high_exposure=best.get("high_exposure", []),
        )

    # ─────────────────────────────────────────────────────────────────────
    # Bridge: Stage 1 → Stage 2 facts
    # ─────────────────────────────────────────────────────────────────────

    def _build_stage2_facts(self, stage1: Stage1Result) -> str:
        """Convert stage 1 output + instance data into stage 2 input facts."""
        inst = self.instance
        lines: list[str] = []

        # totalLoad(From, To, TR, Part, N)
        for (f, t, tr, p), n in sorted(stage1.loads.items()):
            lines.append(f"totalLoad({f},{t},{tr},{p},{n}).")

        # transportCapacity(TR, Cap)
        for tr, cap in sorted(inst.transport_capacity.items()):
            lines.append(f"transportCapacity({tr},{cap}).")

        # activeRoute(From, To, TR, Freq, PerTripCap)
        for rf in stage1.route_freqs:
            per_trip_cap = inst.transport_capacity.get(rf.transport, 0)
            lines.append(
                f"activeRoute({rf.origin},{rf.destination},{rf.transport},"
                f"{rf.frequency},{per_trip_cap})."
            )

        # partSize(P, S)
        for p, s in sorted(inst.part_size.items()):
            lines.append(f"partSize({p},{s}).")

        # partVal(P, V)
        for p, v in sorted(inst.part_value.items()):
            lines.append(f"partVal({p},{v}).")

        # routeCost(From, To, TR, C)
        for rf in stage1.route_freqs:
            key = (rf.origin, rf.destination, rf.transport)
            cost = inst.route_cost.get(key, 0)
            if cost > 0:
                lines.append(f"routeCost({rf.origin},{rf.destination},{rf.transport},{cost}).")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Stage 2: Clingcon per-trip packing
    # ─────────────────────────────────────────────────────────────────────

    def _solve_stage2(self, stage1: Stage1Result) -> Stage2Result | None:
        facts_str = self._build_stage2_facts(stage1)

        theory = ClingconTheory()
        clingo_args: list[str] = [
            "-c", f"hetero_on={self.config.hetero_on}",
            "-c", f"concentrated_on={self.config.concentrated_on}",
        ]
        if self.config.threads > 1:
            clingo_args += ["-t", str(self.config.threads)]
        if self.config.configuration:
            clingo_args += ["--configuration", self.config.configuration]

        ctl = clingo.Control(clingo_args)
        theory.register(ctl)

        with clingo.ast.ProgramBuilder(ctl) as builder:
            def on_rule(stm):
                theory.rewrite_ast(stm, builder.add)
            clingo.ast.parse_string(facts_str, on_rule)
            clingo.ast.parse_files([str(self.encoding_stage2)], on_rule)

        t0 = time.perf_counter()
        ctl.ground([("base", [])])
        theory.prepare(ctl)
        ground_time = time.perf_counter() - t0

        best: dict | None = None
        best_cost: list[int] | None = None
        optimum = False
        trajectory: list[dict] = []

        timer = threading.Timer(self.config.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    best = self._extract_stage2(model, theory)
                    best_cost = list(model.cost) if model.cost else None
                    trajectory.append({
                        "cost": best_cost,
                        "time": round(time.perf_counter() - t0, 3),
                    })
                    if model.optimality_proven:
                        optimum = True
                        break
                solve_result = handle.get()
                if not optimum and solve_result.exhausted:
                    optimum = True
        except RuntimeError:
            pass
        finally:
            timer.cancel()

        total_time = time.perf_counter() - t0
        solve_time = total_time - ground_time

        if best is None:
            return None

        # Extract solver stats
        choices = conflicts = restarts = atoms = 0
        try:
            s = ctl.statistics['solving']['solvers']
            choices = int(s['choices'])
            conflicts = int(s['conflicts'])
            restarts = int(s['restarts'])
        except (KeyError, IndexError, TypeError):
            pass
        try:
            atoms = int(ctl.statistics['problem']['lp']['atoms'])
        except (KeyError, IndexError, TypeError):
            pass

        # Flatten multi-level cost to single int
        cost_int = best_cost[0] if best_cost else None

        return Stage2Result(
            metadata=SolveMetadata(
                ground_time=round(ground_time, 3),
                solve_time=round(solve_time, 3),
                total_time=round(total_time, 3),
                optimum=optimum,
                satisfiable=True,
                cost=cost_int,
                choices=choices,
                conflicts=conflicts,
                restarts=restarts,
                atoms=atoms,
                trajectory=trajectory,
            ),
            trip_loads=best["trip_loads"],
            used_trips=best["used_trips"],
            mono_count=best["mono_count"],
            concentrated_count=best["concentrated_count"],
        )

    # ─────────────────────────────────────────────────────────────────────
    # Combined solve
    # ─────────────────────────────────────────────────────────────────────

    def solve(self) -> TwoStageResult | None:
        """Run both stages sequentially. Returns TwoStageResult or None."""
        if not self.encoding_stage1.exists():
            raise FileNotFoundError(f"Stage 1 encoding not found: {self.encoding_stage1}")
        if not self.encoding_stage2.exists():
            raise FileNotFoundError(f"Stage 2 encoding not found: {self.encoding_stage2}")

        stage1 = self._solve_stage1()
        print(stage1)
        if stage1 is None:
            return None

        stage2 = self._solve_stage2(stage1)
        print(stage2)
        if stage2 is None:
            return None

        return TwoStageResult(stage1=stage1, stage2=stage2)

    # ─────────────────────────────────────────────────────────────────────
    # Extraction helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_stage1(model: clingo.Model, theory: ClingconTheory) -> dict:
        """Extract routeFreq from shown atoms, load from theory assignments."""
        route_freqs: list[dict] = []
        high_exposure: list[tuple[str, str, str, str]] = []

        for sym in model.symbols(shown=True):
            if sym.name == "routeFreq" and len(sym.arguments) == 5:
                a = sym.arguments
                route_freqs.append({
                    "from": str(a[0]),
                    "to": str(a[1]),
                    "tr": str(a[2]),
                    "freq": a[3].number,
                    "total_cap": a[4].number,
                })
            elif sym.name == "highExposure" and len(sym.arguments) == 4:
                a = sym.arguments
                high_exposure.append(
                    (str(a[0]), str(a[1]), str(a[2]), str(a[3]))
                )

        loads: dict[tuple[str, str, str, str], int] = {}
        for sym, value in theory.assignment(model.thread_id):
            val = int(value)
            if sym.name == "load" and len(sym.arguments) == 4 and val > 0:
                a = sym.arguments
                # load(From, To, TR, P) = N
                loads[(str(a[0]), str(a[1]), str(a[2]), str(a[3]))] = val

        return {
            "route_freqs": route_freqs,
            "loads": loads,
            "high_exposure": high_exposure,
        }

    @staticmethod
    def _extract_stage2(model: clingo.Model, theory: ClingconTheory) -> dict:
        """Extract tripLoad from theory, shown atoms for counts."""
        trip_loads: dict[tuple[str, str, str, str, int], int] = {}
        used_trips: set[tuple[str, str, str, int]] = set()
        mono_count = 0
        concentrated_count = 0

        # tripLoad from theory assignments
        for sym, value in theory.assignment(model.thread_id):
            val = int(value)
            if sym.name == "tripLoad" and len(sym.arguments) == 5 and val > 0:
                a = sym.arguments
                key = (str(a[0]), str(a[1]), str(a[2]), str(a[3]), a[4].number)
                trip_loads[key] = val

        # Shown atoms for usedTrip, monoTrip, overloaded
        for sym in model.symbols(shown=True):
            a = sym.arguments
            if sym.name == "usedTrip" and len(a) == 4:
                used_trips.add((str(a[0]), str(a[1]), str(a[2]), a[3].number))
            elif sym.name == "monoTrip" and len(a) == 4:
                mono_count += 1
            elif sym.name == "overloaded" and len(a) == 5:
                concentrated_count += 1

        return {
            "trip_loads": trip_loads,
            "used_trips": used_trips,
            "mono_count": mono_count,
            "concentrated_count": concentrated_count,
        }
