#!/usr/bin/env python3
"""
quality_benchmark.py — Compare Stage 2 packing configurations
==============================================================

Runs Stage 1 ONCE to get the aggregate network flow, then runs Stage 2
with multiple configurations (different objectives / constraints) and
compares packing quality metrics side-by-side.

Usage
-----
    # From "ASP Pure Encodings":
    uv run two_stage/quality_benchmark.py \\
        --instance data/paper_instances.lp

    uv run two_stage/quality_benchmark.py \\
        --instance data/benchmark_quality/medium_instance.lp \\
        --round-timeout 20 --time-limit 180
"""

from __future__ import annotations

import argparse
import sys
import time
import threading
from collections import defaultdict
from pathlib import Path
from statistics import mean

import clingo
import clingo.ast
from clingcon import ClingconTheory

# Re-use Stage 1 solver from the main runner
from run_two_stage import (
    load_instance_data,
    solve_stage1,
    check_feasibility,
    _extract_stage2,
)


HERE       = Path(__file__).parent
STAGE2_BASE = HERE / "stage2_base.lp"


# ─────────────────────────────────────────────────────────────────────────
# Stage 2 configurations
# ─────────────────────────────────────────────────────────────────────────
# Each configuration is a dict with:
#   description: human-readable label
#   extra_rules: ASP/clingcon rules injected on top of stage2_base.lp

CONFIGURATIONS: dict[str, dict] = {
    "baseline": {
        "description": "Feasibility only (no objectives)",
        "extra_rules": "",
    },

    "diversity_soft": {
        "description": "Soft: penalise mono-SKU + empty trips",
        "extra_rules": "\n".join([
            ":~ tripPartCount(F,T,TR,K,1), routePartTypes(F,T,TR,N), N >= 2. [1@2, F,T,TR,K]",
            ":~ trip(F,T,TR,K), tripPartCount(F,T,TR,K,0). [1@1, F,T,TR,K]",
        ]),
    },

    "holding_cost": {
        "description": "Minimise tied-up capital per trip",
        "extra_rules": "\n".join([
            # per-trip value (clingcon variable)
            "&sum { V * tripLoad(F,T,TR,P,K) : totalLoad(F,T,TR,P,_), partVal(P,V) } = tripValue(F,T,TR,K) :- trip(F,T,TR,K).",
            "&show { tripValue/4 }.",
            # minimise transit_time × trip_value
            "&minimize { TT * tripValue(F,T,TR,K) : trip(F,T,TR,K), transitTime(F,T,TR,TT) }.",
        ]),
    },

    "diversity_holding": {
        "description": "Soft diversity + holding cost minimisation",
        "extra_rules": "\n".join([
            # diversity weak constraints
            ":~ tripPartCount(F,T,TR,K,1), routePartTypes(F,T,TR,N), N >= 2. [1@2, F,T,TR,K]",
            ":~ trip(F,T,TR,K), tripPartCount(F,T,TR,K,0). [1@1, F,T,TR,K]",
            # holding cost
            "&sum { V * tripLoad(F,T,TR,P,K) : totalLoad(F,T,TR,P,_), partVal(P,V) } = tripValue(F,T,TR,K) :- trip(F,T,TR,K).",
            "&show { tripValue/4 }.",
            "&minimize { TT * tripValue(F,T,TR,K) : trip(F,T,TR,K), transitTime(F,T,TR,TT) }.",
        ]),
    },

    "diversity_hard": {
        "description": "Hard: every trip MUST carry >= 2 types",
        "extra_rules": "\n".join([
            ":- tripPartCount(F,T,TR,K,1), routePartTypes(F,T,TR,N), N >= 2.",
            ":~ trip(F,T,TR,K), tripPartCount(F,T,TR,K,0). [1@1, F,T,TR,K]",
        ]),
    },
}


# ─────────────────────────────────────────────────────────────────────────
# Build Stage 2 facts (extended with partVal + transitTime)
# ─────────────────────────────────────────────────────────────────────────

