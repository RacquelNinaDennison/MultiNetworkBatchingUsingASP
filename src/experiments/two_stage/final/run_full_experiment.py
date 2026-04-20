#!/usr/bin/env python3
"""
run_full_experiment.py
=====================
Full naive two-stage experiment sweep: Stage 1 (weight) × Stage 2 (config).

Uses the final encodings under experiments/two_stage/final/encodings/.

Runs on:
  - Layered instances:  instances/generated/layered_*.lp
  - Industry instances: instances/industry/industry_test_*.lp

Metrics captured per run:
  R_TR, R_1, S1 cost, S2 cost, S1/S2 dispatch costs, cost_saving,
  mono_count, concentrated_count, optimality flags, solve times.

Usage
-----
    # Full grid: layered + industry, all S2 configs
    python run_full_experiment.py

    # Only layered instances
    python run_full_experiment.py --skip-industry

    # Only industry instances
    python run_full_experiment.py --skip-layered

    # Resume after crash
    python run_full_experiment.py --resume
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parent.parent.parent  # src/

sys.path.insert(0, str(SRC_DIR))

from main import (
    parse_instance,
    solve_stage1,
    solve_stage2_from_stage1,
    compute_r_tr,
    compute_r1,
    compute_r_alpha,
    compute_kit_ratio,
    compute_dispatch_costs,
)

# ── Encoding paths (final versions) ──────────────────────────────────────

FINAL_ENCODINGS = SCRIPT_DIR / "encodings"
STAGE1_ENCODING = FINAL_ENCODINGS / "stage_1_flow.lp"
STAGE1_LIGHT    = SRC_DIR / "encoding" / "twostage" / "clingcon" / "stage_1_clingcon_flow.lp"
STAGE2_ENCODING = FINAL_ENCODINGS / "stage2_packing.lp"
STAGE2_LIGHT    = SRC_DIR / "encoding" / "twostage" / "clingcon" / "stage_2_packing.lp"

# ── Instance directories ─────────────────────────────────────────────────

LAYERED_DIR  = SRC_DIR / "instances" / "generated"
INDUSTRY_DIR = SRC_DIR / "instances" / "industry"

# ── Stage 2 configurations ───────────────────────────────────────────────

S2_CONFIGS = {
    "off_off": {"hetero_on": 0, "concentrated_on": 0},
    "hetero":  {"hetero_on": 1, "concentrated_on": 0},
    "conc":    {"hetero_on": 0, "concentrated_on": 1},
    "both":    {"hetero_on": 1, "concentrated_on": 1},
}

DEFAULT_WEIGHTS = [0, 300]
DEFAULT_S2      = ["off_off", "hetero", "conc", "both"]

ALPHA_VALUES = [0.2, 0.4, 0.6, 0.8]
R_ALPHA_STRATEGIES = ["heaviest", "first", "last"]
R_ALPHA_MODES = ["single", "global"]

def _r_alpha_col(strategy: str, mode: str, alpha: float) -> str:
    return f"r_{strategy}_{mode}_{alpha}"

_R_ALPHA_COLUMNS = [
    _r_alpha_col(s, m, a)
    for s in R_ALPHA_STRATEGIES
    for m in R_ALPHA_MODES
    for a in ALPHA_VALUES
]

_FIRST_R_ALPHA_COLUMNS = [f"first_{c}" for c in _R_ALPHA_COLUMNS]

COLUMNS = [
    "instance_name",
    "instance_type",
    "instance_size",
    "seed",
    "weight",
    "exposure_n",
    "s2_config",
    "hetero_on",
    "concentrated_on",
    "nominal_cost",
    "exposure_count",
    "r_tr",
    "worst_arc",
    "r_1",
    "worst_trip",
    "k_1",
    "kit_bottleneck_trip",
    "kit_bottleneck_part",
    "mono_count",
    "concentrated_count",
    *_R_ALPHA_COLUMNS,
    "s1_optimal",
    "s1_time",
    "s1_trajectory",
    "s1_dispatch_cost",
    "s2_dispatch_cost",
    "cost_saving",
    "s2_optimal",
    "s2_time",
    "s2_trajectory",
    # ── first-solution metrics ──
    "first_s1_time",
    "first_s1_cost",
    "first_r_tr",
    "first_s2_time",
    "first_s2_cost",
    "first_r_1",
    "first_k_1",
    "first_mono_count",
    "first_concentrated_count",
    "first_s1_dispatch_cost",
    "first_s2_dispatch_cost",
    *_FIRST_R_ALPHA_COLUMNS,
    "status",
]


# ── Helpers ──────────────────────────────────────────────────────────────

_RE_LAYERED = re.compile(r"layered_(small|medium|large|xlarge|industrylite)_seed(\d+)")
_RE_INDUSTRY = re.compile(r"industry_test_(\d+)")


def classify_instance(filename: str) -> dict:
    """Classify an instance file into type/size/seed metadata."""
    m = _RE_LAYERED.match(filename)
    if m:
        return {
            "instance_type": "layered",
            "instance_size": m.group(1),
            "seed": int(m.group(2)),
        }

    if filename == "layered_paper":
        return {
            "instance_type": "layered",
            "instance_size": "paper",
            "seed": 0,
        }

    m = _RE_INDUSTRY.match(filename)
    if m:
        return {
            "instance_type": "industry",
            "instance_size": "industry",
            "seed": int(m.group(1)),
        }

    if filename.startswith("industry"):
        return {
            "instance_type": "industry",
            "instance_size": "industry",
            "seed": 0,
        }

    return {
        "instance_type": "custom",
        "instance_size": "custom",
        "seed": 0,
    }


def discover_layered_instances(inst_dir: Path) -> list[Path]:
    """Find layered_*.lp instances."""
    return sorted(inst_dir.glob("layered_*.lp"))


def discover_industry_instances(inst_dir: Path) -> list[Path]:
    """Find industry_*.lp instances."""
    return sorted(inst_dir.glob("industry_*.lp"))


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


def append_row(csv_path: Path, row: dict) -> None:
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in COLUMNS})


# ── Time limit selection ─────────────────────────────────────────────────

def get_time_limit(instance_size: str, time_map: dict[str, int]) -> int:
    return time_map.get(instance_size, time_map.get("default", 120))


# ── Core experiment ──────────────────────────────────────────────────────

def run_weight_group(
    instance_path:  Path,
    instance_data:  dict,
    instance_name:  str,
    meta:           dict,
    weight:         int,
    exposure_n:     int,
    s2_configs:     list[str],
    time_limit:     int,
    max_freq:       int,
    csv_path:       Path,
    completed:      set,
    s1_encoding:    Path | None = None,
    s2_encoding:    Path | None = None,
    threads:        int = 1,
    configuration:  str | None = None,
    cap_size_divide: int = 1,
) -> int:
    """Solve Stage 1 once, compute R_TR once, then loop Stage 2 configs."""

    configs_todo = [c for c in s2_configs
                    if (instance_name, weight, c) not in completed]
    if not configs_todo:
        return 0

    s1_enc = str(s1_encoding) if s1_encoding else str(STAGE1_ENCODING)
    s2_enc = str(s2_encoding) if s2_encoding else str(STAGE2_ENCODING)

    # ── Solve Stage 1 once ────────────────────────────────────────────
    print(f"\n  [{instance_name} w={weight}] Stage 1 solve "
          f"(limit={time_limit}s, enc={Path(s1_enc).name})...")

    try:
        solver, stage1 = solve_stage1(
            str(instance_path),
            weight=weight,
            time_limit=time_limit,
            max_freq=max_freq,
            exposure_n=exposure_n,
            stage1_encoding=s1_enc,
            threads=threads,
            configuration=configuration,
            cap_size_divide=cap_size_divide,
        )
    except Exception as e:
        print(f"  Stage 1 exception: {e}")
        stage1 = None
        solver = None

    if stage1 is None:
        print("  Stage 1: UNSAT — no feasible flow")
        for cfg in configs_todo:
            cfg_params = S2_CONFIGS[cfg]
            row = {
                "instance_name":   instance_name,
                "instance_type":   meta["instance_type"],
                "instance_size":   meta["instance_size"],
                "seed":            meta["seed"],
                "weight":          weight,
                "exposure_n":      exposure_n,
                "s2_config":       cfg,
                "hetero_on":       cfg_params["hetero_on"],
                "concentrated_on": cfg_params["concentrated_on"],
                "status":          "S1_UNSAT",
            }
            append_row(csv_path, row)
        return len(configs_todo)

    print(f"  Stage 1: cost={stage1['cost']}  "
          f"routes={len(stage1['route_freqs'])}  "
          f"loads={len(stage1['loads'])}  "
          f"optimal={stage1['optimum']}")

    # ── Compute R_TR once (depends only on Stage 1 loads) ─────────────
    r_tr_val      = None
    worst_arc_str = None
    try:
        r_tr_val, rtr_details = compute_r_tr(stage1["loads"], instance_data)
        worst_rtr = min(rtr_details, key=lambda d: d["coverage"])
        worst_arc_str = (f"({worst_rtr['lost_f']},"
                         f"{worst_rtr['lost_t']},"
                         f"{worst_rtr['lost_tr']})")
    except Exception as e:
        print(f"  R_TR exception: {e}")

    print(f"  R_TR={r_tr_val}  worst_arc={worst_arc_str}")

    # ── First-solution R_TR (Stage 1) ─────────────────────────────────
    first_s1 = stage1.get("first_solution", {})
    first_r_tr_val = None
    try:
        if first_s1.get("loads"):
            first_r_tr_val, _ = compute_r_tr(first_s1["loads"], instance_data)
    except Exception as e:
        print(f"  First-solution R_TR exception: {e}")

    s1_fields = {
        "nominal_cost":    stage1["cost"],
        "exposure_count":  len(stage1.get("high_exposure", [])),
        "s1_optimal":      stage1["optimum"],
        "s1_time":         stage1.get("time"),
        "s1_trajectory":   json.dumps(stage1.get("trajectory", [])),
        "r_tr":            r_tr_val,
        "worst_arc":       worst_arc_str,
        "first_s1_time":   first_s1.get("time"),
        "first_s1_cost":   first_s1.get("cost"),
        "first_r_tr":      first_r_tr_val,
    }

    # ── Stage 2 per config ────────────────────────────────────────────
    rows_written = 0
    for cfg in configs_todo:
        cfg_params = S2_CONFIGS[cfg]
        print(f"\n  [{instance_name} w={weight} s2={cfg}] "
              f"Stage 2 solve (enc={Path(s2_enc).name})...")

        row = {
            "instance_name":   instance_name,
            "instance_type":   meta["instance_type"],
            "instance_size":   meta["instance_size"],
            "seed":            meta["seed"],
            "weight":          weight,
            "exposure_n":      exposure_n,
            "s2_config":       cfg,
            "hetero_on":       cfg_params["hetero_on"],
            "concentrated_on": cfg_params["concentrated_on"],
        }
        row.update(s1_fields)

        try:
            result = solve_stage2_from_stage1(
                solver,
                stage1,
                hetero_on=cfg_params["hetero_on"],
                concentrated_on=cfg_params["concentrated_on"],
                stage2_encoding=s2_enc,
            )
        except Exception as e:
            print(f"  Stage 2 exception: {e}")
            result = None

        if result is None:
            row["status"] = "S2_UNSAT"
            append_row(csv_path, row)
            rows_written += 1
            continue

        row["mono_count"]         = result.get("mono_count", 0)
        row["concentrated_count"] = result.get("concentrated_count", 0)
        row["s2_optimal"]         = result.get("optimum", False)
        row["s2_time"]            = result.get("time")
        row["s2_trajectory"]      = json.dumps(result.get("trajectory", []))

        print(f"  mono={row['mono_count']}  conc={row['concentrated_count']}  "
              f"optimal={row['s2_optimal']}")

        # ── R_1 ───────────────────────────────────────────────────────
        r1_details = []
        try:
            r_1, r1_details = compute_r1(
                result["trip_loads"], stage1["loads"], instance_data,
            )
            worst_r1 = min(r1_details, key=lambda d: d["coverage"])
            row["r_1"]        = r_1
            row["worst_trip"] = worst_r1["lost_trip"]
        except Exception as e:
            print(f"  R_1 exception: {e}")
            row["r_1"]        = None
            row["worst_trip"] = None

        print(f"  R_1={row.get('r_1')}  worst_trip={row.get('worst_trip')}")

        # ── K_1 (Kit completion ratio) ────────────────────────────────
        try:
            if r1_details:
                k_1, kit_details = compute_kit_ratio(r1_details)
                worst_kit = kit_details[0]
                row["k_1"]                  = k_1
                row["kit_bottleneck_trip"]  = worst_kit["lost_trip"]
                row["kit_bottleneck_part"]  = worst_kit["bottleneck_part"]
            else:
                row["k_1"] = None
        except Exception as e:
            print(f"  K_1 exception: {e}")
            row["k_1"]                 = None
            row["kit_bottleneck_trip"] = None
            row["kit_bottleneck_part"] = None

        print(f"  K_1={row.get('k_1')}")

        # ── R_alpha (partial disruption) ─────────────────────────────
        try:
            for strat in R_ALPHA_STRATEGIES:
                for md in R_ALPHA_MODES:
                    for alph in ALPHA_VALUES:
                        col = _r_alpha_col(strat, md, alph)
                        val, _ = compute_r_alpha(
                            result["trip_loads"], stage1["loads"],
                            instance_data,
                            alpha=alph, mode=md, strategy=strat,
                        )
                        row[col] = val
            print(f"  R_alpha: heaviest_single_0.2={row.get('r_heaviest_single_0.2')}"
                  f"  heaviest_global_0.2={row.get('r_heaviest_global_0.2')}")
        except Exception as e:
            print(f"  R_alpha exception: {e}")

        # ── Dispatch costs ────────────────────────────────────────────
        try:
            costs = compute_dispatch_costs(stage1, result, instance_data)
            row["s1_dispatch_cost"] = costs["s1_dispatch_cost"]
            row["s2_dispatch_cost"] = costs["s2_dispatch_cost"]
            row["cost_saving"]      = costs["cost_saving"]
        except Exception as e:
            print(f"  Dispatch cost exception: {e}")

        # ── First-solution Stage 2 metrics ─────────────────────────────
        first_s2 = result.get("first_solution", {})
        first_s1_loads = first_s1.get("loads", stage1["loads"])
        first_trip_loads = first_s2.get("trip_loads", {})

        row["first_s2_time"]            = first_s2.get("time")
        row["first_s2_cost"]            = first_s2.get("cost")
        row["first_mono_count"]         = first_s2.get("mono_count")
        row["first_concentrated_count"] = first_s2.get("concentrated_count")

        if first_trip_loads:
            fr1_details = []
            try:
                fr1, fr1_details = compute_r1(
                    first_trip_loads, first_s1_loads, instance_data,
                )
                row["first_r_1"] = fr1
            except Exception as e:
                print(f"  First-solution R_1 exception: {e}")

            try:
                if fr1_details:
                    fk1, _ = compute_kit_ratio(fr1_details)
                    row["first_k_1"] = fk1
            except Exception as e:
                print(f"  First-solution K_1 exception: {e}")

            try:
                for strat in R_ALPHA_STRATEGIES:
                    for md in R_ALPHA_MODES:
                        for alph in ALPHA_VALUES:
                            col = f"first_{_r_alpha_col(strat, md, alph)}"
                            val, _ = compute_r_alpha(
                                first_trip_loads, first_s1_loads,
                                instance_data,
                                alpha=alph, mode=md, strategy=strat,
                            )
                            row[col] = val
            except Exception as e:
                print(f"  First-solution R_alpha exception: {e}")

            try:
                fcosts = compute_dispatch_costs(
                    {"loads": first_s1_loads,
                     "route_freqs": first_s1.get("route_freqs", stage1["route_freqs"])},
                    {"trip_loads": first_trip_loads,
                     "used_trips": first_s2.get("used_trips", set())},
                    instance_data,
                )
                row["first_s1_dispatch_cost"] = fcosts["s1_dispatch_cost"]
                row["first_s2_dispatch_cost"] = fcosts["s2_dispatch_cost"]
            except Exception as e:
                print(f"  First-solution dispatch cost exception: {e}")

            print(f"  First solution: R_1={row.get('first_r_1')}  "
                  f"R_TR={row.get('first_r_tr')}  "
                  f"s1_time={row.get('first_s1_time')}  "
                  f"s2_time={row.get('first_s2_time')}")

        row["status"] = "OK"
        append_row(csv_path, row)
        rows_written += 1

    return rows_written


# ── CLI ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Full two-stage experiment: weight × Stage 2 config "
                    "on layered + industry instances")
    p.add_argument("--layered-dir", type=Path, default=LAYERED_DIR,
                   help="Directory with layered instance .lp files")
    p.add_argument("--industry-dir", type=Path, default=INDUSTRY_DIR,
                   help="Directory with industry instance .lp files")
    p.add_argument("--skip-layered", action="store_true",
                   help="Skip layered instances")
    p.add_argument("--skip-industry", action="store_true",
                   help="Skip industry instances")
    p.add_argument("--instance-filter", type=str, default=None,
                   help="Only instances whose name contains this string")
    p.add_argument("--weights", type=int, nargs="+",
                   default=DEFAULT_WEIGHTS)
    p.add_argument("--exposure-n", type=int, default=3,
                   help="Exposure threshold (2=50%%, 3=33%%, 4=25%%)")
    p.add_argument("--s2-configs", nargs="+", default=DEFAULT_S2,
                   choices=list(S2_CONFIGS.keys()),
                   help="Stage 2 configs to sweep")
    p.add_argument("--time-small",    type=int, default=30)
    p.add_argument("--time-medium",   type=int, default=60)
    p.add_argument("--time-large",    type=int, default=120)
    p.add_argument("--time-xlarge",   type=int, default=300)
    p.add_argument("--time-industrylite", type=int, default=600)
    p.add_argument("--time-paper",    type=int, default=30)
    p.add_argument("--time-industry", type=int, default=20000)
    p.add_argument("--max-freq",      type=int, default=20)
    p.add_argument("--cap-size-divide", type=int, default=1,
                   help="Divide capacities/part sizes by this factor "
                        "(use 10 for industry instances)")
    p.add_argument("-t", "--threads", type=int, default=1,
                   help="Solver threads. NOTE: clingcon CSP propagator does "
                        "NOT support -t > 1; keep at 1 (default)")
    p.add_argument("--configuration", type=str, default="many",
                   choices=["many", "frumpy", "crafty", "trendy", "jumpy",
                            "handy", "auto"],
                   help="Clingo solver configuration (default: 'many')")
    p.add_argument("--light-industry", action="store_true",
                   help="Use light encodings (no resilience optimisation) "
                        "for industry instances instead of heavy encodings")
    p.add_argument("--output", "-o", type=Path, default=None,
                   help="Output CSV path (auto-generated if omitted)")
    p.add_argument("--resume", action="store_true",
                   help="Skip already-completed (instance, weight, config)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ── Discover instances ────────────────────────────────────────────
    instances: list[Path] = []
    if not args.skip_layered:
        instances.extend(discover_layered_instances(args.layered_dir))
    if not args.skip_industry:
        instances.extend(discover_industry_instances(args.industry_dir))

    if args.instance_filter:
        instances = [f for f in instances if args.instance_filter in f.stem]

    if not instances:
        sys.exit("No instance files found — check directories and filters.")

    # ── Output path ───────────────────────────────────────────────────
    if args.output is None:
        w = sorted(args.weights)
        wstr = f"w{w[0]}_{w[-1]}" if len(w) > 1 else f"w{w[0]}"
        args.output = (SCRIPT_DIR / "results" /
                       f"final_experiment__{wstr}__n{args.exposure_n}"
                       f"__s2_{'_'.join(args.s2_configs)}.csv")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    # ── Time limits by size ───────────────────────────────────────────
    time_map = {
        "small":         args.time_small,
        "medium":        args.time_medium,
        "large":         args.time_large,
        "xlarge":        args.time_xlarge,
        "industrylite":  args.time_industrylite,
        "paper":         args.time_paper,
        "industry":      args.time_industry,
        "custom":        args.time_small,
        "default":       120,
    }

    weights    = sorted(args.weights)
    s2_configs = args.s2_configs
    total_runs = len(instances) * len(weights) * len(s2_configs)

    completed = load_completed(args.output) if args.resume else set()
    if completed:
        print(f"Resuming: {len(completed)} rows already completed")

    exposure_n = args.exposure_n

    print(f"{'═' * 70}")
    print(f"  FINAL TWO-STAGE EXPERIMENT")
    print(f"{'═' * 70}")
    print(f"  Stage 1 encoding: {STAGE1_ENCODING.name}")
    print(f"  Stage 2 encoding: {STAGE2_ENCODING.name}")
    print(f"  Instances:        {len(instances)}")
    print(f"  Weights:          {weights}")
    print(f"  Exposure N:       {exposure_n}")
    print(f"  S2 configs:       {s2_configs}")
    print(f"  Total runs:       {total_runs}")
    print(f"  Output:           {args.output}")
    print(f"{'═' * 70}")

    t_start    = time.perf_counter()
    rows_total = 0

    for inst_path in instances:
        inst_name = inst_path.stem
        meta = classify_instance(inst_name)
        tl = get_time_limit(meta["instance_size"], time_map)

        print(f"\n{'═' * 70}")
        print(f"  Instance: {inst_name}  "
              f"(type={meta['instance_type']}, "
              f"size={meta['instance_size']}, "
              f"seed={meta['seed']}, "
              f"time_limit={tl}s", )
        print(f"{'═' * 70}")

        instance_data = parse_instance(str(inst_path))
        print(f"  Parsed: {len(instance_data['parts'])} parts, "
              f"{len(instance_data['routes'])} routes")

        is_industry = meta["instance_type"] == "industry"
        use_light = is_industry and args.light_industry
        s1 = STAGE1_LIGHT if use_light else STAGE1_ENCODING
        s2 = STAGE2_LIGHT if use_light else STAGE2_ENCODING

        for w in weights:
            n = run_weight_group(
                inst_path, instance_data, inst_name, meta,
                weight=w,
                exposure_n=exposure_n,
                s2_configs=s2_configs,
                time_limit=tl,
                max_freq=args.max_freq,
                csv_path=args.output,
                completed=completed,
                s1_encoding=s1,
                s2_encoding=s2,
                threads=args.threads,
                configuration=args.configuration,
                cap_size_divide=args.cap_size_divide,
            )
            rows_total += n

    elapsed = time.perf_counter() - t_start
    print(f"\n{'═' * 70}")
    print(f"  COMPLETE: {rows_total} rows in {elapsed:.1f}s")
    print(f"  Results → {args.output}")
    print(f"{'═' * 70}")


if __name__ == "__main__":
    main()
