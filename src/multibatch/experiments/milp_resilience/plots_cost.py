"""Cost-comparison figures, styled like the two-stage EDA (seaborn whitegrid /
colorblind). Reads suite_consolidated.csv, writes cost_*.png to results/figures/.

  cost1: Stage-1 flow vs Stage-2 packing dispatch cost, by instance (baseline vs conc)
  cost2: per-instance cost-saving %% heatmap (config x instance)
  cost3: "is packing earning its cost?" -- Δcost%% vs Δresilience vs baseline
  cost4: cost-vs-resilience frontier -- cost_saving %% vs CVaR10, configs connected

    PYTHONPATH=src .venv/bin/python -m multibatch.experiments.milp_resilience.plots_cost
"""
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from multibatch.experiments.milp_resilience import style
from multibatch.experiments.milp_resilience.style import (
    RES, FIG, save, short, inst_order)
from multibatch.experiments.milp_resilience.style import CFG_COLOR as CONFIG_COLOR
from multibatch.experiments.milp_resilience.style import CFG_ORDER as CONFIG_ORDER

style.apply()


def base(df):
    """Canonical flow point: MILP, cost-optimal flow (w_net=w_flow=0)."""
    d = df[(df.flow_solver == "milp") & (df.w_net == 0) & (df.w_flow == 0)].copy()
    d["save_pct"] = np.where(d.s1_dispatch_cost > 0,
                             d.cost_saving / d.s1_dispatch_cost * 100, np.nan)
    return d


def cost1_s1_vs_s2(d):
    """Stage-1 flow cost vs Stage-2 packing cost (baseline & conc), per instance."""
    insts = inst_order(d.instance.unique())
    piv = d.pivot_table(index="instance", columns="config", values="s2_dispatch_cost")
    s1 = d.groupby("instance").s1_dispatch_cost.first()
    # split industry (millions) from layered (thousands) into two panels for scale
    groups = [("industry", [i for i in insts if i.startswith("industry")]),
              ("layered (small + medium)", [i for i in insts if not i.startswith("industry")])]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [1, 6]})
    for ax, (title, gi) in zip(axes, groups):
        x = np.arange(len(gi)); w = 0.26
        ax.bar(x - 1.5*w, [s1[i] for i in gi], w, label="S1 flow (planned)", color="#444")
        ax.bar(x - 0.5*w, [piv.loc[i, "baseline"] for i in gi], w, label="S2 baseline", color=CONFIG_COLOR["baseline"])
        ax.bar(x + 0.5*w, [piv.loc[i, "conc_w8"] for i in gi], w, label="S2 conc_w8", color=CONFIG_COLOR["conc_w8"])
        ax.set_xticks(x); ax.set_xticklabels([short(i) for i in gi], rotation=40, ha="right")
        ax.set_title(title); ax.set_ylabel("dispatch cost")
    axes[1].legend(ncol=3, loc="upper right")
    fig.suptitle("Stage-1 flow vs Stage-2 packing dispatch cost (resilient packing saves less)",
                 fontweight="bold")
    fig.tight_layout(); save(fig, "cost1_s1_vs_s2")


def cost2_saving_heatmap(d):
    """Cost-saving % heatmap: config x instance."""
    insts = inst_order(d.instance.unique())
    piv = d.pivot_table(index="config", columns="instance", values="save_pct").reindex(
        index=CONFIG_ORDER, columns=insts)
    fig, ax = plt.subplots(figsize=(12, 3.6))
    sns.heatmap(piv, annot=True, fmt=".0f", cmap="YlGnBu", cbar_kws={"label": "cost saving (%)"},
                ax=ax, linewidths=0.5)
    ax.set_xticklabels([short(i) for i in insts], rotation=40, ha="right")
    ax.set_xlabel(""); ax.set_ylabel("")
    ax.set_title("Stage-2 cost saving vs the flow plan (%) — baseline saves most, resilience costs",
                 fontweight="bold")
    fig.tight_layout(); save(fig, "cost2_saving_heatmap")


def cost3_earning_quadrant(d):
    """Δ dispatch cost % vs Δ CVaR10 relative to baseline, per (instance, config)."""
    fig, ax = plt.subplots(figsize=(9, 6.5))
    for inst, g in d.groupby("instance"):
        g = g.set_index("config")
        if "baseline" not in g.index:
            continue
        b_cost, b_cv = g.loc["baseline", "s2_dispatch_cost"], g.loc["baseline", "cov_cvar10"]
        for cfg in ["hetero_w8", "conc_w8", "full_w8_8"]:
            if cfg not in g.index:
                continue
            dc = (g.loc[cfg, "s2_dispatch_cost"] - b_cost) / b_cost * 100
            dr = g.loc[cfg, "cov_cvar10"] - b_cv
            ax.scatter(dc, dr, color=CONFIG_COLOR[cfg], s=55, alpha=0.8,
                       edgecolor="k", linewidth=0.3)
    for cfg in ["hetero_w8", "conc_w8", "full_w8_8"]:
        ax.scatter([], [], color=CONFIG_COLOR[cfg], s=55, label=cfg)
    ax.axhline(0, color="k", lw=0.8); ax.axvline(0, color="k", lw=0.8)
    ax.set_xlabel("Δ dispatch cost vs baseline (%)  →  more expensive")
    ax.set_ylabel("Δ CVaR$_{10}$ resilience vs baseline  →  more resilient")
    ax.set_title("Is the packing earning its cost? (upper-right = pay more, get resilience)",
                 fontweight="bold")
    ax.legend(title="config")
    fig.tight_layout(); save(fig, "cost3_earning_quadrant")


def cost4_frontier(d):
    """Cost-vs-resilience frontier: cost_saving % (x) vs CVaR10 (y), configs connected."""
    insts = inst_order(d.instance.unique())
    fig, ax = plt.subplots(figsize=(9, 6.5))
    for inst in insts:
        g = d[d.instance == inst].set_index("config").reindex(CONFIG_ORDER)
        ax.plot(g.save_pct, g.cov_cvar10, "-", color="#ccc", lw=0.8, zorder=1)
        for cfg in CONFIG_ORDER:
            if cfg in g.index and pd.notna(g.loc[cfg, "save_pct"]):
                ax.scatter(g.loc[cfg, "save_pct"], g.loc[cfg, "cov_cvar10"],
                           color=CONFIG_COLOR[cfg], s=40, zorder=2, edgecolor="k", linewidth=0.3)
    for cfg in CONFIG_ORDER:
        ax.scatter([], [], color=CONFIG_COLOR[cfg], s=40, label=cfg)
    ax.set_xlabel("packing cost saving (% of flow cost)  →  cheaper")
    ax.set_ylabel("CVaR$_{10}$ coverage  →  more resilient")
    ax.set_title("Cost–resilience frontier across instances (each grey line = one instance)",
                 fontweight="bold")
    ax.legend(title="config")
    fig.tight_layout(); save(fig, "cost4_frontier")


def main():
    df = pd.read_csv(RES / "suite_consolidated.csv")
    d = base(df)
    for name, fn in [("cost1", cost1_s1_vs_s2), ("cost2", cost2_saving_heatmap),
                     ("cost3", cost3_earning_quadrant), ("cost4", cost4_frontier)]:
        try:
            fn(d); print(f"  [ok] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
    print(f"-> {FIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
