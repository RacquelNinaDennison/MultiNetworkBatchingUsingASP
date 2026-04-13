# Packing Diversity Experiments — Interpretation Guide

## What This Experiment Does
claude --resume bb94c430-75fc-479f-9dbd-790c4e7f6669  

We solve the same multi-commodity batching problem (paper instance: 6 locations, 2 parts, 2 transport resources) under **five different objective configurations**, then measure how much the solutions differ using the **Jaccard index** and how "good" the packings are using **quality metrics**.

The goal: understand how the choice and ordering of optimisation objectives affects the structure of the logistics packings.

---

## The Five Variants

Each variant uses the same base flow model (flow conservation, capacity constraints, frequency choice) but differs in what is optimised and in what order.

| Variant | Priority Order | What it tests |
|---------|---------------|---------------|
| **E1\_baseline** | Transport cost only | Pure cost minimisation — the simplest objective |
| **E2\_cost\_co2** | Cost @2, CO2 @1 | Does adding emissions as a secondary objective change route selection? |
| **E3\_full** | Cost @3, CO2 @2, Holding @1 | The "standard" multi-objective — cost first, then emissions, then holding cost last |
| **E4\_hold\_first** | Holding @3, Cost @2, CO2 @1 | What happens when tied-up capital is the top priority? |
| **E5\_co2\_first** | CO2 @3, Cost @2, Holding @1 | What happens when emissions are the top priority? |

### How `@priority` works

In clingo/clingcon, `#minimize{ weight @N, ... }` uses **lexicographic optimisation**. Higher `@N` is optimised first. The solver finds the best possible value for `@3`, then within that fixed value, optimises `@2`, then `@1`.

This means the highest-priority objective completely dominates: the solver will never sacrifice even 1 unit of `@3` to improve `@2` or `@1` by any amount.

---

## Reading the Jaccard Results

### What the Jaccard Index Measures

The Jaccard index compares two sets:

```
J(A, B) = |A ∩ B| / |A ∪ B|
```

- **J = 1.0** — the two sets are identical (solutions agree completely)
- **J = 0.0** — the two sets share nothing (solutions are completely different)
- **J = 0.5** — half the elements are shared

We compute Jaccard at three levels of granularity, from coarse to fine:

### The Three Jaccard Levels

#### 1. `jaccard_routes` — Do they use the same physical routes?

Compares the set of active arcs `{(From, To, TR)}` between two solutions, ignoring which parts flow on them and how much.

**Example**: if E1 uses routes {l1→l2 via tr1, l2→l3 via tr1, l3→l5 via tr2} and E3 uses {l1→l2 via tr1, l2→l3 via tr1, l1→l3 via tr2}, they share 2 out of 4 distinct routes → J = 0.5.

**Interpretation**:
- High `jaccard_routes` (>0.8): the two objectives select similar network topology
- Low `jaccard_routes` (<0.5): the objectives fundamentally disagree on which routes to use

#### 2. `jaccard_flows` — Do they ship the same parts on the same routes?

Compares the set of `{(From, To, TR, Part)}` tuples where `load > 0`. This is finer than route structure because two solutions might use the same route but assign different parts to it.

**Interpretation**:
- High `jaccard_flows` (>0.8): the two solutions assign parts to routes similarly
- Low `jaccard_flows` (<0.5): the part-to-route assignments are substantially different — the objectives are steering the solver toward different packing compositions

#### 3. `jaccard_freq` — Do they use the same frequencies?

Compares `{(From, To, TR, Frequency)}` tuples. This is the most sensitive metric because even when two solutions agree on routes and parts, they may disagree on how often to ship.

**Interpretation**:
- High `jaccard_freq` (>0.5): the batch sizing is similar
- Near zero (typical): frequency is the most "free" variable, so it almost always differs between objective configurations

---

## Reading Your Results

### Quality Metrics Table

```
Variant          Routes TotFreq AvgPPR MinPPR MonoSKU AvgFill MinFill MaxShare
E1_baseline          10      47   1.80      1       2   0.972   0.833    0.785
E2_cost_co2          11      50   1.55      1       5   0.972   0.700    0.637
E3_full               8      48   1.62      1       3   0.986   0.889    0.670
E4_hold_first        11      42   1.00      1      11   0.984   0.889    1.000
E5_co2_first          8      51   1.62      1       3   0.980   0.895    0.595
```

#### Column definitions

| Column | Meaning | Good value |
|--------|---------|------------|
| **Routes** | Number of distinct (From,To,TR) arcs with any load > 0 | Depends on context |
| **TotFreq** | Sum of all frequencies across active routes | Lower = fewer shipments |
| **AvgPPR** | Average number of distinct parts per active route | Higher = more diverse packings |
| **MinPPR** | Minimum parts per route (worst case) | >1 means no mono-SKU routes |
| **MonoSKU** | Count of routes carrying only 1 part type | 0 is ideal |
| **AvgFill** | Average capacity utilisation across routes | >0.8 is industry target |
| **MinFill** | Worst-case capacity utilisation | >0.6 is acceptable |
| **MaxShare** | Average of the max single-part volume share per route | Lower = more balanced loads |

