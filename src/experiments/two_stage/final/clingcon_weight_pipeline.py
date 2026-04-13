#!/usr/bin/env python3
"""
Shared clingcon experiment logic for weight sweeps using encodings in ./encodings/.

Used by ``main.py`` (R_TR-only sweep) and ``disruption_solver.py`` (R_TR + robust).
Resilience metrics :func:`compute_r_tr` come from project ``main`` (``src/main.py``).
"""

from __future__ import annotations

import csv
import sys
import time
import threading
from pathlib import Path

import clingo
import clingo.ast
from clingcon import ClingconTheory

_FINAL_DIR = Path(__file__).resolve().parent
_SRC_ROOT = _FINAL_DIR.parent.parent.parent
# Ensure project ``src/main.py`` is imported, not ``experiments/.../main.py``.
_sr = str(_SRC_ROOT)
if _sr in sys.path:
    sys.path.remove(_sr)
sys.path.insert(0, _sr)

from main import compute_r_tr  # noqa: E402

BASE = _FINAL_DIR
STAGE1 = BASE / "encodings" / "stage_1_flow.lp"
MINMAX = BASE / "encodings" / "min_max.lp"


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


def _extract_s1(model: clingo.Model, theory: ClingconTheory) -> dict:
    route_freqs   = []
    dominant      = []
    high_exposure = []
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
        if sym.name == "dominantTR" and len(sym.arguments) == 3:
            a = sym.arguments
            dominant.append((str(a[0]), str(a[1]), str(a[2])))
        elif sym.name == "highExposure" and len(sym.arguments) == 4:
            a = sym.arguments
            high_exposure.append((str(a[0]), str(a[1]), str(a[2]), str(a[3])))
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
        "route_freqs":   route_freqs,
        "loads":         loads,
        "dominant":      dominant,
        "high_exposure": high_exposure,
        "static_facts":  static_facts,
    }


