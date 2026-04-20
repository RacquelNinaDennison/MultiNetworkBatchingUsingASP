# Two-Stage Logistics Optimisation with Resilience Analysis

Project investigating supply chain resilience through a two-stage decomposition of the multi-commodity network batching problem. Stage 1 solves aggregate network flow; Stage 2 solves per-trip bin packing. Resilience metrics are computed via max-flow simulation of arc and trip disruptions.

---

## Problem Overview

This project aims to solve the multi batching problem whereby multiple parts need to be assigned to transport resources which are routed around a network. The problem is solved using a logic programming language, ASP. 

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
├── src/
│   ├── main.py                          # CLI entry point
│   ├── modules/                         # Solver implementations
│   │   ├── run_two_stage.py             # Two-stage pipeline (clingcon)
│   │   ├── run_two_stage_naive.py       # Two-stage pipeline (pure ASP)
│   │   ├── run_two_stage_pipeline.py    # Pipeline from pre-computed Stage 1
│   │   ├── base_solver.py               # Abstract solver interface
│   │   └── checking.py                  # Solution validation
│   ├── encoding/
│   │   ├── twostage/clingcon/           # Clingcon ASP encodings (Stage 1 + Stage 2)
│   │   └── twostage/naive/             # Pure ASP encodings
│   ├── instances/
│   │   ├── generated/                   # Synthetic instances (small → xlarge)
│   │   └── industry/                    # Industry-derived instances
│   └── experiments/
│       └── two_stage/final/
│           ├── run_full_experiment.py   # Main experiment runner
│           ├── generate_reports.py      # CSV summaries and analysis tables
│           └── plot_*.py               # Visualisation scripts
└── pyproject.toml
```

---

## Installation

Requires Python ≥ 3.13 and [`uv`](https://github.com/astral-sh/uv).

```bash
git clone <repo-url>
cd combined_encodings
uv sync
```

### Dependencies

| Package | Purpose |
|---|---|
| `clingcon` | ASP + constraint solving |
| `networkx` + `scipy` | Max-flow for resilience metrics |
| `pandas` | Experiment result aggregation |
| `matplotlib` | Plotting |

---

## Usage

### Single solve

```bash
# Two-stage pipeline on a small instance
uv run src/main.py \
    --solver twostage-clingcon \
    --instance src/instances/generated/paper.lp

# With custom timeouts
uv run src/main.py \
    --solver twostage-clingcon \
    --instance src/instances/generated/paper.lp \
    --round-timeout 30 \
    --max-rounds 10
```

### Full experiment

Sweeps across instances, Stage 2 configurations, and resilience weight settings:

```bash
# Small instances (~1.3h)
uv run src/experiments/two_stage/final/run_full_experiment.py \
    --size small --output results/small.json

# Medium instances (~5h)
uv run src/experiments/two_stage/final/run_full_experiment.py \
    --size medium --output results/medium.json
```

### Reports and plots

```bash
uv run src/experiments/two_stage/final/generate_reports.py \
    --input results/ --output reports/

uv run src/experiments/two_stage/final/plot_paper.py \
    --input results/ --output figures/
```

---

## Instance Format

Instances are written in ASP fact format:

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

Instance generators are in `src/instances/modules/`.

---

## Solver Backends

| Backend | Description |
|---|---|
| `twostage-clingcon` | Two-stage pipeline using clingcon CSP variables (recommended) |
| `twostage-naive` | Two-stage pipeline using pure ASP (grounding-heavy) |
| `twostage-pipeline` | Load pre-computed Stage 1 from JSON, run Stage 2 only |
| `clingcon` | Single-stage clingcon (baseline comparison) |
| `naive` | Single-stage pure ASP (baseline comparison) |

---

