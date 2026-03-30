#!/usr/bin/env python3
"""
run_clingcon.py — RunClingcon solver using clingcon constraint-programming encoding.

Uses the ClingconTheory to handle integer CSP variables for flow and
frequency, extracting their values from the theory assignment.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory

from .base_solver import BaseSolver


ENCODING_DIR = Path(__file__).resolve().parent.parent / "encoding" / "clingcon"


class RunClingcon(BaseSolver):

    def __init__(
        self,
        instance_path: str,
        num_bins: int = 1,
        time_limit: int = 30,
        max_freq: int = 20,
    ):
        super().__init__(instance_path, time_limit)
        self.num_bins = num_bins
        self.max_freq = max_freq
        self.encoding = ENCODING_DIR / "clingcon_binpacking.lp"

        if not self.encoding.exists():
            raise FileNotFoundError(f"Encoding not found: {self.encoding}")

    # ─────────────────────────────────────────────────────────────────────
    # Domain fact generation
    # ─────────────────────────────────────────────────────────────────────

    def _generate_domain_facts(self) -> str:
        """Compute numParts(0..N) facts from instance data."""
        data = self.instance_data
        max_cap  = max(data["transport_cap"].values())
        min_size = min(data["part_size"].values())
        max_items = max_cap // min_size

        lines: list[str] = []
        for i in range(max_items + 1):
            lines.append(f"numParts({i}).")
        return "\n".join(lines)

    def _compute_constants(self) -> dict[str, int]:
        """Compute -c flag values for clingcon."""
        data = self.instance_data
        max_cap  = max(data["transport_cap"].values())
        min_size = min(data["part_size"].values())
        max_items = max_cap // min_size

        # max total supply for any single part
        supply_by_part: dict[str, int] = defaultdict(int)
        for (part, _loc), d in data["demand_offer"].items():
            if d > 0:
                supply_by_part[part] += d
        max_supply = max(supply_by_part.values()) if supply_by_part else 0

        return {
            "numBins":  self.num_bins,
            "maxItems": max(20, max_items),
            "maxFreq":  max(self.max_freq, max_supply),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Solve
    # ─────────────────────────────────────────────────────────────────────

    def solve(self) -> dict | None:
        consts = self._compute_constants()
        clingo_args: list[str] = []
        for k, v in consts.items():
            clingo_args.extend(["-c", f"{k}={v}"])

        theory = ClingconTheory()
        ctl = clingo.Control(clingo_args)
        theory.register(ctl)

        domain_facts = self._generate_domain_facts()

        with clingo.ast.ProgramBuilder(ctl) as builder:
            def on_rule(stm):
                theory.rewrite_ast(stm, builder.add)
            clingo.ast.parse_files(
                [str(self.encoding), str(self.instance_path)], on_rule
            )
            clingo.ast.parse_string(domain_facts, on_rule)

        t0 = time.perf_counter()
        ctl.ground([("base", [])])
        ground_time = time.perf_counter() - t0
        theory.prepare(ctl)

        print(f"  Encoding : {self.encoding.name}")
        print(f"  Constants: {consts}")
        print(f"  Grounding: {ground_time:.3f}s")
        print(f"  Solving (up to {self.time_limit}s)...", end="", flush=True)

        best: dict | None = None
        optimum = False

        timer = threading.Timer(self.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    best = self._extract(model, theory)
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
    def _extract(model: clingo.Model, theory: ClingconTheory) -> dict:
        """Extract pack/6 from shown atoms, flow/3 and frequency/4 from
        theory assignments.  Returns the standard solution dict expected
        by checking.py (pack, freq, flow lists)."""
        atoms: dict[str, list] = {"pack": [], "freq": [], "flow": []}

        # pack/6 from shown atoms
        for sym in model.symbols(shown=True):
            if sym.name == "pack" and len(sym.arguments) == 6:
                a = sym.arguments
                atoms["pack"].append((
                    a[0].number,   # N
                    str(a[1]),     # P
                    a[2].number,   # ID
                    str(a[3]),     # From
                    str(a[4]),     # To
                    str(a[5]),     # TR
                ))

        # flow/3 and frequency/4 from theory (CSP) assignments
        for sym, value in theory.assignment(model.thread_id):
            val = int(value)
            a   = sym.arguments

            if sym.name == "flow" and len(a) == 3:
                # flow(From, To, Part) = N
                atoms["flow"].append((
                    str(a[0]), str(a[1]), str(a[2]), val
                ))

            elif sym.name == "frequency" and len(a) == 4:
                # frequency(origin, dest, TR, ID) = F
                # Map to checking.py format: (ID, From, To, TR, F)
                atoms["freq"].append((
                    a[3].number,   # ID
                    str(a[0]),     # From (origin)
                    str(a[1]),     # To (destination)
                    str(a[2]),     # TR
                    val,           # F
                ))

        return atoms

