#!/usr/bin/env python3
"""
run_experiment.py
=================
div_weight sweep across multiple instances.
Loops (instance x weight), runs Stage 1 + R_TR, writes crash-safe CSV.

Usage
-----
    python run_experiment.py
    python run_experiment.py --instances-dir instances/generated \
        --weights 0 50 100 200 500 1000 --output results/div_weight_sweep.csv
    python run_experiment.py --resume   # skip already-completed rows
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

from main import parse_instance, solve_stage1, compute_r_tr

# ── Constants ────────────────────────────────────────────────────────────

DEFAULT_WEIGHTS = [0, 25, 50, 100, 150, 200, 300, 500, 750, 1000]

SIZE_TIME_DEFAULTS = {"small": 30, "medium": 60, "large": 120}

COLUMNS = [
    "instance_name",
    "instance_size",
    "seed",
    "div_weight",
    "nominal_cost",
    "dominant_count",
    "r_tr",
    "worst_arc",
    "worst_arc_coverage",
    "s1_optimal",
    "s1_time",
    "status",
]


# ── Helpers ──────────────────────────────────────────────────────────────

def classify_instance(filename: str) -> tuple[str, int]:
    """Return (size, seed) from a filename like 'small_seed3.lp'.
    Falls back to ('custom', 0) for non-standard names."""
    m = re.match(r"(small|medium|large)_seed(\d+)", filename)
    if not m:
        return "custom", 0
    return m.group(1), int(m.group(2))


def discover_instances(instances_dir: Path) -> list[Path]:
    """Return sorted list of .lp instance files."""
    files = sorted(instances_dir.glob("*.lp"))
    if not files:
        sys.exit(f"No instance files found in {instances_dir}")
    return files


def load_completed(csv_path: Path) -> set[tuple[str, int]]:
    """Return set of (instance_name, div_weight) pairs already in CSV."""
    completed = set()
    if not csv_path.exists():
        return completed
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            completed.add((row["instance_name"], int(row["div_weight"])))
    return completed


def append_row(csv_path: Path, row: dict) -> None:
    """Append a single row to the CSV (crash-safe checkpoint)."""
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in COLUMNS})


# ── Core experiment ──────────────────────────────────────────────────────

def run_single(
    instance_path: Path,
    instance_data: dict,
    instance_name: str,
    instance_size: str,
    seed: int,
    div_weight: int,
    time_limit: int,
    cap_divide: int,
    max_freq: int,
) -> dict:
    """Run Stage 1 + R_TR for one (instance, weight) pair."""

    row = {
        "instance_name": instance_name,
        "instance_size": instance_size,
        "seed": seed,
        "div_weight": div_weight,
    }

    # ── Stage 1 ──────────────────────────────────────────────────────
    print(f"\n  [{instance_name} w={div_weight}] Solving Stage 1 "
          f"(limit={time_limit}s)...")

    try:
        stage1 = solve_stage1(
            str(instance_path),
            div_weight=div_weight,
            time_limit=time_limit,
            cap_divide=cap_divide,
            max_freq=max_freq,
        )
    except Exception as e:
        print(f"  Stage 1 exception: {e}")
        stage1 = None

    if stage1 is None:
        row.update({
            "nominal_cost": None,
            "dominant_count": None,
            "r_tr": None,
            "worst_arc": None,
            "worst_arc_coverage": None,
            "s1_optimal": False,
            "s1_time": None,
            "status": "UNSAT",
        })
        return row

    nominal_cost = stage1["cost"]
    dominant_count = len(stage1["dominant"])

    row["nominal_cost"] = nominal_cost
    row["dominant_count"] = dominant_count
    row["s1_optimal"] = stage1["optimum"]
    row["s1_time"] = stage1["time"]

    print(f"  Stage 1 done: cost={nominal_cost}  dominant={dominant_count}  "
          f"optimal={stage1['optimum']}  time={stage1['time']}s")

    # ── R_TR ─────────────────────────────────────────────────────────
    print(f"  [{instance_name} w={div_weight}] Computing R_TR...")

    try:
        r_tr, details = compute_r_tr(stage1["loads"], instance_data)

        if details:
            worst = min(details, key=lambda d: d["coverage"])
            worst_arc_str = f"({worst['lost_f']},{worst['lost_t']},{worst['lost_tr']})"
            row["r_tr"] = r_tr
            row["worst_arc"] = worst_arc_str
            row["worst_arc_coverage"] = worst["coverage"]
        else:
            row["r_tr"] = 1.0
            row["worst_arc"] = None
            row["worst_arc_coverage"] = None

        row["status"] = "OK"

    except Exception as e:
        print(f"  R_TR exception: {e}")
        row["r_tr"] = None
        row["worst_arc"] = None
        row["worst_arc_coverage"] = None
        row["status"] = f"R_TR_ERROR: {e}"

    return row


# ── CLI + main ───────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="div_weight sweep: Stage 1 + R_TR across instances")
    p.add_argument("--instances-dir", type=Path,
                   default=Path("instances/generated"),
                   help="Directory with instance .lp files")
    p.add_argument("--weights", type=int, nargs="+",
                   default=DEFAULT_WEIGHTS,
                   help="div_weight values to sweep")
    p.add_argument("--time-small", type=int, default=30,
                   help="Time limit for small instances (s)")
    p.add_argument("--time-medium", type=int, default=60,
                   help="Time limit for medium instances (s)")
    p.add_argument("--time-large", type=int, default=120,
                   help="Time limit for large instances (s)")
    p.add_argument("--instance-filter", type=str, default=None,
                   help="Only run instances whose name contains this string "
                        "(e.g. 'small_seed1')")
    p.add_argument("--cap-divide", type=int, default=1)
    p.add_argument("--max-freq", type=int, default=20)
    p.add_argument("--output", "-o", type=Path,
                   default=Path("results/div_weight_sweep.csv"),
                   help="Output CSV path")
    p.add_argument("--resume", action="store_true",
                   help="Skip already-completed (instance, weight) pairs")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    time_limits = {
        "small": args.time_small,
        "medium": args.time_medium,
        "large": args.time_large,
        "custom": args.time_small,
    }

    instances = discover_instances(args.instances_dir)
    if args.instance_filter:
        instances = [f for f in instances if args.instance_filter in f.stem]
        if not instances:
            sys.exit(f"No instances match filter '{args.instance_filter}'")
    weights = sorted(args.weights)
    total_runs = len(instances) * len(weights)

    completed = load_completed(args.output) if args.resume else set()
    if args.resume and completed:
        print(f"Resuming: {len(completed)} rows already completed")

    print(f"Instances: {len(instances)}  Weights: {weights}")
    print(f"Total runs: {total_runs}  Output: {args.output}")
    print(f"Time limits: {time_limits}")

    t_start = time.perf_counter()
    run_count = 0

    # Instance-first (outer), weight-second (inner)
    for inst_path in instances:
        inst_name = inst_path.stem
        inst_size, seed = classify_instance(inst_name)
        time_limit = time_limits[inst_size]

        print(f"\n{'═' * 65}")
        print(f"  Instance: {inst_name} ({inst_size}, seed={seed})")
        print(f"{'═' * 65}")

        # Parse instance once per instance (not per weight)
        instance_data = parse_instance(str(inst_path))
        print(f"  Parsed: {len(instance_data['parts'])} parts, "
              f"{len(instance_data['routes'])} routes")

        for w in weights:
            if (inst_name, w) in completed:
                print(f"  [{inst_name} w={w}] Already completed, skipping.")
                continue

            run_count += 1
            remaining = total_runs - run_count - len(completed)
            print(f"\n  --- Run {run_count + len(completed)}/{total_runs} "
                  f"({remaining} remaining) ---")

            row = run_single(
                inst_path, instance_data, inst_name, inst_size, seed,
                w, time_limit, args.cap_divide, args.max_freq,
            )
            append_row(args.output, row)
            print(f"  Checkpointed → {args.output}")

    elapsed = time.perf_counter() - t_start
    print(f"\n{'═' * 65}")
    print(f"  COMPLETE: {run_count} runs in {elapsed:.1f}s")
    print(f"  Results → {args.output}")
    print(f"{'═' * 65}")


if __name__ == "__main__":
    main()