def build_stage2_facts_extended(
    stage1: dict,
    instance_data: dict,
    instance_path: str,
) -> str:
    """Build Stage 2 input facts including partVal and transitTime."""
    lines: list[str] = []

    # totalLoad
    for (f, t, tr, p), n in sorted(stage1["loads"].items()):
        lines.append(f"totalLoad({f},{t},{tr},{p},{n}).")

    # activeRoute (with raw per-trip capacity)
    for rf in stage1["route_freqs"]:
        cap = instance_data["transport_cap"].get(rf["tr"], 0)
        lines.append(
            f"activeRoute({rf['from']},{rf['to']},{rf['tr']},"
            f"{rf['freq']},{cap})."
        )

    # partSize (raw)
    for p, s in sorted(instance_data["part_size"].items()):
        lines.append(f"partSize({p},{s}).")

    # partVal
    for p, v in sorted(instance_data["part_val"].items()):
        lines.append(f"partVal({p},{v}).")

    # transitTime: parse routes from instance for distance, use transport speed
    # Scale by 100 for integer precision (same approach as clingcon_flow.lp)
    ctl = clingo.Control()
    ctl.load(instance_path)
    ctl.ground([("base", [])])

    routes: dict[tuple, int] = {}       # (f,t,tr) -> distance
    speeds: dict[str, int] = {}         # tr -> speed

    for atom in ctl.symbolic_atoms:
        sym = atom.symbol
        if sym.name == "route" and len(sym.arguments) == 5:
            f, t, tr = str(sym.arguments[0]), str(sym.arguments[1]), str(sym.arguments[2])
            dist = sym.arguments[3].number
            routes[(f, t, tr)] = dist
        elif sym.name == "transportSpeed" and len(sym.arguments) == 2:
            speeds[str(sym.arguments[0])] = sym.arguments[1].number

    # Only emit transitTime for active routes
    active_keys = set()
    for rf in stage1["route_freqs"]:
        active_keys.add((rf["from"], rf["to"], rf["tr"]))

    for (f, t, tr) in active_keys:
        dist = routes.get((f, t, tr), 0)
        speed = speeds.get(tr, 1)
        if speed > 0:
            tt = dist * 100 // speed  # integer-scaled transit time
            lines.append(f"transitTime({f},{t},{tr},{tt}).")

    # transportSpeed (for Python-side holding cost computation)
    for tr, sp in sorted(speeds.items()):
        lines.append(f"transportSpeed({tr},{sp}).")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# Solve Stage 2 with a given configuration
# ─────────────────────────────────────────────────────────────────────────

