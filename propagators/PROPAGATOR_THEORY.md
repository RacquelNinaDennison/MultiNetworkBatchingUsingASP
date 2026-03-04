# Propagator Theory: Hybrid ASP for Logistics Network Optimisation

This document provides a formal account of the propagator-based hybrid solving approach developed for the logistics network co-design problem. It covers the theoretical foundations of the Clingo propagator API, the design of each of the three propagators, correctness arguments (soundness and completeness), and the trade-offs between lazy and eager propagation modes.

---

## 1. Background: Answer Set Programming and Clingo

### 1.1 ASP and CDNL Solving

Answer Set Programming (ASP) is a declarative problem-solving paradigm in which a problem is encoded as a set of logical rules, and the solutions — called *answer sets* or *stable models* — are the models that satisfy those rules under the *stable model semantics*. Modern ASP solvers such as Clingo use a *Conflict-Driven Nogood Learning* (CDNL) algorithm, which is closely analogous to the CDCL (Conflict-Driven Clause Learning) algorithm underlying modern SAT solvers.

Solving proceeds in two phases:

**Grounding.** First-order rules with variables are expanded by a grounder (in Clingo, *gringo*) into an equivalent variable-free (propositional) program. Each ground rule corresponds to a specific instantiation of its variables. The resulting program is then passed to the solver.

**Solving (CDNL).** The ground program is processed into a set of *nogoods* — clause-like constraints stating that certain combinations of literals cannot all be true simultaneously. The solver then performs Boolean search: it assigns truth values to atoms (the *assignment*), propagates unit implications, and when a contradiction is detected (a *conflict*), it analyses the conflict to learn a new nogood, then backtracks.

### 1.2 The Aggregate Problem

ASP supports *aggregate expressions* such as `#sum`, `#count`, and `#max`. These are powerful but expensive. A `#sum` constraint:

```asp
:- #sum{ N,To : flow(Loc,To,Part,N); -N,From : flow(From,Loc,Part,N) } != DS,
   netdemandSupply(Part,Loc,DS).
```

is expanded by the grounder into a set of *weight constraint* rules — one per (Part, Loc) pair — where each weight constraint enumerates all possible contributing atoms and their weights. For numeric domains (flow values ranging 0–20, pack quantities 0–20, frequencies 0–20), this expansion is proportional to the product of the domain sizes and the number of atoms involved. The result is a ground program with many more rules than the number of logical constraints, and a solver that must reason about generic weight constraints rather than exploiting domain structure.

The flow–packing linkage constraint is particularly costly because it involves a *product* of two choice variables:

```asp
:- flow(From,To,Part,T),
   T != #sum{ Q*Freq,TR,ID : transportLink(From,To,TR,Freq,ID), pack(Q,Part,TR,ID) }.
```

The grounder must enumerate all `(Q, Freq)` pairs to form the weight constraint body, and the solver must re-evaluate the product sum whenever any `pack` or `transportLink` variable changes. On a small test instance (6 locations, 2 parts, 2 transport resources), this produces over 647,000 ground rules and a search with a 75.5% conflict rate.

---

## 2. The Clingo Propagator API

Clingo exposes an **external propagator interface** that allows custom Python (or C++) code to participate directly in the solver's search. A propagator is a class implementing the `clingo.Propagator` interface. The solver calls specific methods at defined points in the search.

### 2.1 Lifecycle Callbacks

**`init(init: PropagatorInit) → None`**

Called once after grounding, before solving begins. This is where the propagator sets up its internal data structures. The `init` object provides access to:

- `init.symbolic_atoms` — the set of all ground atoms in the program, queryable by predicate name and arity
- `init.solver_literal(atom_literal)` — maps a ground atom's literal to the solver's internal integer literal
- `init.add_watch(literal)` — registers a watch: the solver will call `propagate()` whenever this literal's truth value changes

The `init` phase is the propagator's opportunity to index the atoms it cares about and set up the mappings it will need during search.

