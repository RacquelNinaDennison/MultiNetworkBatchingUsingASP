"""Two-stage naive solver — pure ASP stage 1 (flow) + stage 2 (packing).

Stage 1: Network flow + frequency assignment (minimise transport cost).
Stage 2: Per-trip bin packing with diversification (minimise used trips).

Supports multi-shot iterative bound tightening or single-shot mode.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from pathlib import Path

import clingo

from ..models import (
    TwoStageNaiveConfig,
    TwoStageResult,
    Stage1Result,
    Stage2Result,
    SolveMetadata,
    RouteFreq,
    TripLoad,
)
from .base import BaseSolver


ENCODING_DIR = Path(__file__).resolve().parent.parent / "encodings" / "twostage" / "naive"


class NaiveTwoStageSolver(BaseSolver):
    """Pure-ASP two-stage solver.

    Stage 1 solves aggregate network flow to assign routes and frequencies.
    Stage 2 distributes loads into per-trip packings with diversification.
    """

    def __init__(
        self,
        instance_path: str | Path,
        config: TwoStageNaiveConfig | None = None,
        stage1_encoding: str | Path | None = None,
        stage2_encoding: str | Path | None = None,
    ):
        super().__init__(instance_path)
        self.config = config or TwoStageNaiveConfig()
        self.encoding_stage1 = Path(stage1_encoding) if stage1_encoding else ENCODING_DIR / "stage1_flow.lp"
        self.encoding_stage2 = Path(stage2_encoding) if stage2_encoding else ENCODING_DIR / "stage2_packing.lp"

    # ─────────────────────────────────────────────────────────────────────
    # Domain facts
    # ─────────────────────────────────────────────────────────────────────

    def _generate_domain_facts(self) -> str:
        inst = self.instance
        max_items = inst.max_items_per_bin

        supply_by_part: dict[str, int] = defaultdict(int)
        for do in inst.demand_offers:
            if do.quantity > 0:
                supply_by_part[do.part] += do.quantity
        max_supply = max(supply_by_part.values()) if supply_by_part else 0

        lines: list[str] = []
        for i in range(max_items + 1):
            lines.append(f"numParts({i}).")
        for i in range(max_supply + 1):
            lines.append(f"numFlow({i}).")
        for i in range(self.config.max_freq + 1):
            lines.append(f"numFreq({i}).")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Stage 1: Network flow + frequency
    # ─────────────────────────────────────────────────────────────────────

    def _solve_stage1(self) -> Stage1Result | None:
        clingo_args: list[str] = [
            "-c", f"weight={self.config.weight}",
            "-c", f"exposure_n={self.config.exposure_n}",
        ]

        ctl = clingo.Control(clingo_args)
        ctl.load(str(self.encoding_stage1))
        ctl.load(str(self.instance_path))

        domain_facts = self._generate_domain_facts()
        ctl.add("domain", [], domain_facts)

        t0 = time.perf_counter()
        ctl.ground([("base", []), ("domain", [])])
        ground_time = time.perf_counter() - t0

        best: dict | None = None
        best_cost: int | None = None
        optimum = False
        trajectory: list[dict] = []

        timer = threading.Timer(self.config.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    best = self._extract_stage1(model)
                    best_cost = model.cost[0] if model.cost else None
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
            high_exposure=best["high_exposure"],
        )

    # ─────────────────────────────────────────────────────────────────────
    # Stage 2: Per-trip bin packing
    # ─────────────────────────────────────────────────────────────────────

    def _build_stage2_facts(self, stage1: Stage1Result) -> str:
        """Convert stage 1 results into facts that stage 2 encoding expects."""
        lines: list[str] = []

        # routeFreq facts
        for rf in stage1.route_freqs:
            lines.append(
                f"routeFreq({rf.origin},{rf.destination},{rf.transport},"
                f"{rf.frequency},{rf.total_capacity})."
            )

        # load facts
        for (f, t, tr, p), n in stage1.loads.items():
            lines.append(f"load({n},{p},{tr},{f},{t}).")

        return "\n".join(lines)

    def _solve_stage2(self, stage1: Stage1Result) -> Stage2Result | None:
        stage1_facts = self._build_stage2_facts(stage1)

        clingo_args: list[str] = [
            "-c", f"weight={self.config.weight}",
            "-c", f"hetero_on={self.config.hetero_on}",
            "-c", f"concentrated_on={self.config.concentrated_on}",
        ]

        ctl = clingo.Control(clingo_args)
        ctl.load(str(self.encoding_stage2))
        ctl.load(str(self.instance_path))
        ctl.add("stage1_output", [], stage1_facts)

        t0 = time.perf_counter()
        ctl.ground([("base", []), ("stage1_output", [])])
        ground_time = time.perf_counter() - t0

        best: dict | None = None
        best_cost: int | None = None
        optimum = False
        trajectory: list[dict] = []

        timer = threading.Timer(self.config.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    best = self._extract_stage2(model)
                    best_cost = model.cost[0] if model.cost else None
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

        return Stage2Result(
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
        if stage1 is None:
            return None

        stage2 = self._solve_stage2(stage1)
        if stage2 is None:
            return None

        return TwoStageResult(stage1=stage1, stage2=stage2)

    # ─────────────────────────────────────────────────────────────────────
    # Extraction helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_stage1(model: clingo.Model) -> dict:
        loads: dict[tuple[str, str, str, str], int] = {}
        route_freqs: list[dict] = []
        high_exposure: list[tuple[str, str, str, str]] = []

        for sym in model.symbols(shown=True):
            name = sym.name
            a = sym.arguments

            if name == "load" and len(a) == 5:
                n = a[0].number
                p = str(a[1])
                tr = str(a[2])
                f = str(a[3])
                t = str(a[4])
                if n > 0:
                    loads[(f, t, tr, p)] = n

            elif name == "routeFreq" and len(a) == 5:
                route_freqs.append({
                    "from": str(a[0]),
                    "to": str(a[1]),
                    "tr": str(a[2]),
                    "freq": a[3].number,
                    "total_cap": a[4].number,
                })

            elif name == "highExposure" and len(a) == 4:
                high_exposure.append(
                    (str(a[0]), str(a[1]), str(a[2]), str(a[3]))
                )

        return {
            "loads": loads,
            "route_freqs": route_freqs,
            "high_exposure": high_exposure,
        }

    @staticmethod
    def _extract_stage2(model: clingo.Model) -> dict:
        trip_loads: dict[tuple[str, str, str, str, int], int] = {}
        used_trips: set[tuple[str, str, str, int]] = set()
        mono_parts: set[tuple[str, str, str, str]] = set()
        concentrated: set[tuple[str, str, str, str, int]] = set()

        for sym in model.symbols(shown=True):
            name = sym.name
            a = sym.arguments

            if name == "tripLoad" and len(a) == 6:
                f, t, tr = str(a[0]), str(a[1]), str(a[2])
                p = str(a[3])
                q = a[4].number
                k = a[5].number
                if q > 0:
                    trip_loads[(f, t, tr, p, k)] = q

            elif name == "usedTrip" and len(a) == 4:
                used_trips.add(
                    (str(a[0]), str(a[1]), str(a[2]), a[3].number)
                )

            elif name == "monoTripPart" and len(a) == 4:
                mono_parts.add(
                    (str(a[0]), str(a[1]), str(a[2]), str(a[3]))
                )

            elif name == "concentratedLoad" and len(a) == 5:
                concentrated.add(
                    (str(a[0]), str(a[1]), str(a[2]), str(a[3]), a[4].number)
                )

        return {
            "trip_loads": trip_loads,
            "used_trips": used_trips,
            "mono_count": len(mono_parts),
            "concentrated_count": len(concentrated),
        }
