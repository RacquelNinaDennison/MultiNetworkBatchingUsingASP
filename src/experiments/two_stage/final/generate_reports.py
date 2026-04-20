#!/usr/bin/env python3
"""Generate summary tables, Pareto front, and plots from two-stage experiment sweeps."""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"
PLOTS_DIR = RESULTS_DIR / "plots" / "report"

SWEEP_FILES: dict[str, str] = {
    "paper":         "sweep_paper_full_alpha.csv",
    "small":         "sweep_small_ralpha_v2.csv",
    "medium":        "sweep_medium_ralpha_v2.csv",
    "large":         "sweep_large.csv",
    "xlarge":        "sweep_xlarge_ralpha_v2.csv",
    "industrylite":  "sweep_industrylite_ralpha_v2.csv",
    "industry":      "sweep_industry_heavy.csv",
}

# Preferred weight per size for "baseline vs best" comparisons.
# Set to the highest weight that still shows improvement for that size.
BEST_WEIGHT: dict[str, int] = {
    "paper": 1000,
    "small": 750,
    "medium": 750,
    "large": 300,
    "xlarge": 1000,
    "industrylite": 2000,
    "industry": 0,
}

SIZE_ORDER = list(SWEEP_FILES.keys())

CONFIG_ORDER = ["off_off", "hetero", "conc", "both"]


def load_all(sizes: list[str] | None = None) -> pd.DataFrame:
    """Load sweep CSVs into one DataFrame, tagged by instance size.

    Parameters
    ----------
    sizes : list of size labels to load, or None for all.
    """
    targets = {s: SWEEP_FILES[s] for s in (sizes or SWEEP_FILES)}
    frames = []
    for size_label, fname in targets.items():
        path = RESULTS_DIR / fname
        if not path.exists():
            print(f"  [WARN] Missing {path.name} for '{size_label}' — skipped")
            continue
        df = pd.read_csv(path)
        df = df[df["status"] == "OK"].copy()
        if df.empty:
            print(f"  [WARN] No OK rows in {path.name} — skipped")
            continue
        # Coerce all numeric columns
        numeric_cols = [
            "r_tr", "r_1", "k_1",
            "nominal_cost", "s1_dispatch_cost", "s2_dispatch_cost",
            "cost_saving", "mono_count", "concentrated_count",
            "exposure_count", "weight", "seed",
            "s1_time", "s2_time",
            "first_r_tr", "first_s1_cost", "first_s2_cost",
            "first_s1_dispatch_cost", "first_s2_dispatch_cost",
            "first_s1_time", "first_s2_time",
            "first_mono_count", "first_concentrated_count",
        ]
        # Also coerce all r_alpha columns
        for col in df.columns:
            if col.startswith("r_") and any(
                col.startswith(f"r_{s}") for s in ["heaviest", "first", "last"]
            ):
                numeric_cols.append(col)
            if col.startswith("first_r_"):
                numeric_cols.append(col)
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["size_label"] = size_label
        frames.append(df)
    if not frames:
        raise SystemExit("No data loaded — check SWEEP_FILES paths.")
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 1. Averaged summary table (across seeds) per size x weight x config
# ---------------------------------------------------------------------------
def write_averaged_summary(df: pd.DataFrame, out: Path) -> None:
    group_cols = ["size_label", "weight", "s2_config"]
    agg = (
        df.groupby(group_cols, sort=False)
        .agg(
            n_seeds=("seed", "nunique"),
            r_tr_mean=("r_tr", "mean"),
            r_tr_std=("r_tr", "std"),
            r_1_mean=("r_1", "mean"),
            r_1_std=("r_1", "std"),
            k_1_mean=("k_1", "mean"),
            s2_cost_mean=("s2_dispatch_cost", "mean"),
            s1_cost_mean=("s1_dispatch_cost", "mean"),
            cost_saving_mean=("cost_saving", "mean"),
            mono_mean=("mono_count", "mean"),
            conc_mean=("concentrated_count", "mean"),
            exposure_mean=("exposure_count", "mean"),
            s1_time_mean=("s1_time", "mean"),
            s2_time_mean=("s2_time", "mean"),
            s1_optimal_pct=("s1_optimal", lambda x: (x == True).sum() / len(x) * 100),  # noqa: E712
            s2_optimal_pct=("s2_optimal", lambda x: (x == True).sum() / len(x) * 100),  # noqa: E712
        )
        .reset_index()
    )
    size_order = {s: i for i, s in enumerate(SWEEP_FILES.keys())}
    agg["_sort"] = agg["size_label"].map(size_order)
    cfg_order = {c: i for i, c in enumerate(CONFIG_ORDER)}
    agg["_cfg_sort"] = agg["s2_config"].map(cfg_order).fillna(99)
    agg = agg.sort_values(["_sort", "weight", "_cfg_sort"]).drop(columns=["_sort", "_cfg_sort"])

    for col in ["r_tr_mean", "r_tr_std", "r_1_mean", "r_1_std", "k_1_mean"]:
        agg[col] = agg[col].round(4)
    for col in ["s2_cost_mean", "s1_cost_mean", "cost_saving_mean",
                 "mono_mean", "conc_mean", "exposure_mean",
                 "s1_time_mean", "s2_time_mean"]:
        agg[col] = agg[col].round(1)
    for col in ["s1_optimal_pct", "s2_optimal_pct"]:
        agg[col] = agg[col].round(0)

    agg.to_csv(out, index=False)
    print(f"  Wrote averaged summary -> {out}")


# ---------------------------------------------------------------------------
# 2. Per-seed detail table
# ---------------------------------------------------------------------------
def write_per_seed_detail(df: pd.DataFrame, out: Path) -> None:
    cols = [
        "size_label", "instance_name", "seed", "weight", "s2_config",
        "r_tr", "worst_arc", "r_1", "worst_trip", "k_1",
        "kit_bottleneck_part", "mono_count", "concentrated_count",
        "exposure_count", "nominal_cost", "s1_dispatch_cost",
        "s2_dispatch_cost", "cost_saving",
        "s1_optimal", "s1_time", "s2_optimal", "s2_time",
    ]
    present = [c for c in cols if c in df.columns]
    detail = df[present].copy()

    size_order = {s: i for i, s in enumerate(SWEEP_FILES.keys())}
    detail["_sort"] = detail["size_label"].map(size_order)
    cfg_order = {c: i for i, c in enumerate(CONFIG_ORDER)}
    detail["_cfg_sort"] = detail["s2_config"].map(cfg_order).fillna(99)
    detail = detail.sort_values(["_sort", "seed", "weight", "_cfg_sort"]).drop(
        columns=["_sort", "_cfg_sort"]
    )
    detail.to_csv(out, index=False)
    print(f"  Wrote per-seed detail -> {out}")


# ---------------------------------------------------------------------------
# 3. R_1 performance table: config x weight (averaged across seeds)
# ---------------------------------------------------------------------------
def write_r1_by_config_weight(df: pd.DataFrame, out: Path) -> None:
    rows = []
    for size in SWEEP_FILES:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        for w in sorted(sub["weight"].unique()):
            entry = {"size": size, "weight": int(w)}
            for cfg in CONFIG_ORDER:
                vals = sub[(sub["weight"] == w) & (sub["s2_config"] == cfg)]["r_1"]
                if len(vals):
                    entry[f"R1_{cfg}"] = round(vals.mean(), 4)
                    entry[f"R1_{cfg}_std"] = round(vals.std(), 4) if len(vals) > 1 else 0.0
            rows.append(entry)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  Wrote R_1 by config x weight -> {out}")


