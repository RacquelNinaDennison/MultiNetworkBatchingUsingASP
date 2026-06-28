# Network-level resilience (R_resource) + assumption checks

## 1. The network-level metric (the thing R_TR should have been)

`compute_r_tr` removes one **arc** at a time. `compute_r_resource` (new) removes an
**entire transport resource** (all its arcs) at once — the true network/fleet-level
disruption. Flow-only, computed from cached flows (no packing, no re-solve). Reports
worst-case (`r_resource`), expected (`nri_resource`, uniform over which resource is
lost, demand-weighted), tail (`cvar_resource`, worst-30% of resources), and the most
critical resource. Source: `resource_resilience.csv`.

| instance | r_tr (arc) | **r_resource (worst)** | nri_resource (exp.) | cvar_resource | most-critical | #active res |
|---|---|---|---|---|---|---|
| industry_test_1 (w0,w0) | 0.0 | **0.0** | 0.781 | 0.483 | **tr15** | 6 of 16 |
| layered_medium_seed1 | 0.30 | **0.0** | 0.456 | 0.011 | tr2 | 2 |
| layered_medium_seed2 | 0.53 | 0.133 | 0.472 | 0.433 | tr1 | 2 |
| layered_small_seed1 | 0.47 | **0.0** | 0.267 | 0.0 | tr1 | 2 |

**Findings:**
1. **Resource-loss is far more severe than arc-loss.** `r_resource ≤ r_tr` everywhere,
   often collapsing 0.30→0.0. The arc-level R_TR materially *understated* fragility;
   the network-level metric exposes it.
2. **Industry: worst-case = 0 but expected = 0.78.** Losing a random active resource
   leaves ~78% of demand on average, but the worst resource (**tr15**, the high-capacity
   workhorse) is a single point of failure (coverage→0). The flow uses only **6 of 16**
   resources — under-diversified by construction.
3. **Layered has only 2 active resources**, so losing one is near-catastrophic
   (r_resource ≈ 0, cvar ≈ 0).

**Effect of the flow levers (w_net, w_flow) on network-level resilience:**
- Industry w_flow=4: `nri_resource` unchanged (0.781→0.781). Redundancy adds trips on the
  *same* resources, so losing the resource still kills them.
- Layered w_net=4: improved *arc*-level r_tr (0.30→0.63) but **not** resource-level
  (r_resource stayed ≈0). Exposure penalty diversifies arcs, not resources.
- **Conclusion: neither flow lever improves network-level resilience.** It is bounded by
  *resource* concentration (few active resources, one critical). Improving it needs
  resource **diversification** — a different lever than packing or w_net/w_flow.

## 2. Assumption #5 — free-rerouting: SAFE

For every single-trip loss, max-flow coverage (rerouting allowed) vs no-reroute
coverage (lost load simply gone): **Δ = 0.0 in all ~6,000 scenarios** (industry, medium,
small; baseline and conc). The free-rerouting assumption inflates nothing — because the
cost-optimal flow has **no alternative paths with spare capacity**, so coverage = direct
loss. Good for metric validity; also reinforces the fragility story (no rerouting
cushion exists).

## 3. Assumption #2 — synthetic valuation: SAFE

Industry packing under `partVal = size` vs `uniform` gives **identical** NRI / nri_worst
/ cov_cvar10 / concentration for every config (baseline, conc_w8, full_w8_8). The
industry resilience result is **not** an artefact of the size-proportional valuation —
removing a caveat for the paper. (`partVal` weights the anti-concentration objective
only; metrics weight by demand.)

## Implications for the paper

- Report **R_resource** as the network-level resilience axis (worst + expected + tail),
  distinct from the packing-level single-trip metrics. It is the honest "how bad if a
  whole transport mode goes down" number, and it is **packing-invariant** (flow-only).
- The two assumption checks (#2, #5) both come back clean — state them as robustness
  notes, not threats.
