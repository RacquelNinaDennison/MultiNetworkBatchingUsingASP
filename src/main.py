#!/usr/bin/env python3
"""
main.py — CLI entry point + experiment API for multi-commodity batching solvers.

Experiment API
--------------
    from main import (
        parse_instance, solve_combined,
        compute_r_tr, compute_r1, compute_dispatch_costs,
    )

CLI
---
    python main.py --solver naive    -i instances/data_small.lp --bins 2
    python main.py --solver clingcon -i instances/data_small.lp --bins 2
    python main.py --solver twostage -i instances/data_small.lp --weight 100
"""

from __future__ import annotations
import os
import argparse
import sys
from collections import defaultdict
from pathlib import Path

from modules.run_naive import RunNaive
from modules.run_clingcon import RunClingcon
from modules.run_two_stage_naive import RunNaiveTwoStage
from modules.run_two_stage_subprocess import SubprocessTwoStage



def parse_instance(instance_path: str) -> dict:
    """Parse an instance .lp file into Python structures.

    Returns the BaseSolver instance_data dict enriched with separate
    ``demands`` and ``offers`` dicts needed by the R_TR / R_1 metrics.
    """
    solver = RunNaiveTwoStage(instance_path)
    data = solver.instance_data

    demands: dict[tuple, int] = {}
    offers:  dict[tuple, int] = {}
    for (part, loc), vals in data["demand_offer"].items():
        for val in vals:
            if val < 0:
                demands[(part, loc)] = demands.get((part, loc), 0) + (-val)
            elif val > 0:
                offers[(part, loc)] = offers.get((part, loc), 0) + val

    data["demands"] = demands
    data["offers"]  = offers
    return data


def solve_combined(
    instance_path: str,
    weight: int = 1,
    time_limit: int = 30,
    max_freq: int = 20,
    exposure_n: int = 3,
    hetero_on: int = 1,
    concentrated_on: int = 1,
    round_timeout: int = 30,
) -> dict | None:
    """Solve both stages in one clingo call using multi-shot with iterative
    bounds.

    Each round gets exactly ``round_timeout`` seconds.  The number of
    rounds is ``time_limit // round_timeout``.  If a model is found but
    optimality isn't proven, the best cost is added as an upper bound and
    the solver restarts.

    Returns a combined dict with ``_stage1`` holding the stage 1 data
    (loads, route_freqs, high_exposure, cost, optimum, time, trajectory)
    and top-level stage 2 data (trip_loads, mono_count, concentrated_count,
    optimum, time, trajectory), or None if UNSAT.
    """
    solver = RunNaiveTwoStage(
        instance_path,
        time_limit=time_limit,
        max_freq=max_freq,
        weight=weight,
        exposure_n=exposure_n,
    )
    return solver.solve_combined(
        hetero_on=hetero_on,
        concentrated_on=concentrated_on,
        round_timeout=round_timeout,
    )


def solve_stage1(
    instance_path: str,
    weight: int = 1,
    time_limit: int = 30,
    max_freq: int = 20,
    exposure_n: int = 3,
    stage1_encoding: str | None = None,
    threads: int = 1,
    configuration: str | None = None,
) -> tuple[SubprocessTwoStage, dict | None]:
    """Solve Stage 1 via clingcon subprocess.

    Returns ``(solver, stage1_result)`` so the solver can be reused
    for multiple Stage 2 configurations without re-solving Stage 1.
    """
    solver = SubprocessTwoStage(
        instance_path,
        time_limit=time_limit,
        max_freq=max_freq,
        weight=weight,
        exposure_n=exposure_n,
        stage1_encoding=stage1_encoding,
        threads=threads,
        configuration=configuration,
    )
    stage1, wall_time, _ = solver.run_stage1_subprocess()
    if stage1 is not None:
        stage1["time"] = round(wall_time, 3)
    return solver, stage1


def solve_stage2_from_stage1(
    solver: SubprocessTwoStage,
    stage1: dict,
    hetero_on: int = 1,
    concentrated_on: int = 1,
    stage2_encoding: str | None = None,
) -> dict | None:
    """Solve Stage 2 via clingcon subprocess using a cached Stage 1 result.

    Returns a combined dict with ``_stage1`` and Stage 2 data,
    or None if Stage 2 is UNSAT.
    """
    import tempfile

    facts_str = solver.build_stage2_facts(stage1)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".lp", prefix="s2_facts_", delete=False,
    )
    tmp.write(facts_str)
    tmp.close()

    stage2, wall_time, _ = solver.run_stage2_subprocess(
        tmp.name,
        hetero_on=hetero_on,
        concentrated_on=concentrated_on,
        stage2_encoding=stage2_encoding,
    )

    Path(tmp.name).unlink(missing_ok=True)

    if stage2 is None:
        return None

    stage2["time"] = round(wall_time, 3)
    result = dict(stage2)
    result["_stage1"] = stage1
    return result


