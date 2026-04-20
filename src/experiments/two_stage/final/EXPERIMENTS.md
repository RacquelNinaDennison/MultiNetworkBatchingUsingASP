# Two-Stage Resilience Experiment Runner

## Overview

The experiment runner (`run_full_experiment.py`) evaluates how weighted soft constraints in a two-stage ASP/clingcon solver improve supply-chain network resilience.

- **Stage 1** solves network flow and frequency assignment, with a configurable `weight` parameter that penalises high-exposure arcs.
- **Stage 2** performs per-trip bin packing, with configurable penalties for mono-part trips (`hetero`) and overloaded trips (`conc`).

### Metrics

| Metric | Description |
|--------|-------------|
| **R_TR** | Arc-level resilience: worst-case demand coverage if an entire arc is lost |
| **R_1** | Trip-level resilience: worst-case demand coverage if a single trip is lost |
| **K_1** | Kit completion ratio: worst-case complete-kit fulfillment if a trip is lost |
| **R_alpha** | Partial disruption resilience: worst-case demand coverage when only α% of trips survive on disrupted arc(s). Computed for α ∈ {0.2, 0.4, 0.6, 0.8} with three trip-selection strategies (`heaviest`, `first`, `last`) and two disruption scopes (`single`, `global`). See below. |
| **S1 cost** | Nominal transport cost from Stage 1 |
| **S2 dispatch cost** | Actual dispatch cost based on used trips in Stage 2 |

### R_alpha Details

R_alpha simulates partial arc disruption: only α fraction of trips survive on the disrupted arc(s).

**Trip selection strategies:**
- `heaviest`: Remove the most-loaded trips first (worst-case / pessimistic bound)
- `first`: Keep the first k trip indices (tests whether solver front-loads capacity)
- `last`: Keep the last k trip indices (mirror of first)

**Disruption scopes:**
- `single`: Disrupt one arc at a time, report worst-case across all arcs
- `global`: Disrupt all arcs simultaneously to α%

### Stage 2 Configurations

| Config | hetero_on | concentrated_on | Effect |
|--------|-----------|-----------------|--------|
| `off_off` | 0 | 0 | Baseline — no resilience penalties |
| `hetero` | 1 | 0 | Penalise mono-part trips (mix parts) |
| `conc` | 0 | 1 | Penalise overloaded trips (spread load) |
| `both` | 1 | 1 | Both penalties active |

---

## Instance Sizes & Time Estimates

| Size | Locations | Parts | TRs | Routes | Seeds | Runs (2w × 4cfg) | ~Time/run | ~Total |
|------|-----------|-------|-----|--------|-------|-------------------|-----------|--------|
| `small` | 6 (2+2+2) | 2 | 2 | ~17-22 | 5 | 40 | ~2 min | **~1.3 hr** |
| `medium` | 8 (2+3+3) | 3 | 2 | ~36-45 | 5 | 40 | ~4 min | **~2.7 hr** |
| `large` | 10 (2+4+4) | 4 | 2 | ~59-71 | 5 | 40 | ~10 min | **~6.7 hr** |
| `xlarge` | 15 (3+6+6) | 6 | 3 | ~200-220 | 5 | 40 | ~20 min | **~13 hr** |
| `industrylite` | 20 (4+8+8) | 10 | 4 | ~477-524 | 5 | 40 | ~30 min | **~20 hr** |
| `paper` | 6 | 2 | 2 | ~12 | 1 | 8 | ~1 min | **~8 min** |

---

## Running on a Server

### Prerequisites

Make sure `clingcon` is installed and on `PATH`, and Python dependencies are available:

```bash
which clingcon          # should print a path
pip install scipy       # needed for max-flow metrics
```

### Using nohup (keeps running after SSH disconnect)

```bash
cd /path/to/combined_encodings/src
nohup python experiments/two_stage/final/run_full_experiment.py \
    [OPTIONS] \
    -o experiments/two_stage/final/results/OUTPUT.csv \
    > experiments/two_stage/final/results/OUTPUT.log 2>&1 &
echo $!   # prints the PID — save this to check/kill later
```

Monitor progress:

```bash
# Check how many rows are done
wc -l experiments/two_stage/final/results/OUTPUT.csv

# Follow the log
tail -f experiments/two_stage/final/results/OUTPUT.log

# Check if still running
ps aux | grep run_full_experiment
```

### Using screen (recommended)

```bash
screen -S experiments
cd /path/to/combined_encodings/src

# run your command here...

# Detach: Ctrl+A then D
# Reattach later: screen -r experiments
```

