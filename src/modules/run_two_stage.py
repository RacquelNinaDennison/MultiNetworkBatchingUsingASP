#!/usr/bin/env python3
"""
run_two_stage.py — Two-stage logistics optimisation pipeline
=============================================================

Stage 1 (Tactical):  Solve network flow to determine aggregate loads
                     and transport frequencies.
Stage 2 (Operational): Distribute the aggregate loads into per-trip
                       packings with diversification constraints.

Usage
-----
    From the ``src`` directory (see project README for PYTHONPATH)::

        python modules/run_two_stage.py -i path/to/instance.lp
        python modules/run_two_stage.py -i path/to/instance.lp --cap-divide 1 \\
            --max-freq 30 --time-limit 120
"""

from __future__ import annotations

import argparse
import sys
import time
import threading
from collections import defaultdict
from pathlib import Path
from statistics import mean

import clingo
import clingo.ast
from clingcon import ClingconTheory


_SRC_ROOT = Path(__file__).resolve().parent.parent
STAGE1 = _SRC_ROOT / "encoding" / "twostage" / "clingcon" / "stage_1_clingcon_flow.lp"
STAGE2 = _SRC_ROOT / "encoding" / "twostage" / "clingcon" / "stage_2_packing.lp"


# ─────────────────────────────────────────────────────────────────────────
# Instance parsing
# ─────────────────────────────────────────────────────────────────────────

def load_instance_data(path: str) -> dict:
    """Parse instance facts for raw capacities and part sizes."""
    ctl = clingo.Control()
    ctl.load(path)
    ctl.ground([("base", [])])

    data: dict = {
        "transport_cap": {},   # tr -> int (raw capacity)
        "part_size":     {},   # part -> int (raw size)
        "part_val":      {},   # part -> int (monetary value)
        "route_cost":    {},   # (from, to, tr) -> int (cost per trip)
        "parts":         set(),
        "locations":     set(),
    }

    for atom in ctl.symbolic_atoms:
        sym  = atom.symbol
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

    return data


# ─────────────────────────────────────────────────────────────────────────
# Stage 1: Network flow + frequency
# ─────────────────────────────────────────────────────────────────────────

