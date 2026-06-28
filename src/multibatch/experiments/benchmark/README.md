# Benchmark Experiments

Benchmarks for comparing one-shot solver configurations on the multi-commodity network batching problem.

## Solvers Tested

| Name | Encoding | Description |
|------|----------|-------------|
| `naive_basic` | `encoding_route.lp` | Pure ASP, no symmetry breaking |
| `naive_optimised` | `optimised_encoding_route.lp` | Pure ASP + feasibility pruning + symmetry breaking |
| `clingcon` | `clingcon_binpacking.lp` | CASP with CSP flow/frequency variables |
| `clingcon_optimised` | `optimised_clingcon_binpacking.lp` | CASP + tighter domains + symmetry breaking + freq-pack consistency |

## Parameters

- **Bins**: 0-5 (number of bin configurations per route)
- **Repetitions**: 5 per configuration (results averaged)
- **Time limit**: 60s per run
- **Max frequency**: 20

## Running

From the `new_code/` directory:

```bash
# Full benchmark (all solvers, all instances, bins 0-5, 5 reps)
uv run python -m multibatch.experiments.benchmark.main
```

## Output

Results are written to `results/`:

- `benchmark_raw.csv` — every individual run
- `benchmark_summary.csv` — averaged across repetitions per (solver, instance, bins)

### CSV Columns

| Column | Description |
|--------|-------------|
| `solver` | Solver configuration name |
| `instance` | Instance filename (without .lp) |
| `instance_size` | Size category: paper, small, medium, large, xlarge, industrylite |
| `num_bins` | Number of bins (0-5) |
| `run` | Repetition number (raw CSV only) |
| `ground_time` | Time to ground the program (seconds) |
| `solve_time` | Time spent solving after grounding (seconds) |
| `total_time` | Total wall time including grounding (seconds) |
| `cost` | Objective value of best solution found |
| `optimum` | Whether optimality was proven |
| `satisfiable` | Whether any solution was found |
| `choices` | Solver decision points (search space explored) |
| `conflicts` | Dead ends / backtrack points |
| `restarts` | Full search restarts with learned clauses |
| `atoms` | Number of ground atoms (program size after grounding) |

## What the Experiments Test

1. **Grounding vs solving tradeoff** — CPU time as bins increase (naive grounds large programs; clingcon stays compact)
2. **Symmetry breaking benefit** — naive_basic vs naive_optimised, clingcon vs clingcon_optimised
3. **ASP vs CASP atom comparison** — ground program size across approaches
4. **Scalability** — how each solver handles small through xlarge instances