---

## Individual Commands (copy-paste ready)

All commands assume you are in the `src/` directory.

### 1. Paper (~8 min)

```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_paper \
    --weights 0 600 \
    --time-paper 600 \
    -o experiments/two_stage/final/results/sweep_paper_v2.csv \
    > experiments/two_stage/final/results/sweep_paper.log 2>&1 &
```
11876
### 2. Small (~1.3 hr)

```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_small \
    --weights 0 300 500 750 1000 \
    --time-small 60 \
    -o experiments/two_stage/final/results/sweep_small.csv \
    > experiments/two_stage/final/results/sweep_small.log 2>&1 &
```
 11856

### 3. Medium (~2.7 hr)

```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_medium \
    --weights 0 300 500 750 1000 \
    --time-medium 120 \
    -o experiments/two_stage/final/results/sweep_medium_moreweights.csv \
    > experiments/two_stage/final/results/sweep_medium_moreweights.log 2>&1 &
```
11897
### 4. Large (~6.7 hr)

```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_large \
    --weights 0 300 \
    --time-large 300 \
    -o experiments/two_stage/final/results/sweep_large.csv \
    > experiments/two_stage/final/results/sweep_large.log 2>&1 &
```
11910
### 5. XLarge (~13 hr)

```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_xlarge \
    --weights 0 1000 \
    --time-xlarge 600 \
    -o experiments/two_stage/final/results/sweep_xlarge.csv \
    > experiments/two_stage/final/results/sweep_xlarge.log 2>&1 &
```
11948
### 6. Industry-Lite (~20 hr)

```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_industrylite \
    --weights 0 1000 \
    --time-industrylite 900 \
    -o experiments/two_stage/final/results/sweep_industrylite.csv \
    > experiments/two_stage/final/results/sweep_industrylite.log 2>&1 &
```
11960

### 7. Industry — light encoding (no resilience penalties, ~8 hr)

```bash
nohup python experiments/two_stage/final/run_full_experiment.py \
    --skip-layered \
    --light-industry \
    --weights 0 1000 \
    --time-industry 600 \
    -o experiments/two_stage/final/results/sweep_industry_light.csv \
    > experiments/two_stage/final/results/sweep_industry_light.log 2>&1 &
```

### 8. Industry — heavy encoding with resilience soft constraints (~40+ hr)

Uses the same resilience encodings as the layered instances (`stage_1_flow.lp` + `stage2_packing.lp`). These are much harder for the solver at industry scale (50 locs, 35 parts, 5610 routes), so longer time limits are needed. Many instances may not find a feasible model within the limit.

```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-layered \
    --weights 0 10000 \
    --time-industry 200 \
    -o experiments/two_stage/final/results/sweep_industry_heavy.csv \
    > experiments/two_stage/final/results/sweep_industry_heavy.log 2>&1 &
```

To test on just the original industry instance:

```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-layered \
    --instance-filter industry_instances \
    --weights 0 10000000 \
    --time-industry 1800 \
    -o experiments/two_stage/final/results/sweep_industry_original_heavy.csv \
    > experiments/two_stage/final/results/sweep_industry_original_heavy.log 2>&1 &
```
11973
To test on just the generated industry test cases:

```bash
nohup python experiments/two_stage/final/run_full_experiment.py \
    --skip-layered \
    --instance-filter industry_test \
    --weights 0 300 \
    --time-industry 1800 \
    -o experiments/two_stage/final/results/sweep_industry_test_heavy.csv \
    > experiments/two_stage/final/results/sweep_industry_test_heavy.log 2>&1 &
```

### 9. R_alpha experiments (re-run with partial disruption metric)

