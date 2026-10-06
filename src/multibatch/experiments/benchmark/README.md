# One-shot benchmark reproduction

Compare `naive_basic`, `naive_optimised`, `clingcon`, and
`clingcon_optimised` on the same saved instances and bin settings. See the
[shared setup](../README.md) first. All commands below start at the repository root.

## Inputs and current defaults

Inputs: `src/multibatch/instances/generated/*.lp`.
`main.py` defaults to **paper only**, all four solvers, bin settings **1, 2, 3**,
five repetitions, 60 seconds per solve and maximum frequency 20. These are
current CLI defaults, not an assurance of historical run provenance. Bin values
are passed to the solver's `num_bins` parameter; use the same encoding revision
when comparing them.

## Small installation check

```bash
uv run --no-sync python -m multibatch.experiments.benchmark.main --help
uv run --no-sync python -m multibatch.experiments.benchmark.main \
  --sizes paper --solvers clingcon --bins 1 --reps 1 \
  --time-limit 10 --max-freq 20 \
  --output-dir output/reproduction/benchmark-smoke --tag paper
```

This checks that a run can produce records; a short timeout does not guarantee a
feasible or optimal answer.

## Reproduce the small-instance comparison design

```bash
uv run --no-sync python -m multibatch.experiments.benchmark.main \
  --sizes small \
  --solvers naive_basic naive_optimised clingcon clingcon_optimised \
  --bins 1 2 3 --reps 5 --time-limit 60 --max-freq 20 \
  --output-dir output/reproduction/benchmark --tag small
```

With five selected small instances, this schedules `5 * 4 * 3 * 5 = 300` runs,
matching the row count of the saved small raw CSV. It does not prove that every
historical setting was recorded: the raw schema omits some configuration and
budget metadata. Use `--instance-filter` for a filename substring, and
`--instance-dir` to supply an explicit dataset directory.

For more sizes, run one invocation per size with explicit time limits. The
existing `run_all.sh` wrapper instead uses:

| Size | Wrapper time limit (seconds) |
| --- | ---: |
| paper / small | 60 |
| medium | 120 |
| large | 300 |
| xlarge | 600 |
| industrylite | 1200 |

The wrapper defaults to all six sizes, bins 1/2/3 and five repetitions. It writes
uniquely tagged files and logs under this suite's `results/`. Notifications are
optional; leave `NTFY_TOPIC` unset to run without sending them.

**Known runner limitations:** the current benchmark size classifier checks
`large` before `xlarge`, so xlarge filenames can be labelled as large. Inspect
selected filenames before relying on a large/xlarge comparison. Also,
`run_portfolio.sh` passes `--config-sweep`, `--thread-sweep` and `--resume`, which
this version of `main.py` does not accept. The archived portfolio CSVs can be
analysed, but that wrapper is not currently a working reproduction command.

## Outputs and checking a run

`--output-dir` and `--tag small` produce:

- `benchmark_raw_small.csv`: individual runs, including run index, feasibility,
  optimality, cost, grounding/solving times and search statistics.
- `benchmark_summary_small.csv`: aggregate values across repetitions.

The harness writes these files with mode `w` at the end of the sweep. Reusing a
destination overwrites it; it has no supported resume flag and interruption can
lose unsaved runs. Keep fresh results outside the archived `results/` directory.
Do not treat missing cost or `optimum=False` as an optimum or as zero cost.

## Rebuild analysis from saved results

Open `results/eda.ipynb` with the project kernel, working from this suite's
`results/` directory, and run its analysis cells. It explicitly reads the saved
paper/small/medium raw and summary CSVs plus the portfolio-small CSVs. It does
not automatically discover newly tagged reruns. To analyse fresh data, copy the
notebook and adjust its input paths; preserve the original saved-result analysis.