**`propagate(control: PropagateControl, changes: list[int]) → None`**

Called during search, on **partial assignments**, whenever a watched literal's truth value changes. The `changes` list contains the literals that triggered this call. The `control` object provides:

- `control.assignment` — the current (partial) truth assignment; `assignment.value(lit)` returns `True`, `False`, or `None` (unassigned)
- `control.add_nogood(literals, lock=True)` — adds a conflict clause; returns `True` if the nogood was added without immediately triggering a conflict, `False` if the current assignment already conflicts
- `control.propagate()` — triggers unit propagation after adding a nogood

The propagator in `propagate()` can detect that the current partial assignment is **provably infeasible** — i.e., no total assignment extending it can satisfy the constraint — and add a nogood to force backtracking. This is the primary mechanism for early search space pruning.

**`check(control: PropagateControl) → None`**

Called on **complete assignments** — when the solver has found a candidate model (all variables assigned). The propagator must verify the constraint exactly and add a nogood if it is violated. Since `check()` sees a total assignment, it can compute exact constraint values rather than bounds.

### 2.2 Solver Literals and Atoms

Each ground atom in the ASP program is associated with an integer *literal* in the solver. Positive literals represent an atom being true; the negation (bitwise complement or `−lit`) represents it being false. During `init`, the propagator maps symbolic atoms to solver literals:

```python
for atom in init.symbolic_atoms.by_signature("flow", 4):
    lit = init.solver_literal(atom.literal)
    # store: lit -> atom metadata
```

A literal `lit > 0` is true in an assignment if `assignment.value(lit) is True`. Note that multiple atoms may share the same underlying solver literal (due to equivalence detection during preprocessing), so it is important to use `solver_literal` rather than `atom.literal` directly.

### 2.3 Nogoods

A nogood is a set of literals $\{l_1, l_2, \ldots, l_k\}$ asserting that this particular combination cannot all hold simultaneously. Formally, a nogood $C$ is *violated* by an assignment $A$ if every $l_i \in C$ is true under $A$. When the solver detects a violated nogood, it performs conflict analysis and backtracks.

Calling `control.add_nogood(reason, lock=True)` asserts the clause $\neg l_1 \vee \neg l_2 \vee \cdots \vee \neg l_k$. The `lock=True` flag means the nogood persists across restarts (otherwise it may be discarded). The nogood is added as a *reason* for a conflict: it records which literals jointly caused the infeasibility, enabling the solver's learning mechanism to generalise.

### 2.4 Soundness and Completeness (Formal Requirements)

A propagator is **sound** if every nogood it adds during `propagate()` is *valid* — that is, the nogood genuinely characterises an infeasible partial assignment, and no extension of that partial assignment can satisfy the constraint. Formally:

> For a partial assignment $A$ and a constraint $\varphi$: a nogood $C$ added by `propagate()` is sound if, for every total assignment $A' \supseteq A$ with $A' \models C$, we have $A' \not\models \varphi$.

If this condition fails — if the propagator adds a nogood that excludes a *valid* complete assignment — then the solver will miss correct solutions. This is the most serious correctness requirement.

A propagator is **complete** if `check()` rejects every invalid candidate model. Formally:

> For every total assignment $A$: if `check()` returns without adding a nogood, then $A \models \varphi$.

If completeness fails, the solver may report an incorrect answer (an assignment that does not satisfy the constraint).

Together, soundness of `propagate()` and completeness of `check()` guarantee that the hybrid solver finds exactly the same set of valid answer sets as the pure ASP encoding.

---

## 3. The Three Propagators

The three constraints in the logistics problem are replaced by three propagators. In each case, the ASP encoding retains the *choice rules* (which define the decision variables), but the `#sum` integrity constraints are commented out and replaced by the propagator.

### 3.1 Flow Conservation Propagator

#### The Constraint

For each product $p$ and location $l$, the net flow balance must match the supply/demand:

