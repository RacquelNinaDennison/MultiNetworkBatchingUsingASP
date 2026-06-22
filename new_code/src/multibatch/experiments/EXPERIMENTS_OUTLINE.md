# Experimental Evaluation — Outline

Working outline of the three experiment suites, the research questions they
answer, and the reporting plan. Maps to the thesis evaluation chapter and the
ATMOS resubmission (Block 1 = encoding shootout, Block 2 = resilience).

---

## Research questions

- **RQ1 — Encoding optimisation.** How much do domain-specific encoding
  optimisations (feasibility pruning, symmetry breaking, tightened CSP
  domains) contribute to one-shot solver performance, and how does the
  grounding/solving trade-off differ between pure ASP and CASP?
- **RQ2 — Decomposition and paradigm.** Does decomposing the problem into a
  flow stage and a packing stage scale better than the monolithic one-shot
  encoding, and does the CASP backend (clingcon) benefit more from the
  decomposition than pure ASP?
- **RQ3 — Resilience (hero claim).** Can weighted soft constraints steer the
  two-stage CASP encoding toward plans that score measurably higher on
  post-hoc resilience metrics, and what is the dispatch-cost price of that
  resilience?
- **RQ4 — Portfolio robustness.** How sensitive are the one-shot solvers to
  clasp's search configuration and to parallelism, and is the encoding
  ranking (RQ1) stable across portfolio choices — i.e. is performance
  attributable to the encoding or to solver tuning?

A central methodological distinction, maintained throughout: the encoding
contains **resilience heuristics** (the Stage-1 `highExposure` penalty; the
Stage-2 `monoTrip` and `overloaded` penalties), while resilience itself is
measured by **post-hoc metrics** (R_TR, R_1, K_1, R_alpha) computed from the
solution via max-flow disruption simulation, independently of any solver or
encoding. RQ3 asks whether the heuristics improve the metrics — the two are
never conflated.

---

## Common setup (report once, in the chapter preamble)

- **Problem.** Multi-commodity network batching: route parts through a
  transport network (min-cost-flow structure) and pack them into discrete
  trips (bin packing). The combination is NP-hard, motivating CASP over a
  pure min-cost-flow algorithm.
- **Instances.** Synthetic layered networks by size class — paper (1
  instance), small / medium / large / xlarge (5 seeds each), industrylite
  (4 seeds) — plus an industrial test case. Per-instance properties
  (locations, parts, routes, density, capacity tightness) recorded in every
  results row. Report instance counts and per-class standard deviations
  (reviewer requirement).
- **Software.** clingo 5.8.0 / clingcon 5.2.1, Python 3.13; clingo
  configuration `many`.
- **Solve protocol.** Stage 1 and one-shot solves are single-shot with the
  full per-size time limit (an earlier multi-shot bound-tightening scheme
  was removed after it was shown to return suboptimal, unproven results in
  the transition region). Optimality status (`optimum` proven vs anytime
  best) is reported for every run.
- **Threads.** Solver-comparison suites (benchmark, scalability) run
  single-threaded for fairness; the resilience suite uses 4 threads.
- **Crash safety.** All harnesses append results per completed run and
  resume idempotently, so reported CSVs are append-complete records.

---

./src/multibatch/experiments/benchmark/run_all.sh small

## Experiment 1 — One-shot encoding benchmark (RQ1)

**Harness:** `experiments/benchmark/` → `benchmark_{raw,summary}_<size>.csv`

**Design.** 2x2: backend (naive ASP vs clingcon CASP) x optimisation level
(basic vs optimised), crossed with bin count (1–3) per route. 5 repetitions
per cell; per-size time limits (paper/small 60 s, medium 120 s).

**What it tests.**
1. The value of symmetry breaking and feasibility pruning within each
   backend (basic vs optimised).
2. The grounding-vs-solving trade-off: pure ASP grounds large programs as
   bins grow; CASP keeps the ground program compact by moving loads into
   CSP variables (`atoms`, `ground_time` vs `solve_time`).
3. The baseline difficulty of the monolithic encoding, motivating
   decomposition (feeds RQ2).