# ---------------------------------------------------------------------------
# 4. Pareto front computation
# ---------------------------------------------------------------------------
def compute_pareto_2d(points: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """2D Pareto: minimise cost, maximise resilience. Returns non-dominated set."""
    front = []
    for i, (c_i, r_i, lab_i) in enumerate(points):
        dominated = False
        for j, (c_j, r_j, _) in enumerate(points):
            if i == j:
                continue
            if c_j <= c_i and r_j >= r_i and (c_j < c_i or r_j > r_i):
                dominated = True
                break
        if not dominated:
            front.append((c_i, r_i, lab_i))
    return sorted(front, key=lambda x: x[0])


def write_pareto_tables(df: pd.DataFrame, out_dir: Path) -> None:
    """Write Pareto front tables for small (averaged) and small seed-3 (showcase)."""

    # --- Averaged Pareto across all seeds (small) ---
    small = df[df["size_label"] == "small"]
    if small.empty:
        return

    rows_avg = []
    for (w, cfg), grp in small.groupby(["weight", "s2_config"]):
        rows_avg.append({
            "weight": int(w), "config": cfg,
            "s2_cost": round(grp["s2_dispatch_cost"].mean(), 1),
            "r_tr": round(grp["r_tr"].mean(), 4),
            "r_1": round(grp["r_1"].mean(), 4),
        })

    pts = [(r["s2_cost"], r["r_tr"], f"w={r['weight']},{r['config']}") for r in rows_avg]
    front = compute_pareto_2d(pts)
    front_labels = {f[2] for f in front}

    pareto_df = pd.DataFrame(rows_avg)
    pareto_df["pareto_optimal"] = pareto_df.apply(
        lambda r: f"w={int(r['weight'])},{r['config']}" in front_labels, axis=1
    )
    pareto_df = pareto_df.sort_values(["weight", "config"])
    out_avg = out_dir / "pareto_small_averaged.csv"
    pareto_df.to_csv(out_avg, index=False)
    print(f"  Wrote Pareto (small averaged) -> {out_avg}")

    # --- Per-seed Pareto for seed 3 (best R_TR spread) ---
    seed3 = small[small["seed"] == 3]
    if seed3.empty:
        return

    rows_s3 = []
    for _, r in seed3.iterrows():
        rows_s3.append({
            "weight": int(r["weight"]), "config": r["s2_config"],
            "s2_cost": int(r["s2_dispatch_cost"]),
            "r_tr": round(r["r_tr"], 4),
            "r_1": round(r["r_1"], 4),
        })

    pts3 = [(r["s2_cost"], r["r_tr"], f"w={r['weight']},{r['config']}") for r in rows_s3]
    front3 = compute_pareto_2d(pts3)
    front3_labels = {f[2] for f in front3}

    s3_df = pd.DataFrame(rows_s3)
    s3_df["pareto_optimal"] = s3_df.apply(
        lambda r: f"w={int(r['weight'])},{r['config']}" in front3_labels, axis=1
    )
    s3_df = s3_df.sort_values(["weight", "config"])
    out_s3 = out_dir / "pareto_small_seed3.csv"
    s3_df.to_csv(out_s3, index=False)
    print(f"  Wrote Pareto (small seed3) -> {out_s3}")


# ---------------------------------------------------------------------------
# 5. Scalability & optimality gap table
# ---------------------------------------------------------------------------
def write_scalability_table(df: pd.DataFrame, out: Path) -> None:
    rows = []
    size_meta = {
        "paper":         {"layers": "3", "nodes": "5",  "parts": "2", "transports": "2"},
        "small":         {"layers": "3", "nodes": "5",  "parts": "3", "transports": "2"},
        "medium":        {"layers": "3", "nodes": "7",  "parts": "4", "transports": "2"},
        "large":         {"layers": "3", "nodes": "9",  "parts": "5", "transports": "2"},
        "xlarge":        {"layers": "3", "nodes": "15", "parts": "6", "transports": "3"},
        "industrylite":  {"layers": "4", "nodes": "20", "parts": "10", "transports": "4"},
        "industry":      {"layers": "~5", "nodes": "~60", "parts": "~50", "transports": "15"},
    }

    for size in SWEEP_FILES:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        meta = size_meta.get(size, {})
        n_rows = len(sub)
        n_seeds = sub["seed"].nunique()
        s1_times = sub["s1_time"]
        s2_times = sub["s2_time"]
        s1_opt_rate = (sub["s1_optimal"] == True).sum() / len(sub) * 100 if len(sub) else 0  # noqa: E712
        s2_opt_rate = (sub["s2_optimal"] == True).sum() / len(sub) * 100 if len(sub) else 0  # noqa: E712
        rtr_vals = sub["r_tr"].dropna()
        r1_vals = sub["r_1"].dropna()

        rows.append({
            "size": size,
            "layers": meta.get("layers", "?"),
            "nodes_per_layer": meta.get("nodes", "?"),
            "parts": meta.get("parts", "?"),
            "transports": meta.get("transports", "?"),
            "n_seeds": n_seeds,
            "n_experiments": n_rows,
            "s1_time_mean": round(s1_times.mean(), 1),
            "s1_time_max": round(s1_times.max(), 1),
            "s2_time_mean": round(s2_times.mean(), 1),
            "s2_time_max": round(s2_times.max(), 1),
            "s1_optimal_pct": round(s1_opt_rate, 0),
            "s2_optimal_pct": round(s2_opt_rate, 0),
            "r_tr_range": f"{rtr_vals.min():.3f}-{rtr_vals.max():.3f}" if len(rtr_vals) else "N/A",
            "r_1_range": f"{r1_vals.min():.3f}-{r1_vals.max():.3f}" if len(r1_vals) else "N/A",
            "timeout_evidence": _timeout_note(size, s1_opt_rate, s2_opt_rate, s1_times),
        })

    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  Wrote scalability table -> {out}")


def _timeout_note(size: str, s1_opt: float, s2_opt: float, s1_times: pd.Series) -> str:
    """Generate a brief note on why bigger instances need more time."""
    if s1_opt >= 80 and s2_opt >= 80:
        return "Solver converges within budget"
    near_limit = (s1_times > s1_times.max() * 0.95).sum() / len(s1_times) * 100
    parts = []
    if s1_opt < 50:
        parts.append(f"S1 optimal only {s1_opt:.0f}%")
    if s2_opt < 50:
        parts.append(f"S2 optimal only {s2_opt:.0f}%")
    if near_limit > 50:
        parts.append(f"{near_limit:.0f}% runs hit time limit")
    if size in ("xlarge", "industrylite", "industry"):
        parts.append("grounding + search space grows combinatorially with nodes x parts x transports")
    return "; ".join(parts) if parts else "Partial convergence"


# ---------------------------------------------------------------------------
# 6. Plots
# ---------------------------------------------------------------------------
def plot_rtr_vs_weight(df: pd.DataFrame, out_dir: Path) -> None:
    """Line plot: R_TR vs weight for small & medium, averaged over instances."""
    fig, ax = plt.subplots(figsize=(7, 5))

    exclude_weights = {1500}
    colors = {"small": "#1f77b4", "medium": "#ff7f0e"}
    for size in ["small", "medium"]:
        sub = df[(df["size_label"] == size) & (~df["weight"].isin(exclude_weights))]
        if sub.empty:
            continue
        grp = sub.groupby("weight")["r_tr"].mean().sort_index()
        ax.plot(grp.index, grp.values, marker="o", linewidth=2.5,
                markersize=8, label=f"{size.capitalize()}",
                color=colors[size])

    ax.set_xlabel("Stage 1 Weight", fontsize=12)
    ax.set_ylabel("$R_{TR}$", fontsize=12)
    ax.set_title("Effect of Weight on $R_{TR}$", fontsize=13)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    for ext in ("pdf", "png"):
        out = out_dir / f"rtr_vs_weight.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'rtr_vs_weight.[pdf|png]'}")


