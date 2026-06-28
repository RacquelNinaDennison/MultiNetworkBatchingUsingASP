# Parametric CVaR_α analysis — `industry_test_1`

Run: MILP/MOP flow (70% envelope, cached, cost 3,166,409, 35 arcs / 106 trips /
17 single-trip SPOFs, not optimal) + packing sweep {baseline, hetero_w8, conc_w8,
full_w8_8}, 100s each. New metric: `cvar_alpha_{mode}_{α}` = mean of the worst-10%
of the α-survival scenarios (tail sibling of NRI_α=mean and R_α=min).
Reminder: **α is survival fraction** (α=0.2 ⇒ 80% of trips lost = severe; α=0.8 ⇒ 20% lost = mild).

Source: `suite_industry_cvar.csv`, `suite_industry_cvar.log`.

## 1. The triple {R_α, CVaR_α, NRI_α} on the partial-loss axis (single mode)

| config | metric | α0.2 | α0.4 | α0.6 | α0.8 |
|---|---|---|---|---|---|
| baseline | R_α (min) | 0.0 | 0.0 | 0.0 | 0.0 |
| baseline | **CVaR_α (tail)** | 0.8357 | 0.8432 | 0.8772 | 0.8914 |
| baseline | NRI_α (mean) | 0.9570 | 0.9592 | 0.9661 | 0.9702 |
| conc_w8 | **CVaR_α (tail)** | **0.8379** | **0.8549** | 0.8785 | 0.9027 |
| conc_w8 | NRI_α (mean) | 0.9576 | 0.9615 | 0.9675 | 0.9730 |
| hetero_w8 | **CVaR_α (tail)** | 0.8354 | 0.8432 | **0.8856** | 0.9027 |
| full_w8_8 | **CVaR_α (tail)** | 0.8367 | 0.8528 | 0.8798 | **0.9055** |

**Why the tail earns its place:** R_α is a flat **0.0** everywhere (the 17 single-trip
SPOFs guarantee some part hits zero coverage, so the worst-case min is useless for
ranking packings). NRI_α (mean) is informative but compressed into 0.957–0.973 — a
0.002 spread. CVaR_α sits far lower (0.835–0.906) and **spreads the configs ~3–5×
wider**, so it actually discriminates between packings where the mean cannot and the
min is dead.

## 2. Tail amplifies the packing signal (win-rate Δ vs baseline)

| metric | conc_w8 | full_w8_8 | hetero_w8 |
|---|---|---|---|
| NRI_α single 0.4 (mean) | +0.0023 | +0.0023 | +0.0002 |
| **CVaR_α single 0.4 (tail)** | **+0.0117** | +0.0096 | +0.0000 |
| NRI_α single 0.6 (mean) | +0.0014 | +0.0015 | +0.0011 |
| **CVaR_α single 0.6 (tail)** | +0.0013 | +0.0026 | **+0.0084** |

At α=0.4 the tail shows a **~5× larger** improvement for `conc_w8` than the mean
does (+0.0117 vs +0.0023). The packing benefit under partial loss is a *tail*
phenomenon, exactly as it was for single-trip loss (cov_cvar10 moved ~10× more than
cov_mean).

## 3. New finding: a severity-dependent crossover

The mean (NRI_α) ranks conc ≈ full ≈ hetero at every α. The tail (CVaR_α) reveals a
crossover the mean hides:

- **Severe loss (α=0.2, 0.4 ⇒ 60–80% lost): anti-concentration wins.** `conc_w8`
  has the best single-mode tail (0.8379 / 0.8549). Spreading each part over more
  trips means any one loss removes a smaller slice — the regime that matters most
  for resilience.
- **Mild loss (α=0.6 ⇒ 40% lost): heterogeneity wins.** `hetero_w8` jumps to the
  best tail (0.8856, Δ+0.0084) while conc is flat. Mixing product *types* helps when
  enough trips survive to keep every part partially served.
- **`full_w8_8` is the all-rounder, rarely the single best**, and we already know it
  overpays (cost_saving collapses 399k→62k).

**Answer to the original question — does conc_w8's tail advantage hold under partial
(not just single-trip) loss? Yes, in the severe regime (α≤0.4)**, which is the
resilience-relevant one. Under mild loss the lever shifts to heterogeneity.

## 4. Caveat realised: `cvar_alpha_global` is degenerate here

`cvar_alpha[global] = 0.0` for **every** config and α. Global mode loses (1−α) of
trips on all arcs at once; with 17 SPOFs the worst-demand 10% tail lands entirely in
zero-coverage parts, so it saturates at 0 (same as R_α global). At q=10% the global
tail carries no signal on this instance. Options: widen the global tail (CVaR20/30),
or just drop global CVaR and keep global to NRI_α (mean) only. Single-mode CVaR_α is
where the signal is.

## Recommendation

Keep `cvar_alpha_single` in the panel — it discriminates packings where R_α (min) is
dead and NRI_α (mean) is washed out, and it surfaced the severity crossover. Treat
`cvar_alpha_global` as non-informative on SPOF-heavy flows (report NRI_α global
instead, or widen its tail).