The R_alpha metric is computed automatically in the experiment runner. To generate results with R_alpha columns, run to **new** output CSVs (existing CSVs don't have R_alpha columns).

**Small (with R_alpha, ~2 hr):**
```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_small \
    --weights 0 300 500 750 1000 1500 \
    --time-small 600 --configuration many \
    -o experiments/two_stage/final/results/sweep_small_ralpha_v2.csv \
    > experiments/two_stage/final/results/sweep_small_ralpha_v2.log 2>&1 &
```

**Medium (with R_alpha, ~3 hr):**
```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_medium \
    --weights 0 300 500 750 1000 1500\
    --time-medium 600 --configuration many \
    -o experiments/two_stage/final/results/sweep_medium_ralpha_v2.csv \
    > experiments/two_stage/final/results/sweep_medium_ralpha.log 2>&1 &
```

**XLarge (with R_alpha, ~14 hr):**
```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_xlarge \
    --weights 0 1000 2000 5000 \
    --time-xlarge 600 --configuration many \
    -o experiments/two_stage/final/results/sweep_xlarge_ralpha_v2.csv \
    > experiments/two_stage/final/results/sweep_xlarge_ralpha.log 2>&1 &
```

**IndustryLite (with R_alpha, ~22 hr):**
```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_industrylite \
    --weights 0 2000 \
    --time-industrylite 600 --configuration many \
    -o experiments/two_stage/final/results/sweep_industrylite_ralpha_v2.csv \
    > experiments/two_stage/final/results/sweep_industrylite_ralpha.log 2>&1 &
```

**Industry — heavy encoding with R_alpha (~40+ hr):**
```bash
nohup uv run experiments/two_stage/final/run_full_experiment.py \
    --skip-layered \
    --weights 0 100000\
    --time-industry 20000 --configuration many \
    -o experiments/two_stage/final/results/sweep_industry_ralpha_full_run_12h.csv \
    > experiments/two_stage/final/results/sweep_industry_ralpha.log 2>&1 &
```

### Run ALL sizes in one go (~44 hr)

```bash
nohup python experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --weights 0 300 \
    --time-small 60 --time-medium 120 --time-large 300 \
    --time-xlarge 600 --time-industrylite 900 --time-paper 60 \
    -o experiments/two_stage/final/results/full_layered_sweep.csv \
    > experiments/two_stage/final/results/full_layered_sweep.log 2>&1 &
```

### Resume after crash

Add `--resume` to any command above. It reads the CSV and skips completed rows:

```bash
nohup python experiments/two_stage/final/run_full_experiment.py \
    --skip-industry \
    --instance-filter layered_large \
    --weights 0 300 \
    --time-large 300 \
    --resume \
    -o experiments/two_stage/final/results/sweep_large.csv \
    > experiments/two_stage/final/results/sweep_large.log 2>&1 &
```

---

## Solver Notes

- **`--configuration many`** is the default. It uses a portfolio of solver heuristics that improves search on hard instances.
- **`-t` (threads) must stay at 1.** Clingcon's CSP propagator does not support multi-threaded solving — it produces empty/invalid models with `-t > 1`.

---

## Regenerating Test Instances

```bash
cd src/
python -m instances.modules.generate_sparse
```

This regenerates all layered instances (5 seeds × 6 sizes) and industry-derived test cases (10 instances). Existing instances in `instances/generated/` are overwritten.

---

## Output CSV Columns

| Column | Description |
|--------|-------------|
| `instance_name` | Instance filename (without .lp) |
| `instance_type` | `layered` or `industry` |
| `instance_size` | `small`, `medium`, `large`, `xlarge`, `industrylite`, `paper`, `industry` |
| `seed` | Random seed used to generate the instance |
| `weight` | Stage 1 resilience weight |
| `exposure_n` | Exposure threshold parameter |
| `s2_config` | Stage 2 configuration name |
| `hetero_on` | Whether hetero penalty is active (0/1) |
| `concentrated_on` | Whether concentration penalty is active (0/1) |
| `nominal_cost` | Stage 1 nominal transport cost |
| `exposure_count` | Number of high-exposure arcs detected |
| `r_tr` | Arc-level resilience (0–1, higher is better) |
| `worst_arc` | The arc whose loss causes worst coverage |
| `r_1` | Trip-level resilience (0–1, higher is better) |
| `worst_trip` | The trip whose loss causes worst coverage |
| `k_1` | Kit completion ratio (0–1, higher is better) |
| `r_{strat}_{mode}_{alpha}` | R_alpha value for given strategy/mode/alpha (e.g. `r_heaviest_single_0.2`) |
| `mono_count` | Number of mono-part trips |
| `concentrated_count` | Number of concentrated trips |
| `s1_optimal` | Whether Stage 1 reached optimality |
| `s1_time` | Stage 1 wall-clock time (seconds) |
| `s2_optimal` | Whether Stage 2 reached optimality |
| `s2_time` | Stage 2 wall-clock time (seconds) |
| `s1_dispatch_cost` | Dispatch cost based on S1 frequencies |
| `s2_dispatch_cost` | Dispatch cost based on S2 used trips |
| `cost_saving` | S1 dispatch cost − S2 dispatch cost |
| `status` | `OK` or error description |
