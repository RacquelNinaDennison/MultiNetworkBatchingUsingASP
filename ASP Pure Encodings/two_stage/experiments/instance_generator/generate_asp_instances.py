#!/usr/bin/env python3
"""
generate_asp_instances.py — Generate ASP-compatible instances from the
multibatching problem generator.

Generates instances with controlled capacity/demand ratios that ensure:
  - Multiple trips per arc (demand > capacity per trip)
  - All parts fit on multiple transport resources (no bottleneck parts)
  - Flow feasibility verified via max-flow before export
  - Supply/demand balanced per part

Usage:
    python generate_asp_instances.py --seed 42 --locations 6 --parts 3 --transports 2
    python generate_asp_instances.py --seed 42 --locations 8 --parts 5 --transports 3 --output instance.lp

    # Generate a batch:
    for seed in 1 2 3 4 5; do
        python generate_asp_instances.py --seed $seed --locations 6 --parts 3 \
            --transports 2 --output instances/small_seed${seed}.lp
    done
"""

import argparse
import sys
from pathlib import Path

from utils import generate_multibatching_problem


def problem_to_asp(problem, seed: int, params: dict) -> str:
    """Convert a MultibatchingProblem to ASP fact format."""
    lines = []

    # Header
    lines.append(f"% Multibatching benchmark instance")
    lines.append(f"% Generated with seed={seed} locations={params['locations']} "
                 f"parts={params['parts']} transports={params['transports']}")
    lines.append("")

    # Locations
    lines.append("% ---- locations ----")
    for loc in problem.locations:
        lines.append(f"location({loc.id}).")

    # Transport resources
    lines.append("")
    lines.append("% ---- transport resources ----")
    for tt in problem.transport_types:
        tr_id = f"tr{tt.id}"
        lines.append(f"transportCapacity({tr_id},{tt.capacity}).")
        lines.append(f"transportCO2({tr_id},{tt.emissions}).")
        lines.append(f"transportCost({tr_id},{tt.cost}).")
        # Speed is float in the generator — scale to integer for ASP
        speed_int = max(1, int(tt.speed * 10))
        lines.append(f"transportSpeed({tr_id},{speed_int}).")

    # Parts
    lines.append("")
    lines.append("% ---- parts ----")
    for prod in problem.products:
        p_id = prod.name
        lines.append(f"part({p_id}).")
        lines.append(f"partSize({p_id},{prod.size}).")
        lines.append(f"partVal({p_id},{prod.value}).")
        for tt in prod.valid_transports:
            lines.append(f"partTR({p_id},tr{tt.id}).")

    # Demand/Supply
    lines.append("")
    lines.append("% ---- demand and supply ----")
    for loc in problem.locations:
        for prod, qty in loc.net_supply.items():
            if qty != 0:
                # Convention: positive = supply (offer), negative = demand
                lines.append(f"demandOffer({prod.name},{loc.id},{qty}).")

    # Routes
    lines.append("")
    lines.append("% ---- routes ----")
    for link in problem.transport_links:
        tr_id = f"tr{link.transport_type.id}"
        # distance is float, convert to int for ASP
        dist = int(link.distance)
        cost = dist * link.transport_type.cost
        lines.append(f"route({link.location_l1.id},{link.location_l2.id},{tr_id},{dist},{cost}).")

    return "\n".join(lines)


def check_asp_feasibility(asp_text: str, timeout: int = 30) -> bool:
    """Run a quick clingcon flow check to verify the instance is feasible."""
    import threading

    try:
        import clingo
        import clingo.ast
        from clingcon import ClingconTheory
    except ImportError:
        print("  Warning: clingcon not available, skipping ASP feasibility check",
              file=sys.stderr)
        return True

    STAGE1_PATH = str(Path(__file__).parent.parent.parent / "stage1_flow.lp")

    theory = ClingconTheory()
    ctl = clingo.Control(["-c", "cap_size_divide=1", "-c", "max_freq=50"])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_string(asp_text, on_rule)
        clingo.ast.parse_files([STAGE1_PATH], on_rule)

    ctl.ground([("base", [])])
    theory.prepare(ctl)

    found = False
    timer = threading.Timer(timeout, ctl.interrupt)
    timer.start()

    try:
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                theory.on_model(model)
                found = True
                break
    except RuntimeError:
        pass
    finally:
        timer.cancel()

    return found


def main():
    parser = argparse.ArgumentParser(
        description="Generate ASP-compatible multibatching instances."
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--locations", type=int, default=6)
    parser.add_argument("--parts", type=int, default=3)
    parser.add_argument("--transports", type=int, default=2)
    parser.add_argument("--min-capacity", type=int, default=10)
    parser.add_argument("--max-capacity", type=int, default=20)
    parser.add_argument("--min-part-size", type=int, default=1)
    parser.add_argument("--max-part-size", type=int, default=5)
    parser.add_argument("--max-demand", type=int, default=50)
    parser.add_argument("--demand-sparsity", type=float, default=0.7)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--max-retries", type=int, default=20)

    args = parser.parse_args()

    params = {
        "locations": args.locations,
        "parts": args.parts,
        "transports": args.transports,
    }

    for attempt in range(1, args.max_retries + 1):
        # Use different sub-seeds for retries
        current_seed = args.seed * 1000 + attempt

        problem = generate_multibatching_problem(
            num_locations=args.locations,
            num_transport_types=args.transports,
            num_products=args.parts,
            min_capacity=args.min_capacity,
            max_capacity=args.max_capacity,
            min_product_size=args.min_part_size,
            max_product_size=args.max_part_size,
            max_demand_abs=args.max_demand,
            demand_sparsity=args.demand_sparsity,
            seed=current_seed,
        )

        # Check balance
        has_demand = False
        for loc in problem.locations:
            for prod, qty in loc.net_supply.items():
                if qty != 0:
                    has_demand = True
                    break

        if not has_demand:
            print(f"  Attempt {attempt}: no demand generated, retrying...", file=sys.stderr)
            continue

        # Check feasibility: first max-flow (fast), then clingcon (definitive)
        feasible = problem.check_feasibility_per_product(verbose=False)
        if feasible:
            # Double-check with actual ASP solver
            asp_text = problem_to_asp(problem, current_seed, params)
            feasible = check_asp_feasibility(asp_text)

        if feasible:
            print(f"  Attempt {attempt}: feasible (seed={current_seed})", file=sys.stderr)

            asp_text = problem_to_asp(problem, current_seed, params)

            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(asp_text + "\n")
                print(f"  Written to {out_path}", file=sys.stderr)
            else:
                print(asp_text)

            return 0
        else:
            print(f"  Attempt {attempt}: infeasible, retrying...", file=sys.stderr)

    print(f"FAILED: Could not find feasible instance in {args.max_retries} attempts.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
