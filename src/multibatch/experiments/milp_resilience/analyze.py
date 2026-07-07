"""Turn suite.py CSV(s) into the thesis deliverables — tables + plots.

Generates, from one or more suite CSVs:
  1. WIN-RATE table   — per size, each config vs baseline: win-rate + mean Δ on
                        NRI / CVaR10 (overall + packing-addressable). [the claim]
  2. TRADE-OFF plot   — NRI & CVaR10 vs s2_dispatch_cost across w_conc. [price]
  3. TUNING plot      — NRI & CVaR10 vs w_conc / w_hetero. [find the knee]
  4. INTERACTION plot — packing gain & SPOF exposure vs w_flow. [does flow
                        redundancy unlock packing resilience] (needs >1 w_flow)
  5. SCALING table    — ASP vs MILP flow cost/feasibility by size. (needs both)
  6. SPOF panel       — frac_zero / worst-case / single-trip arcs vs w_flow.

Tables are printed and saved as CSV; plots saved as PNG.

Usage:
    uv run python -m multibatch.experiments.milp_resilience.analyze \
        --csv results/suite_milp.csv results/suite_asp.csv results/suite_industry.csv \
        --out-dir results/analysis
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

WIN_METRICS = ["nri", "cov_cvar10", "nri_addr", "cov_cvar10_addr"]
_SIZE_ORDER = ["paper", "small", "medium", "large", "xlarge", "industrylite", "industry"]


def size_of(inst: str) -> str:
    for s in ["industrylite", "industry", "xlarge", "large", "medium", "small", "paper"]:
        if s in inst:
            return s
    return "other"


def load(csv_paths: list[str]) -> pd.DataFrame:
    df = pd.concat([pd.read_csv(p) for p in csv_paths], ignore_index=True)
    df["size"] = df["instance"].map(size_of)
    num = WIN_METRICS + ["s2_dispatch_cost", "cov_frac_zero", "r_1", "r_tr",
                         "n_single_trip_arcs", "flow_cost", "cov_mean", "cov_median",
                         "cov_cvar10", "w_conc", "w_hetero", "w_net", "w_flow",
                         "lambda_net", "lambda_flow", "weight_normalizer"]
    num += [c for c in df.columns if c.startswith("r_alpha_")]
    for c in num:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _with_baseline_delta(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Attach <metric>_base and <metric>_d (delta vs the baseline packing within
    each (instance, lambda_net, lambda_flow, flow_solver) group, so the packing
    effect is isolated at a fixed network weighting)."""
    keys = ["instance", "lambda_net", "lambda_flow", "flow_solver"]
    base = df[df.config == "baseline"][keys + metrics].copy()
    base = base.rename(columns={m: f"{m}_base" for m in metrics})
    out = df.merge(base, on=keys, how="left")
    for m in metrics:
        out[f"{m}_d"] = out[m] - out[f"{m}_base"]
    return out


# ── 1. win-rate table ──────────────────────────────────────────────────

