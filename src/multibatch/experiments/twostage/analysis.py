"""Analysis pipeline for two-stage resilience experiments.

Loads experiment CSVs, applies correct config labels, and generates
summary tables with bootstrap confidence intervals.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import (
    LEGACY_CONFIG_MAP,
    DEFAULT_S2_CONFIGS,
    SIZE_ORDER,
    ALPHA_VALUES,
)
from ...metrics.statistics import bootstrap_ci


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


def _coerce_numeric(df: pd.DataFrame) -> None:
    """Convert known numeric columns from string to float."""
    numeric_cols = [
        "r_tr", "r_1", "k_1", "nominal_cost", "s1_dispatch_cost",
        "s2_dispatch_cost", "cost_saving", "mono_count",
        "concentrated_count", "weight", "s1_time", "s2_time",
    ]
    for strat in ["heaviest", "first", "last"]:
        for mode in ["single", "global"]:
            for a in ALPHA_VALUES:
                numeric_cols.append(f"r_{strat}_{mode}_{a}")

    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


# ── Summary tables ────────────────────────────────────────────────────


def table_with_ci(
    df: pd.DataFrame,
    metrics: list[str],
    group_cols: list[str] | None = None,
    n_bootstrap: int = 10_000,
    confidence: float = 0.95,
) -> pd.DataFrame:
    """Per-group mean ± std + bootstrap CI for selected metrics.

    Group rows by ``group_cols`` (default: instance_size, weight,
    s2_config) and compute, for each metric:
      ``<m>_mean``, ``<m>_std``, ``<m>_ci_lo``, ``<m>_ci_hi``, ``<m>_n``.
    """
    if group_cols is None:
        group_cols = ["instance_size", "weight", "s2_config"]

    rows: list[dict] = []
    for keys, sub in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_cols, keys))
        for m in metrics:
            if m not in sub.columns:
                continue
            vals = sub[m].dropna().tolist()
            ci = bootstrap_ci(
                vals, n_bootstrap=n_bootstrap, confidence=confidence,
            )
            row[f"{m}_mean"] = ci["mean"]
            row[f"{m}_std"] = ci["std"]
            row[f"{m}_ci_lo"] = ci["ci_lower"]
            row[f"{m}_ci_hi"] = ci["ci_upper"]
            row[f"{m}_n"] = ci["n"]
        rows.append(row)

    out = pd.DataFrame(rows)
    return _sort_df(out, size_col="instance_size")


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
