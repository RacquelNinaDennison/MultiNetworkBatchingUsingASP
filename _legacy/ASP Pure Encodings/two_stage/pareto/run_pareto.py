#!/usr/bin/env python3
"""
run_pareto.py — Pareto sweep: transport cost vs load-balanced diversification
=============================================================================

For each div_weight, solves pareto.lp + instances.lp and records:
  - transport_cost  : post-hoc sum of route_cost × freq
  - dominant_arcs   : count of dominantTR atoms from the solver

Solve strategy
--------------
clingo already improves internally within a single solve() call — every
model yielded is strictly better than the previous one. We let clingo do
this natively and only intervene (add a hard bound + restart) when the
solver times out without proving optimality. This way:

  - If clingo proves optimality within the timeout → done, one round.
  - If clingo times out → add a hard bound below the best found so far
    and restart. The next round searches strictly below that bound.
  - Repeat until optimality is proven, UNSAT (proven optimal), or the
    total timeout is exhausted.

Usage
-----
    python run_pareto.py
    python run_pareto.py --weights 0 10 50 100 200 300
    python run_pareto.py --total-timeout 1800 --round-timeout 120
    python run_pareto.py --no-plot
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import threading
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
    "transport_cost",
    "dominant_arcs",
    "solver_cost",
    "solve_time",
    "optimal",
    "rounds",
    "improvements",   # total number of better models found across all rounds
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
        sym  = atom.symbol
        name = sym.name
        args = sym.arguments
        if name == "transportCapacity" and len(args) == 2:
            data["transport_cap"][str(args[0])] = args[1].number
        elif name == "partSize" and len(args) == 2:
            data["part_size"][str(args[0])] = args[1].number
        elif name == "part" and len(args) == 1:
            data["parts"].add(str(args[0]))
        elif name == "route" and len(args) == 5:
            data["route_cost"][
                (str(args[0]), str(args[1]), str(args[2]))
            ] = args[4].number

    return data


# ═══════════════════════════════════════════════════════════════════════════════
# Solver
# ═══════════════════════════════════════════════════════════════════════════════

def solve(
    div_weight:    int,
    cap_divide:    int,
    max_freq:      int,
    total_timeout: int,
    round_timeout: int,
) -> dict | None:
    """
    Solve for one div_weight value using clingo's native optimization +
    external restart-with-bound on timeout.

    Within each round, clingo yields models in strictly improving order
    automatically — no manual bounding needed between models. We only add
    an external hard bound when the round times out, to force clingo to
    restart its search below the current best.

    Returns the best solution found, or None if no solution exists.
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

    # Hard bound on combined objective added between rounds on timeout.
    # Uses a single #sum aggregate combining both cost terms — valid ASP syntax.
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
        # ── Check total time budget ───────────────────────────────────────────
        elapsed   = time.perf_counter() - t0
        remaining = int(total_timeout - elapsed)
        if remaining <= 0:
            print(f"    [total timeout — {round_num} rounds, "
                  f"{total_improvements} improvements]", flush=True)
            break

        budget    = min(round_timeout, remaining)
        round_num += 1
        round_improvements = 0

        print(f"    round {round_num:>2}  budget={budget}s"
              f"  best={best_cost} ...", flush=True)

        # ── Run one solve round ───────────────────────────────────────────────
        # clingo yields models in strictly improving order internally.
        # We record every improvement as it arrives.
        timed_out = False
        timer     = threading.Timer(budget, ctl.interrupt)
        timer.start()
        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    theory.on_model(model)
                    candidate_cost = model.cost[0] if model.cost else None
                    candidate      = _extract(model, theory)

                    # Every model from clingo is strictly better than the last
                    # within this solve call, so always update best
                    best              = candidate
                    best_cost         = candidate_cost
                    round_improvements += 1
                    total_improvements += 1
                    print(f"      ↓ {best_cost}  "
                          f"(dominant={candidate['dominant_arcs']})",
                          flush=True)

                    if model.optimality_proven:
                        optimum = True
                        break

                result = handle.get()

        except RuntimeError:
            timed_out = True
            result    = None
        finally:
            timer.cancel()

        # ── Assess round outcome ──────────────────────────────────────────────
        if optimum:
            print(f"    [✓ optimality proven in round {round_num}]", flush=True)
            break

        # UNSAT: current bound has no solution below it → proven optimal
        if result is not None and getattr(result, "unsatisfiable", False):
            print(f"    [✓ UNSAT — proven optimal at {best_cost}]", flush=True)
            optimum = True
            break

        # No solution found at all → encoding is infeasible
        if best is None:
            print(f"    [no solution found — stopping]", flush=True)
            break

        if round_improvements == 0:
            print(f"    [round {round_num}: no improvement found in {budget}s]",
                  flush=True)
        else:
            print(f"    [round {round_num}: {round_improvements} improvement(s),"
                  f" best={best_cost}]", flush=True)

        # ── Add hard bound and restart ────────────────────────────────────────
        # Only needed because clingo timed out without proving optimality.
        # The bound forces the next round to search strictly below best_cost.
        if best_cost is not None and best_cost < 2_000_000_000:
            bound_str = BOUND.format(dw=div_weight, bound=best_cost)
            section   = f"bound_{round_num}"
            try:
                ctl.add(section, [], bound_str)
                ctl.ground([(section, [])])
                print(f"    [bound added: obj < {best_cost} → round {round_num+1}]",
                      flush=True)
            except RuntimeError as e:
                print(f"    [bound failed: {e} — stopping]", flush=True)
                break
        else:
            print(f"    [cost too large to bound — stopping]", flush=True)
            break

    total_time = time.perf_counter() - t0

    if best is not None:
        best["total_time"]   = round(total_time, 3)
        best["optimum"]      = optimum
        best["cost"]         = best_cost
        best["rounds"]       = round_num
        best["improvements"] = total_improvements

    return best