def solve_stage2_config(
    facts_str:   str,
    extra_rules: str,
    timeout:     int,
) -> dict | None:
    """Solve Stage 2 with base encoding + injected rules."""

    theory = ClingconTheory()
    ctl = clingo.Control(["--configuration=jumpy"])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_string(facts_str, on_rule)
        clingo.ast.parse_files([str(STAGE2_BASE)], on_rule)
        if extra_rules:
            clingo.ast.parse_string(extra_rules, on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    ground_time = time.perf_counter() - t0
    theory.prepare(ctl)

    best: dict | None = None
    optimum = False

    timer = threading.Timer(timeout, ctl.interrupt)
    timer.start()

    try:
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                theory.on_model(model)
                best = _extract_stage2(model, theory)
                if model.optimality_proven:
                    optimum = True
                    break
    except RuntimeError:
        pass
    finally:
        timer.cancel()

    total_time = time.perf_counter() - t0

    if best is not None:
        best["ground_time"] = round(ground_time, 3)
        best["total_time"]  = round(total_time, 3)
        best["optimum"]     = optimum

    return best


# ─────────────────────────────────────────────────────────────────────────
# Compute quality metrics (including holding cost, computed in Python)
# ─────────────────────────────────────────────────────────────────────────

def compute_metrics(
    stage2:        dict,
    instance_data: dict,
    route_freqs:   list,
    instance_path: str,
) -> dict:
    """Compute packing quality metrics + holding cost from any Stage 2 solution."""

    # Per-trip capacity lookup
    trip_cap: dict[tuple, int] = {}
    for rf in route_freqs:
        cap = instance_data["transport_cap"].get(rf["tr"], 0)
        for k in range(1, rf["freq"] + 1):
            trip_cap[(rf["from"], rf["to"], rf["tr"], k)] = cap

    # Parse route distances from instance
    ctl = clingo.Control()
    ctl.load(instance_path)
    ctl.ground([("base", [])])

    route_dist: dict[tuple, int] = {}
    transport_speed: dict[str, int] = {}
    for atom in ctl.symbolic_atoms:
        sym = atom.symbol
        if sym.name == "route" and len(sym.arguments) == 5:
            f, t, tr = str(sym.arguments[0]), str(sym.arguments[1]), str(sym.arguments[2])
            route_dist[(f, t, tr)] = sym.arguments[3].number
        elif sym.name == "transportSpeed" and len(sym.arguments) == 2:
            transport_speed[str(sym.arguments[0])] = sym.arguments[1].number

    # ── Parts per trip ───────────────────────────────────────────────
    counts = list(stage2["trip_part_counts"].values())
    non_empty = [c for c in counts if c > 0]
    mono_trips = sum(1 for c in counts if c == 1)

    # ── Fill rate per trip ───────────────────────────────────────────
    trip_volumes: dict[tuple, int] = defaultdict(int)
    for (f, t, tr, p, k), n in stage2["trip_loads"].items():
        size = instance_data["part_size"].get(p, 0)
        trip_volumes[(f, t, tr, k)] += size * n

    fill_rates: list[float] = []
    for trip_key, vol in trip_volumes.items():
        cap = trip_cap.get(trip_key, 0)
        if cap > 0:
            fill_rates.append(vol / cap)

    # ── Max single-part share ────────────────────────────────────────
    trip_part_vols: dict[tuple, dict[str, int]] = defaultdict(dict)
    for (f, t, tr, p, k), n in stage2["trip_loads"].items():
        size = instance_data["part_size"].get(p, 0)
        trip_part_vols[(f, t, tr, k)][p] = size * n

    max_shares: list[float] = []
    for trip_key, pvols in trip_part_vols.items():
        total = sum(pvols.values())
        if total > 0 and len(pvols) > 1:
            max_shares.append(max(pvols.values()) / total)

    # ── Holding cost (Python-computed, works for all configurations) ─
    total_holding = 0.0
    for (f, t, tr, p, k), n in stage2["trip_loads"].items():
        value = instance_data["part_val"].get(p, 0)
        dist  = route_dist.get((f, t, tr), 0)
        speed = transport_speed.get(tr, 1)
        transit = dist / speed if speed > 0 else 0
        total_holding += n * value * transit

    return {
        "total_trips":        len(counts),
        "non_empty_trips":    len(non_empty),
        "empty_trips":        len(counts) - len(non_empty),
        "mono_sku_trips":     mono_trips,
        "mixed_trips":        sum(1 for c in non_empty if c >= 2),
        "avg_parts_per_trip": round(mean(non_empty), 2) if non_empty else 0,
        "avg_fill_rate":      round(mean(fill_rates), 3) if fill_rates else 0,
        "min_fill_rate":      round(min(fill_rates), 3) if fill_rates else 0,
        "avg_max_share":      round(mean(max_shares), 3) if max_shares else 0,
        "holding_cost":       round(total_holding, 1),
    }


# ─────────────────────────────────────────────────────────────────────────
# Comparison table
# ─────────────────────────────────────────────────────────────────────────

def print_comparison(results: dict[str, dict]) -> None:
    """Print side-by-side comparison of all configurations."""

    configs = list(results.keys())
    metrics_keys = [
        ("total_trips",        "Total trips"),
        ("non_empty_trips",    "Non-empty trips"),
        ("empty_trips",        "Empty trips"),
        ("mono_sku_trips",     "Mono-SKU trips"),
        ("mixed_trips",        "Mixed trips (≥2 types)"),
        ("avg_parts_per_trip", "Avg parts/trip"),
        ("avg_fill_rate",      "Avg fill rate"),
        ("min_fill_rate",      "Min fill rate"),
        ("avg_max_share",      "Avg max-part share"),
        ("holding_cost",       "Holding cost"),
        ("solve_time",         "Solve time (s)"),
        ("optimum",            "Optimum proven"),
    ]

    # Column widths
    label_w = max(len(label) for _, label in metrics_keys) + 2
    col_w = max(max(len(c) for c in configs), 12) + 2

    # Header
    print()
    print(" " * label_w + "".join(f"{c:>{col_w}}" for c in configs))
    print("─" * (label_w + col_w * len(configs)))

    for key, label in metrics_keys:
        row = f"{label:<{label_w}}"
        for cfg in configs:
            r = results[cfg]
            if r is None:
                val = "UNSAT"
            elif key == "solve_time":
                val = f"{r['total_time']:.2f}"
            elif key == "optimum":
                val = "Yes" if r.get("optimum") else "No"
            else:
                v = r["metrics"].get(key, "—")
                val = str(v)
            row += f"{val:>{col_w}}"
        print(row)

    print()


# ─────────────────────────────────────────────────────────────────────────
# CLI + Main
# ─────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compare Stage 2 packing configurations on a fixed Stage 1 solution."
    )
    p.add_argument("--instance", "-i", required=True)
    p.add_argument("--cap-divide", type=int, default=1)
    p.add_argument("--max-freq", type=int, default=30)
    p.add_argument("--time-limit", type=int, default=300,
                   help="Overall time limit per stage (default: 300)")
    p.add_argument("--round-timeout", type=int, default=30,
                   help="Per-round timeout for multi-shot (default: 30)")
    p.add_argument("--configs", nargs="+",
                   choices=list(CONFIGURATIONS.keys()),
                   default=list(CONFIGURATIONS.keys()),
                   help="Which configurations to run (default: all)")
    return p


