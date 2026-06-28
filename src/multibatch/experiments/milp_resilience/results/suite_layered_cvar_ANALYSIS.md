# Generalisation + widened-global-tail analysis — layered small+medium (10 instances)

Run: MILP/MOP flow (70% envelope) + packing sweep {baseline, hetero_w8, conc_w8,
full_w8_8}, 30s each, over 10 instances (small/medium × 5 seeds). All flows solved to
**proven optimality** in <1s (vs industry's 600s timeout). New: global CVaR_α widened
to a **30% tail** (single stays 10%).
Source: `suite_layered_cvar.csv`, `suite_layered_cvar.log`. Reminder: α = survival
fraction (α=0.2 ⇒ 80% lost).

## Headline: the two resilience axes diverge, and the industry α-finding REVERSES

Across-suite win-rate vs baseline (wins / 10, meanΔ):

| metric | conc_w8 | full_w8_8 | hetero_w8 |
|---|---|---|---|
| **Single-trip loss** | | | |
| nri | **9/10 (+0.0084)** | 8/10 (+0.0054) | 3/10 (+0.0007) |
| cov_cvar10 | **8/10 (+0.0191)** | 6/10 (+0.0155) | 8/10 (+0.0185) |
| **Partial (α) loss** | | | |
| nri_alpha_single_0.4 (mean) | 1/10 (**−0.0112**) | 2/10 (−0.0045) | 4/10 (−0.0006) |
| cvar_alpha_single_0.4 (tail) | 2/10 (**−0.0505**) | 1/10 (−0.0311) | 3/10 (−0.0067) |
| nri_alpha_single_0.6 (mean) | 2/10 (−0.0091) | 2/10 (−0.0048) | 2/10 (−0.0012) |
| cvar_alpha_single_0.6 (tail) | 1/10 (**−0.0472**) | 1/10 (−0.0361) | 0/10 (−0.0111) |

**1. Single-trip resilience generalises (soft constraints help).** `conc_w8` improves
NRI on 9/10 and the single-trip tail on 8/10. This is the design target and it holds
robustly across instances and seeds.

**2. Partial-loss resilience REVERSES (soft constraints hurt).** On the α metrics the
soft constraints *lose* to baseline on 8–9 of 10 instances, with **negative** mean
deltas. On the industry instance `conc_w8` *improved* the α=0.4 tail (+0.0117); here it
*degrades* it (−0.0505). The industry severity-crossover does **not** generalise — it
flips sign on the smaller instances.

Within-instance detail (`layered_medium_seed1`, cvar_alpha[single]):

| config | α0.2 | α0.4 | α0.6 | α0.8 |
|---|---|---|---|---|
| baseline | 0.467 | **0.600** | **0.733** | **0.867** |
| conc_w8 | **0.511** | 0.578 | 0.689 | 0.800 |

conc helps only at the most extreme α=0.2 (high-variance payoff) and hurts everywhere
milder — the opposite ordering to industry.

## Why: the α metric is strategy-biased against concentration

`R_α`/`NRI_α`/`CVaR_α` use `strategy="heaviest"` — the most-loaded trips are removed
first. Concentration piles a part onto a few heavy trips, which are then exactly the
ones destroyed, so anti-concentration (even spread) loses its (1−α) share of *every*
part simultaneously. The single-trip metric enumerates every trip equally and has **no
such strategy dependence**. So the partial-loss verdict is an artefact-risk: it should
be re-checked with `strategy="first"`/`"random"` before being trusted. The single-trip
result needs no such caveat.

## The widened global tail: rescued from zeros, but still degenerate

Widening global to a 30% tail removed the all-zero saturation seen on industry — global
CVaR_α now spans 0.0–0.7 across the run. **But** on these instances it is *identical*
to `R_α global` (e.g. medium_seed1 every config/α). Cause: layered medium/small have
only **3 / 2 parts**, and global mode has one scenario per part, so a 30% tail of 2–3
parts collapses to the single worst part = the min = R_α.

Global CVaR_α is therefore pincered:
- few parts (layered) ⇒ collapses onto R_α (adds nothing),
- many parts but SPOF-heavy (industry) ⇒ saturates at 0.

**Keep `cvar_alpha_single`; drop/ignore `cvar_alpha_global`** (report `R_α global` or
`NRI_α global` instead). The widening was worth testing but global CVaR carries no
independent signal on either instance class.

## CVaR is the right statistic (it amplifies, honestly)

CVaR_α magnified the harm here (−0.0505 vs NRI_α's −0.0112 at α=0.4) just as it
magnified the benefit on industry (+0.0117 vs +0.0023). It is the more discriminating
tail measure; it simply reported that on these instances the soft constraints damage
partial-loss resilience.

## Takeaways for the thesis

1. Packing soft constraints (esp. anti-concentration) robustly improve **single-trip**
   resilience across instances — safe to claim.
2. Their effect on **partial-fleet-loss** resilience is **instance-dependent and can
   reverse** — do NOT claim single-trip gains transfer to partial loss.
3. The partial-loss verdict is **survivor-strategy-sensitive** (`heaviest` penalises
   concentration); re-run with alternative strategies before reporting.
4. Use single-mode CVaR_α; global-mode CVaR_α is degenerate (collapses to R_α on
   few-part instances, saturates to 0 on SPOF-heavy ones).
