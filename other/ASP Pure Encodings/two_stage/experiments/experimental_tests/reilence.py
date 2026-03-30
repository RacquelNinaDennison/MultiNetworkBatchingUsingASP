#!/usr/bin/env python3
"""
run_resilience_validation.py
============================

Validates that dominantTR (Stage 1 load-balance metric) is a meaningful
proxy for R_TR — the fraction of total demand satisfiable after a transport
resource fails, with optimal rerouting through the surviving network.

For each div_weight:
  1. Solve Stage 1 (stage1_packings.lp + data.lp)
  2. For every active (F, T, TR) arc, simulate that TR failing
  3. Build the surviving flow network for each part P
  4. Solve max-flow from super-source to super-sink
  5. R_TR = min over all (F,T,TR) and all P of (maxflow / total_demand)

Hypothesis: fewer dominantTR arcs → higher R_TR

Usage
-----
    python run_resilience_validation.py
    python run_resilience_validation.py --weights 0 50 100 200 300 500 1000
    python run_resilience_validation.py --s1-timeout 300 --s1-round 60
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import threading
from collections import defaultdict
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory

# ── Paths ─────────────────────────────────────────────────────────────────────

HERE         = Path(__file__).parent
PARETO_LP    = HERE / "stage1_packings.lp"
INSTANCES_LP = HERE / "data.lp"
RESULTS_DIR  = HERE / "results"

CSV_COLUMNS = [
    "div_weight",
    "transport_cost",
    "dominant_arcs",
    "s1_solver_cost",
    "s1_time",
    "s1_optimal",
    "s1_rounds",
    "R_TR",
    # Per-(F,T,TR) breakdown columns written to separate details CSV
]


# ═══════════════════════════════════════════════════════════════════════════════
# Instance parsing
# ═══════════════════════════════════════════════════════════════════════════════

def load_instance_data() -> dict:
    """
    Parse instance facts from data.lp.

    Extracts:
      offers:   (part, loc) -> qty    from demandOffer where val > 0
      demands:  (part, loc) -> qty    from demandOffer where val < 0
      parts:    set of part names
    """
    ctl = clingo.Control()
    ctl.load(str(INSTANCES_LP))
    ctl.ground([("base", [])])

    data: dict = {
        "transport_cap": {},
        "part_size":     {},
        "part_val":      {},
        "route_cost":    {},
        "demands":       {},
        "offers":        {},
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
                data["offers"][(part, loc)] = val

    return data


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1 solver
# ═══════════════════════════════════════════════════════════════════════════════

def solve_stage1(
    div_weight:    int,
    cap_divide:    int,
    max_freq:      int,
    total_timeout: int,
    round_timeout: int,
) -> dict | None:
    """
    Solve Stage 1 for one div_weight value.
    Uses clingo's native optimization within each round + external
    restart-with-bound when a round times out.
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

    # Bound on combined objective: transport_cost + div_weight × dominant_arcs
    BOUND = (
        ":- #sum {{ V,F,T,TR : _transCost(F,T,TR,V); "
        "{dw},F,T,P : dominantTR(F,T,P) }} >= {bound}."
    )

    best:      dict | None = None
    best_cost: int | None  = None
    optimum                = False
    round_num              = 0
    total_impr             = 0

    while True:
        elapsed   = time.perf_counter() - t0
        remaining = int(total_timeout - elapsed)
        if remaining <= 0:
            print(f"      [S1 timeout — {round_num} rounds,"
                  f" {total_impr} improvements]", flush=True)
            break

        budget    = min(round_timeout, remaining)
        round_num += 1

        print(f"      round {round_num:>2}  budget={budget}s"
              f"  best={best_cost} ...", end="", flush=True)

        timer = threading.Timer(budget, ctl.interrupt)
        timer.start()
        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    candidate_cost = model.cost[0] if model.cost else None
                    candidate      = _extract_stage1(model, theory)
                    # clingo yields in strictly improving order within a round
                    best           = candidate
                    best_cost      = candidate_cost
                    total_impr    += 1
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
            print(f"      [✓ optimal]", flush=True)
            break
        if result is not None and getattr(result, "unsatisfiable", False):
            print(f"      [✓ UNSAT — optimal]", flush=True)
            optimum = True
            break
        if best is None:
            print(f"      [no solution found]", flush=True)
            break

        # Add hard bound: next round must find strictly better combined obj
        if best_cost is not None and best_cost < 2_000_000_000:
            try:
                ctl.add(f"bound_{round_num}", [],
                        BOUND.format(dw=div_weight, bound=best_cost))
                ctl.ground([(f"bound_{round_num}", [])])
            except RuntimeError as e:
                print(f"      [bound failed: {e}]", flush=True)
                break
        else:
            break

    total_time = time.perf_counter() - t0
    if best is not None:
        best["total_time"] = round(total_time, 3)
        best["optimum"]    = optimum
        best["cost"]       = best_cost
        best["rounds"]     = round_num
        best["improvements"] = total_impr

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
# R_TR via max-flow
# ═══════════════════════════════════════════════════════════════════════════════

