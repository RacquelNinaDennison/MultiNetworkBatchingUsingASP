"""Cost-versus-resilience tradeoff figures, in the style of the two-stage experiment's
`plot_ralpha_cost_tradeoff`: the resilience metric on the x-axis, the dispatch-cost
increase relative to the baseline cost-optimal plan on the y-axis, one marker per packing
configuration, swept over the flow-weight grid (exposure w_net, redundancy w_flow). Each
point is annotated with its weight setting w_net/w_flow (as multiples of the normaliser).

One panel per instance size (small, medium, industrial); produced for NRI and R_TR.
R_TR is flow-only, so its configurations share an x-coordinate at each weight and separate
only by realised dispatch cost.

    PYTHONPATH=src .venv/bin/python -m multibatch.experiments.milp_resilience.plots_tradeoff
"""
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from multibatch.experiments.milp_resilience import style
from multibatch.experiments.milp_resilience.style import (
    RES, FIG, CFG_COLOR, CFG_LABEL, CFG_ORDER, save as _save)

style.apply()

MARKERS = {"baseline": "o", "hetero_w8": "s", "conc_w8": "D", "full_w8_8": "^"}
SIZES = ["small", "medium", "industrial"]


def _prep(df, solver="milp"):
    d = df[df.flow_solver == solver].copy()
    d["size"] = np.where(d.instance.str.startswith("industry"), "industrial",
                         np.where(d.instance.str.contains("medium"), "medium", "small"))
    return d


def _wtag(wn, wf):
    f = lambda v: "0" if v == 0 else f"{int(v)}"
    return f"{f(wn)}/{f(wf)}"


def tradeoff(d, metric_col, metric_label, stem, pct_metric=True):
    """Per size: metric (x) vs relative dispatch-cost increase (y), per config, over the
    flow-weight grid. Cost is relative to the baseline cost-optimal plan of that size."""
    sizes = [s for s in SIZES if s in set(d["size"])]
    fig, axes = plt.subplots(1, len(sizes), figsize=(5.2 * len(sizes), 5.2), squeeze=False)
    axes = axes[0]
    for ax, size in zip(axes, sizes):
        ss = d[d["size"] == size]
        ref = ss[(ss.lambda_net == 0) & (ss.lambda_flow == 0) & (ss.config == "baseline")]
        c0 = ref["s2_dispatch_cost"].mean()
        if not c0 or np.isnan(c0):
            continue
        all_x = []
        for cfg in CFG_ORDER:
            g = (ss[ss.config == cfg]
                 .groupby(["lambda_net", "lambda_flow"])
                 .agg(m=(metric_col, "mean"), cost=("s2_dispatch_cost", "mean"))
                 .reset_index().sort_values("cost"))
            if g.empty:
                continue
            xv = g["m"] * (100 if pct_metric else 1)
            yv = (g["cost"] - c0) / c0 * 100
            all_x.extend(xv.tolist())
            ax.plot(xv, yv, MARKERS[cfg] + "--", lw=1.6, ms=7, alpha=0.9,
                    color=CFG_COLOR[cfg], label=CFG_LABEL[cfg])
            for wn, wf, x, y in zip(g.lambda_net, g.lambda_flow, xv, yv):
                ax.annotate(_wtag(wn, wf), (x, y), textcoords="offset points",
                            xytext=(4, 4), fontsize=6, color=CFG_COLOR[cfg])
        ax.axhline(0, color="gray", lw=1, alpha=0.5)
        # degenerate panel: metric identically (near) zero at every weight
        if all_x and (max(all_x) - min(all_x)) < 1e-6:
            ax.set_xlim(-5, 5)
            ax.text(0.5, 0.5, f"{metric_label} $= 0$ at every weight\n(structural single point of failure)",
                    transform=ax.transAxes, ha="center", va="center", fontsize=8,
                    color="#555", style="italic")
        ax.set_title(size)
        ax.set_xlabel(metric_label + (" (%)" if pct_metric else ""))
        ax.grid(True, ls=":", alpha=0.5)
    axes[0].set_ylabel("dispatch cost increase vs baseline (%)")
    handles = [Line2D([], [], marker=MARKERS[c], ls="--", color=CFG_COLOR[c],
                      label=CFG_LABEL[c]) for c in CFG_ORDER]
    fig.legend(handles=handles, title="packing", ncol=4,
               loc="upper center", bbox_to_anchor=(0.5, 0.045))
    fig.suptitle(f"Cost of disruption tolerance: {metric_label} against dispatch-cost "
                 "increase (point labels: $w_{net}/w_{flow}$)", fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.96))
    _save(fig, stem)


