"""
Hybrid ASP + Propagator solver for logistics co-design.

Usage:
    # Default (check-only, best for small instances):
    python3 main.py instances.lp encoding.lp --verbose

    # Eager mode (propagate + check, better for large instances):
    python3 main.py instances.lp encoding.lp --verbose --eager

    # Ablation:
    python3 main.py instances.lp encoding.lp --verbose --no-link
"""

import argparse
import json
import time
from pathlib import Path

import clingo

from src.modules.flow_conservation import FlowConservationPropagator
from src.modules.packing_conservation import PackageCapacityPropagator
from src.modules.links_conservation import LinkPackFlowLazyChecker


def flatten_stats(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flatten_stats(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(d, (list, tuple)):
        for i, v in enumerate(d):
            out.update(flatten_stats(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = d
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Hybrid ASP + Propagator solver for logistics co-design")

    ap.add_argument("lp", nargs="+", help="One or more .lp files (instance + encoding)")
    ap.add_argument("--models", type=int, default=0,
                    help="0 = all models (needed for optimization)")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--opt-mode", type=str, default=None,
                    choices=["opt", "optN", "enum", "ignore"])

    # Propagator toggles
    ap.add_argument("--no-flow", action="store_true",
                    help="Disable flow conservation propagator")
    ap.add_argument("--no-pack", action="store_true",
                    help="Disable packing capacity propagator")
    ap.add_argument("--no-link", action="store_true",
                    help="Disable link-pack-flow propagator")
    ap.add_argument("--eager", action="store_true",
                    help="Enable propagate() in addition to check(). "
                         "Adds early pruning but has Python call overhead. "
                         "Better for large instances, worse for small ones.")

    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", type=str, default=None,
                    help="Write JSON run record to this path")

    args = ap.parse_args()

    clingo_args = ["--stats=2"]
    if args.threads > 1:
        clingo_args.append(f"--threads={args.threads}")
    if args.opt_mode:
        clingo_args.append(f"--opt-mode={args.opt_mode}")

    ctl = clingo.Control(clingo_args)
    ctl.configuration.solve.models = str(args.models)

    for f in args.lp:
        if args.verbose:
            print(f"[info] Loading {f}")
        ctl.load(f)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    t_ground = time.perf_counter() - t0
    if args.verbose:
        print(f"[info] Grounding: {t_ground:.3f}s")

    # Register propagators AFTER grounding
    propagators_enabled = {}
    mode = "eager" if args.eager else "lazy"

    if not args.no_flow:
        ctl.register_propagator(FlowConservationPropagator(eager=args.eager))
        propagators_enabled["flow"] = True
        if args.verbose:
            print(f"[info] Registered: FlowConservationPropagator (mode={mode})")
    else:
        propagators_enabled["flow"] = False

    if not args.no_pack:
        ctl.register_propagator(PackageCapacityPropagator(eager=args.eager))
        propagators_enabled["pack"] = True
        if args.verbose:
            print(f"[info] Registered: PackageCapacityPropagator (mode={mode})")
    else:
        propagators_enabled["pack"] = False

    if not args.no_link:
        ctl.register_propagator(LinkPackFlowLazyChecker(eager=args.eager))
        propagators_enabled["link"] = True
        if args.verbose:
            print(f"[info] Registered: LinkPackFlowLazyChecker (mode={mode})")
    else:
        propagators_enabled["link"] = False

    # Solve
    t1 = time.perf_counter()
    best_cost = None
    model_count = 0

    with ctl.solve(yield_=True) as handle:
        for m in handle:
            model_count += 1
            cost = m.cost[0] if m.cost else None
            best_cost = cost
            if args.verbose:
                print(f"[model #{model_count}] cost={cost}")

    t_solve = time.perf_counter() - t1
    t_total = t_ground + t_solve

    # Result
    if model_count > 0:
        print(f"\nOptimal cost: {best_cost}")
        print(f"Models found: {model_count}")
    else:
        print("\nNo solution found (UNSATISFIABLE)")

    print(f"Time: {t_total:.3f}s (ground={t_ground:.3f}s, solve={t_solve:.3f}s)")
    print(f"Propagators: {propagators_enabled} (mode={mode})")

    if args.verbose:
        flat = flatten_stats(ctl.statistics)
        stat_keys = [
            ("solving.solvers.choices", "Choices"),
            ("solving.solvers.conflicts", "Conflicts"),
            ("solving.solvers.restarts", "Restarts"),
            ("solving.solvers.extra.lemmas", "Lemmas learned"),
            ("problem.lp.atoms", "Atoms"),
            ("problem.lp.rules", "Rules"),
            ("problem.generator.vars", "Solver variables"),
            ("problem.generator.constraints", "Constraints"),
        ]
        print("\n--- Solver Statistics ---")
        for key, label in stat_keys:
            val = flat.get(key, "N/A")
            if isinstance(val, float) and val == int(val):
                val = int(val)
            print(f"  {label}: {val}")

    if args.out:
        flat = flatten_stats(ctl.statistics)
        record = {
            "files": args.lp,
            "propagators": propagators_enabled,
            "mode": mode,
            "timing": {"ground_s": t_ground, "solve_s": t_solve, "total_s": t_total},
            "result": {"models": model_count, "optimal_cost": best_cost},
            "stats": flat,
        }
        Path(args.out).write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"[info] Wrote {args.out}")


if __name__ == "__main__":
    main()
