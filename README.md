# Column Generation for Logistics Optimisation

An ASP/clingcon implementation of column generation for solving multi-commodity network flow problems with packing constraints, based on the formulation in Henning's thesis.

## Problem

Given a logistics network with locations, parts (products), and transport resources (trucks, ships, etc.), find the optimal:

- **Flow routing** — how parts travel through the network
- **Packing patterns** — what goes into each transport resource
- **Frequencies** — how many times each packing is dispatched on each route

The objective is to minimise total transport cost while satisfying all supply and demand constraints.

## Approach

The number of feasible packing patterns is combinatorially huge, making a monolithic solve impractical. Column generation avoids this by starting with a small set of packings and iteratively adding only those that improve the solution.

```
┌─────────────────────────────────────────────┐
│  MASTER PROBLEM  (clingcon)                 │
│  Solves flow + frequency jointly            │
│  Given: current packing pool                │
│  Output: optimal cost, flows, frequencies   │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  PYTHON DRIVER                              │
│  Computes shadow prices from solution       │
│  (our analogue of LP dual variables)        │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  PRICING SUBPROBLEM  (clingcon)             │
│  Finds best new packing for each TR         │
│  Maximises shadow-price value of contents   │
│  If reduced cost < 0 → add to pool, repeat  │
│  If no improvement   → converged            │
└─────────────────────────────────────────────┘
```

## Project Structure

```
column-generation-asp/
├── main.py                          # Entry point (CLI)
├── asp_files/
│   ├── master.lp                    # Master problem encoding (clingcon)
│   ├── pricing.lp                   # Pricing subproblem encoding (clingcon)
│   └── instances.lp                 # Instance data
├── src/
│   └── modules/
│       └── classes/
│           ├── __init__.py
│           ├── consts.py            # Solver configuration constants
│           ├── Master.py            # Column generation loop + master solver
│           ├── Pricing.py           # Pricing subproblem + shadow prices
│           └── Structures.py        # Data classes (Instance, PackingPool, etc.)
├── pyproject.toml
└── README.md
```

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- [clingcon](https://github.com/potassco/clingcon) (installed as a Python package via uv)

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd column-generation-asp

# Install dependencies with uv
uv sync
```

## Usage

```bash
uv run python main.py --master asp_files/master.lp \
                       --pricing asp_files/pricing.lp \
                       --instance asp_files/instances.lp
```

### Arguments

| Argument      | Description                                      |
|---------------|--------------------------------------------------|
| `--master`    | Path to the master problem ASP file              |
| `--pricing`   | Path to the pricing subproblem ASP file          |
| `--instance`  | Path to the instance data file                   |

## Instance Format

Instance files are standard ASP facts:

```prolog
% Locations
location(locA). location(locB). location(locC).

% Parts and their sizes
part(p1). part(p2).
partSize(p1, 2).
partSize(p2, 3).

% Supply (+) and Demand (-)
demandSupply(p1, locA,  6).     % locA supplies 6 of p1
demandSupply(p1, locC, -6).     % locC demands 6 of p1

% Transport resources and capacities
transportResource(truck).  transportCapacity(truck, 10).
transportResource(ship).   transportCapacity(ship,  20).

% Routes: route(From, To, TR, Distance, CostPerTrip)
route(locA, locB, ship,  5, 1).
route(locB, locC, truck, 3, 2).
```

## How It Works

### Master Problem (`master.lp`)

Jointly optimises flow routing and packing frequencies using clingcon. Contains three types of integer variables:

- `flow(From, To, Part)` — network flow (how many units of each part on each edge)
- `frequency(From, To, TR, PackID)` — how many times each packing is used on each route
- `slack(From, To, Part)` — Big-M feasibility slack (penalised in objective)

The coupling constraint links flow to frequency: the total capacity provided by all packings on an edge must cover the flow. This corresponds to equations 19, 20, and 34 in Henning's thesis.

### Pricing Subproblem (`pricing.lp`)

For a given transport resource, finds the packing pattern whose contents are most valuable (highest shadow-price value) subject to capacity. This corresponds to thesis equation 39.

Nogoods are injected as ASP rules to exclude previously found packings, using a `differ` atom pattern compatible with clingcon's theory constraints.

### Shadow Prices (Python)

Since clingcon solves integer programs (no LP duals available), shadow prices are approximated from the integer solution. For each part, the shadow price reflects its transport cost burden across the network:

```
π_p = Σ (cost_per_unit_on_edge × flow_of_part_on_edge)
```

Parts on expensive, high-volume edges get high shadow prices, guiding the pricing subproblem to generate packings that would reduce cost on those bottleneck routes.

### Convergence

The algorithm converges when no pricing subproblem finds a packing with negative reduced cost — meaning no new packing can improve the master's objective. The reduced cost formula is:

```
reduced_cost(B, route) = trip_cost(route) − Σ_p pack_qty_p × π_p
```

## Configuration

Solver parameters can be adjusted in `src/modules/classes/consts.py`:

| Parameter              | Default | Description                                |
|------------------------|---------|--------------------------------------------|
| `MAX_CG_ITERATIONS`   | 50      | Maximum column generation rounds           |
| `MAX_PACKINGS_PER_TR` | 10      | Candidate packings per TR per iteration    |
| `CONVERGENCE_PATIENCE` | 2      | Stop after N non-improving iterations      |



