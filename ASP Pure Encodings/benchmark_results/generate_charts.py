#!/usr/bin/env python3
"""Generate analysis charts from the benchmark CSV."""

import csv
from collections import defaultdict
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

HERE    = Path(__file__).parent
CSV_PATH = HERE / "results_20260310_093917.csv"
OUT_DIR  = HERE / "charts"
OUT_DIR.mkdir(exist_ok=True)

# ── load data ──────────────────────────────────────────────────────────────────

def load(path: Path) -> list[dict]:
    rows = []
    with path.open() as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "series":         r["series"],
                "instance":       r["instance"],
                "encoding":       r["encoding"],
                "bins":           int(r["bins"]),
                "configuration":  r["configuration"],
                "result":         r["result"],
                "atoms":          int(r["atoms"]) if r["atoms"] else None,
                "rules":          int(r["rules"]) if r["rules"] else None,
                "choices":        int(r["choices"]) if r["choices"] else None,
                "conflicts":      int(r["conflicts"]) if r["conflicts"] else None,
                "ground_time_s":  float(r["ground_time_s"]) if r["ground_time_s"] else None,
                "solve_time_s":   float(r["solve_time_s"])  if r["solve_time_s"]  else None,
                "total_time_s":   float(r["total_time_s"])  if r["total_time_s"]  else None,
            })
    return rows


def avg(vals):
    clean = [v for v in vals if v is not None]
    return statistics.mean(clean) if clean else 0.0


RECORDS = load(CSV_PATH)

CONFIGS   = ["jumpy", "tweety", "handy", "parallel"]
ENCODINGS = ["encoding_route", "optimised_encoding"]
ENC_LABELS = {"encoding_route": "Baseline", "optimised_encoding": "Optimised"}
CFG_COLORS = {"jumpy": "#4C72B0", "tweety": "#DD8452", "handy": "#55A868", "parallel": "#C44E52"}
ENC_HATCHES = {"encoding_route": "", "optimised_encoding": "///"}

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "legend.fontsize": 10,
    "figure.dpi": 150,
})


# ── Chart 1: Grounding vs Solving proportion ───────────────────────────────────
# Stacked bar: for each (encoding, config) pair show avg ground and solve time
# over the hardest instances (Series D bins=3 + Series E tight)

def chart_ground_vs_solve():
    hard = [r for r in RECORDS if
            (r["series"] == "D" and r["bins"] == 3) or
            (r["series"] == "E" and "tight" in r["instance"])]

    fig, ax = plt.subplots(figsize=(10, 5))
    labels, ground_vals, solve_vals = [], [], []

    for enc in ENCODINGS:
        for cfg in CONFIGS:
            subset = [r for r in hard if r["encoding"] == enc and r["configuration"] == cfg]
            if not subset:
                continue
            g = avg([r["ground_time_s"] for r in subset])
            s = avg([r["solve_time_s"]  for r in subset])
            labels.append(f"{ENC_LABELS[enc]}\n{cfg}")
            ground_vals.append(g)
            solve_vals.append(s)

    x = np.arange(len(labels))
    w = 0.6
    ax.bar(x, ground_vals, w, label="Grounding", color="#AEC6CF")
    ax.bar(x, solve_vals, w, bottom=ground_vals, label="Solving", color="#F4A460")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Time (s)")
    ax.set_title("Grounding vs Solving Time\n(hard instances: Series D bins=3, Series E tight)")
    ax.legend()
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "01_ground_vs_solve.png")
    plt.close()
    print("Saved 01_ground_vs_solve.png")


# ── Chart 2: Series D — solve time vs bins, lines per config, panels per encoding ──

