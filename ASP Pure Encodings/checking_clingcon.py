#!/usr/bin/env python3
"""
checking_clingcon.py – Solution verifier for the ClinGcon hybrid encoding
                       (encoding_alternative.lp).

Loads the encoding and a data instance via the ClingconTheory API, solves to
optimality, then checks three invariants:

  1. Flow conservation  — for every (part, location), outflow − inflow equals
                          the net demand/supply declared in the instance.
  2. Bin capacity       — for every (bin, route), the total packed weight does
                          not exceed the transport resource's capacity.
  3. Flow satisfaction  — for every arc with positive CSP flow value, the total
                          units dispatched (pack × frequency) equals the flow.

The ClinGcon encoding uses theory atoms for flow and frequency; pack remains a
regular ASP atom.  CSP variable values are read from
theory.assignment(model.thread_id).

Usage
-----
    uv run checking_clingcon.py --encoding encodings/encoding_alternative.lp \\
                                --instance  data/series_D/L06_P02_TR2_s1.lp

    uv run checking_clingcon.py --encoding encodings/encoding_alternative.lp \\
                                --instance  data/series_D/L06_P02_TR2_s1.lp \\
                                --bins 2
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory


# ── Adapter: encoding_alternative uses transportResource/1 but instances only
#    declare transportCapacity/2.  This rule is injected as a string so we do
#    not need to touch the encoding or instance files. ────────────────────────
_ADAPTER = "transportResource(TR) :- transportCapacity(TR, _)."


# ─────────────────────────────────────────────────────────────────────────────
# Instance loading
# ─────────────────────────────────────────────────────────────────────────────

def load_instance(path: str) -> dict:
    """Parse instance facts into Python structures.

    Returns a dict with keys:
        parts          : set[str]
        locations      : set[str]
        demand_offer   : dict[(part, loc), int]  – signed; positive = supply
        transport_cap  : dict[tr, int]
        part_size      : dict[part, int]
        routes         : list[(from, to, tr, dist, cost)]
        max_freq       : int  – upper bound of numFreq range (used as maxFreq constant)
        max_items      : int  – upper bound of numParts range (used as maxItems constant)
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
        "max_freq":      0,
        "max_items":     0,
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
            instance["routes"].append((
                str(args[0]), str(args[1]), str(args[2]),
                args[3].number, args[4].number,
            ))

        elif name == "numFreq" and len(args) == 1:
            # numFreq(0..N) expands to individual atoms; take the maximum
            instance["max_freq"] = max(instance["max_freq"], args[0].number)

        elif name == "numParts" and len(args) == 1:
            instance["max_items"] = max(instance["max_items"], args[0].number)

    return instance


# ─────────────────────────────────────────────────────────────────────────────
# Solving
# ─────────────────────────────────────────────────────────────────────────────

def _parse_model(model: clingo.Model, theory: ClingconTheory) -> dict:
    """Extract pack atoms and CSP assignments from the model.

    Returns a dict with keys:
        pack       : list[(N, P, ID, src, dst, TR)]
        flow       : dict[(src, dst, part), int]
        frequency  : dict[(src, dst, TR, bin_id), int]

    Notes on encoding_alternative argument ordering
    -----------------------------------------------
    The encoding uses confusingly swapped variable names in rules that match
    routes, e.g. ``route(To,From,TR,_,_)`` where ``To`` binds to the *first*
    arg of route (= actual source) and ``From`` to the second (= actual
    destination).  Despite this, all three atoms are stored here with
    (actual_source, actual_destination, ...) ordering so the checker logic is
    straightforward.

    Specifically:
        pack(N, P, ID, To, From, TR)  →  (N, P, ID, src=args[3], dst=args[4], TR)
        frequency(To, From, TR, ID)   →  (src=args[0], dst=args[1], TR, ID)
        flow(From, To, P)             →  (src=args[0], dst=args[1], P)
    """
    solution: dict = {
        "pack":      [],
        "flow":      {},
        "frequency": {},
    }

    # Regular ASP atom: pack/6
    for sym in model.symbols(shown=True):
        if sym.name == "pack" and len(sym.arguments) == 6:
            a = sym.arguments
            solution["pack"].append((
                a[0].number,  # N  (items per trip)
                str(a[1]),    # P  (part)
                a[2].number,  # ID (bin index)
                str(a[3]),    # src — encoding variable name "To", but binds to route's first arg
                str(a[4]),    # dst — encoding variable name "From", but binds to route's second arg
                str(a[5]),    # TR (transport resource)
            ))

    # CSP variables via theory assignment
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "flow" and len(sym.arguments) == 3:
            src  = str(sym.arguments[0])
            dst  = str(sym.arguments[1])
            part = str(sym.arguments[2])
            solution["flow"][(src, dst, part)] = val

        elif sym.name == "frequency" and len(sym.arguments) == 4:
            # frequency(To, From, TR, ID): To=src, From=dst (same swap as pack)
            src    = str(sym.arguments[0])
            dst    = str(sym.arguments[1])
            tr     = str(sym.arguments[2])
            bin_id = sym.arguments[3].number
            solution["frequency"][(src, dst, tr, bin_id)] = val

    return solution