$$\sum_{(l, l') \in A} \text{flow}(l, l', p) - \sum_{(l'', l) \in A} \text{flow}(l'', l, p) = \text{netDemandSupply}(p, l) \quad \forall p, l$$

where $A$ is the set of active arcs (excluding consumer-origin and producer-destination arcs, enforced by the ASP encoding guards `is_consumer` / `is_producer`).

#### `init` Phase

The propagator indexes all `flow/4` atoms by arc and product:

- `arc_lits[(From, To, Part)]` — list of `(solver_literal, flow_value)` pairs for each possible flow value on this arc
- `out_arcs[(Part, Loc)]` — arcs *departing* from Loc for Part
- `in_arcs[(Part, Loc)]` — arcs *arriving at* Loc for Part
- `ds[(Part, Loc)]` — the required net supply/demand value

In eager mode, watches are added on all flow literals (both positive and negative) so `propagate()` is called whenever any flow assignment changes.

#### `propagate()` — Interval-Based Pruning

For a partial assignment, some arcs on a given (Part, Loc) will have a fixed flow value (exactly one of their literals is true), and others will be unfixed (no literal yet assigned true).

Define:
- `fixed_sum` = sum of fixed outgoing flows minus sum of fixed incoming flows
- `unfixed_out` = number of arc variables for outgoing arcs not yet assigned
- `unfixed_in` = number of arc variables for incoming arcs not yet assigned

Since each flow variable ranges over $[\text{MIN\_FLOW}, \text{MAX\_FLOW}] = [0, 20]$, the net sum achievable from any extension of the current assignment lies in the interval:

$$[lo,\, hi] = \bigl[\,\text{fixed\_sum} - 20 \cdot \text{unfixed\_in},\;\; \text{fixed\_sum} + 20 \cdot \text{unfixed\_out}\,\bigr]$$

If the required target $DS \notin [lo, hi]$, conservation is provably unreachable. The propagator adds a nogood on the set of fixed literals that produced this bound violation.

**Soundness argument.** Let $A$ be a partial assignment, and let $A' \supseteq A$ be any total extension. The contribution of unfixed outgoing arcs to the net sum is at most $20 \cdot \text{unfixed\_out}$ (at most one literal is true per arc, and the maximum value is 20). Similarly, unfixed incoming arcs contribute at least $-20 \cdot \text{unfixed\_in}$. Therefore, the net sum under $A'$ must lie in $[lo, hi]$. If $DS \notin [lo, hi]$, every extension violates conservation, so the nogood is valid.

#### `check()` — Exact Verification

On a total assignment, every arc has exactly one literal true. The propagator computes:

$$\text{total} = \sum_{\text{out arcs}} \text{chosen\_value} - \sum_{\text{in arcs}} \text{chosen\_value}$$

If $\text{total} \neq DS$, a nogood is added on the set of chosen literals. Since the assignment is total, the `_chosen` lookup never fails and the exact value is computed correctly.

**Completeness argument.** On a total assignment, `_chosen` returns a definite value for every arc. If $\text{total} \neq DS$, the nogood is added and the solver backtracks. No invalid model passes `check()` unchallenged.

#### Interaction with Encoding Guards

The ASP encoding suppresses `flow/4` atoms for consumer-origin arcs (no flow from a consuming location) and producer-destination arcs (no flow into a producing location) using:

```asp
is_consumer(P, L) :- demandOffer(P, L, D), D < 0.
is_producer(P, L) :- demandOffer(P, L, D), D > 0.

1{ flow(From, To, Part, N) : numFlow(N) } 1 :-
    route(From, To, _, _, _), part(Part),
    not is_consumer(Part, From),
    not is_producer(Part, To).
```

Because `init` reads `flow/4` atoms from `symbolic_atoms` (which only contains atoms that exist after grounding), suppressed arc variables simply do not appear in the propagator's index. The interval bounds are computed correctly over the arcs that do exist.

---

### 3.2 Packing Capacity Propagator

#### The Constraint

For each transport resource $TR$ and package ID $ID$, the total volume packed must not exceed the vehicle capacity:

$$\sum_{p} \text{pack}(q, p, TR, ID) \times \text{partSize}(p) \leq \text{transportCapacity}(TR) \quad \forall TR, ID$$

#### `init` Phase

The propagator indexes all `pack/4` atoms:

- `var_lits[(Part, TR, ID)]` — list of `(solver_literal, quantity)` pairs
- `pkg_vars[(TR, ID)]` — all (Part, TR, ID) variables for this transport resource and package
- `cap[TR]` — the capacity of transport resource TR
- `size[Part]` — the size of each part

#### `propagate()` — Monotone Prefix Detection

This constraint is *monotone*: all coefficients (`quantity × size`) are non-negative and the bound direction is `≤`. This has a crucial consequence: once the weighted sum of *fixed* pack variables exceeds the capacity, no future assignments to unfixed variables can reduce it below capacity.

Therefore, the propagator need only track the fixed partial sum:

$$\text{fixed\_sum} = \sum_{\text{fixed arcs}} \text{chosen\_quantity} \times \text{partSize}$$

If `fixed_sum > capacity`, a nogood is added on the set of fixed pack literals. No reasoning about unfixed variables is required.

**Soundness argument.** All terms $\text{quantity} \times \text{partSize}$ are non-negative. The total sum under any extension $A' \supseteq A$ satisfies $\text{total}(A') \geq \text{fixed\_sum}$. If $\text{fixed\_sum} > \text{capacity}$, then $\text{total}(A') > \text{capacity}$ for all extensions, so the nogood is valid.

#### `check()` — Exact Verification

On a total assignment, compute the exact sum $\sum_p \text{qty}_p \times \text{size}_p$ and add a nogood if it exceeds capacity.

---

### 3.3 Link–Pack–Flow Propagator

#### The Constraint

For each directed arc $(From, To)$ and product $Part$, the chosen flow value must equal the total capacity provided by all packing patterns dispatched on that arc:

$$\text{flow}(From, To, Part) = \sum_{TR,\; ID} \text{pack}(Q, Part, TR, ID) \times \text{transportLink}(From, To, TR, Freq, ID) \quad \forall From, To, Part$$

This is the hardest constraint to propagate because:
1. It is an **equality** (not a one-sided inequality), so violations can come from either direction
2. It involves a **product** of two choice variables ($Q \times Freq$), making bounds computation non-trivial
3. It couples three distinct decision layers: flow routing, packing, and transport frequency

#### `init` Phase

The propagator indexes:

- `pack_lits[(Part, TR, ID)]` — list of `(solver_literal, quantity)` pairs
- `link_lits[(From, To, TR, ID)]` — list of `(solver_literal, frequency)` pairs
- `flow_lits[(From, To, Part)]` — list of `(solver_literal, flow_value)` pairs
- `packs_by_part[Part]` — all (Part, TR, ID) keys for quick lookup

In eager mode, watches are added on all pack and transportLink literals (positive only, to fire when a value is chosen) and on flow literals (both positive and negative, since fixing a flow value immediately constrains the right-hand side).

#### `propagate()` — Two-Sided Bound Pruning

For a fixed flow value $T$ on arc $(From, To)$ for product $Part$, we compute upper and lower bounds on the achievable sum:

$$\text{max\_sum} = \sum_{(TR, ID)} q_{\max}(TR, ID) \times f_{\max}(TR, ID)$$
$$\text{min\_sum} = \sum_{(TR, ID)} q_{\min}(TR, ID) \times f_{\min}(TR, ID)$$

where:
- $q_{\max}$ is the chosen quantity if the pack variable is fixed, otherwise $\text{MAX\_QUANTITY} = 20$
- $q_{\min}$ is the chosen quantity if fixed, otherwise $0$
- $f_{\max}$, $f_{\min}$ are defined analogously for frequency

Two conflict conditions are checked:

1. **Upper bound violation:** $T > \text{max\_sum}$
   Even if all unfixed quantities and frequencies take their maximum values, the total throughput cannot reach $T$. The current assignment is infeasible.

2. **Lower bound violation:** $T < \text{min\_sum}$
   Even if all unfixed quantities and frequencies take their minimum values (0), the already-fixed contributions already exceed $T$. The constraint cannot be satisfied.

**Soundness of upper bound.** For any extension $A' \supseteq A$, each unfixed $(Q, Freq)$ pair satisfies $Q \leq 20$ and $Freq \leq 20$, so the product $Q \times Freq \leq 400$. The total sum satisfies $\text{sum}(A') \leq \text{max\_sum}$. If $T > \text{max\_sum}$, the equality cannot hold under any extension.

