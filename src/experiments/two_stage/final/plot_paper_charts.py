#!/usr/bin/env python3
"""
Paper charts for the medium N=3 experimental analysis.

Usage:
    python plot_paper_charts.py
    python plot_paper_charts.py --csv results/some_other.csv
    python plot_paper_charts.py --out results/plots/custom_dir
"""

import argparse
import csv
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────
CSV_PATH = Path("results/medium_n3_full.csv")
OUT_DIR = Path("results/plots/paper")

MARKER_SIZE = 70
LINE_WIDTH = 2
FONT_SIZE = 12
TITLE_SIZE = 14

matplotlib.rcParams.update({
    "font.size": FONT_SIZE,
    "axes.titlesize": TITLE_SIZE,
    "axes.labelsize": FONT_SIZE,
    "legend.fontsize": 10,
    "figure.dpi": 150,
})

# Colours
C_GREEN = "#2ca02c"
C_RED = "#d62728"
C_BLUE = "#1f77b4"
C_ORANGE = "#ff7f0e"


# ── Data loading ─────────────────────────────────────────────────────

def load(csv_path: Path) -> list[dict]:
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ["div_weight", "nominal_cost", "dominant_count",
                   "mono_count", "concentrated_count"]:
            r[k] = int(r[k]) if r.get(k) else None
        for k in ["r_tr", "r_1"]:
            r[k] = float(r[k]) if r.get(k) else None
        for k in ["exposure_count", "s1_dispatch_cost",
                   "s2_dispatch_cost", "cost_saving"]:
            r[k] = int(r[k]) if r.get(k) and r[k] != "" else None
    return [r for r in rows if r["status"] == "OK"]


def get(rows, s2="off_off"):
    return sorted([r for r in rows if r["s2_config"] == s2],
                  key=lambda r: r["div_weight"])


# ── Chart 1: R_TR vs S1 Dispatch Cost ────────────────────────────────

def plot_rtr_vs_s1_cost(rows, out_dir):
    fig, ax = plt.subplots(figsize=(8, 5))
    data = get(rows, "off_off")

    costs = [r["s1_dispatch_cost"] for r in data]
    rtrs = [r["r_tr"] for r in data]
    ws = [r["div_weight"] for r in data]

    ax.scatter(costs, rtrs, c=C_GREEN, s=MARKER_SIZE, zorder=5,
               edgecolors="black", linewidth=0.5)

    for c, rtr, w in zip(costs, rtrs, ws):
        ax.annotate(f"w={w}", (c, rtr), textcoords="offset points",
                    xytext=(8, 0), fontsize=9, color="#555")

    ax.set_xlabel("Stage 1 Dispatch Cost")
    ax.set_ylabel("$R_{TR}$")
    ax.set_title("$R_{TR}$ vs Stage 1 Dispatch Cost")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "rtr_vs_s1_cost.png", bbox_inches="tight")
    plt.close()
    print("  rtr_vs_s1_cost.png")



# ── Chart 3: Cost vs R_TR Pareto ─────────────────────────────────────

def plot_cost_vs_rtr_pareto(rows, out_dir):
    fig, ax = plt.subplots(figsize=(8, 5))
    data = get(rows, "off_off")

    costs = [r["s1_dispatch_cost"] for r in data]
    rtrs = [r["r_tr"] for r in data]
    exps = [r["exposure_count"] for r in data]
    ws = [r["div_weight"] for r in data]

    # Points coloured by exposure count
    scatter = ax.scatter(costs, rtrs, c=exps, cmap="RdYlGn_r",
                         s=MARKER_SIZE, zorder=5,
                         edgecolors="black", linewidth=0.5,
                         vmin=0, vmax=max(e for e in exps if e is not None))
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("High Exposure Count")

    for c, rtr, w in zip(costs, rtrs, ws):
        ax.annotate(f"w={w}", (c, rtr), textcoords="offset points",
                    xytext=(8, 0), fontsize=9, color="#555")

    # Pareto front (minimise cost, maximise R_TR)
    pareto = []
    best_rtr = -1
    for r in sorted(data, key=lambda r: r["s1_dispatch_cost"]):
        if r["r_tr"] > best_rtr:
            pareto.append(r)
            best_rtr = r["r_tr"]
    if len(pareto) > 1:
        ax.plot([r["s1_dispatch_cost"] for r in pareto],
                [r["r_tr"] for r in pareto],
                "k--", alpha=0.4, linewidth=1.5, label="Pareto front")

    ax.set_xlabel("Stage 1 Dispatch Cost")
    ax.set_ylabel("$R_{TR}$")
    ax.set_title("Cost vs $R_{TR}$ Pareto Front")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "cost_vs_rtr_pareto.png", bbox_inches="tight")
    plt.close()
    print("  cost_vs_rtr_pareto.png")


