# MILP/ASP resilience experiments and paper figures

This suite solves a network-flow stage with OR-Tools/SCIP (`milp`) or clingcon
(`asp`), then packs each selected arc with the weighted Stage-2 encoding. It is
the source of the SACAIR paper's reported resilience/cost results and masters paper reported figures. 

Run commands from the repository root after the [shared setup](../README.md).
Use the saved inputs under `src/multibatch/instances/generated/`:

| Group | Files | Instances |
| --- | --- | ---: |
| Small | `layered_small_seed1.lp` through `layered_small_seed5.lp` | 5 |
| Medium | `layered_medium_seed1.lp` through `layered_medium_seed5.lp` | 5 |
| Industrial | `industry_test_1.lp` (the Airbus dataset identified by the author) | 1 |

The saved consolidated CSV contains **336 rows across these 11 instances**.
Rows represent solver/weight/packing configurations, not repeated trials.

## 1. Rebuild the reported figures from saved results

This does not run either solver:

```bash
make paper-figures
```

Input: `src/multibatch/experiments/milp_resilience/results/suite_consolidated.csv`.
Outputs in `src/multibatch/experiments/milp_resilience/results/figures/sacair2026/`:

- `figure_2_medium_revised.pdf` and `.png`
- `figure_3_industry_revised.pdf` and `.png`
- `figure_data_audit.json`

To keep generated files separate:

```bash
uv run --no-sync python -m multibatch.experiments.milp_resilience.plots_paper \
  --output-dir output/reproduction/milp-resilience/paper-figures
```

### Reconstruct the archived consolidated CSV only if needed

`consolidate.py` reads four fixed files from `results/`:

1. `suite_full_smallmed.csv`
2. `suite_full_smallmed_part2.csv`
3. `suite_full_industry.csv`
4. `suite_full_industry_wn4.csv`

It removes the partial `layered_small_seed3` rows from the first file, keeping
the complete version from the second. Ensure all four files exist before use:
missing files are skipped, so a successful exit alone does not mean a complete
archive. The following command **overwrites** `results/suite_consolidated.csv`:

```bash
uv run --no-sync python -m multibatch.experiments.milp_resilience.consolidate
```

Expect 336 rows and 11 unique instances. This script is specific to the archived
split; use the separate merge below for fresh runs.

## 2. Small smoke run

Use a new output and cache directory for each independent run. A short budget
checks that the pipeline starts; it does not guarantee a feasible solution.

```bash
uv run --no-sync python -m multibatch.experiments.milp_resilience.suite \
  --instances src/multibatch/instances/generated/layered_small_seed1.lp \
  --flow-solvers milp --backend SCIP --synth-values none \
  --w-net-grid 0 --w-flow-grid 0 \
  --w-hetero-grid 0 8 --w-conc-grid 0 8 \
  --flow-time-limit 10 --stage2-time-limit 5 --configuration many \
  --cache-dir output/reproduction/milp-smoke/flows \
  --out output/reproduction/milp-smoke/suite.csv
```

Each feasible flow is evaluated with four packing configurations:

| CSV configuration | Heterogeneity weight | Concentration weight |
| --- | ---: | ---: |
| `baseline` | 0 | 0 |
| `hetero_w8` | 8 | 0 |
| `conc_w8` | 0 | 8 |
| `full_w8_8` | 8 | 8 |

The grids do not form a full Cartesian product of packing weights: the suite
uses baseline, each single lever, and one combined configuration at both maxima.

## 3. Rerun the saved experimental grid

The commands below reproduce the saved grid and reported time budgets with
explicit current settings. They are not a claim that every historical launch
setting was recorded. Start with a new `output/reproduction/milp-resilience/`
directory, or replace that prefix throughout with a unique run directory.

### Small and medium: 120-second flow / 30-second packing budgets

```bash
uv run --no-sync python -m multibatch.experiments.milp_resilience.suite \
  --instances 'src/multibatch/instances/generated/layered_small_seed*.lp' \
              'src/multibatch/instances/generated/layered_medium_seed*.lp' \
  --flow-solvers milp asp --backend SCIP --synth-values none \
  --w-net-grid 0 4 --w-flow-grid 0 4 8 \
  --w-hetero-grid 0 8 --w-conc-grid 0 8 \
  --flow-time-limit 120 --stage2-time-limit 30 --configuration many \
  --cache-dir output/reproduction/milp-resilience/flows-smallmed \
  --out output/reproduction/milp-resilience/smallmed.csv
```

ASP ignores the redundancy grid and uses only `lambda_flow=0`: expect 80 ASP
rows and 240 MILP rows if every flow succeeds (320 total).

### Industrial: 600-second flow / 100-second packing budgets

The archive includes all three redundancy weights at zero exposure weight,
and only zero redundancy at exposure weight four. These two commands preserve
that selection and deliberately share their industrial reference-flow cache:

```bash
uv run --no-sync python -m multibatch.experiments.milp_resilience.suite \
  --instances src/multibatch/instances/generated/industry_test_1.lp \
  --flow-solvers milp --backend SCIP --synth-values none \
  --w-net-grid 0 --w-flow-grid 0 4 8 \
  --w-hetero-grid 0 8 --w-conc-grid 0 8 \
  --flow-time-limit 600 --stage2-time-limit 100 --configuration many \
  --cache-dir output/reproduction/milp-resilience/flows-industry \
  --out output/reproduction/milp-resilience/industry-zero.csv

uv run --no-sync python -m multibatch.experiments.milp_resilience.suite \
  --instances src/multibatch/instances/generated/industry_test_1.lp \
  --flow-solvers milp --backend SCIP --synth-values none \
  --w-net-grid 4 --w-flow-grid 0 \
  --w-hetero-grid 0 8 --w-conc-grid 0 8 \
  --flow-time-limit 600 --stage2-time-limit 100 --configuration many \
  --cache-dir output/reproduction/milp-resilience/flows-industry \
  --out output/reproduction/milp-resilience/industry-wn4.csv
```

Expect 12 and 4 rows respectively if all flows succeed. Merge and check the
fresh files without replacing the paper data:

```bash
uv run --no-sync python - <<'PY'
from pathlib import Path
import pandas as pd
root = Path('output/reproduction/milp-resilience')
frames = [pd.read_csv(root / name) for name in
          ('smallmed.csv', 'industry-zero.csv', 'industry-wn4.csv')]
data = pd.concat(frames, ignore_index=True)
keys = ['instance', 'flow_solver', 'lambda_net', 'lambda_flow', 'config']
assert not data.duplicated(keys).any(), 'Duplicate experimental cells'
assert len(data) == 336, f'Incomplete grid: {len(data)} rows'
assert data.instance.nunique() == 11
path = root / 'suite-fresh.csv'
data.to_csv(path, index=False)
print(path)
PY

uv run --no-sync python -m multibatch.experiments.milp_resilience.analyze \
  --csv output/reproduction/milp-resilience/suite-fresh.csv \
  --out-dir output/reproduction/milp-resilience/analysis
```

`analyze` exports summary CSVs and plots for the supplied results. Check
feasibility/optimality and individual instance results before comparing averages.
The frozen `plots_paper` builder is for the archived values, not arbitrary new
solver results.