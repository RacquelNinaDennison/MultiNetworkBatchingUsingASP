# Hybrid ASP + Propagator Architecture: Full Theory

## 1. The Problem: Why Pure ASP Struggles

### 1.1 What Clingo Does Internally

Clingo solves ASP programs in two phases:

**Grounding:** Your first-order ASP rules (with variables) are expanded into a propositional (variable-free) program. The rule:

```
1{ flow(From,To,Part,N) : numFlow(N) }1 :- route(From,To,_,_,_), part(Part).
```

becomes one ground rule for *every* (route, part) pair. With 10 route/part combinations and `numFlow(0..20)`, this produces 10 choice rules, each with 21 atoms — that's 210 ground atoms just for `flow/4`.

**Solving:** The ground program is converted into a SAT-like problem and solved using CDNL (Conflict-Driven Nogood Learning), which is essentially the same algorithm as modern SAT solvers (CDCL) extended for weight constraints and optimization.

### 1.2 The Aggregate Problem

Your three `#sum` constraints are the bottleneck. Here's why each is expensive:

**Flow conservation:**
```asp
:- #sum{ N,To : flow(Loc,To,Part,N); -N,From : flow(From,Loc,Part,N) } != DS,
   netdemandSupply(Part,Loc,DS).
```

This creates one **weight constraint** per (Part, Loc) pair. Each weight constraint has positive terms (outgoing flow) and negative terms (incoming flow). The solver must track the running sum and propagate whenever a flow variable changes. Because the terms can be both positive and negative, the propagation is **non-monotone** — setting a variable to true can either increase or decrease the sum.

**Packing capacity:**
```asp
:- #sum{ N*Size,P : pack(N,P,TR,ID), partSize(P,Size) } > Cap,
   transportCapacity(TR,Cap), package_id(ID).
```

This is a **monotone** aggregate (all terms are non-negative, and the constraint is ≤). It's the cheapest of the three because the solver knows that adding more items can only increase the sum.

**Flow-packing linkage (the worst offender):**
```asp
:- flow(From,To,Part,T),
   T != #sum{ Q*Freq,TR,ID : transportLink(From,To,TR,Freq,ID), pack(Q,Part,TR,ID) }.
```

This is catastrophic because:
- The aggregate body contains a **product of two choice variables** (`Q × Freq`)
- It's an **equality** constraint (harder than inequality)
- The grounder must enumerate all `(Q, Freq)` pairs to create the weight constraint terms
- The solver must re-evaluate the sum whenever *any* pack or transport variable changes

### 1.3 What the Profiling Data Shows

From running `--stats=2` on the thesis instance (6 locations, 2 parts, 2 TRs):

| Metric | Value | Meaning |
|--------|------:|---------|
| `problem.lp.atoms` | 433,231 | Ground atoms after expansion |
| `problem.lp.rules` | 647,615 | Ground rules (mostly from aggregate expansion) |
| `problem.lp.sum_bodies` | 806 | Number of `#sum` aggregate body instances |
| `problem.generator.vars` | 18,182 | Solver variables after preprocessing |
| `problem.generator.constraints` | 4,712 | Internal solver constraints |
| `problem.generator.constraints_binary` | 48,610 | Binary clauses (from aggregate linearization) |
| `solving.solvers.choices` | 658,334 | Branching decisions during search |
| `solving.solvers.conflicts` | 496,899 | Dead ends (75.5% conflict rate) |
| `solving.solvers.extra.lemmas` | 496,898 | Learned clauses |
| `solving.solvers.extra.lits_learnt` | 63,189,575 | Total literals in learned clauses |

The story these numbers tell:

- **806 `#sum` bodies → 647k ground rules**: Each aggregate instance expands into hundreds of ground rules that enumerate all possible term combinations.
- **18k solver variables from 433k atoms**: Preprocessing eliminates most atoms, but 18k decision variables remain.
- **658k choices for 18k variables = 36 choices/variable**: The solver explores far more than it "should" need to. A well-structured problem needs 1–5 choices per variable.
- **75.5% conflict rate**: 3 out of every 4 decisions lead to a dead end. The solver constantly guesses a flow/pack/freq combination and then discovers it violates the linkage constraint.
- **127 literals per learned clause** (63M / 497k): Conflicts involve many interacting variables — the solver can't localize the problem, so it learns broad, expensive clauses.
- **Grounding: 0.3s, Solving: 41s**: The ground program is small enough (this is a tiny instance), but the search is extremely expensive due to the aggregate interaction.

---

## 2. The Solution: External Propagators

### 2.1 What is a Propagator?

A clingo propagator is a Python class that hooks into the solver's search loop. The solver calls your propagator at specific points during search:

- **`init(init)`**: Called after grounding. You read the ground program (symbolic atoms), map ASP atoms to solver literals, and register watches on literals you care about.