def compute_r_tr(loads: dict, instance_data: dict) -> tuple[float, list[dict]]:
    """
    Compute R_TR = min over all (F,T,TR) disruptions and all parts P of:

        maxflow(N_P^(F,T,TR), S, T) / total_demand(P)

    where N_P^(F,T,TR) is the flow network for part P after TR fails on arc (F,T):
      - super-source S → each offer node L  with capacity = offer(P, L)
      - arc (F'→T') via TR'                 with capacity = load(F',T',TR',P)
                                             EXCEPT cap = 0 if (F',T',TR') = (F,T,TR)
      - each demand node L → super-sink T   with capacity = demand(P, L)

    R_TR answers: "if TR fails between F and T, what is the maximum fraction
    of total demand that can still be satisfied by optimally rerouting supply
    through the surviving network?"

    Returns:
      r_tr:    float in [0,1] — worst case over all disruptions and parts
      details: list of dicts, one per (lost_f, lost_t, lost_tr, part) scenario
    """
    try:
        from scipy.sparse.csgraph import maximum_flow
        from scipy.sparse import csr_matrix
    except ImportError:
        raise ImportError(
            "scipy is required for max-flow. Install with: pip install scipy"
        )

    demands = instance_data["demands"]   # {(part, loc): qty}
    offers  = instance_data["offers"]    # {(part, loc): qty}
    parts   = sorted(instance_data["parts"])

    if not demands or not loads:
        return 1.0, []

    # ── Build node index ──────────────────────────────────────────────────────
    # Collect all locations that appear in the Stage 1 load assignments
    all_locs = sorted(
        set(f for (f, t, tr, p) in loads) |
        set(t for (f, t, tr, p) in loads)
    )
    loc_idx = {loc: i for i, loc in enumerate(all_locs)}
    N       = len(all_locs)

    # super_source = N, super_sink = N+1
    S_NODE = N
    T_NODE = N + 1
    N_NODES = N + 2

    # ── Total demand per part (denominator of coverage fraction) ──────────────
    total_demand: dict = {}
    for p in parts:
        total_demand[p] = sum(
            qty for (part, loc), qty in demands.items() if part == p
        )

    # ── Find all active (F, T, TR) arcs in Stage 1 solution ──────────────────
    active_arcs = sorted(set(
        (f, t, tr) for (f, t, tr, p) in loads
    ))

    details: list  = []
    all_coverages: list = []

    for (lost_f, lost_t, lost_tr) in active_arcs:

        for p in parts:

            if total_demand.get(p, 0) == 0:
                continue

            # ── Build integer capacity matrix ─────────────────────────────────
            # Scale by 1000 to preserve precision with integer max-flow solver
            SCALE = 1000
            cap   = [[0] * N_NODES for _ in range(N_NODES)]

            # Super-source S → offer nodes
            # cap(S → L) = offer(P, L) × SCALE
            for (part, loc), qty in offers.items():
                if part == p and loc in loc_idx:
                    cap[S_NODE][loc_idx[loc]] += int(qty * SCALE)

            # Demand nodes → super-sink T
            # cap(L → T) = demand(P, L) × SCALE
            for (part, loc), qty in demands.items():
                if part == p and loc in loc_idx:
                    cap[loc_idx[loc]][T_NODE] += int(qty * SCALE)

            # Internal arc capacities: load(F', T', TR', P)
            # EXCEPT: set to 0 if (F', T', TR') = (lost_f, lost_t, lost_tr)
            # This is the cap_D function from the formal definition
            for (f, t, tr, part), qty in loads.items():
                if part != p:
                    continue
                if f not in loc_idx or t not in loc_idx:
                    continue

                # Apply disruption: zero out the failed arc-TR combination
                if (f, t, tr) == (lost_f, lost_t, lost_tr):
                    arc_cap = 0   # this TR on this arc has failed
                else:
                    arc_cap = int(qty * SCALE)

                cap[loc_idx[f]][loc_idx[t]] += arc_cap

            # ── Solve max-flow ────────────────────────────────────────────────
            graph      = csr_matrix(cap)
            result     = maximum_flow(graph, S_NODE, T_NODE)
            max_supply = result.flow_value / SCALE

            # Coverage = max achievable supply / total demand for this part
            coverage = round(
                min(max_supply / total_demand[p], 1.0), 4
            )

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

    # R_TR = worst case coverage over all disruptions and all parts
    r_tr = round(min(all_coverages), 4) if all_coverages else 1.0
    return r_tr, details


