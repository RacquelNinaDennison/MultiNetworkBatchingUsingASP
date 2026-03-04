# Masters Research — Logistics Network Optimisation Using ASP

This repo consists of encodings investigating how **Answer Set Programming (ASP)** and hybrid declarative/algorithmic methods can be applied to solve large-scale logistics network co-design problems.

The central problem — drawn from real-world supply chain design — is to simultaneously determine *what* to pack into transport vehicles, *how frequently* to dispatch them, and *how* to route goods through a multi-location network, minimising total cost while satisfying all supply and demand constraints.

---

## Research Overview

### The Problem

A logistics network consists of:
- **Locations** — nodes that supply or consume products
- **Products (Parts)** — commodities with sizes and values
- **Transport Resources** — vehicle types with capacity, cost, speed, and emissions
- **Routes** — directed arcs between locations traversable by specific transport types

The goal is to find an assignment of:
1. **Packing patterns** — how many units of each product to load per vehicle trip
2. **Transport frequencies** — how often each route is used
3. **Flow routing** — how products move through the network

...that satisfies all supply and demand constraints and minimises total transport cost (and optionally CO₂ emissions and capital tying costs).

### Why ASP?

ASP is well-suited for combinatorial optimisation: its declarative semantics allow constraints to be stated naturally, it handles disjunctive reasoning, and the Clingo solver provides a powerful CDNL-based search engine. The thesis asks whether ASP can be made *practical* for this class of problem — which requires overcoming the well-known challenge of **grounding blow-up** from aggregate constraints over large numeric domains.

### Research Trajectory

The work proceeded through several phases, each building on the limitations of the previous:

```
         ↓
1. Pure ASP encodings (Clingo, with #sum aggregates)
        ↓
2. Constraint ASP encodings (Clingcon, integer variables)
         ↓
3. Column Generation with SCIP master + pluggable pricers (incl. ASP)
         ↓
3.1. Hybrid ASP + external propagators  
```

---



---

## Key Components


### 1. Pure ASP Encodings — `ASP Pure Encodings/`

The first original ASP approach. The problem is encoded directly in Clingo using `#sum` aggregates for flow conservation, packing capacity, and the flow–packing linkage constraint. Several encoding variants exist:

| Encoding | Description |
|---|---|
| `encoding_route.lp` | Base encoding with discrete numeric domains |
| `optimised_encoding_route.lp` | Adds feasibility pruning, arc-direction guards, and symmetry breaking |
| `encoding_alternative.lp` | Clingcon variant using `&dom` / `&sum` constraint variables |
| `flingo_encoding.lp` | Variant for flingo (fuzzy ASP extension) |

**Key limitation:** The `#sum` aggregates — especially the flow–packing linkage which involves a product of two choice variables — cause **grounding explosion** (hundreds of thousands of ground rules) and very high search conflict rates, making this approach impractical for non-trivial instances.

---

### 6. Column Generation with SCIP + Pluggable Pricers — `Column generation using ASP/`

A column generation architecture using **SCIP** (via `PySCIPOpt`) as the master LP solver — giving access to exact LP dual values — and a modular, pluggable pricing interface. Three pricers are implemented:

| Pricer | Mechanism |
|---|---|
| `scip` | Exact integer knapsack solved by SCIP |
| `asp` | Knapsack solved by **Clingcon** (`&dom`, `&sum`, `&minimize`) |
| `greedy` | Density-sorted greedy heuristic |

The ASP pricer is notable: it demonstrates ASP being used not as the main solver but as a **specialised subproblem oracle** within a classical LP framework. Each route's subproblem is solved in parallel using `multiprocessing.Pool`.

Cost components (transport distance, CO₂ emissions, capital tying interest) are individually toggleable.

See [`Column generation using ASP/README.md`](Column generation using ASP/README.md) for full details.

---

### 7. Hybrid ASP + Propagators — `propagators/` ← Main Contribution

A **hybrid solver** that keeps the ASP structure (Clingo for search, ASP encoding for the combinatorial structure and objective) but replaces the three expensive `#sum` aggregate constraints with **external Python propagators** that hook directly into Clingo's search loop.

Three propagators are implemented:

| Propagator | Constraint Enforced | Technique |
|---|---|---|
| `FlowConservationPropagator` | Net flow = supply/demand at each node | Interval bounds on partial assignments |
| `PackageCapacityPropagator` | Packed volume ≤ vehicle capacity | Monotone prefix-sum detection |
| `LinkPackFlowLazyChecker` | Flow = Σ(pack qty × frequency) | Two-sided bound pruning (upper + lower) |

Each propagator operates at two levels:
- **`propagate()`** — called during search on partial assignments; prunes branches that provably cannot satisfy the constraint
- **`check()`** — called on complete candidate models; exact verification guaranteeing correctness

This eliminates the grounding explosion, reduces the search conflict rate, and produces shorter, more informative learned clauses.

See [`combined_encodings/propagators/README.md`](combined_encodings/propagators/README.md) for architecture and usage details, and [`PROPAGATOR_THEORY.md`](PROPAGATOR_THEORY.md) for the formal theory.

---

## Key Concepts

### Grounding Blow-up

ASP rules with variables are expanded by the *grounder* into a propositional program before solving. Rules involving `#sum` aggregates over large numeric domains produce enormous ground programs. For example, a linkage constraint involving the product of two choice variables (pack quantity × transport frequency) causes the grounder to enumerate all combinations, producing hundreds of thousands of ground rules even for small instances.

### External Propagators

Clingo's propagator API allows custom Python code to hook into the solver's search. The key insight is that domain-specific knowledge (e.g., interval arithmetic on flow conservation) can detect infeasibility *earlier* and *more precisely* than the generic weight-constraint propagation Clingo would apply to a `#sum` aggregate. This is the core technical contribution.

### Column Generation (Dantzig–Wolfe)

An LP decomposition technique that avoids enumerating all possible loading patterns upfront. A master LP is solved over a small initial set of patterns; a pricing subproblem (knapsack) finds new patterns with negative reduced cost (i.e., patterns that can improve the objective). The process repeats until no improving pattern exists. The dual variables of the master LP guide the pricing.

---

---

## Tools and Dependencies

| Tool | Purpose |
|---|---|
| [Clingo](https://potassco.org/clingo/) | ASP solver (core) |
| [Clingcon](https://potassco.org/labs/clingcon/) | Constraint ASP (integer linear arithmetic) |
| [SCIP / PySCIPOpt](https://www.scipopt.org/) | LP/MIP master problem solver |
| [uv](https://docs.astral.sh/uv/) | Python package manager (used throughout) |

Each sub-project has its own `pyproject.toml`. To set up any of them:
```bash
cd <sub-project-directory>
uv sync
```

