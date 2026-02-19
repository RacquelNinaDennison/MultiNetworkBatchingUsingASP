#!/usr/bin/env python3
"""
Column Generation for Logistics Optimisation
=============================================

Usage:
    uv run python main.py --master asp_files/master.lp \
                           --pricing asp_files/pricing.lp \
                           --instance asp_files/instances.lp

All three ASP file paths are required.
"""

import argparse
import sys
from src.modules.classes import ColumnGeneration


def main():
    parser = argparse.ArgumentParser(
        description="Column generation for logistics optimisation using clingcon"
    )
    parser.add_argument(
        "--master", required=True,
        help="Path to the master problem ASP file (master.lp)"
    )
    parser.add_argument(
        "--pricing", required=True,
        help="Path to the pricing subproblem ASP file (pricing.lp)"
    )
    parser.add_argument(
        "--instance", required=True,
        help="Path to the instance data ASP file (instances.lp)"
    )
    args = parser.parse_args()

    # Create the column generation driver with the file paths
    cg = ColumnGeneration(
        master_lp=args.master,
        pricing_lp=args.pricing,
        instance_lp=args.instance
    )

    # Parse the instance data
    instance = cg.parse_instance()
    print(f"Instance: {len(instance.parts)} parts, "
          f"{len(instance.locations)} locations, "
          f"{len(instance.routes)} routes, "
          f"{len(instance.tr_list)} transport resources")

    # Run column generation
    cost, solution, pool = cg.column_generation(instance)
    print(solution)
    print(cost)
    print(pool)


if __name__ == "__main__":
    main()