# ═══════════════════════════════════════════════════════════════════════════════
# Plotting
# ═══════════════════════════════════════════════════════════════════════════════

def plot(rows: list[dict], out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import numpy as np
    except ImportError:
        print("matplotlib not available — skipping plot.")
        return

    weights = [r["div_weight"] for r in rows]
    norm    = plt.Normalize(min(weights), max(weights))
    cmap    = cm.viridis

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # ── Left: dominant_arcs vs R_TR — the hypothesis test ────────────────────
    ax = axes[0]
    sc = ax.scatter(
        [r["dominant_arcs"] for r in rows],
        [r["R_TR"]          for r in rows],
        c=weights, cmap=cmap, norm=norm, s=120, zorder=3,
    )
    for r in rows:
        marker = "★" if r["s1_optimal"] else "○"
        ax.annotate(
            f"{marker} w={r['div_weight']}",
            (r["dominant_arcs"], r["R_TR"]),
            fontsize=7, xytext=(4, 3), textcoords="offset points",
        )
    # Trend line
    xs = [r["dominant_arcs"] for r in rows]
    ys = [r["R_TR"]          for r in rows]
    if len(set(xs)) > 1:
        z  = np.polyfit(xs, ys, 1)
        xr = np.linspace(min(xs), max(xs), 100)
        ax.plot(xr, np.poly1d(z)(xr), "r--",
                alpha=0.6, lw=1.5, label="trend")
        ax.legend(fontsize=8)
    plt.colorbar(sc, ax=ax, label="div_weight")
    ax.set_xlabel("Dominant Arcs  (Stage 1 metric)")
    ax.set_ylabel("R_TR  (max-flow, optimal rerouting)")
    ax.set_title(
        "Hypothesis: dominantTR ↓ → R_TR ↑\n"
        "(★ = proven optimal, ○ = best found)"
    )
    ax.grid(True, alpha=0.3)

    # ── Right: transport_cost vs R_TR — the Pareto trade-off ─────────────────
    ax = axes[1]
    sc = ax.scatter(
        [r["transport_cost"] for r in rows],
        [r["R_TR"]           for r in rows],
        c=weights, cmap=cmap, norm=norm, s=120, zorder=3,
    )
    for r in rows:
        ax.annotate(
            f"w={r['div_weight']}",
            (r["transport_cost"], r["R_TR"]),
            fontsize=7, xytext=(4, 3), textcoords="offset points",
        )
    plt.colorbar(sc, ax=ax, label="div_weight")
    ax.set_xlabel("Transport Cost")
    ax.set_ylabel("R_TR  (max-flow)")
    ax.set_title("Cost vs Resilience  (Pareto trade-off)")
    ax.grid(True, alpha=0.3)

    plt.suptitle(
        "R_TR = min_P [ maxflow(N_P^(F,T,TR), S, T) / total_demand(P) ]\n"
        "Worst case over all active (F, T, TR) disruptions",
        fontsize=11,
    )
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"Plot saved → {out_path}")
    plt.show()


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate dominantTR as a proxy for R_TR (max-flow)."
    )
    parser.add_argument(
        "--weights", type=int, nargs="+",
        default=[0, 50, 100, 200, 300, 500, 1000],
    )
    parser.add_argument(
        "--s1-timeout", type=int, default=300,
        help="Total Stage 1 budget per weight in seconds (default: 300)",
    )
    parser.add_argument(
        "--s1-round", type=int, default=60,
        help="Per-round timeout within Stage 1 (default: 60)",
    )
    parser.add_argument("--cap-divide", type=int, default=1)
    parser.add_argument("--max-freq",   type=int, default=20)
    parser.add_argument("--no-plot",    action="store_true")
    parser.add_argument(
        "--output", type=Path,
        default=RESULTS_DIR / "resilience_validation.csv",
    )
    args = parser.parse_args()

    # Validate required files
    for f in [PARETO_LP, INSTANCES_LP]:
        if not f.exists():
            print(f"ERROR: {f} not found")
            return 1

    instance_data = load_instance_data()

    # Print instance summary
    sinks  = sorted(set(loc for (_, loc) in instance_data["demands"]))
    sources = sorted(set(loc for (_, loc) in instance_data["offers"]))
    print(f"Instance:      {len(instance_data['parts'])} parts,"
          f" {len(instance_data['route_cost'])} routes")
    print(f"Offer nodes:   {sources}")
    print(f"Demand nodes:  {sinks}")
    for p in sorted(instance_data["parts"]):
        td = sum(q for (part, _), q in instance_data["demands"].items()
                 if part == p)
        print(f"  total_demand({p}) = {td}")
    print(f"Weights:       {args.weights}")
    print(f"S1 timeout:    {args.s1_timeout}s total / {args.s1_round}s per round")
    print()

    rows        = []
    all_details = []

    for weight in args.weights:
        print(f"\n{'═'*65}")
        print(f"  div_weight = {weight}")
        print(f"{'═'*65}")

        # ── Stage 1 ──────────────────────────────────────────────────────────
        s1 = solve_stage1(
            weight, args.cap_divide, args.max_freq,
            args.s1_timeout, args.s1_round,
        )
        if s1 is None:
            print("  → no Stage 1 solution")
            continue

        transport_cost = compute_transport_cost(s1, instance_data)
        dominant_arcs  = s1["dominant_arcs"]

        print(f"\n  S1 result:")
        print(f"    transport_cost = {transport_cost}")
        print(f"    dominant_arcs  = {dominant_arcs}")
        print(f"    solver_obj     = {s1['cost']}")
        print(f"    time           = {s1['total_time']}s")
        print(f"    optimal        = {s1['optimum']}")

        # ── R_TR via max-flow ─────────────────────────────────────────────────
        print(f"\n  Computing R_TR (max-flow over all active (F,T,TR) arcs)...")
        r_tr, details = compute_r_tr(s1["loads"], instance_data)

        # Print per-scenario breakdown
        print(f"\n  {'lost_arc':<20}  {'part':<5}  "
              f"{'max_flow':>10}  {'demand':>8}  {'coverage':>10}")
        print(f"  {'─'*60}")
        for d in sorted(details, key=lambda x: x["coverage"]):
            arc = f"({d['lost_f']},{d['lost_t']},{d['lost_tr']})"
            print(f"  {arc:<20}  {d['part']:<5}  "
                  f"{d['max_flow']:>10.2f}  {d['demand']:>8}  "
                  f"{d['coverage']:>10.4f}")

        print(f"\n  R_TR = {r_tr}  "
              f"(worst case: lose "
              f"{min(details, key=lambda d: d['coverage'])['lost_tr']} on "
              f"({min(details, key=lambda d: d['coverage'])['lost_f']},"
              f"{min(details, key=lambda d: d['coverage'])['lost_t']}), "
              f"part {min(details, key=lambda d: d['coverage'])['part']})")

        # Annotate details with weight for CSV
        for d in details:
            all_details.append({"div_weight": weight, **d})

        rows.append({
            "div_weight":     weight,
            "transport_cost": transport_cost,
            "dominant_arcs":  dominant_arcs,
            "s1_solver_cost": s1["cost"],
            "s1_time":        s1["total_time"],
            "s1_optimal":     s1["optimum"],
            "s1_rounds":      s1["rounds"],
            "R_TR":           r_tr,
        })

    if not rows:
        print("\nNo results produced.")
        return 1

    # ── Write CSVs ────────────────────────────────────────────────────────────
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResults CSV  → {args.output}")

    detail_path = args.output.with_stem(args.output.stem + "_details")
    detail_cols = ["div_weight", "lost_f", "lost_t", "lost_tr",
                   "part", "max_flow", "demand", "coverage"]
    with open(detail_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=detail_cols)
        writer.writeheader()
        writer.writerows(all_details)
    print(f"Details CSV  → {detail_path}")

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  {'w':>6}  {'cost':>8}  {'dominant':>10}  {'R_TR':>8}  optimal")
    print(f"{'─'*60}")
    for r in rows:
        print(f"  {r['div_weight']:>6}  {r['transport_cost']:>8}"
              f"  {r['dominant_arcs']:>10}  {r['R_TR']:>8.4f}"
              f"  {r['s1_optimal']}")

    # ── Hypothesis check ──────────────────────────────────────────────────────
    if len(rows) >= 2:
        # Sort by dominant_arcs DESCENDING
        # As dominant_arcs decreases, R_TR should increase
        by_dom   = sorted(rows, key=lambda r: r["dominant_arcs"], reverse=True)
        dom_vals = [r["dominant_arcs"] for r in by_dom]
        rtr_vals = [r["R_TR"]          for r in by_dom]

        monotone = all(
            rtr_vals[i] <= rtr_vals[i+1]
            for i in range(len(rtr_vals) - 1)
        )

        print(f"\nHypothesis: dominantTR ↓  →  R_TR ↑")
        print(f"  dominant (desc): {dom_vals}")
        print(f"  R_TR:            {rtr_vals}")
        if monotone:
            print("  ✓ CONFIRMED — strictly monotone.")
            print("    dominantTR is a valid proxy for network resilience R_TR.")
        else:
            print("  ~ PARTIAL — not strictly monotone.")
            print("    Likely due to suboptimal Stage 1 solutions (timeout).")
            print("    Increase --s1-timeout and rerun.")

    if not args.no_plot:
        plot(rows, args.output.with_suffix(".png"))

    return 0


if __name__ == "__main__":
    sys.exit(main())