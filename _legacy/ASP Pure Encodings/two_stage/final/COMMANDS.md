# Experiment Commands

All commands run from the `ASP Pure Encodings/` directory (where `pyproject.toml` lives).

```bash
cd "/Users/racqueldennison/Documents/Masters/realdeal_masters/combined_encodings/ASP Pure Encodings"
```

---

## 1. Quick test (single instance, 3 weights, 30s)

```bash
uv run python two_stage/final/run_experiment.py \
  --instances-dir two_stage/final/instances/generated \
  --instance-filter small_seed1 \
  --weights 0 100 500 \
  --time-small 30 \
  --output two_stage/final/results/test_run.csv
```

## 2. Full sweep (all small instances, 10 weights, 30s each)

```bash
uv run python two_stage/final/run_experiment.py \
  --instances-dir two_stage/final/instances/generated \
  --time-small 30 \
  --output two_stage/final/results/div_weight_sweep.csv
```

## 3. Pareto run (single instance, 10 weights, 600s each — ~100 min)

```bash
uv run python two_stage/final/run_experiment.py \
  --instances-dir two_stage/final/instances/generated \
  --instance-filter small_seed1 \
  --time-small 600 \
  --output two_stage/final/results/pareto_600s.csv
```

## 4. Resume an interrupted run

Add `--resume` to skip already-completed rows:

```bash
uv run python two_stage/final/run_experiment.py \
  --instances-dir two_stage/final/instances/generated \
  --time-small 600 \
  --output two_stage/final/results/pareto_600s.csv \
  --resume
```

## 5. Generate plots from any CSV

```bash
uv run python two_stage/final/plot_results.py \
  --input two_stage/final/results/pareto_600s.csv \
  --output-dir two_stage/final/results/plots
```

## 6. Shell wrapper (full sweep + plots)

```bash
bash two_stage/final/run_all.sh
```

---

## CLI Reference

### run_experiment.py

| Flag | Default | Description |
|------|---------|-------------|
| `--instances-dir` | `instances/generated` | Directory with `*_seed*.lp` files |
| `--instance-filter` | (all) | Only run instances matching this string |
| `--weights` | `0 25 50 100 150 200 300 500 750 1000` | div_weight values to sweep |
| `--time-small` | `30` | Seconds per solve for small instances |
| `--time-medium` | `60` | Seconds per solve for medium instances |
| `--time-large` | `120` | Seconds per solve for large instances |
| `--cap-divide` | `1` | Capacity scaling divisor |
| `--max-freq` | `20` | Max route frequency |
| `--output` | `results/div_weight_sweep.csv` | Output CSV path |
| `--resume` | off | Skip already-completed (instance, weight) pairs |

### plot_results.py

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | `results/div_weight_sweep.csv` | Input CSV |
| `--output-dir` | `results/plots` | Directory for PNG outputs |

### Output plots

| File | Content |
|------|---------|
| `cost_vs_weight.png` | Transport cost vs div_weight |
| `rtr_vs_weight.png` | R_TR vs div_weight |
| `dominant_vs_weight.png` | Dominant TR count vs div_weight |
| `cost_resilience_tradeoff.png` | Scatter: transport cost vs R_TR |
| `pareto_per_instance.png` | Per-instance Pareto front (cost vs dominant) |
| `pareto_front.png` | Aggregate Pareto front (cost vs dominant) |
| `experiment_summary.png` | 2x2 summary of the above |
| `summary_stats.csv` | Mean/std per (size, weight) group |