def plot_r1_by_config(df: pd.DataFrame, out_dir: Path) -> None:
    """Grouped bar chart: R_1 by config, faceted by weight=0 vs best weight."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)

    for ax, size in zip(axes, ["small", "medium"]):
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        best_w = sub.groupby("weight")["r_tr"].mean().idxmax()
        weight_labels = [0, best_w]

        x = np.arange(len(CONFIG_ORDER))
        width = 0.35
        for i, w in enumerate(weight_labels):
            means = []
            stds = []
            for cfg in CONFIG_ORDER:
                vals = sub[(sub["weight"] == w) & (sub["s2_config"] == cfg)]["r_1"]
                means.append(vals.mean() if len(vals) else 0)
                stds.append(vals.std() if len(vals) > 1 else 0)
            offset = (i - 0.5) * width
            bars = ax.bar(x + offset, means, width, yerr=stds,
                          label=f"w={int(w)}", capsize=3, alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels(CONFIG_ORDER, fontsize=10)
        ax.set_ylabel("R_1 (trip-level resilience)", fontsize=12)
        ax.set_title(f"{size.capitalize()} — R_1 by packing config", fontsize=13)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3, axis="y")
        ax.set_ylim(0.65, 0.95)

    fig.tight_layout()
    for ext in ("pdf", "png"):
        out = out_dir / f"r1_by_config.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'r1_by_config.[pdf|png]'}")


def plot_pareto_front(df: pd.DataFrame, out_dir: Path) -> None:
    """Network cost vs R_TR."""
    seed3 = df[(df["size_label"] == "small") & (df["seed"] == 3)]
    if seed3.empty:
        print("  [SKIP] No small seed 3 data for Pareto plot")
        return

    pts = []
    for _, r in seed3.iterrows():
        pts.append((r["s2_dispatch_cost"], r["r_tr"],
                     f"w={int(r['weight'])},{r['s2_config']}",
                     int(r["weight"]), r["s2_config"]))

    front = compute_pareto_2d([(p[0], p[1], p[2]) for p in pts])
    front_labels = {f[2] for f in front}

    fig, ax = plt.subplots(figsize=(9, 6))

    cmap = {"off_off": "#1f77b4", "hetero": "#2ca02c", "conc": "#ff7f0e", "both": "#d62728"}
    markers = {"off_off": "o", "hetero": "s", "conc": "D", "both": "^"}

    for cost, rtr, lab, w, cfg in pts:
        is_front = lab in front_labels
        ax.scatter(cost, rtr,
                   c=cmap.get(cfg, "gray"),
                   marker=markers.get(cfg, "o"),
                   s=120 if is_front else 60,
                   edgecolors="black" if is_front else "none",
                   linewidths=2 if is_front else 0,
                   zorder=5 if is_front else 3,
                   alpha=0.9 if is_front else 0.5)

    front_sorted = sorted(front, key=lambda x: x[0])
    if len(front_sorted) > 1:
        fx = [f[0] for f in front_sorted]
        fy = [f[1] for f in front_sorted]
        ax.plot(fx, fy, "k--", linewidth=1.5, alpha=0.6, label="Pareto front")

    for cfg in CONFIG_ORDER:
        ax.scatter([], [], c=cmap[cfg], marker=markers[cfg], s=80, label=cfg)
    ax.scatter([], [], c="gray", marker="o", s=120,
               edgecolors="black", linewidths=2, label="Pareto-optimal")

    ax.set_xlabel("S2 Dispatch Cost", fontsize=12)
    ax.set_ylabel("R_TR ", fontsize=12)
    ax.set_title("Pareto Front: Cost vs Resilience\n(small, seed 3 — widest R_TR spread)", fontsize=13)
    ax.legend(fontsize=10, loc="lower right")
    ax.grid(True, alpha=0.3)

    for ext in ("pdf", "png"):
        out = out_dir / f"pareto_front_seed3.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'pareto_front_seed3.[pdf|png]'}")


def plot_pareto_averaged(df: pd.DataFrame, out_dir: Path) -> None:
    """Side-by-side Pareto: R_TR vs S2 cost for small and medium (excl. w=1500)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    colors = {"small": "#1f77b4", "medium": "#ff7f0e"}
    exclude_weights = {1500}

    for ax, size, title in [(ax1, "small", "Small"), (ax2, "medium", "Medium")]:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue

        pts = []
        for w, grp in sub.groupby("weight"):
            if int(w) in exclude_weights:
                continue
            pts.append((
                grp["r_tr"].mean(),
                grp["s2_dispatch_cost"].mean(),
                int(w),
            ))
        pts.sort(key=lambda x: x[2])

        rtr_vals = [p[0] for p in pts]
        cost_vals = [p[1] for p in pts]

        ax.plot(rtr_vals, cost_vals, "o-", linewidth=2.5, markersize=10,
                color=colors[size], zorder=4)

        for i, (rtr, cost, w) in enumerate(pts):
            xytext = (8, 6) if i % 2 == 0 else (-12, -14)
            ax.annotate(f"w={w}", (rtr, cost), textcoords="offset points",
                        xytext=xytext, fontsize=10, fontweight="bold",
                        color="black")

        ax.set_xlabel("$R_{TR}$", fontsize=12)
        ax.set_ylabel("Average S2 Dispatch Cost", fontsize=12)
        ax.set_title(f"Cost\u2013Resilience Trade-off ({title})", fontsize=13)
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    for ext in ("pdf", "png"):
        out = out_dir / f"pareto_front.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'pareto_front.[pdf|png]'}")


def _pareto_filter(pts: list[tuple[float, float, int]]) -> list[tuple[float, float, int]]:
    """Keep only Pareto-optimal points (minimise cost, maximise R_TR)."""
    front = []
    for i, (r_i, c_i, w_i) in enumerate(pts):
        dominated = False
        for j, (r_j, c_j, _) in enumerate(pts):
            if i == j:
                continue
            # j dominates i if j is at least as good on both and strictly better on one
            if r_j >= r_i and c_j <= c_i and (r_j > r_i or c_j < c_i):
                dominated = True
                break
        if not dominated:
            front.append((r_i, c_i, w_i))
    return sorted(front, key=lambda x: x[0])


