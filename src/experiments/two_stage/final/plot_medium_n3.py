#!/usr/bin/env python3
"""Plot analysis charts for layered_medium_seed1 with N=3 exposure proxy."""

import csv
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from pathlib import Path

matplotlib.rcParams.update({
    "font.size": 11, "axes.titlesize": 13, "axes.labelsize": 12,
    "legend.fontsize": 10, "figure.dpi": 150,
})

CSV_PATH = Path("results/medium_n3_full.csv")
OUT_DIR = Path("results/plots/medium_n3")


def load():
    with open(CSV_PATH) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ["div_weight", "nominal_cost", "dominant_count", "mono_count",
                   "concentrated_count"]:
            r[k] = int(r[k]) if r.get(k) else None
        for k in ["r_tr", "r_1"]:
            r[k] = float(r[k]) if r.get(k) else None
        for k in ["exposure_count", "s1_dispatch_cost", "s2_dispatch_cost", "cost_saving"]:
            r[k] = int(r[k]) if r.get(k) and r[k] != "" else None
    return [r for r in rows if r["status"] == "OK"]


def get(rows, s2="off_off"):
    return sorted([r for r in rows if r["s2_config"] == s2],
                  key=lambda r: r["div_weight"])


# ═══════════════════════════════════════════════════════════════════
# Chart 1: R_TR vs Weight (N=3)
# ═══════════════════════════════════════════════════════════════════

