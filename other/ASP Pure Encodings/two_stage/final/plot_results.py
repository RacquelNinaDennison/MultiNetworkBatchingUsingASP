#!/usr/bin/env python3
"""
plot_results.py
===============
Publication-quality plots from div_weight sweep CSV.

Usage
-----
    python plot_results.py
    python plot_results.py --input results/div_weight_sweep.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ── Helpers ──────────────────────────────────────────────────────────────

def load_and_prepare(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # Derive pure transport cost
    df["transport_cost"] = df["nominal_cost"] - df["div_weight"] * df["dominant_count"]
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Mean +/- 1 std across seeds per (instance_size, div_weight)."""
    metrics = ["transport_cost", "r_tr", "dominant_count", "nominal_cost",
               "s1_time", "worst_arc_coverage"]
    agg_funcs = {m: ["mean", "std"] for m in metrics if m in df.columns}
    grouped = df.groupby(["instance_size", "div_weight"]).agg(agg_funcs)
    grouped.columns = ["_".join(col) for col in grouped.columns]
    return grouped.reset_index()


SIZE_ORDER = ["small", "medium", "large"]
SIZE_COLORS = {"small": "#1f77b4", "medium": "#ff7f0e", "large": "#2ca02c",
               "custom": "#d62728"}
SIZE_MARKERS = {"small": "o", "medium": "s", "large": "^", "custom": "D"}


def _sizes_in(df: pd.DataFrame) -> list[str]:
    """Return size classes present in df, in canonical order."""
    present = set(df["instance_size"].unique())
    ordered = [s for s in SIZE_ORDER if s in present]
    extra = sorted(present - set(SIZE_ORDER))
    return ordered + extra


def pareto_front(df: pd.DataFrame) -> pd.DataFrame:
    """Return non-dominated rows minimising transport_cost and dominant_count."""
    mask = pd.Series(True, index=df.index)
    costs = df["transport_cost"].values
    doms = df["dominant_count"].values
    for i in range(len(df)):
        if not mask.iloc[i]:
            continue
        for j in range(len(df)):
            if i == j or not mask.iloc[j]:
                continue
            # j dominates i if j is at least as good on both and strictly better on one
            if (costs[j] <= costs[i] and doms[j] <= doms[i] and
                    (costs[j] < costs[i] or doms[j] < doms[i])):
                mask.iloc[i] = False
                break
    return df[mask].sort_values("dominant_count")


# ── Plot 1: Transport Cost vs div_weight ─────────────────────────────────

def plot_cost_vs_weight(agg: pd.DataFrame, outdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 7))

    for size in _sizes_in(agg):
        sub = agg[agg["instance_size"] == size].sort_values("div_weight")
        if sub.empty:
            continue
        x = sub["div_weight"]
        y = sub["transport_cost_mean"]
        err = sub["transport_cost_std"].fillna(0)
        c = SIZE_COLORS.get(size, "#333")
        ax.plot(x, y, marker=SIZE_MARKERS.get(size, "o"), color=c,
                label=size, linewidth=2, markersize=6)
        ax.fill_between(x, y - err, y + err, color=c, alpha=0.15)

    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("div_weight", fontsize=12)
    ax.set_ylabel("Transport Cost", fontsize=12)
    ax.set_title("Transport Cost vs div_weight", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(outdir / "cost_vs_weight.png", dpi=150)
    plt.close(fig)
    print(f"  Saved cost_vs_weight.png")


# ── Plot 2: R_TR vs div_weight ───────────────────────────────────────────

def plot_rtr_vs_weight(agg: pd.DataFrame, outdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 7))

    for size in _sizes_in(agg):
        sub = agg[agg["instance_size"] == size].sort_values("div_weight")
        if sub.empty:
            continue
        x = sub["div_weight"]
        y = sub["r_tr_mean"]
        err = sub["r_tr_std"].fillna(0)
        c = SIZE_COLORS.get(size, "#333")
        ax.plot(x, y, marker=SIZE_MARKERS.get(size, "o"), color=c,
                label=size, linewidth=2, markersize=6)
        ax.fill_between(x, y - err, y + err, color=c, alpha=0.15)

    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("div_weight", fontsize=12)
    ax.set_ylabel("R_TR (min coverage)", fontsize=12)
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Network Resilience (R_TR) vs div_weight", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(outdir / "rtr_vs_weight.png", dpi=150)
    plt.close(fig)
    print(f"  Saved rtr_vs_weight.png")