def chart_D_solve_by_bins():
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)

    for ax, enc in zip(axes, ENCODINGS):
        for cfg in CONFIGS:
            ys = []
            for b in [1, 2, 3]:
                subset = [r for r in RECORDS
                          if r["series"] == "D" and r["encoding"] == enc
                          and r["configuration"] == cfg and r["bins"] == b]
                ys.append(avg([r["solve_time_s"] for r in subset]))
            ax.plot([1, 2, 3], ys, marker="o", label=cfg,
                    color=CFG_COLORS[cfg], linewidth=2)

        ax.set_xticks([1, 2, 3])
        ax.set_xlabel("Number of bins")
        ax.set_ylabel("Avg solve time (s)")
        ax.set_title(f"Series D — {ENC_LABELS[enc]}")
        ax.legend(title="Config")
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)

    fig.suptitle("Series D: Bin Scaling — Avg Solve Time by Configuration", fontsize=13)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "02_series_D_solve_by_bins.png")
    plt.close()
    print("Saved 02_series_D_solve_by_bins.png")


# ── Chart 3: Series D bins=3 — per-instance solve time, grouped bar ────────────

def chart_D_bins3_per_instance():
    instances = sorted({r["instance"] for r in RECORDS if r["series"] == "D"})
    n_inst = len(instances)
    n_cfg  = len(CONFIGS)
    n_enc  = len(ENCODINGS)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=False)

    for ax, enc in zip(axes, ENCODINGS):
        x = np.arange(n_inst)
        width = 0.18
        for ci, cfg in enumerate(CONFIGS):
            vals = []
            for inst in instances:
                subset = [r for r in RECORDS
                          if r["series"] == "D" and r["bins"] == 3
                          and r["encoding"] == enc and r["configuration"] == cfg
                          and r["instance"] == inst]
                vals.append(avg([r["solve_time_s"] for r in subset]))
            offset = (ci - n_cfg / 2 + 0.5) * width
            bars = ax.bar(x + offset, vals, width, label=cfg, color=CFG_COLORS[cfg])

        ax.set_xticks(x)
        ax.set_xticklabels([i.replace("L06_P02_TR2_", "") for i in instances],
                           fontsize=9)
        ax.set_xlabel("Instance")
        ax.set_ylabel("Solve time (s)")
        ax.set_title(f"Series D bins=3 — {ENC_LABELS[enc]}")
        ax.legend(title="Config")
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)

    fig.suptitle("Series D bins=3: Solve Time per Instance by Configuration", fontsize=13)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "03_series_D_bins3_per_instance.png")
    plt.close()
    print("Saved 03_series_D_bins3_per_instance.png")


# ── Chart 4: Series E — solve time by tightness, grouped bar ──────────────────

def chart_E_by_tightness():
    tightness_order = ["loose", "medium", "tight"]
    label_map = {"loose": "Loose", "medium": "Medium", "tight": "Tight"}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)

    for ax, enc in zip(axes, ENCODINGS):
        x = np.arange(len(tightness_order))
        width = 0.18
        for ci, cfg in enumerate(CONFIGS):
            vals = []
            for t in tightness_order:
                subset = [r for r in RECORDS
                          if r["series"] == "E" and t in r["instance"]
                          and r["encoding"] == enc and r["configuration"] == cfg]
                vals.append(avg([r["solve_time_s"] for r in subset]))
            offset = (ci - len(CONFIGS) / 2 + 0.5) * width
            ax.bar(x + offset, vals, width, label=cfg, color=CFG_COLORS[cfg])

        ax.set_xticks(x)
        ax.set_xticklabels([label_map[t] for t in tightness_order])
        ax.set_xlabel("Capacity tightness")
        ax.set_ylabel("Avg solve time (s)")
        ax.set_title(f"Series E — {ENC_LABELS[enc]}")
        ax.legend(title="Config")
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)

    fig.suptitle("Series E: Capacity Tightness — Avg Solve Time by Configuration", fontsize=13)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "04_series_E_by_tightness.png")
    plt.close()
    print("Saved 04_series_E_by_tightness.png")


# ── Chart 5: Speedup heatmap — optimised/baseline ratio by (bins, config) ─────

