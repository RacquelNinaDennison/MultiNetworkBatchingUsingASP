"""
Template for adding a new Pricing Solver.

Steps to use:
1. Copy this file.
2. Rename the class and the file.
3. Change the register name in the decorator: @BasePricer.register("my_new_algo").
4. Implement the 'find_patterns' method.
"""

import logging
from pricers.base_pricer import BasePricer

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# REGISTER YOUR PRICER HERE
# The string "template" is what you will pass to the command line:
# python main.py instance.json --pricer template
# ------------------------------------------------------------------
@BasePricer.register("template")
class TemplatePricer(BasePricer):
    """
    A template pricer that demonstrates how to interface with the Master Problem.
    """

    def find_patterns(self, duals):
        """
        Core Logic Method.

        Args:
            duals (dict): A dictionary of dual values from the Master Problem.
                          Key: (TransportLink, Product) -> Value: float (mu)

        Returns:
            list: A list of dictionaries, where each dictionary represents a found column/pattern.
                  Format:
                  {
                      'route': Route object,
                      'pattern': {Product object: quantity (float)},
                      'duration': float (hours),
                      'fixed_cost': float (currency)
                  }
        """
        found_patterns = []

        # Loop through all available routes (candidate transport resources)
        for route in self.routes:
            # --- 1. PREPARE DATA ---
            # Use the helper to get all necessary metrics and filtered products
            capacity, duration, fixed_cost, valid_products = (
                self.prepare_subproblem_data(route)
            )

            if not valid_products:
                continue

            # --- 2. SOLVE SUBPROBLEM ---
            # This is where you plug in your algorithm (ASP, Gurobi, Heuristic, etc.)
            # Goal: Maximize Reduced Cost = Sum(qty * (dual - interest)) - FixedCost

            # Example (Dummy) Logic: Just take 1 unit of the first product
            # (Replace this with your actual knapsack solver!)
            best_pattern = {}
            best_rc = 0.0
            # best_pattern = {valid_products[0]: 1.0}  # <--- YOUR SOLVER RESULT HERE
            # best_rc = -12  # <--- YOUR SOLVER RESULT HERE

            # --- 3. FORMAT OUTPUT ---
            # if best_pattern and best_rc < -self.settings.epsilon:
            #     found_patterns.append({
            #         'route': route,
            #         'pattern': best_pattern,
            #         'duration': duration,
            #         'fixed_cost': fixed_cost
            #     })
            pass

        return found_patterns
