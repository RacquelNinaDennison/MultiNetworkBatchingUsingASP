# Resilience Metrics for Two-Stage Logistics Optimisation

## Notation

| Symbol | Meaning |
|---|---|
| \( \mathcal{P} \) | Set of parts |
| \( \mathcal{L} \) | Set of locations |
| \( \mathcal{A} \) | Set of active arcs \( (f, t, \text{tr}) \) from Stage 1 |
| \( \mathcal{K}_{a} \) | Set of trips on arc \( a \in \mathcal{A} \) from Stage 2 |
| \( D_p \) | Total demand for part \( p \): \( D_p = \sum_{l \in \mathcal{L}} d_{p,l} \) |
| \( d_{p,l} \) | Demand for part \( p \) at location \( l \) |
| \( o_{p,l} \) | Supply (offer) of part \( p \) at location \( l \) |
| \( x_{a,p} \) | Aggregate load of part \( p \) on arc \( a \) (Stage 1 output) |
| \( q_{a,p,k} \) | Quantity of part \( p \) on trip \( k \) of arc \( a \) (Stage 2 output) |

---

## R_TR — Arc-Level Resilience

**Question:** If an entire arc (all trips on a route-transport pair) is disrupted, what fraction of each part's demand can still be met?

For a disrupted arc \( a^* \in \mathcal{A} \) and part \( p \in \mathcal{P} \), define the **residual network** \( G_{-a^*} \) by removing all capacity on arc \( a^* \). Compute the maximum flow for part \( p \) through this residual network:

\[
\phi_p(a^*) = \text{MaxFlow}_{G_{-a^*}}(p)
\]

where the flow network has:
- Source edges: \( s \to l \) with capacity \( o_{p,l} \) for each supply location
- Sink edges: \( l \to t \) with capacity \( d_{p,l} \) for each demand location
- Arc edges: \( f \to t \) with capacity \( x_{a,p} \) for each arc \( a \neq a^* \), and capacity 0 for \( a^* \)

The **coverage** when arc \( a^* \) is lost for part \( p \):

\[
c_p(a^*) = \min\!\left(\frac{\phi_p(a^*)}{D_p},\; 1\right)
\]

**R_TR** is the worst-case coverage across all arcs and parts:

\[
R_{TR} = \min_{a^* \in \mathcal{A}} \;\min_{p \in \mathcal{P}} \; c_p(a^*)
\]

- \( R_{TR} = 1.0 \): Full demand can be met even if any single arc is lost
- \( R_{TR} = 0.0 \): There exists an arc whose loss prevents any units of some part from being delivered

---

## R_1 — Trip-Level Resilience

**Question:** If a single trip is lost, what fraction of a part's demand can still be met?

For a disrupted trip \( k^* \) on arc \( a^* \) and part \( p \), the residual network \( G_{-k^*} \) reduces the capacity on arc \( a^* \) by the trip's load but keeps remaining trips intact:

\[
\phi_p(k^*) = \text{MaxFlow}_{G_{-k^*}}(p)
\]

where the arc capacity for \( a^* \) becomes \( x_{a^*,p} - q_{a^*,p,k^*} \) and all other arcs retain full capacity.

The **coverage** when trip \( k^* \) is lost for part \( p \):

\[
c_p(k^*) = \min\!\left(\frac{\phi_p(k^*)}{D_p},\; 1\right)
\]

**R_1** is the worst-case coverage across all trips and parts:

\[
R_1 = \min_{a^* \in \mathcal{A}} \;\min_{k^* \in \mathcal{K}_{a^*}} \;\min_{p \in \mathcal{P}} \; c_p(k^*)
\]

- \( R_1 \geq R_{TR} \) always (losing a single trip is less severe than losing an entire arc)
- \( R_1 = 1.0 \): Full demand survives the loss of any single trip

---

## K_1 — Kit Completion Ratio

**Question:** If a single trip is lost, what fraction of **complete kits** (orders requiring all parts) can still be assembled?

Individual part coverage may vary when a trip is lost — some parts are unaffected while others lose supply. A complete kit requires all parts, so the **bottleneck part** determines how many complete kits can be made.

For a disrupted trip \( k^* \), the **kit ratio** is the minimum coverage across all parts:

\[
\kappa(k^*) = \min_{p \in \mathcal{P}} \; c_p(k^*)
\]

**K_1** is the worst-case kit ratio across all trips:

\[
K_1 = \min_{a^* \in \mathcal{A}} \;\min_{k^* \in \mathcal{K}_{a^*}} \; \kappa(k^*)
\]

The **bottleneck part** for the worst trip \( k^*_{\text{worst}} \) is:

\[
p_{\text{bottleneck}} = \arg\min_{p \in \mathcal{P}} \; c_p(k^*_{\text{worst}})
\]

### Relationship to R_1

By construction:

\[
K_1 = R_1
\]

since both take the minimum over all (trip, part) combinations. However, K_1 provides additional diagnostic information:

- **Per-trip kit ratios** \( \kappa(k^*) \) — how vulnerable each trip is from a complete-kit perspective
- **Bottleneck identification** — which part limits kit completion for each disruption scenario
- **Kit-level aggregation** — enables comparing trips by their impact on complete orders rather than individual parts

---

## Dispatch Cost Metrics

### S1 Dispatch Cost

The dispatch cost implied by Stage 1 frequency assignments:

\[
C_{S1} = \sum_{a \in \mathcal{A}} f_a \cdot r_a
\]

where \( f_a \) is the assigned frequency and \( r_a \) is the per-trip cost for arc \( a \).

### S2 Dispatch Cost

The actual dispatch cost after Stage 2 packing (only counting used trips):

\[
C_{S2} = \sum_{a \in \mathcal{A}} |\{k \in \mathcal{K}_a : \exists\, p,\; q_{a,p,k} > 0\}| \cdot r_a
\]

### Cost Saving

\[
\Delta C = C_{S1} - C_{S2}
\]

A positive saving indicates Stage 2 packed loads into fewer trips than Stage 1 allocated.

---

## Packing Configuration Metrics

Stage 2 is run under four constraint configurations:

| Config | `hetero_on` | `concentrated_on` | Effect |
|---|---|---|---|
| `off_off` | 0 | 0 | No resilience constraints — pure packing |
| `hetero` | 1 | 0 | Penalise mono-part trips (encourage mixing) |
| `conc` | 0 | 1 | Penalise concentrated trips (limit single-part dominance) |
| `both` | 1 | 1 | Both penalties active |

### Mono-Part Trip Count

A trip is **mono-part** if it carries only one part type on a route that has multiple part types available:

\[
\text{mono\_count} = |\{(a, k) : |\{p : q_{a,p,k} > 0\}| = 1 \;\wedge\; |\{p : x_{a,p} > 0\}| > 1\}|
\]

### Concentrated Trip Count

A trip is **concentrated** in part \( p \) if it carries more than half the total load of \( p \) on that arc:

\[
\text{concentrated\_count} = \left|\left\{(a, p, k) : q_{a,p,k} \geq \left\lfloor \frac{x_{a,p}}{2} \right\rfloor\right\}\right|
\]