**Soundness of lower bound.** For any extension $A' \supseteq A$, each unfixed $(Q, Freq)$ pair satisfies $Q \geq 0$ and $Freq \geq 0$, so each unfixed product contributes at least 0 to the sum. The total sum satisfies $\text{sum}(A') \geq \text{min\_sum}$. If $T < \text{min\_sum}$, the equality cannot hold under any extension.

**Why both bounds are necessary.** A propagator implementing only the upper bound check would miss the following scenario: suppose `pack(5, p, tr, 0)` and `transportLink(a, b, tr, 4, 0)` are both fixed, contributing $5 \times 4 = 20$ to the sum. If `flow(a, b, p, 10)` is also fixed, we have $T = 10 < 20 = \text{min\_sum}$ — an immediate conflict that the upper bound check cannot detect (it would compute $\text{max\_sum} \geq 20 \geq 10$ and find no violation).

#### `check()` — Exact Equality Verification

On a total assignment, compute the exact sum:

$$\text{actual\_sum} = \sum_{TR, ID} Q_{(Part, TR, ID)} \times Freq_{(From, To, TR, ID)}$$

where $Q$ and $Freq$ are the chosen values. If $\text{actual\_sum} \neq T$, add a nogood on the set of chosen literals.

**Completeness argument.** On a total assignment, `_chosen` returns a definite (non-None) value for every pack, link, and flow literal. The exact sum is computed over all contributing (TR, ID) pairs. Any violation of the equality is caught and a nogood is added.