def plot_pareto_grid(df: pd.DataFrame, out_dir: Path) -> None:
    """2x2 grid Pareto: R_TR vs S2 cost for small, medium, large, industrylite.
    Only Pareto-optimal weight points are shown."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # (ax, code label, paper name, colour, weights to exclude, force_weights)
    # force_weights: if set, skip Pareto filter and show only these weights
    panels = [
        (axes[0, 0], "small",        "Small",        "#1f77b4", {1500}, None),
        (axes[0, 1], "medium",       "Medium",       "#ff7f0e", {1500}, None),
        (axes[1, 0], "xlarge",       "Large",        "#2ca02c", set(),  {0, 2000}),
        (axes[1, 1], "industrylite", "IndustryLite", "#d62728", set(),  None),
    ]

    for ax, size, title, color, exclude, force in panels:
        sub = df[df["size_label"] == size]
        if sub.empty:
            ax.set_title(f"{title} (no data)", fontsize=12)
            continue

        all_pts = []
        for w, grp in sub.groupby("weight"):
            if int(w) in exclude:
                continue
            all_pts.append((
                grp["r_tr"].mean(),
                grp["s2_dispatch_cost"].mean(),
                int(w),
            ))

        if force is not None:
            front = sorted([p for p in all_pts if p[2] in force],
                           key=lambda x: x[0])
        else:
            front = _pareto_filter(all_pts)

        rtr_vals = [p[0] for p in front]
        cost_vals = [p[1] for p in front]

        ax.plot(rtr_vals, cost_vals, "o-", linewidth=2.5, markersize=10,
                color=color, zorder=4)

        # Place labels with no overlaps: cycle through positions
        positions = [
            ( 8,  10, "left",  "bottom"),  # above-right
            (-8, -12, "right", "top"),      # below-left
            ( 8, -12, "left",  "top"),      # below-right
            (-8,  10, "right", "bottom"),   # above-left
        ]
        for i, (rtr, cost, w) in enumerate(front):
            dx, dy, ha, va = positions[i % len(positions)]
            ax.annotate(f"w={w}", (rtr, cost), textcoords="offset points",
                        xytext=(dx, dy), fontsize=9, fontweight="bold",
                        color="black", ha=ha, va=va)

        # Add padding so labels aren't clipped
        if rtr_vals:
            rtr_range = max(rtr_vals) - min(rtr_vals) if len(rtr_vals) > 1 else 0.1
            cost_range = max(cost_vals) - min(cost_vals) if len(cost_vals) > 1 else max(cost_vals) * 0.1
            ax.set_xlim(min(rtr_vals) - rtr_range * 0.15,
                        max(rtr_vals) + rtr_range * 0.15)
            ax.set_ylim(min(cost_vals) - cost_range * 0.15,
                        max(cost_vals) + cost_range * 0.2)

        ax.set_xlabel("$R_{TR}$", fontsize=12)
        ax.set_ylabel("Average S2 Dispatch Cost", fontsize=12)
        ax.set_title(f"{title}", fontsize=13)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Cost\u2013Resilience Trade-off by Instance Size", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    for ext in ("pdf", "png"):
        out = out_dir / f"pareto_front_grid.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'pareto_front_grid.[pdf|png]'}")


def plot_cost_increase_vs_rtr(df: pd.DataFrame, out_dir: Path) -> None:
    """All sizes on one plot: R_TR (%) vs S2 cost increase relative to w=0 (%)."""
    # (code label, paper name, best weight)
    size_config = [
        ("small",        "Small",        1000),
        ("medium",       "Medium",       1000),
        ("xlarge",       "Large",        2000),
        ("industrylite", "IndustryLite", 2000),
    ]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    shapes = ["o", "s", "D", "^"]

    fig, ax = plt.subplots(figsize=(9, 6))
    i=0 
    for (size, label, best_w), color in zip(size_config, colors):
        sub = df[df["size_label"] == size]
        
        if sub.empty:
            continue
        # Baseline cost at w=0
        w0 = sub[sub["weight"] == 0]
        if w0.empty:
            continue
        c0 = w0["s2_dispatch_cost"].mean()

        pts = []
        for w in [0, best_w]:
            wsub = sub[sub["weight"] == w]
            if wsub.empty:
                continue
            rtr = wsub["r_tr"].mean() * 100
            cost_pct = (wsub["s2_dispatch_cost"].mean() - c0) / c0 * 100
            pts.append((rtr, cost_pct, int(w)))

        rtr_vals = [p[0] for p in pts]
        pct_vals = [p[1] for p in pts]

        ax.plot(rtr_vals, pct_vals, "o--", linewidth=2, markersize=9,
                color=color, label=label, marker=shapes[i])
        i+=1
        for rtr, pct, w in pts:
            ax.annotate(f"w={w}", (rtr, pct), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=9,
                        fontweight="bold", color="black")
            

    ax.axhline(0, color="gray", linewidth=1, alpha=0.5)
    ax.set_xlabel("Resilience ($R_{TR}$ %)", fontsize=12)
    ax.set_ylabel("Total relative cost increase (%)", fontsize=12)
    ax.set_title("Cost Increase vs Resilience Gain by Instance Size", fontsize=13)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(title="Instance Size", fontsize=10)

    fig.tight_layout()
    for ext in ("pdf", "png"):
        out = out_dir / f"cost_increase_vs_rtr.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'cost_increase_vs_rtr.[pdf|png]'}")


def plot_ralpha_cost_tradeoff(df: pd.DataFrame, out_dir: Path, alpha:float) -> None:
    """Like cost_increase_vs_rtr but for packing configs instead of instance sizes.
    X-axis: global R_alpha at alpha=0.8 (%).  Y-axis: S2 cost increase vs w=0 off_off (%).
    One line per config, points are weights. One figure per instance size."""
    if not _has_r_alpha_cols(df):
        print("  [SKIP] No R_alpha columns for cost tradeoff plot")
        return

    cmap = {"off_off": "#1f77b4", "hetero": "#2ca02c",
            "conc": "#ff7f0e", "both": "#d62728"}
    markers = {"off_off": "o", "hetero": "s", "conc": "D", "both": "^"}
    col = _r_alpha_col("heaviest", "global", alpha)
    exclude_weights = {1500}

    for target_size, size_label in [("small", "Small")]:
        sub = df[df["size_label"] == target_size]
        if sub.empty:
            continue

        # Baseline cost: off_off at w=0
        baseline = sub[(sub["weight"] == 0) & (sub["s2_config"] == "off_off")]
        if baseline.empty:
            continue
        c0 = baseline["s2_dispatch_cost"].mean()

        fig, ax = plt.subplots(figsize=(9, 6))

        for cfg in CONFIG_ORDER:
            cfg_sub = sub[sub["s2_config"] == cfg]
            if cfg_sub.empty:
                continue

            all_weights = sorted(cfg_sub["weight"].unique())
            all_weights = [w for w in all_weights if int(w) not in exclude_weights]
            pick_weights = {int(all_weights[0]), int(all_weights[-1])} if all_weights else set()

            pts = []
            for w in all_weights:
                if int(w) not in pick_weights:
                    continue
                w_sub = cfg_sub[cfg_sub["weight"] == w]
                if w_sub.empty:
                    continue
                r_val = w_sub[col].mean() * 100
                cost_pct = (w_sub["s2_dispatch_cost"].mean() - c0) / c0 * 100
                pts.append((r_val, cost_pct, int(w)))

            if not pts:
                continue
            pts.sort(key=lambda x: x[2])

            r_vals = [p[0] for p in pts]
            cost_vals = [p[1] for p in pts]

            ax.plot(r_vals, cost_vals, f"{markers[cfg]}--",
                    linewidth=2, markersize=9, color=cmap[cfg], label=cfg)

            positions = [
                ( 0,  10, "center", "bottom"),
                ( 0, -12, "center", "top"),
                ( 8,   0, "left",   "center"),
                (-8,   0, "right",  "center"),
            ]
            for i, (r, c, w) in enumerate(pts):
                dx, dy, ha, va = positions[i % len(positions)]
                ax.annotate(f"w={w}", (r, c), textcoords="offset points",
                            xytext=(dx, dy), fontsize=9, fontweight="bold",
                            color="black", ha=ha, va=va)

        ax.axhline(0, color="gray", linewidth=1, alpha=0.5)
        ax.set_xlabel(r"Global $R_{\alpha}$ at $\alpha{=}0.8$ (%)", fontsize=12)
        ax.set_ylabel("Total relative cost increase (%)", fontsize=12)
        ax.set_title(f"Total costs vs Disruption Tolerance",
                     fontsize=13)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(title="Config", fontsize=10)

        fig.tight_layout()
        for ext in ("pdf", "png"):
            out = out_dir / f"ralpha_cost_tradeoff_global_{target_size}.{ext}"
            fig.savefig(out, dpi=200, bbox_inches="tight")
        plt.close(fig)
        print(f"  Wrote plot -> {out_dir / f'ralpha_cost_tradeoff_{target_size}_global_{alpha}.[png]'}")


def plot_mono_reduction(df: pd.DataFrame, out_dir: Path) -> None:
    """Bar chart showing mono-trip count reduction under hetero config."""
    fig, ax = plt.subplots(figsize=(10, 5))

    sizes = ["paper", "small", "medium", "large", "xlarge", "industrylite"]
    x = np.arange(len(sizes))
    width = 0.35

    for i, cfg in enumerate(["off_off", "hetero"]):
        means = []
        for size in sizes:
            sub = df[(df["size_label"] == size) & (df["s2_config"] == cfg)]
            means.append(sub["mono_count"].mean() if len(sub) else 0)
        offset = (i - 0.5) * width
        ax.bar(x + offset, means, width, label=cfg, alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([s.capitalize() for s in sizes], fontsize=10)
    ax.set_ylabel("Average Mono-Trip Count", fontsize=12)
    ax.set_title("Hetero Penalty Eliminates Mono-Part Trips", fontsize=13)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    for ext in ("pdf", "png"):
        out = out_dir / f"mono_reduction.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'mono_reduction.[pdf|png]'}")


def plot_scalability(df: pd.DataFrame, out_dir: Path) -> None:
    """Scatter showing solve time vs optimality rate by instance size."""
    sizes = ["paper", "small", "medium", "xlarge", "industrylite", "industry"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    s1_times, s1_opts, s2_times, s2_opts = [], [], [], []
    for size in sizes:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        s1_times.append(sub["s1_time"].mean())
        s1_opts.append((sub["s1_optimal"] == True).sum() / len(sub) * 100)  # noqa: E712
        s2_times.append(sub["s2_time"].mean())
        s2_opts.append((sub["s2_optimal"] == True).sum() / len(sub) * 100)  # noqa: E712

    labels = [s.capitalize() for s in sizes[:len(s1_times)]]

    ax1.bar(labels, s1_times, alpha=0.7, color="#1f77b4", label="S1 mean time")
    ax1.bar(labels, s2_times, alpha=0.7, color="#ff7f0e", bottom=s1_times, label="S2 mean time")
    ax1.set_ylabel("Mean Solve Time (s)", fontsize=12)
    ax1.set_title("Total Solve Time by Instance Size", fontsize=13)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3, axis="y")

    ax2.plot(labels, s1_opts, "o-", label="S1 optimality %", linewidth=2, markersize=8)
    ax2.plot(labels, s2_opts, "s-", label="S2 optimality %", linewidth=2, markersize=8)
    ax2.set_ylabel("% Runs Proven Optimal", fontsize=12)
    ax2.set_title("Optimality Rate by Instance Size", fontsize=13)
    ax2.set_ylim(-5, 105)
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    for ext in ("pdf", "png"):
        out = out_dir / f"scalability.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'scalability.[pdf|png]'}")


# ---------------------------------------------------------------------------
# 7. R_alpha degradation curves
# ---------------------------------------------------------------------------
ALPHA_VALUES = [0.2, 0.4, 0.6, 0.8]
R_ALPHA_STRATEGIES = ["heaviest", "first", "last"]
R_ALPHA_MODES = ["single", "global"]


def _r_alpha_col(strategy: str, mode: str, alpha: float) -> str:
    return f"r_{strategy}_{mode}_{alpha}"


def _has_r_alpha_cols(df: pd.DataFrame) -> bool:
    """Check if the DataFrame has any R_alpha columns."""
    test_col = _r_alpha_col("heaviest", "single", 0.2)
    return test_col in df.columns and df[test_col].notna().any()


def plot_degradation_curves(df: pd.DataFrame, out_dir: Path) -> None:
    """Degradation curves: R_alpha vs alpha, one subplot per strategy, lines per config."""
    if not _has_r_alpha_cols(df):
        print("  [SKIP] No R_alpha columns found")
        return

    for target_size in ["small", "medium"]:
        sub = df[df["size_label"] == target_size]
        if sub.empty:
            continue

        fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharey="row")
        cmap = {"off_off": "#1f77b4", "hetero": "#2ca02c", "conc": "#ff7f0e", "both": "#d62728"}

        for col_idx, strat in enumerate(R_ALPHA_STRATEGIES):
            for row_idx, md in enumerate(R_ALPHA_MODES):
                ax = axes[row_idx][col_idx]
                for cfg in CONFIG_ORDER:
                    cfg_sub = sub[sub["s2_config"] == cfg]
                    if cfg_sub.empty:
                        continue
                    means = []
                    for a in ALPHA_VALUES:
                        col = _r_alpha_col(strat, md, a)
                        vals = pd.to_numeric(cfg_sub[col], errors="coerce").dropna()
                        means.append(vals.mean() if len(vals) else np.nan)
                    ax.plot(ALPHA_VALUES, means, "o-", linewidth=2, markersize=7,
                            color=cmap[cfg], label=cfg)

                ax.set_xlabel("Survival fraction (α)", fontsize=11)
                ax.set_ylabel("R_α (demand coverage)", fontsize=11)
                ax.set_title(f"{strat} / {md}", fontsize=12)
                ax.set_xlim(0.15, 0.85)
                ax.set_ylim(-0.05, 1.05)
                ax.grid(True, alpha=0.3)
                if col_idx == 0 and row_idx == 0:
                    ax.legend(fontsize=9)

        fig.suptitle(f"Degradation Curves — {target_size.capitalize()} instances "
                     f"(averaged over seeds & weights)", fontsize=14)
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        for ext in ("pdf", "png"):
            out = out_dir / f"degradation_{target_size}.{ext}"
            fig.savefig(out, dpi=200, bbox_inches="tight")
        plt.close(fig)
        print(f"  Wrote degradation plot -> {out_dir / f'degradation_{target_size}.[pdf|png]'}")


def plot_degradation_heaviest_config_weights_grid(df: pd.DataFrame, out_dir: Path) -> None:
    """R_alpha vs alpha (heaviest-trip removal only) in a 2x2 grid.
    Rows: Small, IndustryLite
    Cols: Single-Arc, Global Disruption
    """

    strategy = "heaviest"
    
    # Keys must match CONFIG_ORDER / df["s2_config"]: off_off, hetero, conc, both
    cmap = {
        "off_off": "#0057E9",   # Blue
        "hetero": "#F2CA19",    # Purple
        "conc": "#803E75",      # Magenta (concentration / equal_distr)
        "both": "#E11845",      # Red
    }
    
    ls_by_role = {"min": "-", "max": ":"}

    # Define our grid dimensions
    target_sizes = ["small", "industrylite"]
    modes = [("single", "Single-Arc Disruption"), ("global", "Global Disruption")]

    # Create a 2x2 grid
    fig, axes = plt.subplots(nrows=2, ncols=2, figsize=(12, 9), sharex=True)
    
    # Track items for the custom figure-level legends
    config_handles = []
    added_configs = set()

    for row_idx, target_size in enumerate(target_sizes):
        sub = df[df["size_label"] == target_size]
        if sub.empty:
            continue

        weights_all = sorted(w for w in sub["weight"].dropna().unique())
        if not weights_all:
            continue
            
        w_min = int(weights_all[0])
        w_max = int(weights_all[-1])
        weight_roles: list[tuple[int, str]] = [(w_min, "min")]
        if w_max != w_min:
            weight_roles.append((w_max, "max"))

        for col_idx, (mode, mode_title) in enumerate(modes):
            ax = axes[row_idx, col_idx]
            
            # Variables to track dynamic Y-limits for this specific subplot
            y_min, y_max = float('inf'), float('-inf')
            has_data = False

            for cfg in CONFIG_ORDER:
                color = cmap.get(cfg, "#333333")
                cfg_sub = sub[sub["s2_config"] == cfg]
                if cfg_sub.empty:
                    continue
                
                # Build the color legend handles once
                if cfg not in added_configs:
                    config_handles.append(Line2D([0], [0], color=color, lw=2.2, label=cfg))
                    added_configs.add(cfg)

                for w, role in weight_roles:
                    w_sub = cfg_sub[cfg_sub["weight"] == w]
                    if w_sub.empty:
                        continue
                        
                    means = []
                    for a in ALPHA_VALUES:
                        col = _r_alpha_col(strategy, mode, a)
                        vals = pd.to_numeric(w_sub[col], errors="coerce").dropna()
                        means.append(vals.mean() if len(vals) else np.nan)

                    # Plot the line on the specific subplot without individual labels
                    ax.plot(
                        ALPHA_VALUES,
                        means,
                        
                        color=color,
                        linestyle=ls_by_role[role],
                        linewidth=2.2,
                        marker="o",
                        markersize=6
                    )
                    
                    # Update local Y-limits
                    valid_means = [m for m in means if not np.isnan(m)]
                    if valid_means:
                        y_min = min(y_min, min(valid_means))
                        y_max = max(y_max, max(valid_means))
                        has_data = True

            # Format the specific subplot
            ax.set_title(f"{target_size.capitalize()} - {mode_title}", fontsize=12)
            if row_idx == 1:
                ax.set_xlabel(r"Survival fraction ($\alpha$)", fontsize=11)
            if col_idx == 0:
                ax.set_ylabel(r"$R_\alpha$ (demand coverage)", fontsize=11)
            
            # Add X-limits based on your ALPHA_VALUES bounds
            ax.set_xlim(min(ALPHA_VALUES) - 0.05, max(ALPHA_VALUES) + 0.05)
            
            # Apply tight dynamic Y-limits with 5% padding to see the variance clearly
            if has_data:
                y_range = y_max - y_min
                padding = y_range * 0.2 if y_range > 0 else 0.1
                ax.set_ylim(max(0, y_min - padding), min(1.0, y_max + padding)) # Constrain between 0 and 1
            
            ax.grid(True, alpha=0.3)

    # --- Build the separate legends ---
    # Legend 1: Line Styles (Weights)
    weight_handles = [
        Line2D([0], [0], color='gray', linestyle='-', lw=2.2, label='Min Weight ($w=0$)'),
        Line2D([0], [0], color='gray', linestyle=':', lw=2.2, label='Max Weight ($w>0$)')
    ]

    # 2. UPDATED LEGENDS: Side-by-side positioning with vertically stacked contents
    # bbox_to_anchor uses (x, y) coordinates relative to the figure. 
    # 0.48 puts the right edge of the first box just left of center.
    # 0.52 puts the left edge of the second box just right of center.
    fig.legend(handles=config_handles, title="Packing Configuration", 
               loc='upper right', bbox_to_anchor=(0.48, 0.15), ncol=1, fontsize=10, title_fontsize=11)
    
    fig.legend(handles=weight_handles, title="Stage 1 Weight", 
               loc='upper left', bbox_to_anchor=(0.52, 0.15), ncol=1, fontsize=10, title_fontsize=11)

    fig.tight_layout()
    
    # Compress the subplots slightly upwards to make room for the taller vertical legends below.
    # Increased to 0.25 to accommodate the vertically stacked items.
    fig.subplots_adjust(bottom=0.25)
    
    # Save outputs
    stem = "degradation_ralpha_grid_dynamic"
    for ext in ("pdf", "png"):
        fig.savefig(out_dir / f"{stem}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / f'{stem}.[pdf|png]'}")
# def plot_degradation_heaviest_config_weights(df: pd.DataFrame, out_dir: Path) -> None:
#     """R_alpha vs alpha (heaviest-trip removal only): x = survival fraction α, y = coverage.

