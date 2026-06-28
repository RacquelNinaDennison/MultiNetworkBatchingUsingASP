"""Resilience metrics — R_TR, R_1, K_1, R_alpha.

These measure worst-case demand coverage under disruption scenarios:
- R_TR:    entire transport resource on an arc removed
- R_1:     single trip lost
- K_1:     kit-completion ratio under single-trip loss
- R_alpha: fraction (1-alpha) of trips lost on an arc

All metrics use scipy maximum-flow to compute surviving supply
through the network after removing disrupted capacity.
"""

from __future__ import annotations

import math

from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_flow

from ..models import Instance, Stage1Result, Stage2Result


# ── Shared helpers ────────────────────────────────────────────────────

_SCALE = 1000  # integer scaling for max-flow (avoids float issues)


def _build_location_index(
    loads: dict[tuple[str, str, str, str], int],
) -> tuple[dict[str, int], int]:
    """Build location-to-index mapping from load keys.

    Returns (loc_idx, n_locations).
    """
    all_locs = sorted(
        {f for (f, t, tr, p) in loads}
        | {t for (f, t, tr, p) in loads}
    )
    return {loc: i for i, loc in enumerate(all_locs)}, len(all_locs)


def _total_demand_per_part(
    instance: Instance,
    parts: list[str],
) -> dict[str, int]:
    """Total demand for each part across all locations."""
    demands = instance.demands
    return {
        p: sum(q for (part, loc), q in demands.items() if part == p)
        for p in parts
    }


def _max_flow_coverage(
    part: str,
    instance: Instance,
    loc_idx: dict[str, int],
    n_locs: int,
    arc_capacities: dict[tuple[str, str], int],
    total_demand: int,
) -> float:
    """Compute demand coverage for a single part via max-flow.

    arc_capacities: (origin, dest) -> total capacity for this part
    after disruption (already aggregated across transport resources).
    """
    s_node = n_locs
    t_node = n_locs + 1
    n_nodes = n_locs + 2

    cap = [[0] * n_nodes for _ in range(n_nodes)]

    for (p, loc), qty in instance.offers.items():
        if p == part and loc in loc_idx:
            cap[s_node][loc_idx[loc]] += int(qty * _SCALE)

    for (p, loc), qty in instance.demands.items():
        if p == part and loc in loc_idx:
            cap[loc_idx[loc]][t_node] += int(qty * _SCALE)

    for (f, t), arc_cap in arc_capacities.items():
        if f in loc_idx and t in loc_idx:
            cap[loc_idx[f]][loc_idx[t]] += int(arc_cap * _SCALE)

    flow_val = maximum_flow(csr_matrix(cap), s_node, t_node).flow_value
    max_supply = flow_val / _SCALE
    return round(min(max_supply / total_demand, 1.0), 4)


# ── R_TR: Transport-resource resilience ───────────────────────────────


def compute_r_tr(
    stage1: Stage1Result,
    instance: Instance,
) -> tuple[float, list[dict]]:
    """Worst-case coverage when an entire arc-TR is removed.

    Enumerates every active (origin, dest, transport) arc. For each,
    removes all load on that arc and computes surviving demand coverage
    via max-flow for every part.

    Returns (r_tr, details) where r_tr is the worst coverage across
    all scenarios and parts.
    """
    loads = stage1.loads
    loc_idx, n_locs = _build_location_index(loads)
    parts = sorted({p for (f, t, tr, p) in loads})
    total_demand = _total_demand_per_part(instance, parts)

    active_arcs = sorted({(f, t, tr) for (f, t, tr, p) in loads})
    details: list[dict] = []
    all_coverages: list[float] = []

    for lost_f, lost_t, lost_tr in active_arcs:
        for p in parts:
            td = total_demand.get(p, 0)
            if td == 0:
                continue

            # Build arc capacities with disrupted arc zeroed out
            arc_caps: dict[tuple[str, str], int] = {}
            for (f, t, tr, part), qty in loads.items():
                if part != p:
                    continue
                cap = 0 if (f, t, tr) == (lost_f, lost_t, lost_tr) else qty
                key = (f, t)
                arc_caps[key] = arc_caps.get(key, 0) + cap

            coverage = _max_flow_coverage(
                p, instance, loc_idx, n_locs, arc_caps, td,
            )

            details.append({
                "lost_f": lost_f,
                "lost_t": lost_t,
                "lost_tr": lost_tr,
                "part": p,
                "demand": td,
                "coverage": coverage,
            })
            all_coverages.append(coverage)

    r_tr = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_tr, details


