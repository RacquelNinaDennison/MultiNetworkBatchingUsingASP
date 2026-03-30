import logging
from pricers.base_pricer import BasePricer
from logic import CostCalculator

logger = logging.getLogger(__name__)


@BasePricer.register("greedy")
class GreedyPricer(BasePricer):
    """
    A simple heuristic pricer that sorts items by 'efficiency'.
    """

    def find_patterns(self, duals):
        found_patterns = []

        for route in self.routes:
            # Use BasePricer helper
            capacity, duration, fixed_cost, valid_products = (
                self.prepare_subproblem_data(route)
            )

            if not valid_products:
                continue

            candidates = []
            for p in valid_products:
                mu = duals.get((route.transport_link, p), 0.0)
                interest = CostCalculator.calculate_interest(
                    p.value, duration, self.settings
                )

                # Net impact on Reduced Cost (negative is good)
                net_cost_per_unit = interest - mu

                if net_cost_per_unit < 0:
                    candidates.append((p, net_cost_per_unit, p.size))

            # Sort by Efficiency: Most negative cost per unit of size
            candidates.sort(key=lambda x: x[1] / x[2])

            current_load = 0.0
            pattern = {}

            for prod, cost_impact, size in candidates:
                if current_load + size <= capacity:
                    qty = int((capacity - current_load) // size)
                    if qty > 0:
                        pattern[prod] = float(qty)
                        current_load += qty * size

            if pattern:
                variable_part_rc = sum(
                    qty
                    * (
                        CostCalculator.calculate_interest(
                            p.value, duration, self.settings
                        )
                        - duals.get((route.transport_link, p), 0)
                    )
                    for p, qty in pattern.items()
                )

                total_rc = fixed_cost + variable_part_rc

                # Check Result using settings.epsilon
                if total_rc < -self.settings.epsilon:
                    found_patterns.append(
                        {
                            "route": route,
                            "pattern": pattern,
                            "duration": duration,
                            "fixed_cost": fixed_cost,
                        }
                    )

        return found_patterns
