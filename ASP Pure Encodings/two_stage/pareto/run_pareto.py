#!/usr/bin/env python3
"""
run_pareto.py — Pareto sweep: transport cost vs load-balanced diversification
=============================================================================

For each div_weight, solves pareto.lp + instances.lp and records:
  - transport_cost   : post-hoc sum of route_cost × freq
  - dominant_arcs    : count of dominantTR atoms from the solver
                       (arcs where max single-TR load > total/N fair share)

These two values form the Pareto front axes.

Usage
-----
    python run_pareto.py
    python run_pareto.py --weights 0 50 100 200 300 400 500
    python run_pareto.py --timeout 300 --no-plot
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
PARETO_LP    = HERE / "pareto.lp"
INSTANCES_LP = HERE / "instances.lp"
RESULTS_DIR  = HERE / "results"

CSV_COLUMNS = [
    "div_weight",
    "transport_cost",   # post-hoc: sum(route_cost × freq)
    "dominant_arcs",    # solver: count of dominantTR atoms
    "solver_cost",      # raw combined objective value from solver
    "solve_time",
    "optimal",
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
        "route_cost":    {},
        "parts":         set(),
    }
    for atom in ctl.symbolic_atoms:
        sym, name, args = atom.symbol, atom.symbol.name, atom.symbol.arguments
        if name == "transportCapacity" and len(args) == 2:
            data["transport_cap"][str(args[0])] = args[1].number
        elif name == "partSize" and len(args) == 2:
            data["part_size"][str(args[0])] = args[1].number
        elif name == "part" and len(args) == 1:
            data["parts"].add(str(args[0]))
        elif name == "route" and len(args) == 5:
            data["route_cost"][(str(args[0]), str(args[1]), str(args[2]))] = args[4].number

    return data


# ═══════════════════════════════════════════════════════════════════════════════
# Solver
# ═══════════════════════════════════════════════════════════════════════════════

def solve(div_weight: int, cap_divide: int, max_freq: int, timeout: int) -> dict | None:
    """
    Solve for one div_weight value.
    Returns dict with route_freqs, loads, dominant_arcs count, solver metadata.
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

    best: dict | None = None
    best_cost: int | None = None
    optimum = False

    # Tighten on transport cost between rounds
    BOUND = ":- #sum {{ V,F,T,TR : _transCost(F,T,TR,V) }} >= {bound}."
    for round_num in range(1, 21):
        elapsed   = time.perf_counter() - t0
        remaining = int(timeout - elapsed)
        if remaining <= 0:
            break

        found: dict | None = None
        found_cost: int | None = None

        timer = threading.Timer(remaining, ctl.interrupt)
        timer.start()
        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    found      = _extract(model, theory)
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
            best, best_cost = found, found_cost
            break
        if result is not None and getattr(result, "unsatisfiable", False):
            optimum = True
            break
        if found is None:
            break

        best, best_cost = found, found_cost

        if best_cost is not None and best_cost < 2_000_000_000:
            try:
                ctl.add(f"bound_{round_num}", [], BOUND.format(bound=best_cost))
                ctl.ground([(f"bound_{round_num}", [])])
            except RuntimeError:
                break
        else:
            break

    total_time = time.perf_counter() - t0

    if best is not None:
        best["total_time"] = round(total_time, 3)
        best["optimum"]    = optimum
        best["cost"]       = best_cost

    return best


def _extract(model, theory) -> dict:
    """
    Pull route_freqs, loads, and dominantTR count directly from the model.
    dominantTR atoms are shown by pareto.lp so we just count them here —
    no need to recompute post-hoc.
    """
    route_freqs   = []
    dominant_arcs = 0   # count of dominantTR(F,T,P) atoms in this model

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
        "dominant_arcs": dominant_arcs,  # direct from solver
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Post-hoc transport cost  (the other Pareto axis)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_transport_cost(solution: dict, instance_data: dict) -> int:
    """Sum of route_cost × freq across all active arcs."""
    cost = 0
    for rf in solution["route_freqs"]:
        key   = (rf["from"], rf["to"], rf["tr"])
        cost += instance_data["route_cost"].get(key, 0) * rf["freq"]
    return cost


# ═══════════════════════════════════════════════════════════════════════════════
# Pareto filtering
# ═══════════════════════════════════════════════════════════════════════════════

def filter_pareto(rows: list[dict]) -> list[dict]:
    """Non-dominated set minimising (transport_cost, dominant_arcs)."""
    pareto = []
    for r in rows:
        if not any(
            o is not r
            and o["transport_cost"] <= r["transport_cost"]
            and o["dominant_arcs"]  <= r["dominant_arcs"]
            and (o["transport_cost"] < r["transport_cost"]
                 or o["dominant_arcs"] < r["dominant_arcs"])
            for o in rows
        ):
            pareto.append(r)
    return sorted(pareto, key=lambda r: r["dominant_arcs"])


# ═══════════════════════════════════════════════════════════════════════════════
# Plotting
# ═══════════════════════════════════════════════════════════════════════════════

