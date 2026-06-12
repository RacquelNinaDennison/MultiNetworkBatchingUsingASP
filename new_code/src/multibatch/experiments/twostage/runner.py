"""Two-stage resilience experiment runner.

Runs the full weight x S2-config grid on a set of instances.
Stage 1 solved once per (instance, weight); Stage 2 solved per config.
Resilience metrics computed post-hoc on each solution.

Usage:
    cd new_code
    uv run python -m multibatch.experiments.twostage.runner
    uv run python -m multibatch.experiments.twostage.runner --help
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from ...instance import parse_instance
from ...models import (
    Instance,
    TwoStageClingconConfig,
    Stage1Result,
    Stage2Result,
)
from ...solvers.twostage_clingcon import ClingconTwoStageSolver
from ...metrics.resilience import (
    compute_r_tr,
    compute_r1,
    compute_k1,
    compute_r_alpha,
)
from .config import (
    S2_CONFIGS,
    DEFAULT_S2_CONFIGS,
    ALPHA_VALUES,
    R_ALPHA_STRATEGIES,
    R_ALPHA_MODES,
    ExperimentConfig,
    classify_instance,
    compute_instance_properties,
)
from .columns import COLUMNS, r_alpha_col
from ...verification import verify_twostage


# ── Encoding paths ────────────────────────────────────────────────────

# Default: use the clingcon encodings bundled with the package
_MULTIBATCH = Path(__file__).resolve().parent.parent.parent  # src/multibatch/
_PKG_ENCODINGS = _MULTIBATCH / "encodings" / "twostage" / "clingcon"
DEFAULT_S1_ENCODING = _PKG_ENCODINGS / "stage_1_clingcon_flow.lp"
DEFAULT_S2_ENCODING = _PKG_ENCODINGS / "stage_2_packing.lp"

# Instance directory
INSTANCE_DIR = _MULTIBATCH / "instances" / "generated"

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ── Dispatch cost computation ─────────────────────────────────────────


def compute_dispatch_costs(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
) -> dict:
    """Compare dispatch costs: Stage 1 frequencies vs Stage 2 used trips."""
    route_cost = instance.route_cost

    s1_dispatch = 0
    for rf in stage1.route_freqs:
        key = (rf.origin, rf.destination, rf.transport)
        s1_dispatch += rf.frequency * route_cost.get(key, 0)

    trips_per_route: dict[tuple, set] = defaultdict(set)
    for (f, t, tr, _p, k) in stage2.trip_loads:
        trips_per_route[(f, t, tr)].add(k)

    s2_dispatch = 0
    for (f, t, tr), trip_ids in trips_per_route.items():
        s2_dispatch += len(trip_ids) * route_cost.get((f, t, tr), 0)

    return {
        "s1_dispatch_cost": s1_dispatch,
        "s2_dispatch_cost": s2_dispatch,
        "cost_saving": s1_dispatch - s2_dispatch,
    }


# ── Relative weight normalisation ─────────────────────────────────────


def _normalizer_from_stage1(stage1: Stage1Result, instance: Instance) -> float | None:
    """Mean dispatch cost per trip of a Stage 1 solution.

    Scale for relative weights: lambda resolves to round(lambda * normalizer),
    so lambda is measured in units of "average dispatches paid per exposure
    removed". Only meaningful for the w=0 (cost-optimal) solution.
    """
    total_cost = 0
    total_trips = 0
    for rf in stage1.route_freqs:
        key = (rf.origin, rf.destination, rf.transport)
        total_cost += rf.frequency * instance.route_cost.get(key, 0)
        total_trips += rf.frequency
    if total_trips == 0:
        return None
    return total_cost / total_trips


def stage1_probe(
    instance_path: Path,
    instance: Instance,
    meta,
    exp_config: ExperimentConfig,
    s1_encoding: Path,
    s2_encoding: Path,
) -> float | None:
    """Solve Stage 1 at weight=0 just to measure the cost normalizer.

    Only needed on --resume when the lambda=0 rows exist but predate the
    weight_normalizer column.
    """
    time_limit = exp_config.get_time_limit(meta.size)
    solver_config = TwoStageClingconConfig(
        weight=0,
        exposure_n=exp_config.exposure_n,
        time_limit=time_limit,
        round_timeout=exp_config.round_timeout or time_limit,
        max_freq=exp_config.max_freq,
        cap_size_divide=exp_config.cap_size_divide,
        threads=exp_config.threads,
        configuration=exp_config.configuration,
    )
    solver = ClingconTwoStageSolver(
        instance_path,
        config=solver_config,
        stage1_encoding=s1_encoding,
        stage2_encoding=s2_encoding,
    )
    try:
        stage1 = solver._solve_stage1()
    except Exception as e:
        print(f"  Probe Stage 1 exception: {e}")
        return None
    if stage1 is None:
        return None
    return _normalizer_from_stage1(stage1, instance)


# ── CSV helpers ───────────────────────────────────────────────────────


def load_completed(csv_path: Path) -> set[tuple[str, int, str]]:
    """Return set of (instance_name, weight, s2_config) already done."""
    completed = set()
    if not csv_path.exists():
        return completed
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            completed.add((
                row["instance_name"],
                int(row["weight"]),
                row["s2_config"],
            ))
    return completed


def load_normalizer(csv_path: Path, inst_name: str) -> float | None:
    """Recover a stored weight normalizer for an instance from the CSV."""
    if not csv_path.exists():
        return None
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("instance_name") == inst_name and row.get("weight_normalizer"):
                try:
                    return float(row["weight_normalizer"])
                except ValueError:
                    return None
    return None


def append_row(csv_path: Path, row: dict) -> None:
    """Append a single row to the CSV (creates header if needed)."""
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in COLUMNS})


# ── Core experiment logic ─────────────────────────────────────────────


def run_weight_group(
    instance_path: Path,
    instance: Instance,
    meta,
    weight: int,
    exp_config: ExperimentConfig,
    csv_path: Path,
    completed: set,
    s1_encoding: Path,
    s2_encoding: Path,
    lam: float | None = None,
    normalizer: float | None = None,
) -> tuple[int, str, float | None]:
    """Solve Stage 1 once, compute R_TR, then loop S2 configs.

    `lam`/`normalizer` are set in relative-weight mode and recorded in
    each row. Returns (rows_written, s1_state, measured_normalizer) where
    s1_state is "solved", "skipped" (all configs resumed) or "unsat", and
    measured_normalizer is only non-None for a solved weight=0 group.
    """
    inst_name = meta.name
    s2_configs = exp_config.s2_configs
    time_limit = exp_config.get_time_limit(meta.size)

    configs_todo = [
        c for c in s2_configs
        if (inst_name, weight, c) not in completed
    ]
    if not configs_todo:
        return 0, "skipped", None

    # ── Solve Stage 1 ─────────────────────────────────────────────
    print(f"\n  [{inst_name} w={weight}] Stage 1 (limit={time_limit}s)...")

    solver_config = TwoStageClingconConfig(
        weight=weight,
        exposure_n=exp_config.exposure_n,
        time_limit=time_limit,
        round_timeout=exp_config.round_timeout or time_limit,
        max_freq=exp_config.max_freq,
        cap_size_divide=exp_config.cap_size_divide,
        threads=exp_config.threads,
        configuration=exp_config.configuration,
    )
    solver = ClingconTwoStageSolver(
        instance_path,
        config=solver_config,
        stage1_encoding=s1_encoding,
        stage2_encoding=s2_encoding,
    )

    try:
        stage1 = solver._solve_stage1()
    except Exception as e:
        print(f"  Stage 1 exception: {e}")
        stage1 = None

    if stage1 is None:
        print("Stage 1: UNSAT")
        for cfg_name in configs_todo:
            cfg = S2_CONFIGS[cfg_name]
            row = _base_row(meta, weight, exp_config.exposure_n, cfg,
                            threads=exp_config.threads,
                            solver_config=exp_config.configuration,
                            lam=lam, normalizer=normalizer)
            row["status"] = "S1_UNSAT"
            append_row(csv_path, row)
        return len(configs_todo), "unsat", None

    print(f"  Stage 1: cost={stage1.metadata.cost}  "
          f"routes={len(stage1.route_freqs)}  "
          f"optimal={stage1.metadata.optimum}")

    # The normalizer is only meaningful for the cost-optimal (w=0) plan
    measured_norm = _normalizer_from_stage1(stage1, instance) if weight == 0 else None
    if lam is not None and normalizer is None:
        normalizer = measured_norm

    # ── Compute R_TR (Stage 1 only) ───────────────────────────────
    r_tr_val = None
    worst_arc_str = None
    print(stage1.loads)
    try:
        r_tr_val, rtr_details = compute_r_tr(stage1, instance)
        worst = min(rtr_details, key=lambda d: d["coverage"])
        worst_arc_str = f"({worst['lost_f']},{worst['lost_t']},{worst['lost_tr']})"
    except Exception as e:
        print(f"  R_TR exception: {e}")

    print(f"  R_TR={r_tr_val}  worst_arc={worst_arc_str}")

    s1_fields = {
        "nominal_cost": stage1.metadata.cost,
        "exposure_count": len(stage1.high_exposure),
        "s1_optimal": stage1.metadata.optimum,
        "s1_time": stage1.metadata.total_time,
        "s1_trajectory": json.dumps(stage1.metadata.trajectory),
        "r_tr": r_tr_val,
        "worst_arc": worst_arc_str,
    }

    # ── Stage 2 per config ────────────────────────────────────────
    rows_written = 0
    for cfg_name in configs_todo:
        cfg = S2_CONFIGS[cfg_name]
        print(f"\n  [{inst_name} w={weight} s2={cfg_name}] Stage 2...")

        row = _base_row(meta, weight, exp_config.exposure_n, cfg,
                        threads=exp_config.threads,
                        solver_config=exp_config.configuration,
                        lam=lam, normalizer=normalizer)
        row.update(s1_fields)

        # Update solver config for this S2 variant
        solver.config.hetero_on = cfg.hetero_on
        solver.config.concentrated_on = cfg.concentrated_on

        try:
            stage2 = solver._solve_stage2(stage1)
        except Exception as e:
            print(f"  Stage 2 exception: {e}")
            stage2 = None

        if stage2 is None:
            row["status"] = "S2_UNSAT"
            append_row(csv_path, row)
            rows_written += 1
            continue

        row["mono_count"] = stage2.mono_count
        row["concentrated_count"] = stage2.concentrated_count
        row["s2_optimal"] = stage2.metadata.optimum
        row["s2_time"] = stage2.metadata.total_time
        row["s2_trajectory"] = json.dumps(stage2.metadata.trajectory)

        print(f"  mono={stage2.mono_count}  conc={stage2.concentrated_count}  "
              f"optimal={stage2.metadata.optimum}")
        print(stage2.trip_loads)

        # ── Verification ──────────────────────────────────────────
        passed, check_errors = verify_twostage(stage1, stage2, instance)
        if not passed:
            print(f"  VERIFICATION FAILED ({len(check_errors)} errors):")
            for err in check_errors:
                print(f"    {err}")
            row["status"] = "VERIFY_FAIL"
            append_row(csv_path, row)
            rows_written += 1
            continue
        print("  Verification: PASS")

        # ── R_1 ───────────────────────────────────────────────────
        r1_details = []
        try:
            r_1, r1_details = compute_r1(stage1, stage2, instance)
            worst_r1 = min(r1_details, key=lambda d: d["coverage"])
            row["r_1"] = r_1
            row["worst_trip"] = worst_r1["lost_trip"]
        except Exception as e:
            print(f"  R_1 exception: {e}")

        print(f"  R_1={row.get('r_1')}")

        # ── K_1 ───────────────────────────────────────────────────
        try:
            if r1_details:
                k_1, kit_details = compute_k1(r1_details)
                worst_kit = kit_details[0]
                row["k_1"] = k_1
                row["kit_bottleneck_trip"] = worst_kit["lost_trip"]
                row["kit_bottleneck_part"] = worst_kit["bottleneck_part"]
        except Exception as e:
            print(f"  K_1 exception: {e}")

        print(f"  K_1={row.get('k_1')}")

        # ── R_alpha ───────────────────────────────────────────────
        try:
            for strat in R_ALPHA_STRATEGIES:
                for mode in R_ALPHA_MODES:
                    for alpha in ALPHA_VALUES:
                        col = r_alpha_col(strat, mode, alpha)
                        val, _ = compute_r_alpha(
                            stage1, stage2, instance,
                            alpha=alpha, mode=mode, strategy=strat,
                        )
                        row[col] = val
        except Exception as e:
            print(f"R_alpha exception: {e}")

        try:
            costs = compute_dispatch_costs(stage1, stage2, instance)
            row["s1_dispatch_cost"] = costs["s1_dispatch_cost"]
            row["s2_dispatch_cost"] = costs["s2_dispatch_cost"]
            row["cost_saving"] = costs["cost_saving"]
        except Exception as e:
            print(f"Dispatch cost exception: {e}")

        row["status"] = "OK"
        append_row(csv_path, row)
        rows_written += 1

    return rows_written, "solved", measured_norm


def _base_row(meta, weight, exposure_n, cfg, threads=1, solver_config="handy",
              lam=None, normalizer=None) -> dict:
    """Create a row dict with instance metadata and config params."""
    return {
        "instance_name": meta.name,
        "instance_type": meta.instance_type,
        "instance_size": meta.size,
        "seed": meta.seed,
        "n_locations": meta.n_locations,
        "n_parts": meta.n_parts,
        "n_routes": meta.n_routes,
        "n_transports": meta.n_transports,
        "density": meta.density,
        "capacity_tightness": meta.capacity_tightness,
        "weight": weight,
        "lambda_rel": "" if lam is None else lam,
        "weight_normalizer": "" if normalizer is None else round(normalizer, 4),
        "exposure_n": exposure_n,
        "threads": threads,
        "solver_config": solver_config,
        "s2_config": cfg.name,
        "hetero_on": cfg.hetero_on,
        "concentrated_on": cfg.concentrated_on,
    }


# ── Instance discovery ────────────────────────────────────────────────


def discover_instances(
    instance_dir: Path,
    instance_filter: str | None = None,
) -> list[Path]:
    """Find all .lp instance files."""
    instances = sorted(
        list(instance_dir.glob("layered_*.lp"))
        + list(instance_dir.glob("industry_test_*.lp"))
    )
    if instance_filter:
        instances = [f for f in instances if instance_filter in f.stem]
    return instances


# ── CLI ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Two-stage resilience experiment: weight x S2 config grid",
    )
    p.add_argument("--instance-dir", type=Path, default=INSTANCE_DIR)
    p.add_argument("--instance-filter", type=str, default=None,
                   help="Only instances whose name contains this string")
    wg = p.add_mutually_exclusive_group()
    wg.add_argument("--weights", type=int, nargs="+", default=[0, 1000],
                    help="Absolute exposure-penalty weights")
    wg.add_argument("--weights-relative", type=float, nargs="+", default=None,
                    metavar="LAMBDA",
                    help="Relative weight sweep: each lambda is multiplied by "
                         "the instance's mean trip dispatch cost (measured on "
                         "the w=0 solve) and rounded to an integer weight. "
                         "lambda=0 is always run first as the anchor/probe.")
    p.add_argument("--exposure-n", type=int, default=3)
    p.add_argument("--s2-configs", nargs="+", default=DEFAULT_S2_CONFIGS,
                   choices=list(S2_CONFIGS.keys()))
    p.add_argument("--time-small", type=int, default=600)
    p.add_argument("--time-medium", type=int, default=600)
    p.add_argument("--time-large", type=int, default=600)
    p.add_argument("--time-xlarge", type=int, default=600)
    p.add_argument("--time-industrylite", type=int, default=600)
    p.add_argument("--time-industry", type=int, default=20000)
    p.add_argument("--time-paper", type=int, default=600)
    p.add_argument("--round-timeout", type=int, default=None,
                   help="Multi-shot round length in seconds. Default: one "
                        "single-shot solve using the full per-size time limit "
                        "(recommended; the multi-shot early exit can return "
                        "suboptimal solutions and lose optimality proofs).")
    p.add_argument("--max-freq", type=int, default=20)
    p.add_argument("--cap-size-divide", type=int, default=1)
    p.add_argument("-t", "--threads", type=int, default=1)
    p.add_argument("--thread-sweep", type=int, nargs="+", default=None,
                   help="Sweep over multiple thread counts (e.g. --thread-sweep 1 2 4 8)")
    p.add_argument("--configuration", type=str, default="handy",
                   choices=["many", "frumpy", "crafty", "trendy", "jumpy",
                            "handy", "auto"])
    p.add_argument("--config-sweep", type=str, nargs="+", default=None,
                   choices=["many", "frumpy", "crafty", "trendy", "jumpy",
                            "handy", "auto"],
                   help="Sweep over multiple clingo configurations")
    p.add_argument("--s1-encoding", type=Path, default=None)
    p.add_argument("--s2-encoding", type=Path, default=None)
    p.add_argument("--output", "-o", type=Path, default=None)
    p.add_argument("--resume", action="store_true",
                   help="Skip already-completed (instance, weight, config)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    instances = discover_instances(args.instance_dir, args.instance_filter)
    if not instances:
        sys.exit(f"No instances found in {args.instance_dir}")

    # Build sweep grid
    thread_counts = args.thread_sweep or [args.threads]
    configurations = args.config_sweep or [args.configuration]

    s1_enc = args.s1_encoding or DEFAULT_S1_ENCODING
    s2_enc = args.s2_encoding or DEFAULT_S2_ENCODING

    # Output path
    output = args.output
    if output is None:
        if args.weights_relative is not None:
            lams = sorted(set(args.weights_relative) | {0.0})
            wstr = f"lam{lams[0]:g}_{lams[-1]:g}".replace(".", "p")
        else:
            w = sorted(args.weights)
            wstr = f"w{w[0]}_{w[-1]}" if len(w) > 1 else f"w{w[0]}"
        output = (
            RESULTS_DIR
            / f"experiment__{wstr}__n{args.exposure_n}"
              f"__{'_'.join(args.s2_configs)}.csv"
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    n_weight_points = (
        len(set(args.weights_relative) | {0.0})
        if args.weights_relative is not None
        else len(args.weights)
    )
    total_runs = (
        len(instances) * n_weight_points * len(args.s2_configs)
        * len(thread_counts) * len(configurations)
    )

    completed = load_completed(output) if args.resume else set()

    print(f"{'=' * 70}")
    print(f"  TWO-STAGE RESILIENCE EXPERIMENT")
    print(f"  S1 encoding:  {s1_enc.name}")
    print(f"  S2 encoding:  {s2_enc.name}")
    print(f"  Instances:    {len(instances)}")
    if args.weights_relative is not None:
        print(f"  Lambdas:      {sorted(set(args.weights_relative) | {0.0})}"
              f"  (relative: weight = lambda x mean trip cost at w=0)")
    else:
        print(f"  Weights:      {sorted(args.weights)}")
    print(f"  Exposure N:   {args.exposure_n}")
    print(f"  S2 configs:   {args.s2_configs}")
    print(f"  Threads:      {thread_counts}")
    print(f"  Configurations: {configurations}")
    print(f"  Total runs:   {total_runs}")
    print(f"  Output:       {output}")
    if completed:
        print(f"  Resuming:     {len(completed)} rows done")
    print(f"{'=' * 70}")

    t_start = time.perf_counter()
    rows_total = 0

    for threads in thread_counts:
        for configuration in configurations:
            exp_config = ExperimentConfig(
                weights=sorted(args.weights),
                exposure_n=args.exposure_n,
                s2_configs=args.s2_configs,
                max_freq=args.max_freq,
                cap_size_divide=args.cap_size_divide,
                threads=threads,
                configuration=configuration,
                round_timeout=args.round_timeout,
                time_limits={
                    "paper": args.time_paper,
                    "small": args.time_small,
                    "medium": args.time_medium,
                    "large": args.time_large,
                    "xlarge": args.time_xlarge,
                    "industrylite": args.time_industrylite,
                    "industry": args.time_industry,
                    "default": 120,
                },
            )

            if len(thread_counts) > 1 or len(configurations) > 1:
                print(f"\n{'─' * 70}")
                print(f"  Sweep: threads={threads}, config={configuration}")
                print(f"{'─' * 70}")

            for inst_path in instances:
                meta = classify_instance(inst_path)
                instance = parse_instance(inst_path)
                compute_instance_properties(meta, instance)

                print(f"  Instance: {meta.name}  ")
                print(f"  Properties: {meta.n_locations} locs, "
                      f"{meta.n_parts} parts, {meta.n_routes} routes, "
                      f"density={meta.density}, tightness={meta.capacity_tightness}")
                if args.weights_relative is None:
                    for w in exp_config.weights:
                        n, _, _ = run_weight_group(
                            inst_path, instance, meta,
                            weight=w,
                            exp_config=exp_config,
                            csv_path=output,
                            completed=completed,
                            s1_encoding=s1_enc,
                            s2_encoding=s2_enc,
                        )
                        rows_total += n
                    continue

                # ── Relative mode: lambda=0 first to measure the scale ──
                lams = sorted(set(args.weights_relative) | {0.0})

                norm = load_normalizer(output, meta.name) if args.resume else None
                n, s1_state, measured = run_weight_group(
                    inst_path, instance, meta,
                    weight=0,
                    exp_config=exp_config,
                    csv_path=output,
                    completed=completed,
                    s1_encoding=s1_enc,
                    s2_encoding=s2_enc,
                    lam=0.0,
                    normalizer=norm,
                )
                rows_total += n
                if norm is None:
                    norm = measured
                if norm is None and s1_state == "skipped":
                    # lambda=0 rows predate the weight_normalizer column
                    print(f"  [relative] lambda=0 already done, probing "
                          f"Stage 1 at w=0 for the normalizer...")
                    norm = stage1_probe(inst_path, instance, meta,
                                        exp_config, s1_enc, s2_enc)
                if norm is None:
                    print(f"  [relative] no normalizer for {meta.name} "
                          f"(Stage 1 UNSAT?) -- skipping remaining lambdas")
                    continue

                print(f"  [relative] normalizer (mean trip cost at w=0) "
                      f"= {norm:.2f}")
                seen_weights = {0}
                for lam in lams:
                    if lam == 0.0:
                        continue
                    w = max(1, round(lam * norm))
                    if w in seen_weights:
                        print(f"  [relative] lambda={lam:g} -> weight={w} "
                              f"duplicates an earlier lambda, skipping")
                        continue
                    seen_weights.add(w)
                    print(f"  [relative] lambda={lam:g} -> weight={w}")
                    n, _, _ = run_weight_group(
                        inst_path, instance, meta,
                        weight=w,
                        exp_config=exp_config,
                        csv_path=output,
                        completed=completed,
                        s1_encoding=s1_enc,
                        s2_encoding=s2_enc,
                        lam=lam,
                        normalizer=norm,
                    )
                    rows_total += n

    elapsed = time.perf_counter() - t_start
    print(f"\n{'=' * 70}")
    print(f"  COMPLETE: {rows_total} rows in {elapsed:.1f}s")
    print(f"  Results -> {output}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