# ── Plot 3: Dominant Count vs div_weight ─────────────────────────────────

def plot_dominant_vs_weight(agg: pd.DataFrame, outdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 7))

    for size in _sizes_in(agg):
        sub = agg[agg["instance_size"] == size].sort_values("div_weight")
        if sub.empty:
            continue
        x = sub["div_weight"]
        y = sub["dominant_count_mean"]
        err = sub["dominant_count_std"].fillna(0)
        c = SIZE_COLORS.get(size, "#333")
        ax.plot(x, y, marker=SIZE_MARKERS.get(size, "o"), color=c,
                label=size, linewidth=2, markersize=6)
        ax.fill_between(x, y - err, y + err, color=c, alpha=0.15)

    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("div_weight", fontsize=12)
    ax.set_ylabel("Dominant TR Count", fontsize=12)
    ax.set_title("Dominant Transport Count vs div_weight", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    fig.savefig(outdir / "dominant_vs_weight.png", dpi=150)
    plt.close(fig)
    print(f"  Saved dominant_vs_weight.png")


# ── Plot 4: Cost-Resilience Tradeoff ────────────────────────────────────

def plot_cost_resilience(df: pd.DataFrame, outdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 7))

    # Filter to OK rows with valid data
    ok = df[(df["status"] == "OK") &
            df["transport_cost"].notna() &
            df["r_tr"].notna()].copy()
    if ok.empty:
        plt.close(fig)
        return

    sc = None
    sizes_present = [s for s in SIZE_ORDER if s in ok["instance_size"].values]
    if not sizes_present:
        sizes_present = sorted(ok["instance_size"].unique())

    for size in sizes_present:
        sub = ok[ok["instance_size"] == size]
        if sub.empty:
            continue
        marker = SIZE_MARKERS.get(size, "o")
        sc = ax.scatter(
            sub["transport_cost"], sub["r_tr"],
            c=sub["div_weight"], cmap="viridis",
            marker=marker, s=60, edgecolors="k", linewidths=0.5,
            label=size, vmin=ok["div_weight"].min(), vmax=ok["div_weight"].max(),
        )

    if sc is None:
        plt.close(fig)
        return
    fig.colorbar(sc, ax=ax, label="div_weight")
    ax.set_xlabel("Transport Cost", fontsize=12)
    ax.set_ylabel("R_TR (min coverage)", fontsize=12)
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Cost-Resilience Tradeoff", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(outdir / "cost_resilience_tradeoff.png", dpi=150)
    plt.close(fig)
    print(f"  Saved cost_resilience_tradeoff.png")


# ── Plot 5: Per-Instance Pareto Fronts ─────────────────────────────────

