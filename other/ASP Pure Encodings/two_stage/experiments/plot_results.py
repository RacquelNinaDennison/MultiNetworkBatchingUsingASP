#!/usr/bin/env python3
"""
plot_results.py — Generate diagrams from experiment results
=============================================================

Produces:
  1. Pareto front: Stage 1 diversification weight vs cost vs R_TR
  2. Pareto front: Stage 1 diversification weight vs cost vs R_1
  3. Ablation bar charts: violation counts by S2 variant
  4. Ablation bar charts: resilience metrics by S2 variant

Usage
-----
    uv run experiments/plot_results.py

    # Only plot specific experiments:
    uv run experiments/plot_results.py --plot pareto
    uv run experiments/plot_results.py --plot ablation
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from collections import defaultdict

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
except ImportError:
    print("matplotlib not installed. Install with: uv add matplotlib", file=sys.stderr)
    sys.exit(1)


HERE    = Path(__file__).parent
RESULTS = HERE / "results"
PLOTS   = HERE / "results" / "plots"


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


# ═══════════════════════════════════════════════════════════════════════
# Pareto front: S1 diversification sweep
# ═══════════════════════════════════════════════════════════════════════

def parse_s2_dispatch_cost(s2_cost_str: str) -> int:
    """Extract the dispatch cost (last element) from the s2_cost list string."""
    # s2_cost looks like "[40, 65, 4704]" or "[]"
    s2_cost_str = s2_cost_str.strip()
    if not s2_cost_str or s2_cost_str == "[]":
        return 0
    try:
        # Remove brackets and split
        inner = s2_cost_str.strip("[]")
        parts = [int(x.strip()) for x in inner.split(",")]
        return parts[-1] if parts else 0  # last element is dispatch cost (@1)
    except (ValueError, IndexError):
        return 0


def plot_s1_pareto(rows: list[dict]) -> None:
    """Plot Pareto fronts: transport cost vs diversification metrics."""

    if not rows:
        print("No S1 diversification sweep data found.")
        return

    PLOTS.mkdir(parents=True, exist_ok=True)

    # Group by instance
    by_instance = defaultdict(list)
    for row in rows:
        by_instance[row["instance"]].append(row)

    # ── Plot 1: Pareto front — S1 Transport Cost vs UnderDiversified ──
    fig, ax = plt.subplots(1, 1, figsize=(10, 7))

    for inst, inst_rows in sorted(by_instance.items()):
        sorted_rows = sorted(inst_rows, key=lambda r: int(r["sweep_weight"]))

        if "s1_transport_cost" in sorted_rows[0]:
            costs = [int(r["s1_transport_cost"]) for r in sorted_rows]
            undiv = [int(r["s1_underdiversified"]) for r in sorted_rows]
        else:
            costs = [int(r["s1_cost"]) if r["s1_cost"] else 0 for r in sorted_rows]
            undiv = [int(r["concentrated_trips"]) for r in sorted_rows]

        weights = [int(r["sweep_weight"]) for r in sorted_rows]

        # Color each point by weight using a colormap
        cmap = plt.cm.viridis
        norm = plt.Normalize(vmin=min(weights), vmax=max(weights))

        for i in range(len(costs)):
            color = cmap(norm(weights[i]))
            ax.scatter(costs[i], undiv[i], c=[color], s=80, zorder=5,
                      edgecolors='black', linewidth=0.5)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax)
    cbar.set_label("Diversification Weight", fontsize=11)

    ax.set_xlabel("Stage 1 Transport Cost", fontsize=12)
    ax.set_ylabel("UnderDiversified Arcs (fewer = more resilient)", fontsize=12)
    ax.set_title("Pareto Front: Transport Cost vs Resource Diversification", fontsize=13)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = PLOTS / "pareto_s1_cost_vs_underdiversified.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")

    # ── Plot 2: Weight sweep — how both S1 objectives change ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    for inst, inst_rows in sorted(by_instance.items()):
        sorted_rows = sorted(inst_rows, key=lambda r: int(r["sweep_weight"]))
        weights = [int(r["sweep_weight"]) for r in sorted_rows]

        if "s1_transport_cost" in sorted_rows[0]:
            costs = [int(r["s1_transport_cost"]) for r in sorted_rows]
            undiv = [int(r["s1_underdiversified"]) for r in sorted_rows]
        else:
            costs = [int(r["s1_cost"]) if r["s1_cost"] else 0 for r in sorted_rows]
            undiv = [int(r["concentrated_trips"]) for r in sorted_rows]

        axes[0].plot(weights, costs, 'o-', label=inst, markersize=6, linewidth=2)
        axes[1].plot(weights, undiv, 'o-', label=inst, markersize=6, linewidth=2)

    axes[0].set_xlabel("Diversification Weight", fontsize=11)
    axes[0].set_ylabel("S1 Transport Cost", fontsize=11)
    axes[0].set_title("Transport Cost vs Weight", fontsize=12)
    axes[0].set_xscale('symlog', linthresh=1)
    axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.3)

    axes[1].set_xlabel("Diversification Weight", fontsize=11)
    axes[1].set_ylabel("UnderDiversified Arcs", fontsize=11)
    axes[1].set_title("UnderDiversified vs Weight", fontsize=12)
    axes[1].set_xscale('symlog', linthresh=1)
    axes[1].legend(fontsize=9)
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    path = PLOTS / "sweep_s1_weight_tradeoff.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")

    # ── Plot 3: All violations vs weight ──────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    for inst, inst_rows in sorted(by_instance.items()):
        sorted_rows = sorted(inst_rows, key=lambda r: int(r["sweep_weight"]))
        weights = [int(r["sweep_weight"]) for r in sorted_rows]
        conc = [int(r["concentrated_trips"]) for r in sorted_rows]
        mono = [int(r["mono_trips"]) for r in sorted_rows]
        trips = [int(r["total_used_trips"]) for r in sorted_rows]

        axes[0].plot(weights, conc, 'o-', label=inst, markersize=5)
        axes[1].plot(weights, mono, 'o-', label=inst, markersize=5)
        axes[2].plot(weights, trips, 'o-', label=inst, markersize=5)

    axes[0].set_xlabel("Diversification Weight")
    axes[0].set_ylabel("Concentrated Trips")
    axes[0].set_title("Weight vs Concentrated Trips")
    axes[0].set_xscale('symlog', linthresh=1)
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].set_xlabel("Diversification Weight")
    axes[1].set_ylabel("Mono-part Trips")
    axes[1].set_title("Weight vs Mono-part Trips")
    axes[1].set_xscale('symlog', linthresh=1)
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    axes[2].set_xlabel("Diversification Weight")
    axes[2].set_ylabel("Trips Used")
    axes[2].set_title("Weight vs Trips Used")
    axes[2].set_xscale('symlog', linthresh=1)
    axes[2].legend(fontsize=8)
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    path = PLOTS / "sweep_weight_vs_violations.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════
# Ablation bar charts
# ═══════════════════════════════════════════════════════════════════════

def plot_ablation(rows: list[dict]) -> None:
    """Plot ablation results as grouped bar charts."""

    if not rows:
        print("No ablation data found.")
        return

    PLOTS.mkdir(parents=True, exist_ok=True)

    # Average across instances by (s1, s2)
    agg = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = (row["s1_name"], row["s2_name"])
        agg[key]["R_1"].append(float(row["R_1"]))
        agg[key]["R_TR"].append(float(row["R_TR"]))
        agg[key]["A_1"].append(float(row["A_1"]))
        agg[key]["concentrated"].append(int(row["concentrated_trips"]))
        agg[key]["mono"].append(int(row["mono_trips"]))
        agg[key]["overloaded"].append(int(row["overloaded_trips"]))
        agg[key]["max_concentration"].append(float(row["max_concentration"]))

    s2_order = ["S2-BASE", "S2-EVEN", "S2-HET", "S2-WC", "S2-FULL", "S2-VALW"]
    s1_variants = ["S1-COST", "S1-DIV"]

    # ── Violation counts bar chart ────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    x = range(len(s2_order))
    width = 0.35

    for idx, metric in enumerate(["concentrated", "mono", "overloaded"]):
        for i, s1 in enumerate(s1_variants):
            vals = [
                sum(agg[(s1, s2)][metric]) / len(agg[(s1, s2)][metric])
                if agg[(s1, s2)][metric] else 0
                for s2 in s2_order
            ]
            offset = (i - 0.5) * width
            axes[idx].bar([xi + offset for xi in x], vals, width,
                         label=s1, alpha=0.8)

        axes[idx].set_xlabel("Stage 2 Variant")
        axes[idx].set_ylabel(f"Avg {metric} trips")
        axes[idx].set_title(f"Average {metric.title()} Trips")
        axes[idx].set_xticks(x)
        axes[idx].set_xticklabels(s2_order, rotation=45, ha='right')
        axes[idx].legend()
        axes[idx].grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    path = PLOTS / "ablation_violations.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")

    # ── Resilience metrics bar chart ──────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    for idx, metric in enumerate(["R_1", "R_TR", "max_concentration"]):
        for i, s1 in enumerate(s1_variants):
            vals = [
                sum(agg[(s1, s2)][metric]) / len(agg[(s1, s2)][metric])
                if agg[(s1, s2)][metric] else 0
                for s2 in s2_order
            ]
            offset = (i - 0.5) * width
            axes[idx].bar([xi + offset for xi in x], vals, width,
                         label=s1, alpha=0.8)

        label = {"R_1": "$R_1$", "R_TR": "$R_{TR}$",
                 "max_concentration": "Max Concentration"}[metric]
        axes[idx].set_xlabel("Stage 2 Variant")
        axes[idx].set_ylabel(label)
        axes[idx].set_title(f"Average {label}")
        axes[idx].set_xticks(x)
        axes[idx].set_xticklabels(s2_order, rotation=45, ha='right')
        axes[idx].legend()
        axes[idx].grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    path = PLOTS / "ablation_resilience.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════
# ε-constraint Pareto front
# ═══════════════════════════════════════════════════════════════════════

def plot_epsilon_pareto(rows: list[dict]) -> None:
    """Plot the ε-constraint Pareto front: cost vs underDiversified."""

    if not rows:
        print("No ε-constraint data found.")
        return

    PLOTS.mkdir(parents=True, exist_ok=True)

    by_instance = defaultdict(list)
    for row in rows:
        by_instance[row["instance"]].append(row)

    # ── Pareto front: Transport Cost vs ε (underDiversified) ──
    fig, ax = plt.subplots(1, 1, figsize=(10, 7))

    colors = plt.cm.tab10.colors
    for idx, (inst, inst_rows) in enumerate(sorted(by_instance.items())):
        sorted_rows = sorted(inst_rows, key=lambda r: int(r["sweep_weight"]))

        epsilons = [int(r["sweep_weight"]) for r in sorted_rows]
        costs = [int(r["s1_transport_cost"]) for r in sorted_rows]
        undiv = [int(r["s1_underdiversified"]) for r in sorted_rows]

        color = colors[idx % len(colors)]
        ax.plot(costs, epsilons, 'o-', color=color, label=inst,
                markersize=8, linewidth=2)

        # Annotate each point with ε value
        for i, eps in enumerate(epsilons):
            ax.annotate(f'ε={eps}', (costs[i], epsilons[i]),
                       textcoords="offset points", xytext=(8, 3),
                       fontsize=7, alpha=0.8, color=color)

    ax.set_xlabel("Stage 1 Transport Cost (minimised)", fontsize=12)
    ax.set_ylabel("ε (max allowed underDiversified arcs)", fontsize=12)
    ax.set_title("ε-Constraint Pareto Front: Cost vs Diversification", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

    plt.tight_layout()
    path = PLOTS / "epsilon_pareto_front.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")

    # ── Cost vs ε as step chart (with monotonic correction) ──
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    for idx, (inst, inst_rows) in enumerate(sorted(by_instance.items())):
        sorted_rows = sorted(inst_rows, key=lambda r: int(r["sweep_weight"]))
        epsilons = [int(r["sweep_weight"]) for r in sorted_rows]
        raw_costs = [int(r["s1_transport_cost"]) for r in sorted_rows]

        # Monotonic correction: cost at ε should be ≤ cost at ε-1
        # because any solution feasible at ε-1 is also feasible at ε.
        # Take the running minimum.
        corrected_costs = []
        running_min = float('inf')
        for c in raw_costs:
            running_min = min(running_min, c)
            corrected_costs.append(running_min)

        color = colors[idx % len(colors)]

        # Left: raw data
        axes[0].plot(epsilons, raw_costs, 'o-', color=color,
                    label=inst, markersize=6, linewidth=2)

        # Right: monotonic corrected
        axes[1].plot(epsilons, corrected_costs, 'o-', color=color,
                    label=inst, markersize=6, linewidth=2)

    axes[0].set_xlabel("ε (max allowed underDiversified arcs)", fontsize=12)
    axes[0].set_ylabel("Transport Cost (solver found)", fontsize=12)
    axes[0].set_title("Raw Solver Results (non-optimal)", fontsize=13)
    axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.3)
    axes[0].xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    axes[1].set_xlabel("ε (max allowed underDiversified arcs)", fontsize=12)
    axes[1].set_ylabel("Best Known Transport Cost", fontsize=12)
    axes[1].set_title("Monotonic Correction (running minimum)", fontsize=13)
    axes[1].legend(fontsize=9)
    axes[1].grid(True, alpha=0.3)
    axes[1].xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    plt.tight_layout()
    path = PLOTS / "epsilon_cost_vs_allowed_violations.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="Plot experiment results.")
    parser.add_argument("--plot", choices=["pareto", "epsilon", "ablation", "all"],
                        default="all", help="Which plots to generate")
    args = parser.parse_args()

    print("Loading results...")

    if args.plot in ("pareto", "all"):
        print("\nGenerating weight-sweep Pareto plots...")
        s1_sweep = load_csv(RESULTS / "sweep_s1_diversification.csv")
        plot_s1_pareto(s1_sweep)

    if args.plot in ("epsilon", "all"):
        print("\nGenerating ε-constraint Pareto plots...")
        eps_data = load_csv(RESULTS / "epsilon_pareto.csv")
        plot_epsilon_pareto(eps_data)

    if args.plot in ("ablation", "all"):
        print("\nGenerating ablation plots...")
        ablation = load_csv(RESULTS / "ablation.csv")
        plot_ablation(ablation)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
