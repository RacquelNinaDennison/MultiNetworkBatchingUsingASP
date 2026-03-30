#!/usr/bin/env python3
"""
plot_results.py — Generate charts from diversity experiment results.

Reads the CSV files produced by evaluate.py and generates:
  1. Jaccard heatmaps (one per granularity level)
  2. Quality metrics grouped bar chart
  3. Radar chart comparing all variants across quality dimensions

Usage:
    python plot_results.py --quality results/quality_*.csv --jaccard results/jaccard_*.csv
    python plot_results.py --quality results/quality_paper_instances_20260315_143712.csv \
                           --jaccard results/jaccard_paper_instances_20260315_143712.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np


RESULTS_DIR = Path(__file__).parent / "results"

# Readable labels for variants
LABELS = {
    "E1_baseline":   "E1: Cost only",
    "E2_cost_co2":   "E2: Cost + CO₂",
    "E3_full":       "E3: Cost→CO₂→Hold",
    "E4_hold_first": "E4: Hold→Cost→CO₂",
    "E5_co2_first":  "E5: CO₂→Cost→Hold",
}


def label(variant: str) -> str:
    return LABELS.get(variant, variant)


# ── Data loading ─────────────────────────────────────────────────────────

def load_quality(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def load_jaccard(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


# ── 1. Jaccard Heatmaps ─────────────────────────────────────────────────

def plot_jaccard_heatmaps(rows: list[dict], output_dir: Path) -> None:
    """One heatmap per Jaccard granularity level."""
    # Collect all variants in order
    variants = []
    for r in rows:
        for v in [r["variant_a"], r["variant_b"]]:
            if v not in variants:
                variants.append(v)

    n = len(variants)
    idx = {v: i for i, v in enumerate(variants)}

    levels = [
        ("jaccard_routes", "Route Structure", "Which physical arcs are used?"),
        ("jaccard_flows",  "Active Flows",    "Which parts flow on which routes?"),
        ("jaccard_freq",   "Frequency Match", "Same route with same batch frequency?"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle("Jaccard Similarity Between Objective Variants", fontsize=14, fontweight="bold", y=1.02)

    for ax, (col, title, subtitle) in zip(axes, levels):
        mat = np.ones((n, n))  # diagonal = 1.0
        for r in rows:
            i, j = idx[r["variant_a"]], idx[r["variant_b"]]
            val = float(r[col])
            mat[i][j] = val
            mat[j][i] = val

        cmap = mcolors.LinearSegmentedColormap.from_list(
            "jaccard", ["#d73027", "#fee08b", "#1a9850"]
        )
        im = ax.imshow(mat, cmap=cmap, vmin=0, vmax=1, aspect="equal")

        tick_labels = [label(v) for v in variants]
        ax.set_xticks(range(n))
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(n))
        ax.set_yticklabels(tick_labels, fontsize=8)

        # Annotate cells
        for i in range(n):
            for j in range(n):
                val = mat[i][j]
                color = "white" if val < 0.4 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=9, fontweight="bold", color=color)

        ax.set_title(f"{title}\n{subtitle}", fontsize=10, pad=8)

    fig.colorbar(im, ax=axes, shrink=0.8, label="Jaccard Index (1.0 = identical)")
    fig.tight_layout()

    out = output_dir / "jaccard_heatmaps.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved → {out}")
    plt.close(fig)


# ── 2. Quality Metrics Bar Chart ────────────────────────────────────────

def plot_quality_bars(rows: list[dict], output_dir: Path) -> None:
    """Grouped bar chart of key quality metrics."""
    variants = [r["variant"] for r in rows]
    labels_list = [label(v) for v in variants]
    n = len(variants)
    x = np.arange(n)

    metrics = [
        ("avg_parts_per_route", "Avg Parts/Route", "#2196F3", "higher = more diverse"),
        ("mono_sku_routes",     "Mono-SKU Routes", "#f44336", "lower = better"),
        ("avg_fill_rate",       "Avg Fill Rate",   "#4CAF50", "higher = better utilisation"),
        ("avg_max_part_share",  "Avg Max Part Share", "#FF9800", "lower = more balanced"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Packing Quality Metrics by Objective Variant", fontsize=14, fontweight="bold")

    for ax, (col, title, color, note) in zip(axes.flat, metrics):
        vals = [float(r[col]) for r in rows]
        bars = ax.bar(x, vals, color=color, alpha=0.85, edgecolor="white", linewidth=0.5)

        # Value labels on bars
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=9, fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(labels_list, rotation=30, ha="right", fontsize=8)
        ax.set_title(f"{title}", fontsize=11, fontweight="bold")
        ax.set_ylabel(note, fontsize=8, fontstyle="italic", color="gray")
        ax.set_ylim(0, max(vals) * 1.25 if max(vals) > 0 else 1)
        ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    out = output_dir / "quality_bars.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved → {out}")
    plt.close(fig)


# ── 3. Radar Chart ──────────────────────────────────────────────────────

def plot_radar(rows: list[dict], output_dir: Path) -> None:
    """Spider/radar chart comparing all variants across quality dimensions."""
    # Metrics to include (all normalised to 0-1 where higher = better)
    # We invert metrics where lower is better
    dims = [
        ("avg_parts_per_route", "Parts/Route\n(diversity)", False, 2.0),
        ("avg_fill_rate",       "Fill Rate\n(utilisation)", False, 1.0),
        ("mono_sku_routes",     "Mono-SKU\n(fewer=better)", True, None),
        ("avg_max_part_share",  "Max Share\n(lower=balanced)", True, 1.0),
        ("total_frequency",     "Total Freq\n(fewer=efficient)", True, None),
    ]

    variants = [r["variant"] for r in rows]
    n_dims = len(dims)
    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    colors = ["#2196F3", "#4CAF50", "#FF9800", "#f44336", "#9C27B0"]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.set_title("Multi-Dimensional Quality Comparison", fontsize=13,
                 fontweight="bold", pad=20)

    for i, row in enumerate(rows):
        values = []
        for col, _, invert, max_val in dims:
            raw = float(row[col])
            # Normalise
            if max_val is None:
                max_val = max(float(r[col]) for r in rows)
            norm = raw / max_val if max_val > 0 else 0
            if invert:
                norm = 1.0 - norm
            values.append(min(norm, 1.0))

        values += values[:1]
        ax.plot(angles, values, "o-", linewidth=2, color=colors[i % len(colors)],
                label=label(row["variant"]), markersize=5)
        ax.fill(angles, values, alpha=0.08, color=colors[i % len(colors)])

    dim_labels = [d[1] for d in dims]
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dim_labels, fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=7, color="gray")
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=9)

    fig.tight_layout()
    out = output_dir / "quality_radar.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved → {out}")
    plt.close(fig)


# ── 4. Jaccard Grouped Bars ─────────────────────────────────────────────

def plot_jaccard_bars(rows: list[dict], output_dir: Path) -> None:
    """Grouped bar chart: all pairs, three Jaccard levels side by side."""
    pairs = [f"{label(r['variant_a'])}\nvs\n{label(r['variant_b'])}" for r in rows]
    n = len(pairs)
    x = np.arange(n)
    width = 0.25

    routes = [float(r["jaccard_routes"]) for r in rows]
    flows = [float(r["jaccard_flows"]) for r in rows]
    freqs = [float(r["jaccard_freq"]) for r in rows]

    fig, ax = plt.subplots(figsize=(16, 6))

    ax.bar(x - width, routes, width, label="Route Structure", color="#2196F3", alpha=0.85)
    ax.bar(x,         flows,  width, label="Active Flows",    color="#FF9800", alpha=0.85)
    ax.bar(x + width, freqs,  width, label="Frequency Match", color="#4CAF50", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(pairs, fontsize=7, ha="center")
    ax.set_ylabel("Jaccard Index")
    ax.set_title("Pairwise Jaccard Similarity Across Granularity Levels",
                 fontsize=13, fontweight="bold")
    ax.set_ylim(0, 1.15)
    ax.axhline(y=0.5, color="gray", linestyle="--", alpha=0.4, label="J=0.5 (moderate)")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    out = output_dir / "jaccard_bars.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved → {out}")
    plt.close(fig)


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Plot diversity experiment results.")
    parser.add_argument("--quality", "-q", required=True, help="Path to quality CSV")
    parser.add_argument("--jaccard", "-j", required=True, help="Path to jaccard CSV")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory for charts (default: same as CSV dir)")
    args = parser.parse_args()

    q_path = Path(args.quality)
    j_path = Path(args.jaccard)
    output_dir = Path(args.output_dir) if args.output_dir else q_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    if not q_path.exists():
        print(f"Error: quality CSV not found: {q_path}", file=sys.stderr)
        return 1
    if not j_path.exists():
        print(f"Error: jaccard CSV not found: {j_path}", file=sys.stderr)
        return 1

    quality_rows = load_quality(q_path)
    jaccard_rows = load_jaccard(j_path)

    print(f"Quality data : {len(quality_rows)} variants")
    print(f"Jaccard data : {len(jaccard_rows)} pairs")
    print(f"Output dir   : {output_dir}")
    print()

    print("Generating charts...")
    plot_jaccard_heatmaps(jaccard_rows, output_dir)
    plot_jaccard_bars(jaccard_rows, output_dir)
    plot_quality_bars(quality_rows, output_dir)
    plot_radar(quality_rows, output_dir)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
