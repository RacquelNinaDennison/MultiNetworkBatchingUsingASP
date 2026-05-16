"""CLI entry point for the multibatch package.

Usage:
    python -m multibatch --solver naive_oneshot -i instances/small_seed1.lp --bins 2
    multibatch --solver naive_oneshot -i instances/small_seed1.lp --bins 2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .models import SolverType, NaiveOneShotConfig
from .solvers.naive import NaiveOneShotSolver
from .verification import verify_solution
from .reporting.console import print_oneshot_result


# ─────────────────────────────────────────────────────────────────────────────
# Solver registry — maps SolverType → builder function
# ─────────────────────────────────────────────────────────────────────────────

def _build_naive_oneshot(args) -> NaiveOneShotSolver:
    config = NaiveOneShotConfig(
        num_bins=args.bins,
        time_limit=args.time_limit,
        max_freq=args.max_freq,
        optimised=args.optimised,
    )
    return NaiveOneShotSolver(
        instance_path=args.instance,
        config=config,
    )


# Add new solvers here as they are ported
SOLVER_REGISTRY = {
    SolverType.NAIVE_ONESHOT: _build_naive_oneshot,
    # SolverType.CLINGCON_ONESHOT: _build_clingcon_oneshot,
    # SolverType.TWOSTAGE_NAIVE: _build_twostage_naive,
    # SolverType.TWOSTAGE_CLINGCON: _build_twostage_clingcon,
    # SolverType.TWOSTAGE_SUBPROCESS: _build_twostage_subprocess,
}


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-commodity network batching solver"
    )
    parser.add_argument(
        "--solver", "-s",
        type=SolverType,
        choices=list(SolverType),
        required=True,
        help="Solver variant",
    )
    parser.add_argument("--instance", "-i", required=True, help="Instance .lp file")
    parser.add_argument("--time-limit", type=int, default=30, help="Time limit in seconds")
    parser.add_argument("--bins", type=int, default=1, help="Number of bins (one-shot solvers)")
    parser.add_argument("--max-freq", type=int, default=20, help="Maximum frequency")
    parser.add_argument("--weight", type=int, default=1, help="Objective weight (two-stage)")
    parser.add_argument("--optimised", action="store_true", default=True)
    parser.add_argument("--no-optimised", action="store_false", dest="optimised")
    parser.add_argument("--verify", action="store_true", default=True, help="Run verification")
    parser.add_argument("--no-verify", action="store_false", dest="verify")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    instance_path = Path(args.instance)
    if not instance_path.exists():
        print(f"Error: instance not found: {instance_path}", file=sys.stderr)
        return 1

    builder = SOLVER_REGISTRY.get(args.solver)
    if builder is None:
        available = [s.value for s in SOLVER_REGISTRY]
        print(f"Error: solver '{args.solver.value}' not yet implemented", file=sys.stderr)
        print(f"Available: {', '.join(available)}", file=sys.stderr)
        return 1

    print(f"Solver:   {args.solver.value}")
    print(f"Instance: {instance_path}")
    print()

    solver = builder(args)
    result = solver.solve()

    if result is None:
        print("UNSATISFIABLE — no solution found.")
        return 1

    meta = result.metadata
    status = "OPTIMUM" if meta.optimum else "BEST MODEL"
    print(f"\n{status} (ground={meta.ground_time}s, total={meta.total_time}s)")
    print(f"Clingo stats solving: {meta.clingo_stats_solver}")
    print(f"Clingo stats grounding: {meta.clingo_stats_grounding}")


    print_oneshot_result(result, solver.instance)

    if args.verify:
        print()
        passed, errors = verify_solution(result, solver.instance)
        if passed:
            print("Verification: PASSED")
        else:
            print(f"Verification: FAILED ({len(errors)} errors)")
            for e in errors:
                print(f"  {e}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