def _extract(model, theory) -> dict:
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


# ═══════════════════════════════════════════════════════════════════════════════
# Post-hoc transport cost
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
    """Return non-dominated points minimising (transport_cost, dominant_arcs)."""
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
        marker = "★" if r["optimal"] else "○"
        ax.annotate(
            f"{marker} w={r['div_weight']}",
            (r["transport_cost"], r["dominant_arcs"]),
            fontsize=7, xytext=(4, 3), textcoords="offset points",
        )
    plt.colorbar(sc, ax=ax, label="div_weight")
    ax.set_xlabel("Transport Cost  (Σ route_cost × freq)")
    ax.set_ylabel("Dominant Arcs  (count of dominantTR atoms)")
    ax.set_title("All weight values  (★ = proven optimal)")
    ax.grid(True, alpha=0.3)

    # ── Right: Pareto front ───────────────────────────────────────────────────
    ax = axes[1]
    ax.scatter(
        [r["transport_cost"] for r in all_rows],
        [r["dominant_arcs"]  for r in all_rows],
        c="lightsteelblue", s=70, zorder=2, label="dominated",
    )
    if pareto_rows:
        px = [r["transport_cost"] for r in pareto_rows]
        py = [r["dominant_arcs"]  for r in pareto_rows]
        ax.plot(px, py, "o-", color="steelblue", lw=2.5,
                markersize=10, zorder=4, label=f"Pareto ({len(pareto_rows)} pts)")
        for r in pareto_rows:
            opt = "✓" if r["optimal"] else "~"
            ax.annotate(
                f"{opt} w={r['div_weight']}\n"
                f"({r['transport_cost']}, {r['dominant_arcs']})",
                (r["transport_cost"], r["dominant_arcs"]),
                fontsize=8, fontweight="bold",
                xytext=(6, 4), textcoords="offset points",
            )

    ax.set_xlabel("Transport Cost  (Σ route_cost × freq)")
    ax.set_ylabel("Dominant Arcs  (count of dominantTR atoms)")
    ax.set_title("Pareto Front  (✓ = proven optimal, ~ = best found)")
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
        default=list(range(0, 110, 10)),
        help="div_weight values to sweep (default: 0 10 20 … 100)",
    )
    parser.add_argument(
        "--total-timeout", type=int, default=600,
        help="Total time budget per weight in seconds (default: 600)",
    )
    parser.add_argument(
        "--round-timeout", type=int, default=120,
        help="Max seconds per solve round before adding bound (default: 120)",
    )
    parser.add_argument("--cap-divide", type=int, default=1)
    parser.add_argument("--max-freq",   type=int, default=20)
    parser.add_argument("--no-plot",    action="store_true")
    parser.add_argument(
        "--output", type=Path,
        default=RESULTS_DIR / "pareto_sweep.csv",
    )
    args = parser.parse_args()

    for f in [PARETO_LP, INSTANCES_LP]:
        if not f.exists():
            print(f"ERROR: {f} not found in {HERE}")
            return 1

    instance_data = load_instance_data()
    print(f"Instance:       {len(instance_data['parts'])} parts,"
          f" {len(instance_data['route_cost'])} routes")
    print(f"Weights:        {args.weights}")
    print(f"Total timeout:  {args.total_timeout}s per weight")
    print(f"Round timeout:  {args.round_timeout}s per round")
    print()

    rows = []

    for weight in args.weights:
        print(f"\n{'═'*60}")
        print(f"  div_weight = {weight}")
        print(f"{'═'*60}")

        sol = solve(
            div_weight    = weight,
            cap_divide    = args.cap_divide,
            max_freq      = args.max_freq,
            total_timeout = args.total_timeout,
            round_timeout = args.round_timeout,
        )

        if sol is None:
            print(f"  → no solution found")
            continue

        transport_cost = compute_transport_cost(sol, instance_data)
        dominant_arcs  = sol["dominant_arcs"]

        row = {
            "div_weight":     weight,
            "transport_cost": transport_cost,
            "dominant_arcs":  dominant_arcs,
            "solver_cost":    sol["cost"],
            "solve_time":     sol["total_time"],
            "optimal":        sol["optimum"],
            "rounds":         sol["rounds"],
            "improvements":   sol["improvements"],
        }
        rows.append(row)

        status = "✓ OPTIMAL" if sol["optimum"] else "~ best found"
        print(f"\n  {status}")
        print(f"  cost={transport_cost}  dominant={dominant_arcs}"
              f"  solver_obj={sol['cost']}")
        print(f"  time={sol['total_time']}s  rounds={sol['rounds']}"
              f"  improvements={sol['improvements']}")

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

    # Pareto summary
    pareto = filter_pareto(rows)
    print(f"\n{'─'*65}")
    print(f"Pareto-optimal: {len(pareto)} / {len(rows)} points")
    print(f"{'─'*65}")
    print(f"  {'w':>6}  {'cost':>8}  {'dominant':>10}  "
          f"{'rounds':>7}  {'impr':>6}  status")
    for r in pareto:
        status = "✓ optimal" if r["optimal"] else "~ best found"
        print(f"  {r['div_weight']:>6}  {r['transport_cost']:>8}"
              f"  {r['dominant_arcs']:>10}  {r['rounds']:>7}"
              f"  {r['improvements']:>6}  {status}")

    if len(pareto) == 1:
        print(f"\n  → Single Pareto point: diversification is cost-free"
              f" in this instance.")

    if not args.no_plot:
        plot(rows, pareto, args.output.with_suffix(".png"))

    return 0


if __name__ == "__main__":
    sys.exit(main())