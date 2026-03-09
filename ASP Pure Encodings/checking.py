#!/usr/bin/env python3
"""
checking.py – Solution verifier for multi-network batching ASP encodings.

Loads an encoding and a data instance via the Clingo API, solves to optimality,
then checks three invariants on the solution:

  1. Flow conservation  — for every (part, location), outflow − inflow equals
                          the net demand/supply declared in the instance.
  2. Bin capacity       — for every (bin, route), the total packed weight does
                          not exceed the transport resource's capacity.
  3. Flow satisfaction  — for every arc with positive required flow, the total
                          units dispatched across all bins (pack × freq) is at
                          least the required flow value.

Usage
-----
    uv run checking.py --encoding encodings/encoding_route.lp \\
                       --instance  data/instances.lp

    uv run checking.py --encoding encodings/optimised_encoding.lp \\
                       --instance  data/instances.lp \\
                       --bins 2
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import clingo


# ─────────────────────────────────────────────────────────────────────────────
# Instance extraction
# ─────────────────────────────────────────────────────────────────────────────

def load_instance(path: str) -> dict:
    """Parse instance facts into Python structures using the Clingo API.

    Returns a dict with keys:
        parts            : set[str]
        locations        : set[str]
        demand_offer     : dict[(part, loc), int]   – signed; positive = supply
        transport_cap    : dict[tr, int]
        part_size        : dict[part, int]
        routes           : list[(from, to, tr, dist, cost)]
    """
    ctl = clingo.Control()
    ctl.load(path)
    ctl.ground([("base", [])])

    instance: dict = {
        "parts":         set(),
        "locations":     set(),
        "demand_offer":  {},
        "transport_cap": {},
        "part_size":     {},
        "routes":        [],
    }

    for atom in ctl.symbolic_atoms:
        sym  = atom.symbol
        name = sym.name
        args = sym.arguments

        if name == "part" and len(args) == 1:
            instance["parts"].add(str(args[0]))

        elif name == "location" and len(args) == 1:
            instance["locations"].add(str(args[0]))

        elif name == "demandOffer" and len(args) == 3:
            p, l, d = str(args[0]), str(args[1]), args[2].number
            instance["demand_offer"][(p, l)] = d

        elif name == "transportCapacity" and len(args) == 2:
            tr, c = str(args[0]), args[1].number
            instance["transport_cap"][tr] = c

        elif name == "partSize" and len(args) == 2:
            p, s = str(args[0]), args[1].number
            instance["part_size"][p] = s

        elif name == "route" and len(args) == 5:
            fr   = str(args[0])
            to   = str(args[1])
            tr   = str(args[2])
            dist = args[3].number
            cost = args[4].number
            instance["routes"].append((fr, to, tr, dist, cost))

    return instance


# ─────────────────────────────────────────────────────────────────────────────
# Solving
# ─────────────────────────────────────────────────────────────────────────────

def _parse_model(model: clingo.Model) -> dict:
    """Extract pack/freq/flow atoms from a Clingo model into Python tuples."""
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


def solve(encoding: str, instance: str, num_bins: int) -> dict | None:
    """Run the solver and return the (first) optimal answer set, or None if UNSAT."""
    ctl = clingo.Control(["-c", f"numBins={num_bins}"])
    ctl.load(encoding)
    ctl.load(instance)
    ctl.ground([("base", [])])

    last_model: dict | None = None

    with ctl.solve(yield_=True) as handle:
        for model in handle:
            last_model = _parse_model(model)
            if model.optimality_proven:
                break

    return last_model


# ─────────────────────────────────────────────────────────────────────────────
# Checkers
# ─────────────────────────────────────────────────────────────────────────────

def check_flow_conservation(solution: dict, instance: dict) -> list[str]:
    """
    For every (part, location) pair, verify:
        outflow(P, L) − inflow(P, L) = netDemandSupply(P, L)

    where netDemandSupply(P, L) = demandOffer(P, L) if declared, else 0.
    """
    errors: list[str] = []

    # Build outflow / inflow maps indexed by (part, location)
    outflow: dict[tuple, int] = defaultdict(int)
    inflow:  dict[tuple, int] = defaultdict(int)

    for (fr, to, part, n) in solution["flow"]:
        outflow[(part, fr)] += n
        inflow[ (part, to)] += n

    for part in instance["parts"]:
        for loc in instance["locations"]:
            ds      = instance["demand_offer"].get((part, loc), 0)
            net     = outflow[(part, loc)] - inflow[(part, loc)]
            if net != ds:
                errors.append(
                    f"  flow conservation FAIL  part={part} loc={loc}: "
                    f"outflow({outflow[(part,loc)]}) − inflow({inflow[(part,loc)]}) "
                    f"= {net}  ≠  netDemandSupply={ds}"
                )

    return errors


def check_capacity(solution: dict, instance: dict) -> list[str]:
    """
    For every (bin, route) combination, verify:
        Σ N * partSize(P)  ≤  transportCapacity(TR)
    """
    errors: list[str] = []

    # Aggregate packed weight per (ID, From, To, TR)
    weight: dict[tuple, int] = defaultdict(int)
    for (n, p, id_, fr, to, tr) in solution["pack"]:
        size = instance["part_size"].get(p, 0)
        weight[(id_, fr, to, tr)] += n * size

    for (id_, fr, to, tr), total in weight.items():
        cap = instance["transport_cap"].get(tr)
        if cap is None:
            errors.append(
                f"  capacity FAIL  bin={id_} route=({fr}→{to},{tr}): "
                f"unknown transport resource '{tr}'"
            )
        elif total > cap:
            errors.append(
                f"  capacity FAIL  bin={id_} route=({fr}→{to},{tr}): "
                f"packed weight {total} > capacity {cap}"
            )

    return errors


def check_flow_satisfaction(solution: dict, instance: dict) -> list[str]:
    """
    For every arc (From, To, Part) with flow value > 0, verify:
        Σ_{bins, TR}  pack(N, P, ID, From, To, TR) * freq(ID, From, To, TR, F)  ≥  flow value
    """
    errors: list[str] = []

    # Index freq by (ID, From, To, TR) → F
    freq_map: dict[tuple, int] = {}
    for (id_, fr, to, tr, f) in solution["freq"]:
        freq_map[(id_, fr, to, tr)] = f

    # Index pack by (P, ID, From, To, TR) → N
    pack_map: dict[tuple, int] = {}
    for (n, p, id_, fr, to, tr) in solution["pack"]:
        pack_map[(p, id_, fr, to, tr)] = n

    # Collect all (ID, TR) combinations per route (From, To)
    bins_per_route: dict[tuple, list[tuple]] = defaultdict(list)
    for (id_, fr, to, tr, _) in solution["freq"]:
        bins_per_route[(fr, to)].append((id_, tr))

    for (fr, to, part, value) in solution["flow"]:
        if value <= 0:
            continue

        dispatched = 0
        for (id_, tr) in bins_per_route.get((fr, to), []):
            n = pack_map.get((part, id_, fr, to, tr), 0)
            f = freq_map.get((id_, fr, to, tr), 0)
            dispatched += n * f

        if dispatched < value:
            errors.append(
                f"  flow satisfaction FAIL  arc=({fr}→{to}) part={part}: "
                f"dispatched {dispatched} < required flow {value}"
            )

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Reporting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _report(label: str, errors: list[str]) -> bool:
    """Print check result. Returns True if the check passed."""
    if errors:
        print(f"  [FAIL] {label}")
        for e in errors:
            print(e)
        return False
    print(f"  [PASS] {label}")
    return True


def _print_solution_summary(solution: dict) -> None:
    print(f"  pack atoms : {len(solution['pack'])}")
    print(f"  freq atoms : {len(solution['freq'])}")
    print(f"  flow atoms : {len(solution['flow'])}")

    nonzero_flow = [(f, t, p, n) for (f, t, p, n) in solution["flow"] if n > 0]
    nonzero_pack = [(n, p, id_, f, t, tr) for (n, p, id_, f, t, tr) in solution["pack"] if n > 0]
    print(f"  non-zero flow : {len(nonzero_flow)}")
    print(f"  non-zero pack : {len(nonzero_pack)}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that an ASP multi-batching encoding produces a valid solution "
            "for a given instance, checking flow conservation, bin capacity, and "
            "flow satisfaction."
        )
    )
    parser.add_argument(
        "--encoding", "-e",
        required=True,
        help="Path to the encoding .lp file.",
    )
    parser.add_argument(
        "--instance", "-i",
        required=True,
        help="Path to the instance .lp file.",
    )
    parser.add_argument(
        "--bins", "-b",
        type=int,
        default=1,
        help="Number of bins (sets the numBins constant, default: 1).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    encoding_path = Path(args.encoding)
    instance_path = Path(args.instance)

    if not encoding_path.exists():
        print(f"Error: encoding file not found: {encoding_path}", file=sys.stderr)
        return 1
    if not instance_path.exists():
        print(f"Error: instance file not found: {instance_path}", file=sys.stderr)
        return 1

    print(f"Encoding : {encoding_path}")
    print(f"Instance : {instance_path}")
    print(f"Bins     : {args.bins}")
    print()

    # ── Load instance facts ──────────────────────────────────────────────────
    print("Loading instance facts …")
    instance = load_instance(str(instance_path))
    print(f"  parts          : {sorted(instance['parts'])}")
    print(f"  locations      : {sorted(instance['locations'])}")
    print(f"  routes         : {len(instance['routes'])}")
    print(f"  demand/supply  : {dict(sorted(instance['demand_offer'].items()))}")
    print()

    # ── Solve ────────────────────────────────────────────────────────────────
    print("Solving …")
    solution = solve(str(encoding_path), str(instance_path), args.bins)

    if solution is None:
        print("  Result: UNSATISFIABLE — no solution to check.")
        return 1

    print("  Result: solution found")
    _print_solution_summary(solution)
    print()

    # ── Verify ───────────────────────────────────────────────────────────────
    print("Running checks …")
    fc_errors  = check_flow_conservation(solution, instance)
    cap_errors = check_capacity(solution, instance)
    fs_errors  = check_flow_satisfaction(solution, instance)

    passed = all([
        _report("Flow conservation", fc_errors),
        _report("Bin capacity",      cap_errors),
        _report("Flow satisfaction", fs_errors),
    ])
    print()

    if passed:
        print("All checks PASSED.")
        return 0
    else:
        print("One or more checks FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
