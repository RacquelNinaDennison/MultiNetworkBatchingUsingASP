# Hybrid ASP + Propagator Solver for Logistics Co-Design

This project implements a **hybrid solver** for a logistics network co-design problem, combining Answer Set Programming (ASP) via [Clingo](https://potassco.org/clingo/) with custom external propagators written in Python. The core research question is: *can we make ASP-based logistics optimisation scale better by replacing expensive aggregate constraints with domain-aware propagators?*

---

## 1. The Problem

The logistics co-design problem involves simultaneously deciding:

- **How much** of each product flows along each route in the network (`flow`)
- **How many** units of each product to pack per transport vehicle (`pack`)
- **How frequently** each transport link operates (`transportLink` frequency)

These three decisions interact through three hard constraints:

| Constraint | Description |
|---|---|
| **Flow Conservation** | At every location, for every product: net outflow − net inflow = supply/demand |
| **Packing Capacity** | Total packed volume per transport vehicle ≤ vehicle capacity |
| **Flow–Packing Linkage** | Flow on a route must equal the sum of (packed quantity × transport frequency) |

The objective is to minimise total transport cost (frequency × distance × cost).

### Instance Structure

A problem instance specifies locations, transport resources, parts (products), demand/supply at each location, and available routes. An example instance (`data/instances_paper.lp`) has:

- 6 locations, 2 parts, 2 transport resources, 18 routes
- Supply at l1, l2; demand at l5, l6

---

## 2. Why Pure ASP Struggles

### 2.1 Grounding Explosion from Aggregates

Clingo solves ASP in two phases: **grounding** (expanding first-order rules into a propositional program) and **solving** (CDNL search on the ground program). The three constraints above are naturally expressed as `#sum` aggregates in ASP:

```asp
% Flow conservation
:- #sum{ N,To : flow(Loc,To,Part,N); -N,From : flow(From,Loc,Part,N) } != DS,
   netdemandSupply(Part,Loc,DS).

% Packing capacity
:- #sum{ N*Size,P : pack(N,P,TR,ID), partSize(P,Size) } > Cap,
   transportCapacity(TR,Cap), package_id(ID).

% Flow-packing linkage
:- flow(From,To,Part,T),
   T != #sum{ Q*Freq,TR,ID : transportLink(From,To,TR,Freq,ID), pack(Q,Part,TR,ID) }.
```

Each aggregate instance gets expanded by the grounder into many weight constraint rules. For the small thesis instance, this produces **647,615 ground rules** from just **806 aggregate instances**. The linkage constraint is particularly bad because it involves a **product of two choice variables** (`Q × Freq`), which the grounder must enumerate exhaustively.

### 2.2 Expensive Search

Even after preprocessing collapses the ground program to ~18,000 solver variables, search is very expensive:

| Metric | Value | Interpretation |
|---|---|---|
| Choices | 658,334 | Branching decisions made |
| Conflicts | 496,899 | Dead ends hit (75.5% conflict rate) |
| Learned clauses | 496,898 | Each conflict produces one |
| Literals per clause | ~127 avg | Broad, expensive clauses |
| Solve time | ~41s | For a 6-location, 2-part instance |

The 75.5% conflict rate means 3 out of every 4 decisions immediately lead to a dead end. The solver constantly guesses a flow/pack/frequency combination and then discovers the linkage constraint is violated — only after committing to a full partial assignment.

---

## 3. The Hybrid Approach: External Propagators

### 3.1 What is a Clingo Propagator?

A **propagator** is a Python class that hooks directly into Clingo's search loop. The solver calls it at two points:

- **`propagate(control, changes)`** — called during search whenever a watched literal changes truth value. Here you can detect *partial-assignment infeasibility* and add nogoods (conflict clauses) to prune the search space early.
- **`check(control)`** — called when the solver has found a candidate total assignment (all variables fixed). Here you verify the constraint exactly and reject invalid models.

The propagator architecture replaces the three `#sum` aggregate constraints entirely. The ASP encoding retains only the choice rules and the minimisation objective; the three constraints are enforced externally in Python.

### 3.2 Key Concepts

**Solver literals.** Each ground ASP atom is mapped to an internal integer literal. The propagator uses `init.solver_literal(atom.literal)` to obtain this mapping during `init()`.

**Watches.** Calling `init.add_watch(lit)` tells the solver to invoke `propagate()` whenever `lit` changes. Watching only the relevant atoms avoids unnecessary Python call overhead.

**Nogoods.** A nogood is a clause `¬(lit₁ ∧ lit₂ ∧ … ∧ litₙ)` — it asserts that the listed literals cannot all be true simultaneously. Adding a nogood causes the solver to backtrack immediately. The `lock=True` flag ensures the nogood persists across restarts.

**Soundness and Completeness.**
- *Soundness*: every nogood added during `propagate()` must be valid — the partial assignment it conflicts on must genuinely be infeasible. Over-pruning (rejecting valid assignments) would lose solutions.
- *Completeness*: `check()` must reject every invalid candidate model. Under-pruning would allow incorrect answers.

### 3.3 Two-Level Architecture

Each propagator uses a two-level strategy:

| Level | When | What | Guarantee |
|---|---|---|---|
| `propagate()` | During search (partial assignment) | Bounds-based early conflict detection | Sound but approximate |
| `check()` | At candidate models (total assignment) | Exact constraint verification | Complete |

This gives the best of both worlds: early pruning reduces wasted search, and `check()` ensures correctness.

---

## 4. The Three Propagators

### 4.1 Flow Conservation Propagator (`flow_conservation.py`)

**Constraint:** For each (Part, Location):

$$\sum_{\text{out arcs}} \text{flow} - \sum_{\text{in arcs}} \text{flow} = \text{netDemandSupply}$$

**`propagate()` — Interval pruning.**

Each unfixed arc can contribute between `MIN_FLOW = 0` and `MAX_FLOW = 20` to the net sum. Given the currently fixed arcs, we compute a reachable interval:

$$[\,lo,\, hi\,] = \bigl[\,\text{fixed\_sum} - 20 \cdot |\text{unfixed\_in}|,\;\; \text{fixed\_sum} + 20 \cdot |\text{unfixed\_out}|\,\bigr]$$

If the target `DS ∉ [lo, hi]`, conservation is provably unreachable from this partial assignment → add a nogood on the fixed arc choices and backtrack.

**Soundness argument.** The interval `[lo, hi]` is a sound over-approximation: every achievable net sum must lie within it. If `DS` falls outside, no extension of the current partial assignment can satisfy conservation.

**`check()` — Exact verification.** Compute the exact net sum over all arcs and reject if ≠ DS.

**Interaction with encoding guards.** The encoding suppresses `flow/4` atoms for consumer-origin and producer-destination arcs using `is_consumer` / `is_producer` guards. The propagator reads only atoms that exist after grounding, so suppressed arcs simply don't appear in the arc index — handled correctly by design.

---

### 4.2 Packing Capacity Propagator (`packing_conservation.py`)

**Constraint:** For each (TransportResource TR, Package ID):

$$\sum_{p} \text{pack}(q, p, TR, ID) \times \text{partSize}(p) \leq \text{transportCapacity}(TR)$$

**`propagate()` — Monotone detection.**

This constraint is **monotone**: all terms are non-negative and the bound is `≤`. This means fixing more pack variables can only increase the sum, never decrease it. Therefore:

- If the sum of *already fixed* pack variables exceeds capacity, the constraint is violated — no future assignment can fix it.
- We don't need to consider unfixed variables at all.

This is the cheapest propagation of the three.

**Soundness argument.** The fixed partial sum is a lower bound on the total (all terms non-negative). If it already exceeds capacity, the total must too.

**`check()` — Exact verification.** Compute total weighted volume and reject if > capacity.

---

### 4.3 Link–Pack–Flow Propagator (`links_conservation.py`)

**Constraint:** For each (From, To, Part):

$$\text{flow}(From, To, Part) = \sum_{TR,\, ID} \text{pack}(Q, Part, TR, ID) \times \text{transportLink}(From, To, TR, Freq, ID)$$

This is the hardest constraint because:
- It is an **equality** (not just `≤`)
- It involves a **product of two choice variables** (`Q × Freq`)
- It connects three distinct decision layers (flow, packing, transport frequency)

**`propagate()` — Both-direction bound pruning.**

For each fixed flow value `T`, we compute bounds on the achievable sum using the maximum and minimum possible values of unfixed pack quantities and frequencies:

$$\text{max\_sum} = \sum_{TR,ID} q_{\max} \times f_{\max}$$
$$\text{min\_sum} = \sum_{TR,ID} q_{\min} \times f_{\min}$$

where fixed variables use their actual values and unfixed variables use `MAX = 20` (upper) or `0` (lower).

Two conflict conditions:
- `T > max_sum`: Even the most generous assignment can't transport enough → conflict
- `T < min_sum`: Already-fixed variables transport more than needed → conflict

**Why both directions matter.** The upper bound (`T > max_sum`) was the original check. The lower bound (`T < min_sum`) is equally important: if `pack(5, p, tr, 0)` and `transportLink(a,b,tr,4,0)` are both fixed, the contribution is already `5×4 = 20`. If `flow(a,b,p,10)` is fixed, we have `10 < 20` and can conflict immediately rather than waiting for `check()`.

**Soundness argument.**
- Upper: `max_sum` uses maximum possible values for unfixed variables. If `T > max_sum`, no assignment reaches `T`.
- Lower: `min_sum` uses 0 for unfixed variables (which is in domain). If `T < min_sum`, even the minimum is already too large.

**`check()` — Exact equality.** Compute the exact sum `∑ Q × Freq` and reject if ≠ T.

---

## 5. Expected Performance Benefits

| Aspect | Pure ASP | Hybrid |
|---|---|---|
| Ground program size | 647k rules, 433k atoms | Smaller — no aggregate expansion |
| Sum aggregates | 806 grounded → 48k binary clauses | Zero — replaced by Python |
| Conflict detection | After full aggregate evaluation | Bounds-based on partial assignment |
| Conflict locality | Generic weight constraint nogoods | Domain-specific: exact relevant variables |

The speedup comes from four sources:
1. **Smaller ground program** — no `#sum` expansion means fewer rules and solver constraints
2. **Earlier conflict detection** — bounds pruning catches infeasibility during search, not at candidate models
3. **More specific conflicts** — nogoods contain only the directly relevant literals (shorter clauses → better learning)
4. **No multiplicative grounding** — the `Q × Freq` product is computed in Python, not enumerated by the grounder

**Trade-off.** Python propagators carry a per-call overhead from crossing the Python/C++ boundary. For very simple constraints the overhead can outweigh the benefit. This is why the solver supports two modes:
- `--eager` (default off): only `check()` is active — no Python overhead during search, correctness guaranteed at candidate models. Best for small instances.
- `--eager` (on): `propagate()` is also active — early pruning at the cost of more Python calls. Better for larger instances.

---

## 6. Project Structure

```
propagators/
├── main.py                          # Entry point: argument parsing, propagator registration, solve loop
├── asp_encodings/
│   └── encoding.lp                  # Hybrid ASP encoding (choice rules + minimise, no aggregates)
├── orginal_asp_approach/
│   ├── encoding.lp                  # Original pure ASP encoding (with #sum constraints)
│   └── instances.lp                 # Small test instance
├── data/
│   └── instances_paper.lp           # Paper benchmark instance (6 locations, 2 parts, 2 TRs)
├── src/
│   └── modules/
│       ├── flow_conservation.py     # FlowConservationPropagator
│       ├── packing_conservation.py  # PackageCapacityPropagator
│       └── links_conservation.py   # LinkPackFlowLazyChecker
└── analysis/
    ├── profiler.py                  # Timing and statistics comparison
    └── verfication.py               # Correctness verification against pure ASP
```

---

## 7. Running the Solver

### Requirements

```bash
pip install clingo
# or with uv:
uv sync
```

### Basic usage

```bash
# Solve with all propagators (lazy / check-only mode)
python main.py data/instances_paper.lp asp_encodings/encoding.lp --verbose

# Eager mode (propagate + check) — better for larger instances
python main.py data/instances_paper.lp asp_encodings/encoding.lp --verbose --eager

# Ablation: disable individual propagators to measure contribution
python main.py data/instances_paper.lp asp_encodings/encoding.lp --verbose --no-link
python main.py data/instances_paper.lp asp_encodings/encoding.lp --verbose --no-flow
python main.py data/instances_paper.lp asp_encodings/encoding.lp --verbose --no-pack

# Export JSON run record for analysis
python main.py data/instances_paper.lp asp_encodings/encoding.lp --out results.json
```

### CLI flags

| Flag | Description |
|---|---|
| `--eager` | Enable `propagate()` in addition to `check()` |
| `--no-flow` | Disable flow conservation propagator |
| `--no-pack` | Disable packing capacity propagator |
| `--no-link` | Disable link–pack–flow propagator |
| `--threads N` | Number of solver threads |
| `--models N` | Maximum models (0 = all, needed for optimisation) |
| `--verbose` | Print solver statistics |
| `--out path` | Write JSON run record |

---

## 8. Relationship to the Column Generation Approach

This propagator-based solver is one of two approaches developed in this thesis. The other (in `Logistics-Network-Optimization-including-asp-pricer/`) uses **Column Generation** with SCIP as the master problem solver and a pluggable pricing oracle — including an ASP-based knapsack pricer via Clingcon.

The two approaches represent different decomposition strategies for the same underlying problem:

| | Propagators (this repo) | Column Generation |
|---|---|---|
| **Framework** | ASP (Clingo) + Python propagators | LP/MIP (SCIP) + subproblem pricers |
| **Decomposition** | Propagators replace `#sum` constraints | Dantzig–Wolfe: master LP + pricing subproblem |
| **Role of ASP** | Primary solver | Pricing oracle (subproblem) |
| **Optimality** | Exact (via Clingo CDNL optimisation) | LP relaxation → integer recovery |
