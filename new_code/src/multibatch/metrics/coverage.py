"""Richer demand-service-coverage metrics.

The existing R_1/R_TR/R_alpha report only the WORST case (min coverage over all
disruption scenarios). On a many-part instance one fragile part (e.g. routed on
a single-trip arc the packing cannot protect) zeros the worst case and masks any
packing improvement on the other parts.

This module reports the full coverage DISTRIBUTION over single-trip-loss
scenarios, plus:
  * demand-weighted service level (fill rate, weighting parts by demand),
  * CVaR@k (mean of the worst k% of scenarios — a tail metric between min and mean),
  * the 'packing-addressable' subset (scenarios where the lost trip sits on a
    MULTI-trip arc, so packing has trips to redistribute across; 1-trip arcs are
    flow-level single points of failure that no packing can fix).

Reuses the max-flow coverage engine from resilience.py.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from ..models import Instance, Stage1Result, Stage2Result
from .resilience import (
    _build_location_index,
    _max_flow_coverage,
    _total_demand_per_part,
    compute_r_alpha,
)


def single_trip_coverage_records(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
) -> list[dict]:
    """One record per (lost trip, demanded part): coverage + the arc's trip count.

    Mirrors compute_r1's scenario enumeration but keeps every scenario (not just
    the min) and tags each with how many trips its arc has (so we can isolate the
    packing-addressable scenarios).
    """
    loads = stage1.loads
    trip_loads = stage2.trip_loads
    loc_idx, n_locs = _build_location_index(loads)
    parts = sorted({p for (_f, _t, _tr, p) in loads})
    total_demand = _total_demand_per_part(instance, parts)
    arc_freq = {(rf.origin, rf.destination, rf.transport): rf.frequency for rf in stage1.route_freqs}

    trips: dict[tuple[str, str, str, int], dict[str, int]] = {}
    for (f, t, tr, p, k), qty in trip_loads.items():
        trips.setdefault((f, t, tr, k), {})[p] = qty

    records: list[dict] = []
    for (lost_f, lost_t, lost_tr, lost_k), contents in trips.items():
        n_trips = arc_freq.get((lost_f, lost_t, lost_tr), 1)
        for p in parts:
            td = total_demand.get(p, 0)
            if td == 0:
                continue
            lost_qty = contents.get(p, 0)
            arc_caps: dict[tuple[str, str], int] = {}
            for (f, t, tr, part), qty in loads.items():
                if part != p:
                    continue
                cap = max(0, qty - lost_qty) if (f, t, tr) == (lost_f, lost_t, lost_tr) else qty
                arc_caps[(f, t)] = arc_caps.get((f, t), 0) + cap
            cov = _max_flow_coverage(p, instance, loc_idx, n_locs, arc_caps, td)
            records.append({
                "arc": (lost_f, lost_t, lost_tr),
                "trip_k": lost_k,
                "n_trips_on_arc": n_trips,
                "part": p,
                "demand": td,
                "coverage": cov,
            })
    return records


def coverage_stats(records: list[dict]) -> dict:
    """Summary statistics for a list of coverage records."""
    if not records:
        return {"n": 0}
    cov = np.array([r["coverage"] for r in records], dtype=float)
    dem = np.array([r["demand"] for r in records], dtype=float)
    order = np.sort(cov)
    k = max(1, int(np.ceil(0.10 * len(order))))  # worst 10%
    return {
        "n": len(cov),
        "min": round(float(cov.min()), 4),
        "p10": round(float(np.percentile(cov, 10)), 4),
        "p25": round(float(np.percentile(cov, 25)), 4),
        "median": round(float(np.percentile(cov, 50)), 4),
        "mean": round(float(cov.mean()), 4),
        "cvar10": round(float(order[:k].mean()), 4),  # mean of worst 10%
        "frac_full": round(float((cov >= 0.999).mean()), 4),
        "frac_zero": round(float((cov <= 1e-9).mean()), 4),
        "demand_weighted_mean": round(float((cov * dem).sum() / dem.sum()), 4) if dem.sum() else None,
    }


def compute_nri(records: list[dict], scenario_weights: dict | None = None) -> dict:
    """Network Resilience Indicator (NRI).

    Performance-based resilience: the EXPECTED fraction of pre-disaster demand
    still satisfied post-disaster, over the disruption-scenario set.

    Per scenario s (one lost trip): frac_s = (Σ_p satisfied_p) / (Σ_p demand_p),
    where satisfied_p = coverage_{s,p}·demand_p. NRI = E_s[frac_s] — uniform over
    scenarios unless `scenario_weights` (scenario -> probability) is given.

    Returns nri plus the worst-scenario fraction and p10 of the per-scenario
    distribution (NRI is the mean; these show the tail).
    """
    if not records:
        return {"nri": None, "nri_n_scenarios": 0, "nri_worst": None, "nri_p10": None}
    by_s: dict = defaultdict(lambda: [0.0, 0.0])  # scenario -> [satisfied, demand]
    for r in records:
        s = (r["arc"], r["trip_k"])
        by_s[s][0] += r["coverage"] * r["demand"]
        by_s[s][1] += r["demand"]
    fracs = {s: (sat / dem if dem else 1.0) for s, (sat, dem) in by_s.items()}
    vals = np.array(list(fracs.values()), dtype=float)
    if scenario_weights:
        tot = sum(scenario_weights.get(s, 0.0) for s in fracs)
        nri = (sum(scenario_weights.get(s, 0.0) * f for s, f in fracs.items()) / tot
               if tot else None)
    else:
        nri = float(vals.mean())
    return {
        "nri": round(nri, 4) if nri is not None else None,
        "nri_n_scenarios": len(fracs),
        "nri_worst": round(float(vals.min()), 4),
        "nri_p10": round(float(np.percentile(vals, 10)), 4),
    }


def nri_alpha_from_details(details: list[dict], mode: str) -> float | None:
    """NRI under alpha-survival, derived from compute_r_alpha's details.

    This is the EXPECTED-demand sibling of R_alpha (which takes the min). It uses
    the identical disruption construction, aggregating coverage by demand instead.

      * global: a single scenario (all arcs at alpha) -> demand-weighted served
        fraction across parts.
      * single: one disrupted arc at a time -> served fraction per arc, then the
        expectation (mean) over which arc is disrupted.
    """
    if not details:
        return None
    if mode == "global":
        sat = sum(d["coverage"] * d["demand"] for d in details)
        dem = sum(d["demand"] for d in details)
        return round(sat / dem, 4) if dem else 1.0
    by_arc: dict = defaultdict(lambda: [0.0, 0.0])  # lost_arc -> [satisfied, demand]
    for d in details:
        by_arc[d.get("lost_arc")][0] += d["coverage"] * d["demand"]
        by_arc[d.get("lost_arc")][1] += d["demand"]
    fracs = [sat / dem if dem else 1.0 for sat, dem in by_arc.values()]
    return round(sum(fracs) / len(fracs), 4) if fracs else None


def compute_nri_alpha(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
    alpha: float = 0.2,
    mode: str = "single",
    strategy: str = "heaviest",
) -> tuple[float | None, list[dict]]:
    """Expected fraction of demand satisfied under alpha-survival disruption.

    Sweeps over the same (alpha, mode, strategy) as R_alpha. Returns (nri_alpha,
    r_alpha_details) so the worst-case R_alpha can be read from the same call.
    """
    _, details = compute_r_alpha(stage1, stage2, instance,
                                 alpha=alpha, mode=mode, strategy=strategy)
    return nri_alpha_from_details(details, mode), details


def coverage_report(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
) -> dict:
    """Full coverage report: overall, packing-addressable (multi-trip arcs), and
    flow-limited (single-trip arcs) subsets."""
    records = single_trip_coverage_records(stage1, stage2, instance)
    multi = [r for r in records if r["n_trips_on_arc"] > 1]
    single = [r for r in records if r["n_trips_on_arc"] <= 1]
    return {
        "overall": coverage_stats(records),
        "packing_addressable": coverage_stats(multi),  # multi-trip arcs
        "flow_limited": coverage_stats(single),         # 1-trip arcs (SPOFs)
        "nri": compute_nri(records),                    # expected demand satisfied
        "nri_addressable": compute_nri(multi),
        "n_single_trip_arc_scenarios": len(single),
        "n_multi_trip_arc_scenarios": len(multi),
    }