#     Lines are colored by packing config; line style distinguishes the smallest vs largest
#     weight present in the sweep for that instance size.
#     """
#     if not _has_r_alpha_cols(df):
#         print("  [SKIP] No R_alpha columns found")
#         return

#     strategy = "heaviest"
#     cmap = {"off_off": "#1f77b4", "hetero": "#2ca02c", "conc": "#ff7f0e", "both": "#d62728"}
#     # Min weight: solid; max weight: dotted
#     ls_by_role = {"min": "-", "max": ":"}

#     for target_size in ("small", "medium"):
#         sub = df[df["size_label"] == target_size]
#         if sub.empty:
#             continue

#         weights_all = sorted(w for w in sub["weight"].dropna().unique())
#         if not weights_all:
#             continue
#         w_min = int(weights_all[0])
#         w_max = int(weights_all[-1])
#         weight_roles: list[tuple[int, str]] = [(w_min, "min")]
#         if w_max != w_min:
#             weight_roles.append((w_max, "max"))

#         for mode, mode_title in [
#             ("single", "Single-Arc Disruption"),
#             ("global", "Global Disruption"),
#         ]:
#             fig, ax = plt.subplots(figsize=(9, 5.5))

#             for cfg in CONFIG_ORDER:
#                 color = cmap.get(cfg, "#333333")
#                 cfg_sub = sub[sub["s2_config"] == cfg]
#                 if cfg_sub.empty:
#                     continue

