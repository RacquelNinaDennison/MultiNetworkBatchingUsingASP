#!/usr/bin/env python3
"""
verify_solution.py — Quality control checker for two-stage solutions
=====================================================================

Verifies that a Stage 1 + Stage 2 solution satisfies all hard constraints:

1. Flow conservation (Stage 1): at every node, inflow - outflow = net demand
2. Aggregate capacity (Stage 1): total load volume per arc <= freq × capacity
3. Per-item feasibility (Stage 1): each part unit fits in one trip
4. Load conservation (Stage 2): all units assigned to trips sum to Stage 1 load
5. Per-trip capacity (Stage 2): each trip's total volume <= transport capacity
6. Demand satisfaction: total supply reaching each sink meets its demand

Usage
-----
    # Run the two-stage pipeline and verify the output:
    uv run verify_solution.py --instance data.lp --cap-divide 1

    # Verify with a specific Stage 2 encoding:
    uv run verify_solution.py --instance data.lp --cap-divide 1 \\
        --stage2 stage2_packing.lp
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory

from run_two_stage import (
    load_instance_data,
    solve_stage1,
    build_stage2_facts,
    solve_stage2,
    _extract_stage2,
)


HERE = Path(__file__).parent


def parse_instance_full(path: str) -> dict:
    """Parse instance to get demands, routes, capacities, and part sizes."""
    ctl = clingo.Control()
    ctl.load(path)
    ctl.ground([("base", [])])

    data = {
        "demands": {},          # (part, loc) -> demand (positive)
        "offers": {},           # (part, loc) -> offer (positive)
        "transport_cap": {},    # tr -> capacity
        "part_size": {},        # part -> size
        "routes": {},           # (from, to, tr) -> (dist, cost)
    }

    for atom in ctl.symbolic_atoms:
        sym = atom.symbol
        name = sym.name
        args = sym.arguments

        if name == "demandOffer" and len(args) == 3:
            part, loc, val = str(args[0]), str(args[1]), args[2].number
            if val < 0:
                data["demands"][(part, loc)] = -val
            elif val > 0:
                data["offers"][(part, loc)] = val

        elif name == "transportCapacity" and len(args) == 2:
            data["transport_cap"][str(args[0])] = args[1].number

        elif name == "partSize" and len(args) == 2:
            data["part_size"][str(args[0])] = args[1].number

        elif name == "route" and len(args) == 5:
            f, t, tr = str(args[0]), str(args[1]), str(args[2])
            data["routes"][(f, t, tr)] = (args[3].number, args[4].number)

    return data


# ─────────────────────────────────────────────────────────────────────────
# Stage 1 verification
# ─────────────────────────────────────────────────────────────────────────

def verify_stage1(stage1: dict, instance: dict) -> list[str]:
    """Verify Stage 1 solution against hard constraints."""
    errors = []
    warnings = []

    loads = stage1["loads"]       # (from, to, tr, part) -> quantity
    route_freqs = stage1["route_freqs"]  # list of dicts

    # Build frequency lookup: (from, to, tr) -> {freq, total_cap}
    freq_lookup = {}
    for rf in route_freqs:
        key = (rf["from"], rf["to"], rf["tr"])
        freq_lookup[key] = rf

    # ── Check 1: Flow conservation ──────────────────────────────
    # For each part and location, inflow - outflow must equal net demand

    # Compute net demand at each location for each part
    parts = set()
    locations = set()
    net_demand = defaultdict(int)  # (part, loc) -> net demand

    for (part, loc), d in instance["demands"].items():
        net_demand[(part, loc)] += d
        parts.add(part)
        locations.add(loc)

    for (part, loc), o in instance["offers"].items():
        net_demand[(part, loc)] -= o
        parts.add(part)
        locations.add(loc)

    # Compute inflow and outflow from loads
    inflow = defaultdict(int)   # (part, loc) -> total units flowing in
    outflow = defaultdict(int)  # (part, loc) -> total units flowing out

    for (f, t, tr, part), qty in loads.items():
        outflow[(part, f)] += qty
        inflow[(part, t)] += qty
        parts.add(part)
        locations.add(f)
        locations.add(t)

    for part in parts:
        for loc in locations:
            net = inflow[(part, loc)] - outflow[(part, loc)]
            expected = net_demand.get((part, loc), 0)
            if net != expected:
                errors.append(
                    f"FLOW CONSERVATION VIOLATED: {part} at {loc}: "
                    f"inflow={inflow[(part, loc)]}, outflow={outflow[(part, loc)]}, "
                    f"net={net}, expected={expected}"
                )

    # ── Check 2: Aggregate capacity ─────────────────────────────
    # Total volume on each arc must not exceed freq × per-trip capacity

    arc_volumes = defaultdict(int)  # (from, to, tr) -> total volume
    for (f, t, tr, part), qty in loads.items():
        size = instance["part_size"].get(part, 0)
        arc_volumes[(f, t, tr)] += size * qty

    for (f, t, tr), vol in arc_volumes.items():
        rf = freq_lookup.get((f, t, tr))
        if rf is None:
            errors.append(
                f"LOAD ON INACTIVE ARC: {f}→{t} via {tr} has load but no routeFreq"
            )
            continue
        cap = instance["transport_cap"].get(tr, 0)
        total_cap = cap * rf["freq"]
        if vol > total_cap:
            errors.append(
                f"AGGREGATE CAPACITY EXCEEDED: {f}→{t} via {tr}: "
                f"volume={vol}, capacity={total_cap} "
                f"(cap={cap} × freq={rf['freq']})"
            )

    # ── Check 3: Per-item feasibility ───────────────────────────
    # Each part must physically fit in one trip of its transport resource

    for (f, t, tr, part), qty in loads.items():
        size = instance["part_size"].get(part, 0)
        cap = instance["transport_cap"].get(tr, 0)
        if size > cap:
            errors.append(
                f"PART TOO LARGE: {part} (size={size}) > {tr} capacity ({cap}) "
                f"on {f}→{t}"
            )

    # ── Check 4: Demand satisfaction ────────────────────────────
    # Total arriving supply at each sink must meet demand

    for (part, loc), demand in instance["demands"].items():
        supply = inflow[(part, loc)]
        if supply < demand:
            errors.append(
                f"DEMAND NOT MET: {part} at {loc}: "
                f"supply={supply}, demand={demand}, shortfall={demand - supply}"
            )
        elif supply > demand:
            # Excess supply at a sink — might be transit, check if outflow accounts for it
            excess = supply - demand
            out = outflow[(part, loc)]
            if out < excess:
                warnings.append(
                    f"EXCESS SUPPLY: {part} at {loc}: supply={supply}, "
                    f"demand={demand}, outflow={out}"
                )

    return errors


# ─────────────────────────────────────────────────────────────────────────
# Stage 2 verification
# ─────────────────────────────────────────────────────────────────────────

def verify_stage2(stage2: dict, stage1: dict, instance: dict) -> list[str]:
    """Verify Stage 2 solution against hard constraints."""
    errors = []

    trip_loads = stage2["trip_loads"]  # (from, to, tr, part, trip_k) -> quantity
    route_freqs = stage1["route_freqs"]

    # Build Stage 1 load lookup
    s1_loads = stage1["loads"]  # (from, to, tr, part) -> quantity

    # Build frequency lookup
    freq_lookup = {}
    for rf in route_freqs:
        key = (rf["from"], rf["to"], rf["tr"])
        freq_lookup[key] = rf

    # ── Check 1: Load conservation ──────────────────────────────
    # For each (from, to, tr, part), sum of tripLoad across all trips
    # must equal the Stage 1 load

    arc_part_totals = defaultdict(int)
    for (f, t, tr, part, k), qty in trip_loads.items():
        arc_part_totals[(f, t, tr, part)] += qty

    # Check that Stage 2 totals match Stage 1
    for (f, t, tr, part), s1_qty in s1_loads.items():
        s2_qty = arc_part_totals.get((f, t, tr, part), 0)
        if s2_qty != s1_qty:
            errors.append(
                f"LOAD CONSERVATION VIOLATED: {f}→{t} via {tr}, {part}: "
                f"Stage1={s1_qty}, Stage2 sum={s2_qty}"
            )

    # Check for Stage 2 loads that don't exist in Stage 1
    for (f, t, tr, part), s2_qty in arc_part_totals.items():
        if (f, t, tr, part) not in s1_loads:
            errors.append(
                f"UNEXPECTED LOAD: {f}→{t} via {tr}, {part}: "
                f"Stage2 has {s2_qty} units but Stage1 has no load"
            )

    # ── Check 2: Per-trip capacity ──────────────────────────────
    # Each trip's total volume must not exceed transport capacity

    trip_volumes = defaultdict(int)  # (from, to, tr, trip_k) -> total volume
    for (f, t, tr, part, k), qty in trip_loads.items():
        size = instance["part_size"].get(part, 0)
        trip_volumes[(f, t, tr, k)] += size * qty

    for (f, t, tr, k), vol in trip_volumes.items():
        cap = instance["transport_cap"].get(tr, 0)
        if vol > cap:
            errors.append(
                f"TRIP CAPACITY EXCEEDED: {f}→{t} via {tr}, trip {k}: "
                f"volume={vol}, capacity={cap}"
            )

    # ── Check 3: Trip index within frequency range ──────────────
    # Trip K should be between 1 and Freq

    for (f, t, tr, part, k), qty in trip_loads.items():
        rf = freq_lookup.get((f, t, tr))
        if rf is None:
            errors.append(
                f"TRIP ON INACTIVE ROUTE: {f}→{t} via {tr}, trip {k}"
            )
            continue
        if k < 1 or k > rf["freq"]:
            errors.append(
                f"TRIP INDEX OUT OF RANGE: {f}→{t} via {tr}, trip {k}: "
                f"freq={rf['freq']}"
            )

    # ── Check 4: No negative loads ──────────────────────────────
    for (f, t, tr, part, k), qty in trip_loads.items():
        if qty < 0:
            errors.append(
                f"NEGATIVE LOAD: {f}→{t} via {tr}, {part}, trip {k}: qty={qty}"
            )

    return errors


# ─────────────────────────────────────────────────────────────────────────
# Summary reporting
# ─────────────────────────────────────────────────────────────────────────

def print_summary(stage1: dict, stage2: dict, instance: dict) -> None:
    """Print a summary of the solution for quick inspection."""

    loads = stage1["loads"]
    trip_loads = stage2["trip_loads"]

    # Stage 1 summary
    total_parts_shipped = sum(loads.values())
    active_arcs = len(stage1["route_freqs"])
    total_trips = sum(rf["freq"] for rf in stage1["route_freqs"])

    print(f"  Stage 1: {active_arcs} active arcs, "
          f"{total_parts_shipped} total units shipped, "
          f"{total_trips} total trips allocated")

    # Stage 2 summary
    trips_used = set()
    for (f, t, tr, part, k), qty in trip_loads.items():
        trips_used.add((f, t, tr, k))

    trip_volumes = defaultdict(int)
    for (f, t, tr, part, k), qty in trip_loads.items():
        size = instance["part_size"].get(part, 0)
        trip_volumes[(f, t, tr, k)] += size * qty

    fill_rates = []
    for (f, t, tr, k), vol in trip_volumes.items():
        cap = instance["transport_cap"].get(tr, 0)
        if cap > 0:
            fill_rates.append(vol / cap)

    avg_fill = sum(fill_rates) / len(fill_rates) if fill_rates else 0

    print(f"  Stage 2: {len(trips_used)} trips used out of {total_trips} allocated, "
          f"avg fill rate={avg_fill:.1%}")


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a two-stage logistics solution against hard constraints."
    )
    parser.add_argument("--instance", "-i", required=True,
                        help="Path to the instance .lp file")
    parser.add_argument("--cap-divide", type=int, default=1,
                        help="Capacity scaling divisor (default: 1)")
    parser.add_argument("--max-freq", type=int, default=30,
                        help="Maximum frequency (default: 30)")
    parser.add_argument("--time-limit", type=int, default=120,
                        help="Time limit per stage in seconds")
    parser.add_argument("--round-timeout", type=int, default=60,
                        help="Per-round timeout for Stage 1")
    parser.add_argument("--stage2", type=str, default=None,
                        help="Stage 2 encoding file (default: stage2_packing.lp)")

    args = parser.parse_args()

    instance_path = Path(args.instance)
    if not instance_path.exists():
        print(f"Error: instance not found: {instance_path}", file=sys.stderr)
        return 1

    # Parse instance
    instance = parse_instance_full(str(instance_path))
    instance_data = load_instance_data(str(instance_path))

    # ── Solve Stage 1 ──────────────────────────────────────────
    print("=" * 65)
    print("  SOLVING STAGE 1")
    print("=" * 65)

    stage1 = solve_stage1(
        str(instance_path), args.cap_divide, args.max_freq,
        args.time_limit, round_timeout=args.round_timeout,
    )

    if stage1 is None:
        print("  Stage 1 UNSATISFIABLE")
        return 1

    # ── Verify Stage 1 ─────────────────────────────────────────
    print()
    print("=" * 65)
    print("  VERIFYING STAGE 1")
    print("=" * 65)

    s1_errors = verify_stage1(stage1, instance)
    if s1_errors:
        print(f"  FAILED — {len(s1_errors)} error(s):")
        for e in s1_errors:
            print(f"    {e}")
    else:
        print("  PASSED — all Stage 1 constraints satisfied")

    # ── Solve Stage 2 ──────────────────────────────────────────
    print()
    print("=" * 65)
    print("  SOLVING STAGE 2")
    print("=" * 65)

    facts = build_stage2_facts(stage1, instance_data)
    stage2 = solve_stage2(facts, args.time_limit, round_timeout=args.round_timeout)

    if stage2 is None:
        print("  Stage 2 UNSATISFIABLE")
        return 1

    # ── Verify Stage 2 ─────────────────────────────────────────
    print()
    print("=" * 65)
    print("  VERIFYING STAGE 2")
    print("=" * 65)

    s2_errors = verify_stage2(stage2, stage1, instance)
    if s2_errors:
        print(f"  FAILED — {len(s2_errors)} error(s):")
        for e in s2_errors:
            print(f"    {e}")
    else:
        print("  PASSED — all Stage 2 constraints satisfied")

    # ── Summary ────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("  SOLUTION SUMMARY")
    print("=" * 65)
    print_summary(stage1, stage2, instance)

    # ── Final verdict ──────────────────────────────────────────
    print()
    total_errors = len(s1_errors) + len(s2_errors)
    if total_errors == 0:
        print("  VERDICT: ALL CHECKS PASSED")
        return 0
    else:
        print(f"  VERDICT: {total_errors} ERROR(S) FOUND")
        return 1


if __name__ == "__main__":
    sys.exit(main())