def plot(all_rows: list[dict], pareto_rows: list[dict], out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
    except ImportError:
        print("matplotlib not available — skipping plot.")
        return

    weights = [r["div_weight"] for r in all_rows]
    norm    = plt.Normalize(min(weights), max(weights))
    cmap    = cm.viridis

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # ── Left: all points coloured by weight ──────────────────────────────────
    ax = axes[0]
    sc = ax.scatter(
        [r["transport_cost"] for r in all_rows],
        [r["dominant_arcs"]  for r in all_rows],
        c=weights, cmap=cmap, norm=norm, s=100, zorder=3,
    )
    for r in all_rows:
        ax.annotate(
            f"w={r['div_weight']}",
            (r["transport_cost"], r["dominant_arcs"]),
            fontsize=7, xytext=(4, 3), textcoords="offset points",
        )
    plt.colorbar(sc, ax=ax, label="div_weight")
    ax.set_xlabel("Transport Cost  (post-hoc: Σ route_cost × freq)")
    ax.set_ylabel("Dominant Arcs  (solver: count of dominantTR atoms)")
    ax.set_title("All weight values")
    ax.grid(True, alpha=0.3)

    # ── Right: Pareto front only ──────────────────────────────────────────────
    ax = axes[1]
    # Grey background: all dominated points
    ax.scatter(
        [r["transport_cost"] for r in all_rows],
        [r["dominant_arcs"]  for r in all_rows],
        c="lightsteelblue", s=70, zorder=2, label="dominated",
    )
    # Blue line: Pareto front
    if pareto_rows:
        px = [r["transport_cost"] for r in pareto_rows]
        py = [r["dominant_arcs"]  for r in pareto_rows]
        ax.plot(px, py, "o-", color="steelblue", lw=2.5,
                markersize=10, zorder=4, label=f"Pareto ({len(pareto_rows)} pts)")
        for r in pareto_rows:
            ax.annotate(
                f"w={r['div_weight']}\n({r['transport_cost']}, {r['dominant_arcs']})",
                (r["transport_cost"], r["dominant_arcs"]),
                fontsize=8, fontweight="bold",
                xytext=(6, 4), textcoords="offset points",
            )

    ax.set_xlabel("Transport Cost  (post-hoc: Σ route_cost × freq)")
    ax.set_ylabel("Dominant Arcs  (solver: count of dominantTR atoms)")
    ax.set_title("Pareto Front  (non-dominated points)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.suptitle(
        "Stage 1 Pareto Sweep: Transport Cost vs Load-Balanced Diversification",
        fontsize=13, fontweight="bold",
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
        description="Pareto sweep: transport cost vs load-balanced diversification."
    )
    parser.add_argument(
        "--weights", type=int, nargs="+",
        default=list(range(0, 11, 10)),
        help="div_weight values to sweep (default: 0 50 100 … 500)",
    )
    parser.add_argument(
        "--timeout", type=int, default=10,
        help="Solver timeout per weight in seconds (default: 180)",
    )
    parser.add_argument(
        "--cap-divide", type=int, default=1,
        help="Capacity scaling divisor (default: 1)",
    )
    parser.add_argument(
        "--max-freq", type=int, default=20,
        help="Maximum transport frequency (default: 20)",
    )
    parser.add_argument(
        "--no-plot", action="store_true",
        help="Skip plot, write CSV only",
    )
    parser.add_argument(
        "--output", type=Path,
        default=RESULTS_DIR / "pareto_sweep.csv",
        help="Output CSV path (default: results/pareto_sweep.csv)",
    )
    args = parser.parse_args()

    for f in [PARETO_LP, INSTANCES_LP]:
        if not f.exists():
            print(f"ERROR: {f} not found in {HERE}")
            return 1

    instance_data = load_instance_data()
    print(f"Instance: {len(instance_data['parts'])} parts, "
          f"{len(instance_data['route_cost'])} routes")
    print(f"Sweeping weights: {args.weights}")
    print(f"Timeout per weight: {args.timeout}s")
    print()
    print(f"  {'weight':>7}  {'cost':>8}  {'dominant':>10}  "
          f"{'solver_obj':>12}  {'time':>6}  optimal")
    print("  " + "-" * 62)

    rows = []
    for weight in args.weights:
        sol = solve(weight, args.cap_divide, args.max_freq, args.timeout)

        if sol is None:
            print(f"  {weight:>7}  UNSAT — skipped")
            continue

        transport_cost = compute_transport_cost(sol, instance_data)
        print(transport_cost)
        dominant_arcs  = sol["dominant_arcs"]   # direct from solver atoms
        print(dominant_arcs)
        row = {
            "div_weight":     weight,
            "transport_cost": transport_cost,
            "dominant_arcs":  dominant_arcs,
            "solver_cost":    sol["cost"],
            "solve_time":     sol["total_time"],
            "optimal":        sol["optimum"],
        }
        rows.append(row)

        print(f"  {weight:>7}  {transport_cost:>8}  {dominant_arcs:>10}  "
              f"{sol['cost']:>12}  {sol['total_time']:>5.1f}s  {sol['optimum']}")

    if not rows:
        print("\nNo results produced — check pareto.lp and instances.lp.")
        return 1

    # # Write CSV
    # args.output.parent.mkdir(parents=True, exist_ok=True)
    # with open(args.output, "w", newline="") as f:
    #     writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    #     writer.writeheader()
    #     writer.writerows(rows)
    # print(f"\nCSV → {args.output}")

    # # Pareto summary
    # pareto = filter_pareto(rows)
    # print(f"\nPareto-optimal points: {len(pareto)} / {len(rows)}")
    # print(f"  {'weight':>8}  {'cost':>8}  {'dominant':>10}  optimal")
    # for r in pareto:
    #     print(f"  {r['div_weight']:>8}  {r['transport_cost']:>8}"
    #           f"  {r['dominant_arcs']:>10}  {r['optimal']}")

    # if len(pareto) == 1:
    #     r = pareto[0]
    #     print(f"\n  → Single Pareto point at (cost={r['transport_cost']},"
    #           f" dominant={r['dominant_arcs']}).")
    #     print("    Full load-balance is cost-free in this instance.")

    # if not args.no_plot:
    #     plot(rows, pareto, args.output.with_suffix(".png"))

    # return 0


if __name__ == "__main__":
    sys.exit(main())