def single_instance_suite(d, metrics, stem, instance="industry_test_1"):
    """One instance, several metrics side by side: metric (x) vs relative dispatch-cost
    increase (y), per config, over the full flow-weight grid. `metrics` is a list of
    (column, label) pairs. Cost is relative to that instance's baseline cost-optimal plan."""
    g0 = d[d.instance == instance]
    c0 = g0[(g0.lambda_net == 0) & (g0.lambda_flow == 0)
            & (g0.config == "baseline")]["s2_dispatch_cost"].mean()
    fig, axes = plt.subplots(1, len(metrics), figsize=(5.6 * len(metrics), 5.2), squeeze=False)
    axes = axes[0]
    for ax, (col, lab) in zip(axes, metrics):
        for cfg in CFG_ORDER:
            g = (g0[g0.config == cfg]
                 .groupby(["lambda_net", "lambda_flow"])
                 .agg(m=(col, "mean"), cost=("s2_dispatch_cost", "mean"))
                 .reset_index().sort_values("cost"))
            if g.empty:
                continue
            xv, yv = g["m"] * 100, (g["cost"] - c0) / c0 * 100
            ax.plot(xv, yv, MARKERS[cfg] + "--", lw=1.6, ms=7, alpha=0.9,
                    color=CFG_COLOR[cfg], label=CFG_LABEL[cfg])
            for wn, wf, x, y in zip(g.lambda_net, g.lambda_flow, xv, yv):
                ax.annotate(_wtag(wn, wf), (x, y), textcoords="offset points",
                            xytext=(4, 4), fontsize=6, color=CFG_COLOR[cfg])
        ax.axhline(0, color="gray", lw=1, alpha=0.5)
        ax.set_title(lab); ax.set_xlabel(lab + " (%)"); ax.grid(True, ls=":", alpha=0.5)
    axes[0].set_ylabel("dispatch cost increase vs baseline (%)")
    handles = [Line2D([], [], marker=MARKERS[c], ls="--", color=CFG_COLOR[c],
                      label=CFG_LABEL[c]) for c in CFG_ORDER]
    fig.legend(handles=handles, title="packing", ncol=4,
               loc="upper center", bbox_to_anchor=(0.5, 0.045))
    name = "industrial" if instance.startswith("industry") else instance
    fig.suptitle(f"Cost of disruption tolerance on the {name} instance "
                 "(point labels: $w_{net}/w_{flow}$)", fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.96))
    _save(fig, stem)


def size_suite(d, size, metrics, stem):
    """All instances of one size (seed-averaged): metric (x) vs relative dispatch-cost
    increase (y), per config, over the flow-weight grid present in `d`. `metrics` is a list
    of (column, label) pairs. Cost is relative to the size's baseline cost-optimal plan."""
    g0 = d[d["size"] == size]
    c0 = g0[(g0.lambda_net == 0) & (g0.lambda_flow == 0)
            & (g0.config == "baseline")]["s2_dispatch_cost"].mean()
    fig, axes = plt.subplots(1, len(metrics), figsize=(5.6 * len(metrics), 5.2), squeeze=False)
    axes = axes[0]
    for ax, (col, lab) in zip(axes, metrics):
        for cfg in CFG_ORDER:
            g = (g0[g0.config == cfg]
                 .groupby(["lambda_net", "lambda_flow"])
                 .agg(m=(col, "mean"), cost=("s2_dispatch_cost", "mean"))
                 .reset_index().sort_values("cost"))
            if g.empty:
                continue
            xv, yv = g["m"] * 100, (g["cost"] - c0) / c0 * 100
            ax.plot(xv, yv, MARKERS[cfg] + "--", lw=1.6, ms=7, alpha=0.9,
                    color=CFG_COLOR[cfg], label=CFG_LABEL[cfg])
            for wn, wf, x, y in zip(g.lambda_net, g.lambda_flow, xv, yv):
                ax.annotate(_wtag(wn, wf), (x, y), textcoords="offset points",
                            xytext=(4, 4), fontsize=6, color=CFG_COLOR[cfg])
        ax.axhline(0, color="gray", lw=1, alpha=0.5)
        ax.set_title(lab); ax.set_xlabel(lab + " (%)"); ax.grid(True, ls=":", alpha=0.5)
    axes[0].set_ylabel("dispatch cost increase vs baseline (%)")
    handles = [Line2D([], [], marker=MARKERS[c], ls="--", color=CFG_COLOR[c],
                      label=CFG_LABEL[c]) for c in CFG_ORDER]
    fig.legend(handles=handles, title="Packing configuration", ncol=4,
               loc="upper center", bbox_to_anchor=(0.5, 0.045))
    fig.suptitle(f"Cost of disruption tolerance on the {size} instances",
                 fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.96))
    _save(fig, stem)


