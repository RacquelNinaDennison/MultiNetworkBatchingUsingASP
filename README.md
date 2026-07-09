# Two-Stage Logistics Optimisation with Resilience Analysis

Masters project investigating supply-chain resilience through a two-stage
decomposition of the multi-commodity network batching problem. **Stage 1**
solves aggregate network flow; **Stage 2** solves per-trip bin packing.
Resilience metrics are computed by max-flow simulation of arc and trip
disruptions.

The whole project is the `multibatch` Python package (`src/multibatch/`).

---

## What This Repository Reproduces

The reference model is the multi-batching problem of Dietz et al., *Scaling
Industrial Logistics: Tackling Multi-Batching Problems via Sequential Solving*
(CP 2026). The paper decomposes the problem sequentially: an aggregated-flow
MILP ("MOP") decides how many units of each product travel on each arc, and a
subsequent step packs those flows into discrete trips.

This repository reproduces the paper's **Stage-1 aggregated-flow model** and
its **industrial instance**, then uses that validated base for a resilience
study the paper does not attempt.

### Instance reproduction

`src/multibatch/instances/generated/industry_test_1.lp` matches the paper's
industrial instance (§6.1) exactly:

| | Paper | `industry_test_1.lp` |
|---|---|---|
| locations | 50 | 50 |
| OD pairs | 1,532 | 1,532 |
| routes | 5,610 | 5,610 |
| transport resources | 16 | 16 |
| products | 35 | 35 |

The synthetic `layered_*` instances (paper, small, medium, large, xlarge,
industrylite; several seeds each) scale the same generator between toy size
and the industrial instance.


### What the project adds beyond the paper

1. **ASP implementations.** Both stages are solved with Answer Set
   Programming (pure ASP and clingcon backends), with the paper-style MILP
   available as a Stage-1 oracle (`milpflow_twostage`). The encodings live in
   `src/multibatch/encodings/`.
2. **Packing-diversity objectives.** Stage 2 gains optional soft constraints
   (`hetero`, `conc`) that diversify how parts are spread across trips.
3. **Resilience analysis.** Trip-level solutions are stress-tested by max-flow
   simulation of disruptions (lost arcs, lost trips, lost transport
   resources), quantified by the metrics below. The central research question:
   does paying a small dispatch-cost premium for diversified packing buy
   measurable disruption tolerance?

---

## Problem Overview

Multiple part types must be assigned to transport resources routed around a
logistics network. The model is solved with Answer Set Programming (ASP) with an
optional MILP oracle for the Stage-1 flow.

The core insight: aggregate-optimal flow can be **operationally infeasible** to
pack into discrete trips. The two-stage decomposition makes the aggregate
(tactical) and per-trip (operational) decisions explicit, and packing-diversity
objectives in Stage 2 are shown to improve disruption resilience.

### Stage 1 — Network Flow (tactical)

- `load(From, To, TR, P)` :units of part `P` shipped on each arc
- `routeFreq(From, To, TR, Freq, TotalCap)` : trips and total capacity per arc

Minimises CO₂ + transport cost. Two feasibility safeguards keep Stage 1
solutions packable by Stage 2: a per-item bound and a configurable capacity
utilisation envelope.

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

