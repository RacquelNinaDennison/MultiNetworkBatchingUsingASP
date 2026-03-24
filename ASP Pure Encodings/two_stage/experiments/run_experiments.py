#!/usr/bin/env python3
"""
run_experiments.py — Experiment runner for two-stage resilience evaluation
==========================================================================

Runs the two-stage pipeline across multiple instances and configurations,
collecting solver metrics and solution data for post-hoc resilience evaluation.

Two experiment types:
  1. Ablation: Turn Stage 2 soft constraints on/off to measure each one's
     contribution to resilience metrics.
  2. Weight sweep: Vary the weight of a specific soft constraint to generate
     Pareto fronts (cost vs resilience).

Usage
-----
    # Run ablation experiments on all instances:
    uv run experiments/run_experiments.py --mode ablation

    # Run weight sweep for concentration penalty:
    uv run experiments/run_experiments.py --mode sweep-concentration

    # Run weight sweep for heterogeneity penalty:
    uv run experiments/run_experiments.py --mode sweep-heterogeneity

    # Run everything:
    uv run experiments/run_experiments.py --mode all

    # Specify time limits:
    uv run experiments/run_experiments.py --mode ablation \\
        --time-limit 120 --round-timeout 60 --cap-divide 1000
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import threading
from collections import defaultdict
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory

# ── Paths ──────────────────────────────────────────────────────────────

HERE        = Path(__file__).parent
TWO_STAGE   = HERE.parent
STAGE1_BASE = TWO_STAGE / "stage1_flow.lp"
STAGE2_BASE = TWO_STAGE / "stage2_base.lp"
INSTANCES   = HERE / "instances"
ENCODINGS   = HERE / "encodings"
RESULTS_RAW = HERE / "results" / "raw"
RESULTS     = HERE / "results"

# Modular Stage 2 encoding files
S2_CONCENTRATION       = ENCODINGS / "stage2_concentration.lp"
S2_CONCENTRATION_VALUE = ENCODINGS / "stage2_concentration_value.lp"
S2_HETEROGENEITY       = ENCODINGS / "stage2_heterogeneity.lp"
S2_EVENNESS            = ENCODINGS / "stage2_evenness.lp"
S2_DISPATCH_COST       = ENCODINGS / "stage2_dispatch_cost.lp"
S1_RESOURCE_BALANCE    = ENCODINGS / "stage1_resource_balance.lp"
S1_MIN_FREQ            = ENCODINGS / "stage1_min_freq.lp"
S1_DIV_SWEEP           = ENCODINGS / "stage1_diversification_sweep.lp"
S1_EPSILON             = ENCODINGS / "stage1_epsilon_constraint.lp"


# ═══════════════════════════════════════════════════════════════════════
# Instance parsing
# ═══════════════════════════════════════════════════════════════════════

def load_instance_data(path: str) -> dict:
    """Parse instance facts for capacities, part sizes, values, and routes."""
    ctl = clingo.Control()
    ctl.load(path)
    ctl.ground([("base", [])])

    data: dict = {
        "transport_cap": {},
        "part_size": {},
        "part_val": {},
        "route_cost": {},
        "demands": {},       # (part, loc) -> demand qty (positive)
        "offers": {},        # (part, loc) -> offer qty (positive)
        "parts": set(),
        "locations": set(),
    }

    for atom in ctl.symbolic_atoms:
        sym = atom.symbol
        name = sym.name
        args = sym.arguments

        if name == "transportCapacity" and len(args) == 2:
            data["transport_cap"][str(args[0])] = args[1].number
        elif name == "partSize" and len(args) == 2:
            data["part_size"][str(args[0])] = args[1].number
        elif name == "partVal" and len(args) == 2:
            data["part_val"][str(args[0])] = args[1].number
        elif name == "part" and len(args) == 1:
            data["parts"].add(str(args[0]))
        elif name == "location" and len(args) == 1:
            data["locations"].add(str(args[0]))
        elif name == "route" and len(args) == 5:
            key = (str(args[0]), str(args[1]), str(args[2]))
            data["route_cost"][key] = args[4].number
        elif name == "demandOffer" and len(args) == 3:
            part, loc, val = str(args[0]), str(args[1]), args[2].number
            if val < 0:
                data["demands"][(part, loc)] = -val
            elif val > 0:
                data["offers"][(part, loc)] = val

    return data


# ═══════════════════════════════════════════════════════════════════════
# Stage 1 solver
# ═══════════════════════════════════════════════════════════════════════

def solve_stage1(
    instance_path: str,
    cap_divide: int,
    max_freq: int,
    time_limit: int,
    round_timeout: int = 60,
    extra_files: list[Path] | None = None,
    extra_args: list[str] | None = None,
    stage1_base: Path | None = None,
) -> dict | None:
    """Solve Stage 1 with optional extra encoding files and clingo arguments."""

    theory = ClingconTheory()
    args = [
        "-c", f"cap_size_divide={cap_divide}",
        "-c", f"max_freq={max_freq}",
    ]
    if extra_args:
        args.extend(extra_args)
    ctl = clingo.Control(args)
    theory.register(ctl)

    base = str(stage1_base) if stage1_base else str(STAGE1_BASE)
    files_to_load = [base, instance_path]
    if extra_files:
        files_to_load.extend(str(f) for f in extra_files)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_files(files_to_load, on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    ground_time = time.perf_counter() - t0
    theory.prepare(ctl)

    best: dict | None = None
    best_cost: int | None = None
    optimum = False

    BOUND_TEMPLATE = (
        ":- #sum {{ V,F,T,TR : _transCost(F,T,TR,V) }} >= {bound}."
    )

    max_rounds = 20
    for round_num in range(1, max_rounds + 1):
        elapsed = time.perf_counter() - t0
        if elapsed >= time_limit:
            break

        remaining = min(round_timeout, int(time_limit - elapsed))

        found_this_round: dict | None = None
        found_cost: int | None = None

        timer = threading.Timer(remaining, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    found_this_round = _extract_stage1(model, theory)
                    found_cost = model.cost[0] if model.cost else None
                    if model.optimality_proven:
                        optimum = True
                        break
                result = handle.get()
        except RuntimeError:
            result = None
        finally:
            timer.cancel()

        if optimum:
            best = found_this_round
            best_cost = found_cost
            break

        if result is not None and getattr(result, 'unsatisfiable', False):
            optimum = True
            break

        if found_this_round is None:
            break

        best = found_this_round
        best_cost = found_cost

        # Add bound for next round — skip if cost is too large (overflow risk)
        if best_cost is not None and best_cost < 2_000_000_000:
            bound_rule = BOUND_TEMPLATE.format(bound=best_cost)
            section = f"bound_{round_num}"
            try:
                ctl.add(section, [], bound_rule)
                ctl.ground([(section, [])])
            except RuntimeError:
                # Integer overflow in #sum — accept current best
                break
        else:
            # Cost too large for safe bounding — accept current best
            break

    total_time = time.perf_counter() - t0

    if best is not None:
        best["ground_time"] = round(ground_time, 3)
        best["total_time"] = round(total_time, 3)
        best["optimum"] = optimum
        best["cost"] = best_cost

    return best


def _extract_stage1(model, theory):
    route_freqs = []
    for sym in model.symbols(shown=True):
        if sym.name == "routeFreq" and len(sym.arguments) == 5:
            a = sym.arguments
            route_freqs.append({
                "from": str(a[0]), "to": str(a[1]), "tr": str(a[2]),
                "freq": a[3].number, "total_cap": a[4].number,
            })

    loads = {}
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "load" and len(sym.arguments) == 4 and val > 0:
            key = tuple(str(a) for a in sym.arguments)
            loads[key] = val

    return {"route_freqs": route_freqs, "loads": loads}


# ═══════════════════════════════════════════════════════════════════════
# Bridge: Stage 1 → Stage 2 facts
# ═══════════════════════════════════════════════════════════════════════

def build_stage2_facts(stage1: dict, instance_data: dict) -> str:
    lines = []

    for (f, t, tr, p), n in sorted(stage1["loads"].items()):
        lines.append(f"totalLoad({f},{t},{tr},{p},{n}).")

    for rf in stage1["route_freqs"]:
        per_trip_cap = instance_data["transport_cap"].get(rf["tr"], 0)
        lines.append(
            f"activeRoute({rf['from']},{rf['to']},{rf['tr']},"
            f"{rf['freq']},{per_trip_cap})."
        )

    for p, s in sorted(instance_data["part_size"].items()):
        lines.append(f"partSize({p},{s}).")

    for p, v in sorted(instance_data["part_val"].items()):
        lines.append(f"partVal({p},{v}).")

    for rf in stage1["route_freqs"]:
        key = (rf["from"], rf["to"], rf["tr"])
        cost = instance_data["route_cost"].get(key, 0)
        if cost > 0:
            lines.append(f"routeCost({rf['from']},{rf['to']},{rf['tr']},{cost}).")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Stage 2 solver
# ═══════════════════════════════════════════════════════════════════════

def solve_stage2(
    facts_str: str,
    encoding_files: list[Path],
    timeout: int,
    extra_rules: str = "",
) -> dict | None:
    """Solve Stage 2 with base encoding + modular constraint files + optional rules."""

    theory = ClingconTheory()
    ctl = clingo.Control()
    theory.register(ctl)

    all_files = [str(STAGE2_BASE)] + [str(f) for f in encoding_files]

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_string(facts_str, on_rule)
        clingo.ast.parse_files(all_files, on_rule)
        if extra_rules:
            clingo.ast.parse_string(extra_rules, on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    ground_time = time.perf_counter() - t0
    theory.prepare(ctl)

    best: dict | None = None
    best_cost = []
    optimum = False

    timer = threading.Timer(timeout, ctl.interrupt)
    timer.start()

    try:
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                theory.on_model(model)
                best = _extract_stage2(model, theory)
                best_cost = list(model.cost) if model.cost else []
                if model.optimality_proven:
                    optimum = True
                    break
    except RuntimeError:
        pass
    finally:
        timer.cancel()

    total_time = time.perf_counter() - t0

    if best is not None:
        best["ground_time"] = round(ground_time, 3)
        best["total_time"] = round(total_time, 3)
        best["optimum"] = optimum
        best["cost"] = best_cost

    return best


def _extract_stage2(model, theory):
    trip_loads = {}
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "tripLoad" and len(sym.arguments) == 5 and val > 0:
            a = sym.arguments
            key = (str(a[0]), str(a[1]), str(a[2]), str(a[3]), a[4].number)
            trip_loads[key] = val

    return {"trip_loads": trip_loads}


# ═══════════════════════════════════════════════════════════════════════
# Resilience evaluation
# ═══════════════════════════════════════════════════════════════════════

def evaluate_resilience(
    trip_loads: dict,
    stage1: dict,
    instance_data: dict,
) -> dict:
    """
    Compute resilience metrics from a Stage 2 packing solution.

    Returns dict with R_1, R_TR, R_arc, A_1.
    """

    demands = instance_data["demands"]   # (part, loc) -> demand qty
    offers = instance_data["offers"]     # (part, loc) -> offer qty

    if not demands or not trip_loads:
        return {"R_1": 0.0, "R_TR": 0.0, "R_arc": 0.0, "A_1": 0.0}

    # Build: what each trip delivers to each destination
    # trip_loads: (from, to, tr, part, trip_k) -> qty
    # We need to trace total supply arriving at each sink for each part

    # First, compute total supply arriving at each sink per part (no disruption)
    sink_supply = defaultdict(int)  # (part, sink) -> total arriving
    for (f, t, tr, p, k), qty in trip_loads.items():
        sink_supply[(p, t)] += qty

    # compute per-arc, per-part contributions to demand,
    # then measure what fraction of each arc's load survives each disruption.

    # For each demand sink, compute which arcs directly feed it
    sink_arcs = defaultdict(lambda: defaultdict(int))
    for (f, t, tr, p, k), qty in trip_loads.items():
        # Check if t is a sink for part p
        if (p, t) in demands:
            sink_arcs[(p, t)][(f, t, tr, k)] = qty

    # Group trip loads by arc
    arc_loads = defaultdict(lambda: defaultdict(int))  # (f,t,tr) -> {part: total}
    trip_contents = defaultdict(lambda: defaultdict(int))  # (f,t,tr,k) -> {part: qty}

    for (f, t, tr, p, k), qty in trip_loads.items():
        arc_loads[(f, t, tr)][p] += qty
        trip_contents[(f, t, tr, k)][p] = qty

    # For each sink, trace which arcs feed it (directly)
    # and compute demand fraction surviving each disruption
    sinks = set()
    for (p, loc) in demands:
        sinks.add(loc)

    # ── R_1: single trip loss ──────────────────────────────────
    # For each trip, compute: for each (part, sink) that this trip's arc
    # feeds, what fraction of that part's arc load is on this trip?
    # The surviving fraction = 1 - (trip_load / arc_total)

    sigma_values = []

    all_trips = list(trip_contents.keys())
    for trip_key in all_trips:
        parts_on_trip = trip_contents[trip_key]
        f, t, tr, k = trip_key
        arc_key = (f, t, tr)
        arc_total = arc_loads[arc_key]

        # For each part on this trip
        trip_sigmas = []
        for p, qty in parts_on_trip.items():
            total_on_arc = arc_total.get(p, 0)
            if total_on_arc > 0:
                surviving_fraction = 1.0 - (qty / total_on_arc)
                trip_sigmas.append(surviving_fraction)

        if trip_sigmas:
            sigma_values.append(min(trip_sigmas))

    R_1 = min(sigma_values) if sigma_values else 1.0

    # ── R_TR: transport resource loss on an arc ────────────────
    # For each (f, t, tr), remove ALL trips → what fraction of each part
    # on that arc survives? Answer: 0 for that resource. But if the same
    # arc (f, t) has other transport resources, those survive.

    # Group by arc pair (f, t) → {tr: {part: total}}
    arc_pair_loads = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (f, t, tr), parts in arc_loads.items():
        for p, qty in parts.items():
            arc_pair_loads[(f, t)][tr][p] += qty

    rtr_sigmas = []
    for (f, t), tr_loads in arc_pair_loads.items():
        if len(tr_loads) <= 1:
            # Only one TR on this arc — losing it loses everything
            for tr, parts in tr_loads.items():
                for p, qty in parts.items():
                    rtr_sigmas.append(0.0)
        else:
            # Multiple TRs — losing one leaves the others
            total_per_part = defaultdict(int)
            for tr, parts in tr_loads.items():
                for p, qty in parts.items():
                    total_per_part[p] += qty

            for lost_tr in tr_loads:
                for p in total_per_part:
                    lost = tr_loads[lost_tr].get(p, 0)
                    total = total_per_part[p]
                    if total > 0:
                        surviving = (total - lost) / total
                        rtr_sigmas.append(surviving)

    R_TR = min(rtr_sigmas) if rtr_sigmas else 1.0

    # ── R_arc: full arc failure ────────────────────────────────
    # For each arc pair (f, t), remove ALL trips across ALL TRs.
    # What fraction of each part's total network supply survives?

    # Total supply of each part across the entire network
    total_network_supply = defaultdict(int)
    for (f, t, tr, p, k), qty in trip_loads.items():
        total_network_supply[(p, t)] += qty

    rarc_sigmas = []
    for (f, t), tr_loads in arc_pair_loads.items():
        arc_total_per_part = defaultdict(int)
        for tr, parts in tr_loads.items():
            for p, qty in parts.items():
                arc_total_per_part[p] += qty

        for p, arc_qty in arc_total_per_part.items():
            # How much of this part arrives at t from all sources?
            total_arriving = sum(
                qty for (f2, t2, tr2, p2, k2), qty in trip_loads.items()
                if t2 == t and p2 == p
            )
            if total_arriving > 0 and (p, t) in demands:
                demand = demands[(p, t)]
                surviving = total_arriving - arc_qty
                fraction = surviving / demand if demand > 0 else 1.0
                rarc_sigmas.append(min(fraction, 1.0))

    R_arc = min(rarc_sigmas) if rarc_sigmas else 1.0

    # ── A_1: assembly completeness ─────────────────────────────
    # For each sink, compute consumption ratios from demand.
    # Then for each trip loss, compute surviving kits.

    from math import gcd
    from functools import reduce

    # Compute consumption ratios per sink
    sink_parts = defaultdict(dict)  # sink -> {part: demand}
    for (p, loc), d in demands.items():
        sink_parts[loc][p] = d

    sink_ratios = {}  # sink -> {part: ratio}
    sink_total_kits = {}  # sink -> total kits
    for loc, parts in sink_parts.items():
        if len(parts) < 2:
            continue
        values = list(parts.values())
        g = reduce(gcd, values)
        ratios = {p: d // g for p, d in parts.items()}
        sink_ratios[loc] = ratios
        sink_total_kits[loc] = min(d // ratios[p] for p, d in parts.items())

    if not sink_ratios:
        A_1 = R_1  # degenerates to R_1 if no multi-part sinks
    else:
        a1_values = []
        for trip_key in all_trips:
            parts_on_trip = trip_contents[trip_key]
            f, t, tr, k = trip_key
            arc_key = (f, t, tr)

            # Check each sink that this arc feeds
            for loc in sinks:
                if loc not in sink_ratios:
                    continue

                ratios = sink_ratios[loc]
                total_kits = sink_total_kits[loc]

                # Compute surviving kits at this sink if this trip is lost
                kit_counts = []
                for p, ratio in ratios.items():
                    # Total of this part arriving at this sink
                    total_arriving = sum(
                        qty for (f2, t2, tr2, p2, k2), qty in trip_loads.items()
                        if t2 == loc and p2 == p
                    )
                    # Subtract what's on the lost trip (only if it feeds this sink)
                    if t == loc:
                        lost = parts_on_trip.get(p, 0)
                    else:
                        lost = 0
                    surviving = total_arriving - lost
                    kit_counts.append(surviving // ratio)

                if kit_counts and total_kits > 0:
                    surviving_kits = min(kit_counts)
                    a1_values.append(surviving_kits / total_kits)

        A_1 = min(a1_values) if a1_values else R_1

    return {
        "R_1": round(R_1, 4),
        "R_TR": round(R_TR, 4),
        "R_arc": round(R_arc, 4),
        "A_1": round(A_1, 4),
    }


def count_violations(
    trip_loads: dict,
    stage1: dict,
    instance_data: dict,
) -> dict:
    """
    Count constraint violations in a packing solution, regardless of which
    constraints were active during solving. This tests whether satisfying
    one constraint (e.g. evenness) implicitly satisfies others (e.g.
    concentration avoidance, heterogeneity).

    Returns counts of:
      concentrated_trips: trips carrying > half of any part's arc load
      mono_trips: trips carrying only 1 part type on a multi-part route
      overloaded_trips: trips exceeding the ideal even split for any part
      empty_trips: trips carrying nothing
    """

    # Build arc-level data
    arc_loads = defaultdict(lambda: defaultdict(int))  # (f,t,tr) -> {part: total}
    trip_contents = defaultdict(lambda: defaultdict(int))  # (f,t,tr,k) -> {part: qty}

    for (f, t, tr, p, k), qty in trip_loads.items():
        arc_loads[(f, t, tr)][p] += qty
        trip_contents[(f, t, tr, k)][p] = qty

    # Build freq lookup
    freq_lookup = {}
    for rf in stage1["route_freqs"]:
        key = (rf["from"], rf["to"], rf["tr"])
        freq_lookup[key] = rf["freq"]

    # Count all trips (including empty)
    all_trip_keys = set()
    for rf in stage1["route_freqs"]:
        for k in range(1, rf["freq"] + 1):
            all_trip_keys.add((rf["from"], rf["to"], rf["tr"], k))

    used_trip_keys = set(trip_contents.keys())
    empty_trips = len(all_trip_keys - used_trip_keys)

    # ── Concentrated trips ──────────────────────────────────────
    # A trip is concentrated if it carries > N/2 of any part on its arc
    concentrated_count = 0
    for trip_key, parts in trip_contents.items():
        f, t, tr, k = trip_key
        arc_key = (f, t, tr)
        for p, qty in parts.items():
            total_on_arc = arc_loads[arc_key].get(p, 0)
            if total_on_arc > 1 and qty > total_on_arc / 2:
                concentrated_count += 1
                break  # count each trip at most once

    # ── Mono-part trips ─────────────────────────────────────────
    # A trip is mono-part if it carries exactly 1 part type AND
    # the route ships multiple part types
    mono_count = 0
    for trip_key, parts in trip_contents.items():
        if len(parts) != 1:
            continue
        f, t, tr, k = trip_key
        arc_key = (f, t, tr)
        route_part_count = len(arc_loads[arc_key])
        if route_part_count > 1:
            mono_count += 1

    # ── Overloaded trips ────────────────────────────────────────
    # A trip is overloaded if it carries more than ceil(N/Freq) of any part
    overloaded_count = 0
    for trip_key, parts in trip_contents.items():
        f, t, tr, k = trip_key
        arc_key = (f, t, tr)
        freq = freq_lookup.get(arc_key, 1)
        is_overloaded = False
        for p, qty in parts.items():
            total_on_arc = arc_loads[arc_key].get(p, 0)
            ideal_max = (total_on_arc + freq - 1) // freq  # ceil(N/Freq)
            if qty > ideal_max:
                is_overloaded = True
                break
        if is_overloaded:
            overloaded_count += 1

    # ── Max concentration ratio ─────────────────────────────────
    # The highest fraction of any part's arc load on a single trip
    max_concentration = 0.0
    for trip_key, parts in trip_contents.items():
        f, t, tr, k = trip_key
        arc_key = (f, t, tr)
        for p, qty in parts.items():
            total_on_arc = arc_loads[arc_key].get(p, 0)
            if total_on_arc > 0:
                ratio = qty / total_on_arc
                max_concentration = max(max_concentration, ratio)

    return {
        "concentrated_trips": concentrated_count,
        "mono_trips": mono_count,
        "overloaded_trips": overloaded_count,
        "empty_trips": empty_trips,
        "max_concentration": round(max_concentration, 4),
        "total_used_trips": len(used_trip_keys),
    }


def count_s1_metrics(
    stage1: dict,
    instance_data: dict,
) -> dict:
    """
    Compute Stage 1 metrics: pure transport cost and underDiversified count.

    Transport cost = sum of (route_cost × freq) across all active arcs.
    UnderDiversified = number of (arc, part) pairs where available TRs > used TRs.
    """
    loads = stage1["loads"]  # (from, to, tr, part) -> qty

    # Pure transport cost (not the solver objective, but actual cost)
    transport_cost = 0
    for rf in stage1["route_freqs"]:
        key = (rf["from"], rf["to"], rf["tr"])
        route_cost = instance_data["route_cost"].get(key, 0)
        transport_cost += route_cost * rf["freq"]

    # Count underDiversified: for each (arc_pair, part), check if all
    # available TRs are used
    # Group loads by arc pair (f, t) and part
    arc_part_trs_used = defaultdict(set)    # (f, t, p) -> {trs with load}
    arc_part_trs_available = defaultdict(set)  # (f, t, p) -> {trs that can carry p}

    for (f, t, tr, p), qty in loads.items():
        if qty > 0:
            arc_part_trs_used[(f, t, p)].add(tr)

    # Available TRs: from route data, where partSize <= transportCapacity
    for (f, t, tr), cost in instance_data["route_cost"].items():
        for p in instance_data["parts"]:
            p_size = instance_data["part_size"].get(p, 0)
            tr_cap = instance_data["transport_cap"].get(tr, 0)
            if p_size <= tr_cap and p_size > 0:
                arc_part_trs_available[(f, t, p)].add(tr)

    underdiversified_count = 0
    for key, used in arc_part_trs_used.items():
        available = arc_part_trs_available.get(key, set())
        if len(available) > 1 and len(used) < len(available):
            underdiversified_count += 1

    return {
        "s1_transport_cost": transport_cost,
        "s1_underdiversified": underdiversified_count,
    }


# ═══════════════════════════════════════════════════════════════════════
# Experiment configurations
# ═══════════════════════════════════════════════════════════════════════

# Stage 1 variants
S1_VARIANTS = {
    "S1-COST": {
        "extra_files": [],
    },
    "S1-DIV": {
        "extra_files": [S1_RESOURCE_BALANCE],
    },
    "S1-MINF": {
        "extra_files": [S1_MIN_FREQ],
    },
    "S1-DIV-MINF": {
        "extra_files": [S1_RESOURCE_BALANCE, S1_MIN_FREQ],
    },
}

# Stage 2 ablation variants: each is a list of encoding files to load
S2_ABLATION_VARIANTS = {
    "S2-BASE": {
        "files": [],
    },
    "S2-EVEN": {
        "files": [S2_EVENNESS, S2_DISPATCH_COST],
    },
    "S2-HET": {
        "files": [S2_HETEROGENEITY, S2_DISPATCH_COST],
    },
    "S2-WC": {
        "files": [S2_CONCENTRATION, S2_DISPATCH_COST],
    },
    "S2-FULL": {
        "files": [S2_CONCENTRATION, S2_HETEROGENEITY, S2_EVENNESS, S2_DISPATCH_COST],
    },
    "S2-VALW": {
        "files": [S2_CONCENTRATION, S2_CONCENTRATION_VALUE,
                  S2_HETEROGENEITY, S2_EVENNESS, S2_DISPATCH_COST],
    },
}


def make_sweep_rules(constraint: str, weight: int) -> tuple[list[Path], str]:
    """Generate encoding files + extra rules for a weight sweep experiment.

    Returns (files_to_load, extra_rules_string).
    The base constraint rules come from files; the weight is injected via string.
    """

    if constraint == "concentration":
        # Load all other constraints at default weights.
        # Override the concentration weak constraint with the swept weight.
        files = [S2_HETEROGENEITY, S2_EVENNESS, S2_DISPATCH_COST]
        extra = f"""
