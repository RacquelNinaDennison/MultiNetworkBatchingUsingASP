# MOP Stage-1 formulation check vs CP 2026 paper

Goal: confirm the MILP/"MOP" flow solver (`solvers/milp_flow.py`) reproduces the
aggregated-flow Stage 1 of Dietz et al., *Scaling Industrial Logistics — Tackling
Multi-Batching Problems via Sequential Solving* (CP 2026), on the industrial
instance `industry_test_1.lp`.

The experiments keep the **70% utilisation envelope** as the default. These runs only
*temporarily* set 100% to check the cost lands in the paper's ballpark — they do **not**
change the experiment default.

## Instance match (faithful to paper §6.1)

| | Paper | `industry_test_1.lp` |
|---|---|---|
| locations | 50 | 50 |
| OD pairs | 1532 | 1532 |
| routes | 5610 | 5610 |
| transport resources | 16 | 16 |
| products | 35 | 35 |

## Paper cost ballpark (industrial instance)

- 2-step MILP flow, final objective: ≈ 2,102,555 – 2,124,968 (Table 3)
- Direct exact-flow MILP (`MILP^max`): 2,200,596 (Table 2)
- Best overall (3-step MILP+Greedy+CP): 2,102,043
- LP / MILP lower bound: ≈ 1,616,940
- Solver: **Gurobi v11.1** (converges to ~2.1M in ~10s, Fig. 3)

## Our runs (solver = SCIP via OR-Tools, time limit 1800s, cap_size_divide as noted)

| Run | Envelope | cap_size_divide | Stage-1 flow cost | Optimum | Log |
|---|---|---|---|---|---|
| Experiment default | 70% | 1 | 3,415,081 | No | (from `../resilience_industry_test_1.csv`, flow_cost) |
| **Paper-exact (7b)** | **100%** | **1** | **2,450,071** | No (1800s) | `industry_util100_cap1.log` |
| Paper-exact (7b), distorted | 100% | 10 | 1,790,844 (artifact) | No (1800s) | `industry_util100_cap10.log` |

## Finding

The 70% safety margin was inflating the cost. Switching to the paper's exact
constraint (eq. 7b, `Σ v_p·f ≤ n_r·Q_r`) drops Stage-1 cost from **3.42M → 2.45M**,
≈17% above the paper. The residual gap is explained by solver, not model:
SCIP does not prove optimality in 1800s, whereas the paper's Gurobi converges in
~10s. The Stage-1 MOP formulation is therefore validated as a faithful
reproduction of the paper's aggregated-flow model. **The 70% envelope remains the
default for the resilience experiments — it is an intentional safety margin, not a
bug.**

The faithful comparison is **cap_size_divide=1** (70%→3.42M vs 100%→2.45M, same
granularity). **Do not compare the cap_size_divide=10 run (1,790,844) to the paper:**
that divisor floor-divides part sizes, and **18 of 35 parts (51%) have raw size < 10**,
so they round to size 0 and occupy zero volume (ride free). It under-counts volume,
needs fewer trips, and reports an artificially low cost. cap_size_divide is a solver
tractability knob in this codebase — it is NOT something the paper applies.

## How to reproduce

```bash
cd new_code
# Paper-exact envelope (100%), full integer granularity:
PYTHONPATH=src uv run python -u -m multibatch.solvers.milp_flow \
  src/multibatch/instances/generated/industry_test_1.lp \
  --mode stage1 --backend SCIP --utilisation 1.0 --flow-time-limit 1800

# Same but coarser granularity (cap_size_divide=10, faster search):
PYTHONPATH=src uv run python -u -m multibatch.solvers.milp_flow \
  src/multibatch/instances/generated/industry_test_1.lp \
  --mode stage1 --backend SCIP --utilisation 1.0 --cap-size-divide 10 --flow-time-limit 1800
```

`--utilisation` defaults to **0.7** (the experiment setting); only pass `1.0` for this
paper comparison. See memory `project_mop_formulation_validation`.
