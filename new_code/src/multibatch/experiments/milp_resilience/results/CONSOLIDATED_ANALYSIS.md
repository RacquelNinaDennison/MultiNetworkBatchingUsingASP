# Resilience study — consolidated analysis (for the paper)

**Central question:** do the Stage-2 packing soft constraints (anti-concentration
`w_conc`, heterogeneity `w_hetero`) measurably change resilience under our metrics?

**Dataset:** `suite_consolidated.csv` — 336 rows, 11 instances (5 medium + 5 small +
industry), 4 packing configs {baseline, hetero_w8, conc_w8, full_w8_8}, flow-lever grid
`w_net{0,4} × w_flow{0,4,8}`, MILP and ASP flow. Industry flow at 70% envelope (the
experiment setting), packings are 30–100s incumbents. Figures in `results/figures/`.
Two industry corners (`w_net=4` with `w_flow∈{4,8}`) found no feasible flow in 600s and
are absent by design.

---

## Result 1 — Packing improves SINGLE-TRIP resilience (the headline). `fig1`

Holding the flow fixed (MILP, w_net=w_flow=0), `conc_w8` beats baseline on **NRI 10/11**
and **CVaR$_{10}$ 8/11** instances. Effect sizes: NRI +0.004…+0.016, CVaR$_{10}$
+0.01…+0.064. Only `medium_seed4` is the consistent exception. This is the **defensible,
strategy-free headline claim**: anti-concentration spreads each part over more trips, so
a single-trip loss removes a smaller slice → higher tail coverage.

## Result 2 — It holds across every flow-redundancy level. `fig3`

On industry, `conc_w8`/`full_w8_8` lift CVaR$_{10}$ at all three `w_flow` levels
(e.g. baseline→conc: 0.802→0.838 at w_flow=0, 0.798→0.852 at w_flow=8λ). The packing
effect is independent of the flow lever — it is not an artefact of one flow.

## Result 3 — Flow redundancy is a complementary but EXPENSIVE lever. `fig3`

Raising `w_flow` cuts single-trip SPOFs (17 → 2–5 arcs) and lifts **worst-case** NRI
(baseline nri_worst 0.891 → 0.909 → 0.913), but **flow cost rises +13% → +47%** and the
tail-average barely moves. So worst-case gains cost real money; packing is the cheaper
resilience lever. Best combined point: `full_w8_8` + w_flow=4λ (nri_worst 0.938, +13%).
Caveat: `w_net` (exposure) actually produced a *more* SPOF-heavy flow (76 single arcs) —
it does not help and may hurt; single non-optimal incumbents, treat with care.

## Result 4 — Dose-response: resilience saturates early. `fig5`

Sweeping `w_conc ∈ {1,2,4,8,16}` on industry: concentration drops 124→52 and CVaR$_{10}$
makes its whole move by **w_conc ≈ 2**, flat thereafter. Best worst-case at **w_conc = 4**
(nri_worst 0.934) at slightly better cost than w=2. Recommendation: a *small* weight
(2–4× mean trip cost); higher weights waste cost. (w=1 helps the tail but worsens the
absolute worst case — use w≥2.)

## Result 5 — Network-level resilience: a structural ceiling packing can't touch. `fig4`

New metric `compute_r_resource` removes an **entire transport resource** (all its arcs),
vs the old arc-level R_TR. Findings: r_resource ≤ R_TR everywhere (often 0.30→0.0); on
industry the worst-case is 0 but the *expected* is 0.78, with **tr15** the critical
single-point-of-failure resource (flow uses only 6 of 16 resources). **R_resource is
flow-only and packing-invariant**, and neither flow lever fixes it (it needs cross-
resource *diversification*). This is the honest limitation: packing helps fine-grained
single-trip resilience but cannot address fleet-level fragility.

## Result 6 — ASP vs MILP flow: MILP dominates. `fig2`

On the layered flows, **MILP solves in <1s and proves optimality (6/6); ASP routinely
hits the 120s cap (0–2/6 proven) — a 200–800× speedup.** ASP cannot reach a feasible
industry flow at all. Supports the paper's MILP-for-flow recommendation.

## Robustness checks — both pass

- **#5 free-rerouting:** max-flow vs no-reroute coverage Δ = 0.0 in ~6,000 scenarios —
  the cost-optimal flow has no spare-capacity alternative paths, so the metric is not
  inflated by optimistic rerouting.
- **#2 synthetic valuation:** industry packing under `partVal = size` vs `uniform` gives
  identical resilience — results are not an artefact of the invented valuation.

## Parametric (α) axis — report as a sensitivity panel, not a claim. `fig6`

R_α/CVaR_α/NRI_α under the suite default `strategy="heaviest"` show packing *harming*
partial-loss resilience, but the `strategy_probe` proves this is an artefact: the harm
(−0.05 at α=0.4) collapses to ≈0 under load-agnostic `first`/`last` removal. So the
partial-loss verdict is **strategy-dependent → neutral**, not a real effect. R_α and R_TR
are worst-case/flow-dominated and not packing claims.

---

## One-paragraph summary for the paper

> Packing soft constraints (anti-concentration) measurably and cheaply improve
> single-trip resilience across 11 instances (NRI 10/11, CVaR$_{10}$ 8/11), robustly to
> the flow lever and saturating at a small weight (w_conc≈2–4). Flow redundancy is a
> complementary but costly lever for worst-case resilience (+13–47% cost). Network-level
> resilience to whole-resource loss is a structural ceiling that is flow-determined and
> packing-invariant (critical resource tr15). MILP dominates ASP for the flow (200–800×).
> Two robustness checks (free-rerouting, synthetic valuation) pass; the parametric α-axis
> verdict is a survivor-strategy artefact and is reported as a sensitivity panel.

## Figures
1. `fig1_packing_single_trip.png` — packing effect on NRI & CVaR$_{10}$ (headline)
2. `fig2_asp_vs_milp.png` — flow solve time, MILP vs ASP (log)
3. `fig3_flow_lever_tradeoff.png` — industry cost vs resilience as w_flow rises
4. `fig4_network_resource.png` — network-level R_resource vs arc-level R_TR
5. `fig5_dose_response.png` — w_conc dose-response (the knee)
6. `fig6_strategy_artefact.png` — α verdict flips with survivor strategy
