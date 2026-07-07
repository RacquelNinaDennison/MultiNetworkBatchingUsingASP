"""Network-level resilience (entire-transport-resource loss) across cached flows.

The suite's `r_tr` removes one (origin,dest,transport) ARC at a time. This probe uses
`compute_r_resource`, which removes an ENTIRE transport resource (all its arcs) at
once — the true network/fleet-level disruption. It is FLOW-only, so it just reads each
cached flow JSON (no packing, no re-solve) and reports, per (instance, w_net, w_flow):

  * r_resource   : worst coverage over (resource, part)            [strict worst case]
  * nri_resource : demand-weighted mean served fraction, uniform over which resource
                   is lost                                          [expected]
  * cvar_resource: mean of the worst-30% resources' served fraction [tail]
  * worst_res    : the most critical resource and its served fraction
  * r_tr (arc)   : the old arc-level number, for contrast

    PYTHONPATH=src .venv/bin/python -m multibatch.experiments.milp_resilience.resource_probe
"""

from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

from ...instance.parser import parse_instance
from ...metrics.resilience import compute_r_resource, compute_r_tr
from .suite import INSTANCE_DIR, _load_flow

RES = Path(__file__).resolve().parent / "results"
CACHE = RES / "flows"
NAME_RE = re.compile(r"flow_(?P<solver>\w+?)_ln(?P<ln>[\d.]+)_lf(?P<lf>[\d.]+)_(?P<stem>.+)\.json")


def _resource_summary(details: list[dict], q: float = 0.30) -> dict:
    """Aggregate compute_r_resource details into worst / expected / tail / criticality."""
    by_res: dict = {}
    for d in details:
        s, dem = by_res.setdefault(d["lost_tr"], [0.0, 0.0]), d["demand"]
        s[0] += d["coverage"] * dem
        s[1] += dem
    fracs = {tr: (sat / dem if dem else 1.0) for tr, (sat, dem) in by_res.items()}
    if not fracs:
        return {}
    vals = sorted(fracs.values())
    k = max(1, int(math.ceil(q * len(vals))))
    worst_tr = min(fracs, key=fracs.get)
    return {
        "n_resources": len(fracs),
        "nri_resource": round(sum(vals) / len(vals), 4),       # expected (uniform resource loss)
        "cvar_resource": round(sum(vals[:k]) / k, 4),          # worst-30% tail
        "worst_res_frac": round(min(vals), 4),                 # most critical resource
        "worst_res": worst_tr,
    }


def main(argv=None) -> int:
    flows = sorted(CACHE.glob("*.json"))
    if not flows:
        print(f"No cached flows in {CACHE} — run the suite first."); return 1
    rows = []
    print(f"{'instance':24s}{'w_net':>6}{'w_flow':>7}{'r_tr(arc)':>10}{'r_resource':>11}"
          f"{'nri_res':>9}{'cvar_res':>9}{'worst_res':>11}{'#res':>5}")
    inst_cache: dict = {}
    for fp in flows:
        m = NAME_RE.match(fp.name)
        if not m:
            continue
        stem, ln, lf = m["stem"], float(m["ln"]), float(m["lf"])
        inst_path = INSTANCE_DIR / f"{stem}.lp"
        if not inst_path.exists():
            continue
        instance = inst_cache.setdefault(stem, parse_instance(inst_path))
        stage1 = _load_flow(fp)
        try:
            r_tr = compute_r_tr(stage1, instance)[0]
            r_res, details = compute_r_resource(stage1, instance)
        except Exception as e:
            print(f"  {stem}: exc {e}"); continue
        summ = _resource_summary(details)
        row = dict(instance=stem, w_net=ln, w_flow=lf, solver=m["solver"],
                   r_tr_arc=r_tr, r_resource=r_res, **summ)
        rows.append(row)
        print(f"{stem:24s}{ln:>6}{lf:>7}{r_tr:>10}{r_res:>11}"
              f"{summ.get('nri_resource'):>9}{summ.get('cvar_resource'):>9}"
              f"{str(summ.get('worst_res')):>11}{summ.get('n_resources'):>5}")

    out = RES / "resource_resilience.csv"
    fields = ["instance", "solver", "w_net", "w_flow", "r_tr_arc", "r_resource",
              "nri_resource", "cvar_resource", "worst_res_frac", "worst_res", "n_resources"]
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"\n-> {out}  ({len(rows)} flows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
