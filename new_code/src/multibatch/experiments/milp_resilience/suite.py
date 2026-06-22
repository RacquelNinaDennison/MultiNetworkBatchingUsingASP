"""Resilience SUITE harness — calculate & run everything for the thesis claim.

  1. Solves the network flow ONCE per (solver, w_net, w_flow), caching it to
     JSON so the expensive solve is paid once.
  2. Sweeps the Stage-2 packing weights (baseline + w_hetero sweep + w_conc sweep
     + full), using the weighted Stage-2 encoding.
  3. Computes the FULL metric panel per (instance, solver, w_net, w_flow, packing):
       flow-level : R_TR, flow cost, #arcs, total trips, #single-trip arcs
       worst-case : R_1, K_1, R_alpha (single & global, every alpha)
       distribution: coverage mean/median/CVaR10/frac_zero (overall + addressable)
       NRI        : expected demand satisfied (overall + addressable), worst
       cost       : s1/s2 dispatch cost, saving, mono/concentrated counts
     ...and PRINTS every one of them per packing.
  4. Writes one long CSV + an across-suite win-rate summary vs baseline.

Instances are discovered by WILDCARD (like the two-stage experiments) — point at
a directory and glob, optionally filtered by size:

    # all generated layered+industry instances, both solvers:
    uv run python -m multibatch.experiments.milp_resilience.suite \
      -o src/multibatch/experiments/milp_resilience/results/suite.csv

    # only the small/medium sweep (size filter), both solvers, w_net sweep:
    ... --instance-filter small --w-net-grid 0 1 2 4 8

    # explicit globs (small + medium buckets):
    ... --instance-glob 'layered_small_*.lp' 'layered_medium_*.lp'

    # or still hand a literal file / glob via --instances:
    ... --instances 'src/multibatch/instances/generated/layered_small_*.lp'

    # interaction study (does flow-redundancy help packings?, MILP only):
    ... --w-flow-grid 0 20

    # industry (synthesise part values so even/full are active, 600s flow budget):
    ... --instance-filter industry --synth-values size --flow-time-limit 600

    # restrict to one solver if you must:
    ... --flow-solvers asp
"""

from __future__ import annotations

import argparse
import csv
import glob as _glob
import json
import sys
from collections import defaultdict
from itertools import product
from pathlib import Path

from ...metrics.coverage import coverage_report, nri_alpha_from_details
from ...metrics.resilience import compute_r_alpha, compute_r_tr
from ...models import RouteFreq, SolveMetadata, Stage1Result, TwoStageClingconConfig
from ...solvers.milp_flow import ENCODING_DIR, MilpFlowTwoStageSolver
from ...solvers.twostage_clingcon import ClingconTwoStageSolver
from ..twostage.config import ALPHA_VALUES, R_ALPHA_MODES
from ..twostage.runner import _normalizer_from_stage1
from .runner import _synth_values, compute_dispatch_costs

WEIGHTED_ENC = ENCODING_DIR / "stage_2_packing_weighted.lp"

# Instance discovery (mirrors twostage.runner.discover_instances)
_MULTIBATCH = Path(__file__).resolve().parents[2]  # src/multibatch/
INSTANCE_DIR = _MULTIBATCH / "instances" / "generated"
DEFAULT_GLOBS = ["layered_*.lp", "industry_test_*.lp"]

# Solvers iterated by default (ASP two-stage, then the MILP/"MOP" flow solver)
DEFAULT_FLOW_SOLVERS = ["asp", "milp"]

# Full alpha grid: worst-case R_alpha and expected NRI_alpha at every (mode, alpha)
R_ALPHA_COLS = [f"r_alpha_{m}_{a}" for m in R_ALPHA_MODES for a in ALPHA_VALUES]
NRI_ALPHA_COLS = [f"nri_alpha_{m}_{a}" for m in R_ALPHA_MODES for a in ALPHA_VALUES]