def solve_stage1(
    instance_path: str,
    div_weight:    int  = 0,
    time_limit:    int  = 30,
    cap_divide:    int  = 1,
    max_freq:      int  = 20,
    *,
    use_dominant:  int  = 1,
    use_exposure:  int  = 0,
    exposure_n:    int  = 2,
    s1_simple_ctl: bool = False,
    track_trajectory: bool = True,
) -> dict | None:
    """Stage 1 with local ``stage_1_flow.lp``.

    If ``s1_simple_ctl`` is True, only ``cap_size_divide``, ``max_freq``, and
    ``weight=1`` are passed (legacy disruption script behaviour). Otherwise the
    full soft-constraint flags are set and ``weight={div_weight}``.
    """
    theory = ClingconTheory()
    if s1_simple_ctl:
        ctl = clingo.Control([
            "-c", f"cap_size_divide={cap_divide}",
            "-c", f"max_freq={max_freq}",
            "-c", "weight=1",
        ])
    else:
        ctl = clingo.Control([
            "-c", f"cap_size_divide={cap_divide}",
            "-c", f"max_freq={max_freq}",
            "-c", f"weight={div_weight}",
            "-c", f"use_dominant={use_dominant}",
            "-c", f"use_exposure={use_exposure}",
            "-c", f"exposure_n={exposure_n}",
        ])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_files([str(STAGE1), str(instance_path)], on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    theory.prepare(ctl)

    best       = None
    best_cost  = None
    optimum    = False
    trajectory: list[tuple[float, int | None]] = []

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
                    if track_trajectory:
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
        best["cost"]    = best_cost
        best["optimum"] = optimum
        best["time"]    = round(total, 3)
        if track_trajectory:
            best["trajectory"] = trajectory
    return best


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
    print("  [Robust] Grounding...")
    ctl.ground([("base", [])])
    print("  [Robust] Preparing...")
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
    print("\n" + "═" * 90)
    print("  EXPERIMENT SUMMARY")
    print("═" * 90)
    header = (f"  {'w':>6}  {'cost':>6}  {'dom':>4}  {'R_TR':>6}  "
              f"{'worst_arc':<22}  {'rec_cost':>8}  {'regret':>8}  {'dev':>6}  {'opt'}")
    print(header)
    print("  " + "─" * 86)
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
    print("═" * 90)


def run_r_tr_weight_sweep(args) -> None:
    """Stage 1 → R_TR only; checkpoint CSV after each weight."""
    instance_data = parse_instance(args.instances)
    results: list[dict] = []

    print(f"Instance: {len(instance_data['parts'])} parts, "
          f"{len(instance_data['routes'])} routes")
    print(f"Sweeping div_weight: {args.weights}")
    print(f"Time limit per stage: {args.time_limit}s")
    print(f"Output: {args.output}")

    for w in args.weights:
        print(f"\n{'═' * 65}")
        print(f"  div_weight = {w}")
        print(f"{'═' * 65}")

        row: dict = {"div_weight": w}

        print("\n  [Step 1] Solving Stage 1...")
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

        nominal_cost   = stage1["cost"]
        dominant_count = len(stage1["dominant"])

        row["nominal_cost"]   = nominal_cost
        row["dominant_count"] = dominant_count
        row["s1_optimal"]     = stage1["optimum"]
        row["s1_time"]        = stage1["time"]

        print(f"  Done. cost={nominal_cost}  dominant={dominant_count}  "
              f"optimal={stage1['optimum']}")

        print("\n  [Step 2] Computing R_TR...")
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


def run_disruption_weight_sweep(args) -> None:
    """Stage 1 → R_TR → robust (min_max.lp); checkpoint CSV after each weight."""
    instance_data = parse_instance(args.instances)
    results: list[dict] = []

    print(f"Instance: {len(instance_data['parts'])} parts, "
          f"{len(instance_data['routes'])} routes")
    print(f"Sweeping div_weight: {args.weights}")
    print(f"Time limit per stage: {args.time_limit}s")
    print(f"Output: {args.output}")

    for w in args.weights:
        print(f"\n{'═' * 65}")
        print(f"  div_weight = {w}")
        print(f"{'═' * 65}")

        row: dict = {"div_weight": w}

        print("\n  [Step 1] Solving Stage 1...")
        stage1 = solve_stage1(
            args.instances,
            div_weight=w,
            time_limit=args.time_limit,
            cap_divide=args.cap_divide,
            max_freq=args.max_freq,
            s1_simple_ctl=True,
            track_trajectory=False,
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

        nominal_cost   = stage1["cost"]
        dominant_count = len(stage1["dominant"])

        row["nominal_cost"]   = nominal_cost
        row["dominant_count"] = dominant_count
        row["s1_optimal"]     = stage1["optimum"]
        row["s1_time"]        = stage1["time"]
        print(stage1["loads"])
        print(f"Done. cost={nominal_cost}  dominant={dominant_count}  "
              f"optimal={stage1['optimum']}")

        print("\n  [Step 2] Computing R_TR...")
        r_tr, details = compute_r_tr(stage1["loads"], instance_data)
        worst         = min(details, key=lambda d: d["coverage"])
        worst_arc     = (worst["lost_f"], worst["lost_t"], worst["lost_tr"])
        worst_arc_str = f"({worst['lost_f']},{worst['lost_t']},{worst['lost_tr']})"

        row["r_tr"]               = r_tr
        row["worst_arc"]          = worst_arc_str
        row["worst_arc_coverage"] = worst["coverage"]

        print(f"  R_TR={r_tr}  worst={worst_arc_str}  coverage={worst['coverage']}")

        print(f"\n  [Step 3] Solving robust plan for disrupted{worst_arc}...")
        facts  = build_facts(stage1, worst_arc)
        robust = solve_robust(
            args.instances, facts,
            time_limit=args.time_limit,
            cap_divide=args.cap_divide,
            max_freq=args.max_freq,
        )

        if robust is None:
            print(f"  WARNING: Robust solve returned no solution for w={w}.")
            row.update({
                "recovery_cost": None, "regret": None,
                "load_deviation": None, "robust_optimal": False,
                "robust_time": None,
            })
            print(f"  Injected facts:\n{facts}")
        else:
            rec_cost = robust.get("recovery_cost")
            regret   = robust.get("regret")

            if regret is None and rec_cost is not None:
                regret = rec_cost - nominal_cost

            cost_vec  = robust.get("cost_vec", [])
            deviation = cost_vec[1] if len(cost_vec) > 1 else None

            row["recovery_cost"]  = rec_cost
            row["regret"]         = regret
            row["load_deviation"] = deviation
            row["robust_optimal"] = robust["optimum"]
            row["robust_time"]    = robust["time"]

            print(f"  recovery_cost={rec_cost}  regret={regret}  "
                  f"deviation={deviation}  optimal={robust['optimum']}")

        results.append(row)
        write_csv(results, args.output)

    write_csv(results, args.output)
