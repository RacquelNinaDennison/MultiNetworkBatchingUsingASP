# Scalability experiment reproduction

Compare one-shot and two-stage decomposition using four solvers:
`naive_oneshot`, `clingcon_oneshot`, `naive_twostage`, and `clingcon_twostage`.
See the [shared setup](../README.md). Run commands from the repository root.
Inputs are the saved `.lp` files in `src/multibatch/instances/generated/`.

## Settings and time budgets

The CLI defaults to all six generated sizes, three repetitions, one-shot bin
setting 3 and maximum frequency 20. The two-stage baseline disables the
resilience penalties. The shell wrapper has longer budgets than the CLI:

| Size | Python CLI default (seconds) | `run_all.sh` budget (seconds) |
| --- | ---: | ---: |
| paper | 30 | 600 |
| small | 30 | 600 |
| medium | 60 | 600 |
| large | 120 | 1200 |
| xlarge | 300 | 1200 |
| industrylite | 600 | 1200 |

One-shot receives one budget. Two-stage receives the budget **per stage**, so
combined solving time can approach twice that amount, plus overhead. Compare
`wall_time` for actual elapsed time; `total_time` combines the solver's stage
measurements. This is not an equal-total-wall-budget experiment.

## Small installation check

```bash
uv run --no-sync python -m multibatch.experiments.scalability.main --help
uv run --no-sync python -m multibatch.experiments.scalability.main \
  --sizes paper --solvers clingcon_oneshot clingcon_twostage \
  --reps 1 --num-bins 3 --max-freq 20 --time-paper 10 \
  --output-dir output/reproduction/scalability-smoke --tag paper
```

## Reproduce the recorded small-instance budget

The saved `results/scalability_raw_small.csv` has 60 rows and records a
600-second budget, not the CLI's 30-second default:

```bash
uv run --no-sync python -m multibatch.experiments.scalability.main \
  --sizes small \
  --solvers naive_oneshot clingcon_oneshot naive_twostage clingcon_twostage \
  --reps 3 --num-bins 3 --max-freq 20 --time-small 600 \
  --output-dir output/reproduction/scalability --tag small
```

Five instances, four solvers and three repetitions give 60 scheduled records.
For the wrapper's full design, select all sizes and pass the six wrapper budgets
in the table explicitly. Alternatively, `bash
src/multibatch/experiments/scalability/run_all.sh` uses them and writes tagged
files/logs under `results/`; keep `NTFY_TOPIC` unset for no notifications.

## Outputs and interpretation

The example writes `scalability_raw_small.csv` and
`scalability_summary_small.csv` under its output directory. Reusing a path
replaces the outputs; no resume option is exposed. Both files are written
after the sweep, so an interruption can lose runs not yet saved.

Raw rows include instance properties, `status`, times, cost, search statistics,
and stage-specific fields. Inspect `OK`, `TIMEOUT`, `S1_UNSAT`, `S2_UNSAT` and
`ERROR` statuses alongside feasibility and optimality; don't average failures as
zero-cost solutions.

The `cost` column uses the one-shot objective or the two-stage `s1_cost`.
`s2_cost` is a separate packing objective, not directly interchangeable with
monetary dispatch cost. Check the encoding revision and cost formula when
comparing with the MILP resilience or Pareto suites.

## Saved-result analysis

Open `results/eda.ipynb` using the project kernel and its `results/` directory as
the working directory. It loads the saved raw CSVs for paper, small and medium.
For fresh results, copy the notebook and change its input paths to your output
directory. Current notebook inputs do not automatically include tagged reruns or
all larger sizes.