**Headline measures.** Proven-optimality rate, average total time, ground
program size (atoms), all per solver x size x bins.

**Status / expectation.** Pilot data (May) suggests `clingcon_optimised`
proves optimality several times more often than the other three variants
(e.g. 83% vs 17% on the paper instance); rerun required because the naive
encodings changed after that pilot.

**Reporting plan.** Table: optimality rate and mean time per solver x size.
Figure: atoms and ground time vs bin count (grounding blow-up). State per
cell: n runs, mean, std dev.

---

## Experiment 2 — Scalability: one-shot vs two-stage (RQ2)

**Harness:** `experiments/scalability/` → `scalability_{raw,summary}_<size>.csv`

**Design.** 2x2: encoding family (one-shot vs two-stage) x backend (naive
vs clingcon), all four on identical instances; 3 repetitions. Two-stage
runs with `weight = 0` and all Stage-2 penalties off, so all four solvers
minimise the same pure transport-cost objective (`cost` is apples-to-apples
across the grid; Stage-2's trip count is reported separately as `s2_cost`).
Time-limit semantics: one-shot gets one budget; two-stage gets the budget
per stage (combined wall clock up to 2x, reported as `wall_time`).
Initial scope: paper, small, medium; larger classes added after reviewing
the medium results.

**What it tests.**
1. Whether the flow/packing decomposition scales better than solving the
   joint problem monolithically (time-to-optimal, optimality rate by size).
2. Whether decomposition interacts with the paradigm — i.e. does CASP gain
   more from decomposition than pure ASP.
3. Where two-stage spends its effort (`s1_time` vs `s2_time`) and how
   ground-program size grows per family (`atoms`, `s1_atoms`, `s2_atoms`).

**Headline measures.** Wall time, proven-optimality rate, and
solution cost at timeout, per solver x size class.

**Status / expectation.** No usable data yet (a June pilot crashed before
the harness was made crash-safe). A smoke run is directionally consistent
with the hypothesis: on the paper instance, clingcon two-stage proved
optimality in ~5 s where clingcon one-shot timed out at 20 s.

**Reporting plan.** Scaling figure: mean wall time (log scale) vs size
class, one line per solver, with optimality-rate annotations. Table:
cost-at-timeout comparison for cells where optimality is out of reach.

---

## Experiment 3 — Resilience trade-off (RQ3, hero)

**Harness:** `experiments/twostage/` → `experiment_rel_<size>.csv`

**Design.** clingcon two-stage only. Two heuristic axes:

1. **Stage-1 exposure penalty (arc level).** Weak constraint charging
   `weight` per high-exposure flow (a flow carrying more than 1/exposure_n
   of a part's total supply; exposure_n = 3). Swept as a **relative weight**
   lambda in {0, 0.1, 0.25, 0.5, 1, 2, 4, 8}, where the absolute weight is
   lambda x (mean dispatch cost per trip of the instance's cost-optimal
   plan). lambda is therefore dimensionless — "average dispatches paid per
   exposure removed" — and comparable across instance scales and seeds.
   This normalisation is the principled answer to "how were soft-constraint
   weights chosen": the sweep brackets the economically meaningful range
   instead of guessing absolute magnitudes per instance.
2. **Stage-2 packing configuration (trip level).** 2x2 factorial:
   `baseline` (cost only), `mixed` (penalise mono-part trips), `even`
   (penalise value-concentrated trips), `full` (both).

Stage 1 is solved once per (instance, lambda); Stage 2 once per
configuration on that fixed flow.

**Measured outcomes (post-hoc, solver-independent).**
- **R_TR** — worst-case demand coverage after losing a single
  (arc, transport) — Stage-1-level resilience.
- **R_1** — worst-case coverage after losing a single trip — packing-level.
- **K_1** — kit-completeness analogue of R_1 (bottleneck part).
- **R_alpha** — coverage after losing an alpha fraction of capacity
  (alpha in {0.2, 0.4, 0.6, 0.8}; single-arc and global variants).
- **Cost side:** Stage-1 dispatch cost, Stage-2 dispatch cost, exposure
  count, mono/concentrated trip counts, solve times, optimality status.

**What it tests.**
1. *Does the Stage-1 heuristic buy arc-level resilience, and at what
   price?* The lambda sweep traces the cost-vs-exposure staircase; the
   **critical lambda** (where the plan switches to resilient routing) is a
   per-instance result, and its stability across size classes is itself a
   finding. Preliminary: paper transitions around lambda ≈ 0.5–1, small
   seeds around 2–4, i.e. the normalised resilience price appears to rise
   for smaller/tighter networks (to be confirmed across classes).
2. *Do the Stage-2 heuristics buy trip-level resilience?* Compare R_1, K_1,
   R_alpha across the four configurations at each lambda. Preliminary
   (paper + 2 small seeds): `mixed` dominates — highest R_1 at every
   weight, near-zero mono-part trips, retains most dispatch savings, and
   solves orders of magnitude faster than `even`/`full`, which time out and
   forfeit savings without metric gains.
3. *The price of resilience.* Dispatch-cost premium of the fully
   de-exposed plan vs the cost-optimal plan (observed range so far:
   +27% to +50% on small seeds; +5.7% on paper).

**Known caveats to state.**
- R_TR is not monotone in lambda: the exposure heuristic targets flow
  concentration, not worst-arc coverage, so intermediate weights can lower
  R_TR before eliminating exposures raises it.
- Co-optimal Stage-1 plans can differ in R_TR (tie-breaking instability);
  exposure count and R_TR are therefore reported side by side.
- K_1 coincides with R_1 on 2-part instances; divergence is only
  observable on part-richer classes.

**Reporting plan.** (a) Trade-off staircase: dispatch cost and exposure
count vs lambda, per size class (shared lambda axis is the point of the
normalisation). (b) Critical-lambda table per class (mean ± std over
seeds). (c) Stage-2 configuration table: R_1/K_1/R_alpha, mono count, cost
saving, solve time, optimality rate. (d) Resilience-premium summary.

---

## Experiment 4 — Portfolio robustness (RQ4)

**Harness:** `experiments/benchmark/run_portfolio.sh` →
`benchmark_{raw,summary}_portfolio_<size>.csv`

**Design.** Solver in {naive_optimised, clingcon, clingcon_optimised} x
clingo configuration in {default, frumpy, handy, trendy, many} x threads in
{1, 4}, bins fixed at 3, 3 repetitions, on the small and medium classes
(5 seeds each). Time limits as in Experiment 1. Multi-threaded runs are
nondeterministic, so per-cell variance is reported, not just means.

**What it tests.**
1. Sensitivity of each solver to the search-configuration preset — whether
   any encoding conclusion from RQ1 could be an artifact of one preset.
2. Parallel speedup (1 → 4 threads) per solver and whether it differs
   between pure ASP and CASP (theory propagation may parallelise
   differently than pure clause learning).
3. Justification of the defaults used elsewhere in the thesis
   (`many`, 4 threads for the resilience suite): chosen settings should be
   at or near the per-solver optimum, or the choice is revisited.

**Headline measures.** Proven-optimality rate and mean/std total time per
(solver, configuration, threads); cost-at-timeout where optimality is out
of reach. Key figure: encoding ranking (naive vs clingcon vs optimised)
plotted per configuration — a stable ranking across presets supports the
claim that the encoding, not tuning, drives the RQ1/RQ2 results.

**Status.** Harness implemented and smoke-tested; not yet run.

---

## Threats to validity (chapter section)

- Synthetic instance generator; one industrial case as external check.
- Single machine per suite, sequential runs (no timing contamination);
  hardware stated per suite.
- Anytime results at timeout are labelled as such; optimality rates
  reported everywhere (addresses "most solutions non-optimal" objection —
  limits were raised and the multi-shot early-exit removed).
- asp-fzn backend comparison deferred to future work (encoding
  compatibility would break identity with the main CASP encoding; the
  contribution is the resilience trade-off, not a solver shoot-out).