def win_rate_table(df: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    d = _with_baseline_delta(df, WIN_METRICS)
    d = d[d.config != "baseline"]
    rows = []
    for (size, config), g in d.groupby(["size", "config"]):
        row = {"size": size, "config": config, "n": len(g)}
        for m in WIN_METRICS:
            dd = g[f"{m}_d"].dropna()
            row[f"{m}_win"] = round((dd > 1e-9).mean(), 3) if len(dd) else None
            row[f"{m}_meanD"] = round(dd.mean(), 4) if len(dd) else None
        rows.append(row)
    tbl = pd.DataFrame(rows).sort_values(
        ["size", "config"], key=lambda s: s.map(lambda x: _SIZE_ORDER.index(x) if x in _SIZE_ORDER else 99))
    tbl.to_csv(out_dir / "table1_winrate.csv", index=False)
    print("\n=== 1. WIN-RATE vs baseline (win = config beats baseline) ===")
    with pd.option_context("display.width", 200, "display.max_columns", 30, "display.max_rows", 200):
        print(tbl.to_string(index=False))
    return tbl


# ── 1b. network-weighting effect on the full metric set ────────────────

def network_effect_table(df: pd.DataFrame, out_dir: Path) -> pd.DataFrame | None:
    """With packing held at baseline, show how every flow-level metric responds
    to the network weighting (w_net, and w_flow for MILP). Answers: 'if we turn on
    network weighting, how does it affect everything?'"""
    bp = df[df.config == "baseline"].copy()
    if bp.empty:
        print("\n(skipping network-effect table — no baseline rows)")
        return None
    metrics = [m for m in ["r_tr", "nri", "cov_cvar10", "cov_frac_zero",
                           "n_single_trip_arcs", "flow_cost", "w_net",
                           "r_alpha_single_0.2", "r_alpha_global_0.2"] if m in bp.columns]
    t = (bp.groupby(["size", "flow_solver", "lambda_net", "lambda_flow"])[metrics]
         .mean(numeric_only=True).reset_index())
    t["__so"] = t["size"].map(lambda x: _SIZE_ORDER.index(x) if x in _SIZE_ORDER else 99)
    t = t.sort_values(["__so", "flow_solver", "lambda_net", "lambda_flow"]).drop(columns="__so")
    t.to_csv(out_dir / "table7_network_effect.csv", index=False)
    print("\n=== 7. NETWORK-WEIGHTING EFFECT (baseline packing; metrics vs lambda_net / lambda_flow) ===")
    with pd.option_context("display.width", 220, "display.max_columns", 30, "display.max_rows", 300):
        print(t.round(4).to_string(index=False))
    return t


# ── 2+3. tuning / trade-off curves (the w_conc and w_hetero sweeps) ─────

def _sweep(df: pd.DataFrame, hold_zero: str, vary: str) -> pd.DataFrame:
    """Rows isolating one weight axis: e.g. hold w_hetero==0 and vary w_conc.
    Includes baseline (both 0). Averaged over seeds per size."""
    sub = df[(df[hold_zero] == 0)].copy()
    return (sub.groupby(["size", vary])
            .agg(nri=("nri", "mean"), cvar=("cov_cvar10", "mean"),
                 s2cost=("s2_dispatch_cost", "mean"), fz=("cov_frac_zero", "mean"))
            .reset_index())


def tuning_plots(df: pd.DataFrame, out_dir: Path) -> None:
    for axis, hold in [("w_conc", "w_hetero"), ("w_hetero", "w_conc")]:
        s = _sweep(df, hold, axis)
        if s[axis].nunique() < 2:
            continue
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
        for size, g in s.groupby("size"):
            g = g.sort_values(axis)
            a1.plot(g[axis], g.nri, marker="o", label=f"{size} NRI")
            a1.plot(g[axis], g.cvar, marker="s", ls="--", label=f"{size} CVaR10")
            a2.plot(g.s2cost, g.nri, marker="o", label=size)
        a1.set_xlabel(axis); a1.set_ylabel("resilience"); a1.set_title(f"Tuning: vs {axis}")
        a1.legend(fontsize=7); a1.grid(alpha=.3)
        a2.set_xlabel("s2_dispatch_cost"); a2.set_ylabel("NRI")
        a2.set_title(f"Trade-off: NRI vs cost ({axis} sweep)")
        a2.legend(fontsize=7); a2.grid(alpha=.3)
        fig.tight_layout()
        p = out_dir / f"fig_tuning_{axis}.png"
        fig.savefig(p, dpi=130); plt.close(fig)
        print(f"  saved {p}")


# ── 4+6. interaction & SPOF (needs >1 w_flow) ───────────────────────────

def interaction_and_spof(df: pd.DataFrame, out_dir: Path) -> None:
    if df.lambda_flow.nunique() < 2:
        print("\n(skipping interaction/SPOF plots — only one lambda_flow value)")
        return
    # best non-baseline NRI gain per (instance, lambda_flow)
    d = _with_baseline_delta(df, ["nri", "cov_cvar10"])
    d = d[d.config != "baseline"]
    gain = (d.groupby(["size", "lambda_flow"])
            .agg(nri_gain=("nri_d", "max"), cvar_gain=("cov_cvar10_d", "max"))
            .reset_index().rename(columns={"lambda_flow": "w_flow"}))
    spof = (df.groupby(["size", "lambda_flow"])
            .agg(frac_zero=("cov_frac_zero", "mean"),
                 single_arcs=("n_single_trip_arcs", "mean"),
                 worst=("r_1", "mean")).reset_index().rename(columns={"lambda_flow": "w_flow"}))
    spof.to_csv(out_dir / "table6_spof.csv", index=False)
    gain.to_csv(out_dir / "table4_interaction.csv", index=False)
    print("\n=== 4. INTERACTION: best packing gain vs w_flow ===")
    print(gain.to_string(index=False))
    print("\n=== 6. SPOF exposure vs w_flow ===")
    print(spof.to_string(index=False))

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    for size, g in gain.groupby("size"):
        a1.plot(g.w_flow, g.nri_gain, marker="o", label=f"{size} NRI gain")
    for size, g in spof.groupby("size"):
        a2.plot(g.w_flow, g.frac_zero, marker="s", label=f"{size} frac_zero")
    a1.set_xlabel("w_flow"); a1.set_ylabel("max packing NRI gain"); a1.set_title("Interaction")
    a1.legend(fontsize=7); a1.grid(alpha=.3)
    a2.set_xlabel("w_flow"); a2.set_ylabel("frac_zero (SPOF)"); a2.set_title("SPOF reduction")
    a2.legend(fontsize=7); a2.grid(alpha=.3)
    fig.tight_layout(); p = out_dir / "fig_interaction.png"
    fig.savefig(p, dpi=130); plt.close(fig)
    print(f"  saved {p}")


# ── 5. scaling table (ASP vs MILP flow) ─────────────────────────────────

def scaling_table(df: pd.DataFrame, out_dir: Path) -> None:
    if df.flow_solver.nunique() < 2:
        print("\n(skipping scaling table — need both asp and milp flow_solver runs)")
        return
    flows = df.drop_duplicates(["instance", "flow_solver", "w_flow"]).copy()
    flows["opt"] = flows["flow_optimum"].astype(str).str.lower().isin(["true", "1"])
    t = (flows.groupby(["size", "flow_solver"])
         .agg(n=("instance", "nunique"),
              mean_flow_cost=("flow_cost", "mean"),
              frac_optimum=("opt", "mean"))
         .reset_index())
    t.to_csv(out_dir / "table5_scaling.csv", index=False)
    print("\n=== 5. SCALING: ASP vs MILP flow ===")
    print(t.to_string(index=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Analyse suite CSV(s) into thesis deliverables")
    p.add_argument("--csv", nargs="+", required=True)
    p.add_argument("--out-dir",
                   default=str(Path(__file__).resolve().parent / "results" / "analysis"))
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load(args.csv)
    print(f"loaded {len(df)} rows; sizes={sorted(df['size'].unique())}; "
          f"flow_solvers={sorted(df.flow_solver.unique())}; w_flow={sorted(df.w_flow.unique())}")

    win_rate_table(df, out_dir)
    network_effect_table(df, out_dir)
    tuning_plots(df, out_dir)
    interaction_and_spof(df, out_dir)
    scaling_table(df, out_dir)
    print(f"\nAll deliverables -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
