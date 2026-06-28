# Scalability Experiments

How does the two-stage decomposition scale against the one-shot encoding,
for both the naive (pure ASP) and clingcon (CASP) backends?

## Solvers Compared

| Name | Class | Encoding family | Backend |
|------|-------|-----------------|---------|
| `naive_oneshot` | `NaiveOneShotSolver` (optimised) | one-shot | naive |
| `clingcon_oneshot` | `ClingconOneShotSolver` (optimised) | one-shot | clingcon |
| `naive_twostage` | `NaiveTwoStageSolver` | two-stage | naive |
| `clingcon_twostage` | `ClingconTwoStageSolver` (baseline, weight=0) | two-stage | clingcon |

Two-stage solvers run with `weight=0`, `hetero_on=0`, `concentrated_on=0`,
so Stage 1 minimises pure transport cost (no exposure penalty) and Stage 2
minimises used trips with no diversification penalties. This is the closest
analogue to the one-shot objective.

## Time-Limit Semantics

| Family | Budget |
|--------|--------|
| One-shot | `time_limit` seconds, single solve. |
| Two-stage | `time_limit` seconds **per stage**. Combined wall time can therefore reach ~2x `time_limit`. |

Per-stage budgets keep Stage 1's multi-shot bound-tightening and Stage 2's
packing search each properly resourced. The runner records both:

- `total_time` = `s1.total_time + s2.total_time` (matches `TwoStageResult.total_time`)
- `wall_time` = `perf_counter` measured around `solver.solve()`, includes inter-stage glue

## Cost Comparability

| Column | One-shot | Two-stage |
|--------|----------|-----------|
| `cost` | transport-cost objective | `s1_cost` (transport cost from Stage 1) |
| `s1_cost` | `None` | Stage 1 transport cost |
| `s2_cost` | `None` | Stage 2 used-trip count |

So `cost` is apples-to-apples across all four solvers. `s2_cost` is the
Stage 2 objective and should not be compared directly to one-shot `cost`.

## Parameters

- **Sizes**: paper, small, medium, large, xlarge, industrylite
- **Reps**: 3 per (solver, instance) (default)
- **Time limits** (per stage for two-stage):
  - paper, small: 30s
  - medium: 60s
  - large: 120s
  - xlarge: 300s
  - industrylite: 600s
- **Bins**: 3 (one-shot only)
- **Max frequency**: 20

## Running

From `new_code/`:

```bash
# Full sweep (4 solvers x all sizes x 3 reps)
uv run python -m multibatch.experiments.scalability.main

# Restrict to small instances for a quick run
uv run python -m multibatch.experiments.scalability.main --sizes paper small --reps 2

# Override time limits
uv run python -m multibatch.experiments.scalability.main --time-large 300 --time-xlarge 600

# Just one solver family
uv run python -m multibatch.experiments.scalability.main \
    --solvers naive_oneshot naive_twostage
```

## Output

- `results/scalability_raw.csv` — every run (one row per solver x instance x rep)
- `results/scalability_summary.csv` — averaged across reps per (solver, instance)

### CSV Columns

Identification: `solver`, `encoding_family`, `backend`, `instance`,
`instance_size`, `seed`, `num_bins`, `time_limit`, `run`, `status`.

Instance properties (from `experiments/twostage/config.py`):
`n_locations`, `n_parts`, `n_routes`, `n_transports`, `density`,
`capacity_tightness`.

Timing: `wall_time`, `total_time`, `ground_time`, `solve_time`.

Quality + search: `cost`, `optimum`, `satisfiable`, `choices`,
`conflicts`, `restarts`, `atoms`.

Two-stage extras (None for one-shot rows): `s1_time`, `s2_time`,
`s1_atoms`, `s2_atoms`, `s1_cost`, `s2_cost`, `s1_optimum`, `s2_optimum`.

`status` ∈ {`OK`, `S1_UNSAT`, `S2_UNSAT`, `TIMEOUT`, `ERROR`}.

## What the Experiment Tests

1. **Decomposition vs monolithic** — does splitting flow + packing scale
   better than solving them jointly?
2. **Backend x decomposition interaction** — does CASP (clingcon) benefit
   more or less from decomposition than pure ASP (naive)?
3. **Where the cost is paid** — `ground_time` vs `solve_time`, plus
   `s1_time` vs `s2_time` for two-stage, locates the bottleneck.
4. **Atom growth** — `atoms` (and `s1_atoms`, `s2_atoms`) shows ground
   program size by size and family, the key signal for ASP scaling.