def solve(encoding: str, instance: str, num_bins: int, instance_data: dict) -> dict | None:
    """Run the ClinGcon solver and return the optimal answer set, or None if UNSAT."""
    max_freq  = instance_data["max_freq"]
    max_items = instance_data["max_items"]

    theory = ClingconTheory()
    ctl = clingo.Control([
        "-c", f"numBins={num_bins}",
        "-c", f"maxFreq={max_freq}",
        "-c", f"maxItems={max_items}",
    ])
    theory.register(ctl)

    # AST rewriting is required so that theory atoms are processed correctly
    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)

        clingo.ast.parse_string(_ADAPTER, on_rule)
        clingo.ast.parse_files([encoding, instance], on_rule)

    ctl.ground([("base", [])])
    theory.prepare(ctl)

    last_model: dict | None = None

    with ctl.solve(yield_=True) as handle:
        for model in handle:
            theory.on_model(model)
            last_model = _parse_model(model, theory)
            if model.optimality_proven:
                break

    return last_model


# ─────────────────────────────────────────────────────────────────────────────
# Checkers
# ─────────────────────────────────────────────────────────────────────────────

def check_flow_conservation(solution: dict, instance: dict) -> list[str]:
    """For every (part, location), verify outflow − inflow = netDemandSupply."""
    errors: list[str] = []

    outflow: dict[tuple, int] = defaultdict(int)
    inflow:  dict[tuple, int] = defaultdict(int)

    for (src, dst, part), val in solution["flow"].items():
        outflow[(part, src)] += val
        inflow[ (part, dst)] += val

    for part in instance["parts"]:
        for loc in instance["locations"]:
            expected = instance["demand_offer"].get((part, loc), 0)
            actual   = outflow[(part, loc)] - inflow[(part, loc)]
            if actual != expected:
                errors.append(
                    f"  flow conservation FAIL  part={part} loc={loc}: "
                    f"outflow({outflow[(part,loc)]}) − inflow({inflow[(part,loc)]}) "
                    f"= {actual}  ≠  netDemandSupply={expected}"
                )

    return errors


def check_capacity(solution: dict, instance: dict) -> list[str]:
    """For every (bin, route), verify packed weight ≤ transport capacity."""
    errors: list[str] = []

    weight: dict[tuple, int] = defaultdict(int)
    for (n, p, bin_id, src, dst, tr) in solution["pack"]:
        size = instance["part_size"].get(p, 0)
        weight[(bin_id, src, dst, tr)] += n * size

    for (bin_id, src, dst, tr), total in weight.items():
        cap = instance["transport_cap"].get(tr)
        if cap is None:
            errors.append(
                f"  capacity FAIL  bin={bin_id} route=({src}→{dst},{tr}): "
                f"unknown transport resource '{tr}'"
            )
        elif total > cap:
            errors.append(
                f"  capacity FAIL  bin={bin_id} route=({src}→{dst},{tr}): "
                f"packed weight {total} > capacity {cap}"
            )

    return errors