---

## 4. The Lazy/Eager Trade-off

Each propagator supports two operating modes, controlled by the `eager` flag:

| Mode | `propagate()` | `check()` | Best for |
|---|---|---|---|
| **Lazy** (`eager=False`) | No-op (returns immediately) | Active — exact verification | Small instances |
| **Eager** (`eager=True`) | Active — bounds-based pruning | Active — exact verification | Large instances |

### 4.1 Cost of Eager Mode

In eager mode, the solver calls `propagate()` every time a watched literal changes. Since propagators are implemented in Python and the solver is implemented in C++, every call crosses the Python/C++ language boundary. This has a fixed overhead per call that is independent of the complexity of the propagator's logic.

For very small instances, the solver may find a solution quickly anyway, and the overhead of many `propagate()` calls can outweigh the benefit of early pruning. In lazy mode, `propagate()` is a no-op, so there is zero overhead beyond the watch registration itself.

### 4.2 Benefit of Eager Mode

For larger instances, the solver makes hundreds of thousands of branching decisions before finding a solution or proving infeasibility. In this regime, the benefit of detecting infeasibility early — potentially pruning entire subtrees of the search space — significantly outweighs the per-call overhead. Each early conflict also generates a shorter, more specific learned clause (containing only the relevant arc/pack/flow literals), which improves the solver's subsequent learning and reduces restarts.

### 4.3 Watch Strategy

To minimise the number of `propagate()` calls in eager mode, the propagators use selective watch registration:

