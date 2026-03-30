#!/usr/bin/env python3
"""
main.py — CLI entry point for multi-commodity network batching solvers.

Usage:
    python main.py --solver naive    -i instances/data_small.lp --bins 2
    python main.py --solver clingcon -i instances/data_small.lp --bins 2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from modules.run_naive import RunNaive
from modules.run_clingcon import RunClingcon


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Multi-commodity network batching solver"
    )
    parser.add_argument(
        "--solver", choices=["naive", "clingcon", "twostage"],
        required=True, help="Solver to use",
    )
    parser.add_argument(
        "--instance", "-i", required=True, help="Instance .lp file",
    )
    parser.add_argument(
        "--time-limit", type=int, default=30, help="Time limit in seconds",
    )
    parser.add_argument(
        "--bins", type=int, default=1, help="Number of bins",
    )
    parser.add_argument(
        "--optimised", action="store_true", default=True,
        help="Use optimised encoding (naive only, default)",
    )
    parser.add_argument(
        "--no-optimised", action="store_false", dest="optimised",
        help="Use basic encoding (naive only)",
    )
    parser.add_argument(
        "--max-freq", type=int, default=20,
        help="Maximum frequency (default: 20)",
    )

    # Two-stage args (reserved for later integration)
    parser.add_argument("--cap-divide", type=int, default=1000)
    parser.add_argument("--round-timeout", type=int, default=30)

    args = parser.parse_args()

    instance = Path(args.instance)
    if not instance.exists():
        print(f"Error: instance not found: {instance}", file=sys.stderr)
        return 1

    print(f"Solver     : {args.solver}")
    print(f"Instance   : {instance}")
    print(f"Bins       : {args.bins}")
    print(f"Time limit : {args.time_limit}s")
    print()

    if args.solver == "naive":
        solver = RunNaive(
            str(instance),
            num_bins=args.bins,
            optimised=args.optimised,
            time_limit=args.time_limit,
            max_freq=args.max_freq,
        )
    elif args.solver == "clingcon":
        solver = RunClingcon(
            str(instance),
            num_bins=args.bins,
            time_limit=args.time_limit,
            max_freq=args.max_freq,
        )
    elif args.solver == "twostage":
        print("Two-stage solver not yet integrated. "
              "Run modules/run_two_stage.py directly.")
        return 1
    else:
        return 1

    return solver.run()


if __name__ == "__main__":
    sys.exit(main())
