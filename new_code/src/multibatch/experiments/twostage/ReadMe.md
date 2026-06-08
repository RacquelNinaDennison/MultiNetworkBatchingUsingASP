## Two-Stage Resilience Experiment

Runs Stage 1 (network flow) once per (instance, weight), then sweeps Stage 2 packing configs. Computes R_TR, R_1, K_1, R_alpha metrics per row.

### Quick start

```bash
cd new_code
caffeinate -dims uv run python -m multibatch.experiments.twostage \
    --weights 0 500 10000 50000 75000 100000 150000 \
    -t 4 --configuration handy \
    --time-paper 600 --time-small 600 --time-medium 600 \
    --time-large 1200 --time-xlarge 1200 --time-industrylite 1200 \
    --time-industry 20000 \
    -o src/multibatch/experiments/twostage/results/experiment_main_sweep.csv
```

### Filtering by instance size

`--instance-filter <substr>` matches against filename stem (substring match).

| Target | Flag | Notes |
|--------|------|-------|
| paper | `--instance-filter paper` | single instance |
| small | `--instance-filter small` | 5 seeds |
| medium | `--instance-filter medium` | 5 seeds |
| large only | `--instance-filter _large_` | underscores avoid `xlarge` collision |
| xlarge | `--instance-filter xlarge` | 5 seeds |
| industrylite | `--instance-filter industrylite` | 4 seeds |
| industry (main) | `--instance-filter industry_test` | excludes `industrylite` |

Bare `large` also matches `xlarge` — use `_large_`.

### Per-size time limits

| Flag | Default (s) | Applies to |
|------|-------------|------------|
| `--time-paper` | 600 | `layered_paper` |
| `--time-small` | 600 | `layered_small_*` |
| `--time-medium` | 600 | `layered_medium_*` |
| `--time-large` | 600 | `layered_large_*` |
| `--time-xlarge` | 600 | `layered_xlarge_*` |
| `--time-industrylite` | 600 | `layered_industrylite_*` |
| `--time-industry` | 20000 | `industry_test_*` |

Size auto-detected from filename via regex (`config.py:60`). Custom names fall back to 120s default.

### Capacity scaling

`--cap-size-divide <int>` (default `1`) divides both `transportCapacity` and `partSize` by N inside the encoding. Smaller integers → faster solving, coarser granularity. Stage 1 encoding's baked-in default is 10; CLI value overrides.

```bash
--cap-size-divide 10
```

### Other key flags

| Flag | Purpose |
|------|---------|
| `--weights <ints...>` | Stage 1 exposure weight sweep |
| `--exposure-n <int>` | Top-N exposure threshold (default 3) |
| `--s2-configs <names>` | Subset of `{baseline, mixed, even, full}` |
| `-t / --threads <int>` | Clingo thread count |
| `--configuration <name>` | Clingo preset: `handy`, `jumpy`, `trendy`, `crafty`, `frumpy`, `many`, `auto` |
| `--config-sweep <names>` | Sweep multiple presets |
| `--thread-sweep <ints>` | Sweep multiple thread counts |
| `--max-freq <int>` | Max dispatches per route (default 20) |
| `--resume` | Skip already-done (instance, weight, s2_config) rows |
| `-o / --output <path>` | Output CSV path |

### Industry-only run

```bash
caffeinate -dims uv run python -m multibatch.experiments.twostage \
    --weights 0 500 10000 50000 75000 100000 150000 \
    -t 4 --configuration handy \
    --time-industry 20000 \
    --cap-size-divide 10 \
    --instance-filter industry_test \
    -o src/multibatch/experiments/twostage/results/experiment_industry.csv
```

Industry instance file must match pattern `industry_test_<seed>.lp` and live in `src/multibatch/instances/generated/`.


Furthermore, to make the experiments easier, we have added in bash scripts. 
  # scalability — all sizes
  ./src/multibatch/experiments/scalability/run_all.sh                                                                                                                                             

  # benchmark — paper + small only 
  ./src/multibatch/experiments/benchmark/run_all.sh paper small

  # custom tag for grouping                                                                                                                                                                       
  RUN_TAG=baseline_v2 ./src/multibatch/experiments/scalability/run_all.sh

  # tweak via env
  REPS=5 NUM_BINS=4 ./src/multibatch/experiments/scalability/run_all.sh