def main() -> int:
    args = build_parser().parse_args()

    instance_path = Path(args.instance)
    if not instance_path.exists():
        print(f"Error: {instance_path} not found", file=sys.stderr)
        return 1

    instance_data = load_instance_data(str(instance_path))
    print(f"Instance: {instance_path}")
    print(f"  Locations: {len(instance_data['locations'])}  "
          f"Parts: {len(instance_data['parts'])}")
    print()

    # ── Stage 1 (run once) ───────────────────────────────────────────
    print("═" * 70)
    print("  STAGE 1: Network Flow (shared across all configurations)")
    print("═" * 70)

    stage1 = solve_stage1(
        str(instance_path), args.cap_divide, args.max_freq,
        args.time_limit, round_timeout=args.round_timeout,
    )
    if stage1 is None:
        print("  UNSATISFIABLE")
        return 1

    print(f"  Active routes:  {len(stage1['route_freqs'])}")
    print(f"  Non-zero loads: {len(stage1['loads'])}")
    print(f"  Cost:           {stage1.get('cost', '?')}")
    print(f"  Optimum proven: {stage1['optimum']}")
    print()

    warnings = check_feasibility(stage1, instance_data)
    for w in warnings:
        print(w)

    # ── Build extended Stage 2 facts ─────────────────────────────────
    facts = build_stage2_facts_extended(stage1, instance_data, str(instance_path))

    # ── Run each Stage 2 configuration ───────────────────────────────
    print("═" * 70)
    print("  STAGE 2: Running configurations")
    print("═" * 70)

    results: dict[str, dict | None] = {}

    for cfg_name in args.configs:
        cfg = CONFIGURATIONS[cfg_name]
        print(f"\n  [{cfg_name}] {cfg['description']}")
        print(f"  {'─' * 60}")

        stage2 = solve_stage2_config(
            facts, cfg["extra_rules"], args.round_timeout,
        )

        if stage2 is None:
            print(f"    UNSATISFIABLE or no model found")
            results[cfg_name] = None
            continue

        print(f"    Solve time: {stage2['total_time']}s  "
              f"Optimum: {stage2['optimum']}")

        metrics = compute_metrics(
            stage2, instance_data, stage1["route_freqs"], str(instance_path),
        )
        results[cfg_name] = {
            "metrics":    metrics,
            "total_time": stage2["total_time"],
            "optimum":    stage2["optimum"],
        }

        print(f"    Mono-SKU: {metrics['mono_sku_trips']}  "
              f"Mixed: {metrics['mixed_trips']}  "
              f"Fill: {metrics['avg_fill_rate']}  "
              f"Holding: {metrics['holding_cost']}")

    # ── Comparison table ─────────────────────────────────────────────
    print()
    print("═" * 70)
    print("  COMPARISON")
    print("═" * 70)
    print_comparison(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
