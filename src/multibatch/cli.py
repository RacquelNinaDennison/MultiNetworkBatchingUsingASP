"""CLI entry point for the multibatch package.

Usage:
    python -m multibatch --solver naive_oneshot -i instances/small_seed1.lp --bins 2
    multibatch --solver naive_oneshot -i instances/small_seed1.lp --bins 2
"""

import argparse
import sys
from pathlib import Path

from .models import (
    SolverType,
    NaiveOneShotConfig,
    ClingconOneShotConfig,
    TwoStageNaiveConfig,
    TwoStageClingconConfig,
    OneShotResult,
    TwoStageResult,
)
from .solvers.naive import NaiveOneShotSolver
from .solvers.clingcon import ClingconOneShotSolver
from .solvers.twostage_naive import NaiveTwoStageSolver
from .solvers.twostage_clingcon import ClingconTwoStageSolver
from .solvers.milp_flow import MilpFlowTwoStageSolver
from .verification import verify_solution
from .reporting.console import print_oneshot_result, print_twostage_result


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


def _build_clingcon_oneshot(args) -> ClingconOneShotSolver:
    config = ClingconOneShotConfig(
        num_bins=args.bins,
        time_limit=args.time_limit,
        max_freq=args.max_freq,
    )
    return ClingconOneShotSolver(
        instance_path=args.instance,
        config=config,
    )


def _build_twostage_naive(args) -> NaiveTwoStageSolver:
    config = TwoStageNaiveConfig(
        time_limit=args.time_limit,
        max_freq=args.max_freq,
        weight=args.weight,
    )
    return NaiveTwoStageSolver(
        instance_path=args.instance,
        config=config,
    )


def _build_twostage_clingcon(args) -> ClingconTwoStageSolver:
    config = TwoStageClingconConfig(
        time_limit=args.time_limit,
        max_freq=args.max_freq,
        weight=args.weight,
    )
    return ClingconTwoStageSolver(
        instance_path=args.instance,
        config=config,
    )


def _build_milpflow_twostage(args) -> MilpFlowTwoStageSolver:
    config = TwoStageClingconConfig(
        time_limit=args.time_limit,
        max_freq=args.max_freq,
        weight=args.weight,
    )
    return MilpFlowTwoStageSolver(
        instance_path=args.instance,
        config=config,
        backend=args.backend,
        flow_time_limit=args.flow_time_limit,
        flow_redundancy_weight=args.flow_redundancy_weight,
        utilisation=args.utilisation,
    )


SOLVER_REGISTRY = {
    SolverType.NAIVE_ONESHOT: _build_naive_oneshot,
    SolverType.CLINGCON_ONESHOT: _build_clingcon_oneshot,
    SolverType.TWOSTAGE_NAIVE: _build_twostage_naive,
    SolverType.TWOSTAGE_CLINGCON: _build_twostage_clingcon,
    SolverType.MILPFLOW_TWOSTAGE: _build_milpflow_twostage,
}



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
    parser.add_argument("--bins", type=int, default=1, help="Number of bins")
    parser.add_argument("--max-freq", type=int, default=20, help="Maximum frequency")
    parser.add_argument("--weight", type=int, default=1, help="Objective weight (two-stage)")
    # milpflow_twostage (MILP Stage-1) options
    parser.add_argument("--backend", default="SCIP", help="MILP backend for milpflow_twostage")
    parser.add_argument("--utilisation", type=float, default=0.7,
                        help="Stage-1 capacity-fill fraction (milpflow_twostage); "
                             "1.0 = the paper's exact constraint, 0.7 = 30%% safety margin")
    parser.add_argument("--flow-time-limit", type=int, default=300,
                        help="Stage-1 MILP time limit in seconds (milpflow_twostage)")
    parser.add_argument("--flow-redundancy-weight", type=int, default=0,
                        help="push active arcs toward >=2 trips (milpflow_twostage; 0=off)")
    parser.add_argument("--optimised", action="store_true", default=True)
    parser.add_argument("--no-optimised", action="store_false", dest="optimised")
    parser.add_argument("--verify", action="store_true", default=True, help="Run verification")
    parser.add_argument("--no-verify", action="store_false", dest="verify")
    parser.add_argument("--visualise", action="store_true", default=False,
                        help="Generate interactive HTML visualisation of the solution")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output path for visualisation HTML (default: multibatch_solution.html)")
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

    if isinstance(result, OneShotResult):
        meta = result.metadata
        status = "OPTIMUM" if meta.optimum else "BEST MODEL"
        print(f"\n{status} (ground={meta.ground_time}s, solve={meta.solve_time}s, total={meta.total_time}s)")
        print(f"Cost: {meta.cost}")
        print(f"Atoms: {meta.atoms}  Choices: {meta.choices}  Conflicts: {meta.conflicts}  Restarts: {meta.restarts}")

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

        if args.visualise:
            from .visualisation import visualise_oneshot
            out = Path(args.output) if args.output else None
            path = visualise_oneshot(result, solver.instance, output_path=out)
            print(f"\nVisualisation saved to: {path.resolve()}")

    elif isinstance(result, TwoStageResult):
        status = "OPTIMUM" if result.optimum else "BEST MODEL"
        print(f"\n{status} (total={result.total_time:.3f}s)")

        print_twostage_result(result, solver.instance)

        if args.visualise:
            from .visualisation import visualise_twostage
            out = Path(args.output) if args.output else None
            path = visualise_twostage(result, solver.instance, output_path=out)
            print(f"\nVisualisation saved to: {path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
