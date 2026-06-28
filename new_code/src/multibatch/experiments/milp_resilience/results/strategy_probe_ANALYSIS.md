# Strategy-sensitivity probe — is the "soft constraints hurt partial loss" result an artefact?

Method: per instance, load cached MILP flow, solve each packing ONCE, score the
alpha-triple on that *identical* packing under {heaviest, first, last}. Strategy is the
only variable. 10 layered instances (small/medium × 5 seeds), single mode, q=0.10.
Source: `strategy_probe.csv`, `strategy_probe.log`.

Validation: the `heaviest` column reproduces the earlier suite run exactly
(conc_w8 CVaR_α a0.4 meanΔ = −0.0505 in both) — the probe is correct.

## CVaR_α meanΔ vs baseline, conc_w8 (the main soft constraint)

| α | heaviest | first | last |
|---|---|---|---|
| 0.2 | −0.0222 | −0.0133 | −0.0044 |
| 0.4 | **−0.0505** | −0.0078 | −0.0023 |
| 0.6 | **−0.0472** | −0.0033 | −0.0005 |
| 0.8 | −0.0300 | −0.0128 | +0.0011 |
| wins/10 | 1–2 / 10 | 2–5 / 10 | 3–5 / 10 |

The harm collapses as the strategy stops targeting the heavy (concentrated) trips:
**heaviest −0.03…−0.05 → first −0.003…−0.013 → last −0.004…+0.001 (≈ zero).** At α=0.4,
~95% of the apparent harm disappears under load-agnostic removal.

## Verdict

**The strong "anti-concentration hurts partial-loss resilience" result is an artefact
of `strategy="heaviest"`.** That strategy removes the most-loaded trips first — exactly
the trips concentration creates — so it adversarially penalises concentration. Under a
load-agnostic strategy (`last`) the effect vanishes; conc_w8 is **neutral** on the
partial-loss tail (neither helps nor hurts, win-rate ≈ coin-flip).

Note the honest refinement: conc_w8 does NOT become *beneficial* under first/last — it
becomes *neutral*. So the partial-loss axis simply does not reward anti-concentration;
the earlier "hurts" reading was the strategy, the real signal is "no effect".

Secondary observations (non-adversarial strategies even favour the other two configs):
- `hetero_w8` under `first`: **positive** at α=0.4 (+0.0094, 4/10) and α=0.6 (+0.0067, 6/10).
- `full_w8_8` under `last`: **positive** at α=0.4 (+0.0128, 6/10), α=0.6 (+0.0056, 6/10), α=0.8 (+0.0061).

## Consequences for the thesis

1. **Defensible:** packing soft constraints (esp. anti-concentration) robustly improve
   **single-trip** resilience (9/10 on NRI, 8/10 on cov_cvar10). Strategy-free metric.
2. **Retract:** the claim that they *hurt* **partial-fleet-loss** resilience. That was a
   `heaviest`-removal artefact. Under load-agnostic removal the effect is ~neutral.
3. **Methodological:** R_α / CVaR_α under a single adversarial strategy is NOT "the"
   resilience. Report the strategy explicitly and either average over strategies or
   treat single-trip loss as the primary axis (strategy-free) and α-loss as a
   sensitivity check. `strategy="heaviest"` should not be the silent default for headline
   numbers.

## Suggested defaults going forward

- Headline resilience = single-trip metrics (NRI, cov_cvar10) — robust, strategy-free.
- α-loss = report as a strategy panel (heaviest/first/last) or strategy-averaged, never
  a single adversarial number.