CSV_FIELDS = [
    "instance", "flow_solver", "lambda_net", "lambda_flow", "weight_normalizer",
    "w_net", "w_flow", "config", "w_hetero", "w_conc",
    "flow_optimum", "flow_cost", "n_arcs", "total_trips", "n_single_trip_arcs",
    # runtime: s1_time = flow solve (MILP vs ASP, the headline); s2_time = ASP packing
    "s1_time", "s2_time",
    # Stage-1 anytime convergence: first incumbent, best-before-timeout, #improvements
    "s1_first_cost", "s1_first_time", "s1_best_cost", "s1_best_time", "s1_n_improve",
    "s2_optimal", "mono_count", "concentrated_count",
    "r_tr", *R_ALPHA_COLS,
    "cov_mean", "cov_median", "cov_cvar10", "cov_frac_zero", "cov_dw_mean",
    "cov_mean_addr", "cov_cvar10_addr",
    "nri", "nri_worst", "nri_addr", *NRI_ALPHA_COLS,
    "s1_dispatch_cost", "s2_dispatch_cost", "cost_saving",
    # full (time, cost) horizon as JSON — the convergence curve; kept last (wide)
    "s1_trajectory",
]


# ── flow cache I/O ──────────────────────────────────────────────────────

def _dump_flow(stage1: Stage1Result, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    m = stage1.metadata
    path.write_text(json.dumps({
        "loads": {",".join(k): v for k, v in stage1.loads.items()},
        "route_freqs": [rf.model_dump() for rf in stage1.route_freqs],
        "optimum": m.optimum, "cost": m.cost,
        # persist timing + convergence trace so a cached re-run still reports the
        # real flow solve time and the anytime (time, cost) horizon
        "ground_time": m.ground_time, "solve_time": m.solve_time, "total_time": m.total_time,
        "trajectory": m.trajectory,
    }))


def _load_flow(path: Path) -> Stage1Result:
    d = json.loads(path.read_text())
    return Stage1Result(
        metadata=SolveMetadata(
            satisfiable=True, optimum=d.get("optimum", False), cost=d.get("cost"),
            ground_time=d.get("ground_time", 0.0), solve_time=d.get("solve_time", 0.0),
            total_time=d.get("total_time", 0.0), trajectory=d.get("trajectory", [])),
        loads={tuple(k.split(",")): v for k, v in d["loads"].items()},
        route_freqs=[RouteFreq(**rf) for rf in d["route_freqs"]],
        high_exposure=[],
    )


# ── metric panel ────────────────────────────────────────────────────────

def _metric_panel(stage1, stage2, instance, r_tr) -> dict:
    row = {"r_tr": r_tr}
    try:
        # One max-flow pass per (mode, alpha) yields BOTH the worst-case R_alpha
        # and the expected NRI_alpha (sibling sweep, expectation vs min).
        for m in R_ALPHA_MODES:
            for a in ALPHA_VALUES:
                ra, details = compute_r_alpha(
                    stage1, stage2, instance, alpha=a, mode=m, strategy="heaviest")
                row[f"r_alpha_{m}_{a}"] = ra
                row[f"nri_alpha_{m}_{a}"] = nri_alpha_from_details(details, m)
    except Exception as e:
        print(f"    R_alpha/NRI_alpha exc: {e}")
    try:
        rep = coverage_report(stage1, stage2, instance)
        ov, ad = rep["overall"], rep["packing_addressable"]
        row.update(cov_mean=ov.get("mean"), cov_median=ov.get("median"),
                   cov_cvar10=ov.get("cvar10"), cov_frac_zero=ov.get("frac_zero"),
                   cov_dw_mean=ov.get("demand_weighted_mean"),
                   cov_mean_addr=ad.get("mean"), cov_cvar10_addr=ad.get("cvar10"),
                   nri=rep["nri"]["nri"], nri_worst=rep["nri"]["nri_worst"],
                   nri_addr=rep["nri_addressable"]["nri"])
    except Exception as e:
        print(f"    coverage/NRI exc: {e}")
    try:
        c = compute_dispatch_costs(stage1, stage2, instance)
        row.update(s1_dispatch_cost=c["s1_dispatch_cost"], s2_dispatch_cost=c["s2_dispatch_cost"],
                   cost_saving=c["cost_saving"])
    except Exception as e:
        print(f"    dispatch exc: {e}")
    return row


def _trajectory_fields(stage1) -> dict:
    """Stage-1 anytime convergence: first incumbent, best-before-timeout, and the
    full (time, cost) horizon.

    The ASP/clingcon solver records a model every time it improves the bound, so
    the trace shows whether cost converged early or kept improving up to the wall.
    The MILP backend (pywraplp) exposes only the FINAL incumbent, so we fall back
    to a single point (first == best == final) for it.
    """
    m = stage1.metadata
    traj = m.trajectory or []
    if traj:
        first, best = traj[0], traj[-1]
        return {
            "s1_first_cost": first.get("cost"), "s1_first_time": first.get("time"),
            "s1_best_cost": best.get("cost"), "s1_best_time": best.get("time"),
            "s1_n_improve": len(traj), "s1_trajectory": json.dumps(traj),
        }
    return {
        "s1_first_cost": m.cost, "s1_first_time": m.total_time,
        "s1_best_cost": m.cost, "s1_best_time": m.total_time,
        "s1_n_improve": 0, "s1_trajectory": json.dumps([]),
    }


def _print_all_metrics(row: dict) -> None:
    """Print the FULL metric panel for one packing row — every metric, grouped."""
    def g(*keys):
        return "  ".join(f"{k}={row.get(k)}" for k in keys)
    print(f"      time      : {g('s1_time', 's2_time')}  flow_optimum={row.get('flow_optimum')}")
    print(f"      converge  : first={row.get('s1_first_cost')}@{row.get('s1_first_time')}s "
          f"best={row.get('s1_best_cost')}@{row.get('s1_best_time')}s n_improve={row.get('s1_n_improve')}")
    print(f"      flow      : {g('r_tr', 'flow_cost', 'n_arcs', 'total_trips', 'n_single_trip_arcs')}")
    for m in R_ALPHA_MODES:
        cells = "  ".join(f"a{a}={row.get(f'r_alpha_{m}_{a}')}" for a in ALPHA_VALUES)
        print(f"      r_alpha[{m:6s}] : {cells}")
    print(f"      coverage  : {g('cov_mean', 'cov_median', 'cov_cvar10', 'cov_frac_zero', 'cov_dw_mean', 'cov_mean_addr', 'cov_cvar10_addr')}")
    print(f"      nri       : {g('nri', 'nri_worst', 'nri_addr')}")
    for m in R_ALPHA_MODES:
        cells = "  ".join(f"a{a}={row.get(f'nri_alpha_{m}_{a}')}" for a in ALPHA_VALUES)
        print(f"        nri_alpha[{m:6s}] : {cells}")
    print(f"      cost      : {g('s1_dispatch_cost', 's2_dispatch_cost', 'cost_saving', 'mono_count', 'concentrated_count')}")


def _packing_combos(wh_grid, wc_grid) -> list[tuple[str, int, int]]:
    """baseline + one-at-a-time hetero sweep + conc sweep + full(max,max)."""
    combos = [("baseline", 0, 0)]
    combos += [(f"hetero_w{wh}", wh, 0) for wh in wh_grid if wh > 0]
    combos += [(f"conc_w{wc}", 0, wc) for wc in wc_grid if wc > 0]
    if wh_grid and wc_grid:
        combos.append((f"full_w{max(wh_grid)}_{max(wc_grid)}", max(wh_grid), max(wc_grid)))
    return combos


# ── instance discovery (wildcard, mirrors twostage.runner) ──────────────

def discover_instances(instance_dir: Path, globs: list[str], instance_filter: str | None) -> list[Path]:
    """Glob instance files under `instance_dir`, optionally substring-filtered."""
    paths: list[Path] = []
    for pat in globs:
        paths += instance_dir.glob(pat)
    paths = sorted(set(paths))
    if instance_filter:
        paths = [p for p in paths if instance_filter in p.stem]
    return paths


def resolve_instances(args) -> list[Path]:
    """Explicit --instances (literal paths or glob patterns) override discovery."""
    if args.instances:
        out: list[str] = []
        for item in args.instances:
            matches = _glob.glob(item)
            if matches:
                out += matches
            else:
                print(f"  [warn] no instance matched: {item}")
        return [Path(p) for p in sorted(set(out))]
    return discover_instances(args.instance_dir, args.instance_glob, args.instance_filter)


# ── solver construction + cached flow solve ────────────────────────────

def _build_solver(args, inst_path, weight_abs: int, w_flow_abs: int):
    """Build the flow+packing solver with absolute network weights applied."""
    cfg = TwoStageClingconConfig(
        weight=weight_abs, max_freq=20, cap_size_divide=1,
        time_limit=args.stage2_time_limit, round_timeout=args.stage2_time_limit,
        configuration=args.configuration,
    )
    if args.flow_solver == "milp":
        solver = MilpFlowTwoStageSolver(
            inst_path, config=cfg, backend=args.backend,
            flow_time_limit=args.flow_time_limit,
            flow_redundancy_weight=w_flow_abs, stage2_encoding=WEIGHTED_ENC)
    else:
        solver = ClingconTwoStageSolver(inst_path, config=cfg, stage2_encoding=WEIGHTED_ENC)
    _synth_values(solver.instance, args.synth_values)
    return solver


def _solve_or_load(solver, cache_path: Path, args, label: str):
    if cache_path.exists():
        print(f"[{label}] flow from cache")
        return _load_flow(cache_path)
    print(f"[{label}] solving flow ({args.flow_solver})...")
    if args.flow_solver == "asp":
        # clingcon shares config.time_limit across stages: give the flow its own
        # budget, then restore the packing budget afterwards.
        solver.config.time_limit = args.flow_time_limit
        solver.config.round_timeout = args.flow_time_limit
    stage1 = solver._solve_stage1()
    solver.config.time_limit = args.stage2_time_limit
    solver.config.round_timeout = args.stage2_time_limit
    if stage1 is not None:
        _dump_flow(stage1, cache_path)
    return stage1


# ── per-(instance, solver) run ──────────────────────────────────────────

def run_solver_on_instance(args, inst_path, flow_solver: str, combos, cache: Path,
                           writer, fh) -> list[dict]:
    """Sweep flow weights x packing weights for ONE (instance, solver).

    For each network weighting it re-solves the flow (cached), records R_TR, then
    runs the full packing sweep and prints every metric. Returns the rows written.
    """
    args.flow_solver = flow_solver  # config bag: _build_solver/_solve_or_load read it
    rows: list[dict] = []
    stem = Path(inst_path).stem
    # w_flow (flow-redundancy) is MILP-only; ASP forces it to the single 0 point.
    w_flow_grid = args.w_flow_grid if flow_solver == "milp" else [0]

    # Cost-optimal flow (lambda=0) once -> normaliser for relative weights.
    norm_solver = _build_solver(args, inst_path, 0, 0)
    norm_cache = cache / f"flow_{flow_solver}_ln0.0_lf0.0_{stem}.json"
    norm_flow = _solve_or_load(norm_solver, norm_cache, args, f"{stem}/{flow_solver} ln=0 lf=0")
    if norm_flow is None:
        print(f"  [{flow_solver}] NO feasible flow; skipping (increase --flow-time-limit).")
        return rows
    normalizer = _normalizer_from_stage1(norm_flow, norm_solver.instance) or 1.0
    print(f"  [{flow_solver}] normaliser (mean dispatch cost / trip, cost-optimal) = {round(normalizer, 2)}")

    for lam_net, lam_flow in product(args.w_net_grid, w_flow_grid):
        # Relative weights: absolute encoding weight = round(lambda x normaliser).
        w_net_abs = round(lam_net * normalizer)
        w_flow_abs = round(lam_flow * normalizer)
        if lam_net == 0 and lam_flow == 0:
            solver, stage1 = norm_solver, norm_flow
        else:
            solver = _build_solver(args, inst_path, w_net_abs, w_flow_abs)
            cpath = cache / f"flow_{flow_solver}_ln{lam_net}_lf{lam_flow}_{stem}.json"
            stage1 = _solve_or_load(solver, cpath, args, f"{stem}/{flow_solver} ln={lam_net} lf={lam_flow}")
            if stage1 is None:
                continue

        arc_freq = {(rf.origin, rf.destination, rf.transport): rf.frequency
                    for rf in stage1.route_freqs}
        n_single = sum(1 for v in arc_freq.values() if v == 1)
        try:
            r_tr = compute_r_tr(stage1, solver.instance)[0]
        except Exception as e:
            print(f"  R_TR exc: {e}"); r_tr = None
        flow_fields = {
            "instance": stem, "flow_solver": flow_solver,
            "lambda_net": lam_net, "lambda_flow": lam_flow,
            "weight_normalizer": round(normalizer, 2),
            "w_net": w_net_abs, "w_flow": w_flow_abs,
            "flow_optimum": stage1.metadata.optimum, "flow_cost": stage1.metadata.cost,
            "n_arcs": len(stage1.route_freqs),
            "total_trips": sum(arc_freq.values()), "n_single_trip_arcs": n_single,
            "s1_time": stage1.metadata.total_time,  # flow solve time: MILP vs ASP
        }
        flow_fields.update(_trajectory_fields(stage1))
        print(f"  [{flow_solver}] ln={lam_net} lf={lam_flow} (w_net={w_net_abs} w_flow={w_flow_abs}): "
              f"arcs={flow_fields['n_arcs']} trips={flow_fields['total_trips']} "
              f"single={n_single} R_TR={r_tr} s1_time={stage1.metadata.total_time}s "
              f"flow_optimum={stage1.metadata.optimum}")
        print(f"      convergence: first={flow_fields['s1_first_cost']}@{flow_fields['s1_first_time']}s "
              f"-> best={flow_fields['s1_best_cost']}@{flow_fields['s1_best_time']}s "
              f"improvements={flow_fields['s1_n_improve']} budget={stage1.metadata.total_time}s "
              f"(optimum={stage1.metadata.optimum})")

        if args.flow_only:
            # Flow-level only: R_TR is determined by the flow, independent
            # of packing. Record one row per (w_net, w_flow) and move on.
            row = dict(flow_fields)
            row.update(config="(flow)", w_hetero=0, w_conc=0, r_tr=r_tr)
            writer.writerow(row); fh.flush()
            rows.append(row)
            print(f"    (flow)         s1_time={row.get('s1_time')}s R_TR={r_tr}")
            continue

        # ── packing weight sweep ──
        for name, wh, wc in combos:
            solver.config.w_hetero = wh
            solver.config.w_conc = wc
            stage2 = solver._solve_stage2(stage1)
            row = dict(flow_fields)
            row.update(config=name, w_hetero=wh, w_conc=wc)
            if stage2 is None:
                row["s2_optimal"] = "UNSAT"
                writer.writerow(row); fh.flush()
                rows.append(row)
                print(f"    {name:14s} wh={wh} wc={wc} -> UNSAT")
                continue
            row.update(s2_optimal=stage2.metadata.optimum,
                       s2_time=stage2.metadata.total_time,
                       mono_count=stage2.mono_count,
                       concentrated_count=stage2.concentrated_count)
            row.update(_metric_panel(stage1, stage2, solver.instance, r_tr))
            writer.writerow(row); fh.flush()
            rows.append(row)
            print(f"    {name:14s} wh={wh} wc={wc}  s2_optimal={row.get('s2_optimal')}")
            _print_all_metrics(row)
    return rows


# ── main ────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Resilience suite harness")
    p.add_argument("--instances", nargs="*", default=None,
                   help="explicit instance paths or glob patterns; overrides "
                        "--instance-dir/--instance-glob discovery")
    p.add_argument("--instance-dir", type=Path, default=INSTANCE_DIR,
                   help="directory globbed for instances when --instances is omitted")
    p.add_argument("--instance-glob", nargs="+", default=DEFAULT_GLOBS,
                   help="glob patterns within --instance-dir (e.g. 'layered_small_*.lp')")
    p.add_argument("--instance-filter", default=None,
                   help="keep only discovered instances whose name contains this "
                        "string (e.g. 'small', 'medium', 'industry')")
    p.add_argument("--flow-solvers", nargs="+", choices=["milp", "asp"],
                   default=DEFAULT_FLOW_SOLVERS,
                   help="solvers to iterate over (default: both ASP and MILP/MOP)")
    p.add_argument("--w-hetero-grid", nargs="+", type=int, default=[0, 1, 2, 4, 8, 16])
    p.add_argument("--w-conc-grid", nargs="+", type=int, default=[0, 1, 2, 4, 8, 16])
    p.add_argument("--w-flow-grid", nargs="+", type=float, default=[0.0],
                   help="RELATIVE MILP flow-redundancy weights (lambda; abs = round(lambda x cost/trip)); >1 value = interaction study")
    p.add_argument("--w-net-grid", nargs="+", type=float, default=[0.0],
                   help="RELATIVE network exposure weights (lambda; abs = round(lambda x cost/trip)); sweep to test R_TR")
    p.add_argument("--flow-only", action="store_true",
                   help="skip the packing sweep; record flow-level metrics (R_TR) only")
    p.add_argument("--synth-values", choices=["none", "uniform", "size"], default="none")
    p.add_argument("--backend", default="SCIP")
    p.add_argument("--flow-time-limit", type=int, default=600)
    p.add_argument("--stage2-time-limit", type=int, default=30)
    p.add_argument("--configuration", default="many")
    p.add_argument("--cache-dir", default="src/multibatch/experiments/milp_resilience/results/flows")
    p.add_argument("-o", "--out", default="src/multibatch/experiments/milp_resilience/results/suite.csv")
    args = p.parse_args(argv)

    instances = resolve_instances(args)
    if not instances:
        print("No instances found (check --instance-dir/--instance-glob/--instances).")
        return 1
    combos = _packing_combos(args.w_hetero_grid, args.w_conc_grid)
    cache = Path(args.cache_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    print(f"Instances ({len(instances)}): {[p.stem for p in instances]}")
    print(f"Solvers: {args.flow_solvers}")

    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()

        for inst_path in instances:
            for flow_solver in args.flow_solvers:
                print(f"\n=== {Path(inst_path).stem}  solver={flow_solver} ===")
                rows += run_solver_on_instance(
                    args, inst_path, flow_solver, combos, cache, writer, fh)

    _summary(rows)
    _runtime_summary(rows)
    print(f"\n-> {out}")
    return 0


def _runtime_summary(rows: list[dict]) -> None:
    """Flow solve time per solver per instance — the MILP-vs-ASP speed claim.

    R_TR and flow time are set by Stage 1 alone, so we collapse over packing
    configs: one flow time per (instance, solver, w_net, w_flow).
    """
    if not rows:
        return
    # (instance, solver) -> list of distinct flow solve times (one per flow point)
    seen: dict = {}
    for r in rows:
        fk = (r["instance"], r.get("flow_solver"), r.get("lambda_net"), r.get("lambda_flow"))
        if fk in seen or r.get("s1_time") is None:
            continue
        seen[fk] = (r["instance"], r.get("flow_solver"), float(r["s1_time"]),
                    r.get("flow_optimum"))
    times: dict = defaultdict(list)   # (instance, solver) -> [s1_time, ...]
    proved: dict = defaultdict(lambda: [0, 0])  # (instance, solver) -> [n_optimum, n]
    for inst, solver, t, opt in seen.values():
        times[(inst, solver)].append(t)
        proved[(inst, solver)][1] += 1
        proved[(inst, solver)][0] += int(bool(opt))
    print("\n=== FLOW SOLVE-TIME (MILP vs ASP) ===")
    instances = sorted({k[0] for k in times})
    for inst in instances:
        cells = []
        for solver in ("milp", "asp"):
            ts = times.get((inst, solver))
            if not ts:
                continue
            no, n = proved[(inst, solver)]
            cells.append(f"{solver}: mean={sum(ts) / len(ts):.2f}s "
                         f"max={max(ts):.2f}s opt={no}/{n}")
        m, a = times.get((inst, "milp")), times.get((inst, "asp"))
        speed = (f"  speedup(asp/milp)x{(sum(a) / len(a)) / (sum(m) / len(m)):.1f}"
                 if m and a and sum(m) else "")
        print(f"  {inst:28s} " + "   ".join(cells) + speed)


def _summary(rows: list[dict]) -> None:
    """Across-suite win-rate vs baseline on NRI and CVaR10 (per solver+flow group)."""
    if not rows:
        return
    # (instance, solver, lambda_net, lambda_flow) -> {config: row}: baselines
    # never cross solvers or flow weightings.
    groups: dict = defaultdict(dict)
    for r in rows:
        key = (r["instance"], r.get("flow_solver"), r.get("lambda_net"), r.get("lambda_flow"))
        groups[key][r["config"]] = r
    print("\n=== ACROSS-SUITE SUMMARY (win = beats baseline) ===")
    for metric in ("nri", "cov_cvar10", "nri_addr", "cov_cvar10_addr"):
        wins: dict = defaultdict(lambda: [0, 0, 0.0])  # config -> [wins, n, sumDelta]
        for cfgs in groups.values():
            base = cfgs.get("baseline", {}).get(metric)
            if base is None:
                continue
            for name, r in cfgs.items():
                if name == "baseline" or r.get(metric) is None:
                    continue
                d = r[metric] - base
                wins[name][1] += 1
                wins[name][0] += int(d > 1e-9)
                wins[name][2] += d
        print(f"\n  {metric}:")
        for name in sorted(wins):
            w, n, sd = wins[name]
            print(f"    {name:16s} wins {w}/{n}  meanΔ={sd / n:+.4f}" if n else f"    {name}: n/a")


if __name__ == "__main__":
    sys.exit(main())
