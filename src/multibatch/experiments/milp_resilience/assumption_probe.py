"""Pressure-test two modelling assumptions, reusing cached flows (NO flow re-solve).

#5 free-rerouting: coverage is a max-flow recomputed AFTER a loss, i.e. demand may
   reroute freely over the part's surviving arcs. Compare against a NO-REROUTE coverage
   (the lost trip's load is simply gone) to quantify how much the rerouting assumption
   inflates resilience. Applies to every instance.

#2 synthetic valuation: the industry instance has no partVal, so we synthesise it.
   partVal weights ONLY the anti-concentration packing objective (not the metrics, which
   weight by demand). Re-solve the industry packing under {size, uniform} and check
   whether the resilience result is an artefact of the size-proportional valuation.
   (Layered instances ship real partVal, so #2 is industry-only.)

    PYTHONPATH=src .venv/bin/python -m multibatch.experiments.milp_resilience.assumption_probe
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from ...metrics.coverage import coverage_report
from ...metrics.resilience import (
    _build_location_index,
    _max_flow_coverage,
    _total_demand_per_part,
)
from ...models import TwoStageClingconConfig
from ...solvers.milp_flow import MilpFlowTwoStageSolver
from .suite import INSTANCE_DIR, WEIGHTED_ENC, _load_flow

RES = Path(__file__).resolve().parent / "results"
CACHE = RES / "flows"


def _build(inst_path, stage2_tl):
    cfg = TwoStageClingconConfig(weight=0, max_freq=20, cap_size_divide=1,
                                 time_limit=stage2_tl, round_timeout=stage2_tl,
                                 configuration="many")
    return MilpFlowTwoStageSolver(inst_path, config=cfg, backend="SCIP",
                                  flow_time_limit=1, stage2_encoding=WEIGHTED_ENC)


def _stats(vals):
    if not vals:
        return None, None
    s = sorted(vals)
    k = max(1, int(0.10 * len(s)))
    return round(sum(s) / len(s), 4), round(sum(s[:k]) / k, 4)   # mean, cvar10


def _both_coverages(stage1, stage2, instance):
    """Per (lost trip, part): max-flow coverage (reroute) vs no-reroute coverage."""
    loads, trip_loads = stage1.loads, stage2.trip_loads
    loc_idx, n_locs = _build_location_index(loads)
    parts = sorted({p for (_f, _t, _tr, p) in loads})
    td = _total_demand_per_part(instance, parts)
    trips: dict = {}
    for (f, t, tr, p, k), qty in trip_loads.items():
        trips.setdefault((f, t, tr, k), {})[p] = qty
    recs = []
    for (lf, lt, ltr, _lk), contents in trips.items():
        for p in parts:
            d = td.get(p, 0)
            if d == 0:
                continue
            lost = contents.get(p, 0)
            arc_caps: dict = {}
            for (f, t, tr, part), qty in loads.items():
                if part != p:
                    continue
                cap = max(0, qty - lost) if (f, t, tr) == (lf, lt, ltr) else qty
                arc_caps[(f, t)] = arc_caps.get((f, t), 0) + cap
            mf = _max_flow_coverage(p, instance, loc_idx, n_locs, arc_caps, d)
            nr = max(0.0, (d - lost) / d)
            recs.append({"lost": lost, "maxflow": mf, "noreroute": nr})
    return recs


def _set_partval(inst, scheme):
    if scheme == "size":
        inst.part_value = {p: max(1, inst.part_size.get(p, 1)) for p in inst.parts}
    else:
        inst.part_value = {p: 1 for p in inst.parts}


def main(argv=None) -> int:
    rows = []
    # ---------- #5 rerouting gap: industry + 2 layered ----------
    print("===== ASSUMPTION #5: free-rerouting (max-flow) vs no-reroute =====")
    reroute_targets = [("industry_test_1", 60), ("layered_medium_seed1", 20),
                       ("layered_small_seed1", 20)]
    for stem, tl in reroute_targets:
        cache = CACHE / f"flow_milp_ln0.0_lf0.0_{stem}.json"
        if not cache.exists():
            print(f"[{stem}] no cached flow — skip"); continue
        inst_path = INSTANCE_DIR / f"{stem}.lp"
        solver = _build(inst_path, tl)
        if stem == "industry_test_1":
            _set_partval(solver.instance, "size")   # industry needs a partVal
        stage1 = _load_flow(cache)
        for name, wh, wc in [("baseline", 0, 0), ("conc_w8", 0, 8)]:
            solver.config.w_hetero, solver.config.w_conc = wh, wc
            stage2 = solver._solve_stage2(stage1)
            if stage2 is None:
                print(f"  {stem} {name}: UNSAT"); continue
            recs = _both_coverages(stage1, stage2, solver.instance)
            aff = [r for r in recs if r["lost"] > 0]      # scenarios that actually hit the part
            mf_all, mf_t = _stats([r["maxflow"] for r in recs])
            nr_all, nr_t = _stats([r["noreroute"] for r in recs])
            mf_a, mf_at = _stats([r["maxflow"] for r in aff])
            nr_a, nr_at = _stats([r["noreroute"] for r in aff])
            row = dict(test="reroute", instance=stem, config=name, n=len(recs), n_aff=len(aff),
                       maxflow_mean=mf_all, noreroute_mean=nr_all,
                       maxflow_cvar10=mf_t, noreroute_cvar10=nr_t,
                       maxflow_mean_aff=mf_a, noreroute_mean_aff=nr_a,
                       maxflow_cvar10_aff=mf_at, noreroute_cvar10_aff=nr_at)
            rows.append(row)
            print(f"  {stem:22s} {name:9s} affected={len(aff):>5}/{len(recs)}  "
                  f"mean: mf={mf_all} nr={nr_all} (Δ{round((mf_all or 0)-(nr_all or 0),4)})  "
                  f"AFFECTED mean: mf={mf_a} nr={nr_a} (Δ{round((mf_a or 0)-(nr_a or 0),4)})  "
                  f"cvar10: mf={mf_at} nr={nr_at}")

    # ---------- #2 synthetic valuation (industry only) ----------
    print("\n===== ASSUMPTION #2: industry partVal = size vs uniform =====")
    cache = CACHE / "flow_milp_ln0.0_lf0.0_industry_test_1.json"
    if cache.exists():
        stage1 = _load_flow(cache)
        for scheme in ["size", "uniform"]:
            solver = _build(INSTANCE_DIR / "industry_test_1.lp", 100)
            _set_partval(solver.instance, scheme)
            for name, wh, wc in [("baseline", 0, 0), ("conc_w8", 0, 8), ("full_w8_8", 8, 8)]:
                solver.config.w_hetero, solver.config.w_conc = wh, wc
                stage2 = solver._solve_stage2(stage1)
                if stage2 is None:
                    print(f"  [{scheme}] {name}: UNSAT"); continue
                rep = coverage_report(stage1, stage2, solver.instance)
                ov = rep["overall"]
                row = dict(test="synthval", instance="industry_test_1", scheme=scheme,
                           config=name, nri=rep["nri"]["nri"], nri_worst=rep["nri"]["nri_worst"],
                           cov_cvar10=ov.get("cvar10"), cov_mean=ov.get("mean"),
                           concentrated=stage2.concentrated_count, mono=stage2.mono_count)
                rows.append(row)
                print(f"  [{scheme:7s}] {name:9s} nri={row['nri']} nri_worst={row['nri_worst']} "
                      f"cvar10={row['cov_cvar10']} conc={row['concentrated']} mono={row['mono']}")

    out = RES / "assumption_probe.csv"
    fields = sorted({k for r in rows for k in r})
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
