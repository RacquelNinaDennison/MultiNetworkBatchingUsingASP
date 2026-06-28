"""Merge the four full-suite CSVs into one consolidated dataset.

Drops the partial layered_small_seed3 rows from suite_full_smallmed.csv (it was
re-run fully in part2). Output: suite_consolidated.csv.
"""
import sys
from pathlib import Path

import pandas as pd

RES = Path("src/multibatch/experiments/milp_resilience/results")
SRC = ["suite_full_smallmed.csv", "suite_full_smallmed_part2.csv",
       "suite_full_industry.csv", "suite_full_industry_wn4.csv"]


def main() -> int:
    frames = []
    for name in SRC:
        p = RES / name
        if not p.exists():
            print(f"  [skip] {name} missing"); continue
        df = pd.read_csv(p)
        if name == "suite_full_smallmed.csv":
            before = len(df)
            df = df[df["instance"] != "layered_small_seed3"]   # drop partial; full copy in part2
            print(f"  {name}: {before} -> {len(df)} rows (dropped partial small_seed3)")
        else:
            print(f"  {name}: {len(df)} rows")
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    out = RES / "suite_consolidated.csv"
    full.to_csv(out, index=False)
    print(f"\nConsolidated: {len(full)} rows -> {out}")
    print("Instances:", sorted(full["instance"].unique()))
    print("Configs:", sorted(full["config"].unique()))
    print("Flow solvers:", sorted(full["flow_solver"].unique()))
    # coverage of (instance, flow_solver, w_net, w_flow) flow points
    fp = full[["instance", "flow_solver", "w_net", "w_flow"]].drop_duplicates()
    print(f"Distinct flow points: {len(fp)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
