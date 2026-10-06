# Reproducing the experiments

This ReadMe acts as a reference for the experiments ran on the multi batching problem. 

## Choose the experiment

| Experiment | Purpose | Instructions |
| --- | --- | --- |
| Benchmark | Compare four one-shot encoding variants | [benchmark/README.md](benchmark/README.md) |
| Scalability | Compare one-shot and two-stage ASP/clingcon | [scalability/README.md](scalability/README.md) |
| MILP resilience | MILP/ASP network stages plus weighted packing; tables and figures | [milp_resilience/README.md](milp_resilience/README.md) |


## Environment

Use Python 3.11 or newer and the checked-in `uv.lock`:

```bash
uv sync --locked
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
uv run --no-sync python -c "import clingo, clingcon, scipy, pandas, matplotlib; from ortools.linear_solver import pywraplp; assert pywraplp.Solver.CreateSolver('SCIP') is not None; print('Experiment imports and SCIP backend available')"
```


## Saved reports versus fresh experiments

We saved reports on experiments produced for our own purpose. 
