#!/usr/bin/env python3
"""
run_naive.py — RunNaive solver using pure-ASP bin-packing encodings.

Supports both the basic (encoding_route.lp) and optimised
(optimised_encoding_route.lp) encodings.  Generates the required domain
facts (numParts, numFlow, numFreq) from the instance data at runtime.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from pathlib import Path

import clingo

from .base_solver import BaseSolver


ENCODING_DIR = Path(__file__).resolve().parent.parent / "encoding" / "naive"


class RunNaive(BaseSolver):

    def __init__(
        self,
        instance_path: str,
        num_bins: int = 1,
        optimised: bool = True,
        time_limit: int = 30,
        max_freq: int = 20,
    ):
        super().__init__(instance_path, time_limit)
        self.num_bins = num_bins
        self.optimised = optimised
        self.max_freq = max_freq

        if optimised:
            self.encoding = ENCODING_DIR / "optimised_encoding_route.lp"
        else:
            self.encoding = ENCODING_DIR / "encoding_route.lp"

        if not self.encoding.exists():
            raise FileNotFoundError(f"Encoding not found: {self.encoding}")

    # ─────────────────────────────────────────────────────────────────────
    # Domain fact generation
    # ─────────────────────────────────────────────────────────────────────

    def _generate_domain_facts(self) -> str:
        """Compute numParts/numFlow/numFreq (and bins for basic encoding)."""
        data = self.instance_data
        max_cap  = max(data["transport_cap"].values())
        min_size = min(data["part_size"].values())
        max_items = max_cap // min_size

        # max total supply for any single part
        supply_by_part: dict[str, int] = defaultdict(int)
        for (part, _loc), vals in data["demand_offer"].items():
            for d in vals:
                if d > 0:
                    supply_by_part[part] += d
        max_supply = max(supply_by_part.values()) if supply_by_part else 0

        lines: list[str] = []

        # basic encoding needs explicit bins facts
        if not self.optimised:
            for i in range(1, self.num_bins + 1):
                lines.append(f"bins({i}).")

        for i in range(max_items + 1):
            lines.append(f"numParts({i}).")
        for i in range(max_supply + 1):
            lines.append(f"numFlow({i}).")
        for i in range(self.max_freq + 1):
            lines.append(f"numFreq({i}).")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Solve
    # ─────────────────────────────────────────────────────────────────────

    def solve(self) -> dict | None:
        clingo_args: list[str] = []
        if self.optimised:
            clingo_args.extend(["-c", f"numBins={self.num_bins}"])

        ctl = clingo.Control(clingo_args)
        ctl.load(str(self.encoding))
        ctl.load(str(self.instance_path))

        domain_facts = self._generate_domain_facts()
        ctl.add("domain", [], domain_facts)

        t0 = time.perf_counter()
        ctl.ground([("base", []), ("domain", [])])
        ground_time = time.perf_counter() - t0

        print(f"  Encoding : {self.encoding.name}")
        print(f"  Grounding: {ground_time:.3f}s")
        print(f"  Solving (up to {self.time_limit}s)...", end="", flush=True)

        best: dict | None = None
        optimum = False

        timer = threading.Timer(self.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    best = self._extract(model)
                    if model.optimality_proven:
                        optimum = True
                        break
        except RuntimeError:
            pass
        finally:
            timer.cancel()

        total_time = time.perf_counter() - t0

        if optimum:
            print(f" OPTIMUM ({total_time:.3f}s)")
        elif best is not None:
            print(f" best model ({total_time:.3f}s)")
        else:
            print(f" no model ({total_time:.3f}s)")

        if best is not None:
            best["ground_time"] = round(ground_time, 3)
            best["total_time"]  = round(total_time, 3)
            best["optimum"]     = optimum

        return best

    # ─────────────────────────────────────────────────────────────────────
    # Model extraction
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract(model: clingo.Model) -> dict:
        """Extract pack/6, freq/5, flow/4 atoms from a Clingo model."""
        atoms: dict[str, list] = {"pack": [], "freq": [], "flow": []}

        for sym in model.symbols(shown=True):
            name = sym.name
            a    = sym.arguments

            if name == "pack" and len(a) == 6:
                atoms["pack"].append((
                    a[0].number,   # N
                    str(a[1]),     # P
                    a[2].number,   # ID
                    str(a[3]),     # From
                    str(a[4]),     # To
                    str(a[5]),     # TR
                ))
            elif name == "freq" and len(a) == 5:
                atoms["freq"].append((
                    a[0].number,   # ID
                    str(a[1]),     # From
                    str(a[2]),     # To
                    str(a[3]),     # TR
                    a[4].number,   # F
                ))
            elif name == "flow" and len(a) == 4:
                atoms["flow"].append((
                    str(a[0]),     # From
                    str(a[1]),     # To
                    str(a[2]),     # Part
                    a[3].number,   # N
                ))

        return atoms