#### What the quality results tell us

**E4 (holding cost first) produces the worst packings:**
- `MonoSKU = 11` — every single route carries only one part type
- `AvgPPR = 1.00` — zero mixing
- `MaxShare = 1.000` — each route is 100% dominated by one part

This confirms the original problem: when holding cost (`D * V * Freq`) dominates, the solver isolates each part onto its own dedicated route to minimise value-at-risk per shipment. Logistically, this is terrible — it means dedicated trucks for each SKU.

**E1 (cost only) produces the most diverse packings:**
- `AvgPPR = 1.80` — routes carry nearly 2 parts on average
- `MonoSKU = 2` — only 2 routes are single-part
- But `MaxShare = 0.785` — the mixing is still unbalanced (one part dominates)

**E5 (CO2 first) produces the most balanced loads:**
- `MaxShare = 0.595` — the most even distribution of parts within routes
- This makes sense: CO2 optimisation favours fewer, fuller shipments on low-emission transport, which naturally consolidates multiple parts

### Jaccard Table — Key Pairs

```
E3_full vs E5_co2_first            1.0000   0.6250   0.1429
```
**E3 and E5 use identical routes** (J\_routes = 1.0) but differ in which parts go where (J\_flows = 0.625) and especially in frequency (J\_freq = 0.14). The route topology is stable between "cost-first" and "CO2-first", but the packing composition changes.

```
E1_baseline vs E4_hold_first       0.9091   0.5263   0.1053
```
**E1 and E4 use nearly the same routes** (J\_routes = 0.91) but the part assignments are very different (J\_flows = 0.53). Adding holding cost as the top priority doesn't change *which* routes are used — it changes *what goes on them* (mono-SKU vs mixed).

```
E2_cost_co2 vs E4_hold_first       0.6923   0.4000   0.1000
```
**E2 and E4 are the most different** — different routes (J = 0.69), very different part assignments (J = 0.40), almost no frequency overlap (J = 0.10). Adding CO2 and putting holding cost first produces fundamentally different logistics plans.

---

## General Patterns

1. **Route topology is the most stable** (`jaccard_routes` is highest across all pairs, typically 0.6–1.0). The physical network structure is largely determined by flow conservation and capacity — the objectives mainly influence *how* routes are used, not *which* routes exist.

2. **Frequency is the most volatile** (`jaccard_freq` is near zero for most pairs). Batch sizing is highly sensitive to the objective function — small changes in priority completely change how many trips are made on each route.

3. **Part-to-route assignments are moderately sensitive** (`jaccard_flows` ranges 0.4–0.6). This is the "packing composition" level — it tells you how much the objective influences which parts share a container.

4. **Priority ordering matters more than objective inclusion.** E3 and E5 contain the same three objectives but in different priority order, and they produce different solutions (J\_flows = 0.625). The `@priority` ordering is not just a tiebreaker — it fundamentally shapes the solution.

---

## How to Use These Results

### For your thesis/paper
- The Jaccard analysis provides quantitative evidence that objective priority ordering has a material effect on packing structure
- The quality metrics show that holding-cost-first optimisation produces operationally poor packings (mono-SKU), motivating the need for diversification constraints
- The contrast between E1 (naturally diverse) and E4 (mono-SKU) quantifies the cost of holding cost optimisation on packing quality

### For the next experiment
- Add **E6**: E3 + diversification constraints (minimum parts per route, fill rate floor)
- Compare E6's Jaccard against E3 to measure how much the diversification constraints change the solution
- Compare E6's quality metrics against E4 to show the improvement

### Running on larger instances
```bash
python evaluate.py \
    --instance ../data/benchmark_quality/medium_instance.lp \
    --time-limit 60 \
    -c cap_size_divide=10000
```

---

## File Reference

| File | Purpose |
|------|---------|
| `encodings/base_flow.lp` | Shared flow model (clingcon CSP) |
| `encodings/obj_baseline.lp` | E1: cost only |
| `encodings/obj_cost_co2.lp` | E2: cost @2 + CO2 @1 |
| `encodings/obj_full.lp` | E3: cost @3 + CO2 @2 + holding @1 |
| `encodings/obj_hold_first.lp` | E4: holding @3 + cost @2 + CO2 @1 |
| `encodings/obj_co2_first.lp` | E5: CO2 @3 + cost @2 + holding @1 |
| `evaluate.py` | Runner, parser, Jaccard computation, quality metrics |
| `results/*.csv` | Quality and Jaccard results per run |
| `results/*.json` | Full solution data for reproducibility |
