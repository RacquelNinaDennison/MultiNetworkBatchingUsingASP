"""Generate per-class summary tables with mean ± std + bootstrap CI.

Reads existing experiment CSVs in ``results/`` and writes one summary
CSV per source plus a combined wide-format markdown table for the paper.

Usage:
    cd new_code
    uv run python -m multibatch.experiments.twostage.make_summary_tables
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .analysis import load_experiment_csv, table_with_ci
from .config import ALPHA_VALUES


RESULTS_DIR = Path(__file__).resolve().parent / "results"
SUMMARY_DIR = RESULTS_DIR / "summary"


METRICS = [
    "r_tr",
    "r_1",
    "k_1",
    "nominal_cost",
    "s1_dispatch_cost",
    "s2_dispatch_cost",
    "s1_time",
    "s2_time",
] + [f"r_heaviest_single_{a}" for a in ALPHA_VALUES] \
  + [f"r_heaviest_global_{a}" for a in ALPHA_VALUES]


def main() -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    csvs = sorted(RESULTS_DIR.glob("experiment__*.csv"))
    if not csvs:
        raise SystemExit(f"No experiment CSVs in {RESULTS_DIR}")

    for src in csvs:
        df = load_experiment_csv(src)
        if df.empty:
            print(f"skip empty: {src.name}")
            continue

        table = table_with_ci(df, METRICS)
        out = SUMMARY_DIR / f"summary__{src.stem}.csv"
        table.to_csv(out, index=False)
        print(f"wrote {out.name}: {len(table)} group rows from {len(df)} runs")


if __name__ == "__main__":
    main()
