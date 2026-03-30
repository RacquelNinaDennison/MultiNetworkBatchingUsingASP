import argparse
import logging
import pkgutil
import importlib
import dataclasses

from pricers.base_pricer import BasePricer
import pricers


package = pricers
prefix = package.__name__ + "."

for _, name, _ in pkgutil.iter_modules(package.__path__, prefix):
    try:
        importlib.import_module(name)
    except ImportError as e:
        logging.warning(f"Could not import pricer module {name}: {e}")

from input_parser import read_problem
from master_problem import MasterProblem, print_problem_stats


def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("LNO_Solver")

    parser = argparse.ArgumentParser(
        description="Logistics Network Optimization Solver"
    )


    parser.add_argument("instance", help="Path to the JSON instance file")

    
    parser.add_argument(
        "--mode",
        default="lp",
        choices=["lp", "ip"],
        help="Relaxed (lp) or Integer (ip) mode of lambda vars",
    )

    available = list(BasePricer._registry.keys())
    if not available:
        logger.error("No pricers registered. Check your 'pricers' folder.")
        return

    parser.add_argument(
        "--pricer",
        required=True,
        choices=available,
        help=f"Pricing engine to use. Available: {available}",
    )


    parser.add_argument("--epsilon", type=float, default=1e-6, help="Solver tolerance")
    parser.add_argument(
        "--big_m", type=float, default=100000.0, help="Penalty for dummy vars"
    )
    parser.add_argument(
        "--export_lp",
        action="store_true",
        help="Export the math model to 'master_problem.lp'",
    )


    parser.add_argument(
        "--no_transport", action="store_true", help="Disable transport distance costs"
    )
    parser.add_argument(
        "--no_co2", action="store_true", help="Disable CO2 emissions costs"
    )
    parser.add_argument(
        "--no_interest", action="store_true", help="Disable capital interest costs"
    )

    args = parser.parse_args()

    # Get class from Registry
    selected_pricer_class = BasePricer.get_pricer_class(args.pricer)
    logger.info(f"Using Pricer: {selected_pricer_class.__name__}")

    # Load data
    result = read_problem(args.instance)
    if not result:
        return

    settings, locations, products, links, routes = result

    # --- INJECT ARGUMENTS INTO SETTINGS ---
    settings = dataclasses.replace(
        settings,
        epsilon=args.epsilon,
        big_m=args.big_m,
        enable_transport=not args.no_transport,
        enable_co2=not args.no_co2,
        enable_interest=not args.no_interest,
    )

    # Log active components
    active_costs = []
    if settings.enable_transport:
        active_costs.append("Transport")
    if settings.enable_co2:
        active_costs.append("CO2")
    if settings.enable_interest:
        active_costs.append("Interest")
    logger.info(f"Active Cost Components: {', '.join(active_costs)}")

    print_problem_stats(locations, products, links, routes)

    # Initialize Master Problem
    problem = MasterProblem(settings, locations, products, links, routes)
    problem.build_model()

    # Solve
    problem.solve(
        pricer_class=selected_pricer_class, mode=args.mode, export_lp=args.export_lp
    )
    problem.print_results()


if __name__ == "__main__":
    main()
