#!/usr/bin/env python3
"""
Plot experimental analysis graphs for the layered instance experiments.
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "legend.fontsize": 9,
    "figure.dpi": 150,
})

CSV_PATH = Path("results/smoke_test.csv")
OUT_DIR = Path("results/plots")


def load_data(csv_path: Path) -> list[dict]:
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    # Type conversions
    for r in rows:
        r["div_weight"] = int(r["div_weight"])
        r["dominant_count"] = int(r["dominant_count"]) if r["dominant_count"] else None
        r["r_tr"] = float(r["r_tr"]) if r["r_tr"] else None
        r["r_1"] = float(r["r_1"]) if r["r_1"] else None
        r["nominal_cost"] = int(r["nominal_cost"]) if r["nominal_cost"] else None
        r["mono_count"] = int(r["mono_count"]) if r["mono_count"] else None
        r["concentrated_count"] = int(r["concentrated_count"]) if r["concentrated_count"] else None
        r["s1_dispatch_cost"] = int(r["s1_dispatch_cost"]) if r.get("s1_dispatch_cost") else None
        r["s2_dispatch_cost"] = int(r["s2_dispatch_cost"]) if r.get("s2_dispatch_cost") else None
        r["cost_saving"] = int(r["cost_saving"]) if r.get("cost_saving") else None
    return rows


def classify_size(name: str) -> str:
    if "paper" in name:
        return "paper"
    elif "small" in name:
        return "small"
    elif "medium" in name:
        return "medium"
    elif "large" in name:
        return "large"
    return "other"


# ═══════════════════════════════════════════════════════════════════════
# Graph 1: R_TR vs Weight
# ═══════════════════════════════════════════════════════════════════════

def plot_rtr_vs_weight(rows):
    fig, ax = plt.subplots(figsize=(10, 5))

    # Use off_off only (R_TR doesn't depend on Stage 2)
    data = [r for r in rows if r["s2_config"] == "off_off"
            and r["status"] == "OK" and r["r_tr"] is not None]

    sizes = {"paper": "o", "small": "s", "medium": "^", "large": "D"}
    colors = {"paper": "#2ca02c", "small": "#1f77b4", "medium": "#ff7f0e", "large": "#d62728"}

    for inst in sorted(set(r["instance_name"] for r in data)):
        inst_data = sorted([r for r in data if r["instance_name"] == inst],
                          key=lambda r: r["div_weight"])
        ws = [r["div_weight"] for r in inst_data]
        rtrs = [r["r_tr"] for r in inst_data]
        size = classify_size(inst)
        ax.plot(ws, rtrs, marker=sizes.get(size, "o"), color=colors.get(size, "gray"),
                alpha=0.7, linewidth=1.2, markersize=5, label=inst)

    ax.set_xlabel("Stage 1 Diversification Weight")
    ax.set_ylabel("$R_{TR}$")
    ax.set_title("Transport Resilience vs Diversification Weight")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "rtr_vs_weight.png", bbox_inches="tight")
    plt.close()
    print("  Saved rtr_vs_weight.png")


# ═══════════════════════════════════════════════════════════════════════
# Graph 2: R_1 vs S2 Config (grouped bar per weight bracket)
# ═══════════════════════════════════════════════════════════════════════

def plot_r1_vs_s2_config(rows):
    fig, ax = plt.subplots(figsize=(10, 5))

    ok = [r for r in rows if r["status"] == "OK" and r["r_1"] is not None]

    # Weight brackets
    brackets = [(0, 0, "w=0"), (50, 150, "w=50-150"), (200, 350, "w=200-350"),
                (400, 550, "w=400-550"), (600, 700, "w=600-700")]
    configs = ["off_off", "hetero", "conc", "both"]
    config_labels = ["Off/Off", "Hetero", "Conc", "Both"]
    config_colors = ["#bdbdbd", "#74c0fc", "#ffa94d", "#69db7c"]

    x = np.arange(len(brackets))
    width = 0.2

    for i, cfg in enumerate(configs):
        means = []
        for lo, hi, _ in brackets:
            vals = [r["r_1"] for r in ok
                    if r["s2_config"] == cfg and lo <= r["div_weight"] <= hi]
            means.append(np.mean(vals) if vals else 0)
        ax.bar(x + i * width, means, width, label=config_labels[i],
               color=config_colors[i], edgecolor="black", linewidth=0.5)

    ax.set_xlabel("Weight Bracket")
    ax.set_ylabel("Mean $R_1$")
    ax.set_title("Single-Trip Resilience by Stage 2 Configuration")
    ax.set_xticks(x + 1.5 * width)
    ax.set_xticklabels([b[2] for b in brackets])
    ax.legend()
    ax.set_ylim(0.7, 0.95)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "r1_vs_s2_config.png", bbox_inches="tight")
    plt.close()
    print("  Saved r1_vs_s2_config.png")


# ═══════════════════════════════════════════════════════════════════════
# Graph 3a: R_TR vs Cost (Pareto scatter)
# ═══════════════════════════════════════════════════════════════════════

def plot_rtr_vs_cost(rows):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    data = [r for r in rows if r["s2_config"] == "off_off"
            and r["status"] == "OK" and r["r_tr"] is not None
            and r["s1_dispatch_cost"] is not None]

    colors = {"paper": "#2ca02c", "small": "#1f77b4", "medium": "#ff7f0e", "large": "#d62728"}
    markers = {"paper": "o", "small": "s", "medium": "^", "large": "D"}

    # R_TR vs dispatch cost
    for inst in sorted(set(r["instance_name"] for r in data)):
        idata = [r for r in data if r["instance_name"] == inst]
        size = classify_size(inst)
        ax1.scatter([r["s1_dispatch_cost"] for r in idata],
                   [r["r_tr"] for r in idata],
                   c=colors.get(size, "gray"), marker=markers.get(size, "o"),
                   alpha=0.7, s=40, label=inst)

    ax1.set_xlabel("Stage 1 Dispatch Cost")
    ax1.set_ylabel("$R_{TR}$")
    ax1.set_title("Transport Resilience vs Cost")
    ax1.grid(True, alpha=0.3)

    # Dominant count vs dispatch cost
    for inst in sorted(set(r["instance_name"] for r in data)):
        idata = [r for r in data if r["instance_name"] == inst]
        size = classify_size(inst)
        ax2.scatter([r["s1_dispatch_cost"] for r in idata],
                   [r["dominant_count"] for r in idata],
                   c=colors.get(size, "gray"), marker=markers.get(size, "o"),
                   alpha=0.7, s=40, label=inst)

    ax2.set_xlabel("Stage 1 Dispatch Cost")
    ax2.set_ylabel("Dominant TR Count")
    ax2.set_title("Load Imbalance vs Cost")
    ax2.grid(True, alpha=0.3)
    ax2.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=7)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "rtr_and_dominant_vs_cost.png", bbox_inches="tight")
    plt.close()
    print("  Saved rtr_and_dominant_vs_cost.png")


# ═══════════════════════════════════════════════════════════════════════
# Graph 4: Stage 1 vs Stage 2 Dispatch Cost
# ═══════════════════════════════════════════════════════════════════════

def plot_cost_saving(rows):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    configs = ["off_off", "both"]
    config_labels = {"off_off": "No S2 constraints", "both": "Both S2 constraints"}
    config_colors = {"off_off": "#bdbdbd", "both": "#69db7c"}

    for cfg in configs:
        data = [r for r in rows if r["s2_config"] == cfg
                and r["status"] == "OK"
                and r["s1_dispatch_cost"] is not None
                and r["cost_saving"] is not None]

        # Average saving by weight
        weights = sorted(set(r["div_weight"] for r in data))
        avg_savings = []
        avg_pct = []
        for w in weights:
            wdata = [r for r in data if r["div_weight"] == w]
            savings = [r["cost_saving"] for r in wdata]
            pcts = [r["cost_saving"] / max(1, r["s1_dispatch_cost"]) * 100
                    for r in wdata if r["s1_dispatch_cost"] > 0]
            avg_savings.append(np.mean(savings))
            avg_pct.append(np.mean(pcts) if pcts else 0)

        ax1.plot(weights, avg_savings, marker="o", markersize=4,
                label=config_labels[cfg], color=config_colors[cfg], linewidth=1.5)
        ax2.plot(weights, avg_pct, marker="o", markersize=4,
                label=config_labels[cfg], color=config_colors[cfg], linewidth=1.5)

    ax1.set_xlabel("Stage 1 Diversification Weight")
    ax1.set_ylabel("Absolute Cost Saving")
    ax1.set_title("Stage 2 Dispatch Cost Saving (Absolute)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.set_xlabel("Stage 1 Diversification Weight")
    ax2.set_ylabel("Cost Saving (%)")
    ax2.set_title("Stage 2 Dispatch Cost Saving (Percentage)")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "cost_saving.png", bbox_inches="tight")
    plt.close()
    print("  Saved cost_saving.png")


# ═══════════════════════════════════════════════════════════════════════
# Graph 5: R_1 vs R_TR scatter coloured by S2 config
# ═══════════════════════════════════════════════════════════════════════

def plot_r1_vs_rtr(rows):
    fig, ax = plt.subplots(figsize=(7, 6))

    ok = [r for r in rows if r["status"] == "OK"
          and r["r_1"] is not None and r["r_tr"] is not None]

    config_colors = {"off_off": "#bdbdbd", "hetero": "#74c0fc",
                     "conc": "#ffa94d", "both": "#69db7c"}
    config_labels = {"off_off": "Off/Off", "hetero": "Hetero",
                     "conc": "Conc", "both": "Both"}

    for cfg in ["off_off", "hetero", "conc", "both"]:
        cdata = [r for r in ok if r["s2_config"] == cfg]
        ax.scatter([r["r_tr"] for r in cdata],
                  [r["r_1"] for r in cdata],
                  c=config_colors[cfg], alpha=0.5, s=25,
                  label=config_labels[cfg], edgecolors="black", linewidth=0.3)

    # R_1 = R_TR line
    ax.plot([0.2, 1.0], [0.2, 1.0], "k--", alpha=0.3, linewidth=1, label="$R_1 = R_{TR}$")

    ax.set_xlabel("$R_{TR}$ (Arc-level resilience)")
    ax.set_ylabel("$R_1$ (Trip-level resilience)")
    ax.set_title("$R_1$ vs $R_{TR}$ by Stage 2 Configuration")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0.2, 0.85)
    ax.set_ylim(0.65, 0.95)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "r1_vs_rtr.png", bbox_inches="tight")
    plt.close()
    print("  Saved r1_vs_rtr.png")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_data(CSV_PATH)
    print(f"Loaded {len(rows)} rows")
    print()

    plot_rtr_vs_weight(rows)
    plot_r1_vs_s2_config(rows)
    plot_rtr_vs_cost(rows)
    plot_cost_saving(rows)
    plot_r1_vs_rtr(rows)

    print(f"\nAll plots saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