#                 for w, role in weight_roles:
#                     w_sub = cfg_sub[cfg_sub["weight"] == w]
#                     if w_sub.empty:
#                         continue
#                     means = []
#                     for a in ALPHA_VALUES:
#                         col = _r_alpha_col(strategy, mode, a)
#                         vals = pd.to_numeric(w_sub[col], errors="coerce").dropna()
#                         means.append(vals.mean() if len(vals) else np.nan)

#                     label = f"{cfg}, w={w}"
#                     ax.plot(
#                         ALPHA_VALUES,
#                         means,
#                         color=color,
#                         linestyle=ls_by_role[role],
#                         linewidth=2.2,
#                         marker="o",
#                         markersize=6,
#                         label=label,
#                     )

#             ax.set_xlabel(r"Survival fraction ($\alpha$)", fontsize=12)
#             ax.set_ylabel(r"$R_\alpha$ (demand coverage)", fontsize=12)
#             ax.set_title(
#                 f"Heaviest-trip removal — {mode_title}\n"
#                 f"{target_size.capitalize()} instances (mean over seeds)",
#                 fontsize=13,
#             )
#             ax.set_xlim(0.15, 0.85)
#             ax.set_ylim(-0.05, 1.05)
#             ax.grid(True, alpha=0.3)
#             ax.legend(
#                 title="Config, weight",
#                 fontsize=9,
#                 title_fontsize=10,
#                 loc="lower right",
#                 ncol=2,
#             )