def plot_pareto_per_instance(df: pd.DataFrame, outdir: Path) -> None:
    ok = df[(df["status"] == "OK") &
            df["transport_cost"].notna() &
            df["dominant_count"].notna()].copy()
    if ok.empty:
        return

    instances = sorted(ok["instance_name"].unique())
    n = len(instances)
    cols = min(n, 5)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4.5 * rows),
                             squeeze=False)

    for idx, inst in enumerate(instances):
        ax = axes[idx // cols][idx % cols]
        sub = ok[ok["instance_name"] == inst]
        pf = pareto_front(sub)

        # All points
        ax.scatter(sub["transport_cost"], sub["dominant_count"],
                   c="lightsteelblue", s=50, edgecolors="grey",
                   linewidths=0.5, zorder=2, label="dominated")

        # Pareto-optimal points + connecting line
        if not pf.empty:
            ax.plot(pf["transport_cost"], pf["dominant_count"],
                    "o-", color="steelblue", lw=2, markersize=7,
                    zorder=4, label=f"Pareto ({len(pf)} pts)")
            for _, row in pf.iterrows():
                ax.annotate(f"w={int(row['div_weight'])}",
                            (row["transport_cost"], row["dominant_count"]),
                            fontsize=7, xytext=(4, 4),
                            textcoords="offset points")

        ax.set_title(inst, fontsize=10)
        ax.set_xlabel("Transport Cost", fontsize=9)
        ax.set_ylabel("Dominant TR Count", fontsize=9)
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    # Hide unused subplots
    for idx in range(n, rows * cols):
        axes[idx // cols][idx % cols].set_visible(False)

    fig.suptitle("Per-Instance Pareto Fronts: Transport Cost vs Dominant Count",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(outdir / "pareto_per_instance.png", dpi=150)
    plt.close(fig)
    print(f"  Saved pareto_per_instance.png")


# ── Plot 6: Aggregate Pareto Front ────────────────────────────────────

def plot_pareto_aggregate(df: pd.DataFrame, outdir: Path) -> None:
    ok = df[(df["status"] == "OK") &
            df["transport_cost"].notna() &
            df["dominant_count"].notna()].copy()
    if ok.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # ── Left panel: pooled Pareto front across all instances ────────────
    ax = axes[0]
    pf_all = pareto_front(ok)

    for size in _sizes_in(ok):
        sub = ok[ok["instance_size"] == size]
        if sub.empty:
            continue
        ax.scatter(sub["transport_cost"], sub["dominant_count"],
                   c="lightsteelblue", marker=SIZE_MARKERS.get(size, "o"),
                   s=40, edgecolors="grey", linewidths=0.4,
                   zorder=2, alpha=0.6)

    if not pf_all.empty:
        ax.plot(pf_all["transport_cost"], pf_all["dominant_count"],
                "o-", color="steelblue", lw=2.5, markersize=8,
                zorder=4, label=f"Pareto ({len(pf_all)} pts)")
        for _, row in pf_all.iterrows():
            ax.annotate(f"w={int(row['div_weight'])}\n{row['instance_name']}",
                        (row["transport_cost"], row["dominant_count"]),
                        fontsize=6, xytext=(5, 3), textcoords="offset points")

    ax.set_xlabel("Transport Cost", fontsize=12)
    ax.set_ylabel("Dominant TR Count", fontsize=12)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.set_title("Pooled Pareto Front (all instances)", fontsize=12)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    # ── Right panel: mean Pareto front per size class ───────────────────
    ax = axes[1]
    for size in _sizes_in(ok):
        sub = ok[ok["instance_size"] == size]
        if sub.empty:
            continue
        # Aggregate per div_weight, then extract Pareto from the means
        means = sub.groupby("div_weight").agg(
            transport_cost=("transport_cost", "mean"),
            dominant_count=("dominant_count", "mean"),
            tc_std=("transport_cost", "std"),
            dom_std=("dominant_count", "std"),
        ).reset_index()
        pf_size = pareto_front(means)

        # All mean points as faint dots
        c = SIZE_COLORS.get(size, "#333")
        ax.scatter(means["transport_cost"], means["dominant_count"],
                   color=c, marker=SIZE_MARKERS.get(size, "o"),
                   s=40, alpha=0.3, zorder=2)

        # Pareto-optimal means connected
        if not pf_size.empty:
            ax.plot(pf_size["transport_cost"], pf_size["dominant_count"],
                    marker=SIZE_MARKERS.get(size, "o"), color=c,
                    lw=2, markersize=7, zorder=4,
                    label=f"{size} Pareto ({len(pf_size)} pts)")
            for _, row in pf_size.iterrows():
                ax.annotate(f"w={int(row['div_weight'])}",
                            (row["transport_cost"], row["dominant_count"]),
                            fontsize=7, color=c,
                            xytext=(4, 4), textcoords="offset points")

    ax.set_xlabel("Transport Cost (mean across seeds)", fontsize=12)
    ax.set_ylabel("Dominant TR Count (mean across seeds)", fontsize=12)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.set_title("Mean Pareto Front per Size Class", fontsize=12)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    fig.suptitle("Pareto Fronts: Transport Cost vs Dominant Count",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(outdir / "pareto_front.png", dpi=150)
    plt.close(fig)
    print(f"  Saved pareto_front.png")


# ── Plot 7: 2x2 Summary ──────────────────────────────────────────────

def plot_summary(df: pd.DataFrame, agg: pd.DataFrame, outdir: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # (0,0) Transport Cost vs div_weight
    ax = axes[0, 0]
    for size in _sizes_in(agg):
        sub = agg[agg["instance_size"] == size].sort_values("div_weight")
        if sub.empty:
            continue
        x = sub["div_weight"]
        y = sub["transport_cost_mean"]
        err = sub["transport_cost_std"].fillna(0)
        c = SIZE_COLORS.get(size, "#333")
        ax.plot(x, y, marker=SIZE_MARKERS.get(size, "o"), color=c,
                label=size, linewidth=2, markersize=5)
        ax.fill_between(x, y - err, y + err, color=c, alpha=0.15)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("div_weight")
    ax.set_ylabel("Transport Cost")
    ax.set_title("Transport Cost vs div_weight")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # (0,1) R_TR vs div_weight
    ax = axes[0, 1]
    for size in _sizes_in(agg):
        sub = agg[agg["instance_size"] == size].sort_values("div_weight")
        if sub.empty:
            continue
        x = sub["div_weight"]
        y = sub["r_tr_mean"]
        err = sub["r_tr_std"].fillna(0)
        c = SIZE_COLORS.get(size, "#333")
        ax.plot(x, y, marker=SIZE_MARKERS.get(size, "o"), color=c,
                label=size, linewidth=2, markersize=5)
        ax.fill_between(x, y - err, y + err, color=c, alpha=0.15)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("div_weight")
    ax.set_ylabel("R_TR")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("R_TR vs div_weight")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # (1,0) Dominant Count vs div_weight
    ax = axes[1, 0]
    for size in _sizes_in(agg):
        sub = agg[agg["instance_size"] == size].sort_values("div_weight")
        if sub.empty:
            continue
        x = sub["div_weight"]
        y = sub["dominant_count_mean"]
        err = sub["dominant_count_std"].fillna(0)
        c = SIZE_COLORS.get(size, "#333")
        ax.plot(x, y, marker=SIZE_MARKERS.get(size, "o"), color=c,
                label=size, linewidth=2, markersize=5)
        ax.fill_between(x, y - err, y + err, color=c, alpha=0.15)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("div_weight")
    ax.set_ylabel("Dominant TR Count")
    ax.set_title("Dominant Count vs div_weight")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

    # (1,1) Cost-Resilience Tradeoff
    ax = axes[1, 1]
    ok = df[(df["status"] == "OK") &
            df["transport_cost"].notna() &
            df["r_tr"].notna()].copy()
    sc = None
    if not ok.empty:
        sizes_present = [s for s in SIZE_ORDER if s in ok["instance_size"].values]
        if not sizes_present:
            sizes_present = sorted(ok["instance_size"].unique())
        for size in sizes_present:
            sub = ok[ok["instance_size"] == size]
            if sub.empty:
                continue
            marker = SIZE_MARKERS.get(size, "o")
            sc = ax.scatter(
                sub["transport_cost"], sub["r_tr"],
                c=sub["div_weight"], cmap="viridis",
                marker=marker, s=40, edgecolors="k", linewidths=0.4,
                label=size, vmin=ok["div_weight"].min(), vmax=ok["div_weight"].max(),
            )
        if sc is not None:
            fig.colorbar(sc, ax=ax, label="div_weight")
    ax.set_xlabel("Transport Cost")
    ax.set_ylabel("R_TR")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Cost-Resilience Tradeoff")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(outdir / "experiment_summary.png", dpi=150)
    plt.close(fig)
    print(f"  Saved experiment_summary.png")


# ── Summary stats CSV ───────────────────────────────────────────────────

def write_summary_stats(agg: pd.DataFrame, outdir: Path) -> None:
    out_path = outdir / "summary_stats.csv"
    agg.to_csv(out_path, index=False)
    print(f"  Saved summary_stats.csv")


# ── CLI + main ───────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot div_weight sweep results")
    p.add_argument("--input", "-i", type=Path,
                   default=Path("results/div_weight_sweep.csv"),
                   help="Input CSV from run_experiment.py")
    p.add_argument("--output-dir", type=Path,
                   default=Path("results/plots"),
                   help="Directory for output plots")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found. Run run_experiment.py first.")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {args.input}...")
    df = load_and_prepare(args.input)
    print(f"  {len(df)} rows, {df['instance_name'].nunique()} instances, "
          f"{df['div_weight'].nunique()} weights")

    ok = df[df["status"] == "OK"]
    print(f"  {len(ok)} OK rows, {len(df) - len(ok)} errors/UNSAT")

    agg = aggregate(ok)

    print(f"\nGenerating plots → {args.output_dir}/")
    plot_cost_vs_weight(agg, args.output_dir)
    plot_rtr_vs_weight(agg, args.output_dir)
    plot_dominant_vs_weight(agg, args.output_dir)
    plot_cost_resilience(df, args.output_dir)
    plot_pareto_per_instance(df, args.output_dir)
    plot_pareto_aggregate(df, args.output_dir)
    plot_summary(df, agg, args.output_dir)
    write_summary_stats(agg, args.output_dir)

    print(f"\nDone. All outputs in {args.output_dir}/")


if __name__ == "__main__":
    main()