def check_flow_satisfaction(solution: dict, instance: dict) -> list[str]:
    """For every arc with positive CSP flow, verify dispatched units match."""
    errors: list[str] = []

    # Index pack by (P, bin_id, src, dst, TR) → N
    pack_map: dict[tuple, int] = {}
    for (n, p, bin_id, src, dst, tr) in solution["pack"]:
        pack_map[(p, bin_id, src, dst, tr)] = n

    # Collect all (bin_id, TR) combos seen per route (src, dst)
    bins_per_route: dict[tuple, list[tuple]] = defaultdict(list)
    for (src, dst, tr, bin_id) in solution["frequency"]:
        bins_per_route[(src, dst)].append((bin_id, tr))

    for (src, dst, part), flow_val in solution["flow"].items():
        if flow_val <= 0:
            continue

        dispatched = 0
        for (bin_id, tr) in bins_per_route.get((src, dst), []):
            n = pack_map.get((part, bin_id, src, dst, tr), 0)
            f = solution["frequency"].get((src, dst, tr, bin_id), 0)
            dispatched += n * f

        if dispatched != flow_val:
            errors.append(
                f"  flow satisfaction FAIL  arc=({src}→{dst}) part={part}: "
                f"dispatched {dispatched} ≠ flow {flow_val}"
            )

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def _report(label: str, errors: list[str]) -> bool:
    if errors:
        print(f"  [FAIL] {label}")
        for e in errors:
            print(e)
        return False
    print(f"  [PASS] {label}")
    return True


def _print_solution_summary(solution: dict) -> None:
    nonzero_flow = {k: v for k, v in solution["flow"].items() if v > 0}
    nonzero_freq = {k: v for k, v in solution["frequency"].items() if v > 0}
    nonzero_pack = [(n, p, b, s, d, tr) for (n, p, b, s, d, tr) in solution["pack"] if n > 0]

    print(f"  pack atoms         : {len(solution['pack'])}")
    print(f"  flow CSP vars      : {len(solution['flow'])} total, "
          f"{len(nonzero_flow)} non-zero")
    print(f"  frequency CSP vars : {len(solution['frequency'])} total, "
          f"{len(nonzero_freq)} non-zero")
    print(f"  non-zero pack      : {len(nonzero_pack)}")

    if nonzero_flow:
        print("  non-zero flows:")
        for (src, dst, part), val in sorted(nonzero_flow.items()):
            print(f"    flow({src},{dst},{part}) = {val}")

    if nonzero_freq:
        print("  non-zero frequencies:")
        for (src, dst, tr, bin_id), val in sorted(nonzero_freq.items()):
            print(f"    frequency({src},{dst},{tr},{bin_id}) = {val}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that the ClinGcon multi-batching encoding "
            "(encoding_alternative.lp) produces a valid solution, checking "
            "flow conservation, bin capacity, and flow satisfaction."
        )
    )
    parser.add_argument("--encoding", "-e", required=True,
                        help="Path to encoding_alternative.lp")
    parser.add_argument("--instance", "-i", required=True,
                        help="Path to the instance .lp file")
    parser.add_argument("--bins", "-b", type=int, default=1,
                        help="Number of bins (numBins constant, default: 1)")
    return parser


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    encoding_path = Path(args.encoding)
    instance_path = Path(args.instance)

    if not encoding_path.exists():
        print(f"Error: encoding not found: {encoding_path}", file=sys.stderr)
        return 1
    if not instance_path.exists():
        print(f"Error: instance not found: {instance_path}", file=sys.stderr)
        return 1

    print(f"Encoding : {encoding_path}")
    print(f"Instance : {instance_path}")
    print(f"Bins     : {args.bins}")
    print()

    # Load instance facts
    print("Loading instance facts ...")
    instance = load_instance(str(instance_path))
    print(f"  parts          : {sorted(instance['parts'])}")
    print(f"  locations      : {sorted(instance['locations'])}")
    print(f"  routes         : {len(instance['routes'])}")
    print(f"  demand/supply  : {dict(sorted(instance['demand_offer'].items()))}")
    print(f"  maxFreq        : {instance['max_freq']}")
    print(f"  maxItems       : {instance['max_items']}")
    print()

    # Solve
    print("Solving (ClinGcon) ...")
    solution = solve(str(encoding_path), str(instance_path), args.bins, instance)

    if solution is None:
        print("  Result: UNSATISFIABLE — no solution to check.")
        return 1

    print("  Result: solution found")
    _print_solution_summary(solution)
    print()

    # Verify
    print("Running checks ...")
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