#             fig.tight_layout()
#             stem = f"degradation_ralpha_heaviest_wminmax_{target_size}_{mode}"
#             for ext in ("pdf", "png"):
#                 fig.savefig(out_dir / f"{stem}.{ext}", dpi=200, bbox_inches="tight")
#             plt.close(fig)
#             print(f"  Wrote plot -> {out_dir / f'{stem}.[pdf|png]'}")




def plot_degradation_heaviest(df: pd.DataFrame, out_dir: Path) -> None:
    """2x2 grids: one figure for single-arc, one for global.
    Each subplot is a packing config; lines are per-weight degradation curves."""
    if not _has_r_alpha_cols(df):
        print("  [SKIP] No R_alpha columns found")
        return

    sub = df[df["size_label"] == "small"]
    if sub.empty:
        return

    exclude_weights = {1500}
    weights = sorted(w for w in sub["weight"].unique() if w not in exclude_weights)
    weight_colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(weights)))

    cfg_titles = {
        "off_off": "No Constraints (off\\_off)",
        "hetero": "Heterogeneity (hetero)",
        "conc": "Concentration (conc)",
        "both": "Both Constraints (both)",
    }

    for mode, mode_title, fname in [
        ("single", "Single-Arc Disruption", "degradation_single_small"),
        ("global", "Global Disruption", "degradation_global_small"),
    ]:
        fig, axes = plt.subplots(2, 2, figsize=(11, 9), sharey=True, sharex=True)

        for ax, cfg in zip(axes.flat, CONFIG_ORDER):
            cfg_sub = sub[sub["s2_config"] == cfg]
            if cfg_sub.empty:
                continue

            for w, color in zip(weights, weight_colors):
                w_sub = cfg_sub[cfg_sub["weight"] == w]
                if w_sub.empty:
                    continue
                means = []
                stds = []
                for a in ALPHA_VALUES:
                    col = _r_alpha_col("heaviest", mode, a)
                    vals = pd.to_numeric(w_sub[col], errors="coerce").dropna()
                    means.append(vals.mean() if len(vals) else np.nan)
                    stds.append(vals.std() if len(vals) > 1 else 0)
                ax.errorbar(ALPHA_VALUES, means, yerr=stds, fmt="o-",
                            linewidth=2, markersize=6, capsize=3,
                            color=color, label=f"w={int(w)}")

            ax.set_title(cfg_titles[cfg], fontsize=11)
            ax.set_xlim(0.15, 0.85)
            ax.set_ylim(-0.05, 1.05)
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=8, loc="lower right")

        for ax in axes[1]:
            ax.set_xlabel(r"Survival fraction ($\alpha$)", fontsize=11)
        for ax in axes[:, 0]:
            ax.set_ylabel(r"$R_\alpha$ (demand coverage)", fontsize=11)

        fig.suptitle(f"Heaviest-Trip Removal \u2014 {mode_title}\n"
                     f"Small Instances (n=5 seeds)", fontsize=13)
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        for ext in ("pdf", "png"):
            out = out_dir / f"{fname}.{ext}"
            fig.savefig(out, dpi=200, bbox_inches="tight")
        plt.close(fig)
        print(f"  Wrote plot -> {out_dir / f'{fname}.[pdf|png]'}")


def write_r_alpha_summary(df: pd.DataFrame, out: Path) -> None:
    """Summary table: R_alpha at each alpha for heaviest/single, by size and config."""
    if not _has_r_alpha_cols(df):
        print("  [SKIP] No R_alpha columns found")
        return

    rows = []
    for size in SWEEP_FILES:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        for cfg in CONFIG_ORDER:
            cfg_sub = sub[sub["s2_config"] == cfg]
            if cfg_sub.empty:
                continue
            entry = {"size": size, "config": cfg}
            for strat in R_ALPHA_STRATEGIES:
                for md in R_ALPHA_MODES:
                    for a in ALPHA_VALUES:
                        col = _r_alpha_col(strat, md, a)
                        vals = pd.to_numeric(cfg_sub[col], errors="coerce").dropna()
                        entry[col] = round(vals.mean(), 4) if len(vals) else None
            rows.append(entry)

    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  Wrote R_alpha summary -> {out}")


# ===========================================================================
# Paper-specific tables
# ===========================================================================

# ---------------------------------------------------------------------------
# P1. Summary across sizes (Table: summary_across_sizes)
#     For each size: baseline (w=0) and best weight rows.
#     Columns: Size, w, R_TR, S1 Cost, S2 Cost, Saving(%)
# ---------------------------------------------------------------------------
def table_summary_across_sizes(df: pd.DataFrame, out: Path) -> None:
    rows = []
    for size in SIZE_ORDER:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        best_w = BEST_WEIGHT.get(size, 0)
        for w in sorted({0, best_w}):
            wsub = sub[sub["weight"] == w]
            if wsub.empty:
                continue
            r_tr = wsub["r_tr"].mean()
            s1_cost = wsub["s1_dispatch_cost"].mean()
            s2_cost = wsub["s2_dispatch_cost"].mean()
            saving = (s1_cost - s2_cost) / s1_cost * 100 if s1_cost else 0
            rows.append({
                "size": size, "weight": int(w),
                "r_tr": round(r_tr, 2),
                "s1_cost": round(s1_cost, 0),
                "s2_cost": round(s2_cost, 0),
                "saving_pct": round(saving, 1),
            })
    out_df = pd.DataFrame(rows)
    out_df.to_csv(out, index=False)
    print(f"  Wrote summary_across_sizes -> {out}")
    print(out_df.to_string(index=False))


# ---------------------------------------------------------------------------
# P2. R_alpha table for a given size (Tables: ralpha_small, ralpha_industrylite)
#     Rows: weight x config.  Columns: single-arc 0.2..0.8, global 0.2..0.8
#     Uses heaviest strategy only.
# ---------------------------------------------------------------------------
def table_ralpha(df: pd.DataFrame, size: str, out: Path) -> None:
    sub = df[df["size_label"] == size]
    if sub.empty:
        print(f"  [SKIP] No data for {size}")
        return
    rows = []
    for w in sorted(sub["weight"].unique()):
        for cfg in CONFIG_ORDER:
            csub = sub[(sub["weight"] == w) & (sub["s2_config"] == cfg)]
            if csub.empty:
                continue
            entry: dict = {"weight": int(w), "config": cfg}
            for mode in ["single", "global"]:
                for alpha in ALPHA_VALUES:
                    col = _r_alpha_col("heaviest", mode, alpha)
                    if col in csub.columns:
                        entry[f"{mode}_{alpha}"] = round(csub[col].mean(), 2)
            rows.append(entry)
    out_df = pd.DataFrame(rows)
    out_df.to_csv(out, index=False)
    print(f"  Wrote ralpha ({size}) -> {out}")
    print(out_df.to_string(index=False))


# ---------------------------------------------------------------------------
# P3. First feasible vs best solution (Table: first_vs_best)
#     Rows: size x weight.  Columns: first R_TR, best R_TR
# ---------------------------------------------------------------------------
def table_first_vs_best(df: pd.DataFrame, out: Path) -> None:
    rows = []
    for size in SIZE_ORDER:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        for w in sorted(sub["weight"].unique()):
            wsub = sub[sub["weight"] == w]
            if wsub.empty:
                continue
            first_rtr = wsub["first_r_tr"].mean()
            best_rtr = wsub["r_tr"].mean()
            rows.append({
                "size": size, "weight": int(w),
                "first_r_tr": round(first_rtr, 2),
                "best_r_tr": round(best_rtr, 2),
            })
    out_df = pd.DataFrame(rows)
    out_df.to_csv(out, index=False)
    print(f"  Wrote first_vs_best -> {out}")
    print(out_df.to_string(index=False))


