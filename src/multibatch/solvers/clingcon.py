"""Clingcon one-shot solver — constraint-programming encoding.

Uses ClingconTheory for integer CSP variables (flow, frequency).
Pack atoms come from shown atoms; flow and frequency come from
theory assignments.
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
    ClingconOneShotConfig,
    OneShotResult,
    SolveMetadata,
    PackAtom,
    FreqAtom,
    FlowAtom,
)
from .base import BaseSolver


ENCODING_DIR = Path(__file__).resolve().parent.parent / "encodings" / "clingcon"


class ClingconOneShotSolver(BaseSolver):
    """Clingcon one-shot solver using CSP variables for flow and frequency.

    The encoding uses &dom and &sum constraints for flow conservation
    and frequency-packing linkage. Often faster than pure ASP on larger instances.
    """

    def __init__(
        self,
        instance_path: str | Path,
        config: ClingconOneShotConfig | None = None,
        encoding_path: str | Path | None = None,
    ):
        super().__init__(instance_path)
        self.config = config or ClingconOneShotConfig()
        if encoding_path:
            self.encoding = Path(encoding_path)
        elif self.config.optimised:
            self.encoding = ENCODING_DIR / "optimised_clingcon_binpacking.lp"
        else:
            self.encoding = ENCODING_DIR / "clingcon_binpacking.lp"

    def _generate_domain_facts(self) -> str:
        """Compute bins and numParts facts from instance data."""
        inst = self.instance
        max_items = inst.max_items_per_bin

        lines: list[str] = []
        lines.append(f"bins(0..{self.config.num_bins}).")
        for i in range(max_items + 1):
            lines.append(f"numParts({i}).")
        return "\n".join(lines)

    def _compute_constants(self) -> dict[str, int]:
        """Compute -c flag values for clingcon."""
        inst = self.instance
        max_items = inst.max_items_per_bin

        supply_by_part: dict[str, int] = defaultdict(int)
        for do in inst.demand_offers:
            if do.quantity > 0:
                supply_by_part[do.part] += do.quantity
        max_supply = max(supply_by_part.values()) if supply_by_part else 0

        return {
            "numBins": self.config.num_bins,
            "maxItems": max(20, max_items),
            "maxFreq": max(self.config.max_freq, max_supply),
        }

    def solve(self) -> OneShotResult | None:
        """Run the clingcon solver. Returns OneShotResult or None if UNSAT."""
        if not self.encoding.exists():
            raise FileNotFoundError(f"Encoding not found: {self.encoding}")

        consts = self._compute_constants()
        clingo_args: list[str] = []
        for k, v in consts.items():
            clingo_args.extend(["-c", f"{k}={v}"])

        theory = ClingconTheory()
        ctl = clingo.Control(clingo_args)
        theory.register(ctl)

        domain_facts = self._generate_domain_facts()

        # Clingcon requires AST-level loading via ProgramBuilder
        with clingo.ast.ProgramBuilder(ctl) as builder:
            def on_rule(stm):
                theory.rewrite_ast(stm, builder.add)
            clingo.ast.parse_files(
                [str(self.encoding), str(self.instance_path)], on_rule
            )
            clingo.ast.parse_string(domain_facts, on_rule)

        t0 = time.perf_counter()
        ctl.ground([("base", [])])
        theory.prepare(ctl)
        ground_time = time.perf_counter() - t0

        best: dict | None = None
        best_cost: int | None = None
        optimum = False

        timer = threading.Timer(self.config.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    best = self._extract(model, theory)
                    best_cost = model.cost[0] if model.cost else None
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

        # Extract solver statistics
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

        if best is None:
            return None

        # Clingcon &minimize doesn't populate model.cost; compute from solution
        if best_cost is None and best["freq"]:
            route_dc = {
                (r.origin, r.destination, r.transport): r.distance * r.cost
                for r in self.instance.routes
            }
            best_cost = sum(
                fa.frequency * route_dc.get((fa.origin, fa.destination, fa.transport), 0)
                for fa in best["freq"]
                if fa.frequency > 0
            )

        return OneShotResult(
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
            ),
            pack=best["pack"],
            freq=best["freq"],
            flow=best["flow"],
        )

    @staticmethod
    def _extract(model: clingo.Model, theory: ClingconTheory) -> dict:
        """Extract pack from shown atoms, flow and frequency from theory assignments."""
        pack: list[PackAtom] = []
        freq: list[FreqAtom] = []
        flow: list[FlowAtom] = []

        # pack/6 from shown atoms
        for sym in model.symbols(shown=True):
            if sym.name == "pack" and len(sym.arguments) == 6:
                a = sym.arguments
                pack.append(PackAtom(
                    quantity=a[0].number,
                    part=str(a[1]),
                    bin_id=a[2].number,
                    origin=str(a[3]),
                    destination=str(a[4]),
                    transport=str(a[5]),
                ))

        # flow/3 and frequency/4 from theory (CSP) assignments
        for sym, value in theory.assignment(model.thread_id):
            val = int(value)
            a = sym.arguments

            if sym.name == "flow" and len(a) == 3:
                # flow(From, To, Part) = N
                flow.append(FlowAtom(
                    origin=str(a[0]),
                    destination=str(a[1]),
                    part=str(a[2]),
                    quantity=val,
                ))

            elif sym.name == "frequency" and len(a) == 4:
                # frequency(origin, dest, TR, ID) = F
                freq.append(FreqAtom(
                    bin_id=a[3].number,
                    origin=str(a[0]),
                    destination=str(a[1]),
                    transport=str(a[2]),
                    frequency=val,
                ))

        return {"pack": pack, "freq": freq, "flow": flow}
