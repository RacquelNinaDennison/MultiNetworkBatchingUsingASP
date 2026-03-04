# Combined Encodings

This directory contains Answer Set Programming (ASP) encodings for the **multi-network batching problem**: given a logistics network of locations, parts, routes, and transport resources, find an optimal set of recurring shipment patterns (bins/batches) that satisfies all supply and demand requirements at minimum cost.

## Problem Overview

The core problem involves:
- **Locations** that either supply or consume parts
- **Parts** with sizes that must be transported between locations
- **Routes** connecting locations via different transport resources (each with a capacity, distance, and cost)
- **Bins** (packing patterns) that define how many of each part to load per dispatch
- **Frequencies** that define how often each bin is dispatched on a route

The goal is to choose bins and dispatch frequencies such that:
1. All supply/demand requirements are met (flow conservation)
2. Transport capacity constraints are respected
3. Total transport cost (frequency × distance × cost) is minimised

---

## Encodings

### `encoding_route.lp` — Base ASP Encoding
The primary pure-ASP encoding. Uses `clingo` with explicit numeric domains (`numFlow`, `numFreq`, `numParts`) for flow values, frequencies, and pack quantities.

Key structure:
- **Flow network**: One flow value per (route, part) pair, constrained by supply/demand balance using `#sum` aggregates
- **Pack choices**: One packing pattern (bin) chosen per (route, bin-id, part) combination from feasible quantities
- **Frequency choices**: One dispatch frequency chosen per (route, bin-id) from a discrete domain
- **Flow support constraint**: The total flow delivered across all bins and frequencies must cover the required flow
- **Objective**: Minimise total shipping cost `freq × distance × cost`

### `optimised_encoding_route.lp` — Optimised ASP Encoding
An improved version of `encoding_route.lp` with additional constraints to tighten the search:
- **Feasibility pruning**: Only allows pack quantities `N` where `N * partSize <= transportCapacity` (eliminates infeasible pack choices early)
- **Arc-direction constraints**: Prevents packing a positive quantity of a part on an arc that goes the wrong way relative to supply/demand (no consumer exporting, no producer importing)
- **Bin validity constraints**: Ensures an active frequency implies a non-empty bin and vice versa
- **Symmetry breaking**: Enforces that if bin `ID2` is used, bin `ID1 < ID2` must also be used — eliminating equivalent solutions with permuted bin labels

### `encoding_alternative.lp` — Clingcon Encoding
An alternative encoding that uses **clingcon** (ASP with linear constraints over integers). Flow values and frequencies are modelled as constraint variables rather than discrete choice atoms.

Key differences from the base encoding:
- `&dom{ 0..maxFreq } = flow(...)` declares flow as a constraint variable with a bounded domain
- `&sum{...} = DemandValue` enforces flow conservation as a linear equality
- `frequency(...)` is a constraint variable; `auxilary(...)` variables link pack counts to frequencies via linear constraints
- `&minimize{...}` minimises cost as a linear objective
- Customers are prevented from exporting and suppliers from importing via `&sum{...} = 0` constraints

### `flingo_encoding.lp` — Flingo Encoding
A variant designed for use with **flingo** (a fuzzy/ASP extension tool). Uses a single bin (`numBins = 1`) and constraint variables for frequencies.

Key features:
- `freq(ID, From, To, TR)` is a constraint variable with bounds enforced conditionally on whether the bin is active
- Flow conservation is expressed directly over frequencies weighted by pack quantities — bypassing explicit flow variables
- Symmetry breaking on frequencies is expressed as a constraint inequality

---

## Instance Data

### `data/instances.lp`
A small test instance with:
- **6 locations**: `l1`–`l6`
- **2 transport resources**: `tr1` (capacity 10) and `tr2` (capacity 15)
- **1 part**: `p1` (size 4)
- Supply: `p1` produced at `l1` (10 units) and `l2` (20 units)
- Demand: `p1` consumed at `l5` (10 units) and `l6` (20 units)
- **20 routes** connecting locations with varying distances and costs

---

## How to Run

### Prerequisites
- Python 3.13
- A virtual environment is provided in `.venv/`

Activate it:
```bash
source .venv/bin/activate
```

### Running with clingo (base and optimised encodings)

```bash
# Base encoding
clingo data/instances.lp encodings/encoding_route.lp

# Optimised encoding
clingo data/instances.lp encodings/optimised_encoding_route.lp
```

To use multiple bins (default is 2, set by `numBins`):
```bash
clingo data/instances.lp encodings/optimised_encoding_route.lp --const numBins=3
```

### Running with clingcon (alternative encoding)

```bash
clingcon data/instances.lp encodings/encoding_alternative.lp
```

### Running with flingo (flingo encoding)

```bash
python -m flingo data/instances.lp encodings/flingo_encoding.lp
```

### Useful clingo flags

| Flag | Description |
|------|-------------|
| `-n 0` | Find all optimal solutions |
| `--opt-mode=optN` | Enumerate all optimal solutions |
| `-t 4` | Use 4 threads |
| `--time-limit=60` | Stop after 60 seconds |

Example:
```bash
clingo data/instances.lp encodings/optimised_encoding_route.lp -n 0 -t 4 --time-limit=60
```

---

## Output

All encodings show:
- `pack(N, Part, BinID, From, To, TR)` — pack `N` units of `Part` in bin `BinID` for route `From→To` via `TR`
- `freq(BinID, From, To, TR, F)` — dispatch bin `BinID` on route `From→To` via `TR` with frequency `F`
- `flow(From, To, Part, Value)` — flow of `Value` units of `Part` along arc `From→To`

The objective value reported is the total transport cost: `sum of (F × Distance × Cost)` over all active bins.