def compute_kit_ratio(
    r1_details: list[dict],
) -> tuple[float, list[dict]]:
    """Compute kit-completion ratio K_1 from R_1 per-trip details.

    For each lost trip, the bottleneck part is the one with the lowest
    coverage ratio.  K_1 is the worst-case bottleneck across all trips.
    """
    trip_groups: dict[str, list[dict]] = {}
    for d in r1_details:
        trip_groups.setdefault(d["lost_trip"], []).append(d)

    kit_details: list[dict] = []
    for trip_key, parts in trip_groups.items():
        bottleneck = min(parts, key=lambda d: d["coverage"])
        kit_details.append({
            "lost_trip":       trip_key,
            "bottleneck_part": bottleneck["part"],
            "kit_ratio":       bottleneck["coverage"],
        })

    kit_details.sort(key=lambda d: d["kit_ratio"])
    k_1 = kit_details[0]["kit_ratio"] if kit_details else 1.0
    return k_1, kit_details


def compute_dispatch_costs(
    stage1: dict,
    stage2: dict,
    instance_data: dict,
) -> dict:
    """Compare dispatch costs between stage 1 frequencies and stage 2 used trips."""
    route_cost = instance_data["route_cost"]

    s1_dispatch_cost = 0
    for rf in stage1["route_freqs"]:
        key = (rf["from"], rf["to"], rf["tr"])
        s1_dispatch_cost += rf["freq"] * route_cost.get(key, 0)

    trips_per_route: dict[tuple, set] = defaultdict(set)
    for (f, t, tr, _p, k) in stage2["trip_loads"]:
        trips_per_route[(f, t, tr)].add(k)

    s2_dispatch_cost = 0
    for (f, t, tr), trip_ids in trips_per_route.items():
        s2_dispatch_cost += len(trip_ids) * route_cost.get((f, t, tr), 0)

    return {
        "s1_dispatch_cost": s1_dispatch_cost,
        "s2_dispatch_cost": s2_dispatch_cost,
        "cost_saving":      s1_dispatch_cost - s2_dispatch_cost,
    }


def compute_r_tr(loads: dict, instance_data: dict) -> tuple[float, list[dict]]:
    """Worst-case coverage when an entire arc-TR is removed.

    ``loads`` is keyed ``(F, T, TR, P) -> N``.
    ``instance_data`` must contain ``demands`` and ``offers`` dicts.
    """
    from scipy.sparse.csgraph import maximum_flow
    from scipy.sparse import csr_matrix

    demands = instance_data["demands"]
    offers  = instance_data["offers"]
    parts   = sorted(set(p for (f, t, tr, p) in loads))

    all_locs = sorted(
        set(f for (f, t, tr, p) in loads) |
        set(t for (f, t, tr, p) in loads)
    )
    loc_idx = {loc: i for i, loc in enumerate(all_locs)}
    N       = len(all_locs)
    S_NODE  = N
    T_NODE  = N + 1
    N_NODES = N + 2
    SCALE   = 1000

    total_demand = {
        p: sum(q for (part, loc), q in demands.items() if part == p)
        for p in parts
    }

    active_arcs   = sorted(set((f, t, tr) for (f, t, tr, p) in loads))
    details: list[dict] = []
    all_coverages: list[float] = []

    for (lost_f, lost_t, lost_tr) in active_arcs:
        for p in parts:
            if total_demand.get(p, 0) == 0:
                continue

            cap = [[0] * N_NODES for _ in range(N_NODES)]

            for (part, loc), qty in offers.items():
                if part == p and loc in loc_idx:
                    cap[S_NODE][loc_idx[loc]] += int(qty * SCALE)

            for (part, loc), qty in demands.items():
                if part == p and loc in loc_idx:
                    cap[loc_idx[loc]][T_NODE] += int(qty * SCALE)

            for (f, t, tr, part), qty in loads.items():
                if part != p or f not in loc_idx or t not in loc_idx:
                    continue
                arc_cap = 0 if (f, t, tr) == (lost_f, lost_t, lost_tr) \
                          else int(qty * SCALE)
                cap[loc_idx[f]][loc_idx[t]] += arc_cap

            flow_val   = maximum_flow(csr_matrix(cap), S_NODE, T_NODE).flow_value
            max_supply = flow_val / SCALE
            coverage   = round(min(max_supply / total_demand[p], 1.0), 4)

            details.append({
                "lost_f":   lost_f,
                "lost_t":   lost_t,
                "lost_tr":  lost_tr,
                "part":     p,
                "max_flow": round(max_supply, 3),
                "demand":   total_demand[p],
                "coverage": coverage,
            })
            all_coverages.append(coverage)

    r_tr = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_tr, details


