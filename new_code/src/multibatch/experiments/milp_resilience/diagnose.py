"""Diagnose why resilience metrics are 0 on an instance.

Solves the MILP flow, dumps it to JSON (so re-analysis is instant), and reports
per part: supply/demand balance, #arcs, #single-trip arcs, and the *nominal*
(no-disruption) max-flow coverage. If nominal coverage is already < 1, the
flow/metric can't satisfy demand even before any disruption (a metric/flow
mismatch). If nominal == 1 but single-trip arcs exist, R_1 = 0 is a real
single-point-of-failure result that packing cannot fix.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from ...metrics.resilience import (
    _build_location_index,
    _max_flow_coverage,
    _total_demand_per_part,
)
from ...models import TwoStageClingconConfig
from ...solvers.milp_flow import MilpFlowTwoStageSolver
from .runner import _synth_values


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("instance")
    p.add_argument("--synth-values", default="size")
    p.add_argument("--flow-time-limit", type=int, default=300)
    p.add_argument("--backend", default="SCIP")
    p.add_argument("--dump", default=None, help="JSON path to save the flow")
    args = p.parse_args(argv)

    config = TwoStageClingconConfig(weight=0, max_freq=20, cap_size_divide=1, time_limit=20)
    solver = MilpFlowTwoStageSolver(args.instance, config=config, backend=args.backend,
                                    flow_time_limit=args.flow_time_limit)
    _synth_values(solver.instance, args.synth_values)
    inst = solver.instance

    stage1 = solver._solve_stage1()
    if stage1 is None:
        print("No feasible flow."); return 1

    loads = stage1.loads
    dump = args.dump or str(Path(__file__).resolve().parent / "results" /
                            f"flow_{Path(args.instance).stem}.json")
    Path(dump).parent.mkdir(parents=True, exist_ok=True)
    with open(dump, "w") as fh:
        json.dump({"loads": {",".join(k): v for k, v in loads.items()},
                   "route_freqs": [rf.model_dump() for rf in stage1.route_freqs]}, fh)
    print(f"flow dumped -> {dump}")

    parts = sorted({p for (_f, _t, _tr, p) in loads})
    loc_idx, n_locs = _build_location_index(loads)
    total_demand = _total_demand_per_part(inst, parts)
    trips_arc = {(rf.origin, rf.destination, rf.transport): rf.frequency for rf in stage1.route_freqs}

    sup: dict[str, int] = defaultdict(int)
    for (pp, _l), q in inst.offers.items():
        sup[pp] += q
    dem: dict[str, int] = defaultdict(int)
    for (pp, _l), q in inst.demands.items():
        dem[pp] += q
    arcs_for_part: dict[str, set] = defaultdict(set)
    for (f, t, tr, pp) in loads:
        arcs_for_part[pp].add((f, t, tr))

    print(f"\n{'part':10s} {'sup':>5} {'dem':>5} {'bal':>4} {'arcs':>5} {'1trip':>6} {'nominal_cov':>11}")
    n_zero = n_lt1 = 0
    for pp in parts:
        td = total_demand.get(pp, 0)
        arc_caps: dict[tuple[str, str], int] = defaultdict(int)
        for (f, t, tr, part), q in loads.items():
            if part == pp:
                arc_caps[(f, t)] += q
        cov = _max_flow_coverage(pp, inst, loc_idx, n_locs, dict(arc_caps), td) if td else None
        n_single = sum(1 for a in arcs_for_part[pp] if trips_arc.get(a, 0) == 1)
        bal = "ok" if sup[pp] == dem[pp] else "NEQ"
        if cov is not None and cov == 0:
            n_zero += 1
        if cov is not None and cov < 1:
            n_lt1 += 1
        print(f"{pp:10s} {sup[pp]:>5} {dem[pp]:>5} {bal:>4} {len(arcs_for_part[pp]):>5} "
              f"{n_single:>6} {str(cov):>11}")

    print(f"\nparts with demand: {sum(1 for pp in parts if total_demand.get(pp,0))}")
    print(f"parts with nominal coverage < 1 (BEFORE any disruption): {n_lt1}")
    print(f"parts with nominal coverage == 0: {n_zero}")
    print("\nINTERPRETATION:")
    print("  nominal_cov < 1  -> flow/metric cannot even satisfy demand undisrupted (mismatch)")
    print("  nominal_cov == 1 but 1trip>0 -> losing that trip can zero the part: real SPOF,")
    print("                                   packing cannot help a 1-trip arc.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