def plot_rtr_vs_weight(rows):
    fig, ax = plt.subplots(figsize=(8, 5))
    data = get(rows, "off_off")  # R_TR same across s2 configs

    ws = [r["div_weight"] for r in data]
    rtrs = [r["r_tr"] for r in data]
    exps = [r["exposure_count"] for r in data]

    ax.plot(ws, rtrs, "o-", color="#2ca02c", linewidth=2, markersize=8, label="$R_{TR}$")

    # Annotate exposure count
    for w, rtr, exp in zip(ws, rtrs, exps):
        ax.annotate(f"exp={exp}", (w, rtr), textcoords="offset points",
                    xytext=(0, 12), ha="center", fontsize=8, color="#666")

    # Mark the exposure=0 boundary
    zero_w = min(w for w, e in zip(ws, exps) if e == 0)
    ax.axvline(x=zero_w, color="red", linestyle="--", alpha=0.5,
               label=f"Exposure = 0 (w={zero_w})")

    ax.set_xlabel("Stage 1 Diversification Weight")
    ax.set_ylabel("$R_{TR}$")
    ax.set_title("Transport Resilience vs Weight (N=3, max 33% per arc-TR)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0.5, 0.75)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "1_rtr_vs_weight.png", bbox_inches="tight")
    plt.close()
    print("  1_rtr_vs_weight.png")


# ═══════════════════════════════════════════════════════════════════
# Chart 2: R_TR vs Dispatch Cost (N=3)
# ═══════════════════════════════════════════════════════════════════

def plot_rtr_vs_cost(rows):
    fig, ax = plt.subplots(figsize=(8, 5))
    data = get(rows, "off_off")

    costs = [r["s1_dispatch_cost"] for r in data]
    rtrs = [r["r_tr"] for r in data]
    ws = [r["div_weight"] for r in data]

    ax.scatter(costs, rtrs, c="#2ca02c", s=80, zorder=5, edgecolors="black", linewidth=0.5)

    for c, rtr, w in zip(costs, rtrs, ws):
        ax.annotate(f"w={w}", (c, rtr), textcoords="offset points",
                    xytext=(8, 0), fontsize=8, color="#666")

    # Pareto front
    pareto = []
    best_rtr = -1
    for r in sorted(data, key=lambda r: r["s1_dispatch_cost"]):
        if r["r_tr"] > best_rtr:
            pareto.append(r)
            best_rtr = r["r_tr"]
    if pareto:
        ax.plot([r["s1_dispatch_cost"] for r in pareto],
                [r["r_tr"] for r in pareto],
                "r--", alpha=0.6, linewidth=1.5, label="Pareto front")

    ax.set_xlabel("Stage 1 Dispatch Cost")
    ax.set_ylabel("$R_{TR}$")
    ax.set_title("Cost-Resilience Tradeoff (N=3)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "2_rtr_vs_cost.png", bbox_inches="tight")
    plt.close()
    print("  2_rtr_vs_cost.png")


# ═══════════════════════════════════════════════════════════════════
# Chart 3: R_1 by S2 config (4 subplots)
# ═══════════════════════════════════════════════════════════════════

def plot_r1_by_config(rows):
    configs = ["off_off", "hetero", "conc", "both"]
    titles = ["No S2 constraints", "Heterogeneity only",
              "Concentration only", "Both constraints"]
    colors = ["#bdbdbd", "#74c0fc", "#ffa94d", "#69db7c"]

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharey=True)

    for idx, (cfg, title, color) in enumerate(zip(configs, titles, colors)):
        ax = axes[idx // 2][idx % 2]
        data = get(rows, cfg)

        ws = [r["div_weight"] for r in data]
        r1s = [r["r_1"] for r in data]
        monos = [r["mono_count"] for r in data]
        concs = [r["concentrated_count"] for r in data]

        ax.bar(ws, r1s, width=35, color=color, edgecolor="black", linewidth=0.5)

        # Annotate mono/conc
        for w, r1, m, c in zip(ws, r1s, monos, concs):
            ax.annotate(f"m={m}\nc={c}", (w, r1), textcoords="offset points",
                        xytext=(0, 5), ha="center", fontsize=7, color="#444")

        ax.set_title(title)
        ax.set_xlabel("Weight")
        ax.set_ylabel("$R_1$")
        ax.set_ylim(0.7, 0.95)
        ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle("Single-Trip Resilience by Stage 2 Configuration (N=3)", fontsize=14)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "3_r1_by_config.png", bbox_inches="tight")
    plt.close()
    print("  3_r1_by_config.png")


# ═══════════════════════════════════════════════════════════════════
# Chart 4: Cost vs Exposure (Pareto)
# ═══════════════════════════════════════════════════════════════════

def plot_cost_vs_exposure(rows):
    fig, ax = plt.subplots(figsize=(8, 5))
    data = get(rows, "off_off")

    costs = [r["s1_dispatch_cost"] for r in data]
    exps = [r["exposure_count"] for r in data]
    ws = [r["div_weight"] for r in data]

    ax.scatter(costs, exps, c="#d62728", s=80, zorder=5,
               edgecolors="black", linewidth=0.5)

    for c, e, w in zip(costs, exps, ws):
        ax.annotate(f"w={w}", (c, e), textcoords="offset points",
                    xytext=(8, 4), fontsize=8, color="#666")

    # Pareto front (minimise both cost and exposure)
    pareto = []
    best_exp = float("inf")
    for r in sorted(data, key=lambda r: r["s1_dispatch_cost"]):
        if r["exposure_count"] < best_exp:
            pareto.append(r)
            best_exp = r["exposure_count"]
    if pareto:
        ax.plot([r["s1_dispatch_cost"] for r in pareto],
                [r["exposure_count"] for r in pareto],
                "r--", alpha=0.6, linewidth=1.5, label="Pareto front")

    ax.set_xlabel("Stage 1 Dispatch Cost")
    ax.set_ylabel("High Exposure Count")
    ax.set_title("Cost vs Exposure (N=3) - Lower is better on both axes")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "4_cost_vs_exposure.png", bbox_inches="tight")
    plt.close()
    print("  4_cost_vs_exposure.png")


# ═══════════════════════════════════════════════════════════════════
# Chart 5: Cost vs R_TR (Pareto)
# ═══════════════════════════════════════════════════════════════════

