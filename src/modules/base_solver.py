#!/usr/bin/env python3
"""
base_solver.py — Abstract base class for all solver pipelines.

Provides shared instance loading and check integration via checking.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path

import clingo

from .checking import (
    check_flow_conservation,
    check_capacity,
    check_flow_satisfaction,
)


class BaseSolver(ABC):
    """Solve → check → display pipeline shared by all solver variants."""

    def __init__(self, instance_path: str, time_limit: int = 30):
        self.instance_path = Path(instance_path)
        self.time_limit = time_limit
        self.instance_data = self._load_instance()

    # ─────────────────────────────────────────────────────────────────────
    # Instance loading
    # ─────────────────────────────────────────────────────────────────────

    def _load_instance(self) -> dict:
        """Parse instance .lp into Python structures.

        Returns a dict with keys:
            parts, locations, demand_offer, transport_cap,
            part_size, part_val, routes, route_cost
        """
        ctl = clingo.Control()
        ctl.load(str(self.instance_path))
        ctl.ground([("base", [])])

        data: dict = {
            "parts":         set(),
            "locations":     set(),
            "demand_offer":  {},   # (part, loc) -> int  (signed)
            "transport_cap": {},   # tr -> int
            "part_size":     {},   # part -> int
            "part_val":      {},   # part -> int
            "routes":        [],   # (from, to, tr, dist, cost)
            "route_cost":    {},   # (from, to, tr) -> cost
        }

        for atom in ctl.symbolic_atoms:
            sym  = atom.symbol
            name = sym.name
            args = sym.arguments

            if name == "part" and len(args) == 1:
                data["parts"].add(str(args[0]))

            elif name == "location" and len(args) == 1:
                data["locations"].add(str(args[0]))

            elif name == "demandOffer" and len(args) == 3:
                p, loc, d = str(args[0]), str(args[1]), args[2].number
                data["demand_offer"][(p, loc)] = d

            elif name == "transportCapacity" and len(args) == 2:
                data["transport_cap"][str(args[0])] = args[1].number

            elif name == "partSize" and len(args) == 2:
                data["part_size"][str(args[0])] = args[1].number

            elif name == "partVal" and len(args) == 2:
                data["part_val"][str(args[0])] = args[1].number

            elif name == "route" and len(args) == 5:
                fr   = str(args[0])
                to   = str(args[1])
                tr   = str(args[2])
                dist = args[3].number
                cost = args[4].number
                data["routes"].append((fr, to, tr, dist, cost))
                data["route_cost"][(fr, to, tr)] = cost

        return data

    # ─────────────────────────────────────────────────────────────────────
    # Solver (subclass-specific)
    # ─────────────────────────────────────────────────────────────────────

    @abstractmethod
    def solve(self) -> dict | None:
        """Run the solver.  Returns a solution dict or None if UNSAT.

        The solution dict must contain at least:
            pack : list[(N, P, ID, From, To, TR)]
            freq : list[(ID, From, To, TR, F)]
            flow : list[(From, To, Part, N)]
        """

    # ─────────────────────────────────────────────────────────────────────
    # Checking
    # ─────────────────────────────────────────────────────────────────────

    def check(self, solution: dict) -> bool:
        """Run all checks from checking.py.  Returns True if all pass."""
        checks = [
            ("Flow conservation",
             check_flow_conservation(solution, self.instance_data)),
            ("Bin capacity",
             check_capacity(solution, self.instance_data)),
            ("Flow satisfaction",
             check_flow_satisfaction(solution, self.instance_data)),
        ]

        passed = True
        for label, errors in checks:
            if errors:
                print(f"  [FAIL] {label}")
                for e in errors:
                    print(e)
                passed = False
            else:
                print(f"  [PASS] {label}")

        return passed

    # ─────────────────────────────────────────────────────────────────────
    # Full pipeline
    # ─────────────────────────────────────────────────────────────────────

    def run(self) -> int:
        """Solve -> check -> display.  Returns 0 on success, 1 on failure."""
        print("=" * 55)
        print("  SOLVING")
        print("=" * 55)

        result = self.solve()

        if result is None:
            print("\n  UNSATISFIABLE — no solution found.")
            return 1

        print()
        print("=" * 55)
        print("  VERIFICATION")
        print("=" * 55)

        passed = self.check(result)

        self.print_results(result, passed)
        return 0 if passed else 1

    def print_results(self, result: dict, checks_passed: bool) -> None:
        """Display packing, frequency, flow, and statistics."""
        inst = self.instance_data

        # ── Build lookups ─────────────────────────────────────────────
        # freq: (ID, From, To, TR) -> F
        freq_map: dict[tuple, int] = {}
        for (id_, fr, to, tr, f) in result["freq"]:
            freq_map[(id_, fr, to, tr)] = f

        # packing grouped by route -> bin -> {part: count}
        route_bins: dict[tuple, dict[int, dict[str, int]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for (n, p, id_, fr, to, tr) in result["pack"]:
            if n > 0:
                route_bins[(fr, to, tr)][id_][p] = n

        # flow grouped by arc -> {part: n}
        flows: dict[tuple, dict[str, int]] = defaultdict(dict)
        for (fr, to, p, n) in result["flow"]:
            if n > 0:
                flows[(fr, to)][p] = n

        # ── Packing & frequency ───────────────────────────────────────
        print()
        print("-" * 55)
        print("  PACKING & FREQUENCY")
        print("-" * 55)

        for (fr, to, tr) in sorted(route_bins.keys()):
            cap = inst["transport_cap"].get(tr, "?")
            print(f"  {fr} -> {to} via {tr} (cap={cap}):")

            for id_ in sorted(route_bins[(fr, to, tr)].keys()):
                parts = route_bins[(fr, to, tr)][id_]
                items = ", ".join(
                    f"{n}x{p}" for p, n in sorted(parts.items())
                )
                f = freq_map.get((id_, fr, to, tr), 0)
                size = sum(
                    n * inst["part_size"].get(p, 0)
                    for p, n in parts.items()
                )
                print(f"    Bin {id_}: [{items}]  freq={f}  "
                      f"(weight={size}/{cap})")
            print()

        # ── Flow ──────────────────────────────────────────────────────
        print("-" * 55)
        print("  FLOW")
        print("-" * 55)

        for (fr, to) in sorted(flows.keys()):
            parts = flows[(fr, to)]
            items = ", ".join(
                f"{p}={n}" for p, n in sorted(parts.items())
            )
            print(f"  {fr} -> {to}: {items}")

        # ── Statistics ────────────────────────────────────────────────
        nonzero_pack = [t for t in result["pack"] if t[0] > 0]
        nonzero_flow = [t for t in result["flow"] if t[3] > 0]

        print()
        print("-" * 55)
        print("  STATISTICS")
        print("-" * 55)
        print(f"  pack atoms    : {len(result['pack'])}  "
              f"(non-zero: {len(nonzero_pack)})")
        print(f"  freq atoms    : {len(result['freq'])}")
        print(f"  flow atoms    : {len(result['flow'])}  "
              f"(non-zero: {len(nonzero_flow)})")
        print(f"  ground time   : {result.get('ground_time', '?')}s")
        print(f"  total time    : {result.get('total_time', '?')}s")
        print(f"  optimum       : {result.get('optimum', '?')}")
        print()

        if checks_passed:
            print("All checks PASSED.")
        else:
            print("One or more checks FAILED.")
