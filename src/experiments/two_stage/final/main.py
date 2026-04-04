#!/usr/bin/env python3
"""
run_pipeline.py
===============
Sweeps div_weight across a range, and for each weight:
  Step 1 — Solve Stage 1 with that div_weight
  Step 2 — Compute R_TR via max-flow → find worst (F,T,TR) arc
  Save the results to a CSV which will be used to plot results 

Usage
-----
    python run_pipeline.py --instances instances/data.lp
    python run_pipeline.py --instances instances/data.lp \
        --weights 0 50 100 200 500 1000 \
        --time-limit 60 --output results/experiment.csv
"""

from __future__ import annotations

import argparse
import csv
import time
import threading
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory

# ── File paths ──────────────────────────────────────────────────────────────
BASE   = Path(__file__).parent
STAGE1 = BASE / "encodings" / "stage_1_flow.lp"
STAGE2 = BASE / "encodings" / "stage2_packing.lp"
MINMAX = BASE / "encodings" / "min_max.lp"


# ═══════════════════════════════════════════════════════════════════════════
# Instance parsing
# ═══════════════════════════════════════════════════════════════════════════

def parse_instance(path: str) -> dict:
    ctl = clingo.Control()
    ctl.load(str(path))
    ctl.ground([("base", [])])

    data = {
        "demands":       {},
        "offers":        {},
        "transport_cap": {},
        "part_size":     {},
        "part_val":      {},
        "routes":        {},
        "parts":         set(),
        "locations":     set(),
    }

    for atom in ctl.symbolic_atoms:
        sym  = atom.symbol
        name = sym.name
        args = sym.arguments

        if name == "demandOffer" and len(args) == 3:
            part, loc, val = str(args[0]), str(args[1]), args[2].number
            if val < 0:
                data["demands"][(part, loc)] = -val
            elif val > 0:
                data["offers"][(part, loc)] = val
        elif name == "transportCapacity" and len(args) == 2:
            data["transport_cap"][str(args[0])] = args[1].number
        elif name == "partSize" and len(args) == 2:
            data["part_size"][str(args[0])] = args[1].number
        elif name == "partVal" and len(args) == 2:
            data["part_val"][str(args[0])] = args[1].number
        elif name == "route" and len(args) == 5:
            f, t, tr = str(args[0]), str(args[1]), str(args[2])
            data["routes"][(f, t, tr)] = (args[3].number, args[4].number)
        elif name == "part" and len(args) == 1:
            data["parts"].add(str(args[0]))
        elif name == "location" and len(args) == 1:
            data["locations"].add(str(args[0]))

    return data


# ═══════════════════════════════════════════════════════════════════════════
# Stage 1 solver
# ═══════════════════════════════════════════════════════════════════════════

def _extract_s1(model: clingo.Model, theory: ClingconTheory) -> dict:
    route_freqs = []
    dominant    = []
    static_facts  = {         
        "maxItemsPerTrip": [],
        "requiredNet":     [],
        "tRCapSmall":      [],
        "partSizeSmall":   [],
        "totalSupply":     [],
    }
    for sym in model.symbols(shown=True):
        if sym.name == "routeFreq" and len(sym.arguments) == 5:
            a = sym.arguments
            route_freqs.append({
                "from": str(a[0]), "to": str(a[1]), "tr": str(a[2]),
                "freq": a[3].number, "total_cap": a[4].number,
            })
        # Collect dominantTR atoms to count load imbalance
        if sym.name == "dominantTR" and len(sym.arguments) == 3:
            a = sym.arguments
            dominant.append((str(a[0]), str(a[1]), str(a[2])))
        elif sym.name == "maxItemsPerTrip" and len(sym.arguments) == 3:
            static_facts["maxItemsPerTrip"].append(
                (str(sym.arguments[0]), str(sym.arguments[1]), sym.arguments[2].number)
            )
        elif sym.name == "requiredNet" and len(sym.arguments) == 3:
            static_facts["requiredNet"].append(
                (str(sym.arguments[0]), str(sym.arguments[1]), sym.arguments[2].number)
            )
        elif sym.name == "tRCapSmall" and len(sym.arguments) == 2:
            static_facts["tRCapSmall"].append(
                (str(sym.arguments[0]), sym.arguments[1].number)
            )
        elif sym.name == "partSizeSmall" and len(sym.arguments) == 2:
            static_facts["partSizeSmall"].append(
                (str(sym.arguments[0]), sym.arguments[1].number)
            )
        elif sym.name == "totalSupply" and len(sym.arguments) == 2:
            static_facts["totalSupply"].append(
                (str(sym.arguments[0]), sym.arguments[1].number)
            )

    loads = {}
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "load" and len(sym.arguments) == 4 and val > 0:
            key = tuple(str(a) for a in sym.arguments)
            loads[key] = val

    return {
        "route_freqs": route_freqs,
        "loads":       loads,
        "dominant":    dominant,
        "static_facts": static_facts,
    }