def solve_stage1(
    instance_path: str,
    cap_divide:    int,
    max_freq:      int,
    time_limit:    int,
    round_timeout: int = 30,
    max_rounds:    int = 20,
) -> dict | None:
    """Solve the tactical network flow using multi-shot with iterative bounds.

    Each round solves for up to ``round_timeout`` seconds.  If a model is
    found but optimality isn't proven, the best cost is used as a nogood
    (upper bound) and the solver restarts.  When a round returns UNSAT or
    finds no new model, the previous best is accepted as optimal.
    """

    weight = 1
    theory = ClingconTheory()
    ctl = clingo.Control([
        "-c", f"cap_size_divide={cap_divide}",
        "-c", f"max_freq={max_freq}",
        "-c", f"weight={weight}"
    ])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_files([str(STAGE1), instance_path], on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    ground_time = time.perf_counter() - t0
    theory.prepare(ctl)

    best: dict | None = None
    best_cost: int | None = None
    optimum = False

    # The bound constraint uses the cost helper atoms from stage1_flow.lp:
    #   _co2Cost(F,T,TR,V) and _transCost(F,T,TR,V)
    BOUND = (
        ":- #sum {{ V,F,T,TR : _transCost(F,T,TR,V); "
        "{weight},F,T,P : dominantTR(F,T,P); "
        "{weight},F,T,P : monoPartTR(F,T,P) }} >= {bound}."
    )

    for round_num in range(1, max_rounds + 1):
        elapsed = time.perf_counter() - t0
        if elapsed >= time_limit:
            print(f"  Round {round_num}: overall time limit reached", flush=True)
            break

        remaining = min(round_timeout, int(time_limit - elapsed))
        print(f"  Round {round_num}: solving (up to {remaining}s) "
              f"{'[bound < ' + str(best_cost) + ']' if best_cost else '[no bound]'}",
              end="", flush=True)

        found_this_round: dict | None = None
        found_cost: int | None = None

        # Use ctl.interrupt() from a timer — safe with clingcon (unlike handle.cancel)
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
            # ctl.interrupt() can occasionally trigger a clingcon assertion;
            # treat as timeout — we still have best from previous rounds
            result = None
        finally:
            timer.cancel()

        # ── Analyse this round ───────────────────────────────────────
        if optimum:
            best = found_this_round
            best_cost = found_cost
            print(f" → OPTIMUM (cost={best_cost})", flush=True)
            break

        if result is not None and getattr(result, 'unsatisfiable', False):
            # No solution better than bound → previous best is optimal
            print(f" → UNSAT (previous cost={best_cost} is optimal)", flush=True)
            optimum = True
            break

        if found_this_round is None:
            # Timeout with no new model → can't improve
            print(f" → no new model (using best cost={best_cost})", flush=True)
            break

        # We found a model but didn't prove optimality → tighten bound
        best = found_this_round
        best_cost = found_cost
        print(f" → model found (cost={best_cost})", flush=True)

        # Add nogood: next solution must have cost strictly less than best
        bound_rule = BOUND.format(weight=weight, bound=best_cost)
        section = f"bound_{round_num}"
        ctl.add(section, [], bound_rule)
        ctl.ground([(section, [])])

    total_time = time.perf_counter() - t0

    if best is not None:
        best["ground_time"] = round(ground_time, 3)
        best["total_time"]  = round(total_time, 3)
        best["optimum"]     = optimum
        best["cost"]        = best_cost

    return best


def _extract_stage1(model: clingo.Model, theory: ClingconTheory) -> dict:
    """Extract routeFreq atoms and load CSP assignments from the model."""

    route_freqs: list[dict] = []
    for sym in model.symbols(shown=True):
        if sym.name == "routeFreq" and len(sym.arguments) == 5:
            a = sym.arguments
            route_freqs.append({
                "from": str(a[0]), "to": str(a[1]), "tr": str(a[2]),
                "freq": a[3].number, "total_cap": a[4].number,
            })

    loads: dict[tuple, int] = {}
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "load" and len(sym.arguments) == 4 and val > 0:
            key = tuple(str(a) for a in sym.arguments)
            loads[key] = val

    return {"route_freqs": route_freqs, "loads": loads}


# ─────────────────────────────────────────────────────────────────────────
# Bridge: Stage 1 output → Stage 2 input
# ─────────────────────────────────────────────────────────────────────────

def build_stage2_facts(stage1: dict, instance_data: dict) -> str:
    """Convert Stage 1 results + instance data into Stage 2 input facts."""
    lines: list[str] = []

    # totalLoad(From, To, TR, Part, N).
    for (f, t, tr, p), n in sorted(stage1["loads"].items()):
        lines.append(f"totalLoad({f},{t},{tr},{p},{n}).")
    
    for tr, cap in sorted(instance_data["transport_cap"].items()):
        lines.append(f"transportCapacity({tr},{cap}).")

    # activeRoute(From, To, TR, Freq, PerTripCap).
    for rf in stage1["route_freqs"]:
        per_trip_cap = instance_data["transport_cap"].get(rf["tr"], 0)
        lines.append(
            f"activeRoute({rf['from']},{rf['to']},{rf['tr']},"
            f"{rf['freq']},{per_trip_cap})."
        )

    # partSize(P, S).  (raw, unscaled)
    for p, s in sorted(instance_data["part_size"].items()):
        lines.append(f"partSize({p},{s}).")

    # partVal(P, V).
    for p, v in sorted(instance_data["part_val"].items()):
        lines.append(f"partVal({p},{v}).")

    # routeCost(From, To, TR, C).  — per-trip dispatch cost for Stage 2
    for rf in stage1["route_freqs"]:
        key = (rf["from"], rf["to"], rf["tr"])
        cost = instance_data["route_cost"].get(key, 0)
        if cost > 0:
            lines.append(f"routeCost({rf['from']},{rf['to']},{rf['tr']},{cost}).")
    print(lines)
    return "\n".join(lines)


def check_feasibility(stage1: dict, instance_data: dict) -> list[str]:
    """Warn about loads that can't physically fit in a single trip."""
    warnings: list[str] = []
    for (f, t, tr, p), n in stage1["loads"].items():
        part_size  = instance_data["part_size"].get(p, 0)
        trip_cap   = instance_data["transport_cap"].get(tr, 0)
        if part_size > trip_cap:
            warnings.append(
                f"  WARNING: {p} (size={part_size}) > {tr} capacity "
                f"({trip_cap}) on {f}→{t} — Stage 2 will be infeasible "
                f"for this arc"
            )
    return warnings


# ─────────────────────────────────────────────────────────────────────────
# Stage 2: Per-trip bin packing
# ─────────────────────────────────────────────────────────────────────────

def solve_stage2(facts_str: str, time_limit: int, round_timeout: int = 30) -> dict | None:
    """Solve per-trip packing with diversification.

    Uses ctl.interrupt() with a timer to bound each round, then accepts the
    best model found (weak-constraint costs are available via model.cost).
    """

    theory = ClingconTheory()
    ctl = clingo.Control()
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_string(facts_str, on_rule)
        clingo.ast.parse_files([str(STAGE2)], on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    ground_time = time.perf_counter() - t0
    theory.prepare(ctl)

    best: dict | None = None
    optimum = False

    remaining = min(round_timeout, time_limit)
    print(f"  Solving (up to {remaining}s)...", end="", flush=True)

    timer = threading.Timer(remaining, ctl.interrupt)
    timer.start()

    try:
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                theory.on_model(model)
                best = _extract_stage2(model, theory)
                cost = list(model.cost) if model.cost else []
                if model.optimality_proven:
                    optimum = True
                    break
    except RuntimeError:
        pass
    finally:
        timer.cancel()

    total_time = time.perf_counter() - t0

    if optimum:
        print(f" OPTIMUM (cost={cost})", flush=True)
    elif best is not None:
        print(f" best found (cost={cost})", flush=True)
    else:
        print(f" no model found", flush=True)

    if best is not None:
        best["ground_time"] = round(ground_time, 3)
        best["total_time"]  = round(total_time, 3)
        best["optimum"]     = optimum

    return best


def _extract_stage2(model: clingo.Model, theory: ClingconTheory) -> dict:
    """Extract per-trip packings from Stage 2 model."""

    trip_loads: dict[tuple, int] = {}
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "tripLoad" and len(sym.arguments) == 5 and val > 0:
            a = sym.arguments
            key = (str(a[0]), str(a[1]), str(a[2]), str(a[3]), a[4].number)
            trip_loads[key] = val

    trip_part_counts: dict[tuple, int] = {}
    route_part_types: dict[tuple, int] = {}

    for sym in model.symbols(shown=True):
        a = sym.arguments
        if sym.name == "tripPartCount" and len(a) == 5:
            key = (str(a[0]), str(a[1]), str(a[2]), a[3].number)
            trip_part_counts[key] = a[4].number
        elif sym.name == "routePartTypes" and len(a) == 4:
            key = (str(a[0]), str(a[1]), str(a[2]))
            route_part_types[key] = a[3].number

    return {
        "trip_loads":       trip_loads,
        "trip_part_counts": trip_part_counts,
        "route_part_types": route_part_types,
    }


# ─────────────────────────────────────────────────────────────────────────
# Quality metrics
# ─────────────────────────────────────────────────────────────────────────

def compute_metrics(stage2: dict, instance_data: dict, route_freqs: list) -> dict:
    """Compute packing quality metrics from Stage 2 output."""

    # Build per-trip cap lookup
    trip_cap: dict[tuple, int] = {}
    for rf in route_freqs:
        cap = instance_data["transport_cap"].get(rf["tr"], 0)
        for k in range(1, rf["freq"] + 1):
            trip_cap[(rf["from"], rf["to"], rf["tr"], k)] = cap

    # ── Parts per trip ───────────────────────────────────────────────
    counts = list(stage2["trip_part_counts"].values())
    non_empty_counts = [c for c in counts if c > 0]
    mono_trips = sum(1 for c in counts if c == 1)

    # ── Fill rate per trip ───────────────────────────────────────────
    trip_volumes: dict[tuple, int] = defaultdict(int)
    for (f, t, tr, p, k), n in stage2["trip_loads"].items():
        size = instance_data["part_size"].get(p, 0)
        trip_volumes[(f, t, tr, k)] += size * n

    fill_rates: list[float] = []
    for trip_key, vol in trip_volumes.items():
        cap = trip_cap.get(trip_key, 0)
        if cap > 0:
            fill_rates.append(vol / cap)

    # ── Max single-part share per trip ───────────────────────────────
    trip_part_vols: dict[tuple, dict[str, int]] = defaultdict(dict)
    for (f, t, tr, p, k), n in stage2["trip_loads"].items():
        size = instance_data["part_size"].get(p, 0)
        trip_part_vols[(f, t, tr, k)][p] = size * n

    max_shares: list[float] = []
    for trip_key, part_vols in trip_part_vols.items():
        total = sum(part_vols.values())
        if total > 0 and len(part_vols) > 1:
            max_shares.append(max(part_vols.values()) / total)

    # ── Cost metrics ─────────────────────────────────────────────────
    # Stage 1 cost: freq × route_cost for each active route
    s1_dispatch_cost = 0
    for rf in route_freqs:
        key = (rf["from"], rf["to"], rf["tr"])
        cost_per_trip = instance_data["route_cost"].get(key, 0)
        s1_dispatch_cost += rf["freq"] * cost_per_trip

    # Stage 2 actual cost: only count used trips
    trips_per_route: dict[tuple, set] = defaultdict(set)
    for (f, t, tr, p, k), n in stage2["trip_loads"].items():
        trips_per_route[(f, t, tr)].add(k)

    s2_dispatch_cost = 0
    for (f, t, tr), trip_ids in trips_per_route.items():
        cost_per_trip = instance_data["route_cost"].get((f, t, tr), 0)
        s2_dispatch_cost += len(trip_ids) * cost_per_trip

    # Per-route breakdown
    route_freq_savings: list[dict] = []
    for rf in route_freqs:
        key = (rf["from"], rf["to"], rf["tr"])
        s1_freq = rf["freq"]
        s2_freq = len(trips_per_route.get(key, set()))
        cost_per_trip = instance_data["route_cost"].get(key, 0)
        route_freq_savings.append({
            "route": f"{rf['from']}→{rf['to']} via {rf['tr']}",
            "s1_freq": s1_freq,
            "s2_freq": s2_freq,
            "saved_trips": s1_freq - s2_freq,
            "cost_per_trip": cost_per_trip,
            "s1_cost": s1_freq * cost_per_trip,
            "s2_cost": s2_freq * cost_per_trip,
        })

    return {
        "total_trips":       len(counts),
        "non_empty_trips":   len(non_empty_counts),
        "empty_trips":       len(counts) - len(non_empty_counts),
        "mono_sku_trips":    mono_trips,
        "avg_parts_per_trip": round(mean(non_empty_counts), 2) if non_empty_counts else 0,
        "min_parts_per_trip": min(non_empty_counts) if non_empty_counts else 0,
        "max_parts_per_trip": max(non_empty_counts) if non_empty_counts else 0,
        "avg_fill_rate":      round(mean(fill_rates), 3) if fill_rates else 0,
        "min_fill_rate":      round(min(fill_rates), 3) if fill_rates else 0,
        "max_fill_rate":      round(max(fill_rates), 3) if fill_rates else 0,
        "avg_max_part_share": round(mean(max_shares), 3) if max_shares else 0,
        "s1_dispatch_cost":   s1_dispatch_cost,
        "s2_dispatch_cost":   s2_dispatch_cost,
        "cost_saving":        s1_dispatch_cost - s2_dispatch_cost,
        "route_details":      route_freq_savings,
    }


# ─────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────

def print_stage1(stage1: dict) -> None:
    print(f"  Active routes:  {len(stage1['route_freqs'])}")
    print(f"  Non-zero loads: {len(stage1['loads'])}")
    print(f"  Cost:           {stage1.get('cost', '?')}")
    print(f"  Ground time:    {stage1['ground_time']}s")
    print(f"  Total time:     {stage1['total_time']}s")
    print(f"  Optimum proven: {stage1['optimum']}")
    print()

    print("  Aggregate flows:")
    # Group loads by route
    route_loads: dict[tuple, dict] = defaultdict(dict)
    for (f, t, tr, p), n in stage1["loads"].items():
        route_loads[(f, t, tr)][p] = n

    for rf in sorted(stage1["route_freqs"],
                     key=lambda r: (r["from"], r["to"], r["tr"])):
        key = (rf["from"], rf["to"], rf["tr"])
        parts = route_loads.get(key, {})
        parts_str = ", ".join(f"{p}={n}" for p, n in sorted(parts.items()))
        print(f"    {rf['from']}→{rf['to']} via {rf['tr']}  "
              f"freq={rf['freq']}  totalCap={rf['total_cap']}  "
              f"loads=[{parts_str}]")


def print_stage2(stage2: dict, instance_data: dict) -> None:
    print(f"  Ground time:    {stage2['ground_time']}s")
    print(f"  Total time:     {stage2['total_time']}s")
    print(f"  Optimum proven: {stage2['optimum']}")
    print()

    # Group by route, then by trip
    routes: dict[tuple, dict[int, dict]] = defaultdict(lambda: defaultdict(dict))
    for (f, t, tr, p, k), n in stage2["trip_loads"].items():
        routes[(f, t, tr)][k][p] = n

    print("  Per-trip packings:")
    for (f, t, tr) in sorted(routes.keys()):
        n_types = stage2["route_part_types"].get((f, t, tr), "?")
        print(f"    {f}→{t} via {tr}  ({n_types} part types on route)")

        for k in sorted(routes[(f, t, tr)].keys()):
            parts = routes[(f, t, tr)][k]
            items: list[str] = []
            total_vol = 0
            for p, n in sorted(parts.items()):
                size = instance_data["part_size"].get(p, 0)
                vol  = size * n
                total_vol += vol
                items.append(f"{p}×{n} (vol {vol})")

            n_parts = stage2["trip_part_counts"].get((f, t, tr, k), 0)
            print(f"      trip {k}: {', '.join(items)}  "
                  f"| total vol={total_vol}  | {n_parts} part types")
        print()


def print_metrics(metrics: dict) -> None:
    print(f"  Total trips:         {metrics['total_trips']}")
    print(f"  Non-empty trips:     {metrics['non_empty_trips']}")
    print(f"  Empty trips:         {metrics['empty_trips']}")
    print(f"  Mono-SKU trips:      {metrics['mono_sku_trips']}")
    print()
    print(f"  Parts per trip:      "
          f"avg={metrics['avg_parts_per_trip']}  "
          f"min={metrics['min_parts_per_trip']}  "
          f"max={metrics['max_parts_per_trip']}")
    print(f"  Fill rate:           "
          f"avg={metrics['avg_fill_rate']}  "
          f"min={metrics['min_fill_rate']}  "
          f"max={metrics['max_fill_rate']}")
    if metrics["avg_max_part_share"] > 0:
        print(f"  Max part share:      "
              f"avg={metrics['avg_max_part_share']}  (lower = more balanced)")

    print()
    print(f"  Stage 1 dispatch cost:  {metrics['s1_dispatch_cost']}")
    print(f"  Stage 2 actual cost:    {metrics['s2_dispatch_cost']}")
    print(f"  Cost saving:            {metrics['cost_saving']}  "
          f"({round(metrics['cost_saving'] / max(1, metrics['s1_dispatch_cost']) * 100, 1)}%)")
    print()
    print("  Per-route frequency comparison:")
    for rd in metrics["route_details"]:
        saved = f"  (-{rd['saved_trips']})" if rd["saved_trips"] > 0 else ""
        print(f"    {rd['route']:>20}  "
              f"S1: {rd['s1_freq']} trips → S2: {rd['s2_freq']} trips{saved}  "
              f"cost: {rd['s1_cost']} → {rd['s2_cost']}")


# ─────────────────────────────────────────────────────────────────────────
# Full pipeline (callable from ``src.main`` and this module's CLI)
# ─────────────────────────────────────────────────────────────────────────

def run_pipeline(
    instance_path: str | Path,
    *,
    cap_divide: int = 1,
    max_freq: int = 6,
    time_limit: int = 30,
    round_timeout: int = 30,
    show_facts: bool = False,
) -> int:
    """Run in-process clingcon Stage 1 + Stage 2.  Returns exit code (0 = ok)."""
    instance_path = Path(instance_path)
    if not instance_path.exists():
        print(f"Error: instance not found: {instance_path}", file=sys.stderr)
        return 1

    instance_data = load_instance_data(str(instance_path))

    print("═" * 65)
    print("  STAGE 1: Network Flow + Frequency Assignment")
    print("═" * 65)

    stage1 = solve_stage1(
        str(instance_path),
        cap_divide,
        max_freq,
        time_limit,
        round_timeout=round_timeout,
    )

    if stage1 is None:
        print("  UNSATISFIABLE — no feasible flow exists.")
        return 1

    print_stage1(stage1)

    warnings = check_feasibility(stage1, instance_data)
    if warnings:
        print()
        print("─" * 65)
        print("  FEASIBILITY WARNINGS")
        print("─" * 65)
        for w in warnings:
            print(w)
        print()

    facts = build_stage2_facts(stage1, instance_data)

    if show_facts:
        print()
        print("─" * 65)
        print("  STAGE 2 INPUT FACTS")
        print("─" * 65)
        print(facts)
        print()

    print("═" * 65)
    print("  STAGE 2: Per-Trip Bin Packing")
    print("═" * 65)

    stage2 = solve_stage2(facts, time_limit, round_timeout)

    if stage2 is None:
        print("  UNSATISFIABLE — cannot pack loads into individual trips.")
        print("  Check feasibility warnings above, or adjust cap-divide.")
        return 1

    print_stage2(stage2, instance_data)

    print("═" * 65)
    print("  QUALITY METRICS")
    print("═" * 65)

    metrics = compute_metrics(stage2, instance_data, stage1["route_freqs"])
    print_metrics(metrics)

    return 0


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Two-stage logistics optimisation: "
            "Stage 1 solves aggregate network flow, "
            "Stage 2 solves per-trip bin packing with diversification."
        )
    )
    parser.add_argument("--instance", "-i", required=True,
                        help="Path to the instance .lp file")
    parser.add_argument("--cap-divide", type=int, default=1,
                        help="Capacity scaling divisor (default: 1 = exact)")
    parser.add_argument("--max-freq", type=int, default=6,
                        help="Maximum transport frequency (default: 30)")
    parser.add_argument("--time-limit", type=int, default=30,
                        help="Overall time limit per stage in seconds (default: 30)")
    parser.add_argument("--round-timeout", type=int, default=30,
                        help="Per-round timeout for multi-shot solving (default: 120)")
    parser.add_argument("--show-facts", action="store_true",
                        help="Print the Stage 2 input facts")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_pipeline(
        args.instance,
        cap_divide=args.cap_divide,
        max_freq=args.max_freq,
        time_limit=args.time_limit,
        round_timeout=args.round_timeout,
        show_facts=args.show_facts,
    )


if __name__ == "__main__":
    sys.exit(main())