def plot_cost_vs_rtr_pareto(rows):
    fig, ax = plt.subplots(figsize=(8, 5))
    data = get(rows, "off_off")

    costs = [r["s1_dispatch_cost"] for r in data]
    rtrs = [r["r_tr"] for r in data]
    exps = [r["exposure_count"] for r in data]
    ws = [r["div_weight"] for r in data]

    # Colour by exposure count
    scatter = ax.scatter(costs, rtrs, c=exps, cmap="RdYlGn_r", s=100, zorder=5,
                         edgecolors="black", linewidth=0.5, vmin=0, vmax=6)
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("Exposure Count")

    for c, rtr, w in zip(costs, rtrs, ws):
        ax.annotate(f"w={w}", (c, rtr), textcoords="offset points",
                    xytext=(8, 0), fontsize=8, color="#666")

    # Pareto front (minimise cost, maximise R_TR)
    pareto = []
    best_rtr = -1
    for r in sorted(data, key=lambda r: r["s1_dispatch_cost"]):
        if r["r_tr"] > best_rtr:
            pareto.append(r)
            best_rtr = r["r_tr"]
    if pareto:
        ax.plot([r["s1_dispatch_cost"] for r in pareto],
                [r["r_tr"] for r in pareto],
                "k--", alpha=0.4, linewidth=1.5, label="Pareto front")

    ax.set_xlabel("Stage 1 Dispatch Cost")
    ax.set_ylabel("$R_{TR}$")
    ax.set_title("Cost vs $R_{TR}$ with Exposure Count (N=3)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "5_cost_vs_rtr_pareto.png", bbox_inches="tight")
    plt.close()
    print("  5_cost_vs_rtr_pareto.png")


# ═══════════════════════════════════════════════════════════════════
# Chart 6: S2 dispatch cost by config
# ═══════════════════════════════════════════════════════════════════

def plot_s2_cost_by_config(rows):
    configs = ["off_off", "hetero", "conc", "both"]
    labels = ["Off/Off", "Hetero", "Conc", "Both"]
    colors = ["#bdbdbd", "#74c0fc", "#ffa94d", "#69db7c"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    weights = sorted(set(r["div_weight"] for r in rows))
    x = np.arange(len(weights))
    width = 0.2

    # Left: S2 dispatch cost
    for i, (cfg, label, color) in enumerate(zip(configs, labels, colors)):
        data = get(rows, cfg)
        vals = [r["s2_dispatch_cost"] for r in data]
        ax1.bar(x + i * width, vals, width, label=label,
                color=color, edgecolor="black", linewidth=0.5)

    ax1.set_xlabel("Weight")
    ax1.set_ylabel("Stage 2 Dispatch Cost")
    ax1.set_title("Actual Dispatch Cost by S2 Config")
    ax1.set_xticks(x + 1.5 * width)
    ax1.set_xticklabels([str(w) for w in weights])
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis="y")

    # Right: Cost saving (s1 - s2)
    for i, (cfg, label, color) in enumerate(zip(configs, labels, colors)):
        data = get(rows, cfg)
        vals = [r["cost_saving"] for r in data]
        ax2.bar(x + i * width, vals, width, label=label,
                color=color, edgecolor="black", linewidth=0.5)

    ax2.set_xlabel("Weight")
    ax2.set_ylabel("Cost Saving (S1 - S2)")
    ax2.set_title("Trip Consolidation Savings by S2 Config")
    ax2.set_xticks(x + 1.5 * width)
    ax2.set_xticklabels([str(w) for w in weights])
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis="y")

    fig.suptitle("Stage 2 Cost Impact (N=3, layered_medium_seed1)", fontsize=14)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "6_s2_cost_by_config.png", bbox_inches="tight")
    plt.close()
    print("  6_s2_cost_by_config.png")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load()
    print(f"Loaded {len(rows)} OK rows\n")

    plot_rtr_vs_weight(rows)
    plot_rtr_vs_cost(rows)
    plot_r1_by_config(rows)
    plot_cost_vs_exposure(rows)
    plot_cost_vs_rtr_pareto(rows)
    plot_s2_cost_by_config(rows)

    print(f"\nAll plots saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