# ---------------------------------------------------------------------------
# P4. Scalability table (Table: scalability)
#     Rows: size.  Columns: S1 time, S1 opt%, S2 time, S2 opt%, avg R_TR
# ---------------------------------------------------------------------------
def table_scalability(df: pd.DataFrame, out: Path) -> None:
    rows = []
    for size in SIZE_ORDER:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        n = len(sub)
        rows.append({
            "size": size,
            "s1_time": round(sub["s1_time"].mean(), 1),
            "s1_opt_pct": round((sub["s1_optimal"] == True).sum() / n * 100, 0),
            "s2_time": round(sub["s2_time"].mean(), 1),
            "s2_opt_pct": round((sub["s2_optimal"] == True).sum() / n * 100, 0),
            "r_tr": round(sub["r_tr"].mean(), 2),
        })
    out_df = pd.DataFrame(rows)
    out_df.to_csv(out, index=False)
    print(f"  Wrote scalability -> {out}")
    print(out_df.to_string(index=False))


# ---------------------------------------------------------------------------
# P5. Pareto: cost vs R_TR for small instances (averaged over seeds, per weight)
# ---------------------------------------------------------------------------
def table_pareto_small(df: pd.DataFrame, out: Path) -> None:
    small = df[df["size_label"] == "small"]
    if small.empty:
        print("  [SKIP] No small data")
        return
    rows = []
    for w in sorted(small["weight"].unique()):
        wsub = small[small["weight"] == w]
        rows.append({
            "weight": int(w),
            "r_tr": round(wsub["r_tr"].mean(), 2),
            "s2_cost": round(wsub["s2_dispatch_cost"].mean(), 0),
            "s1_cost": round(wsub["s1_dispatch_cost"].mean(), 0),
        })
    out_df = pd.DataFrame(rows)
    out_df.to_csv(out, index=False)
    print(f"  Wrote pareto_small -> {out}")
    print(out_df.to_string(index=False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
REPORT_REGISTRY: dict[str, str] = {
    "summary":       "Table: summary across sizes (R_TR + costs at w=0 vs best w)",
    "ralpha_small":  "Table: R_alpha degradation for small instances",
    "ralpha_medium": "Table: R_alpha degradation for medium instances",
    "ralpha_ilite":  "Table: R_alpha degradation for industrylite instances",
    "ralpha_xlarge": "Table: R_alpha degradation for xlarge instances",
    "first_vs_best": "Table: first feasible vs best R_TR",
    "scalability":   "Table: solve times and optimality rates",
    "pareto_small":  "Table: Pareto cost-vs-R_TR for small",
    "plots":         "All plots (existing)",
    "all":           "Generate everything",
}


def _run_paper_tables(df: pd.DataFrame, reports: set[str]) -> None:
    """Run the paper-specific table generators."""
    analysis = RESULTS_DIR / "analysis"
    analysis.mkdir(exist_ok=True)

    if "summary" in reports:
        print("\n--- Summary across sizes ---")
        table_summary_across_sizes(df, analysis / "summary_across_sizes.csv")

    if "ralpha_small" in reports:
        print("\n--- R_alpha: small ---")
        table_ralpha(df, "small", analysis / "ralpha_small.csv")

    if "ralpha_medium" in reports:
        print("\n--- R_alpha: medium ---")
        table_ralpha(df, "medium", analysis / "ralpha_medium.csv")

    if "ralpha_ilite" in reports:
        print("\n--- R_alpha: industrylite ---")
        table_ralpha(df, "industrylite", analysis / "ralpha_industrylite.csv")

    if "ralpha_xlarge" in reports:
        print("\n--- R_alpha: xlarge ---")
        table_ralpha(df, "xlarge", analysis / "ralpha_xlarge.csv")

    if "first_vs_best" in reports:
        print("\n--- First vs best ---")
        table_first_vs_best(df, analysis / "first_vs_best.csv")

    if "scalability" in reports:
        print("\n--- Scalability ---")
        table_scalability(df, analysis / "scalability.csv")

    if "pareto_small" in reports:
        print("\n--- Pareto (small) ---")
        table_pareto_small(df, analysis / "pareto_small.csv")


def _run_legacy_tables(df: pd.DataFrame) -> None:
    """Run the original generic summary/detail tables."""
    write_averaged_summary(df, RESULTS_DIR / "summary_averaged.csv")
    write_per_seed_detail(df, RESULTS_DIR / "summary_per_seed.csv")
    write_r1_by_config_weight(df, RESULTS_DIR / "r1_by_config_weight.csv")
    write_pareto_tables(df, RESULTS_DIR)
    write_scalability_table(df, RESULTS_DIR / "scalability_table.csv")
    if _has_r_alpha_cols(df):
        write_r_alpha_summary(df, RESULTS_DIR / "r_alpha_summary.csv")


def _run_plots(df: pd.DataFrame) -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_rtr_vs_weight(df, PLOTS_DIR)
    plot_r1_by_config(df, PLOTS_DIR)
    plot_mono_reduction(df, PLOTS_DIR)
    plot_scalability(df, PLOTS_DIR)
    plot_pareto_averaged(df, PLOTS_DIR)
    plot_pareto_grid(df, PLOTS_DIR)
    plot_cost_increase_vs_rtr(df, PLOTS_DIR)
    plot_ralpha_cost_tradeoff(df, PLOTS_DIR,0.8)
    plot_degradation_heaviest_config_weights_grid(df, PLOTS_DIR)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate report tables and plots from experiment sweeps.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    report_names = "\n".join(f"  {k:18s} {v}" for k, v in REPORT_REGISTRY.items())
    parser.add_argument(
        "reports", nargs="*", default=["all"],
        help=f"Reports to generate (default: all).\nAvailable:\n{report_names}",
    )
    args = parser.parse_args()

    requested = set(args.reports)
    run_all = "all" in requested

    print("Loading experiment data...")
    df = load_all()
    print(f"  Loaded {len(df)} rows across {df['size_label'].nunique()} instance sizes")
    for size in SIZE_ORDER:
        n = len(df[df["size_label"] == size])
        if n:
            ws = sorted(df[df["size_label"] == size]["weight"].unique())
            print(f"    {size}: {n} rows, weights={[int(w) for w in ws]}")

    # Paper tables
    paper_reports = requested & set(REPORT_REGISTRY.keys()) - {"plots", "all"}
    if run_all or paper_reports:
        targets = set(REPORT_REGISTRY.keys()) - {"plots", "all"} if run_all else paper_reports
        _run_paper_tables(df, targets)

    # Legacy generic tables
    if run_all:
        print("\n--- Legacy tables ---")
        _run_legacy_tables(df)

    # Plots
    if run_all or "plots" in requested:
        print("\n--- Plots ---")
        _run_plots(df)

    print("\nDone! Outputs in:")
    print(f"  Analysis: {RESULTS_DIR / 'analysis'}")
    print(f"  Tables:   {RESULTS_DIR}")
    print(f"  Plots:    {PLOTS_DIR}")


if __name__ == "__main__":
    main()
