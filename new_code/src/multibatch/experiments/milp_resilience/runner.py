"""Run the MILP-flow + ASP-packing pipeline and compare resilience across configs.

For one instance:
  1. Solve the network flow ONCE with the MILP oracle (fixed substrate).
  2. For each Stage-2 config (baseline/mixed/even/full), run the ASP packing on
     that flow and compute R_1, K_1, R_alpha + dispatch cost.
  3. Print a comparison table and append rows to a CSV.

This isolates the packing effect (flow held fixed) so any resilience gain is
attributable to the soft constraints, not the flow.

Usage:
    uv run python -m multibatch.experiments.milp_resilience.runner \
        src/multibatch/instances/generated/layered_medium_seed1.lp
    # industry (no partVal in file -> synthesise so even/full are active):
    uv run python -m multibatch.experiments.milp_resilience.runner \
        src/multibatch/instances/generated/industry_test_1.lp --synth-values size
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from ...metrics.resilience import compute_k1, compute_r1, compute_r_alpha, compute_r_tr
from ...models import TwoStageClingconConfig
from ...solvers.milp_flow import MilpFlowTwoStageSolver
from ...verification.checks import verify_twostage
from ..twostage.runner import compute_dispatch_costs

# (name, hetero_on, concentrated_on)
CONFIGS = [
    ("baseline", 0, 0),
    ("mixed", 1, 0),
    ("even", 0, 1),
    ("full", 1, 1),
]

CSV_FIELDS = [
    "instance", "config", "flow_optimum", "flow_cost", "n_arcs", "total_trips",
    "s2_status", "s2_optimal", "mono_count", "concentrated_count",
    "r_tr", "r_1", "k_1", "r_alpha_single_0.2", "r_alpha_global_0.2",
    "s1_dispatch_cost", "s2_dispatch_cost", "cost_saving", "s2_time",
]


def _synth_values(instance, mode: str) -> None:
    """Populate part_value if missing (industry instance has no partVal).

    'size'   -> value proportional to part size (larger parts more valuable)
    'uniform'-> value 1 for every part
    """
    if mode == "none" or instance.part_value:
        return
    if mode == "size":
        instance.part_value = {p: max(1, instance.part_size.get(p, 1)) for p in instance.parts}
    else:  # uniform
        instance.part_value = {p: 1 for p in instance.parts}
    print(f"  (synthesised partVal for {len(instance.part_value)} parts via '{mode}')")


def run_instance(args: argparse.Namespace) -> list[dict]:
    inst_name = Path(args.instance).stem
    config = TwoStageClingconConfig(
        weight=args.weight,
        exposure_n=args.exposure_n,
        max_freq=args.max_freq,
        cap_size_divide=args.cap_size_divide,
        time_limit=args.stage2_time_limit,
        configuration=(args.configuration or None),
        threads=args.threads,
    )
    solver = MilpFlowTwoStageSolver(
        args.instance, config=config, backend=args.backend,
        flow_time_limit=args.flow_time_limit,
    )
    _synth_values(solver.instance, args.synth_values)

    print(f"\n=== MILP flow on {inst_name} (backend={args.backend}, budget {args.flow_time_limit}s) ===")
    stage1 = solver._solve_stage1()
    if stage1 is None:
        print(f"  MILP found NO feasible flow within {args.flow_time_limit}s. Aborting.")
        print("  Hint: large instances need a bigger --flow-time-limit (industry needs "
              ">~150s with SCIP), or try a faster backend (--backend CBC).")
        return []
    n_arcs = len(stage1.route_freqs)
    total_trips = sum(rf.frequency for rf in stage1.route_freqs)
    print(f"  flow: optimum={stage1.metadata.optimum} cost={stage1.metadata.cost} "
          f"arcs={n_arcs} trips={total_trips}")

    # R_TR is flow-level: identical across all packing configs (same flow).
    r_tr = None
    try:
        r_tr, _ = compute_r_tr(stage1, solver.instance)
    except Exception as e:
        print(f"  R_TR exception: {e}")

    rows: list[dict] = []
    configs = [c for c in CONFIGS if c[0] in args.configs]
    if args.synth_values == "none" and not solver.instance.part_value:
        active = {"even", "full"} & {c[0] for c in configs}
        if active:
            print(f"  WARNING: no partVal -> {sorted(active)} behave like baseline/mixed "
                  f"(use --synth-values size to activate value-evenness)")

    for name, hetero, conc in configs:
        solver.config.hetero_on = hetero
        solver.config.concentrated_on = conc
        stage2 = solver._solve_stage2(stage1)
        row = {
            "instance": inst_name, "config": name,
            "flow_optimum": stage1.metadata.optimum, "flow_cost": stage1.metadata.cost,
            "n_arcs": n_arcs, "total_trips": total_trips, "r_tr": r_tr,
        }
        if stage2 is None:
            row["s2_status"] = "UNSAT"
            rows.append(row)
            continue

        passed, errs = verify_twostage(stage1, stage2, solver.instance)
        row["s2_status"] = "OK" if passed else f"VERIFY_FAIL({len(errs)})"
        row["s2_optimal"] = stage2.metadata.optimum
        row["mono_count"] = stage2.mono_count
        row["concentrated_count"] = stage2.concentrated_count
        row["s2_time"] = stage2.metadata.total_time

        try:
            r_1, r1_details = compute_r1(stage1, stage2, solver.instance)
            row["r_1"] = r_1
            if r1_details:
                row["k_1"], _ = compute_k1(r1_details)
        except Exception as e:
            print(f"  [{name}] R_1/K_1 exception: {e}")
        try:
            row["r_alpha_single_0.2"], _ = compute_r_alpha(
                stage1, stage2, solver.instance, alpha=0.2, mode="single", strategy="heaviest")
            row["r_alpha_global_0.2"], _ = compute_r_alpha(
                stage1, stage2, solver.instance, alpha=0.2, mode="global", strategy="heaviest")
        except Exception as e:
            print(f"  [{name}] R_alpha exception: {e}")
        try:
            costs = compute_dispatch_costs(stage1, stage2, solver.instance)
            row.update(s1_dispatch_cost=costs["s1_dispatch_cost"],
                       s2_dispatch_cost=costs["s2_dispatch_cost"],
                       cost_saving=costs["cost_saving"])
        except Exception as e:
            print(f"  [{name}] dispatch cost exception: {e}")
        rows.append(row)
    return rows


def _print_table(rows: list[dict]) -> None:
    if not rows:
        return
    print(f"\n  RESILIENCE COMPARISON (higher R_1/K_1/R_alpha = more resilient):")
    hdr = (f"  {'config':9s} {'s2opt':6s} {'mono':>5} {'conc':>5} {'R_1':>7} {'K_1':>7} "
           f"{'Rα_s.2':>7} {'Rα_g.2':>7} {'s2_cost':>9} {'saving':>8}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in rows:
        def g(k, fmt="{}"):
            v = r.get(k)
            return fmt.format(v) if v is not None else "-"
        print(f"  {r['config']:9s} {str(r.get('s2_optimal','-')):6s} "
              f"{g('mono_count'):>5} {g('concentrated_count'):>5} "
              f"{g('r_1','{:.3f}'):>7} {g('k_1','{:.3f}'):>7} "
              f"{g('r_alpha_single_0.2','{:.3f}'):>7} {g('r_alpha_global_0.2','{:.3f}'):>7} "
              f"{g('s2_dispatch_cost'):>9} {g('cost_saving'):>8}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MILP flow + ASP packing resilience comparison")
    p.add_argument("instance")
    p.add_argument("--configs", nargs="+", default=["baseline", "mixed", "even", "full"],
                   choices=[c[0] for c in CONFIGS])
    p.add_argument("--synth-values", choices=["none", "uniform", "size"], default="none",
                   help="synthesise partVal when missing (industry) so even/full activate")
    p.add_argument("--weight", type=int, default=0)
    p.add_argument("--exposure-n", type=int, default=3)
    p.add_argument("--max-freq", type=int, default=20)
    p.add_argument("--cap-size-divide", type=int, default=1)
    p.add_argument("--backend", default="SCIP")
    p.add_argument("--flow-time-limit", type=int, default=120)
    p.add_argument("--stage2-time-limit", type=int, default=30)
    p.add_argument("--configuration", default="many")
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("-o", "--out", default=None,
                   help="CSV path (default results/resilience_<instance>.csv)")
    args = p.parse_args(argv)

    rows = run_instance(args)
    _print_table(rows)

    if rows:
        out = Path(args.out) if args.out else (
            Path(__file__).resolve().parent / "results" / f"resilience_{Path(args.instance).stem}.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
