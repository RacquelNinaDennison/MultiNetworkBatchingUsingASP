# Two-Stage Logistics Optimisation with Resilience Analysis

Project investigating supply chain resilience through a two-stage decomposition of the multi-commodity network batching problem. Stage 1 solves aggregate network flow; Stage 2 solves per-trip bin packing. Resilience metrics are computed via max-flow simulation of arc and trip disruptions.

> **The main entry point for all solvers and experiments is the `new_code/` directory**, which contains the `multibatch` Python package. The legacy `src/` directory holds earlier prototype code and is retained for reference only.

---

## Problem Overview

This project solves the multi-batching problem: multiple part types must be assigned to transport resources routed around a logistics network. The problem is formulated and solved using Answer Set Programming (ASP), with both pure ASP and clingcon (ASP + constraint programming) backends.

---

## Approach

### Stage 1 — Network Flow (Tactical)

Solves for:
- `load(From, To, TR, P)` — total units of part P shipped on each arc (CSP variable)
- `routeFreq(From, To, TR, Freq, TotalCap)` — number of trips and total capacity on each arc

Minimises CO₂ cost + transport cost using iterative bound-tightening (multi-shot solving with `clingcon`).

Two feasibility safeguards ensure Stage 1 solutions are packable by Stage 2:
1. **Per-item constraint** — load of each part cannot exceed `floor(capacity / size) × frequency`
2. **80% utilisation headroom** — aggregate volume capped at 80% of total capacity to absorb combinatorial packing effects

### Stage 2 — Per-Trip Bin Packing (Operational)

Takes Stage 1 aggregate flows as fixed input and solves:
- `tripLoad(From, To, TR, P, K)` — units of part P on trip K

Core constraints: conservation (all units assigned), per-trip capacity. Configurable objectives:

| Configuration | Objective |
|---|---|
| `baseline` | No quality signal — solver default |
| `hetero` | Soft penalties for mono-SKU trips (diversity) |
| `conc` | Soft penalties for load concentration |
| `both` | Both diversity and concentration penalties |

### Resilience Metrics

Computed via max-flow simulation on the trip-level solution:

| Metric | Description |
|---|---|
| **R_TR** | Arc disruption resilience — fraction of demand met if a route is lost |
| **R_1** | Trip disruption resilience — fraction of demand met if a single trip is lost |
| **K_1** | Kit completion ratio — fraction of complete orders satisfied under worst-case trip loss |
| **R_alpha** | Partial disruption resilience — demand met when α% of trips survive |

---

## Repository Structure

```
combined_encodings/
├── new_code/                            # Main package (start here)
│   ├── pyproject.toml                   # Package config & dependencies
│   ├── uv.lock
│   └── src/multibatch/
│       ├── cli.py                       # CLI entry point
│       ├── models/                      # Pydantic data models (Instance, Config, Solution)
│       ├── instance/                    # Instance .lp parser
│       ├── solvers/                     # Solver implementations
│       │   ├── naive.py                 # Pure ASP one-shot solver
│       │   ├── clingcon.py              # Clingcon one-shot solver
│       │   ├── twostage_naive.py        # Two-stage pure ASP
│       │   └── twostage_clingcon.py     # Two-stage clingcon
│       ├── encodings/                   # ASP/LP encoding files
│       │   ├── naive/                   # Pure ASP encodings
│       │   ├── clingcon/                # Clingcon encodings
│       │   └── twostage/               # Two-stage encodings (naive + clingcon)
│       ├── verification/                # Solution correctness checks
│       ├── metrics/                     # Quality and resilience metrics
│       ├── reporting/                   # Console output formatting
│       ├── visualisation/               # Network visualisation
│       ├── experiments/                 # Benchmarking and experiment runners
│       └── instances/                   # Problem instances
│           └── generated/               # Synthetic instances (paper → xlarge)
└── src/                                 # Legacy prototype code (reference only)
```

---

## Installation

Requires Python ≥ 3.11 and [`uv`](https://github.com/astral-sh/uv).

```bash
git clone <repo-url>
cd combined_encodings/new_code
uv sync
```

### Dependencies

| Package | Purpose |
|---|---|
| `clingo` | ASP solver |
| `clingcon` | ASP + constraint solving |
| `pydantic` | Data models |
| `scipy` | Network flow for resilience metrics |

---

## Usage

All commands run from the `new_code/` directory.

### Single solve

```bash
# Naive one-shot solver (pure ASP)
uv run multibatch --solver naive_oneshot \
    -i src/multibatch/instances/generated/layered_paper.lp \
    --bins 2 --time-limit 60

# Clingcon one-shot solver
uv run multibatch --solver clingcon_oneshot \
    -i src/multibatch/instances/generated/layered_paper.lp \
    --bins 2 --time-limit 60

# Two-stage naive solver
uv run multibatch --solver twostage_naive \
    -i src/multibatch/instances/generated/layered_paper.lp \
    --bins 2 --time-limit 60

# Two-stage clingcon solver
uv run multibatch --solver twostage_clingcon \
    -i src/multibatch/instances/generated/layered_paper.lp \
    --bins 2 --time-limit 60

# Use basic (non-optimised) encoding
uv run multibatch --solver naive_oneshot \
    -i src/multibatch/instances/generated/layered_paper.lp \
    --no-optimised --bins 2

# Skip verification
uv run multibatch --solver naive_oneshot \
    -i src/multibatch/instances/generated/layered_paper.lp \
    --no-verify
```

Futhermore, to visualise the packings, run 

```
uv run multibatch --solver naive_oneshot \
    -i src/multibatch/instances/generated/layered_paper.lp \
    --visualise

```


image.png


### Python API

```python
from multibatch.instance import parse_instance
from multibatch.solvers.naive import NaiveOneShotSolver
from multibatch.solvers.clingcon import ClingconOneShotSolver
from multibatch.models import NaiveOneShotConfig, ClingconOneShotConfig
from multibatch.verification import verify_solution

# Parse instance
instance = parse_instance("src/multibatch/instances/generated/layered_small_seed1.lp")

# Configure and run solver
config = NaiveOneShotConfig(num_bins=2, time_limit=30)
solver = NaiveOneShotSolver("src/multibatch/instances/generated/layered_small_seed1.lp", config)
result = solver.solve()

# Check result
if result:
    passed, errors = verify_solution(result, instance)
    print(f"Optimum: {result.metadata.optimum}")
    print(f"Time: {result.metadata.total_time}s")
    print(f"Valid: {passed}")
```

---

## Solver Backends

| Backend | Description |
|---|---|
| `naive_oneshot` | Pure ASP monolithic encoding with weak constraints |
| `clingcon_oneshot` | Uses CSP integer variables for flow and frequency |
| `twostage_naive` | Two-stage pipeline using pure ASP |
| `twostage_clingcon` | Two-stage pipeline using clingcon CSP variables |

---

## Instance Format

Instances are ASP fact files (`.lp`):

```prolog
% Locations and parts
location(l1). location(l2). location(l3).
part(p1). part(p2).

% Supply (+) and demand (-)
demandOffer(p1, l1, 10).    % l1 supplies 10 units of p1
demandOffer(p1, l2, -10).   % l2 demands 10 units of p1

% Part properties
partSize(p1, 4).             % 4 volume units per item
partVal(p1, 1000).           % value per unit (for holding cost)

% Transport and routes
transportCapacity(tr1, 15).
route(l1, l2, tr1, 100, 500).  % From, To, Transport, Distance, Cost
```

---