def compute_r1(
    trip_loads:    dict,
    loads:         dict,
    instance_data: dict,
) -> tuple[float, list[dict]]:
    """Worst-case coverage when a single trip is lost.

    ``trip_loads`` is keyed ``(F, T, TR, P, K) -> Q``.
    ``loads`` is keyed ``(F, T, TR, P) -> N``.
    ``instance_data`` must contain ``demands`` and ``offers`` dicts.
    """
    from scipy.sparse.csgraph import maximum_flow
    from scipy.sparse import csr_matrix

    demands = instance_data["demands"]
    offers  = instance_data["offers"]
    parts   = sorted(set(p for (f, t, tr, p) in loads))

    all_locs = sorted(
        set(f for (f, t, tr, p) in loads) |
        set(t for (f, t, tr, p) in loads)
    )
    loc_idx = {loc: i for i, loc in enumerate(all_locs)}
    N       = len(all_locs)
    S_NODE  = N
    T_NODE  = N + 1
    N_NODES = N + 2
    SCALE   = 1000

    total_demand = {
        p: sum(q for (part, loc), q in demands.items() if part == p)
        for p in parts
    }

    trips: dict[tuple, dict[str, int]] = {}
    for (f, t, tr, p, k), qty in trip_loads.items():
        trip_key = (f, t, tr, k)
        if trip_key not in trips:
            trips[trip_key] = {}
        trips[trip_key][p] = qty

    details: list[dict] = []
    all_coverages: list[float] = []

    for trip_key, trip_contents in trips.items():
        lost_f, lost_t, lost_tr, lost_k = trip_key

        for p in parts:
            td = total_demand.get(p, 0)
            if td == 0:
                continue

            lost_qty = trip_contents.get(p, 0)

            cap = [[0] * N_NODES for _ in range(N_NODES)]

            for (part, loc), qty in offers.items():
                if part == p and loc in loc_idx:
                    cap[S_NODE][loc_idx[loc]] += int(qty * SCALE)

            for (part, loc), qty in demands.items():
                if part == p and loc in loc_idx:
                    cap[loc_idx[loc]][T_NODE] += int(qty * SCALE)

            for (f, t, tr, part), qty in loads.items():
                if part != p or f not in loc_idx or t not in loc_idx:
                    continue
                if (f, t, tr) == (lost_f, lost_t, lost_tr):
                    arc_cap = int((qty - lost_qty) * SCALE)
                else:
                    arc_cap = int(qty * SCALE)
                cap[loc_idx[f]][loc_idx[t]] += max(0, arc_cap)

            flow_val   = maximum_flow(csr_matrix(cap), S_NODE, T_NODE).flow_value
            max_supply = flow_val / SCALE
            coverage   = round(min(max_supply / td, 1.0), 4)

            details.append({
                "lost_trip":     f"({lost_f},{lost_t},{lost_tr},k{lost_k})",
                "lost_contents": dict(trip_contents),
                "part":          p,
                "max_flow":      round(max_supply, 3),
                "demand":        td,
                "coverage":      coverage,
            })
            all_coverages.append(coverage)

    r_1 = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_1, details



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-commodity network batching solver"
    )
    parser.add_argument(
        "--solver",
        choices=["naive", "clingcon", "twostage-naive", "twostage-clingcon",
                 "twostage-subprocess"],
        required=True, help="Solver to use",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output file to write results to",
    )
    parser.add_argument(
        "--instance", "-i", default=None, help="Instance .lp file",
    )
    parser.add_argument(
        "--time-limit", type=int, default=30, help="Time limit in seconds",
    )
    parser.add_argument(
        "--bins", type=int, default=1, help="Number of bins",
    )
    parser.add_argument(
        "--optimised", action="store_true", default=True,
        help="Use optimised encoding (naive only, default)",
    )
    parser.add_argument(
        "--no-optimised", action="store_false", dest="optimised",
        help="Use basic encoding (naive only)",
    )
    parser.add_argument(
        "--max-freq", type=int, default=20,
        help="Maximum frequency (default: 20)",
    )
    parser.add_argument(
        "--weight", type=int, default=1,
        help="Weight for soft constraints (default: 1)",
    )
    parser.add_argument("--cap-divide", type=int, default=1000)
    parser.add_argument("--round-timeout", type=int, default=30)
    parser.add_argument("--configurations", type=bool, default=False)
    return parser


def main() -> int:
   
    args = build_parser().parse_args()
    if not args.instance:
        print("Error: --instance / -i is required", file=sys.stderr)
        return 1

    instance = Path(args.instance)
    if not instance.exists():
        print(f"Error: instance not found: {instance}", file=sys.stderr)
        return 1

    print(f"Solver     : {args.solver}")
    print(f"Instance   : {instance}")
    print(f"Time limit : {args.time_limit}s")
    print()

    if args.solver == "naive":
        solver = RunNaive(
            str(instance),
            num_bins=args.bins,
            optimised=args.optimised,
            time_limit=args.time_limit,
            max_freq=args.max_freq,
        )
    elif args.solver == "clingcon":
        solver = RunClingcon(
            str(instance),
            num_bins=args.bins,
            time_limit=args.time_limit,
            max_freq=args.max_freq,
        )
    elif args.solver == "twostage":
        solver = RunNaiveTwoStage(
            str(instance),
            time_limit=args.time_limit,
            max_freq=args.max_freq,
            weight=args.weight,
        )
    elif args.solver == "twostage-subprocess":
        solver = SubprocessTwoStage(
            str(instance),
            time_limit=args.time_limit,
            max_freq=args.max_freq,
            weight=args.weight,
        )
    else:
        return 1

    return solver.run()


if __name__ == "__main__":
    sys.exit(main())