def chart_speedup_heatmap():
    bins_list = [1, 2, 3]

    ratios = np.zeros((len(CONFIGS), len(bins_list)))
    for ci, cfg in enumerate(CONFIGS):
        for bi, b in enumerate(bins_list):
            base_t = avg([r["solve_time_s"] for r in RECORDS
                          if r["series"] == "D" and r["bins"] == b
                          and r["encoding"] == "encoding_route"
                          and r["configuration"] == cfg])
            opt_t  = avg([r["solve_time_s"] for r in RECORDS
                          if r["series"] == "D" and r["bins"] == b
                          and r["encoding"] == "optimised_encoding"
                          and r["configuration"] == cfg])
            ratios[ci, bi] = opt_t / base_t if base_t > 0 else 1.0

    fig, ax = plt.subplots(figsize=(7, 4))
    # Use a diverging colourmap centred at 1.0
    im = ax.imshow(ratios, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=3)

    ax.set_xticks(range(len(bins_list)))
    ax.set_xticklabels([f"bins={b}" for b in bins_list])
    ax.set_yticks(range(len(CONFIGS)))
    ax.set_yticklabels(CONFIGS)
    ax.set_title("Speedup Ratio: Optimised / Baseline Solve Time\n(Series D; green < 1 = optimised wins)")

    for ci in range(len(CONFIGS)):
        for bi in range(len(bins_list)):
            v = ratios[ci, bi]
            ax.text(bi, ci, f"{v:.2f}x", ha="center", va="center",
                    fontsize=11, fontweight="bold",
                    color="white" if abs(v - 1.5) > 0.4 else "black")

    plt.colorbar(im, ax=ax, label="opt / baseline")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "05_speedup_heatmap.png")
    plt.close()
    print("Saved 05_speedup_heatmap.png")


# ── Chart 6: Choices vs solve time scatter — all Series D bins=3 runs ─────────

def chart_choices_vs_time():
    subset = [r for r in RECORDS if r["series"] == "D" and r["bins"] == 3]

    fig, ax = plt.subplots(figsize=(8, 5))
    for enc in ENCODINGS:
        for cfg in CONFIGS:
            pts = [(r["choices"], r["solve_time_s"])
                   for r in subset
                   if r["encoding"] == enc and r["configuration"] == cfg
                   and r["choices"] is not None and r["solve_time_s"] is not None]
            if pts:
                xs, ys = zip(*pts)
                marker = "o" if enc == "encoding_route" else "^"
                ax.scatter(xs, ys, label=f"{ENC_LABELS[enc]} / {cfg}",
                           color=CFG_COLORS[cfg],
                           marker=marker, alpha=0.8, s=60,
                           edgecolors="white", linewidths=0.5)

    ax.set_xlabel("Choices (search space explored)")
    ax.set_ylabel("Solve time (s)")
    ax.set_title("Choices vs Solve Time — Series D bins=3")
    ax.legend(fontsize=8, ncol=2)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.xaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "06_choices_vs_time.png")
    plt.close()
    print("Saved 06_choices_vs_time.png")


# ── Chart 7: Atoms/rules comparison — encoding size by (encoding, bins) ────────

def chart_program_size():
    bins_list = [1, 2, 3]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)

    metrics = [("atoms", "Atoms"), ("rules", "Rules")]
    for ax, (metric, label) in zip(axes, metrics):
        for enc in ENCODINGS:
            vals = []
            for b in bins_list:
                subset = [r for r in RECORDS
                          if r["series"] == "D" and r["encoding"] == enc and r["bins"] == b]
                vals.append(avg([r[metric] for r in subset]))
            ax.plot(bins_list, vals, marker="o", linewidth=2,
                    label=ENC_LABELS[enc])

        ax.set_xticks(bins_list)
        ax.set_xlabel("Number of bins")
        ax.set_ylabel(label)
        ax.set_title(f"Grounded Program {label} vs Bins (Series D)")
        ax.legend()
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "07_program_size_by_bins.png")
    plt.close()
    print("Saved 07_program_size_by_bins.png")


if __name__ == "__main__":
    chart_ground_vs_solve()
    chart_D_solve_by_bins()
    chart_D_bins3_per_instance()
    chart_E_by_tightness()
    chart_speedup_heatmap()
    chart_choices_vs_time()
    chart_program_size()
    print(f"\nAll charts saved to {OUT_DIR}")
