"""Reporting figures for the resilience study. Reads the consolidated suite CSV plus
the resource / dose-response / strategy probes, writes PNGs to results/figures/.

    PYTHONPATH=src .venv/bin/python -m multibatch.experiments.milp_resilience.plots
"""
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from multibatch.experiments.milp_resilience import style
from multibatch.experiments.milp_resilience.style import (
    RES, FIG, SOLVER_COLOR, save, short)
from multibatch.experiments.milp_resilience.style import CFG_COLOR as C

style.apply()


def fig1_packing_effect(df):
    """Single-trip resilience: baseline vs conc_w8 across instances (milp, flow=(0,0))."""
    d = df[(df.flow_solver == "milp") & (df.w_net == 0) & (df.w_flow == 0)]
    piv_n = d.pivot_table(index="instance", columns="config", values="nri")
    piv_c = d.pivot_table(index="instance", columns="config", values="cov_cvar10")
    insts = sorted(piv_n.index, key=lambda s: (not s.startswith("industry"), s))
    x = np.arange(len(insts)); w = 0.38
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for ax, piv, lab in [(axes[0], piv_n, "NRI (single-trip)"),
                         (axes[1], piv_c, "CVaR$_{10}$ coverage (single-trip)")]:
        b = [piv.loc[i, "baseline"] for i in insts]
        c = [piv.loc[i, "conc_w8"] for i in insts]
        ax.bar(x - w/2, b, w, label="baseline", color=C["baseline"])
        ax.bar(x + w/2, c, w, label="conc_w8", color=C["conc_w8"])
        wins = sum(ci > bi + 1e-9 for bi, ci in zip(b, c))
        ax.set_ylabel(lab)
        ax.set_title(f"conc_w8 beats baseline on {wins}/{len(insts)} instances", fontsize=10)
        ax.legend(loc="lower right", ncol=2)
        ax.set_ylim(min(min(b), min(c)) - 0.03, 1.005)
    axes[1].set_xticks(x); axes[1].set_xticklabels([short(i) for i in insts], rotation=40, ha="right")
    fig.suptitle("Packing soft constraints improve single-trip resilience", fontweight="bold")
    fig.tight_layout(); save(fig, "fig1_packing_single_trip")


def fig2_asp_vs_milp(df):
    """Flow solve time: ASP vs MILP (layered; industry is MILP-only)."""
    d = df[(df.w_net == 0) & (df.w_flow == 0)].drop_duplicates(["instance", "flow_solver"])
    piv = d.pivot_table(index="instance", columns="flow_solver", values="s1_time")
    piv = piv.dropna(subset=["asp", "milp"], how="any")
    insts = sorted(piv.index)
    x = np.arange(len(insts)); w = 0.38
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - w/2, piv["milp"], w, label="MILP flow", color=SOLVER_COLOR["milp"])
    ax.bar(x + w/2, piv["asp"], w, label="ASP flow", color=SOLVER_COLOR["asp"])
    ax.set_yscale("log"); ax.set_ylabel("flow solve time (s, log)")
    sp = (piv["asp"] / piv["milp"]).mean()
    ax.set_title(f"MILP flow is ~{sp:.0f}× faster than ASP (ASP hits the 120s cap)", fontsize=10)
    ax.set_xticks(x); ax.set_xticklabels([short(i) for i in insts], rotation=40, ha="right")
    ax.legend()
    fig.suptitle("Flow solve time: MILP vs ASP", fontweight="bold")
    fig.tight_layout(); save(fig, "fig2_asp_vs_milp")


def fig3_flow_lever_tradeoff(df):
    """Industry: cost vs resilience as flow-redundancy (w_flow) rises, per packing."""
    d = df[(df.instance == "industry_test_1") & (df.w_net == 0)].copy()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for cfg in ["baseline", "conc_w8", "full_w8_8"]:
        s = d[d.config == cfg].sort_values("w_flow")
        axes[0].plot(s.w_flow, s.cov_cvar10, "o-", color=C[cfg], label=cfg)
        axes[1].plot(s.w_flow, s.nri_worst, "o-", color=C[cfg], label=cfg)
    # cost annotation (flow_cost is per flow point, shared across configs)
    fc = d.drop_duplicates("w_flow").sort_values("w_flow")
    ax2 = axes[0].twinx()
    ax2.plot(fc.w_flow, fc.flow_cost / 1e6, "k--s", alpha=0.6, label="flow cost")
    ax2.set_ylabel("flow cost (millions)")
    for ax, lab in [(axes[0], "CVaR$_{10}$ coverage"), (axes[1], "worst-case NRI")]:
        ax.set_xlabel("flow-redundancy weight  $w_{flow}$ (abs)"); ax.set_ylabel(lab); ax.legend(loc="lower right")
    axes[0].set_title("Tail resilience + flow cost vs redundancy")
    axes[1].set_title("Worst-case resilience vs redundancy")
    fig.suptitle("Industry: flow redundancy lifts worst-case resilience but at rising cost",
                 fontweight="bold")
    fig.tight_layout(); save(fig, "fig3_flow_lever_tradeoff")


