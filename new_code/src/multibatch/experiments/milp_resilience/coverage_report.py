"""Coverage-distribution report for the MILP+ASP pipeline.

For each Stage-2 config, report the FULL coverage distribution (not just the
worst case) under single-trip loss, split into overall vs packing-addressable
(multi-trip arcs). Can reuse a flow dumped by diagnose.py (`--from-flow`) so the
expensive MILP solve is paid once.

Usage:
    # reuse a dumped flow (fast):
    uv run python -m multibatch.experiments.milp_resilience.coverage_report \
        src/multibatch/instances/generated/industry_test_1.lp \
        --from-flow src/multibatch/experiments/milp_resilience/results/flow_industry_test_1.json \
        --synth-values size
    # or solve the flow fresh:
    uv run python -m multibatch.experiments.milp_resilience.coverage_report \
        src/multibatch/instances/generated/layered_medium_seed1.lp
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from ...metrics.coverage import coverage_report
from ...models import RouteFreq, SolveMetadata, Stage1Result, TwoStageClingconConfig
from ...solvers.milp_flow import MilpFlowTwoStageSolver
from ...solvers.twostage_clingcon import ClingconTwoStageSolver
from .runner import CONFIGS, _synth_values


def load_flow(path: str) -> Stage1Result:
    d = json.loads(Path(path).read_text())
    loads = {tuple(k.split(",")): v for k, v in d["loads"].items()}
    rfs = [RouteFreq(**rf) for rf in d["route_freqs"]]
    return Stage1Result(
        metadata=SolveMetadata(satisfiable=True, optimum=False),
        loads=loads, route_freqs=rfs, high_exposure=[],
    )


_STAT_COLS = ["n", "min", "p10", "p25", "median", "mean", "cvar10",
              "frac_full", "frac_zero", "demand_weighted_mean"]


def _print_block(title: str, rows: list[tuple[str, dict]]) -> None:
    print(f"\n  {title}")
    print(f"  {'config':9s} {'n':>5} {'min':>6} {'p10':>6} {'p25':>6} {'med':>6} "
          f"{'mean':>6} {'cvar10':>7} {'full%':>6} {'zero%':>6} {'dw_mean':>7}")
    for name, s in rows:
        if not s or s.get("n", 0) == 0:
            print(f"  {name:9s}  (no scenarios)")
            continue
        print(f"  {name:9s} {s['n']:>5} {s['min']:>6.3f} {s['p10']:>6.3f} {s['p25']:>6.3f} "
              f"{s['median']:>6.3f} {s['mean']:>6.3f} {s['cvar10']:>7.3f} "
              f"{s['frac_full']:>6.2f} {s['frac_zero']:>6.2f} "
              f"{(s['demand_weighted_mean'] if s['demand_weighted_mean'] is not None else float('nan')):>7.3f}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Coverage-distribution report (MILP+ASP)")
    p.add_argument("instance")
    p.add_argument("--flow-solver", choices=["milp", "asp"], default="milp",
                   help="milp = MILP network flow; asp = clingcon two-stage flow")
    p.add_argument("--from-flow", default=None, help="reuse a dumped flow JSON (skip solve)")
    p.add_argument("--configs", nargs="+", default=["baseline", "mixed", "even", "full"])
    p.add_argument("--synth-values", default="none", choices=["none", "uniform", "size"])
    p.add_argument("--backend", default="SCIP")
    p.add_argument("--flow-time-limit", type=int, default=300)
    p.add_argument("--stage2-time-limit", type=int, default=30)
    p.add_argument("-o", "--out", default=None)
    args = p.parse_args(argv)

    config = TwoStageClingconConfig(weight=0, max_freq=20, cap_size_divide=1,
                                    time_limit=args.stage2_time_limit,
                                    round_timeout=args.stage2_time_limit, configuration="many")
    if args.flow_solver == "milp":
        solver = MilpFlowTwoStageSolver(args.instance, config=config, backend=args.backend,
                                        flow_time_limit=args.flow_time_limit)
    else:
        solver = ClingconTwoStageSolver(args.instance, config=config)
    _synth_values(solver.instance, args.synth_values)

    if args.from_flow:
        stage1 = load_flow(args.from_flow)
    elif args.flow_solver == "asp":
        # clingcon shares config.time_limit across stages: give the flow its own
        # budget, then restore the packing budget before the per-config loop.
        solver.config.time_limit = args.flow_time_limit
        solver.config.round_timeout = args.flow_time_limit
        stage1 = solver._solve_stage1()
        solver.config.time_limit = args.stage2_time_limit
    else:
        stage1 = solver._solve_stage1()
    if stage1 is None:
        print("No feasible flow (ASP flow may not scale to this instance; try --flow-solver milp).")
        return 1
    print(f"Flow: arcs={len(stage1.route_freqs)} trips={sum(rf.frequency for rf in stage1.route_freqs)}")

    overall_rows, addr_rows, csv_rows = [], [], []
    for name, hetero, conc in [c for c in CONFIGS if c[0] in args.configs]:
        solver.config.hetero_on = hetero
        solver.config.concentrated_on = conc
        stage2 = solver._solve_stage2(stage1)
        if stage2 is None:
            overall_rows.append((name, {})); addr_rows.append((name, {}))
            continue
        rep = coverage_report(stage1, stage2, solver.instance)
        overall_rows.append((name, rep["overall"]))
        addr_rows.append((name, rep["packing_addressable"]))
        for scope in ("overall", "packing_addressable", "flow_limited"):
            row = {"instance": Path(args.instance).stem, "config": name, "scope": scope,
                   "mono_count": stage2.mono_count, "concentrated_count": stage2.concentrated_count}
            row.update({c: rep[scope].get(c) for c in _STAT_COLS})
            csv_rows.append(row)

    print("\n=== COVERAGE DISTRIBUTION under single-trip loss (higher = more resilient) ===")
    _print_block("OVERALL (all scenarios):", overall_rows)
    _print_block("PACKING-ADDRESSABLE (multi-trip arcs only — where packing CAN help):", addr_rows)

    out = Path(args.out) if args.out else (
        Path(__file__).resolve().parent / "results" / f"coverage_{Path(args.instance).stem}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["instance", "config", "scope", "mono_count",
                                           "concentrated_count", *_STAT_COLS], extrasaction="ignore")
        w.writeheader()
        w.writerows(csv_rows)
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
