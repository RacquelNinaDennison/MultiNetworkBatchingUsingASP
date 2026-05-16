"""Naive one-shot solver — pure ASP bin-packing encoding."""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from pathlib import Path

import clingo

from ..models import (
    NaiveOneShotConfig,
    OneShotResult,
    SolveMetadata,
    PackAtom,
    FreqAtom,
    FlowAtom,
)
from .base import BaseSolver


ENCODING_DIR = Path(__file__).resolve().parent.parent / "encodings" / "naive"


class NaiveOneShotSolver(BaseSolver):
    """Pure-ASP one-shot solver using bin-packing encodings.

    Supports basic (encoding_route.lp) and optimised
    (optimised_encoding_route.lp) variants.
    """

    def __init__(
        self,
        instance_path: str | Path,
        config: NaiveOneShotConfig | None = None,
        encoding_path: str | Path | None = None,
    ):
        super().__init__(instance_path)
        self.config = config or NaiveOneShotConfig()

        if encoding_path:
            self.encoding = Path(encoding_path)
        elif self.config.optimised:
            self.encoding = ENCODING_DIR / "optimised_encoding_route.lp"
        else:
            self.encoding = ENCODING_DIR / "encoding_route.lp"

    def _generate_domain_facts(self) -> str:
        """Compute numParts/numFlow/numFreq domain facts from instance."""
        inst = self.instance
        max_items = inst.max_items_per_bin

        supply_by_part: dict[str, int] = defaultdict(int)
        for do in inst.demand_offers:
            if do.quantity > 0:
                supply_by_part[do.part] += do.quantity
        max_supply = max(supply_by_part.values()) if supply_by_part else 0

        lines: list[str] = []
        lines.append(f"bins(0..{self.config.num_bins}).")
        for i in range(max_items + 1):
            lines.append(f"numParts({i}).")
        for i in range(max_supply + 1):
            lines.append(f"numFlow({i}).")
        for i in range(self.config.max_freq + 1):
            lines.append(f"numFreq({i}).")

        return "\n".join(lines)

    def solve(self) -> OneShotResult | None:
        """Run the naive ASP solver. Returns OneShotResult or None if UNSAT."""
        if not self.encoding.exists():
            raise FileNotFoundError(f"Encoding not found: {self.encoding}")

        clingo_args: list[str] = []
        clingo_args.extend(["-c", f"numBins={self.config.num_bins}"])
        ctl = clingo.Control(clingo_args)
        ctl.load(str(self.encoding))
        ctl.load(str(self.instance_path))

        domain_facts = self._generate_domain_facts()
        ctl.add("domain", [], domain_facts)

        t0 = time.perf_counter()
        ctl.ground([("base", []), ("domain", [])])
        ground_time = time.perf_counter() - t0

        best: dict | None = None
        optimum = False

        timer = threading.Timer(self.config.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    best = self._extract(model)
                    if model.optimality_proven:
                        optimum = True
                        break
                solve_result = handle.get()
                if not optimum and solve_result.satisfiable:    
                    clingo_stats=ctl.statistics['solving']
                    optimum = True
        except RuntimeError:
            pass
        finally:
            timer.cancel()

        total_time = time.perf_counter() - t0

        if best is None:
            return None

        return OneShotResult(
            metadata=SolveMetadata(
                ground_time=round(ground_time, 3),
                total_time=round(total_time, 3),
                optimum=optimum,
                clingo_stats=clingo_stats,
                clingo_stats_grounding=ctl.statistics,
            ),
            pack=best["pack"],
            freq=best["freq"],
            flow=best["flow"],
        )

    @staticmethod
    def _extract(model: clingo.Model) -> dict:
        """Extract pack/freq/flow atoms from a Clingo model."""
        pack: list[PackAtom] = []
        freq: list[FreqAtom] = []
        flow: list[FlowAtom] = []

        for sym in model.symbols(shown=True):
            name = sym.name
            a = sym.arguments

            if name == "pack" and len(a) == 6:
                pack.append(PackAtom(
                    quantity=a[0].number,
                    part=str(a[1]),
                    bin_id=a[2].number,
                    origin=str(a[3]),
                    destination=str(a[4]),
                    transport=str(a[5]),
                ))
            elif name == "freq" and len(a) == 5:
                freq.append(FreqAtom(
                    bin_id=a[0].number,
                    origin=str(a[1]),
                    destination=str(a[2]),
                    transport=str(a[3]),
                    frequency=a[4].number,
                ))
            elif name == "flow" and len(a) == 4:
                flow.append(FlowAtom(
                    origin=str(a[0]),
                    destination=str(a[1]),
                    part=str(a[2]),
                    quantity=a[3].number,
                ))

        return {"pack": pack, "freq": freq, "flow": flow}
