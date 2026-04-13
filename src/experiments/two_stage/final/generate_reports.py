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
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"
PLOTS_DIR = RESULTS_DIR / "plots" / "report"

SWEEP_FILES: dict[str, str] = {
    "paper":         "sweep_paper.csv",
    "small":         "sweep_small.csv",
    "medium":        "sweep_medium_moreweights.csv",
    "large":         "sweep_large.csv",
    "xlarge":        "sweep_xlarge.csv",
    "industrylite":  "sweep_industrylite.csv",
    "industry":      "sweep_industry_original_heavy.csv",
}

CONFIG_ORDER = ["off_off", "hetero", "conc", "both"]


def load_all() -> pd.DataFrame:
    """Load all sweep CSVs into one DataFrame, tagged by instance size."""
    frames = []
    for size_label, fname in SWEEP_FILES.items():
        path = RESULTS_DIR / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df = df[df["status"] == "OK"].copy()
        for col in ["r_tr", "r_1", "k_1"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ["nominal_cost", "s1_dispatch_cost", "s2_dispatch_cost",
                     "cost_saving", "mono_count", "concentrated_count",
                     "exposure_count", "weight", "seed"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["s1_time"] = pd.to_numeric(df["s1_time"], errors="coerce")
        df["s2_time"] = pd.to_numeric(df["s2_time"], errors="coerce")
        df["size_label"] = size_label
        frames.append(df)
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

    colors = {"small": "#1f77b4", "medium": "#ff7f0e"}
    for size in ["small", "medium"]:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        grp = sub.groupby("weight")["r_tr"].mean().sort_index()
        ax.plot(grp.index, grp.values, marker="o", linewidth=2.5,
                markersize=8, label=f"{size.capitalize()}",
                color=colors[size])

    ax.set_xlabel("Stage 1 Weight", fontsize=12)
    ax.set_ylabel("R_TR", fontsize=12)
    ax.set_title("Effect of weight on R_TR ", fontsize=13)
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
    """Pareto scatter: R_TR vs S2 cost (cost on y-axis), collapsed across configs."""
    small = df[df["size_label"] == "small"]
    if small.empty:
        return

    pts = []
    for w, grp in small.groupby("weight"):
        if int(w) == 750:
            continue
        pts.append((
            grp["r_tr"].mean(),
            grp["s2_dispatch_cost"].mean(),
            int(w),
        ))
    pts.sort(key=lambda x: x[2])

    fig, ax = plt.subplots(figsize=(7, 5))

    rtr_vals = [p[0] for p in pts]
    cost_vals = [p[1] for p in pts]
    weights = [p[2] for p in pts]

    ax.plot(rtr_vals, cost_vals, "o-", linewidth=2.5, markersize=10,
            color="#1f77b4", zorder=4)

    for rtr, cost, w in pts:
        ax.annotate(f"w={w}", (rtr, cost), textcoords="offset points",
                    xytext=(8, 4), fontsize=10, fontweight="bold")

    ax.set_xlabel("R_TR", fontsize=12)
    ax.set_ylabel("Average S2 Dispatch Cost", fontsize=12)
    ax.set_title("Cost–Resilience Trade-off for small instances", fontsize=13)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    for ext in ("pdf", "png"):
        out = out_dir / f"pareto_front_averaged.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'pareto_front_averaged.[pdf|png]'}")


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


def plot_degradation_heaviest(df: pd.DataFrame, out_dir: Path) -> None:
    """Focused plot: heaviest strategy, single vs global, for small instances."""
    if not _has_r_alpha_cols(df):
        print("  [SKIP] No R_alpha columns found")
        return

    sub = df[df["size_label"] == "small"]
    if sub.empty:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    cmap = {"off_off": "#1f77b4", "hetero": "#2ca02c", "conc": "#ff7f0e", "both": "#d62728"}

    for ax, md, title in [(ax1, "single", "Single-Arc Disruption"),
                           (ax2, "global", "Global Disruption")]:
        for cfg in CONFIG_ORDER:
            cfg_sub = sub[sub["s2_config"] == cfg]
            if cfg_sub.empty:
                continue
            means = []
            stds = []
            for a in ALPHA_VALUES:
                col = _r_alpha_col("heaviest", md, a)
                vals = pd.to_numeric(cfg_sub[col], errors="coerce").dropna()
                means.append(vals.mean() if len(vals) else np.nan)
                stds.append(vals.std() if len(vals) > 1 else 0)
            ax.errorbar(ALPHA_VALUES, means, yerr=stds, fmt="o-", linewidth=2,
                        markersize=7, capsize=4, color=cmap[cfg], label=cfg)

        ax.set_xlabel("Survival fraction (α)", fontsize=12)
        ax.set_ylabel("R_α (worst-case demand coverage)", fontsize=12)
        ax.set_title(title, fontsize=13)
        ax.set_xlim(0.15, 0.85)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=10)

    fig.suptitle("Heaviest-Trip Removal — Small Instances (n=5 seeds)", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    for ext in ("pdf", "png"):
        out = out_dir / f"degradation_heaviest_small.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote plot -> {out_dir / 'degradation_heaviest_small.[pdf|png]'}")


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("Loading experiment data...")
    df = load_all()
    print(f"  Loaded {len(df)} rows across {df['size_label'].nunique()} instance sizes")

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    print("\n--- CSV Tables ---")
    write_averaged_summary(df, RESULTS_DIR / "summary_averaged.csv")
    write_per_seed_detail(df, RESULTS_DIR / "summary_per_seed.csv")
    write_r1_by_config_weight(df, RESULTS_DIR / "r1_by_config_weight.csv")
    write_pareto_tables(df, RESULTS_DIR)
    write_scalability_table(df, RESULTS_DIR / "scalability_table.csv")

    if _has_r_alpha_cols(df):
        write_r_alpha_summary(df, RESULTS_DIR / "r_alpha_summary.csv")

    print("\n--- Plots ---")
    plot_rtr_vs_weight(df, PLOTS_DIR)
    plot_r1_by_config(df, PLOTS_DIR)
    # plot_pareto_front(df, PLOTS_DIR)
    plot_mono_reduction(df, PLOTS_DIR)
    plot_scalability(df, PLOTS_DIR)
    plot_pareto_averaged(df, PLOTS_DIR)
    plot_degradation_curves(df, PLOTS_DIR)
    plot_degradation_heaviest(df, PLOTS_DIR)
    print("\nDone! All outputs in:")
    print(f"  Tables: {RESULTS_DIR}")
    print(f"  Plots:  {PLOTS_DIR}")


if __name__ == "__main__":
    main()