- **Flow conservation:** watches both positive (`+lit`) and negative (`-lit`) flow literals, since the net sum is affected by any change in flow assignment
- **Packing capacity:** watches only *positive* pack literals (`+lit`), because the constraint is monotone — a variable becoming false can never cause a violation, so there is no need to react to it
- **Link–pack–flow:** watches positive pack and frequency literals (reacting when a value is chosen) and both positive and negative flow literals (since a flow value being fixed immediately constrains the right-hand side)

This halves the call frequency for monotone constraints compared to watching both polarities.

---

## 5. Correctness Summary

The following table summarises the formal correctness properties of each propagator:

| Propagator | Soundness of `propagate()` | Completeness of `check()` |
|---|---|---|
| Flow conservation | Interval $[lo, hi]$ is a sound over-approximation of reachable net sums — proved by bounding contributions of unfixed arcs | Exact net sum computed over total assignment; every violation caught |
| Packing capacity | Fixed partial sum is a lower bound on total (non-negative terms) — if it exceeds capacity, all extensions do too | Exact total volume computed; every overflow caught |
| Link–pack–flow | `max_sum` over-approximates achievable throughput; `min_sum` under-approximates using zero for unfixed variables — both are provably tight bounds | Exact product sum computed; any equality violation caught |

**Joint correctness.** The three propagators are independent: each enforces a distinct constraint over a distinct set of atoms. Because the solver explores assignments consistent with all propagators simultaneously, the conjunction of soundness and completeness properties of all three together guarantees that the hybrid solver finds exactly the same optimal solutions as the pure ASP encoding — but with substantially fewer search steps.

---

## 6. Expected Effect on Solver Statistics

Replacing the `#sum` aggregates with propagators changes the solver's behaviour in the following ways:

**Grounding.** The ground program contains only the choice rules and the minimisation objective — no aggregate expansion. The number of ground rules and atoms is reduced significantly, and in particular the expensive enumeration of $(Q \times Freq)$ products disappears entirely from the ground program.

**Search conflict rate.** In pure ASP, the linkage constraint is only checked after the solver has committed to a full assignment of all flow, pack, and frequency variables for a given (arc, part) — potentially many hundreds of decisions later. With propagators, the interval/bound check fires as soon as the relevant literals are assigned. Conflicts are detected earlier and are more precisely characterised.

**Clause quality.** A nogood added by a propagator contains only the literals directly involved in the violated constraint — typically 3–10 literals. By contrast, a learned clause from a generic weight constraint conflict may involve the entire propagation chain, often 100+ literals. Shorter, more specific clauses are retained longer by the solver's clause database, lead to better unit propagation, and reduce restarts.

**Python overhead.** Each `propagate()` call has a fixed Python/C++ crossing cost. For large instances, this is amortised over the pruning benefit. For small instances, lazy mode (check-only) avoids this overhead entirely while still guaranteeing correctness.

---

## 7. Relation to Other Propagator Literature

External propagators in ASP solvers have been studied in the context of theory-based solving (e.g., SMT-style integration) and specialised constraint propagation. The Clingo propagator interface is documented in the context of *theory propagators* for linear arithmetic (as used in Clingcon), difference logic, and scheduling constraints.

The approach taken here is closest to the *lazy clause generation* style of hybrid solving (Ohrimenko et al., Feydy & Stuckey), where a constraint solver communicates explanations for infeasibility to a SAT/CDNL-based master solver. The key difference from Clingcon is that Clingcon encodes linear constraints generically, while these propagators exploit the specific structure of the logistics constraints (the interval arithmetic of flow conservation, the monotonicity of packing capacity, the equality-with-products structure of the linkage constraint) to produce tighter, domain-specific nogoods.

The use of a two-level `propagate()`/`check()` split follows standard practice: `propagate()` handles cheap approximate detection (avoiding exploration of provably infeasible branches), while `check()` handles exact verification (providing the completeness guarantee). This split decouples efficiency from correctness.
