"""CLI entry point for the multibatch package.

Usage:
    multibatch --solver naive_oneshot -i instances/small_seed1.lp --bins 2
    multibatch --solver twostage_naive -i instances/small_seed1.lp --weight 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .models import SolverType


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-commodity network batching solver"
    )
    parser.add_argument(
        "--solver", type=SolverType, choices=list(SolverType),
        required=True, help="Solver variant to use",
    )
    parser.add_argument(
        "--instance", "-i", required=True,
        help="Path to the instance .lp file",
    )
    parser.add_argument("--time-limit", type=int, default=30)
    parser.add_argument("--bins", type=int, default=1)
    parser.add_argument("--max-freq", type=int, default=20)
    parser.add_argument("--weight", type=int, default=1)
    parser.add_argument("--optimised", action="store_true", default=True)
    parser.add_argument("--no-optimised", action="store_false", dest="optimised")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    instance_path = Path(args.instance)
    if not instance_path.exists():
        print(f"Error: instance not found: {instance_path}", file=sys.stderr)
        return 1

    # TODO: wire up solvers once ported
    print(f"Solver:   {args.solver.value}")
    print(f"Instance: {instance_path}")
    print(f"(solver implementations pending)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
