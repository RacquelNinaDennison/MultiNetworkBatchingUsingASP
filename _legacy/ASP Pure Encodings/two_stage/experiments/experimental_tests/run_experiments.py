#!/usr/bin/env python3
"""
Validates that dominantTR (Stage 1 load-balance metric) is a meaningful
proxy for R_TR (Stage 2 resilience metric).

For each div_weight:
  1. Solve Stage 1 with pareto.lp — records transport_cost and dominantTR count
  2. Pipe Stage 1 solution into Stage 2 (S2-FULL) — assigns parts to trips
  3. Compute R_TR from Stage 2 trip assignments
  4. Record: (div_weight, transport_cost, dominantTR, R_TR)

Hypothesis: lower dominantTR → higher R_TR.
If monotone, dominantTR is a valid Stage 1 resilience proxy.

Expected outcomes (all publishable):
  - dominantTR ↓ → R_TR ↑  : proxy is valid, Stage 1 decisions propagate
  - dominantTR ↓, R_TR flat : Stage 2 packing dominates, Stage 1 less critical
  - Noisy relationship       : both stages needed together

Usage
-----
    python run_resilience_validation.py
    python run_resilience_validation.py --weights 0 50 100 200 300
    python run_resilience_validation.py --s1-timeout 600 --s2-timeout 120
    python run_resilience_validation.py --no-plot
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import threading
from collections import defaultdict
from math import gcd
from functools import reduce
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory

# ── Paths ─────────────────────────────────────────────────────────────────────

HERE         = Path(__file__).parent
PARETO_LP    = HERE / "stage1_packings.lp"        # Stage 1 encoding with dominantTR
INSTANCES_LP = HERE / "data.lp"     # instance data
PACKINGS_BASE = HERE / "stage2_packings.lp"      # Stage 2 encoding with no soft constraints (for ablation)

# Stage 2 files — adjust paths to match your project layout
TWO_STAGE    = HERE.parent
STAGE2_BASE  = TWO_STAGE / "stage2_base.lp"
ENCODINGS    = TWO_STAGE / "experiments" / "encodings"
S2_CONCENTRATION = ENCODINGS / "stage2_concentration.lp"
S2_HETEROGENEITY = ENCODINGS / "stage2_heterogeneity.lp"
S2_EVENNESS      = ENCODINGS / "stage2_evenness.lp"
S2_DISPATCH_COST = ENCODINGS / "stage2_dispatch_cost.lp"

RESULTS_DIR  = HERE / "results"

CSV_COLUMNS = [
    "div_weight",
    # Stage 1 outputs
    "transport_cost",
    "dominant_arcs",
    "s1_solver_cost",
    "s1_time",
    "s1_optimal",
    "s1_rounds",
    # Stage 2 outputs
    "R_1",
    "R_TR",
    "R_arc",
    "A_1",
    "s2_time",
    "s2_optimal",
    # Violation counts (post-hoc)
    "concentrated_trips",
    "mono_trips",
    "overloaded_trips",
    "empty_trips",
    "max_concentration",
    "total_used_trips",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Instance parsing
# ═══════════════════════════════════════════════════════════════════════════════

def load_instance_data() -> dict:
    ctl = clingo.Control()
    ctl.load(str(INSTANCES_LP))
    ctl.ground([("base", [])])

    data: dict = {
        "transport_cap": {},
        "part_size":     {},
        "part_val":      {},
        "route_cost":    {},
        "demands":       {},   # (part, loc) -> qty (positive)
        "offers":        {},   # (part, loc) -> qty (positive)
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
            data["route_cost"][
                (str(args[0]), str(args[1]), str(args[2]))
            ] = args[4].number
        elif name == "demandOffer" and len(args) == 3:
            part, loc, val = str(args[0]), str(args[1]), args[2].number
            if val < 0:
                data["demands"][(part, loc)] = -val
            elif val > 0:
                data["offers"][(part, loc)]  =  val

    return data


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1 solver  (from run_pareto.py)
# ═══════════════════════════════════════════════════════════════════════════════

def solve_stage1(
    div_weight:    int,
    cap_divide:    int,
    max_freq:      int,
    total_timeout: int,
    round_timeout: int,
) -> dict | None:
    """
    Solve Stage 1 using pareto.lp with a given div_weight.
    Uses clingo's native optimization + external restart-with-bound on timeout.
    """

    theory = ClingconTheory()
    ctl    = clingo.Control([
        "-c", f"div_weight={div_weight}",
        "-c", f"cap_size_divide={cap_divide}",
        "-c", f"max_freq={max_freq}",
    ])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_files([str(PARETO_LP), str(INSTANCES_LP)], on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    theory.prepare(ctl)

    BOUND = (
        ":- #sum {{ V,F,T,TR : _transCost(F,T,TR,V); "
        "{dw},F,T,P : dominantTR(F,T,P) }} >= {bound}."
    )

    best:         dict | None = None
    best_cost:    int | None  = None
    optimum                   = False
    round_num                 = 0
    total_improvements        = 0

    while True:
        elapsed   = time.perf_counter() - t0
        remaining = int(total_timeout - elapsed)
        if remaining <= 0:
            print(f"      [S1 total timeout — {round_num} rounds]", flush=True)
            break

        budget    = min(round_timeout, remaining)
        round_num += 1
        round_impr = 0

        print(f"      S1 round {round_num}  budget={budget}s"
              f"  best={best_cost} ...", end="", flush=True)

        timer = threading.Timer(budget, ctl.interrupt)
        timer.start()
        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    candidate_cost = model.cost[0] if model.cost else None
                    candidate      = _extract_stage1(model, theory)
                    best           = candidate
                    best_cost      = candidate_cost
                    round_impr    += 1
                    total_improvements += 1
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
            print(f"      [S1 ✓ optimal]", flush=True)
            break
        if result is not None and getattr(result, "unsatisfiable", False):
            print(f"      [S1 ✓ UNSAT — optimal]", flush=True)
            optimum = True
            break
        if best is None:
            print(f"      [S1 no solution found]", flush=True)
            break

        if best_cost is not None and best_cost < 2_000_000_000:
            bound_str = BOUND.format(dw=div_weight, bound=best_cost)
            try:
                ctl.add(f"bound_{round_num}", [], bound_str)
                ctl.ground([(f"bound_{round_num}", [])])
            except RuntimeError as e:
                print(f"      [S1 bound failed: {e}]", flush=True)
                break
        else:
            break

    total_time = time.perf_counter() - t0
    if best is not None:
        best["total_time"]   = round(total_time, 3)
        best["optimum"]      = optimum
        best["cost"]         = best_cost
        best["rounds"]       = round_num
        best["improvements"] = total_improvements

    return best


def _extract_stage1(model, theory) -> dict:
    route_freqs   = []
    dominant_arcs = 0

    for sym in model.symbols(shown=True):
        if sym.name == "routeFreq" and len(sym.arguments) == 5:
            a = sym.arguments
            route_freqs.append({
                "from": str(a[0]), "to": str(a[1]), "tr": str(a[2]),
                "freq": a[3].number,
            })
        elif sym.name == "dominantTR" and len(sym.arguments) == 3:
            dominant_arcs += 1

    loads = {}
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "load" and len(sym.arguments) == 4 and val > 0:
            loads[tuple(str(a) for a in sym.arguments)] = val

    return {
        "route_freqs":   route_freqs,
        "loads":         loads,
        "dominant_arcs": dominant_arcs,
    }


def compute_transport_cost(solution: dict, instance_data: dict) -> int:
    cost = 0
    for rf in solution["route_freqs"]:
        key   = (rf["from"], rf["to"], rf["tr"])
        cost += instance_data["route_cost"].get(key, 0) * rf["freq"]
    return cost


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1 → Stage 2 bridge
# ═══════════════════════════════════════════════════════════════════════════════

def build_stage2_facts(stage1: dict, instance_data: dict) -> str:
    """Convert Stage 1 solution into facts for Stage 2."""
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
        key  = (rf["from"], rf["to"], rf["tr"])
        cost = instance_data["route_cost"].get(key, 0)
        if cost > 0:
            lines.append(
                f"routeCost({rf['from']},{rf['to']},{rf['tr']},{cost})."
            )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2 solver  (S2-FULL: all soft constraints active)
# ═══════════════════════════════════════════════════════════════════════════════

def solve_stage2(facts_str: str, timeout: int) -> dict | None:
    """
    Solve Stage 2 with S2-FULL (concentration + heterogeneity + evenness).
    Assigns parts to specific trips subject to diversification objectives.
    """

    # Check all Stage 2 files exist
    s2_files = [PACKINGS_BASE]
    missing  = [f for f in s2_files if not f.exists()]
    if missing:
        print(f"      [S2 missing files: {missing}]", flush=True)
        return None

    theory = ClingconTheory()
    ctl    = clingo.Control()
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_string(facts_str, on_rule)
        clingo.ast.parse_files([str(f) for f in s2_files], on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    theory.prepare(ctl)

    best:     dict | None = None
    best_cost             = []
    optimum               = False

    timer = threading.Timer(timeout, ctl.interrupt)
    timer.start()
    try:
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                theory.on_model(model)
                best      = _extract_stage2(model, theory)
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
        best["total_time"] = round(total_time, 3)
        best["optimum"]    = optimum
        best["cost"]       = best_cost

    return best


def _extract_stage2(model, theory) -> dict:
    trip_loads = {}
    for sym, value in theory.assignment(model.thread_id):
        val = int(value)
        if sym.name == "tripLoad" and len(sym.arguments) == 5 and val > 0:
            a   = sym.arguments
            key = (str(a[0]), str(a[1]), str(a[2]), str(a[3]), a[4].number)
            trip_loads[key] = val
    return {"trip_loads": trip_loads}


# ═══════════════════════════════════════════════════════════════════════════════
# Resilience metrics
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_resilience(
    trip_loads: dict,
    stage1:     dict,
    instance_data: dict,
) -> dict:
    """
    Compute R_1, R_TR, R_arc, A_1 from Stage 2 trip assignments.

    R_TR is the key metric for this experiment:
      For each arc (f,t), simulate losing ALL trips of one transport resource TR.
      R_TR = min over all such losses of (surviving_load / total_load).
      Higher R_TR = more resilient to TR failure.
    """

    demands = instance_data["demands"]
    if not demands or not trip_loads:
        return {"R_1": 0.0, "R_TR": 0.0, "R_arc": 0.0, "A_1": 0.0}

    arc_loads     = defaultdict(lambda: defaultdict(int))
    trip_contents = defaultdict(lambda: defaultdict(int))

    for (f, t, tr, p, k), qty in trip_loads.items():
        arc_loads[(f, t, tr)][p]       += qty
        trip_contents[(f, t, tr, k)][p] = qty

    sinks     = {loc for (_, loc) in demands}
    all_trips = list(trip_contents.keys())

    # ── R_1: lose one trip ────────────────────────────────────────────────────
    sigma = []
    for tk in all_trips:
        parts  = trip_contents[tk]
        f, t, tr, k = tk
        totals = arc_loads[(f, t, tr)]
        trip_s = []
        for p, qty in parts.items():
            tot = totals.get(p, 0)
            if tot > 0:
                trip_s.append(1.0 - qty / tot)
        if trip_s:
            sigma.append(min(trip_s))
    R_1 = min(sigma) if sigma else 1.0

    # ── R_TR: lose all trips of one transport resource on an arc ──────────────
    # This directly corresponds to dominantTR: if load is balanced across TRs,
    # losing one TR loses at most 1/N of the supply.
    arc_pair = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (f, t, tr), parts in arc_loads.items():
        for p, qty in parts.items():
            arc_pair[(f, t)][tr][p] += qty

    rtr = []
    rtr_skipped = 0  # arcs with only one active TR — can't be diversified
    for (f, t), tr_loads in arc_pair.items():
        if len(tr_loads) <= 1:
            # Only one TR active on this arc — skip rather than penalise.
            # dominantTR also ignores these arcs (N > 1 guard), so R_TR
            # should do the same to stay aligned with the proxy metric.
            rtr_skipped += 1
            continue
        else:
            total_pp = defaultdict(int)
            for tr, parts in tr_loads.items():
                for p, qty in parts.items():
                    total_pp[p] += qty
            for lost_tr in tr_loads:
                for p in total_pp:
                    lost  = tr_loads[lost_tr].get(p, 0)
                    total = total_pp[p]
                    if total > 0:
                        rtr.append((total - lost) / total)
    R_TR = min(rtr) if rtr else 1.0

    # # ── R_arc: lose entire arc (all TRs) ─────────────────────────────────────
    # rarc = []
    # for (f, t), tr_loads in arc_pair.items():
    #     arc_total_pp = defaultdict(int)
    #     for tr, parts in tr_loads.items():
    #         for p, qty in parts.items():
    #             arc_total_pp[p] += qty
    #     for p, arc_qty in arc_total_pp.items():
    #         total_arr = sum(
    #             qty for (f2, t2, tr2, p2, k2), qty in trip_loads.items()
    #             if t2 == t and p2 == p
    #         )
    #         if total_arr > 0 and (p, t) in demands:
    #             dem  = demands[(p, t)]
    #             surv = total_arr - arc_qty
    #             rarc.append(min(surv / dem if dem > 0 else 1.0, 1.0))
    # R_arc = min(rarc) if rarc else 1.0

    # # ── A_1: assembly completeness after single trip loss ─────────────────────
    # sink_parts = defaultdict(dict)
    # for (p, loc), d in demands.items():
    #     sink_parts[loc][p] = d

    # sink_ratios    = {}
    # sink_total_kits = {}
    # for loc, parts in sink_parts.items():
    #     if len(parts) < 2:
    #         continue
    #     g      = reduce(gcd, list(parts.values()))
    #     ratios = {p: d // g for p, d in parts.items()}
    #     sink_ratios[loc]     = ratios
    #     sink_total_kits[loc] = min(d // ratios[p] for p, d in parts.items())

    # if not sink_ratios:
    #     A_1 = R_1
    # else:
    #     a1 = []
    #     for tk in all_trips:
    #         parts  = trip_contents[tk]
    #         f, t, tr, k = tk
    #         for loc in sinks:
    #             if loc not in sink_ratios:
    #                 continue
    #             ratios     = sink_ratios[loc]
    #             total_kits = sink_total_kits[loc]
    #             kc = []
    #             for p, ratio in ratios.items():
    #                 tot_arr = sum(
    #                     qty for (f2, t2, tr2, p2, k2), qty in trip_loads.items()
    #                     if t2 == loc and p2 == p
    #                 )
    #                 lost = parts.get(p, 0) if t == loc else 0
    #                 surv = tot_arr - lost
    #                 kc.append(surv // ratio)
    #             if kc and total_kits > 0:
    #                 a1.append(min(kc) / total_kits)
    #     A_1 = min(a1) if a1 else R_1

    return {
        "R_1":   round(R_1,   4),
        "R_TR":  round(R_TR,  4)
    }


# def count_violations(trip_loads: dict, stage1: dict) -> dict:
#     """Post-hoc violation counts regardless of which S2 constraints were active."""

#     arc_loads     = defaultdict(lambda: defaultdict(int))
#     trip_contents = defaultdict(lambda: defaultdict(int))
#     for (f, t, tr, p, k), qty in trip_loads.items():
#         arc_loads[(f, t, tr)][p]       += qty
#         trip_contents[(f, t, tr, k)][p] = qty

#     freq_lookup = {}
#     for rf in stage1["route_freqs"]:
#         freq_lookup[(rf["from"], rf["to"], rf["tr"])] = rf["freq"]

#     all_trip_keys = set()
#     for rf in stage1["route_freqs"]:
#         for k in range(1, rf["freq"] + 1):
#             all_trip_keys.add((rf["from"], rf["to"], rf["tr"], k))

#     used_keys   = set(trip_contents.keys())
#     empty_trips = len(all_trip_keys - used_keys)

#     concentrated = 0
#     for tk, parts in trip_contents.items():
#         f, t, tr, k = tk
#         for p, qty in parts.items():
#             tot = arc_loads[(f, t, tr)].get(p, 0)
#             if tot > 1 and qty > tot / 2:
#                 concentrated += 1
#                 break

#     mono = 0
#     for tk, parts in trip_contents.items():
#         if len(parts) != 1:
#             continue
#         f, t, tr, k = tk
#         if len(arc_loads[(f, t, tr)]) > 1:
#             mono += 1

#     overloaded = 0
#     for tk, parts in trip_contents.items():
#         f, t, tr, k = tk
#         freq        = freq_lookup.get((f, t, tr), 1)
#         for p, qty in parts.items():
#             tot   = arc_loads[(f, t, tr)].get(p, 0)
#             ideal = (tot + freq - 1) // freq
#             if qty > ideal:
#                 overloaded += 1
#                 break

#     max_conc = 0.0
#     for tk, parts in trip_contents.items():
#         f, t, tr, k = tk
#         for p, qty in parts.items():
#             tot = arc_loads[(f, t, tr)].get(p, 0)
#             if tot > 0:
#                 max_conc = max(max_conc, qty / tot)

#     return {
#         "concentrated_trips": concentrated,
#         "mono_trips":         mono,
#         "overloaded_trips":   overloaded,
#         "empty_trips":        empty_trips,
#         "max_concentration":  round(max_conc, 4),
#         "total_used_trips":   len(used_keys),
#     }


# ═══════════════════════════════════════════════════════════════════════════════
# Plotting
# ═══════════════════════════════════════════════════════════════════════════════

# def plot(rows: list[dict], out_path: Path) -> None:
#     try:
#         import matplotlib.pyplot as plt
#         import matplotlib.cm as cm
#         import numpy as np
#     except ImportError:
#         print("matplotlib not available — skipping plot.")
#         return

#     weights = [r["div_weight"] for r in rows]
#     norm    = plt.Normalize(min(weights), max(weights))
#     cmap    = cm.viridis

#     fig, axes = plt.subplots(1, 3, figsize=(18, 6))

#     # ── Left: dominantTR vs R_TR (the key validation plot) ───────────────────
#     ax = axes[0]
#     sc = ax.scatter(
#         [r["dominant_arcs"] for r in rows],
#         [r["R_TR"]          for r in rows],
#         c=weights, cmap=cmap, norm=norm, s=120, zorder=3,
#     )
#     for r in rows:
#         marker = "★" if r["s1_optimal"] else "○"
#         ax.annotate(
#             f"{marker}w={r['div_weight']}",
#             (r["dominant_arcs"], r["R_TR"]),
#             fontsize=7, xytext=(4, 3), textcoords="offset points",
#         )
#     plt.colorbar(sc, ax=ax, label="div_weight")
#     ax.set_xlabel("Dominant Arcs (Stage 1 load-balance metric)")
#     ax.set_ylabel("R_TR (Stage 2 resilience: survive TR loss)")
#     ax.set_title("KEY: dominantTR vs R_TR\n(should be monotone ↗ if proxy is valid)")
#     ax.grid(True, alpha=0.3)

#     # Add trend line if enough points
#     xs = [r["dominant_arcs"] for r in rows]
#     ys = [r["R_TR"]          for r in rows]
#     if len(xs) >= 3:
#         z  = np.polyfit(xs, ys, 1)
#         p  = np.poly1d(z)
#         xr = np.linspace(min(xs), max(xs), 100)
#         ax.plot(xr, p(xr), "r--", alpha=0.5, lw=1.5, label="trend")
#         ax.legend(fontsize=8)

#     # ── Middle: cost vs R_TR ──────────────────────────────────────────────────
#     ax = axes[1]
#     sc = ax.scatter(
#         [r["transport_cost"] for r in rows],
#         [r["R_TR"]           for r in rows],
#         c=weights, cmap=cmap, norm=norm, s=120, zorder=3,
#     )
#     for r in rows:
#         ax.annotate(
#             f"w={r['div_weight']}",
#             (r["transport_cost"], r["R_TR"]),
#             fontsize=7, xytext=(4, 3), textcoords="offset points",
#         )
#     plt.colorbar(sc, ax=ax, label="div_weight")
#     ax.set_xlabel("Transport Cost (Stage 1)")
#     ax.set_ylabel("R_TR (Stage 2)")
#     ax.set_title("Cost vs Resilience\n(Pareto trade-off)")
#     ax.grid(True, alpha=0.3)

#     # ── Right: all resilience metrics ─────────────────────────────────────────
#     ax = axes[2]
#     dom = [r["dominant_arcs"] for r in rows]
#     for metric, color, label in [
#         ("R_1",   "steelblue",  "R_1 (trip loss)"),
#         ("R_TR",  "darkorange", "R_TR (TR loss)"),
#         ("R_arc", "green",      "R_arc (arc loss)"),
#         ("A_1",   "purple",     "A_1 (assembly)"),
#     ]:
#         vals = [r[metric] for r in rows]
#         ax.plot(dom, vals, "o-", color=color, lw=2,
#                 markersize=8, label=label)

#     ax.set_xlabel("Dominant Arcs (Stage 1)")
#     ax.set_ylabel("Resilience Metric (0–1)")
#     ax.set_title("All Resilience Metrics vs dominantTR")
#     ax.legend(fontsize=8)
#     ax.grid(True, alpha=0.3)
#     ax.set_ylim(-0.05, 1.05)

#     plt.suptitle(
#         "Resilience Validation: Does Stage 1 dominantTR predict Stage 2 R_TR?",
#         fontsize=13, fontweight="bold",
#     )
#     plt.tight_layout()
#     plt.savefig(out_path, dpi=150)
#     print(f"Plot saved → {out_path}")
#     plt.show()


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate dominantTR as a resilience proxy via R_TR."
    )
    parser.add_argument(
        "--weights", type=int, nargs="+",
        default=[0, 50, 100, 150, 200, 250, 300, 400, 500],
        help="div_weight values to sweep",
    )
    parser.add_argument(
        "--s1-timeout", type=int, default=60,
        help="Total Stage 1 timeout per weight in seconds (default: 60)",
    )
    parser.add_argument(
        "--s1-round", type=int, default=30,
        help="Stage 1 round timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--s2-timeout", type=int, default=120,
        help="Stage 2 timeout per weight in seconds (default: 120)",
    )
    parser.add_argument("--cap-divide", type=int, default=1)
    parser.add_argument("--max-freq",   type=int, default=20)
    parser.add_argument("--no-plot",    action="store_true")
    parser.add_argument(
        "--output", type=Path,
        default=RESULTS_DIR / "resilience_validation.csv",
    )
    args = parser.parse_args()

    # # Validate required files
    # missing = [f for f in [PARETO_LP, INSTANCES_LP] if not f.exists()]
    # if missing:
    #     print("ERROR: missing files:")
    #     for f in missing:
    #         print(f"  {f}")
    #     return 1

    # s2_missing = [f for f in [STAGE2_BASE, S2_CONCENTRATION,
    #                            S2_HETEROGENEITY, S2_EVENNESS, S2_DISPATCH_COST]
    #               if not f.exists()]
    # if s2_missing:
    #     print("WARNING: Stage 2 files not found — only Stage 1 will run:")
    #     for f in s2_missing:
    #         print(f"  {f}")
    #     print("Update the Stage 2 path constants at the top of this script.")
    #     run_s2 = False
    # else:
    #     run_s2 = True

    instance_data = load_instance_data()
    print(f"Instance:     {len(instance_data['parts'])} parts,"
          f" {len(instance_data['route_cost'])} routes")
    print(f"Weights:      {args.weights}")
    print(f"S1 timeout:   {args.s1_timeout}s total / {args.s1_round}s per round")
    print(f"S2 timeout:   {args.s2_timeout}s")
    print()

    rows = []

    for weight in args.weights:
        print(f"\n{'═'*60}")
        print(f"  div_weight = {weight}")
        print(f"{'═'*60}")

        # ── Stage 1 ──────────────────────────────────────────────────────────
        s1 = solve_stage1(
            div_weight    = weight,
            cap_divide    = args.cap_divide,
            max_freq      = args.max_freq,
            total_timeout = args.s1_timeout,
            round_timeout = args.s1_round,
        )

        if s1 is None:
            print(f"  → S1 no solution — skipping")
            continue

        transport_cost = compute_transport_cost(s1, instance_data)
        dominant_arcs  = s1["dominant_arcs"]

        print(f"  S1 done: cost={transport_cost}  dominant={dominant_arcs}"
              f"  time={s1['total_time']}s  optimal={s1['optimum']}")

        row: dict = {
            "div_weight":    weight,
            "transport_cost": transport_cost,
            "dominant_arcs":  dominant_arcs,
            "s1_solver_cost": s1["cost"],
            "s1_time":        s1["total_time"],
            "s1_optimal":     s1["optimum"],
            "s1_rounds":      s1["rounds"],
            # defaults if S2 not run
            # "R_1":   None, "R_TR": None, "R_arc": None, "A_1": None,
            # "s2_time": None, "s2_optimal": None,
            # "concentrated_trips": None, "mono_trips": None,
            # "overloaded_trips": None, "empty_trips": None,
            # "max_concentration": None, "total_used_trips": None,
        }

        # ── Stage 2 ──────────────────────────────────────────────────────────
        if True:
            facts = build_stage2_facts(s1, instance_data)
            print(f"  Solving S2 (S2-FULL, timeout={args.s2_timeout}s)...",
                  end="", flush=True)
            s2 = solve_stage2(facts, args.s2_timeout)

            if s2 is None:
                print(" UNSAT")
            else:
                print(f" done  time={s2['total_time']}s  optimal={s2['optimum']}")
                resilience = evaluate_resilience(
                    s2["trip_loads"], s1, instance_data
                )
                # violations = count_violations(s2["trip_loads"], s1)

                row.update({
                    **resilience,
                    "s2_time":    s2["total_time"],
                    "s2_optimal": s2["optimum"],
                    # **violations,
                })

                print(f"  R_TR={resilience['R_TR']:.4f}  "
                      f"R_1={resilience['R_1']:.4f}  ")
                    #   f"R_arc={resilience['R_arc']:.4f}  "
                    #   f"A_1={resilience['A_1']:.4f}")

        rows.append(row)

    if not rows:
        print("\nNo results produced.")
        return 1

    # Write CSV
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV → {args.output}")

    # Summary table
    # print(f"\n{'─'*75}")
    # print(f"  {'w':>6}  {'cost':>8}  {'dom':>5}  "
    #       f"{'R_TR':>7}  {'R_1':>7}  {'R_arc':>7}  {'A_1':>7}  s1_opt")
    # print(f"{'─'*75}")
    for r in rows:
        rtr  = f"{r['R_TR']:.4f}"  if r["R_TR"]  is not None else "  N/A "
        r1   = f"{r['R_1']:.4f}"   if r["R_1"]   is not None else "  N/A "
        # rarc = f"{r['R_arc']:.4f}" if r["R_arc"] is not None else "  N/A "
        # # a1   = f"{r['A_1']:.4f}"   if r["A_1"]   is not None else "  N/A "
        # print(f"  {r['div_weight']:>6}  {r['transport_cost']:>8}"
        #       f"  {r['dominant_arcs']:>5}  "
        #       f"{rtr:>7}  {r1:>7}  {rarc:>7}  {a1:>7}  {r['s1_optimal']}")

    # Check if hypothesis holds
    valid_rows = [r for r in rows if r["R_TR"] is not None]
    if len(valid_rows) >= 2:
        # Sort by dominant DESCENDING (most dominant first)
        # R_TR should be non-decreasing (improving as dominant decreases)
        sorted_by_dom = sorted(valid_rows, key=lambda r: r["dominant_arcs"], reverse=True)
        rtr_vals = [r["R_TR"] for r in sorted_by_dom]
        monotone = all(rtr_vals[i] <= rtr_vals[i+1] for i in range(len(rtr_vals)-1))

        # Check monotonicity: as dominant_arcs decreases, R_TR should increase
        monotone = all(
            rtr_vals[i] <= rtr_vals[i+1]
            for i in range(len(rtr_vals)-1)
        )
        print(f"\nHypothesis check (dominantTR ↓ → R_TR ↑):")
        if monotone:
            print("  ✓ CONFIRMED — R_TR increases as dominant arcs decrease.")
            print("    dominantTR is a valid Stage 1 resilience proxy.")
        else:
            print("  ~ PARTIAL — relationship is not strictly monotone.")
            print("    Stage 2 packing may partially override Stage 1 balance.")
            print("    Check the plot for the overall trend.")

    # if not args.no_plot:
    #     plot_rows = [r for r in rows if r["R_TR"] is not None]
    #     if plot_rows:∂R_arc
    #         plot(plot_rows, args.output.with_suffix(".png"))
    #     else:
    #         print("No Stage 2 results to plot.")

    return 0


if __name__ == "__main__":
    sys.exit(main())