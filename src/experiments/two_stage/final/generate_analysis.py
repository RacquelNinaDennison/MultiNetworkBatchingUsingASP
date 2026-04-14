#!/usr/bin/env python3
"""
generate_analysis.py
====================
Generate analysis tables for the thesis from the full R_alpha experiment CSVs.

Outputs CSV summary tables and prints LaTeX-ready values to stdout.

Usage:
    uv run python src/experiments/two_stage/final/generate_analysis.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR = RESULTS_DIR / "analysis"

SWEEP_FILES: dict[str, str] = {
    "paper":        "sweep_paper_full_alpha.csv",
    "small":        "sweep_small_full_ra.csv",
    "medium":       "sweep_medium_full_ra.csv",
    "large":        "sweep_large.csv",
    "xlarge":       "sweep_xlarge_full_ra.csv",
    "industrylite": "sweep_industrylite_full_ra.csv",
    "industry":     "sweep_industry_original_heavy_again.csv",
}

SIZE_ORDER = list(SWEEP_FILES.keys())
CONFIG_ORDER = ["off_off", "hetero", "conc", "both"]
ALPHAS = [0.2, 0.4, 0.6, 0.8]

BEST_WEIGHT: dict[str, int] = {
    "paper": 1000,
    "small": 750,
    "medium": 750,
    "large": 300,
    "xlarge": 1000,
    "industrylite": 1000,
    "industry": 0,
}


def load_all() -> pd.DataFrame:
    frames = []
    for label, fname in SWEEP_FILES.items():
        path = RESULTS_DIR / fname
        if not path.exists():
            print(f"  SKIP {label}: file not found ({fname})")
            continue
        df = pd.read_csv(path)
        df = df[df["status"] == "OK"].copy()
        df["size_label"] = label
        frames.append(df)
        print(f"  Loaded {label}: {len(df)} OK rows from {fname}")

    if not frames:
        raise SystemExit("No data files found.")

    df = pd.concat(frames, ignore_index=True)

    numeric_cols = [
        "r_tr", "r_1", "k_1", "nominal_cost", "s1_dispatch_cost",
        "s2_dispatch_cost", "cost_saving", "mono_count",
        "concentrated_count", "weight", "s1_time", "s2_time",
        "first_r_tr", "first_r_1", "first_k_1",
        "first_s1_time", "first_s2_time",
        "first_s1_cost", "first_s2_cost",
        "first_mono_count", "first_concentrated_count",
        "first_s1_dispatch_cost", "first_s2_dispatch_cost",
    ]
    for strat in ["heaviest", "first", "last"]:
        for mode in ["single", "global"]:
            for a in ALPHAS:
                numeric_cols.append(f"r_{strat}_{mode}_{a}")
                numeric_cols.append(f"first_r_{strat}_{mode}_{a}")

    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def _has_ralpha(df: pd.DataFrame) -> bool:
    return "r_heaviest_single_0.8" in df.columns


def _has_first(df: pd.DataFrame) -> bool:
    return "first_r_tr" in df.columns


def _sort_df(df: pd.DataFrame) -> pd.DataFrame:
    size_map = {s: i for i, s in enumerate(SIZE_ORDER)}
    cfg_map = {c: i for i, c in enumerate(CONFIG_ORDER)}
    df = df.copy()
    df["_sz"] = df["size_label"].map(size_map).fillna(99)
    sort_cols = ["_sz", "weight"]
    drop_cols = ["_sz"]
    if "s2_config" in df.columns:
        df["_cfg"] = df["s2_config"].map(cfg_map).fillna(99)
        sort_cols.append("_cfg")
        drop_cols.append("_cfg")
    df = df.sort_values(sort_cols).drop(columns=drop_cols)
    return df


# ── Section 5.2.1: R_TR by weight ──────────────────────────────────────

def table_rtr_by_weight(df: pd.DataFrame) -> pd.DataFrame:
    """R_TR and costs by size x weight (averaged over configs + seeds)."""
    agg_dict: dict = {
        "r_tr": ("r_tr", "mean"),
        "r_1": ("r_1", "mean"),
        "nominal_cost": ("nominal_cost", "mean"),
        "s1_dispatch": ("s1_dispatch_cost", "mean"),
        "s2_dispatch": ("s2_dispatch_cost", "mean"),
        "n": ("r_tr", "count"),
    }
    if _has_ralpha(df):
        agg_dict["ra08_single"] = ("r_heaviest_single_0.8", "mean")
        agg_dict["ra08_global"] = ("r_heaviest_global_0.8", "mean")

    grp = df.groupby(["size_label", "weight"]).agg(**agg_dict).reset_index()

    grp["saving_pct"] = (
        (grp["s1_dispatch"] - grp["s2_dispatch"]) / grp["s1_dispatch"] * 100
    ).round(1)

    round_cols = ["r_tr", "r_1"]
    if "ra08_single" in grp.columns:
        round_cols += ["ra08_single", "ra08_global"]
    for c in round_cols:
        grp[c] = grp[c].round(3)
    for c in ["nominal_cost", "s1_dispatch", "s2_dispatch"]:
        grp[c] = grp[c].round(0)

    return _sort_df(grp)


# ── Section 5.2.2: Packing config at w=0 and w=best ────────────────────

def table_packing_at_weight(df: pd.DataFrame, weight: int | None = None,
                             use_best: bool = False) -> pd.DataFrame:
    """Packing config effect at a specific weight or best weight per size."""
    has_ra = _has_ralpha(df)
    rows = []
    for size in SIZE_ORDER:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        w = BEST_WEIGHT.get(size, 0) if use_best else (weight or 0)
        wsub = sub[sub["weight"] == w]
        if wsub.empty:
            continue
        for cfg in CONFIG_ORDER:
            csub = wsub[wsub["s2_config"] == cfg]
            if csub.empty:
                continue
            row_dict: dict = {
                "size_label": size,
                "weight": w,
                "s2_config": cfg,
                "r_1": csub["r_1"].mean(),
                "mono": csub["mono_count"].mean(),
                "s2_dispatch": csub["s2_dispatch_cost"].mean(),
                "s1_dispatch": csub["s1_dispatch_cost"].mean(),
                "n_seeds": csub["seed"].nunique(),
            }
            if has_ra and "r_heaviest_single_0.8" in csub.columns:
                row_dict["ra08_single"] = csub["r_heaviest_single_0.8"].mean()
                row_dict["ra08_global"] = csub["r_heaviest_global_0.8"].mean()
            rows.append(row_dict)

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["saving_pct"] = (
        (out["s1_dispatch"] - out["s2_dispatch"]) / out["s1_dispatch"] * 100
    ).round(1)

    off = out[out["s2_config"] == "off_off"].set_index("size_label")
    for idx, row in out.iterrows():
        sz = row["size_label"]
        if sz in off.index and row["s2_config"] != "off_off":
            base = off.loc[sz]
            out.loc[idx, "delta_r1"] = round(row["r_1"] - base["r_1"], 4)
            if "ra08_single" in out.columns:
                out.loc[idx, "delta_ra08s"] = round(
                    row.get("ra08_single", np.nan) - base.get("ra08_single", np.nan), 4
                )
                out.loc[idx, "delta_ra08g"] = round(
                    row.get("ra08_global", np.nan) - base.get("ra08_global", np.nan), 4
                )

    for c in ["r_1"]:
        out[c] = out[c].round(3)
    if "ra08_single" in out.columns:
        out["ra08_single"] = out["ra08_single"].round(3)
        out["ra08_global"] = out["ra08_global"].round(3)
    out["mono"] = out["mono"].round(1)
    out["s2_dispatch"] = out["s2_dispatch"].round(0)

    return out


# ── Section 5.2.3: Full R_alpha sweep ──────────────────────────────────

def table_ralpha_sweep(df: pd.DataFrame, scope: str = "single") -> pd.DataFrame:
    """Full R_alpha sweep (heaviest strategy) by size x weight x config."""
    agg_cols = {}
    for a in ALPHAS:
        col = f"r_heaviest_{scope}_{a}"
        if col not in df.columns:
            return pd.DataFrame()
        agg_cols[f"a{a}"] = (col, "mean")

    grp = df.groupby(["size_label", "weight", "s2_config"]).agg(**agg_cols).reset_index()
    for a in ALPHAS:
        grp[f"a{a}"] = grp[f"a{a}"].round(3)

    return _sort_df(grp)


# ── Section 5.2.4: First vs Best ──────────────────────────────────────

def table_first_vs_best(df: pd.DataFrame) -> pd.DataFrame:
    """First solution vs best solution comparison."""
    if not _has_first(df):
        return pd.DataFrame()

    agg_dict: dict = {
        "best_rtr": ("r_tr", "mean"),
        "first_rtr": ("first_r_tr", "mean"),
        "best_r1": ("r_1", "mean"),
        "first_r1": ("first_r_1", "mean"),
        "first_s1_time": ("first_s1_time", "mean"),
        "best_s1_time": ("s1_time", "mean"),
        "first_s2_time": ("first_s2_time", "mean"),
        "best_s2_time": ("s2_time", "mean"),
    }
    if _has_ralpha(df):
        agg_dict["best_ra08s"] = ("r_heaviest_single_0.8", "mean")
        agg_dict["first_ra08s"] = ("first_r_heaviest_single_0.8", "mean")
        agg_dict["best_ra08g"] = ("r_heaviest_global_0.8", "mean")
        agg_dict["first_ra08g"] = ("first_r_heaviest_global_0.8", "mean")

    # Only include rows that have first-solution data
    sub = df.dropna(subset=["first_r_tr"])
    if sub.empty:
        return pd.DataFrame()

    grp = sub.groupby(["size_label", "weight", "s2_config"]).agg(**agg_dict).reset_index()

    grp["delta_rtr"] = (grp["best_rtr"] - grp["first_rtr"]).round(4)
    grp["delta_r1"] = (grp["best_r1"] - grp["first_r1"]).round(4)

    for c in grp.columns:
        if c not in ("size_label", "weight", "s2_config"):
            grp[c] = grp[c].round(3)

    return _sort_df(grp)


# ── Section 5.2.5: Scalability ─────────────────────────────────────────

def table_scalability(df: pd.DataFrame) -> pd.DataFrame:
    """Solve time and optimality by size."""
    grp = df.groupby("size_label").agg(
        s1_time=("s1_time", "mean"),
        s2_time=("s2_time", "mean"),
        s1_opt=("s1_optimal", lambda x: (x == True).mean() * 100),
        s2_opt=("s2_optimal", lambda x: (x == True).mean() * 100),
        r_tr=("r_tr", "mean"),
        r_1=("r_1", "mean"),
        n=("r_tr", "count"),
    ).reset_index()

    size_map = {s: i for i, s in enumerate(SIZE_ORDER)}
    grp["_sz"] = grp["size_label"].map(size_map).fillna(99)
    grp = grp.sort_values("_sz").drop(columns=["_sz"])

    grp["s1_time"] = grp["s1_time"].round(1)
    grp["s2_time"] = grp["s2_time"].round(1)
    grp["s1_opt"] = grp["s1_opt"].round(0)
    grp["s2_opt"] = grp["s2_opt"].round(0)
    grp["r_tr"] = grp["r_tr"].round(3)
    grp["r_1"] = grp["r_1"].round(3)

    return grp


# ── Section 5.2.6: Cost by configuration ───────────────────────────────

def table_cost_by_config(df: pd.DataFrame) -> pd.DataFrame:
    """S2 cost and saving by config, averaged over seeds per size x weight."""
    grp = df.groupby(["size_label", "weight", "s2_config"]).agg(
        s1_dispatch=("s1_dispatch_cost", "mean"),
        s2_dispatch=("s2_dispatch_cost", "mean"),
        r_tr=("r_tr", "mean"),
        r_1=("r_1", "mean"),
        n=("r_tr", "count"),
    ).reset_index()

    grp["saving_pct"] = (
        (grp["s1_dispatch"] - grp["s2_dispatch"]) / grp["s1_dispatch"] * 100
    ).round(1)

    off = grp[grp["s2_config"] == "off_off"][
        ["size_label", "weight", "s2_dispatch"]
    ].rename(columns={"s2_dispatch": "off_dispatch"})
    grp = grp.merge(off, on=["size_label", "weight"], how="left")
    grp["cost_delta_pct"] = (
        (grp["s2_dispatch"] - grp["off_dispatch"]) / grp["off_dispatch"] * 100
    ).round(1)

    grp["s1_dispatch"] = grp["s1_dispatch"].round(0)
    grp["s2_dispatch"] = grp["s2_dispatch"].round(0)
    grp["r_tr"] = grp["r_tr"].round(3)
    grp["r_1"] = grp["r_1"].round(3)

    return _sort_df(grp.drop(columns=["off_dispatch"]))


# ── Headline summary ───────────────────────────────────────────────────

def table_headline(df: pd.DataFrame) -> pd.DataFrame:
    """One-row-per-size summary: baseline R_TR, best R_TR, delta, best R_1, etc."""
    rows = []
    for size in SIZE_ORDER:
        sub = df[df["size_label"] == size]
        if sub.empty:
            continue
        w_best = BEST_WEIGHT.get(size, 0)
        base = sub[sub["weight"] == 0]
        best = sub[sub["weight"] == w_best]
        row: dict = {"size": size, "w_best": w_best}
        if not base.empty:
            row["rtr_w0"] = base["r_tr"].mean()
            row["r1_w0"] = base["r_1"].mean()
            row["s2_cost_w0"] = base["s2_dispatch_cost"].mean()
        if not best.empty:
            row["rtr_wbest"] = best["r_tr"].mean()
            row["r1_wbest"] = best["r_1"].mean()
            row["s2_cost_wbest"] = best["s2_dispatch_cost"].mean()
        if "rtr_w0" in row and "rtr_wbest" in row:
            row["delta_rtr"] = row["rtr_wbest"] - row["rtr_w0"]
        if "s2_cost_w0" in row and "s2_cost_wbest" in row:
            row["cost_increase_pct"] = (
                (row["s2_cost_wbest"] - row["s2_cost_w0"]) / row["s2_cost_w0"] * 100
            )
        rows.append(row)

    out = pd.DataFrame(rows)
    for c in out.columns:
        if c not in ("size", "w_best"):
            out[c] = pd.to_numeric(out[c], errors="coerce").round(3)
    return out


# ── Print helpers ──────────────────────────────────────────────────────

def print_section(title: str) -> None:
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def print_df(df: pd.DataFrame, title: str = "") -> None:
    if title:
        print(f"\n  --- {title} ---")
    print(df.to_string(index=False))
    print()


# ── Main ──────────────────────────────────────────────────────────────

def _write(tbl: pd.DataFrame, name: str, title: str) -> None:
    if tbl.empty:
        print(f"\n  --- {title} --- (no data)")
        return
    path = OUT_DIR / f"{name}.csv"
    tbl.to_csv(path, index=False)
    print_df(tbl, title)
    print(f"  -> {path}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading data...")
    df = load_all()
    print(f"  Total: {len(df)} rows\n")

    # Headline
    print_section("Headline Summary (per size)")
    _write(table_headline(df), "headline", "Headline")

    # 5.2.1: R_TR by weight
    print_section("5.2.1: R_TR by Stage 1 Weight")
    _write(table_rtr_by_weight(df), "rtr_by_weight", "R_TR by weight")

    # 5.2.2: Packing at w=0
    print_section("5.2.2a: Packing Effect at w=0")
    _write(table_packing_at_weight(df, weight=0), "packing_w0", "Packing at w=0")

    # 5.2.2: Packing at best weight
    print_section("5.2.2b: Packing Effect at Best Weight")
    _write(table_packing_at_weight(df, use_best=True), "packing_wbest", "Packing at w=best")

    # 5.2.3: R_alpha sweep (single-arc)
    print_section("5.2.3a: R_alpha Degradation (Single-Arc)")
    _write(table_ralpha_sweep(df, scope="single"), "ralpha_single", "R_alpha single-arc")

    # 5.2.3: R_alpha sweep (global)
    print_section("5.2.3b: R_alpha Degradation (Global)")
    _write(table_ralpha_sweep(df, scope="global"), "ralpha_global", "R_alpha global")

    # 5.2.4: First vs Best
    print_section("5.2.4: First vs Best Solution")
    _write(table_first_vs_best(df), "first_vs_best", "First vs Best")

    # 5.2.5: Scalability
    print_section("5.2.5: Scalability")
    _write(table_scalability(df), "scalability", "Scalability")

    # 5.2.6: Cost by config
    print_section("5.2.6: Cost by Configuration")
    _write(table_cost_by_config(df), "cost_by_config", "Cost by Config")

    print(f"\n{'='*80}")
    print(f"  All CSVs written to {OUT_DIR}/")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
