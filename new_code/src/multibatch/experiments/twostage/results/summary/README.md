# Summary Tables — How to Run & Interpret

Aggregation pipeline for two-stage resilience experiments. Reads raw
per-run CSVs from `results/` and produces per-class summary tables with
mean, standard deviation, and bootstrap 95% confidence interval.

---

## How to run

```
cd new_code
uv run python -m multibatch.experiments.twostage.make_summary_tables
```

What happens:
- Discovers every `experiment__*.csv` in `results/`.
- For each, groups rows by `(instance_size, weight, s2_config)`.
- For each metric (R_TR, R_1, K_1, R_alpha variants, nominal_cost,
  s1/s2_dispatch_cost, s1/s2_time) computes mean, std, bootstrap CI,
  and n (sample count).
- Writes one `summary__<source-name>.csv` per source into this
  directory.

Idempotent: rerun any time after new data lands; overwrites prior
summaries.

To regenerate the human-readable markdown reports (CSV1_REPORT.md,
R_ALPHA_REPORT.md): currently built ad-hoc via one-off scripts.
Promote to a runner if reporting becomes routine.

---

## Output columns

For each metric `m`:

| Column | Meaning |
|---|---|
| `m_mean` | Average value across seeds for this group |
| `m_std` | Sample standard deviation (ddof=1) |
| `m_ci_lo` | Bootstrap 95% CI lower bound |
| `m_ci_hi` | Bootstrap 95% CI upper bound |
| `m_n` | Number of seeds contributing to this group |

`m_ci_lo` and `m_ci_hi` are `NaN` when n < 2 (e.g. paper class, n=1).

---

## How to interpret

### Standard deviation

`std` = spread of values across seeds within one (class, weight,
s2_config) cell. Small std → seeds agree, the system behaves
consistently on this class. Large std → the metric is seed-sensitive,
which usually means the instances vary more than the class label
suggests, or the solver finds substantially different solutions on
different seeds.

Rule of thumb for our setting (n=5 seeds, resilience metrics on [0, 1]):
- std < 0.02 → very tight, claim is robust within this class.
- std 0.02–0.06 → typical, still informative.
- std > 0.10 → noisy, treat means with care.

### Bootstrap 95% confidence interval

What it is: an interval that has a 95% chance of containing the *true*
mean value the system would produce if you ran infinitely many seeds.
Built by resampling the 5 observed seed values with replacement 10 000
times, recomputing the mean each time, and taking the 2.5th and 97.5th
percentiles of those simulated means.

Why bootstrap rather than the textbook `mean ± 1.96·std/√n`:
- Resilience metrics are bounded on [0, 1] and skewed near the edges.
  Bootstrap reflects that shape; the textbook formula doesn't.
- n=5 is too small for the normality assumption to hold.
- Distribution-free: still correct if data is bimodal, capped, or odd.

### CI overlap — what it actually means

When you compare two configurations on the same metric, you have two
intervals. There are three cases:

**Disjoint CIs.** Example:
- baseline R_TR: [0.51, 0.61]
- mixed    R_TR: [0.67, 0.69]

These don't overlap. Strong evidence the two configurations have
different true means. You can write: "mixed improves R_TR over
baseline on this class."

**Partial overlap.** Example:
- baseline R_TR: [0.34, 0.54]
- mixed    R_TR: [0.45, 0.67]

Overlap region: [0.45, 0.54]. This means: both configurations could
plausibly have a true mean somewhere in that shared range. We cannot
rule out that the two configurations actually have the same true mean
and the observed difference is just seed noise.

Important: overlap ≠ proof of no difference. It only means the current
evidence is insufficient. With more seeds the intervals would tighten;
a real effect would eventually separate them.

**Heavy overlap.** Example:
- baseline R_1: [0.76, 0.84]
- mixed    R_1: [0.78, 0.87]

The overlap covers almost the entire range of both intervals. Treat as
"indistinguishable in current data." Don't claim improvement; just
report the numbers and say so.

A useful informal threshold: if config A's mean falls outside config B's
CI (and vice versa), the configs are "probably different." If both means
fall inside each other's CIs, they're "probably the same."

---

## What to report in the paper

For each metric of interest:

1. **Per-class table.** Rows = (weight, s2_config) combos; columns =
   `mean ± std [CI_lo, CI_hi]`. One table per class, or one per metric
   with class as a column.