Computed by max-flow simulation on the trip-level solution
(`src/multibatch/metrics/`):

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
├── Makefile                  # setup / test / lint targets
├── src/multibatch/
│   ├── cli.py                # CLI entry point (single solves)
│   ├── models/               # pydantic data models (Instance, Config, Solution)
│   ├── instance/             # instance .lp parser
│   ├── solvers/              # naive / clingcon / two-stage / MILP-flow solvers
│   ├── encodings/            # ASP/LP encoding files (naive, clingcon, twostage)
│   ├── verification/         # solution correctness checks
│   ├── metrics/              # coverage & resilience metrics
│   ├── reporting/            # console output
│   ├── visualisation/        # interactive network visualisation
│   ├── instances/generated/  # synthetic instances (paper → xlarge) + industry_test_1
│   └── experiments/          # the five experiment suites (see below)
└── Docs/                     # thesis writing (kept outside git — Overleaf/local)
```

---

## Installation and Environment

Requires Python ≥ 3.11 and [`uv`](https://github.com/astral-sh/uv).

```bash
make setup
```

`make setup` runs `uv sync` into `.venv.nosync` and keeps `.venv` as a symlink
to it. After that, plain `uv run ...` works as normal.

### Dependencies

| Package | Purpose |
|---|---|
| `clingo` | ASP solver |
| `clingcon` | ASP + constraint solving |
| `ortools` | MILP backend for the Stage-1 flow oracle |
| `pydantic` | data models |
| `scipy` | max-flow for resilience metrics |

---

## Usage — Single Solves

All commands run from the repository root.

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

`uv run multibatch --help` lists every flag.

### Solver Backends

| Backend | Description |
|---|---|
| `naive_oneshot` | pure-ASP monolithic encoding with weak constraints |
| `clingcon_oneshot` | CSP integer variables for flow and frequency |
| `twostage_naive` | two-stage pipeline, pure ASP |
| `twostage_clingcon` | two-stage pipeline, clingcon CSP |
| `milpflow_twostage` | MILP Stage-1 flow oracle (OR-Tools) + ASP Stage-2 packing |

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

## Experiments

The five suites under `src/multibatch/experiments/` answer the thesis
questions in sequence:

| Suite | Question |
|---|---|
| `benchmark/` | one-shot encoding shootout (ASP vs clingcon, basic vs optimised) |
| `scalability/` | one-shot vs two-stage decomposition scaling |
| `twostage/` | resilience–cost trade-off: weight sweep × Stage-2 configs |
| `milp_resilience/` | MILP-flow + ASP-packing resilience suite (the main resilience study) |
| `packing_stress/` | Stage-2 packing stress test on synthetic arcs |

### Conventions shared by all suites

- **Results are checked in.** Every suite's `results/` directory contains the
  captured CSVs, so all notebooks render their figures and tables without
  re-running a single solver. Re-running the harnesses is only needed to
  produce new data.
- **Harnesses are modules.** Each suite is invoked as
  `uv run python -m multibatch.experiments.<suite>.<module>`; every harness
  accepts `--help`. `benchmark/`, `scalability/`, and `twostage/` also ship a
  `run_all.sh` batch wrapper for full overnight sweeps.
- **Notebooks come in two kinds.** The twostage notebooks
  (`results/eda.ipynb`, `results/eda_rel.ipynb`) are **generated** by
  `results/_build_eda.py` and `results/_build_eda_rel.py`. Edit the builder,
  regenerate, then execute; never hand-edit those notebooks, or the edits die
  at the next regeneration. All other notebooks are hand-written and edited
  directly.
- Output paths are anchored on each package's own directory, so any command
  can be run from any working directory.

### `benchmark/` — one-shot encoding shootout

Compares `naive_oneshot` and `clingcon_oneshot` (basic and optimised
encodings) across instance sizes and bin counts.

```bash
uv run python -m multibatch.experiments.benchmark.main --help
src/multibatch/experiments/benchmark/run_all.sh        # full sweep
src/multibatch/experiments/benchmark/run_portfolio.sh  # clingo configuration portfolio
```

Outputs `results/benchmark_raw_<tag>.csv` + `results/benchmark_summary_<tag>.csv`.
Analysis: `results/eda.ipynb`.

### `scalability/` — one-shot vs two-stage

Runs the four ASP solver variants across sizes paper → industrylite with
per-size time limits. Note the time-limit semantics: two-stage solvers get the
budget **per stage**, so combined wall time can reach twice the one-shot
budget; the `wall_time` column records the real combined wall clock.

```bash
uv run python -m multibatch.experiments.scalability.main --help
src/multibatch/experiments/scalability/run_all.sh
```

Outputs raw + summary CSVs in `results/`. Analysis: `results/eda.ipynb`.

### `twostage/` — resilience–cost trade-off (clingcon)

The weight sweep at the heart of the thesis: Stage-1 exposure weight (absolute
`w`, or dimensionless `λ` in relative mode) × Stage-2 packing configs
(`baseline / mixed / even / full`), with all resilience metrics recorded per
run. Appends one CSV row per completed run and resumes idempotently
(`--resume`).

```bash
uv run python -m multibatch.experiments.twostage --help
src/multibatch/experiments/twostage/run_all.sh

# summary tables (mean ± bootstrap CI):
uv run python -m multibatch.experiments.twostage.make_summary_tables
```

Outputs `results/experiment_*.csv` (absolute sweep) and
`results/experiment_rel_*.csv` (λ sweep). Analysis: `results/eda.ipynb`
(absolute) and `results/eda_rel.ipynb` (relative) — both generated, see
conventions above.

### `milp_resilience/` — the main resilience study

MILP cost-optimal flow (Stage 1) + ASP packing (Stage 2) under a
`(w_net, w_flow)` flow-weight grid × packing configs
(`baseline / hetero_w8 / conc_w8 / full_w8_8`), on the layered and industrial
instances. Stage-1 flows are cached as JSON under `results/flows/`, so packing
sweeps and probes re-use solved flows instead of re-solving.


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
