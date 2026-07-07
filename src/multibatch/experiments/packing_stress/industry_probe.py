"""Sample the real per-arc trip/part/load distribution of an instance.

Runs Stage 1 (network flow) with a bounded budget, then reports, per active arc,
how many distinct parts, how many units, and how many trips land on it. This
places a real instance on the packing-stress curve. Later, the same per-arc
profile can be sourced from the MILP flow oracle instead of ASP Stage 1.

Usage:
    uv run python -m multibatch.experiments.packing_stress.industry_probe \
        <instance.lp> --time-limit 90 --weight 0
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
import time
from collections import defaultdict
from pathlib import Path

from multibatch.models.config import TwoStageClingconConfig
from multibatch.solvers.twostage_clingcon import ClingconTwoStageSolver


def _desc(name: str, xs: list[int]) -> None:
    if not xs:
        print(f"  {name}: (none)")
        return
    xs = sorted(xs)
    print(
        f"  {name:18s} n={len(xs):<5} min={xs[0]:<6} med={int(st.median(xs)):<6} "
        f"mean={round(st.mean(xs), 1):<7} p90={xs[int(0.9 * (len(xs) - 1))]:<6} max={xs[-1]}"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Per-arc profile of an instance via Stage 1")
    p.add_argument("instance")
    p.add_argument("--time-limit", type=int, default=90)
    p.add_argument("--round-timeout", type=int, default=30)
    p.add_argument("--weight", type=int, default=0, help="exposure weight (0 = pure cost, fastest)")
    p.add_argument("--max-freq", type=int, default=20)
    p.add_argument("--configuration", type=str, default="many")
    p.add_argument("--threads", type=int, default=1)
    args = p.parse_args(argv)

    cfg = TwoStageClingconConfig(
        time_limit=args.time_limit,
        round_timeout=args.round_timeout,
        weight=args.weight,
        max_freq=args.max_freq,
        configuration=args.configuration,
        threads=args.threads,
    )
    solver = ClingconTwoStageSolver(args.instance, config=cfg)

    print(f"Running Stage 1 on {args.instance} (budget {args.time_limit}s, weight {args.weight})...")
    t0 = time.perf_counter()
    stage1 = solver._solve_stage1()
    dt = time.perf_counter() - t0
    print(f"Stage 1 returned in {dt:.1f}s")

    if stage1 is None:
        print("\n*** Stage 1 produced NO feasible flow within the budget. ***")
        print("    -> This is the case for the MILP flow oracle: ASP can't even")
        print("       reach feasibility at this scale.")
        return 0

    m = stage1.metadata
    print(f"  optimum_proven={m.optimum}  cost={m.cost}  ground={m.ground_time}s solve={m.solve_time}s")

    # Per-arc aggregation
    parts_per_arc: dict[tuple, set] = defaultdict(set)
    units_per_arc: dict[tuple, int] = defaultdict(int)
    for (f, t, tr, part), n in stage1.loads.items():
        arc = (f, t, tr)
        parts_per_arc[arc].add(part)
        units_per_arc[arc] += n
    trips_per_arc = {(rf.origin, rf.destination, rf.transport): rf.frequency
                     for rf in stage1.route_freqs}

    n_arcs = len(set(parts_per_arc) | set(trips_per_arc))
    print(f"\nActive arcs: {n_arcs}")
    _desc("parts / arc", [len(s) for s in parts_per_arc.values()])
    _desc("units / arc", list(units_per_arc.values()))
    _desc("trips / arc", list(trips_per_arc.values()))

    # Flag the arcs that land in the packing-stress 'watch zone' (>64 trips)
    hot = sorted(((v, k) for k, v in trips_per_arc.items()), reverse=True)[:8]
    print("\n  hottest arcs (trips, arc, #parts):")
    for trips, arc in hot:
        print(f"    trips={trips:<5} arc={arc} parts={len(parts_per_arc.get(arc, set()))}")
    n_hot = sum(1 for v in trips_per_arc.values() if v > 64)
    print(f"\n  arcs with >64 trips (packing watch zone): {n_hot} / {len(trips_per_arc)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