2. **Claim language matched to evidence.**
   - Disjoint CIs → "improves" / "outperforms".
   - Overlapping CIs → "tends to" / "shows a slight increase" /
     "differences within the confidence band".
   - Heavy overlap → "no significant difference observed".

3. **n=5 caveat.** State up front: results are preliminary, n=5 seeds
   per class, bootstrap CIs at 95%. Differences within the CI band are
   descriptive only.

4. **Don't run t-tests or report p-values.** Underpowered with n=5;
   misleading. Bootstrap CIs already carry the uncertainty story.

---

## Metric reference

| Column | What it measures | Stage |
|---|---|---|
| `r_tr` | Worst-case coverage when one (origin, dest, transport) arc is fully removed | 1 |
| `r_1` | Worst-case coverage when one specific trip is lost | 2 |
| `k_1` | Kit-completion ratio under single-trip loss | 2 |
| `r_heaviest_single_α` | Coverage when fraction (1-α) of trips on one arc lost | 2 |
| `r_heaviest_global_α` | Coverage when fraction (1-α) of trips on every arc lost simultaneously | 2 |
| `nominal_cost` | **Stage 1 objective value** = transport cost + (weight × #highExposure violations). See note below. | 1 |
| `s1_dispatch_cost` | Stage 1 transport cost (no penalty), recomputed from route frequencies × route_cost | 1 |
| `s2_dispatch_cost` | Stage 2 actual transport cost from chosen trips × route_cost | 2 |
| `cost_saving` | `s1_dispatch_cost − s2_dispatch_cost` | derived |
| `s1_time`, `s2_time` | Wall-clock seconds for each stage | — |

### Note on `nominal_cost` — resolve this

`nominal_cost` is the augmented stage 1 objective: at `w0=0` it equals
`s1_dispatch_cost`; at `w0>0` it equals `s1_dispatch_cost + (w0 × #highExposure_violations)`.
On a w=1M run this can be ~800× the transport cost.

**Decision needed before paper-ready tables:**
- **Option A — keep it.** Frame it as "operational cost including
  resilience penalty" and explain that the penalty represents the
  business cost of concentrated flow. Caption must say
  `nominal_cost = transport + w0 × #violations`.
- **Option B — switch to `s2_dispatch_cost`.** This is the actual
  cost of dispatch you pay after stage 2 packing decisions. Cleanest
  for a cost-vs-resilience trade-off plot.
- **Option C — report both.** `s1_dispatch_cost` / `s2_dispatch_cost`
  for the real-money view, `nominal_cost` for the optimizer-view.

Current state: tables use whatever column you pick. The summary CSVs
contain all three.

---

## Pareto-front plan (when current weight sweep completes)

The active sweep adds intermediate `w0` values across all classes.
Once landed, build per-class Pareto plots:

1. **Axes.** x = dispatch cost (pick from `s2_dispatch_cost` or
   `nominal_cost` per the decision above). y = resilience metric
   (start with `r_tr`; add panels for `r_1` and global R_alpha).

2. **Points.** One point per `(w0, s2_config)` combination. Plot the
   mean. Error bars or shaded band = bootstrap CI.

3. **Lines.** Connect points belonging to the same `s2_config` across
   `w0` values, in `w0` order. This traces how that configuration's
   cost/resilience trade-off evolves as the stage 1 weight increases.

4. **Frontier check.** A configuration is Pareto-dominant at a given
   weight if no other configuration achieves both lower cost AND
   higher resilience at any weight. Mark dominated points dimly.

5. **Per-class panels.** Pareto shape differs by class (small vs
   industrylite have different baselines). Don't aggregate across
   classes.

6. **Two-panel layout suggestion.** Left panel: R_TR (stage 1
   metric, varies with w0). Right panel: R_alpha global α=0.6
   (stage 2 metric, varies most with s2_config). Together they show
   the orthogonal-mechanism story (stage 1 softs help arc resilience,
   stage 2 softs help systemic resilience).

7. **Reading the plot.** The "knee" of the curve is the
   recommendation: smallest `w0` that captures most of the
   resilience gain. Beyond the knee, additional weight buys little
   resilience but costs more.

When ready, implement as a new function in `analysis.py` reading the
summary CSVs, or a notebook section in `results_analysis.ipynb`.
