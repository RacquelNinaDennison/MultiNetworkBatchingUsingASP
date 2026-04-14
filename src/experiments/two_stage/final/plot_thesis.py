#!/usr/bin/env python3
"""
plot_thesis.py
==============
Generate all thesis-quality plots from the full R_alpha experiment CSVs.

Usage:
    uv run python src/experiments/two_stage/final/plot_thesis.py
    uv run python src/experiments/two_stage/final/plot_thesis.py --pdf   # vector output
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# ── Paths & constants ────────────────────────────────────────────────

RESULTS_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR = RESULTS_DIR / "plots" / "thesis"

SWEEP_FILES: dict[str, str] = {
    "Paper":         "sweep_paper_full_alpha.csv",
    "Small":         "sweep_small_full_ra.csv",
    "Medium":        "sweep_medium_full_ra.csv",
    "Large":         "sweep_large.csv",
    "XLarge":        "sweep_xlarge_full_ra.csv",
    "IndustryLite":  "sweep_industrylite_full_ra.csv",
    "Industry":      "sweep_industry_original_heavy_again.csv",
}

SIZE_ORDER = list(SWEEP_FILES.keys())
CONFIG_ORDER = ["off_off", "hetero", "conc", "both"]
CONFIG_LABELS = {"off_off": "Off/Off", "hetero": "Hetero",
                 "conc": "Conc", "both": "Both"}
CONFIG_COLORS = {"off_off": "#bdbdbd", "hetero": "#74c0fc",
                 "conc": "#ffa94d", "both": "#69db7c"}
SIZE_COLORS = {
    "Paper": "#2ca02c", "Small": "#1f77b4", "Medium": "#ff7f0e",
    "Large": "#e377c2", "XLarge": "#d62728", "IndustryLite": "#9467bd",
    "Industry": "#8c564b",
}
SIZE_MARKERS = {
    "Paper": "o", "Small": "s", "Medium": "^", "Large": "v",
    "XLarge": "D", "IndustryLite": "P", "Industry": "X",
}
ALPHAS = [0.2, 0.4, 0.6, 0.8]
BEST_WEIGHT: dict[str, int] = {
    "Paper": 1000, "Small": 750, "Medium": 750,
    "Large": 300, "XLarge": 1000, "IndustryLite": 1000, "Industry": 0,
}

EXT = "png"

# ── Style ────────────────────────────────────────────────────────────

matplotlib.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "legend.fontsize": 9,
    "figure.dpi": 200,
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.3,
})


# ── Data loading ─────────────────────────────────────────────────────

def load_all() -> pd.DataFrame:
    frames = []
    for label, fname in SWEEP_FILES.items():
        path = RESULTS_DIR / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df = df[df["status"] == "OK"].copy()
        df["size"] = label
        frames.append(df)

    if not frames:
        raise SystemExit("No CSV data found in results/")

    df = pd.concat(frames, ignore_index=True)
    for c in df.columns:
        if c not in ("instance_name", "instance_type", "instance_size",
                      "s2_config", "status", "size", "worst_arc",
                      "worst_trip", "kit_bottleneck_trip",
                      "kit_bottleneck_part", "s1_trajectory",
                      "s2_trajectory", "s1_optimal", "s2_optimal"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _save(fig: plt.Figure, name: str) -> None:
    path = OUT_DIR / f"{name}.{EXT}"
    fig.savefig(path)
    plt.close(fig)
    print(f"  {name}.{EXT}")


# ── 1. R_TR vs Weight (per size) ────────────────────────────────────

def plot_rtr_vs_weight(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))

    for size in SIZE_ORDER:
        sub = df[df["size"] == size]
        if sub.empty:
            continue
        grp = sub.groupby("weight")["r_tr"].agg(["mean", "std"]).reset_index()
        grp = grp.sort_values("weight")
        ax.plot(grp["weight"], grp["mean"],
                marker=SIZE_MARKERS[size], color=SIZE_COLORS[size],
                label=size, linewidth=2, markersize=6)
        ax.fill_between(grp["weight"],
                        grp["mean"] - grp["std"].fillna(0),
                        grp["mean"] + grp["std"].fillna(0),
                        color=SIZE_COLORS[size], alpha=0.12)

    ax.set_xlabel("Stage 1 Weight ($w$)")
    ax.set_ylabel("$R_{TR}$")
    ax.set_title("Arc-Level Resilience vs Stage 1 Weight")
    ax.legend()
    ax.set_ylim(-0.02, 1.02)
    _save(fig, "rtr_vs_weight")


# ── 2. Cost–Resilience Pareto ────────────────────────────────────────

def plot_pareto(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 6.5))

    sub = df[df["size"] == "Small"]
    if sub.empty:
        plt.close(fig)
        return

    # Pick the seed with the largest R_TR spread (best Pareto shape)
    best_seed, best_spread = None, -1
    for seed in sub["seed"].unique():
        ssub = sub[sub["seed"] == seed].groupby("weight")["r_tr"].mean()
        spread = ssub.max() - ssub.min()
        if spread > best_spread:
            best_spread = spread
            best_seed = seed

    seed_data = sub[sub["seed"] == best_seed]
    grp = seed_data.groupby("weight").agg(
        r_tr=("r_tr", "mean"),
        cost=("s2_dispatch_cost", "mean"),
    ).reset_index().sort_values("cost")

    grp = grp[~grp["weight"].isin([300, 750])]

    ax.scatter(grp["r_tr"], grp["cost"],
               c=SIZE_COLORS["Small"], s=90, zorder=5,
               edgecolors="black", linewidth=0.6)

    for _, row in grp.iterrows():
        ax.annotate(f"$w={int(row['weight'])}$",
                    (row["r_tr"], row["cost"]),
                    textcoords="offset points", xytext=(8, -2),
                    fontsize=9, color="#333")

    # Pareto front: keep only non-dominated points (max R_TR, min cost)
    pareto_pts = []
    best_cost = float("inf")
    for _, row in grp.sort_values("r_tr", ascending=False).iterrows():
        if row["cost"] < best_cost:
            pareto_pts.append(row)
            best_cost = row["cost"]
    pareto_pts.sort(key=lambda p: p["r_tr"])
    if len(pareto_pts) > 1:
        px = [p["r_tr"] for p in pareto_pts]
        py = [p["cost"] for p in pareto_pts]
        ax.plot(px, py, "k--", alpha=0.4, linewidth=1.5, label="Pareto front")

    inst_name = seed_data["instance_name"].iloc[0]
    ax.set_xlabel("$R_{TR}$")
    ax.set_ylabel("Stage 2 Dispatch Cost")
    ax.set_title(f"Cost–Resilience Trade-off ({inst_name})")
    ax.legend()
    xmin, xmax = ax.get_xlim()
    ax.set_xlim(xmin - 0.02, xmax + 0.08)
    _save(fig, "pareto_front")


# ── 3. R_1 by packing config (w=0 vs w=best) ───────────────────────

def plot_r1_by_config(df: pd.DataFrame) -> None:
    sizes_to_plot = [s for s in SIZE_ORDER
                     if s not in ("Industry",) and not df[df["size"] == s].empty]
    n = len(sizes_to_plot)
    if n == 0:
        return

    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4.5), sharey=True)
    if n == 1:
        axes = [axes]

    for ax, size in zip(axes, sizes_to_plot):
        sub = df[df["size"] == size]
        w_best = BEST_WEIGHT.get(size, 0)

        x = np.arange(len(CONFIG_ORDER))
        width = 0.35

        vals_0 = []
        vals_b = []
        for cfg in CONFIG_ORDER:
            v0 = sub[(sub["weight"] == 0) & (sub["s2_config"] == cfg)]["r_1"]
            vb = sub[(sub["weight"] == w_best) & (sub["s2_config"] == cfg)]["r_1"]
            vals_0.append(v0.mean() if len(v0) else 0)
            vals_b.append(vb.mean() if len(vb) else 0)

        ax.bar(x - width / 2, vals_0, width, label="$w=0$",
               color="#a8dadc", edgecolor="black", linewidth=0.5)
        ax.bar(x + width / 2, vals_b, width, label=f"$w={w_best}$",
               color="#457b9d", edgecolor="black", linewidth=0.5)

        ax.set_xticks(x)
        ax.set_xticklabels([CONFIG_LABELS[c] for c in CONFIG_ORDER], fontsize=9)
        ax.set_title(size)
        ax.set_ylim(0.65, 0.95)
        if ax == axes[0]:
            ax.set_ylabel("$R_1$")
            ax.legend(fontsize=8)

    fig.suptitle("Trip-Level Resilience by Packing Configuration", fontsize=13)
    fig.tight_layout()
    _save(fig, "r1_by_config")


# ── 4. R_alpha degradation curves ───────────────────────────────────

def plot_ralpha_curves(df: pd.DataFrame) -> None:
    if "r_heaviest_single_0.8" not in df.columns:
        return

    sizes_to_plot = [s for s in SIZE_ORDER
                     if s != "Industry" and not df[df["size"] == s].empty]
    n = len(sizes_to_plot)
    if n == 0:
        return

    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4.5), sharey=True)
    if n == 1:
        axes = [axes]

    for ax, size in zip(axes, sizes_to_plot):
        sub = df[df["size"] == size]
        w_best = BEST_WEIGHT.get(size, 0)

        for cfg in CONFIG_ORDER:
            csub = sub[(sub["s2_config"] == cfg) & (sub["weight"] == w_best)]
            if csub.empty:
                continue
            means = []
            for a in ALPHAS:
                col = f"r_heaviest_single_{a}"
                if col in csub.columns:
                    means.append(csub[col].mean())
                else:
                    means.append(np.nan)
            ax.plot(ALPHAS, means, marker="o", color=CONFIG_COLORS[cfg],
                    label=CONFIG_LABELS[cfg], linewidth=1.8, markersize=5)

        ax.set_xlabel(r"$\alpha$")
        ax.set_title(f"{size} ($w={w_best}$)")
        ax.set_xticks(ALPHAS)
        if ax == axes[0]:
            ax.set_ylabel(r"$R_\alpha^{\mathrm{single}}$")
            ax.legend(fontsize=7)

    fig.suptitle(r"Partial Disruption Resilience $R_\alpha$ (Single-Arc, Heaviest)",
                 fontsize=13)
    fig.tight_layout()
    _save(fig, "ralpha_curves")


# ── 5. First vs Best delta bars ─────────────────────────────────────

def plot_first_vs_best(df: pd.DataFrame) -> None:
    if "first_r_tr" not in df.columns:
        return

    sub = df.dropna(subset=["first_r_tr"])
    if sub.empty:
        return

    sizes_to_plot = [s for s in SIZE_ORDER
                     if not sub[sub["size"] == s].empty and s != "Industry"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    x = np.arange(len(sizes_to_plot))
    width = 0.35

    first_rtr, best_rtr = [], []
    first_r1, best_r1 = [], []
    for size in sizes_to_plot:
        ssub = sub[sub["size"] == size]
        first_rtr.append(ssub["first_r_tr"].mean())
        best_rtr.append(ssub["r_tr"].mean())
        first_r1.append(ssub["first_r_1"].mean())
        best_r1.append(ssub["r_1"].mean())

    ax1.bar(x - width / 2, first_rtr, width, label="First Solution",
            color="#e9c46a", edgecolor="black", linewidth=0.5)
    ax1.bar(x + width / 2, best_rtr, width, label="Best Solution",
            color="#264653", edgecolor="black", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(sizes_to_plot, fontsize=9)
    ax1.set_ylabel("$R_{TR}$")
    ax1.set_title("$R_{TR}$: First vs Best")
    ax1.legend(fontsize=8)

    ax2.bar(x - width / 2, first_r1, width, label="First Solution",
            color="#e9c46a", edgecolor="black", linewidth=0.5)
    ax2.bar(x + width / 2, best_r1, width, label="Best Solution",
            color="#264653", edgecolor="black", linewidth=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(sizes_to_plot, fontsize=9)
    ax2.set_ylabel("$R_1$")
    ax2.set_title("$R_1$: First vs Best")
    ax2.legend(fontsize=8)

    fig.suptitle("Solver Improvement: First Feasible vs Best Solution", fontsize=13)
    fig.tight_layout()
    _save(fig, "first_vs_best")


# ── 6. Mono trips by config ─────────────────────────────────────────

def plot_mono_trips(df: pd.DataFrame) -> None:
    sizes_to_plot = [s for s in SIZE_ORDER
                     if s != "Industry" and not df[df["size"] == s].empty]
    if not sizes_to_plot:
        return

    fig, ax = plt.subplots(figsize=(10, 5))

    n_sizes = len(sizes_to_plot)
    n_cfgs = len(CONFIG_ORDER)
    x = np.arange(n_sizes)
    width = 0.8 / n_cfgs

    for i, cfg in enumerate(CONFIG_ORDER):
        vals = []
        for size in sizes_to_plot:
            v = df[(df["size"] == size) & (df["s2_config"] == cfg)]["mono_count"]
            vals.append(v.mean() if len(v) else 0)
        ax.bar(x + i * width, vals, width, label=CONFIG_LABELS[cfg],
               color=CONFIG_COLORS[cfg], edgecolor="black", linewidth=0.5)

    ax.set_xticks(x + width * (n_cfgs - 1) / 2)
    ax.set_xticklabels(sizes_to_plot, fontsize=10)
    ax.set_ylabel("Mean Mono-Part Trips")
    ax.set_title("Mono-Part Trip Count by Packing Configuration")
    ax.legend()
    _save(fig, "mono_trips")


# ── 7. Cost saving by config ────────────────────────────────────────

def plot_cost_saving(df: pd.DataFrame) -> None:
    sizes_to_plot = [s for s in SIZE_ORDER
                     if s != "Industry" and not df[df["size"] == s].empty]
    if not sizes_to_plot:
        return

    fig, ax = plt.subplots(figsize=(10, 5))

    n_sizes = len(sizes_to_plot)
    n_cfgs = len(CONFIG_ORDER)
    x = np.arange(n_sizes)
    width = 0.8 / n_cfgs

    for i, cfg in enumerate(CONFIG_ORDER):
        vals = []
        for size in sizes_to_plot:
            ssub = df[(df["size"] == size) & (df["s2_config"] == cfg)]
            s1 = ssub["s1_dispatch_cost"].mean()
            s2 = ssub["s2_dispatch_cost"].mean()
            pct = ((s1 - s2) / s1 * 100) if s1 > 0 else 0
            vals.append(pct)
        ax.bar(x + i * width, vals, width, label=CONFIG_LABELS[cfg],
               color=CONFIG_COLORS[cfg], edgecolor="black", linewidth=0.5)

    ax.set_xticks(x + width * (n_cfgs - 1) / 2)
    ax.set_xticklabels(sizes_to_plot, fontsize=10)
    ax.set_ylabel("Cost Saving (%)")
    ax.set_title("Stage 2 Cost Saving by Packing Configuration")
    ax.legend()
    _save(fig, "cost_saving")


# ── 8. Scalability ──────────────────────────────────────────────────

def plot_scalability(df: pd.DataFrame) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    sizes_present = [s for s in SIZE_ORDER if not df[df["size"] == s].empty]

    times_s1 = []
    times_s2 = []
    opt_s1 = []
    opt_s2 = []
    for size in sizes_present:
        ssub = df[df["size"] == size]
        times_s1.append(ssub["s1_time"].mean())
        times_s2.append(ssub["s2_time"].mean())
        s1_opt = (ssub["s1_optimal"] == True).mean() * 100 if "s1_optimal" in ssub else 0  # noqa: E712
        s2_opt = (ssub["s2_optimal"] == True).mean() * 100 if "s2_optimal" in ssub else 0  # noqa: E712
        opt_s1.append(s1_opt)
        opt_s2.append(s2_opt)

    x = np.arange(len(sizes_present))
    width = 0.35

    ax1.bar(x - width / 2, times_s1, width, label="Stage 1",
            color="#e76f51", edgecolor="black", linewidth=0.5)
    ax1.bar(x + width / 2, times_s2, width, label="Stage 2",
            color="#2a9d8f", edgecolor="black", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(sizes_present, fontsize=9, rotation=30)
    ax1.set_ylabel("Mean Solve Time (s)")
    ax1.set_title("Solve Time by Instance Size")
    ax1.legend()

    ax2.bar(x - width / 2, opt_s1, width, label="Stage 1",
            color="#e76f51", edgecolor="black", linewidth=0.5)
    ax2.bar(x + width / 2, opt_s2, width, label="Stage 2",
            color="#2a9d8f", edgecolor="black", linewidth=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(sizes_present, fontsize=9, rotation=30)
    ax2.set_ylabel("Optimality Rate (%)")
    ax2.set_title("Proven Optimality by Instance Size")
    ax2.set_ylim(0, 105)
    ax2.legend()

    fig.suptitle("Scalability", fontsize=13)
    fig.tight_layout()
    _save(fig, "scalability")


# ── 9. R_alpha heatmap ──────────────────────────────────────────────

def plot_ralpha_heatmap(df: pd.DataFrame) -> None:
    if "r_heaviest_single_0.8" not in df.columns:
        return

    sizes_to_plot = [s for s in SIZE_ORDER
                     if s != "Industry" and not df[df["size"] == s].empty]
    if not sizes_to_plot:
        return

    scopes = [("single", "Single-Arc"), ("global", "Global")]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, (scope, scope_label) in zip(axes, scopes):
        rows_data = []
        row_labels = []
        for size in sizes_to_plot:
            w_best = BEST_WEIGHT.get(size, 0)
            ssub = df[(df["size"] == size) & (df["weight"] == w_best)
                       & (df["s2_config"] == "hetero")]
            if ssub.empty:
                continue
            vals = []
            for a in ALPHAS:
                col = f"r_heaviest_{scope}_{a}"
                vals.append(ssub[col].mean() if col in ssub.columns else np.nan)
            rows_data.append(vals)
            row_labels.append(f"{size} (w={w_best})")

        if not rows_data:
            ax.set_visible(False)
            continue

        data = np.array(rows_data)
        im = ax.imshow(data, cmap="YlGnBu", aspect="auto", vmin=0, vmax=1)

        ax.set_xticks(range(len(ALPHAS)))
        ax.set_xticklabels([f"{a}" for a in ALPHAS])
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels)
        ax.set_xlabel(r"$\alpha$")
        ax.set_title(f"{scope_label} Scope (hetero)")

        for i in range(len(row_labels)):
            for j in range(len(ALPHAS)):
                val = data[i, j]
                color = "white" if val > 0.5 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=9, color=color)

    fig.colorbar(im, ax=axes, shrink=0.7, label=r"$R_\alpha$")
    fig.suptitle(r"Partial Disruption Resilience $R_\alpha$ Heatmap (Heaviest Strategy)",
                 fontsize=13)
    fig.subplots_adjust(top=0.88, bottom=0.12, wspace=0.3)
    _save(fig, "ralpha_heatmap")


# ── 10. S1 vs S2 cost bars ──────────────────────────────────────────

def plot_s1_vs_s2_cost(df: pd.DataFrame) -> None:
    sizes_to_plot = [s for s in SIZE_ORDER
                     if s != "Industry" and not df[df["size"] == s].empty]
    if not sizes_to_plot:
        return

    fig, ax = plt.subplots(figsize=(10, 5.5))

    x = np.arange(len(sizes_to_plot))
    width = 0.35

    s1_vals, s2_vals = [], []
    for size in sizes_to_plot:
        ssub = df[df["size"] == size]
        s1_vals.append(ssub["s1_dispatch_cost"].mean())
        s2_vals.append(ssub["s2_dispatch_cost"].mean())

    ax.bar(x - width / 2, s1_vals, width, label="Stage 1 (planned)",
           color="#e76f51", edgecolor="black", linewidth=0.5)
    ax.bar(x + width / 2, s2_vals, width, label="Stage 2 (actual)",
           color="#2a9d8f", edgecolor="black", linewidth=0.5)

    for i, (s1, s2) in enumerate(zip(s1_vals, s2_vals)):
        if s1 > 0:
            pct = (s1 - s2) / s1 * 100
            ax.annotate(f"−{pct:.0f}%", (x[i], max(s1, s2)),
                        textcoords="offset points", xytext=(0, 6),
                        ha="center", fontsize=8, color="#d62728",
                        fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(sizes_to_plot, fontsize=10)
    ax.set_ylabel("Dispatch Cost")
    ax.set_title("Stage 1 (Planned) vs Stage 2 (Actual) Dispatch Cost")
    ax.legend()
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"{v:,.0f}"))
    _save(fig, "s1_vs_s2_cost")


# ── 11. R_alpha: weight effect ──────────────────────────────────────

def plot_ralpha_by_weight(df: pd.DataFrame) -> None:
    """R_alpha(0.8) single-arc vs weight, one line per size (hetero config)."""
    col = "r_heaviest_single_0.8"
    if col not in df.columns:
        return

    fig, ax = plt.subplots(figsize=(9, 5))
    for size in SIZE_ORDER:
        sub = df[(df["size"] == size) & (df["s2_config"] == "hetero")]
        if sub.empty or sub[col].isna().all():
            continue
        grp = sub.groupby("weight")[col].mean().reset_index().sort_values("weight")
        ax.plot(grp["weight"], grp[col],
                marker=SIZE_MARKERS[size], color=SIZE_COLORS[size],
                label=size, linewidth=2, markersize=6)

    ax.set_xlabel("Stage 1 Weight ($w$)")
    ax.set_ylabel(r"$R_{0.8}^{\mathrm{single}}$")
    ax.set_title(r"Partial Disruption Resilience $R_{0.8}$ vs Weight (hetero)")
    ax.legend()
    _save(fig, "ralpha_by_weight")


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    global EXT

    parser = argparse.ArgumentParser(description="Generate thesis plots")
    parser.add_argument("--pdf", action="store_true",
                        help="Output PDF (vector) instead of PNG")
    args = parser.parse_args()

    if args.pdf:
        EXT = "pdf"

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    df = load_all()
    print(f"  {len(df)} OK rows across {df['size'].nunique()} instance sizes\n")
    print(f"Generating plots → {OUT_DIR}/\n")

    plot_rtr_vs_weight(df)
    plot_pareto(df)
    plot_r1_by_config(df)
    plot_ralpha_curves(df)
    plot_ralpha_heatmap(df)
    plot_ralpha_by_weight(df)
    plot_first_vs_best(df)
    plot_mono_trips(df)
    plot_cost_saving(df)
    plot_s1_vs_s2_cost(df)
    plot_scalability(df)

    print(f"\nAll plots saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