def fig4_network_resource(rr):
    """Network-level R_resource vs arc-level R_TR, plus expected/tail, at flow=(0,0)."""
    d = rr[(rr.w_net == 0) & (rr.w_flow == 0)].drop_duplicates("instance")
    insts = sorted(d.instance, key=lambda s: (not s.startswith("industry"), s))
    d = d.set_index("instance").loc[insts]
    x = np.arange(len(insts)); w = 0.27
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    axes[0].bar(x - w, d.r_tr_arc, w, label="R_TR (arc-level)", color="#56B4E9")
    axes[0].bar(x, d.r_resource, w, label="R_resource (worst, network)", color="#D55E00")
    axes[0].set_ylabel("worst-case coverage")
    axes[0].set_title("Losing a whole transport resource is far worse than losing one arc")
    axes[0].legend()
    axes[1].bar(x - w/2, d.nri_resource, w, label="NRI_resource (expected)", color="#0072B2")
    axes[1].bar(x + w/2, d.cvar_resource, w, label="CVaR_resource (worst-30%)", color="#E69F00")
    axes[1].set_ylabel("served fraction")
    axes[1].set_title("Network-level resilience distribution (expected & tail)")
    axes[1].legend()
    axes[1].set_xticks(x); axes[1].set_xticklabels([short(i) for i in insts], rotation=40, ha="right")
    fig.suptitle("Network-level resilience: entire-transport-resource loss", fontweight="bold")
    fig.tight_layout(); save(fig, "fig4_network_resource")


def fig5_dose_response(dose):
    """Industry w_conc dose-response: resilience vs cost_saving (the knee)."""
    d = dose[dose.config.str.startswith(("baseline", "conc"))].copy()
    d["wc"] = d["w_conc"].astype(float)
    d = d.sort_values("wc")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(d.wc, d.cov_cvar10, "o-", color="#0072B2", label="CVaR$_{10}$ coverage")
    ax.set_xlabel("anti-concentration weight  $w_{conc}$"); ax.set_ylabel("CVaR$_{10}$ coverage", color="#0072B2")
    ax2 = ax.twinx()
    ax2.plot(d.wc, d.cost_saving / 1e3, "s--", color="#D55E00", label="cost saving")
    ax2.set_ylabel("packing cost saving (thousands)", color="#D55E00")
    ax.axvspan(2, 4, color="green", alpha=0.08); ax.text(3, ax.get_ylim()[0], " knee", color="green")
    ax.set_title("Industry dose-response: resilience saturates by $w_{conc}\\approx2$–4")
    fig.suptitle("Anti-concentration dose-response", fontweight="bold")
    fig.tight_layout(); save(fig, "fig5_dose_response")


def fig6_strategy_artefact(sp):
    """conc_w8 CVaR_alpha delta vs baseline, per survivor strategy (the artefact)."""
    alphas = [0.2, 0.4, 0.6, 0.8]
    strs = ["heaviest", "first", "last"]
    base = sp[sp.config == "baseline"].set_index(["instance", "strategy"])
    conc = sp[sp.config == "conc_w8"].set_index(["instance", "strategy"])
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(alphas)); w = 0.26
    col = {"heaviest": "#D55E00", "first": "#0072B2", "last": "#009E73"}
    for j, st in enumerate(strs):
        deltas = []
        for a in alphas:
            c = conc.xs(st, level="strategy")[f"cvar_alpha_{a}"]
            b = base.xs(st, level="strategy")[f"cvar_alpha_{a}"]
            deltas.append((c - b).mean())
        ax.bar(x + (j-1)*w, deltas, w, label=st, color=col[st])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels([f"α={a}" for a in alphas])
    ax.set_ylabel("mean Δ CVaR$_α$ (conc_w8 − baseline)")
    ax.set_title("Partial-loss verdict flips with survivor strategy: only 'heaviest' shows harm")
    ax.legend(title="survivor strategy")
    fig.suptitle("Strategy artefact in the parametric (α) resilience axis", fontweight="bold")
    fig.tight_layout(); save(fig, "fig6_strategy_artefact")


def main():
    df = pd.read_csv(RES / "suite_consolidated.csv")
    rr = pd.read_csv(RES / "resource_resilience.csv")
    figs = [("fig1", fig1_packing_effect, df), ("fig2", fig2_asp_vs_milp, df),
            ("fig3", fig3_flow_lever_tradeoff, df), ("fig4", fig4_network_resource, rr)]
    dose_p = RES / "suite_industry_doseB.csv"
    if dose_p.exists():
        figs.append(("fig5", fig5_dose_response, pd.read_csv(dose_p)))
    sp_p = RES / "strategy_probe.csv"
    if sp_p.exists():
        figs.append(("fig6", fig6_strategy_artefact, pd.read_csv(sp_p)))
    for name, fn, data in figs:
        try:
            fn(data); print(f"  [ok] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
    print(f"-> {FIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
