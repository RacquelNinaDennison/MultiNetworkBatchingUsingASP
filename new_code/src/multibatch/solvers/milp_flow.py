"""MILP flow oracle for the network level (Stage 1), with ASP packing (Stage 2).

The ASP/clingcon Stage-1 network flow does not scale to industry instances (on
`industry_test_1.lp` it cannot even reach a feasible flow). This solver replaces
ONLY Stage 1 with an OR-Tools MILP and inherits the real ASP Stage-2 packing
unchanged, so the comparison is apples-to-apples: only the flow solver changes.

The MILP mirrors `encodings/twostage/clingcon/stage_1_clingcon_flow.lp` exactly:

  * possibleFlow(F,T,TR,P): route(F,T,TR,..) ∧ partTR(P,TR) ∧ sizeS(P) < capS(TR)
  * flow conservation per (part, location): inflow - outflow = demand - offer
  * feasibility envelope (70% utilisation):  10·Σ sizeS·flow ≤ 7·capS·nb_trips
  * nb_trips ∈ [0, max_freq]
  * objective: minimise Σ route_cost · nb_trips  (+ weight · #highExposure)

Run modes:
    # MILP flow only (also prints the per-arc profile)
    uv run python -m multibatch.solvers.milp_flow <instance.lp> --mode stage1
    # MILP flow + ASP resilient packing
    uv run python -m multibatch.solvers.milp_flow <instance.lp> --mode full
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..models import (
    Instance,
    RouteFreq,
    SolveMetadata,
    Stage1Result,
    Stage2Result,
    TwoStageClingconConfig,
    TwoStageResult,
)
from .twostage_clingcon import ENCODING_DIR, ClingconTwoStageSolver

try:
    from ortools.linear_solver import pywraplp
except ImportError:  # pragma: no cover
    pywraplp = None


# ─────────────────────────────────────────────────────────────────────────────
# The MILP model
# ─────────────────────────────────────────────────────────────────────────────


def solve_milp_flow(
    instance: Instance,
    *,
    max_freq: int = 20,
    weight: int = 0,
    exposure_n: int = 3,
    cap_size_divide: int = 1,
    time_limit: int = 300,
    backend: str = "SCIP",
    flow_redundancy_weight: int = 0,
) -> dict | None:
    """Solve the Stage-1 network flow as a MILP. Returns a dict mirroring the
    clingcon Stage-1 output, or None if no feasible flow was found."""
    if pywraplp is None:
        raise RuntimeError("ortools is required: `uv add ortools`")

    t_build = time.perf_counter()
    solver = pywraplp.Solver.CreateSolver(backend) or pywraplp.Solver.CreateSolver("CBC")
    if solver is None:
        raise RuntimeError(f"Could not create MILP solver backend '{backend}'")

    # Scaled capacities / sizes (cap_size_divide matches the encoding; default 1).
    cap_s = {tr: c // cap_size_divide for tr, c in instance.transport_capacity.items()}
    size_s = {p: s // cap_size_divide for p, s in instance.part_size.items()}

    # totalSupply(P) = Σ positive demandOffer for P.
    total_supply: dict[str, int] = defaultdict(int)
    for (p, _loc), v in instance.offers.items():
        total_supply[p] += v

    # net required per (part, location) = demand - offer  (requiredNet in the .lp)
    demand = instance.demands   # (part, loc) -> positive demand
    offer = instance.offers     # (part, loc) -> positive supply

    parts_for_tr: dict[str, set[str]] = defaultdict(set)
    for p, tr in instance.part_transport:
        parts_for_tr[tr].add(p)

    route_cost: dict[tuple[str, str, str], int] = {}

    # Decision variables.
    flow: dict[tuple[str, str, str, str], Any] = {}
    arc_parts: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    inflow_idx: dict[tuple[str, str], list] = defaultdict(list)   # (part, loc) -> vars arriving at loc
    outflow_idx: dict[tuple[str, str], list] = defaultdict(list)  # (part, loc) -> vars leaving loc

    for r in instance.routes:
        tr = r.transport
        cap_tr = cap_s.get(tr)
        if cap_tr is None:
            continue
        arc = (r.origin, r.destination, tr)
        route_cost[arc] = r.cost
        for p in parts_for_tr.get(tr, ()):
            if size_s.get(p, 10**9) < cap_tr:  # part physically fits (strict, matches S < Cap)
                ub = total_supply.get(p, 0)
                if ub <= 0:
                    continue
                v = solver.IntVar(0, ub, f"flow_{r.origin}_{r.destination}_{tr}_{p}")
                flow[(r.origin, r.destination, tr, p)] = v
                arc_parts[arc].append(p)
                inflow_idx[(p, r.destination)].append(v)
                outflow_idx[(p, r.origin)].append(v)

    nb_trips = {arc: solver.IntVar(0, max_freq, f"trips_{arc[0]}_{arc[1]}_{arc[2]}")
                for arc in arc_parts}

    # Flow conservation: inflow - outflow = net, for every (part, loc) that is
    # touched by a variable OR has nonzero net (the latter catches infeasibility).
    keys = set(inflow_idx) | set(outflow_idx)
    for p in instance.parts:
        for loc in instance.locations:
            if demand.get((p, loc), 0) - offer.get((p, loc), 0) != 0:
                keys.add((p, loc))
    for (p, loc) in keys:
        net = demand.get((p, loc), 0) - offer.get((p, loc), 0)
        solver.Add(solver.Sum(inflow_idx.get((p, loc), []))
                   - solver.Sum(outflow_idx.get((p, loc), [])) == net)

    # Feasibility envelope (70% utilisation): 10·Σ sizeS·flow ≤ 7·capS·nb_trips.
    for arc, ps in arc_parts.items():
        cap_tr = cap_s[arc[2]]
        vol = solver.Sum(10 * size_s[p] * flow[(arc[0], arc[1], arc[2], p)] for p in ps)
        solver.Add(vol <= 7 * cap_tr * nb_trips[arc])

    # Optional exposure penalty (only when weight > 0; default oracle uses 0).
    he_vars: dict = {}
    if weight > 0:
        for key, v in flow.items():
            ts = total_supply.get(key[3], 0)
            if ts <= 0:
                continue
            b = solver.IntVar(0, 1, f"he_{key[0]}_{key[1]}_{key[2]}_{key[3]}")
            # exposure_n·flow > ts  forces b = 1
            solver.Add(exposure_n * v <= ts + exposure_n * ts * b)
            he_vars[key] = b

    # Optional network-level redundancy term (w_flow): softly push every ACTIVE
    # arc toward >= 2 trips, creating multi-trip arcs that (a) reduce single-trip
    # SPOFs and (b) give the ASP packing trips to redistribute across. Only added
    # when flow_redundancy_weight > 0 (keeps the base MILP small/fast).
    under2_vars: dict = {}
    if flow_redundancy_weight > 0:
        for arc in arc_parts:
            active = solver.IntVar(0, 1, f"active_{arc[0]}_{arc[1]}_{arc[2]}")
            solver.Add(nb_trips[arc] >= active)                 # active=0 => nb_trips=0
            solver.Add(nb_trips[arc] <= max_freq * active)      # nb_trips>=1 => active=1
            u = solver.NumVar(0, max_freq, f"under2_{arc[0]}_{arc[1]}_{arc[2]}")
            solver.Add(u >= 2 * active - nb_trips[arc])         # u = max(0, 2*active - nb_trips)
            under2_vars[arc] = u

    obj = solver.Sum(route_cost[arc] * nb_trips[arc] for arc in arc_parts)
    if weight > 0:
        obj = obj + weight * solver.Sum(he_vars.values())
    if flow_redundancy_weight > 0:
        obj = obj + flow_redundancy_weight * solver.Sum(under2_vars.values())
    solver.Minimize(obj)

    build_time = time.perf_counter() - t_build
    n_vars, n_cons = solver.NumVariables(), solver.NumConstraints()

    solver.SetTimeLimit(time_limit * 1000)
    t_solve = time.perf_counter()
    status = solver.Solve()
    solve_time = time.perf_counter() - t_solve

    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return None

    loads = {
        k: round(v.solution_value())
        for k, v in flow.items()
        if v.solution_value() > 0.5
    }
    route_freqs = []
    for arc, tvar in nb_trips.items():
        fr = round(tvar.solution_value())
        if fr > 0:
            route_freqs.append({"from": arc[0], "to": arc[1], "tr": arc[2],
                                "freq": fr, "total_cap": fr * cap_s[arc[2]]})

    # high_exposure recomputed from the flow (so it is populated even at weight=0)
    high_exposure = [
        k for k, n in loads.items()
        if total_supply.get(k[3], 0) > 0 and exposure_n * n > total_supply[k[3]]
    ]

    return {
        "loads": loads,
        "route_freqs": route_freqs,
        "high_exposure": high_exposure,
        "cost": round(solver.Objective().Value()),
        "optimum": status == pywraplp.Solver.OPTIMAL,
        "build_time": round(build_time, 3),
        "solve_time": round(solve_time, 3),
        "n_vars": n_vars,
        "n_cons": n_cons,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Solver: MILP Stage 1 + inherited ASP Stage 2
# ─────────────────────────────────────────────────────────────────────────────


class MilpFlowTwoStageSolver(ClingconTwoStageSolver):
    """MILP network flow (Stage 1) + ASP resilient packing (Stage 2).

    Overrides ONLY `_solve_stage1`; `_solve_stage2`, `_build_stage2_facts`, and
    the Stage-1→Stage-2 contract are inherited from ClingconTwoStageSolver.
    """

    def __init__(
        self,
        instance_path,
        config: TwoStageClingconConfig | None = None,
        backend: str = "SCIP",
        flow_time_limit: int = 300,
        flow_redundancy_weight: int = 0,
        stage2_encoding=None,
    ):
        super().__init__(instance_path, config=config, stage2_encoding=stage2_encoding)
        self.backend = backend
        self.flow_time_limit = flow_time_limit
        self.flow_redundancy_weight = flow_redundancy_weight

    def _solve_stage1(self) -> Stage1Result | None:
        sol = solve_milp_flow(
            self.instance,
            max_freq=self.config.max_freq,
            weight=self.config.weight,
            exposure_n=self.config.exposure_n,
            cap_size_divide=self.config.cap_size_divide,
            time_limit=self.flow_time_limit,
            backend=self.backend,
            flow_redundancy_weight=self.flow_redundancy_weight,
        )
        if sol is None:
            return None

        route_freqs = [
            RouteFreq(origin=rf["from"], destination=rf["to"], transport=rf["tr"],
                      frequency=rf["freq"], total_capacity=rf["total_cap"])
            for rf in sol["route_freqs"]
        ]
        return Stage1Result(
            metadata=SolveMetadata(
                ground_time=sol["build_time"],
                solve_time=sol["solve_time"],
                total_time=round(sol["build_time"] + sol["solve_time"], 3),
                optimum=sol["optimum"],
                satisfiable=True,
                cost=sol["cost"],
                atoms=sol["n_vars"],          # reuse 'atoms' column for MILP var count
                conflicts=sol["n_cons"],      # and 'conflicts' for constraint count
                trajectory=[],
            ),
            loads=sol["loads"],
            route_freqs=route_freqs,
            high_exposure=sol["high_exposure"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Reporting helpers + CLI
# ─────────────────────────────────────────────────────────────────────────────


def _per_arc_profile(stage1: Stage1Result) -> None:
    import statistics as st

    parts_per_arc: dict[tuple, set] = defaultdict(set)
    units_per_arc: dict[tuple, int] = defaultdict(int)
    for (f, t, tr, part), n in stage1.loads.items():
        parts_per_arc[(f, t, tr)].add(part)
        units_per_arc[(f, t, tr)] += n
    trips = {(rf.origin, rf.destination, rf.transport): rf.frequency for rf in stage1.route_freqs}

    def desc(name, xs):
        if not xs:
            print(f"  {name}: (none)"); return
        xs = sorted(xs)
        p90 = xs[int(0.9 * (len(xs) - 1))]
        print(f"  {name:14s} n={len(xs):<5} min={xs[0]:<5} med={int(st.median(xs)):<5} "
              f"mean={round(st.mean(xs), 1):<7} p90={p90:<5} max={xs[-1]}")

    print(f"\nPer-arc profile ({len(trips)} active arcs):")
    desc("parts/arc", [len(s) for s in parts_per_arc.values()])
    desc("units/arc", list(units_per_arc.values()))
    desc("trips/arc", list(trips.values()))
    n_hot = sum(1 for v in trips.values() if v > 64)
    print(f"  arcs >64 trips (packing watch zone): {n_hot} / {len(trips)}")


def _arc_allocation(stage1: Stage1Result) -> None:
    """Print the explicit per-arc allocation: each active arc with its trips,
    total capacity, and the parts/units routed across it."""
    parts_per_arc: dict[tuple, dict] = defaultdict(dict)
    for (f, t, tr, part), n in stage1.loads.items():
        parts_per_arc[(f, t, tr)][part] = n

    print(f"\nArc allocation ({len(stage1.route_freqs)} active arcs):")
    for rf in sorted(stage1.route_freqs,
                     key=lambda r: (r.origin, r.destination, r.transport)):
        parts = parts_per_arc.get((rf.origin, rf.destination, rf.transport), {})
        units = sum(parts.values())
        util = (100 * units / rf.total_capacity) if rf.total_capacity else 0
        load_str = ", ".join(f"{p}:{n}" for p, n in sorted(parts.items()))
        print(f"  {rf.origin}->{rf.destination} [{rf.transport}]  "
              f"trips={rf.frequency:<3} cap={rf.total_capacity:<5} "
              f"units={units:<5} util={util:>3.0f}%  parts={len(parts):<3} "
              f"{{{load_str}}}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MILP flow oracle (+ ASP packing)")
    p.add_argument("instance")
    p.add_argument("--mode", choices=["stage1", "full"], default="full",
                   help="stage1 = MILP flow only; full = MILP flow + ASP packing")
    p.add_argument("--backend", default="SCIP")
    p.add_argument("--weight", type=int, default=0, help="exposure penalty weight (0 = pure cost)")
    p.add_argument("--exposure-n", type=int, default=3)
    p.add_argument("--max-freq", type=int, default=20)
    p.add_argument("--cap-size-divide", type=int, default=1)
    p.add_argument("--flow-time-limit", type=int, default=300)
    p.add_argument("--flow-redundancy-weight", type=int, default=0,
                   help="network-level w_flow: push active arcs toward >=2 trips (0=off)")
    # Stage-2 packing options (full mode only)
    p.add_argument("--hetero-on", type=int, default=1)
    p.add_argument("--concentrated-on", type=int, default=1)
    p.add_argument("--w-hetero", type=int, default=1, help="weighted-packing heterogeneity weight")
    p.add_argument("--w-conc", type=int, default=1, help="weighted-packing anti-concentration weight")
    p.add_argument("--weighted-packing", action="store_true",
                   help="use the single-level weighted Stage-2 encoding (w_hetero/w_conc)")
    p.add_argument("--stage2-time-limit", type=int, default=60)
    p.add_argument("--configuration", type=str, default="many")
    p.add_argument("--threads", type=int, default=1)
    args = p.parse_args(argv)

    config = TwoStageClingconConfig(
        weight=args.weight,
        exposure_n=args.exposure_n,
        max_freq=args.max_freq,
        cap_size_divide=args.cap_size_divide,
        time_limit=args.stage2_time_limit,
        hetero_on=args.hetero_on,
        concentrated_on=args.concentrated_on,
        w_hetero=args.w_hetero,
        w_conc=args.w_conc,
        configuration=(args.configuration or None),
        threads=args.threads,
    )
    stage2_enc = (ENCODING_DIR / "stage_2_packing_weighted.lp") if args.weighted_packing else None
    solver = MilpFlowTwoStageSolver(
        args.instance, config=config, backend=args.backend,
        flow_time_limit=args.flow_time_limit,
        flow_redundancy_weight=args.flow_redundancy_weight,
        stage2_encoding=stage2_enc,
    )

    print(f"=== MILP Stage 1 ({args.backend}) on {args.instance} ===")
    stage1 = solver._solve_stage1()
    if stage1 is None:
        print("MILP found NO feasible flow within the time limit.")
        return 1
    m = stage1.metadata
    print(f"  feasible flow found. optimum={m.optimum} cost={m.cost} "
          f"vars={m.atoms} cons={m.conflicts} build={m.ground_time}s solve={m.solve_time}s")
    print(f"  active arcs={len(stage1.route_freqs)} total trips={sum(rf.frequency for rf in stage1.route_freqs)}")
    _per_arc_profile(stage1)
    _arc_allocation(stage1)

    if args.mode == "stage1":
        return 0

    print(f"\n=== ASP Stage 2 packing (hetero={args.hetero_on} concentrated={args.concentrated_on}) ===")
    stage2 = solver._solve_stage2(stage1)
    if stage2 is None:
        print("Stage 2 produced no packing (infeasible or no model in budget).")
        return 1
    m2 = stage2.metadata
    print(f"  packing found. optimum={m2.optimum} cost={m2.cost} "
          f"trips_used={len(stage2.used_trips)} mono={stage2.mono_count} "
          f"concentrated={stage2.concentrated_count} "
          f"first={(m2.trajectory[0]['time'] if m2.trajectory else '-')}s total={m2.total_time}s")
    _ = TwoStageResult(stage1=stage1, stage2=stage2)
    from ..reporting.console import print_stage2_packings
    print_stage2_packings(stage2, solver.instance)
    return 0


if __name__ == "__main__":
    sys.exit(main())