def solve_stage1(
    instance_path: str,
    div_weight:    int  = 0,
    time_limit:    int  = 30,
    cap_divide:    int  = 1,
    max_freq:      int  = 20,
) -> dict | None:

    theory = ClingconTheory()
    ctl    = clingo.Control([
        "-c", f"cap_size_divide={cap_divide}",
        "-c", f"max_freq={max_freq}",
        "-c", f"weight={div_weight}",
    ])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_files([str(STAGE1), str(instance_path)], on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    theory.prepare(ctl)

    best      = None
    best_cost = None
    optimum   = False
    trajectory = []   # [(elapsed_seconds, cost)]

    # Bound the combined objective: transCost + div_weight * dominantTR count
    BOUND_TEMPLATE = (
        ":- #sum {{ V,F,T,TR : _transCost(F,T,TR,V); "
        + str(div_weight)
        + ",F,T,P : dominantTR(F,T,P) }} >= {bound}."
    )

    for rnd in range(1, 20):
        elapsed   = time.perf_counter() - t0
        remaining = int(time_limit - elapsed)
        if remaining <= 0:
            break

        print(f"  [S1 w={div_weight} round {rnd}] budget={remaining}s "
              f"best={best_cost}", end="", flush=True)

        timer = threading.Timer(remaining, ctl.interrupt)
        timer.start()
        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    best      = _extract_s1(model, theory)
                    best_cost = model.cost[0] if model.cost else None
                    elapsed_now = round(time.perf_counter() - t0, 3)
                    trajectory.append((elapsed_now, best_cost))
                    print(f" ↓{best_cost}", end="", flush=True)
                    if model.optimality_proven:
                        optimum = True
                        break
                result = handle.get()
        except RuntimeError:
            result = None
        finally:
            timer.cancel()
        print(flush=True)

        if optimum:
            break
        if result is not None and getattr(result, "unsatisfiable", False):
            optimum = True
            break
        if best is None:
            break
        if best_cost is not None:
            ctl.add(f"b{rnd}", [], BOUND_TEMPLATE.format(bound=best_cost))
            ctl.ground([(f"b{rnd}", [])])
        else:
            break

    total = time.perf_counter() - t0
    if best:
        best["cost"]       = best_cost
        best["optimum"]    = optimum
        best["time"]       = round(total, 3)
        best["trajectory"] = trajectory
    return best


# ═══════════════════════════════════════════════════════════════════════════
# R_TR via max-flow
# ═══════════════════════════════════════════════════════════════════════════

def compute_r_tr(loads: dict, instance_data: dict) -> tuple[float, list[dict]]:
    from scipy.sparse.csgraph import maximum_flow
    from scipy.sparse import csr_matrix

    demands = instance_data["demands"]
    offers  = instance_data["offers"]
    parts   = sorted(set(p for (f, t, tr, p) in loads))

    all_locs = sorted(
        set(f for (f, t, tr, p) in loads) |
        set(t for (f, t, tr, p) in loads)
    )
    loc_idx = {loc: i for i, loc in enumerate(all_locs)}
    N       = len(all_locs)
    S_NODE  = N
    T_NODE  = N + 1
    N_NODES = N + 2
    SCALE   = 1000

    total_demand = {
        p: sum(q for (part, loc), q in demands.items() if part == p)
        for p in parts
    }

    active_arcs   = sorted(set((f, t, tr) for (f, t, tr, p) in loads))
    details       = []
    all_coverages = []

    for (lost_f, lost_t, lost_tr) in active_arcs:
        for p in parts:
            if total_demand.get(p, 0) == 0:
                continue

            cap = [[0] * N_NODES for _ in range(N_NODES)]

            for (part, loc), qty in offers.items():
                if part == p and loc in loc_idx:
                    cap[S_NODE][loc_idx[loc]] += int(qty * SCALE)

            for (part, loc), qty in demands.items():
                if part == p and loc in loc_idx:
                    cap[loc_idx[loc]][T_NODE] += int(qty * SCALE)

            for (f, t, tr, part), qty in loads.items():
                if part != p or f not in loc_idx or t not in loc_idx:
                    continue
                
                arc_cap = 0 if (f, t, tr) == (lost_f, lost_t, lost_tr) \
                          else int(qty * SCALE)
                cap[loc_idx[f]][loc_idx[t]] += arc_cap

            flow_val   = maximum_flow(csr_matrix(cap), S_NODE, T_NODE).flow_value
            max_supply = flow_val / SCALE
            coverage   = round(min(max_supply / total_demand[p], 1.0), 4)

            details.append({
                "lost_f":   lost_f,
                "lost_t":   lost_t,
                "lost_tr":  lost_tr,
                "part":     p,
                "max_flow": round(max_supply, 3),
                "demand":   total_demand[p],
                "coverage": coverage,
            })
            all_coverages.append(coverage)

    r_tr = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_tr, details


# ═══════════════════════════════════════════════════════════════════════════
# Stage 2 solver
# ═══════════════════════════════════════════════════════════════════════════

def build_stage2_facts(stage1: dict, instance_data: dict) -> str:
    """Convert Stage 1 results into Stage 2 input facts."""
    lines = []

    for (f, t, tr, p), n in sorted(stage1["loads"].items()):
        lines.append(f"totalLoad({f},{t},{tr},{p},{n}).")

    for tr, cap in sorted(instance_data["transport_cap"].items()):
        lines.append(f"transportCapacity({tr},{cap}).")

    for rf in stage1["route_freqs"]:
        cap = instance_data["transport_cap"].get(rf["tr"], 0)
        lines.append(
            f"activeRoute({rf['from']},{rf['to']},{rf['tr']},"
            f"{rf['freq']},{cap})."
        )

    for p, s in sorted(instance_data["part_size"].items()):
        lines.append(f"partSize({p},{s}).")

    for p, v in sorted(instance_data.get("part_val", {}).items()):
        lines.append(f"partVal({p},{v}).")

    # routeCost for dispatch cost minimisation in Stage 2
    for rf in stage1["route_freqs"]:
        key = (rf["from"], rf["to"], rf["tr"])
        route_info = instance_data["routes"].get(key)
        if route_info:
            _, cost = route_info
            lines.append(f"routeCost({rf['from']},{rf['to']},{rf['tr']},{cost}).")

    return "\n".join(lines)


def compute_dispatch_costs(
    stage1: dict,
    stage2: dict | None,
    instance_data: dict,
) -> dict:
    """Compute Stage 1 planned cost and Stage 2 actual dispatch cost."""

    # Stage 1 cost: freq × cost_per_trip for each active route
    s1_cost = 0
    for rf in stage1["route_freqs"]:
        key = (rf["from"], rf["to"], rf["tr"])
        route_info = instance_data["routes"].get(key)
        if route_info:
            _, cost = route_info
            s1_cost += rf["freq"] * cost

    if stage2 is None:
        return {"s1_dispatch_cost": s1_cost, "s2_dispatch_cost": None, "cost_saving": None}

    # Stage 2 cost: count distinct used trips per route
    from collections import defaultdict
    trips_per_route: dict[tuple, set] = defaultdict(set)
    for (f, t, tr, p, k), n in stage2["trip_loads"].items():
        trips_per_route[(f, t, tr)].add(k)

    s2_cost = 0
    for (f, t, tr), trip_ids in trips_per_route.items():
        route_info = instance_data["routes"].get((f, t, tr))
        if route_info:
            _, cost = route_info
            s2_cost += len(trip_ids) * cost

    return {
        "s1_dispatch_cost": s1_cost,
        "s2_dispatch_cost": s2_cost,
        "cost_saving": s1_cost - s2_cost,
    }


def _extract_stage2(model: clingo.Model, theory: ClingconTheory) -> dict:
    """Extract trip packings and metric atoms from Stage 2 model."""

    trip_loads:       dict[tuple, int] = {}
    trip_part_counts: dict[tuple, int] = {}
    route_part_types: dict[tuple, int] = {}
    mono_trips:       list = []
    concentrated_atoms: list = []

    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "tripLoad" and len(sym.arguments) == 5 and val > 0:
            a = sym.arguments
            key = (str(a[0]), str(a[1]), str(a[2]), str(a[3]), a[4].number)
            trip_loads[key] = val

    for sym in model.symbols(shown=True):
        a = sym.arguments
        if sym.name == "tripPartCount" and len(a) == 5:
            key = (str(a[0]), str(a[1]), str(a[2]), a[3].number)
            trip_part_counts[key] = a[4].number
        elif sym.name == "routePartTypes" and len(a) == 4:
            key = (str(a[0]), str(a[1]), str(a[2]))
            route_part_types[key] = a[3].number
        elif sym.name == "monoTrip" and len(a) == 4:
            mono_trips.append(
                (str(a[0]), str(a[1]), str(a[2]), a[3].number)
            )
        elif sym.name == "concentrated" and len(a) == 5:
            concentrated_atoms.append(
                (str(a[0]), str(a[1]), str(a[2]), str(a[3]), a[4].number)
            )

    return {
        "trip_loads":         trip_loads,
        "trip_part_counts":   trip_part_counts,
        "route_part_types":   route_part_types,
        "mono_count":         len(mono_trips),
        "concentrated_count": len(concentrated_atoms),
    }


def solve_stage2(
    facts_str:       str,
    hetero_on:       int = 1,
    concentrated_on: int = 1,
    time_limit:      int = 30,
) -> dict | None:
    """Solve Stage 2 bin-packing with configurable constraints."""

    theory = ClingconTheory()
    ctl    = clingo.Control([
        "-c", f"hetero_on={hetero_on}",
        "-c", f"concentrated_on={concentrated_on}",
    ])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_string(facts_str, on_rule)
        clingo.ast.parse_files([str(STAGE2)], on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    theory.prepare(ctl)

    best       = None
    optimum    = False
    trajectory = []   # [(elapsed_seconds, cost_vector)]

    timer = threading.Timer(time_limit, ctl.interrupt)
    timer.start()

    try:
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                theory.on_model(model)
                best = _extract_stage2(model, theory)
                cost = list(model.cost) if model.cost else []
                elapsed_now = round(time.perf_counter() - t0, 3)
                trajectory.append((elapsed_now, cost))
                print(f" ↓{cost}", end="", flush=True)
                if model.optimality_proven:
                    optimum = True
                    break
    except RuntimeError:
        pass
    finally:
        timer.cancel()

    total_time = time.perf_counter() - t0
    if best:
        best["optimum"]    = optimum
        best["time"]       = round(total_time, 3)
        best["trajectory"] = trajectory
    print(flush=True)

    return best


# ═══════════════════════════════════════════════════════════════════════════
# R_1 via max-flow (trip-level resilience)
# ═══════════════════════════════════════════════════════════════════════════

def compute_r1(
    trip_loads:    dict,
    loads:         dict,
    instance_data: dict,
) -> tuple[float, list[dict]]:
    """Compute R_1: worst-case coverage under any single trip loss.

    Unlike R_TR (which removes an entire arc-TR), R_1 reduces the arc
    capacity by only the contents of the lost trip.
    """
    from scipy.sparse.csgraph import maximum_flow
    from scipy.sparse import csr_matrix

    demands = instance_data["demands"]
    offers  = instance_data["offers"]
    parts   = sorted(set(p for (f, t, tr, p) in loads))

    all_locs = sorted(
        set(f for (f, t, tr, p) in loads) |
        set(t for (f, t, tr, p) in loads)
    )
    loc_idx = {loc: i for i, loc in enumerate(all_locs)}
    N       = len(all_locs)
    S_NODE  = N
    T_NODE  = N + 1
    N_NODES = N + 2
    SCALE   = 1000

    total_demand = {
        p: sum(q for (part, loc), q in demands.items() if part == p)
        for p in parts
    }

    # Group trip_loads by trip key: (f, t, tr, k) -> {p: qty}
    trips: dict[tuple, dict[str, int]] = {}
    for (f, t, tr, p, k), qty in trip_loads.items():
        trip_key = (f, t, tr, k)
        if trip_key not in trips:
            trips[trip_key] = {}
        trips[trip_key][p] = qty

    details       = []
    all_coverages = []

    for trip_key, trip_contents in trips.items():
        lost_f, lost_t, lost_tr, lost_k = trip_key

        for p in parts:
            td = total_demand.get(p, 0)
            if td == 0:
                continue

            lost_qty = trip_contents.get(p, 0)

            cap = [[0] * N_NODES for _ in range(N_NODES)]

            # Supply arcs: S -> supply locations
            for (part, loc), qty in offers.items():
                if part == p and loc in loc_idx:
                    cap[S_NODE][loc_idx[loc]] += int(qty * SCALE)

            # Demand arcs: demand locations -> T
            for (part, loc), qty in demands.items():
                if part == p and loc in loc_idx:
                    cap[loc_idx[loc]][T_NODE] += int(qty * SCALE)

            # Internal arcs: aggregate loads, reduce disrupted arc by trip contents
            for (f, t, tr, part), qty in loads.items():
                if part != p or f not in loc_idx or t not in loc_idx:
                    continue

                if (f, t, tr) == (lost_f, lost_t, lost_tr):
                    arc_cap = int((qty - lost_qty) * SCALE)
                else:
                    arc_cap = int(qty * SCALE)

                cap[loc_idx[f]][loc_idx[t]] += max(0, arc_cap)

            flow_val   = maximum_flow(csr_matrix(cap), S_NODE, T_NODE).flow_value
            max_supply = flow_val / SCALE
            coverage   = round(min(max_supply / td, 1.0), 4)

            details.append({
                "lost_trip":     f"({lost_f},{lost_t},{lost_tr},k{lost_k})",
                "lost_contents": dict(trip_contents),
                "part":          p,
                "max_flow":      round(max_supply, 3),
                "demand":        td,
                "coverage":      coverage,
            })
            all_coverages.append(coverage)

    r_1 = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_1, details


# ═══════════════════════════════════════════════════════════════════════════
# Build injected facts
# ═══════════════════════════════════════════════════════════════════════════

def build_facts(stage1: dict, worst_arc: tuple) -> str:
    lines = []
    f, t, tr = worst_arc
    lines.append(f"disrupted({f}, {t}, {tr}).")
    lines.append("")

    for (lf, lt, ltr, lp), qty in sorted(stage1["loads"].items()):
        lines.append(f"nominalLoad({lf}, {lt}, {ltr}, {lp}, {qty}).")
    lines.append("")

    lines.append(f"nominalCost({stage1['cost']}).")
    lines.append("")

    sf = stage1["static_facts"]

    for (tr_, p, cap) in sf["maxItemsPerTrip"]:
        lines.append(f"maxItemsPerTrip({tr_}, {p}, {cap}).")
    lines.append("")

    for (p, loc, net) in sf["requiredNet"]:
        lines.append(f"requiredNet({p}, {loc}, {net}).")
    lines.append("")

    for (tr_, cap) in sf["tRCapSmall"]:
        lines.append(f"tRCapSmall({tr_}, {cap}).")
    lines.append("")

    for (p, s) in sf["partSizeSmall"]:
        lines.append(f"partSizeSmall({p}, {s}).")
    lines.append("")

    for (p, sup) in sf["totalSupply"]:
        lines.append(f"totalSupply({p}, {sup}).")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Robust (min-max) solver
# ═══════════════════════════════════════════════════════════════════════════

def _extract_robust(model: clingo.Model, theory: ClingconTheory) -> dict:
    recovery_cost = None
    regret_val    = None

    for sym in model.symbols(shown=True):
        if sym.name == "totalRecoveryCost" and len(sym.arguments) == 1:
            recovery_cost = sym.arguments[0].number
        if sym.name == "regret" and len(sym.arguments) == 1:
            regret_val = sym.arguments[0].number

    loads_d = {}
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "load_d" and len(sym.arguments) == 4:
            key = tuple(str(a) for a in sym.arguments)
            loads_d[key] = val

    # @0 deviation is the sum of hasDevPos + hasDevNeg penalties
    deviation = sum(abs(model.cost[i]) for i in range(len(model.cost)))

    return {
        "recovery_cost": recovery_cost,
        "regret":        regret_val,
        "loads_d":       loads_d,
        "cost_vec":      list(model.cost) if model.cost else [],
    }


def solve_robust(
    instance_path: str,
    facts_str:     str,
    time_limit:    int = 60,
    cap_divide:    int = 1,
    max_freq:      int = 20,
) -> dict | None:

    theory = ClingconTheory()
    ctl    = clingo.Control([
        "-c", f"cap_size_divide={cap_divide}",
        "-c", f"max_freq={max_freq}",
    ])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_files([str(MINMAX), str(instance_path)], on_rule)
        clingo.ast.parse_string(facts_str, on_rule)

    t0 = time.perf_counter()
    print(f"  [Robust] Grounding...")
    ctl.ground([("base", [])])
    print(f"  [Robust] Preparing...")
    theory.prepare(ctl)

    best      = None
    best_cost = None
    optimum   = False

    for rnd in range(1, 30):
        elapsed   = time.perf_counter() - t0
        remaining = int(time_limit - elapsed)
        if remaining <= 0:
            break

        print(f"  [Robust round {rnd}] budget={remaining}s best={best_cost}",
              end="", flush=True)

        timer = threading.Timer(remaining, ctl.interrupt)
        timer.start()
        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    best      = _extract_robust(model, theory)
                    best_cost = list(model.cost) if model.cost else None
                    print(f" ↓{best_cost}", end="", flush=True)
                    if model.optimality_proven:
                        optimum = True
                        break
                result = handle.get()
        except RuntimeError:
            result = None
        finally:
            timer.cancel()
        print(flush=True)

        if optimum:
            break
        if result is not None and getattr(result, "unsatisfiable", False):
            optimum = True
            break
        if best is None:
            break

    total = time.perf_counter() - t0
    if best:
        best["optimum"] = optimum
        best["time"]    = round(total, 3)
    return best


# ═══════════════════════════════════════════════════════════════════════════
# CSV writer
# ═══════════════════════════════════════════════════════════════════════════

COLUMNS = [
    "div_weight",
    "nominal_cost",
    "dominant_count",
    "s1_optimal",
    "s1_time",
    "r_tr",
    "worst_arc",
    "worst_arc_coverage",
    "recovery_cost",
    "regret",
    "load_deviation",
    "robust_optimal",
    "robust_time",
]


def write_csv(results: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in results:
            writer.writerow({col: row.get(col, "") for col in COLUMNS})
    print(f"\nResults written → {output_path}")


def print_summary(results: list[dict]) -> None:
    print("\n" + "═"*90)
    print("  EXPERIMENT SUMMARY")
    print("═"*90)
    header = (f"  {'w':>6}  {'cost':>6}  {'dom':>4}  {'R_TR':>6}  "
              f"{'worst_arc':<22}  {'rec_cost':>8}  {'regret':>8}  {'dev':>6}  {'opt'}")
    print(header)
    print("  " + "─"*86)
    for r in results:
        arc = r.get("worst_arc", "?")
        print(
            f"  {r['div_weight']:>6}  "
            f"{r.get('nominal_cost', '?'):>6}  "
            f"{r.get('dominant_count', '?'):>4}  "
            f"{r.get('r_tr', '?'):>6}  "
            f"{str(arc):<22}  "
            f"{r.get('regret', '?'):>8}  "
            f"{r.get('load_deviation', '?'):>6}  "
        )
    print("═"*90)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage 1 → R_TR → min-max regret sweep")
    p.add_argument("--instances", "-i", required=True,
                   help="Path to instance .lp file")
    p.add_argument("--weights", type=int, nargs="+",
                   default=[0, 50, 100, 200, 500, 1000],
                   help="div_weight values to sweep (default: 0 50 100 200 500 1000)")
    p.add_argument("--time-limit", type=int, default=30,
                   help="Seconds per solve stage (default: 30)")
    p.add_argument("--cap-divide", type=int, default=1)
    p.add_argument("--max-freq",   type=int, default=20)
    p.add_argument("--output", "-o", type=Path,
                   default=Path("results/experiment.csv"),
                   help="Output CSV path (default: results/experiment.csv)")
    return p.parse_args()


def main() -> None:
    args          = parse_args()
    instance_data = parse_instance(args.instances)
    results       = []

    print(f"Instance: {len(instance_data['parts'])} parts, "
          f"{len(instance_data['routes'])} routes")
    print(f"Sweeping div_weight: {args.weights}")
    print(f"Time limit per stage: {args.time_limit}s")
    print(f"Output: {args.output}")

    for w in args.weights:
        print(f"\n{'═'*65}")
        print(f"  div_weight = {w}")
        print(f"{'═'*65}")

        row: dict = {"div_weight": w}

        # ── Step 1: Stage 1 ──────────────────────────────────────────
        print(f"\n  [Step 1] Solving Stage 1...")
        stage1 = solve_stage1(
            args.instances,
            div_weight=w,
            time_limit=args.time_limit,
            cap_divide=args.cap_divide,
            max_freq=args.max_freq,
        )

        if stage1 is None:
            print(f"  ERROR: Stage 1 UNSAT for w={w}, skipping.")
            row.update({
                "nominal_cost": None, "dominant_count": None,
                "s1_optimal": False,  "s1_time": None,
                "r_tr": None, "worst_arc": None, "worst_arc_coverage": None,
                "recovery_cost": None, "regret": None,
                "load_deviation": None, "robust_optimal": False,
                "robust_time": None,
            })
            results.append(row)
            continue

        nominal_cost    = stage1["cost"]
        dominant_count  = len(stage1["dominant"])

        row["nominal_cost"]   = nominal_cost
        row["dominant_count"] = dominant_count
        row["s1_optimal"]     = stage1["optimum"]
        row["s1_time"]        = stage1["time"]

        print(f"  Done. cost={nominal_cost}  dominant={dominant_count}  "
              f"optimal={stage1['optimum']}")

        # ── Step 2: R_TR ─────────────────────────────────────────────
        print(f"\n  [Step 2] Computing R_TR...")
        r_tr, details = compute_r_tr(stage1["loads"], instance_data)
        worst         = min(details, key=lambda d: d["coverage"])
        worst_arc     = (worst["lost_f"], worst["lost_t"], worst["lost_tr"])
        worst_arc_str = f"({worst['lost_f']},{worst['lost_t']},{worst['lost_tr']})"

        row["r_tr"]               = r_tr
        row["worst_arc"]          = worst_arc_str
        row["worst_arc_coverage"] = worst["coverage"]

        print(f"  R_TR={r_tr}  worst={worst_arc_str}  coverage={worst['coverage']}")
        results.append(row)
        write_csv(results, args.output)  

if __name__ == "__main__":
    main()