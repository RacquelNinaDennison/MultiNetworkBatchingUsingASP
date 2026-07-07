"""Cost-vs-resilience figures under the two levers (network exposure w_net and flow
redundancy w_flow) crossed with the packing configuration. The question: as flow cost
rises with the levers, which resilience metric (NRI single-trip, R_alpha partial-loss,
CVaR10 tail) responds, and is it the lever or the packing that buys it?

Reads suite_consolidated.csv, writes lever_*.{png,pdf} to results/figures/.

    PYTHONPATH=src .venv/bin/python -m multibatch.experiments.milp_resilience.plots_levers
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

# marker by network-exposure setting
NET_MARK = {0.0: "o", 4.0: "*"}
NET_LABEL = {0.0: r"$w_{net}=0$", 4.0: r"$w_{net}=4\lambda$ (network lever)"}


def _prep(df, solver="milp"):
    d = df[df.flow_solver == solver].copy()
    d["grp"] = np.where(d.instance.str.startswith("industry"), "industry",
                        np.where(d.instance.str.contains("medium"), "medium", "small"))
    opt = (d[(d.lambda_net == 0) & (d.lambda_flow == 0)]
           .groupby("instance").flow_cost.first())
    d["cost_rise"] = (d.flow_cost / d.instance.map(opt) - 1) * 100
    return d


# ---------------------------------------------------------------------------
def lever_layered(d):
    """Layered (mean over 5 seeds): flow-cost rise vs three metrics, coloured by
    packing config, marker by network lever. One row per size group."""
    metrics = [("nri", "NRI (single-trip)", (0.925, 0.952)),
               ("r_alpha_single_0.4", r"$R_\alpha$ (partial-loss, $\alpha{=}0.4$)", (0.40, 0.76)),
               ("cov_cvar10", r"CVaR$_{10}$ (tail coverage)", (0.78, 0.875))]
    groups = [("medium", "Layered medium"), ("small", "Layered small")]
    fig, axes = plt.subplots(len(groups), len(metrics), figsize=(12, 7), sharex="row")
    for r, (grp, gtitle) in enumerate(groups):
        g = (d[d.grp == grp]
             .groupby(["config", "lambda_net", "lambda_flow"])
             .agg(cost_rise=("cost_rise", "mean"),
                  **{m: (m, "mean") for m, _, _ in metrics})
             .reset_index())
        for c, (m, mlab, ylim) in enumerate(metrics):
            ax = axes[r, c]
            for cfg in CFG_ORDER:
                for net, mk in NET_MARK.items():
                    s = g[(g.config == cfg) & (g.lambda_net == net)].sort_values("cost_rise")
                    if s.empty:
                        continue
                    ax.plot(s.cost_rise, s[m], mk, color=CFG_COLOR[cfg],
                            ms=9 if mk == "*" else 6, alpha=0.9,
                            mec="k" if mk == "*" else "none", mew=0.4)
            if r == 0:
                ax.set_title(mlab, fontsize=10)
            if c == 0:
                ax.set_ylabel(f"{gtitle}\n", fontsize=10)
            ax.set_ylim(*ylim)
            if r == len(groups) - 1:
                ax.set_xlabel("flow cost increase vs optimal (%)")
    # one shared legend row: packing colours, then flow-lever markers
    sep = Line2D([], [], ls="none", label="     ")
    cfg_handles = [Line2D([], [], marker="s", ls="none", color=CFG_COLOR[c],
                          label=CFG_LABEL[c]) for c in CFG_ORDER]
    net_handles = [Line2D([], [], marker=NET_MARK[n], ls="none", color="#444",
                          mec="k", label=NET_LABEL[n]) for n in NET_MARK]
    fig.legend(handles=cfg_handles + [sep] + net_handles, ncol=7,
               loc="upper center", bbox_to_anchor=(0.5, 0.05),
               columnspacing=1.4, handletextpad=0.4)
    fig.suptitle("Cost of resilience under the flow levers: packing buys NRI, the "
                 "network lever buys $R_\\alpha$", fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.97))
    _save(fig, "lever_layered_cost_metrics")


def lever_industry(d):
    """Industry: flow cost (absolute, millions) vs NRI / CVaR10 / worst-case NRI,
    coloured by packing config, marker by network lever. R_alpha omitted (==0)."""
    g = d[d.instance == "industry_test_1"].copy()
    g["flow_M"] = g.flow_cost / 1e6
    metrics = [("nri", "NRI (single-trip)", (0.980, 0.989)),
               ("cov_cvar10", r"CVaR$_{10}$ (tail coverage)", (0.78, 0.875)),
               ("nri_worst", "worst-case NRI", (0.88, 0.945))]
    fig, axes = plt.subplots(1, len(metrics), figsize=(12, 4.0))
    for c, (m, mlab, ylim) in enumerate(metrics):
        ax = axes[c]
        for cfg in CFG_ORDER:
            for net, mk in NET_MARK.items():
                s = g[(g.config == cfg) & (g.lambda_net == net)].sort_values("flow_M")
                if s.empty:
                    continue
                # connect the flow-redundancy sweep (net=0) with a faint line
                if net == 0.0:
                    ax.plot(s.flow_M, s[m], "-", color=CFG_COLOR[cfg], lw=1, alpha=0.5, zorder=1)
                ax.plot(s.flow_M, s[m], mk, color=CFG_COLOR[cfg],
                        ms=11 if mk == "*" else 6.5, alpha=0.9,
                        mec="k" if mk == "*" else "none", mew=0.4, zorder=2)
        ax.set_title(mlab, fontsize=10)
        ax.set_xlabel("flow cost (millions)")
        ax.set_ylim(*ylim)
    cfg_handles = [Line2D([], [], marker="s", ls="none", color=CFG_COLOR[c],
                          label=CFG_LABEL[c]) for c in CFG_ORDER]
    net_handles = [Line2D([], [], marker=NET_MARK[n], ls="none", color="#444",
                          mec="k", label=NET_LABEL[n]) for n in NET_MARK]
    leg1 = fig.legend(handles=cfg_handles + net_handles, ncol=6,
                      loc="upper center", bbox_to_anchor=(0.5, 0.04))
    fig.add_artist(leg1)
    fig.suptitle("Industry: resilience vs flow cost under network and redundancy levers",
                 fontweight="bold")
    fig.tight_layout(rect=(0, 0.08, 1, 0.96))
    _save(fig, "lever_industry_cost_metrics")


def ralpha_vs_wnet(d):
    """Isolated finding: R_alpha (partial-loss worst case) is bought by the network
    weight, not by packing. Layered only (R_alpha == 0 on industry). x = w_net setting,
    one line per packing config, panels per alpha level, mean +/- s.e. over seeds."""
    alphas = [0.2, 0.4, 0.6, 0.8]
    g = d[d.grp.isin(["medium", "small"]) & (d.lambda_flow == 0)].copy()
    fig, axes = plt.subplots(1, len(alphas), figsize=(13, 3.6), sharey=True)
    for c, a in enumerate(alphas):
        ax = axes[c]
        col = f"r_alpha_single_{a}"
        for cfg in CFG_ORDER:
            s = g[g.config == cfg]
            agg = s.groupby("lambda_net")[col].agg(["mean", "sem"]).reindex([0.0, 4.0])
            ax.errorbar([0, 1], agg["mean"], yerr=agg["sem"], marker="o", ms=6,
                        color=CFG_COLOR[cfg], capsize=3, lw=1.5,
                        label=CFG_LABEL[cfg] if c == 0 else None)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["$w_{net}=0$", r"$w_{net}=4\lambda$"])
        ax.set_xlim(-0.3, 1.3)
        ax.set_title(rf"$\alpha={a}$")
        if c == 0:
            ax.set_ylabel(r"$R_\alpha$ (single-mode, partial loss)")
    axes[0].legend(title="packing", loc="upper left")
    fig.suptitle(r"Partial-loss resilience $R_\alpha$ is bought by the network weight, "
                 "not by packing (layered, mean $\\pm$ s.e. over seeds)",
                 fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save(fig, "lever_ralpha_vs_wnet")


def main():
    df = pd.read_csv(RES / "suite_consolidated.csv")
    d = _prep(df)
    for name, fn in [("lever_layered", lever_layered), ("lever_industry", lever_industry),
                     ("lever_ralpha_vs_wnet", ralpha_vs_wnet)]:
        try:
            fn(d); print(f"  [ok] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
    print(f"-> {FIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
