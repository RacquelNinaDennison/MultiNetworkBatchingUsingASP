# multibatch

Multi-commodity network batching solvers using Answer Set Programming (ASP).

Solves the combined routing, frequency assignment, and bin-packing problem for logistics networks where multiple part types must be shipped across transport arcs with capacity constraints.

## Installation

Requires Python 3.11+ and [clingo](https://potassco.org/clingo/) / [clingcon](https://github.com/potassco/clingcon).

```bash
# Clone and install
cd new_code
uv pip install -e .

# Or with uv (recommended)
uv sync
```

### Dependencies

- `clingo >= 5.6` — ASP solver
- `clingcon >= 5.2` — Constraint-programming extension for clingo
- `pydantic >= 2.0` ��� Data models
- `scipy >= 1.10` — Network flow computations (resilience metrics)

## Usage

### CLI

```bash
# Naive one-shot solver (pure ASP)
uv run multibatch --solver naive_oneshot -i instances/generated/layered_paper.lp --bins 2 --time-limit 60

# Clingcon one-shot solver (CSP variables for flow/frequency)
uv run multibatch --solver clingcon_oneshot -i instances/generated/layered_paper.lp --bins 2 --time-limit 60

# Use basic (non-optimised) encoding
uv run multibatch --solver naive_oneshot -i instances/generated/layered_paper.lp --no-optimised --bins 2

# Skip verification
uv run multibatch --solver naive_oneshot -i instances/generated/layered_paper.lp --no-verify
```

### Python API

```python
from multibatch.instance import parse_instance
from multibatch.solvers.naive import NaiveOneShotSolver
from multibatch.solvers.clingcon import ClingconOneShotSolver
from multibatch.models import NaiveOneShotConfig, ClingconOneShotConfig
from multibatch.verification import verify_solution

# Parse instance
instance = parse_instance("instances/generated/layered_small_seed1.lp")

# Configure and run naive solver
config = NaiveOneShotConfig(num_bins=2, time_limit=30)
solver = NaiveOneShotSolver("instances/generated/layered_small_seed1.lp", config)
result = solver.solve()

# Check result
if result:
    passed, errors = verify_solution(result, instance)
    print(f"Optimum: {result.metadata.optimum}")
    print(f"Time: {result.metadata.total_time}s")
    print(f"Valid: {passed}")
```

## Solvers

| Solver | Type | Description |
|--------|------|-------------|
| `naive_oneshot` | Pure ASP | Monolithic encoding with weak constraints. Supports basic and optimised variants. |
| `clingcon_oneshot` | Clingcon | Uses CSP integer variables for flow and frequency. Often faster on larger instances. |
| `twostage_naive` | Pure ASP | Stage 1: network flow. Stage 2: per-trip bin packing. *(coming soon)* |
| `twostage_clingcon` | Clingcon | Two-stage with CSP variables. *(coming soon)* |

## Project Structure

```
src/multibatch/
├── models/          # Pydantic data models (Instance, Config, Solution)
├── instance/        # Instance .lp parser
├── solvers/         # Solver implementations
├── verification/    # Solution correctness checks
├── metrics/         # Quality and resilience metrics
├��─ reporting/       # Console output formatting
└── encodings/       # ASP/LP encoding files
    ├── naive/       # Pure ASP encodings
    └── clingcon/    # Clingcon encodings
```

## Instance Format

Instances are ASP fact files (`.lp`) declaring:

```prolog
part(p1). part(p2).
location(l1). location(l2). location(l3).
route(l1, l3, tr1, 10, 5).          % route(From, To, Transport, Distance, Cost)
transportCapacity(tr1, 19).          % capacity per trip
partSize(p1, 4). partSize(p2, 3).    % weight/volume per unit
partVal(p1, 100). partVal(p2, 50).   % monetary value per unit
demandOffer(p1, l1, 10).             % positive = supply
demandOffer(p1, l3, -10).            % negative = demand
```