def ralpha_packing_profile(d, size, stem, alphas=(0.2, 0.4, 0.6, 0.8)):
    """Fixed cost-optimal flow (lambda_net = lambda_flow = 0): R_alpha against the surviving
    fraction alpha, one line per packing config. With the flow held fixed the network weight
    cannot act, so the packing ordering is visible directly. Single and global panels."""
    g0 = d[(d["size"] == size) & (d.lambda_net == 0) & (d.lambda_flow == 0)]
    xs = [a * 100 for a in alphas]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, mode in zip(axes, ["single", "global"]):
        for cfg in CFG_ORDER:
            gg = g0[g0.config == cfg]
            ys = [gg[f"r_alpha_{mode}_{a}"].mean() * 100 for a in alphas]
            ax.plot(xs, ys, MARKERS[cfg] + "-", lw=1.7, ms=7,
                    color=CFG_COLOR[cfg], label=CFG_LABEL[cfg])
        ax.set_title(f"{mode} scope")
        ax.set_xlabel(r"surviving fraction $\alpha$ (%)")
        ax.grid(True, ls=":", alpha=0.5)
    axes[0].set_ylabel(r"$R_\alpha$ (%)")
    handles = [Line2D([], [], marker=MARKERS[c], ls="-", color=CFG_COLOR[c],
                      label=CFG_LABEL[c]) for c in CFG_ORDER]
    fig.legend(handles=handles, title="packing", ncol=4,
               loc="upper center", bbox_to_anchor=(0.5, 0.04))
    fig.suptitle(r"Partial-loss resilience $R_\alpha$ by packing at the fixed cost-optimal "
                 f"flow ({size} instances)", fontweight="bold")
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _save(fig, stem)


def main():
    d = _prep(pd.read_csv(RES / "suite_consolidated.csv"))
    wnet = lambda x: x[x.lambda_flow == 0]                       # w_net lever only
    wnet_sm = lambda x: wnet(x)[wnet(x)["size"].isin(["small", "medium"])]
    jobs = [("nri", "NRI", "tradeoff_nri", wnet),
            ("cov_cvar10", r"CVaR$_{10}$", "tradeoff_cvar10", wnet),
            ("r_tr", r"$R_{TR}$", "tradeoff_rtr", wnet_sm)]
    for col, lab, stem, filt in jobs:
        try:
            tradeoff(filt(d), col, lab, stem); print(f"  [ok] {stem}")
        except Exception as e:
            print(f"  [FAIL] {stem}: {type(e).__name__}: {e}")
    try:
        single_instance_suite(wnet(d), [("nri", "NRI"), ("cov_cvar10", r"CVaR$_{10}$")],
                              "tradeoff_industry_nri_cvar")
        print("  [ok] tradeoff_industry_nri_cvar")
    except Exception as e:
        print(f"  [FAIL] tradeoff_industry_nri_cvar: {type(e).__name__}: {e}")
    try:
        size_suite(wnet(d), "small",
                   [("r_alpha_single_0.2", r"$R_\alpha$ single ($\alpha{=}0.2$)"),
                    ("r_alpha_global_0.2", r"$R_\alpha$ global ($\alpha{=}0.2$)")],
                   "tradeoff_small_ralpha02")
        print("  [ok] tradeoff_small_ralpha02")
    except Exception as e:
        print(f"  [FAIL] tradeoff_small_ralpha02: {type(e).__name__}: {e}")
    try:
        size_suite(wnet(d), "small",
                   [("r_alpha_single_0.4", r"$R_\alpha$ single ($\alpha{=}0.4$)"),
                    ("r_alpha_global_0.4", r"$R_\alpha$ global ($\alpha{=}0.4$)")],
                   "tradeoff_small_ralpha04")
        print("  [ok] tradeoff_small_ralpha04")
    except Exception as e:
        print(f"  [FAIL] tradeoff_small_ralpha04: {type(e).__name__}: {e}")
    try:
        ralpha_packing_profile(d, "small", "ralpha_packing_profile_small")
        print("  [ok] ralpha_packing_profile_small")
    except Exception as e:
        print(f"  [FAIL] ralpha_packing_profile_small: {type(e).__name__}: {e}")
    # NRI_alpha (expected partial-loss): single is flat, global separates by packing
    for size in ["small", "medium"]:
        try:
            size_suite(wnet(d), size,
                       [("nri_alpha_single_0.8", r"$\mathrm{NRI}_\alpha$ single ($\alpha{=}0.8$)"),
                        ("nri_alpha_global_0.8", r"$\mathrm{NRI}_\alpha$ global ($\alpha{=}0.8$)")],
                       f"tradeoff_{size}_nrialpha08")
            print(f"  [ok] tradeoff_{size}_nrialpha08")
        except Exception as e:
            print(f"  [FAIL] tradeoff_{size}_nrialpha08: {type(e).__name__}: {e}")
    print(f"-> {FIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
