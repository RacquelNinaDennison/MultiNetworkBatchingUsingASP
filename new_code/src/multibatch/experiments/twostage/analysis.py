"""Analysis pipeline for two-stage resilience experiments.

Loads experiment CSVs, applies correct config labels, computes
post-hoc instance properties, and generates summary tables with
statistical tests.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    LEGACY_CONFIG_MAP,
    S2_CONFIGS,
    DEFAULT_S2_CONFIGS,
    SIZE_ORDER,
    ALPHA_VALUES,
)
from ...metrics.statistics import paired_wilcoxon, bootstrap_ci


# ── Loading and normalisation ─────────────────────────────────────────


def load_experiment_csv(
    path: Path,
    size_label: str | None = None,
) -> pd.DataFrame:
    """Load a single experiment CSV, normalise config names."""
    df = pd.read_csv(path)
    df = df[df["status"] == "OK"].copy()

    # Rename legacy config names
    if "s2_config" in df.columns:
        df["s2_config"] = df["s2_config"].map(
            lambda x: LEGACY_CONFIG_MAP.get(x, x)
        )

    if size_label:
        df["size_label"] = size_label

    _coerce_numeric(df)
    return df


def load_multiple_csvs(
    file_map: dict[str, Path],
) -> pd.DataFrame:
    """Load multiple experiment CSVs keyed by size label."""
    frames = []
    for label, path in file_map.items():
        if not path.exists():
            continue
        df = load_experiment_csv(path, size_label=label)
        frames.append(df)

    if not frames:
        raise ValueError("No data files found")

    return pd.concat(frames, ignore_index=True)


def _coerce_numeric(df: pd.DataFrame) -> None:
    """Convert known numeric columns from string to float."""
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
            for a in ALPHA_VALUES:
                numeric_cols.append(f"r_{strat}_{mode}_{a}")
                numeric_cols.append(f"first_r_{strat}_{mode}_{a}")

    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


# ── Summary tables ────────────────────────────────────────────────────


def table_ablation(
    df: pd.DataFrame,
    metric: str = "r_1",
    group_by: str = "size_label",
) -> pd.DataFrame:
    """Ablation table: metric by config, grouped by size/weight.

    Shows main effect of each soft constraint and their interaction.
    """
    agg = df.groupby([group_by, "weight", "s2_config"]).agg(
        value=(metric, "mean"),
        std=(metric, "std"),
        n=(metric, "count"),
    ).reset_index()

    # Compute delta from baseline
    base = agg[agg["s2_config"] == "baseline"].set_index([group_by, "weight"])
    for idx, row in agg.iterrows():
        key = (row[group_by], row["weight"])
        if key in base.index and row["s2_config"] != "baseline":
            agg.loc[idx, "delta"] = round(
                row["value"] - base.loc[key, "value"], 4,
            )

    agg["value"] = agg["value"].round(4)
    agg["std"] = agg["std"].round(4)
    return _sort_df(agg, group_by)


def table_r_alpha_degradation(
    df: pd.DataFrame,
    strategy: str = "heaviest",
    scope: str = "single",
) -> pd.DataFrame:
    """R_alpha degradation across alpha values."""
    agg_cols = {}
    for a in ALPHA_VALUES:
        col = f"r_{strategy}_{scope}_{a}"
        if col not in df.columns:
            return pd.DataFrame()
        agg_cols[f"a{a}"] = (col, "mean")

    grp = df.groupby(["size_label", "weight", "s2_config"]).agg(
        **agg_cols,
    ).reset_index()

    for a in ALPHA_VALUES:
        grp[f"a{a}"] = grp[f"a{a}"].round(3)

    return _sort_df(grp)


def table_scalability(df: pd.DataFrame) -> pd.DataFrame:
    """Solve time and optimality by instance size."""
    grp = df.groupby("size_label").agg(
        s1_time=("s1_time", "mean"),
        s2_time=("s2_time", "mean"),
        s1_opt=("s1_optimal", lambda x: (x == True).mean() * 100),
        s2_opt=("s2_optimal", lambda x: (x == True).mean() * 100),
        r_tr=("r_tr", "mean"),
        r_1=("r_1", "mean"),
        n=("r_tr", "count"),
    ).reset_index()

    for c in ["s1_time", "s2_time"]:
        grp[c] = grp[c].round(1)
    for c in ["s1_opt", "s2_opt"]:
        grp[c] = grp[c].round(0)
    for c in ["r_tr", "r_1"]:
        grp[c] = grp[c].round(3)

    return _sort_df(grp)


def table_first_vs_best(df: pd.DataFrame) -> pd.DataFrame:
    """First solution vs best solution quality gap."""
    if "first_r_tr" not in df.columns:
        return pd.DataFrame()

    sub = df.dropna(subset=["first_r_tr"])
    if sub.empty:
        return pd.DataFrame()

    grp = sub.groupby(["size_label", "weight", "s2_config"]).agg(
        best_rtr=("r_tr", "mean"),
        first_rtr=("first_r_tr", "mean"),
        best_r1=("r_1", "mean"),
        first_r1=("first_r_1", "mean"),
        best_s1_time=("s1_time", "mean"),
        first_s1_time=("first_s1_time", "mean"),
        best_s2_time=("s2_time", "mean"),
        first_s2_time=("first_s2_time", "mean"),
    ).reset_index()

    grp["delta_rtr"] = (grp["best_rtr"] - grp["first_rtr"]).round(4)
    grp["delta_r1"] = (grp["best_r1"] - grp["first_r1"]).round(4)

    for c in grp.columns:
        if c not in ("size_label", "weight", "s2_config"):
            grp[c] = grp[c].round(3)

    return _sort_df(grp)


# ── Statistical comparisons ──────────────────────────────────────────


def statistical_comparison(
    df: pd.DataFrame,
    metric: str = "r_1",
    baseline: str = "baseline",
    weight: int | None = None,
) -> dict[str, dict]:
    """Run paired Wilcoxon + bootstrap CI for each config vs baseline.

    If weight is specified, filters to that weight. Otherwise pools
    across all weights (each instance×weight is a pair).
    """
    sub = df.copy()
    if weight is not None:
        sub = sub[sub["weight"] == weight]

    # Pivot: one row per instance, one column per config
    pivot = sub.pivot_table(
        index=["instance_name", "weight"],
        columns="s2_config",
        values=metric,
        aggfunc="mean",
    )

    if baseline not in pivot.columns:
        return {}

    results = {}
    baseline_vals = pivot[baseline].dropna().values.tolist()

    for config in pivot.columns:
        if config == baseline:
            continue

        # Align pairs (drop rows where either is NaN)
        paired = pivot[[baseline, config]].dropna()
        if len(paired) < 3:
            continue

        b_vals = paired[baseline].values.tolist()
        t_vals = paired[config].values.tolist()

        results[config] = {
            "wilcoxon": paired_wilcoxon(b_vals, t_vals),
            "baseline_ci": bootstrap_ci(b_vals),
            "treatment_ci": bootstrap_ci(t_vals),
        }

    return results


# ── Helpers ───────────────────────────────────────────────────────────


def _sort_df(
    df: pd.DataFrame,
    size_col: str = "size_label",
) -> pd.DataFrame:
    """Sort by size order, weight, config."""
    size_map = {s: i for i, s in enumerate(SIZE_ORDER)}
    cfg_map = {c: i for i, c in enumerate(DEFAULT_S2_CONFIGS)}

    df = df.copy()
    df["_sz"] = df[size_col].map(size_map).fillna(99) if size_col in df.columns else 0
    sort_cols = ["_sz"]
    drop_cols = ["_sz"]

    if "weight" in df.columns:
        sort_cols.append("weight")
    if "s2_config" in df.columns:
        df["_cfg"] = df["s2_config"].map(cfg_map).fillna(99)
        sort_cols.append("_cfg")
        drop_cols.append("_cfg")

    df = df.sort_values(sort_cols).drop(columns=drop_cols)
    return df