def compute_r_resource(
    stage1: Stage1Result,
    instance: Instance,
) -> tuple[float, list[dict]]:
    """NETWORK-level resilience: remove an ENTIRE transport resource at once.

    Unlike compute_r_tr (which removes one (origin,dest,transport) ARC at a time),
    this loses every arc operated by a transport resource tr_k simultaneously — the
    whole fleet/mode across the network. For each resource and part it zeroes all of
    that resource's arcs and recomputes surviving demand coverage via max-flow.

    Returns (r_resource, details): r_resource is the worst coverage over all
    (resource, part) scenarios; `details` keeps every scenario so the caller can form
    distributional summaries (expected NRI_resource, CVaR_resource, per-resource
    criticality) the same way as the single-trip and alpha panels.
    """
    loads = stage1.loads
    loc_idx, n_locs = _build_location_index(loads)
    parts = sorted({p for (f, t, tr, p) in loads})
    total_demand = _total_demand_per_part(instance, parts)
    resources = sorted({tr for (_f, _t, tr, _p) in loads})

    details: list[dict] = []
    all_coverages: list[float] = []
    for lost_tr in resources:
        for p in parts:
            td = total_demand.get(p, 0)
            if td == 0:
                continue
            arc_caps: dict[tuple[str, str], int] = {}
            for (f, t, tr, part), qty in loads.items():
                if part != p:
                    continue
                cap = 0 if tr == lost_tr else qty   # whole resource removed
                arc_caps[(f, t)] = arc_caps.get((f, t), 0) + cap
            coverage = _max_flow_coverage(p, instance, loc_idx, n_locs, arc_caps, td)
            details.append({"lost_tr": lost_tr, "part": p, "demand": td, "coverage": coverage})
            all_coverages.append(coverage)

    r_resource = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_resource, details


# ── R_1: Single-trip resilience ───────────────────────────────────────


def compute_r1(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
) -> tuple[float, list[dict]]:
    """Worst-case coverage when a single trip is lost.

    Enumerates every trip in the Stage 2 solution. For each,
    subtracts that trip's load from the aggregate arc capacity
    and computes surviving demand coverage via max-flow.

    Returns (r_1, details).
    """
    loads = stage1.loads
    trip_loads = stage2.trip_loads
    loc_idx, n_locs = _build_location_index(loads)
    parts = sorted({p for (f, t, tr, p) in loads})
    total_demand = _total_demand_per_part(instance, parts)

    # Group trip_loads by trip key
    trips: dict[tuple[str, str, str, int], dict[str, int]] = {}
    for (f, t, tr, p, k), qty in trip_loads.items():
        trip_key = (f, t, tr, k)
        trips.setdefault(trip_key, {})[p] = qty

    details: list[dict] = []
    all_coverages: list[float] = []

    for trip_key, trip_contents in trips.items():
        lost_f, lost_t, lost_tr, lost_k = trip_key

        for p in parts:
            td = total_demand.get(p, 0)
            if td == 0:
                continue

            lost_qty = trip_contents.get(p, 0)

            # Build arc capacities with trip's load subtracted
            arc_caps: dict[tuple[str, str], int] = {}
            for (f, t, tr, part), qty in loads.items():
                if part != p:
                    continue
                if (f, t, tr) == (lost_f, lost_t, lost_tr):
                    cap = max(0, qty - lost_qty)
                else:
                    cap = qty
                key = (f, t)
                arc_caps[key] = arc_caps.get(key, 0) + cap

            coverage = _max_flow_coverage(
                p, instance, loc_idx, n_locs, arc_caps, td,
            )

            details.append({
                "lost_trip": f"({lost_f},{lost_t},{lost_tr},k{lost_k})",
                "lost_contents": dict(trip_contents),
                "part": p,
                "demand": td,
                "coverage": coverage,
            })
            all_coverages.append(coverage)

    r_1 = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_1, details


# ── K_1: Kit-completion ratio ─────────────────────────────────────────


def compute_k1(
    r1_details: list[dict],
) -> tuple[float, list[dict]]:
    """Kit-completion ratio from R_1 per-trip details.

    For each lost trip, the bottleneck part is the one with lowest
    coverage. K_1 is the worst bottleneck across all trips.

    Must be called with the details list returned by compute_r1.
    """
    trip_groups: dict[str, list[dict]] = {}
    for d in r1_details:
        trip_groups.setdefault(d["lost_trip"], []).append(d)

    kit_details: list[dict] = []
    for trip_key, part_details in trip_groups.items():
        bottleneck = min(part_details, key=lambda d: d["coverage"])
        kit_details.append({
            "lost_trip": trip_key,
            "bottleneck_part": bottleneck["part"],
            "kit_ratio": bottleneck["coverage"],
        })

    kit_details.sort(key=lambda d: d["kit_ratio"])
    k_1 = kit_details[0]["kit_ratio"] if kit_details else 1.0
    return k_1, kit_details


# ── R_alpha: Partial arc disruption ───────────────────────────────────