halfLoad(F, T, TR, P, N/2) :- totalLoad(F, T, TR, P, N), N > 1.
concentrated(F, T, TR, P, K) :-
    &sum {{ tripLoad(F, T, TR, P, K) }} > H,
    halfLoad(F, T, TR, P, H), trip(F, T, TR, K).
:~ concentrated(F, T, TR, P, K). [{weight}@3, F, T, TR, P, K]
#show concentrated/5.
"""
        return files, extra

    elif constraint == "heterogeneity":
        # Load all other constraints at default weights.
        # Override the heterogeneity weak constraint with the swept weight.
        files = [S2_CONCENTRATION, S2_EVENNESS, S2_DISPATCH_COST]
        extra = f"""
monoTrip(F, T, TR, K) :-
    tripPartCount(F, T, TR, K, 1),
    routePartTypes(F, T, TR, Total), Total > 1.
:~ monoTrip(F, T, TR, K). [{weight}@2, F, T, TR, K]
#show monoTrip/4.
"""
        return files, extra

    else:
        raise ValueError(f"Unknown constraint to sweep: {constraint}")


# ═══════════════════════════════════════════════════════════════════════
# Experiment runners
# ═══════════════════════════════════════════════════════════════════════

def run_single(
    instance_path: Path,
    instance_data: dict,
    s1_name: str,
    s1_extra_files: list[Path],
    s2_name: str,
    s2_files: list[Path],
    s2_extra_rules: str,
    cap_divide: int,
    max_freq: int,
    time_limit: int,
    round_timeout: int,
    stage1_cache: dict,
    s1_extra_args: list[str] | None = None,
    s1_base: Path | None = None,
) -> dict | None:
    """Run a single (S1 variant, S2 variant) configuration and return results."""

    # Use cached Stage 1 solution if available
    if s1_name not in stage1_cache:
        print(f"    Solving Stage 1 ({s1_name})...", end="", flush=True)
        s1 = solve_stage1(
            str(instance_path), cap_divide, max_freq, time_limit,
            round_timeout=round_timeout,
            extra_files=s1_extra_files if s1_extra_files else None,
            extra_args=s1_extra_args,
            stage1_base=s1_base,
        )
        if s1 is None:
            print(" UNSAT")
            stage1_cache[s1_name] = None
            return None
        print(f" cost={s1['cost']}, time={s1['total_time']}s")
        stage1_cache[s1_name] = s1

    s1 = stage1_cache[s1_name]
    if s1 is None:
        return None

    # Build Stage 2 facts
    facts = build_stage2_facts(s1, instance_data)

    # Solve Stage 2
    print(f"    Solving Stage 2 ({s2_name})...", end="", flush=True)
    s2 = solve_stage2(
        facts, s2_files, timeout=round_timeout,
        extra_rules=s2_extra_rules,
    )
    if s2 is None:
        print(" UNSAT")
        return None
    print(f" cost={s2['cost']}, time={s2['total_time']}s")

    # Evaluate resilience
    resilience = evaluate_resilience(s2["trip_loads"], s1, instance_data)

    # Count violations (post-hoc, regardless of which constraints were active)
    violations = count_violations(s2["trip_loads"], s1, instance_data)

    # Stage 1 metrics (pure transport cost, underdiversified count)
    s1_metrics = count_s1_metrics(s1, instance_data)

    total_trips = sum(rf["freq"] for rf in s1["route_freqs"])

    return {
        "s1_name": s1_name,
        "s2_name": s2_name,
        "s1_cost": s1["cost"],
        "s1_time": s1["total_time"],
        "s1_optimal": s1["optimum"],
        "s2_cost": s2["cost"],
        "s2_time": s2["total_time"],
        "s2_optimal": s2["optimum"],
        "total_trips": total_trips,
        **resilience,
        **violations,
        **s1_metrics,
    }


def run_ablation(
    instances: list[Path],
    cap_divide: int,
    max_freq: int,
    time_limit: int,
    round_timeout: int,
) -> list[dict]:
    """Run ablation experiments: all S1 × S2 variant combinations."""

    results = []

    for instance_path in sorted(instances):
        name = instance_path.stem
        inst_class = name.rsplit("_", 1)[0]  # e.g. "small" from "small_seed1"

        print(f"\n{'='*65}")
        print(f"  Instance: {name} ({inst_class})")
        print(f"{'='*65}")

        instance_data = load_instance_data(str(instance_path))
        stage1_cache: dict = {}

        for s1_name, s1_config in S1_VARIANTS.items():
            for s2_name, s2_config in S2_ABLATION_VARIANTS.items():
                result = run_single(
                    instance_path, instance_data,
                    s1_name, s1_config["extra_files"],
                    s2_name, s2_config["files"], "",
                    cap_divide, max_freq, time_limit, round_timeout,
                    stage1_cache,
                )
                if result:
                    result["instance"] = name
                    result["class"] = inst_class
                    result["experiment"] = "ablation"
                    result["sweep_param"] = ""
                    result["sweep_weight"] = ""
                    results.append(result)

    return results


def run_sweep(
    instances: list[Path],
    constraint: str,
    weights: list[int],
    cap_divide: int,
    max_freq: int,
    time_limit: int,
    round_timeout: int,
) -> list[dict]:
    """Run weight sweep experiments for a specific constraint."""

    results = []

    for instance_path in sorted(instances):
        name = instance_path.stem
        inst_class = name.rsplit("_", 1)[0]

        print(f"\n{'='*65}")
        print(f"  Instance: {name} — sweep {constraint}")
        print(f"{'='*65}")

        instance_data = load_instance_data(str(instance_path))
        stage1_cache: dict = {}

        # Only use S1-COST for sweep experiments (isolate Stage 2 effect)
        s1_name = "S1-COST"
        s1_config = S1_VARIANTS[s1_name]

        for weight in weights:
            s2_name = f"sweep-{constraint}-w{weight}"
            files, extra_rules = make_sweep_rules(constraint, weight)

            result = run_single(
                instance_path, instance_data,
                s1_name, s1_config["extra_files"],
                s2_name, files, extra_rules,
                cap_divide, max_freq, time_limit, round_timeout,
                stage1_cache,
            )
            if result:
                result["instance"] = name
                result["class"] = inst_class
                result["experiment"] = f"sweep-{constraint}"
                result["sweep_param"] = constraint
                result["sweep_weight"] = weight
                results.append(result)

    return results


S1_FLOW_NO_SCALE = ENCODINGS / "stage1_flow_no_scale.lp"

def run_s1_diversification_sweep(
    instances: list[Path],
    weights: list[int],
    cap_divide: int,
    max_freq: int,
    time_limit: int,
    round_timeout: int,
    use_unscaled_cost: bool = False,
) -> list[dict]:
    """Sweep the Stage 1 diversification weight to generate cost vs R_TR Pareto front.

    For each weight, Stage 1 runs with both cost and diversification at @1,
    competing directly. Stage 2 runs with S2-FULL to give the best possible
    packing for each Stage 1 output.
    """

    results = []
    s1_base = S1_FLOW_NO_SCALE if use_unscaled_cost else None

    for instance_path in sorted(instances):
        name = instance_path.stem
        inst_class = name.rsplit("_", 1)[0]

        print(f"\n{'='*65}")
        print(f"  Instance: {name} — S1 diversification sweep")
        print(f"{'='*65}")

        instance_data = load_instance_data(str(instance_path))

        for weight in weights:
            s1_name = f"S1-div-w{weight}"
            s2_name = "S2-FULL"

            # Each weight gets a fresh Stage 1 solve (can't cache across weights)
            stage1_cache: dict = {}

            result = run_single(
                instance_path, instance_data,
                s1_name, [S1_DIV_SWEEP],
                s2_name,
                [S2_CONCENTRATION, S2_HETEROGENEITY, S2_EVENNESS, S2_DISPATCH_COST],
                "",
                cap_divide, max_freq, time_limit, round_timeout,
                stage1_cache,
                s1_extra_args=["-c", f"div_weight={weight}"],
                s1_base=s1_base,
            )
            if result:
                result["instance"] = name
                result["class"] = inst_class
                result["experiment"] = "sweep-s1-diversification"
                result["sweep_param"] = "div_weight"
                result["sweep_weight"] = weight
                results.append(result)

    return results


def run_epsilon_pareto(
    instances: list[Path],
    epsilons: list[int],
    cap_divide: int,
    max_freq: int,
    time_limit: int,
    round_timeout: int,
    use_unscaled_cost: bool = False,
    extra_s1_files: list[Path] | None = None,
    experiment_label: str = "epsilon-pareto",
) -> list[dict]:
    """ε-constraint Pareto front: for each ε, minimise cost subject to
    underDiversified ≤ ε. Each ε gives one guaranteed Pareto point.

    Uses the standard #minimize from stage1_flow.lp for cost, plus
    a hard constraint on the number of underDiversified arcs.
    Optionally loads extra S1 files (e.g., min-freq constraint).
    """

    results = []
    s1_base = S1_FLOW_NO_SCALE if use_unscaled_cost else None

    for instance_path in sorted(instances):
        name = instance_path.stem
        inst_class = name.rsplit("_", 1)[0]

        print(f"\n{'='*65}")
        print(f"  Instance: {name} — ε-constraint Pareto")
        print(f"{'='*65}")

        instance_data = load_instance_data(str(instance_path))

        for eps in epsilons:
            s1_name = f"S1-eps{eps}"
            s2_name = "S2-FULL"

            stage1_cache: dict = {}

            s1_files = [S1_EPSILON]
            if extra_s1_files:
                s1_files.extend(extra_s1_files)

            result = run_single(
                instance_path, instance_data,
                s1_name, s1_files,
                s2_name,
                [S2_CONCENTRATION, S2_HETEROGENEITY, S2_EVENNESS, S2_DISPATCH_COST],
                "",
                cap_divide, max_freq, time_limit, round_timeout,
                stage1_cache,
                s1_extra_args=["-c", f"epsilon={eps}"],
                s1_base=s1_base,
            )
            if result:
                result["instance"] = name
                result["class"] = inst_class
                result["experiment"] = experiment_label
                result["sweep_param"] = "epsilon"
                result["sweep_weight"] = eps
                results.append(result)
            else:
                print(f"    ε={eps}: UNSAT (constraint too tight)")

    return results


# ═══════════════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════════════

CSV_COLUMNS = [
    "instance", "class", "experiment", "s1_name", "s2_name",
    "sweep_param", "sweep_weight",
    "s1_cost", "s1_time", "s1_optimal",
    "s2_cost", "s2_time", "s2_optimal",
    "total_trips", "total_used_trips",
    "R_1", "R_TR", "R_arc", "A_1",
    "concentrated_trips", "mono_trips", "overloaded_trips",
    "empty_trips", "max_concentration",
    "s1_transport_cost", "s1_underdiversified",
]


def write_csv(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    print(f"\nResults written to {path} ({len(results)} rows)")


def write_json_raw(results: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        name = f"{r['instance']}_{r['s1_name']}_{r['s2_name']}.json"
        with open(output_dir / name, "w") as f:
            json.dump(r, f, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run two-stage resilience experiments."
    )
    parser.add_argument("--mode", required=True,
                        choices=["ablation", "sweep-concentration",
                                 "sweep-heterogeneity",
                                 "sweep-s1-diversification",
                                 "epsilon-pareto",
                                 "epsilon-pareto-minfreq", "all"],
                        help="Which experiments to run")
    parser.add_argument("--cap-divide", type=int, default=1,
                        help="Capacity scaling divisor")
    parser.add_argument("--max-freq", type=int, default=20,
                        help="Maximum frequency")
    parser.add_argument("--time-limit", type=int, default=120,
                        help="Total time limit per stage (seconds)")
    parser.add_argument("--round-timeout", type=int, default=60,
                        help="Per-round timeout (seconds)")
    parser.add_argument("--instances-dir", type=Path, default=INSTANCES,
                        help="Directory containing instance .lp files")
    parser.add_argument("--instance-filter", type=str, default=None,
                        help="Only run instances matching this prefix (e.g. 'small')")
    parser.add_argument("--unscaled-cost", action="store_true",
                        help="Use unscaled cost for S1 sweep (for small-cost instances like data.lp)")

    args = parser.parse_args()

    # Discover instances
    instances = sorted(args.instances_dir.glob("*.lp"))
    if args.instance_filter:
        instances = [i for i in instances if i.stem.startswith(args.instance_filter)]

    if not instances:
        print(f"No instances found in {args.instances_dir}")
        return 1

    print(f"Found {len(instances)} instances")

    all_results = []

    # ── Ablation ───────────────────────────────────────────────
    if args.mode in ("ablation", "all"):
        print("\n" + "=" * 65)
        print("  ABLATION EXPERIMENTS")
        print("=" * 65)
        results = run_ablation(
            instances, args.cap_divide, args.max_freq,
            args.time_limit, args.round_timeout,
        )
        all_results.extend(results)
        write_csv(results, RESULTS / "ablation.csv")

    # ── Concentration sweep ────────────────────────────────────
    if args.mode in ("sweep-concentration", "all"):
        print("\n" + "=" * 65)
        print("  CONCENTRATION WEIGHT SWEEP")
        print("=" * 65)
        weights = [0, 1, 5, 10, 20, 50, 100, 500]
        results = run_sweep(
            instances, "concentration", weights,
            args.cap_divide, args.max_freq,
            args.time_limit, args.round_timeout,
        )
        all_results.extend(results)
        write_csv(results, RESULTS / "sweep_concentration.csv")

    # ── Heterogeneity sweep ────────────────────────────────────
    if args.mode in ("sweep-heterogeneity", "all"):
        print("\n" + "=" * 65)
        print("  HETEROGENEITY WEIGHT SWEEP")
        print("=" * 65)
        weights = [0, 1, 5, 10, 20, 50, 100, 500]
        results = run_sweep(
            instances, "heterogeneity", weights,
            args.cap_divide, args.max_freq,
            args.time_limit, args.round_timeout,
        )
        all_results.extend(results)
        write_csv(results, RESULTS / "sweep_heterogeneity.csv")

    # ── Stage 1 diversification sweep ─────────────────────────
    if args.mode in ("sweep-s1-diversification", "all"):
        print("\n" + "=" * 65)
        print("  STAGE 1 DIVERSIFICATION WEIGHT SWEEP")
        print("=" * 65)
        weights = list(range(0, 520, 20))  # 0, 20, 40, ..., 500
        results = run_s1_diversification_sweep(
            instances, weights,
            args.cap_divide, args.max_freq,
            args.time_limit, args.round_timeout,
            use_unscaled_cost=args.unscaled_cost,
        )
        all_results.extend(results)
        write_csv(results, RESULTS / "sweep_s1_diversification.csv")

    # ── ε-constraint Pareto ──────────────────────────────────
    if args.mode in ("epsilon-pareto", "all"):
        print("\n" + "=" * 65)
        print("  ε-CONSTRAINT PARETO FRONT")
        print("=" * 65)
        epsilons = list(range(0, 11))  # 0, 1, 2, ..., 10
        results = run_epsilon_pareto(
            instances, epsilons,
            args.cap_divide, args.max_freq,
            args.time_limit, args.round_timeout,
            use_unscaled_cost=args.unscaled_cost,
        )
        all_results.extend(results)
        write_csv(results, RESULTS / "epsilon_pareto.csv")

    # ── ε-constraint Pareto with min-freq + resource balance ──
    if args.mode in ("epsilon-pareto-minfreq", "all"):
        print("\n" + "=" * 65)
        print("  ε-CONSTRAINT PARETO FRONT (freq ≥ 2 + resource balance)")
        print("=" * 65)
        epsilons = list(range(0, 11))
        results = run_epsilon_pareto(
            instances, epsilons,
            args.cap_divide, args.max_freq,
            args.time_limit, args.round_timeout,
            use_unscaled_cost=args.unscaled_cost,
            extra_s1_files=[S1_MIN_FREQ, S1_RESOURCE_BALANCE],
            experiment_label="epsilon-pareto-minfreq",
        )
        all_results.extend(results)
        write_csv(results, RESULTS / "epsilon_pareto_minfreq.csv")

    # ── Combined output ────────────────────────────────────────
    if all_results:
        write_csv(all_results, RESULTS / "all_results.csv")
        write_json_raw(all_results, RESULTS_RAW)

    print(f"\nTotal experiments completed: {len(all_results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
