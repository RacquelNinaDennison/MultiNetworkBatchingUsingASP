#!/usr/bin/env python3
"""
run_full_experiment.py
=====================
Full two-stage experiment sweep: Stage 1 (div_weight) × Stage 2 (config).

Supports three experiment modes:
  A) Stage 1 sweep:  vary div_weight, fix Stage 2 config
  B) Stage 2 sweep:  fix div_weight, vary Stage 2 config
  C) Combined sweep:  vary both

Usage
-----
    # Experiment A: Stage 1 weight sweep, Stage 2 = both constraints on
    python run_full_experiment.py \\
        --instances-dir ../../../instances/generated \\
        --div-weights 0 50 100 200 500 1000 \\
        --s2-configs both

    # Experiment B: Fix Stage 1, sweep Stage 2 configs
    python run_full_experiment.py \\
        --div-weights 100 \\
        --s2-configs off_off hetero conc both

    # Experiment C: Full grid
    python run_full_experiment.py \\
        --div-weights 0 50 100 200 500 1000 \\
        --s2-configs off_off hetero conc both

    # Resume after crash
    python run_full_experiment.py --resume
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

from main import (
    parse_instance,
    solve_stage1,
    compute_r_tr,
    build_stage2_facts,
    solve_stage2,
    compute_r1,
    compute_dispatch_costs,
)


# ── Stage 2 configurations ───────────────────────────────────────────────

S2_CONFIGS = {
    "off_off": {"hetero_on": 0, "concentrated_on": 0},
    "hetero":  {"hetero_on": 1, "concentrated_on": 0},
    "conc":    {"hetero_on": 0, "concentrated_on": 1},
    "both":    {"hetero_on": 1, "concentrated_on": 1},
}

DEFAULT_WEIGHTS = [0, 50, 100, 200, 500, 1000]
DEFAULT_S2      = ["off_off", "hetero", "conc", "both"]

SIZE_TIME_DEFAULTS = {"small": 30, "medium": 60}

COLUMNS = [
    "instance_name",
    "instance_size",
    "seed",
    "div_weight",
    "s2_config",
    "hetero_on",
    "concentrated_on",
    "nominal_cost",
    "dominant_count",
    "r_tr",
    "worst_arc",
    "r_1",
    "worst_trip",
    "mono_count",
    "concentrated_count",
    "s1_optimal",
    "s1_time",
    "s1_trajectory",
    "s1_dispatch_cost",
    "s2_dispatch_cost",
    "cost_saving",
    "s2_optimal",
    "s2_time",
    "s2_trajectory",
    "status",
]


# ── Helpers ──────────────────────────────────────────────────────────────

def classify_instance(filename: str) -> tuple[str, int]:
    m = re.match(r"(small|medium)_seed(\d+)", filename)
    if not m:
        return "custom", 0
    return m.group(1), int(m.group(2))


def discover_instances(instances_dir: Path) -> list[Path]:
    files = sorted(instances_dir.glob("*.lp"))
    if not files:
        sys.exit(f"No instance files found in {instances_dir}")
    return files


def load_completed(csv_path: Path) -> set[tuple[str, int, str]]:
    """Return set of (instance_name, div_weight, s2_config) already done."""
    completed = set()
    if not csv_path.exists():
        return completed
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            completed.add((
                row["instance_name"],
                int(row["div_weight"]),
                row["s2_config"],
            ))
    return completed


def append_row(csv_path: Path, row: dict) -> None:
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in COLUMNS})


# ── Core experiment ──────────────────────────────────────────────────────

def run_stage1_group(
    instance_path:  Path,
    instance_data:  dict,
    instance_name:  str,
    instance_size:  str,
    seed:           int,
    div_weight:     int,
    s2_configs:     list[str],
    s1_time_limit:  int,
    s2_time_limit:  int,
    cap_divide:     int,
    max_freq:       int,
    csv_path:       Path,
    completed:      set,
) -> int:
    """Run Stage 1 once, then Stage 2 for each config. Returns rows written."""

    configs_todo = [c for c in s2_configs
                    if (instance_name, div_weight, c) not in completed]
    if not configs_todo:
        return 0

    # ── Stage 1 ──────────────────────────────────────────────────────
    print(f"\n  [{instance_name} w={div_weight}] Solving Stage 1 "
          f"(limit={s1_time_limit}s)...")

    try:
        stage1 = solve_stage1(
            str(instance_path),
            div_weight=div_weight,
            time_limit=s1_time_limit,
            cap_divide=cap_divide,
            max_freq=max_freq,
        )
    except Exception as e:
        print(f"  Stage 1 exception: {e}")
        stage1 = None

    if stage1 is None:
        for cfg in configs_todo:
            row = _make_row(instance_name, instance_size, seed,
                            div_weight, cfg, status="S1_UNSAT")
            append_row(csv_path, row)
        return len(configs_todo)

    nominal_cost   = stage1["cost"]
    dominant_count = len(stage1["dominant"])

    print(f"Stage 1: cost={nominal_cost}  dominant={dominant_count}  "
          f"optimal={stage1['optimum']}")

    # ── R_TR ─────────────────────────────────────────────────────────
    try:
        r_tr, rtr_details = compute_r_tr(stage1["loads"], instance_data)
        worst_rtr = min(rtr_details, key=lambda d: d["coverage"])
        worst_arc_str = (f"({worst_rtr['lost_f']},"
                         f"{worst_rtr['lost_t']},"
                         f"{worst_rtr['lost_tr']})")
    except Exception as e:
        print(f"  R_TR exception: {e}")
        r_tr, worst_arc_str = None, None

    print(f"  R_TR={r_tr}  worst_arc={worst_arc_str}")

    # ── Stage 2 facts (shared across configs) ────────────────────────
    s2_facts = build_stage2_facts(stage1, instance_data)

    # ── Stage 2 per config ───────────────────────────────────────────
    rows_written = 0
    for cfg in configs_todo:
        cfg_params = S2_CONFIGS[cfg]
        print(f"\n  [{instance_name} w={div_weight} s2={cfg}] "
              f"Solving Stage 2 (limit={s2_time_limit}s)...", end="")

        row = {
            "instance_name":  instance_name,
            "instance_size":  instance_size,
            "seed":           seed,
            "div_weight":     div_weight,
            "s2_config":      cfg,
            "hetero_on":      cfg_params["hetero_on"],
            "concentrated_on": cfg_params["concentrated_on"],
            "nominal_cost":   nominal_cost,
            "dominant_count": dominant_count,
            "r_tr":           r_tr,
            "worst_arc":      worst_arc_str,
            "s1_optimal":     stage1["optimum"],
            "s1_time":        stage1["time"],
            "s1_trajectory":  json.dumps(stage1.get("trajectory", [])),
        }

        try:
            stage2 = solve_stage2(
                s2_facts,
                hetero_on=cfg_params["hetero_on"],
                concentrated_on=cfg_params["concentrated_on"],
                time_limit=s2_time_limit,
            )
        except Exception as e:
            print(f"  Stage 2 exception: {e}")
            stage2 = None

        if stage2 is None:
            row.update({
                "r_1": None, "worst_trip": None,
                "mono_count": None, "concentrated_count": None,
                "s2_optimal": False, "s2_time": None,
                "status": "S2_UNSAT",
            })
            append_row(csv_path, row)
            rows_written += 1
            continue

        row["mono_count"]         = stage2["mono_count"]
        row["concentrated_count"] = stage2["concentrated_count"]
        row["s2_optimal"]         = stage2["optimum"]
        row["s2_trajectory"]      = json.dumps(stage2.get("trajectory", []))
        row["s2_time"]            = stage2["time"]

        print(f"  Stage 2: mono={stage2['mono_count']}  "
              f"conc={stage2['concentrated_count']}  "
              f"optimal={stage2['optimum']}")

        # ── R_1 ──────────────────────────────────────────────────────
        try:
            r_1, r1_details = compute_r1(
                stage2["trip_loads"], stage1["loads"], instance_data,
            )
            worst_r1 = min(r1_details, key=lambda d: d["coverage"])
            row["r_1"]        = r_1
            row["worst_trip"]  = worst_r1["lost_trip"]
            row["status"]      = "OK"
        except Exception as e:
            print(f"  R_1 exception: {e}")
            row["r_1"]        = None
            row["worst_trip"]  = None
            row["status"]      = f"R1_ERROR: {e}"

        print(f"  R_1={row.get('r_1')}  worst_trip={row.get('worst_trip')}")

        # ── Dispatch costs ───────────────────────────────────────────
        costs = compute_dispatch_costs(stage1, stage2, instance_data)
        row["s1_dispatch_cost"] = costs["s1_dispatch_cost"]
        row["s2_dispatch_cost"] = costs["s2_dispatch_cost"]
        row["cost_saving"]      = costs["cost_saving"]

        print(f"  Dispatch: s1={costs['s1_dispatch_cost']}  "
              f"s2={costs['s2_dispatch_cost']}  "
              f"saving={costs['cost_saving']}")

        append_row(csv_path, row)
        rows_written += 1

    return rows_written


def _make_row(name, size, seed, weight, cfg, status):
    cfg_params = S2_CONFIGS[cfg]
    return {
        "instance_name": name, "instance_size": size, "seed": seed,
        "div_weight": weight, "s2_config": cfg,
        "hetero_on": cfg_params["hetero_on"],
        "concentrated_on": cfg_params["concentrated_on"],
        "status": status,
    }


# ── CLI ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Full two-stage experiment: div_weight × Stage 2 config")
    p.add_argument("--instances-dir", type=Path,
                   default=Path("../../../instances/generated"),
                   help="Directory with instance .lp files")
    p.add_argument("--instance-filter", type=str, default=None,
                   help="Only instances whose name contains this string")
    p.add_argument("--div-weights", type=int, nargs="+",
                   default=DEFAULT_WEIGHTS)
    p.add_argument("--s2-configs", nargs="+", default=DEFAULT_S2,
                   choices=list(S2_CONFIGS.keys()),
                   help="Stage 2 configs to sweep")
    p.add_argument("--time-s1-small",  type=int, default=30)
    p.add_argument("--time-s1-medium", type=int, default=60)
    p.add_argument("--time-s1-large",  type=int, default=120)
    p.add_argument("--time-s2",        type=int, default=30,
                   help="Stage 2 time limit per config (seconds)")
    p.add_argument("--cap-divide", type=int, default=1)
    p.add_argument("--max-freq",   type=int, default=20)
    p.add_argument("--output", "-o", type=Path, default=None,
                   help="Output CSV path (auto-generated from params if omitted)")
    p.add_argument("--resume", action="store_true",
                   help="Skip already-completed (instance, weight, config)")
    return p.parse_args()


def _auto_output_name(args: argparse.Namespace) -> Path:
    """Build a descriptive filename from the run parameters."""
    parts = []

    # Instance filter or "all"
    parts.append(args.instance_filter if args.instance_filter else "all")

    # Weights summary
    w = sorted(args.div_weights)
    if len(w) <= 3:
        parts.append("w" + "_".join(str(x) for x in w))
    else:
        parts.append(f"w{w[0]}-{w[-1]}x{len(w)}")

    # S2 configs summary
    parts.append("s2_" + "_".join(args.s2_configs))

    name = "__".join(parts) + ".csv"
    return Path("results") / name


def main() -> None:
    args = parse_args()

    if args.output is None:
        args.output = _auto_output_name(args)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    s1_time = {
        "small":  args.time_s1_small,
        "medium": args.time_s1_medium,
        "custom": args.time_s1_small,
    }

    instances = discover_instances(args.instances_dir)
    if args.instance_filter:
        instances = [f for f in instances if args.instance_filter in f.stem]
        if not instances:
            sys.exit(f"No instances match filter '{args.instance_filter}'")

    weights    = sorted(args.div_weights)
    s2_configs = args.s2_configs
    total_runs = len(instances) * len(weights) * len(s2_configs)

    completed = load_completed(args.output) if args.resume else set()
    if completed:
        print(f"Resuming: {len(completed)} rows already completed")

    print(f"Instances:  {len(instances)}")
    print(f"Weights:    {weights}")
    print(f"S2 configs: {s2_configs}")
    print(f"Total runs: {total_runs}  Output: {args.output}")

    t_start    = time.perf_counter()
    rows_total = 0

    for inst_path in instances:
        inst_name = inst_path.stem
        inst_size, seed = classify_instance(inst_name)

        print(f"\n{'═' * 70}")
        print(f"  Instance: {inst_name} ({inst_size}, seed={seed})")
        print(f"{'═' * 70}")

        instance_data = parse_instance(str(inst_path))
        print(f"  Parsed: {len(instance_data['parts'])} parts, "
              f"{len(instance_data['routes'])} routes")

        for w in weights:
            n = run_stage1_group(
                inst_path, instance_data, inst_name, inst_size, seed,
                div_weight=w,
                s2_configs=s2_configs,
                s1_time_limit=s1_time[inst_size],
                s2_time_limit=args.time_s2,
                cap_divide=args.cap_divide,
                max_freq=args.max_freq,
                csv_path=args.output,
                completed=completed,
            )
            rows_total += n

    elapsed = time.perf_counter() - t_start
    print(f"\n{'═' * 70}")
    print(f"  COMPLETE: {rows_total} rows in {elapsed:.1f}s")
    print(f"  Results → {args.output}")
    print(f"{'═' * 70}")


if __name__ == "__main__":
    main()