def compute_r_alpha(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
    alpha: float = 0.2,
    mode: str = "single",
    strategy: str = "heaviest",
) -> tuple[float, list[dict]]:
    """Worst-case coverage under partial arc disruption.

    Only ``alpha`` fraction of trips survive on the disrupted arc(s).

    Parameters
    ----------
    alpha : float
        Survival fraction (0.0-1.0). E.g. alpha=0.2 means 20% of
        trips survive, 80% are lost.
    mode : str
        ``"single"`` disrupts one arc at a time (worst case);
        ``"global"`` disrupts all arcs simultaneously.
    strategy : str
        How to choose surviving trips:
        ``"heaviest"`` removes most-loaded trips first,
        ``"first"`` keeps first k trips (smallest indices),
        ``"last"`` keeps last k trips (largest indices).
    """
    loads = stage1.loads
    trip_loads = stage2.trip_loads
    loc_idx, n_locs = _build_location_index(loads)
    parts = sorted({p for (f, t, tr, p) in loads})
    total_demand = _total_demand_per_part(instance, parts)

    # Group trip_loads by arc
    arc_trips: dict[tuple[str, str, str], dict[int, dict[str, int]]] = {}
    for (f, t, tr, p, k), qty in trip_loads.items():
        arc_trips.setdefault((f, t, tr), {}).setdefault(k, {})[p] = qty

    def _select_survivors(
        trips_dict: dict[int, dict[str, int]],
    ) -> set[int]:
        trip_ids = sorted(trips_dict.keys())
        freq = len(trip_ids)
        k = max(math.floor(alpha * freq), 0)
        if k >= freq:
            return set(trip_ids)
        if k == 0:
            return set()

        if strategy == "first":
            return set(trip_ids[:k])
        elif strategy == "last":
            return set(trip_ids[-k:])
        else:  # heaviest: remove most-loaded first
            by_load = sorted(
                trip_ids,
                key=lambda tid: sum(trips_dict[tid].values()),
                reverse=True,
            )
            removed = set(by_load[:freq - k])
            return set(trip_ids) - removed

    def _surviving_loads(
        arc: tuple[str, str, str],
        survivors: set[int],
    ) -> dict[str, int]:
        result: dict[str, int] = {}
        for kid, parts_dict in arc_trips.get(arc, {}).items():
            if kid in survivors:
                for p, qty in parts_dict.items():
                    result[p] = result.get(p, 0) + qty
        return result

    active_arcs = sorted(arc_trips.keys())

    if mode == "global":
        return _r_alpha_global(
            loads, instance, loc_idx, n_locs, parts,
            total_demand, active_arcs, arc_trips,
            _select_survivors, _surviving_loads, alpha, strategy,
        )

    return _r_alpha_single(
        loads, instance, loc_idx, n_locs, parts,
        total_demand, active_arcs, arc_trips,
        _select_survivors, _surviving_loads, alpha, strategy,
    )


def _r_alpha_global(
    loads, instance, loc_idx, n_locs, parts,
    total_demand, active_arcs, arc_trips,
    select_survivors, surviving_loads, alpha, strategy,
) -> tuple[float, list[dict]]:
    """All arcs disrupted simultaneously."""
    survivors_per_arc = {
        arc: select_survivors(arc_trips[arc])
        for arc in active_arcs
    }
    reduced_loads: dict[tuple[str, str, str, str], int] = {}
    for arc in active_arcs:
        sl = surviving_loads(arc, survivors_per_arc[arc])
        for p, qty in sl.items():
            reduced_loads[(*arc, p)] = qty
    for key in loads:
        if key not in reduced_loads:
            reduced_loads[key] = 0

    details: list[dict] = []
    all_coverages: list[float] = []

    for p in parts:
        td = total_demand.get(p, 0)
        if td == 0:
            continue

        arc_caps: dict[tuple[str, str], int] = {}
        for (f, t, tr, part), qty in reduced_loads.items():
            if part != p:
                continue
            key = (f, t)
            arc_caps[key] = arc_caps.get(key, 0) + qty

        coverage = _max_flow_coverage(
            p, instance, loc_idx, n_locs, arc_caps, td,
        )

        details.append({
            "mode": "global", "strategy": strategy, "alpha": alpha,
            "part": p, "demand": td, "coverage": coverage,
        })
        all_coverages.append(coverage)

    r_alpha = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_alpha, details


def _r_alpha_single(
    loads, instance, loc_idx, n_locs, parts,
    total_demand, active_arcs, arc_trips,
    select_survivors, surviving_loads, alpha, strategy,
) -> tuple[float, list[dict]]:
    """One arc disrupted at a time (worst case)."""
    details: list[dict] = []
    all_coverages: list[float] = []

    for disrupted_arc in active_arcs:
        survivors = select_survivors(arc_trips[disrupted_arc])
        surviving = surviving_loads(disrupted_arc, survivors)

        for p in parts:
            td = total_demand.get(p, 0)
            if td == 0:
                continue

            arc_caps: dict[tuple[str, str], int] = {}
            for (f, t, tr, part), qty in loads.items():
                if part != p:
                    continue
                if (f, t, tr) == disrupted_arc:
                    cap = surviving.get(p, 0)
                else:
                    cap = qty
                key = (f, t)
                arc_caps[key] = arc_caps.get(key, 0) + cap

            coverage = _max_flow_coverage(
                p, instance, loc_idx, n_locs, arc_caps, td,
            )

            details.append({
                "mode": "single", "strategy": strategy, "alpha": alpha,
                "lost_arc": f"({disrupted_arc[0]},{disrupted_arc[1]},{disrupted_arc[2]})",
                "part": p, "demand": td, "coverage": coverage,
            })
            all_coverages.append(coverage)

    r_alpha = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_alpha, details
