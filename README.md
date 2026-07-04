# Two-Stage Logistics Optimisation with Resilience Analysis

Masters project investigating supply-chain resilience through a two-stage
decomposition of the multi-commodity network batching problem. **Stage 1**
solves aggregate network flow; **Stage 2** solves per-trip bin packing.
Resilience metrics are computed by max-flow simulation of arc and trip
disruptions.

The whole project is the `multibatch` Python package (`src/multibatch/`).

---

## Problem Overview

Multiple part types must be assigned to transport resources routed around a
logistics network. The model is solved with Answer Set Programming (ASP) —
pure ASP and clingcon (ASP + constraint programming) backends — with an
optional MILP oracle for the Stage-1 flow.

The core insight: aggregate-optimal flow can be **operationally infeasible** to
pack into discrete trips. The two-stage decomposition makes the aggregate
(tactical) and per-trip (operational) decisions explicit, and packing-diversity
objectives in Stage 2 are shown to improve disruption resilience.

### Stage 1 — Network Flow (tactical)

- `load(From, To, TR, P)` — units of part `P` shipped on each arc
- `routeFreq(From, To, TR, Freq, TotalCap)` — trips and total capacity per arc

Minimises CO₂ + transport cost. Two feasibility safeguards keep Stage 1
solutions packable by Stage 2: a per-item bound and a configurable capacity
utilisation envelope (default 70%, `1.0` = the paper's exact constraint).

Stage 1 can be solved three ways: clingcon multi-shot (`twostage_clingcon`),
pure ASP (`twostage_naive`), or a MILP oracle (`milpflow_twostage`, OR-Tools).

### Stage 2 — Per-Trip Bin Packing (operational)

Takes Stage 1 flows as fixed input and solves `tripLoad(From, To, TR, P, K)`.
Configurable packing objectives:

| Config | Objective |
|---|---|
| `baseline` | cost only — no quality signal |
| `hetero` | penalise mono-SKU trips (diversity) |
| `conc` | penalise load concentration |
| `both` | diversity + concentration |

### Resilience Metrics

Computed by max-flow simulation on the trip-level solution:

| Metric | Description |
|---|---|
| `R_TR` | arc-disruption resilience (one route lost) |
| `R_resource` | network/fleet-level resilience (a whole transport resource lost) |
| `R_1` | single-trip-disruption resilience |
| `K_1` | kit-completion ratio under worst-case trip loss |
| `R_alpha` / `NRI_alpha` / `CVaR_alpha` | partial-disruption resilience: worst-case / mean / tail when α% of trips survive |

---

## Repository Structure

```
.
├── pyproject.toml            # package config & dependencies (uv)
├── uv.lock
├── src/multibatch/
│   ├── cli.py                # CLI entry point
│   ├── models/               # pydantic data models (Instance, Config, Solution)
│   ├── instance/             # instance .lp parser
│   ├── solvers/              # naive / clingcon / two-stage / MILP-flow solvers
│   ├── encodings/            # ASP/LP encoding files (naive, clingcon, twostage)
│   ├── verification/         # solution correctness checks
│   ├── metrics/              # coverage & resilience metrics
│   ├── reporting/            # console output
│   ├── visualisation/        # interactive network visualisation
│   ├── instances/generated/  # synthetic instances (paper → xlarge)
│   └── experiments/          # benchmark / scalability / twostage / milp_resilience / packing_stress
└── Docs/                     # thesis writing (kept outside git — Overleaf/local)
```

---

## Installation

Requires Python ≥ 3.11 and [`uv`](https://github.com/astral-sh/uv).

```bash
uv sync
```

> **macOS note:** if `uv run multibatch` fails with `ModuleNotFoundError: No
> module named 'multibatch'`, the editable-install `.pth` files in `.venv` have
> been marked hidden by APFS. Fix with `chflags -R nohidden .venv` (wrapped in
> the `make setup` target).

### Dependencies

| Package | Purpose |
|---|---|
| `clingo` | ASP solver |
| `clingcon` | ASP + constraint solving |
| `ortools` | MILP backend for the Stage-1 flow oracle |
| `pydantic` | data models |
| `scipy` | max-flow for resilience metrics |

---

## Usage

All commands run from the repository root. Before running the application, you need to ensure that all the environments are setup properly. In the root folder, run 
```bash
make setup
```

```bash
# One-shot solvers
uv run multibatch --solver naive_oneshot    -i src/multibatch/instances/generated/layered_paper.lp --bins 2 --time-limit 60
uv run multibatch --solver clingcon_oneshot -i src/multibatch/instances/generated/layered_paper.lp --bins 2 --time-limit 60

# Two-stage solvers
uv run multibatch --solver twostage_naive    -i src/multibatch/instances/generated/layered_paper.lp --bins 2 --time-limit 60
uv run multibatch --solver twostage_clingcon -i src/multibatch/instances/generated/layered_paper.lp --bins 2 --time-limit 60

# MILP Stage-1 flow oracle (OR-Tools) + ASP Stage-2 packing
uv run multibatch --solver milpflow_twostage -i src/multibatch/instances/generated/layered_paper.lp --utilisation 0.7 --flow-time-limit 60 --time-limit 60

# Basic (non-optimised) encoding / skip verification / visualise
uv run multibatch --solver naive_oneshot -i src/multibatch/instances/generated/layered_paper.lp --no-optimised --bins 2
uv run multibatch --solver naive_oneshot -i src/multibatch/instances/generated/layered_paper.lp --no-verify
uv run multibatch --solver naive_oneshot -i src/multibatch/instances/generated/layered_paper.lp --visualise
```

### Python API

```python
from multibatch.instance import parse_instance
from multibatch.solvers.naive import NaiveOneShotSolver
from multibatch.models import NaiveOneShotConfig
from multibatch.verification import verify_solution

inst_path = "src/multibatch/instances/generated/layered_small_seed1.lp"
instance = parse_instance(inst_path)

config = NaiveOneShotConfig(num_bins=2, time_limit=30)
result = NaiveOneShotSolver(inst_path, config).solve()
if result:
    passed, errors = verify_solution(result, instance)
    print(result.metadata.optimum, result.metadata.total_time, passed)
```

---

## Solver Backends

| Backend | Description |
|---|---|
| `naive_oneshot` | pure-ASP monolithic encoding with weak constraints |
| `clingcon_oneshot` | CSP integer variables for flow and frequency |
| `twostage_naive` | two-stage pipeline, pure ASP |
| `twostage_clingcon` | two-stage pipeline, clingcon CSP |
| `milpflow_twostage` | MILP Stage-1 flow oracle (OR-Tools) + ASP Stage-2 packing |

---

## Experiments

Each suite under `src/multibatch/experiments/` produces append-only CSVs and a
per-folder Jupyter notebook that loads those CSVs and renders the figures and
tables:

| Suite | Question |
|---|---|
| `benchmark/` | one-shot encoding shootout (ASP vs clingcon, basic vs optimised) |
| `scalability/` | one-shot vs two-stage decomposition scaling |
| `twostage/` | resilience–cost trade-off: weight sweep × Stage-2 configs |
| `milp_resilience/` | MILP-flow + ASP-packing resilience suite (the main resilience study) |
| `packing_stress/` | Stage-2 packing stress test on synthetic arcs |

---

## Instance Format

Instances are ASP fact files (`.lp`):

```prolog
location(l1). location(l2). location(l3).
part(p1). part(p2).
demandOffer(p1, l1, 10).        % +supply / -demand
demandOffer(p1, l2, -10).
partSize(p1, 4).                % volume per unit
partVal(p1, 1000).              % value per unit (holding cost)
transportCapacity(tr1, 15).
route(l1, l2, tr1, 100, 500).   % From, To, Transport, Distance, Cost
```