# ── Chart 4: S1 vs S2 Dispatch Cost Comparison ───────────────────────

def plot_s1_vs_s2_cost(rows, out_dir):
    fig, ax = plt.subplots(figsize=(9, 7))

    # Use 'both' config to show the full effect of Stage 2
    data = get(rows, "both")
    weights = [r["div_weight"] for r in data]
    s1_costs = [r["s1_dispatch_cost"] for r in data]
    s2_costs = [r["s2_dispatch_cost"] for r in data]

    x = np.arange(len(weights))
    width = 0.35

    bars1 = ax.bar(x - width / 2, s1_costs, width, label="Stage 1 (planned)",
                   color="#ff7f0e", edgecolor="black", linewidth=0.5)
    bars2 = ax.bar(x + width / 2, s2_costs, width, label="Stage 2 (actual)",
                   color="#2ca02c", edgecolor="black", linewidth=0.5)

    # Annotate savings on top
    for i, (s1, s2) in enumerate(zip(s1_costs, s2_costs)):
        saving = s1 - s2
        if saving > 0:
            pct = saving / s1 * 100
            ax.annotate(f"-{saving}\n({pct:.0f}%)",
                        (x[i], max(s1, s2)),
                        textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=8, color="#d62728")

    ax.set_xlabel("Stage 1 Diversification Weight")
    ax.set_ylabel("Dispatch Cost")
    ax.set_title("Stage 1 Planned vs Stage 2 Actual Dispatch Cost (both constraints)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"w={w}" for w in weights])
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_dir / "s1_vs_s2_cost.png", bbox_inches="tight")
    plt.close()
    print("  s1_vs_s2_cost.png")


# ── Chart 5: R_1 by S2 Configuration ─────────────────────────────────

def plot_r1_by_config(rows, out_dir):
    configs = ["off_off", "hetero", "conc", "both"]
    labels = ["Off/Off", "Hetero", "Conc", "Both"]
    colors = ["#bdbdbd", "#74c0fc", "#ffa94d", "#69db7c"]

    fig, ax = plt.subplots(figsize=(10, 6))

    weights = sorted(set(r["div_weight"] for r in rows))
    x = np.arange(len(weights))
    width = 0.2

    for i, (cfg, label, color) in enumerate(zip(configs, labels, colors)):
        data = get(rows, cfg)
        r1s = [r["r_1"] for r in data]
        bars = ax.bar(x + i * width, r1s, width, label=label,
                      color=color, edgecolor="black", linewidth=0.5)

    ax.set_xlabel("Stage 1 Diversification Weight")
    ax.set_ylabel("$R_1$")
    ax.set_title("$R_1$ by Stage 2 Configuration across Weights")
    ax.set_xticks(x + 1.5 * width)
    ax.set_xticklabels([f"w={w}" for w in weights])
    ax.set_ylim(0.7, 0.92)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_dir / "r1_by_config.png", bbox_inches="tight")
    plt.close()
    print("  r1_by_config.png")


# ── Main ─────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Generate paper charts")
    p.add_argument("--csv", type=Path, default=CSV_PATH,
                   help=f"Input CSV (default: {CSV_PATH})")
    p.add_argument("--out", type=Path, default=OUT_DIR,
                   help=f"Output directory (default: {OUT_DIR})")
    return p.parse_args()


def main():
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows = load(args.csv)
    print(f"Loaded {len(rows)} OK rows from {args.csv}\n")

    plot_rtr_vs_s1_cost(rows, args.out)
    plot_cost_vs_rtr_pareto(rows, args.out)
    plot_s1_vs_s2_cost(rows, args.out)
    plot_r1_by_config(rows, args.out)

    print(f"\nAll plots saved to {args.out}/")


if __name__ == "__main__":
    main()
