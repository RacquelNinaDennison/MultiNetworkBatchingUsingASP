# clingcon Runtime Benchmark Suite

This repo now includes a benchmark runner to measure runtime for:
- `encoding_alternative.lp`
- `instances.lp`
- two bin-count setups (`numBins=1` and `numBins=2`)
- naive clingcon and alternative solver configurations

## What is measured

For each run, the suite records:
- total runtime
- solving time
- grounding time estimate (`total - solving`)
- CPU time
- result status, timeout flag, model count, and full command

## Benchmark script

Use:

```bash
uv sync
uv run python benchmark_suite.py run
```

Default behavior:
- bins: `1 2`
- configs: `naive frumpy jumpy trendy`
- runs per `(bins, config)` pair: `3`
- outputs to `benchmark_results/<timestamp>/`

### Common examples

Run only naive + two configs, 5 repetitions, and a 60s time limit:

```bash
uv run python benchmark_suite.py run \
  --runs 5 \
  --bins 1 2 \
  --configs naive frumpy jumpy \
  --time-limit 60
```

Add a custom configuration:

```bash
uv run python benchmark_suite.py run \
  --configs naive \
  --custom-config "rand::--rand-freq=0.1 --seed=7"
```

Analyze an existing CSV again:

```bash
uv run python benchmark_suite.py analyze \
  --csv benchmark_results/<timestamp>/results.csv
```

## Notes

- `encoding_alternative.lp` now uses:
  - `#const numBins = 2.`
  - `bins(1..numBins).`
- The suite overrides this per run with `-c numBins=<value>`.