- **`propagate(control, changes)`**: Called during search whenever a watched literal's truth value changes. You can:
  - Detect early conflicts and add **nogoods** (clauses that prevent the current partial assignment)
  - This is where you gain speed — detecting infeasibility *before* the solver wastes time exploring

- **`check(control)`**: Called on **total assignments** (candidate models). You verify the exact constraint and reject invalid models.

### 2.2 Key Concepts

**Solver literals vs symbolic atoms:** Each ground ASP atom gets mapped to an internal solver literal (an integer). Positive means "this atom is true," negative means "this atom is false." You use `init.solver_literal(atom.literal)` to get the mapping.

**Watches:** When you call `init.add_watch(lit)`, you're telling the solver "call my `propagate()` whenever this literal becomes true." Watching `lit` AND `-lit` means you're notified whenever the truth value changes in either direction.

**Nogoods:** A nogood is a clause saying "this combination of literals cannot all be true simultaneously." When you call `control.add_nogood([lit1, lit2, lit3], lock=True)`, you're telling the solver: "if lit1 AND lit2 AND lit3 are all true, that's a conflict — backtrack." The `lock=True` means the nogood survives restarts.

**Soundness requirement:** Every nogood you add must be *valid* — it must only conflict on genuinely infeasible partial assignments. If you add an incorrect nogood, you'll prune valid solutions (over-pruning).

**Completeness requirement:** Your `check()` must reject every invalid model. If a model passes `check()` but violates the constraint, the solver will report an incorrect answer.

### 2.3 The Two-Level Architecture

Each propagator uses a two-level approach:

| Level | When called | What it does | Strength |
|-------|-------------|--------------|----------|
| `propagate()` | During search (partial assignments) | Bounds-based early conflict detection | Fast but approximate |
| `check()` | On total assignments (candidate models) | Exact constraint verification | Complete but late |

This gives you the best of both worlds:
- `propagate()` prunes obviously infeasible branches early, reducing the search space
- `check()` guarantees correctness on the final answer

---

## 3. The Three Propagators

### 3.1 Flow Conservation Propagator

**Constraint:** For each (Part, Location): `∑ outgoing_flow − ∑ incoming_flow = netdemandSupply`

**propagate() — Interval pruning:**

The key insight is that each unfixed arc can contribute between `MIN_FLOW` (0) and `MAX_FLOW` (20) to the sum. So we can compute a *reachable interval* [lo, hi] for the net sum:

```
lo = fixed_sum + 0 × unfixed_outgoing − 20 × unfixed_incoming
hi = fixed_sum + 20 × unfixed_outgoing − 0 × unfixed_incoming
```

If the target `DS` falls outside [lo, hi], we know no extension of the current partial assignment can satisfy conservation. We conflict immediately with the fixed arc choices as the reason.

**Why this works:** The interval is a sound over-approximation. Every reachable sum must lie within [lo, hi], so if DS ∉ [lo, hi], it's provably unreachable. We never reject a valid partial assignment.

**check() — Exact verification:** On total assignments, compute the exact net flow and reject if ≠ DS.

### 3.2 Packing Capacity Propagator

**Constraint:** For each (TR, ID): `∑ pack_qty × part_size ≤ capacity`

**propagate() — Monotone detection:**

This constraint is monotone: all terms are non-negative, and the bound is ≤. This means:
- If the sum of *already fixed* pack variables exceeds capacity, no future assignment can fix it
- We don't even need to consider unfixed variables — they can only make things worse

This is the simplest and cheapest propagation because we only need to track the fixed partial sum.

**check() — Exact verification:** Compute total and reject if > capacity.

### 3.3 Link-Pack-Flow Propagator

**Constraint:** For each (From, To, Part): `flow_amount = ∑ pack_qty × freq` over all (TR, ID)

**propagate() — Both-direction bound pruning:**

This is the most complex propagator because the constraint is an *equality* involving a *product* of choice variables. We compute both upper and lower bounds:

```
max_sum = ∑ q_max × f_max    (use actual value if fixed, MAX if unfixed)
min_sum = ∑ q_min × f_min    (use actual value if fixed, 0 if unfixed)
```

Two conflict conditions:
- `T > max_sum`: Even the most generous assignment can't transport enough → CONFLICT
- `T < min_sum`: The fixed variables already transport more than needed → CONFLICT

**Why upper-bound-only is insufficient:** The original version only checked `T > max_sum`. But consider: if `pack(5,p,tr,0)` and `transportLink(a,b,tr,4,0)` are both fixed, `min_sum ≥ 5×4 = 20`. If `flow(a,b,p,10)` is also fixed, then `T=10 < 20=min_sum`, and we can conflict immediately. Without the lower bound check, the solver would discover this later through `check()`, wasting search effort.

**check() — Exact equality:** Compute the exact sum and reject if ≠ T.

---

## 4. Correctness Arguments

### 4.1 Soundness (No false conflicts)

A propagator is **sound** if every nogood it adds is valid — i.e., the partial assignment it conflicts on genuinely cannot be extended to a valid solution.

- **Flow:** The interval [lo, hi] is provably a superset of all reachable net sums. If DS ∉ [lo, hi], no extension works. ✓
- **Capacity:** The partial sum of fixed variables is a lower bound on the total. If it exceeds capacity, the total must also exceed it (since all terms are non-negative). ✓
- **Linkage upper:** max_sum uses maximum possible values for unfixed variables. If T > max_sum, no assignment can reach T. ✓
- **Linkage lower:** min_sum uses 0 for unfixed variables (which is in the domain). If T < min_sum, even the minimum is too large. ✓

### 4.2 Completeness (No valid solutions lost)

A propagator is **complete** if `check()` rejects every invalid candidate model.

All three propagators follow the same pattern in `check()`:
1. Iterate over all ground instances of the constraint
2. Require all relevant variables to be fixed (return early if any is unfixed)
3. Compute the exact constraint value
4. Add a nogood if violated

Since `check()` is called on total assignments (all variables fixed), the early return never triggers. Every violation is caught. ✓

### 4.3 Interaction with Encoding Guards

The encoding uses `is_consumer`/`is_producer` guards to suppress some flow atoms:

```asp
1{ flow(From,To,Part,N) : numFlow(N) }1 :-
    route(From,To,_,_,_), part(Part),
    not is_consumer(Part, From),    % no flow FROM consumers
    not is_producer(Part, To).      % no flow TO producers
```

The propagators read `flow/4` atoms from `symbolic_atoms`, which only contains atoms that *exist* after grounding. Suppressed arcs simply don't appear, so:
- `out_arcs[(p, consumer_loc)]` is empty → no outgoing contribution
- `in_arcs[(p, producer_loc)]` is empty → no incoming contribution

This is correct: at a consumer location with demand = −15, the net sum is `0 − incoming = −incoming`, which must equal −15, so `incoming = 15`. The propagator handles this naturally.

---

## 5. Expected Performance Impact

### 5.1 What Changes

| Aspect | Pure ASP | Hybrid |
|--------|----------|--------|
| Ground program | 647k rules, 433k atoms | Rules for choice + minimize only |
| Sum aggregates | 806 grounded, creating 48k binary clauses | Zero — replaced by Python |
| Conflict detection | After full aggregate evaluation | Interval/bound check on partial assignment |
| Conflict specificity | Generic weight constraint propagation | Domain-specific: "this flow can't be covered" |

### 5.2 Where the Speedup Comes From

1. **Smaller ground program:** No aggregate expansion → fewer rules, fewer solver constraints
2. **Earlier conflict detection:** Bounds-based pruning catches infeasibility during search, before the solver commits to full assignments
3. **More specific conflicts:** The nogoods contain only the relevant variables, not the entire aggregate body. This means shorter learned clauses → better learning → fewer restarts
4. **No multiplicative grounding:** The `Q × Freq` product is computed in Python, not enumerated by the grounder

### 5.3 Trade-off

The propagator functions are called in Python, which is slower per-call than native C++ propagation. For very simple constraints, the overhead of crossing the Python/C++ boundary can outweigh the benefit. But for your linkage constraint (multiplicative aggregate with equality), the benefit is substantial because the native approach is so wasteful.

---

## 6. Running the Experiments

```bash
# 1. Verify correctness (soundness + completeness)
python3 analysis/test_and_bench.py --test \
    --instance orginal_asp_approach/instances.lp \
    --hybrid-encoding orginal_asp_approach/encoding.lp \
    --pure-encoding orginal_asp_approach/encoding_pure.lp

# 2. Benchmark comparison
python3 analysis/test_and_bench.py --benchmark \
    --instance orginal_asp_approach/instances.lp \
    --hybrid-encoding orginal_asp_approach/encoding.lp \
    --pure-encoding orginal_asp_approach/encoding_pure.lp

# 3. Profile both encodings
python3 analysis/profiler.py --compare \
    --instance orginal_asp_approach/instances.lp \
    --encoding orginal_asp_approach/encoding_pure.lp \
    --encoding2 orginal_asp_approach/encoding.lp \
    --label1 pure_asp --label2 hybrid

# 4. Ablation study (which propagator helps most)
python3 main.py instances.lp encoding.lp --verbose              # all propagators
python3 main.py instances.lp encoding.lp --verbose --no-link    # without linkage
python3 main.py instances.lp encoding.lp --verbose --no-flow    # without flow
python3 main.py instances.lp encoding.lp --verbose --no-pack    # without capacity
```
