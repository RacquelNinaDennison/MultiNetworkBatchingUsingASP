import multiprocessing
import logging
from pyscipopt import Model
from logic import CostCalculator
from pricers.base_pricer import BasePricer

logger = logging.getLogger(__name__)


def solve_subproblem_worker(task_data):
    """
    Worker to solve the Knapsack Subproblem.
    """
    route = task_data["route"]
    valid_products = task_data["valid_products"]
    duals = task_data["duals"]

    capacity = task_data["capacity"]
    duration = task_data["duration"]
    fixed_cost = task_data["fixed_cost"]
    settings = task_data["settings"]

    if not valid_products:
        return None

    sub_scip = Model("sub_parallel")
    sub_scip.hideOutput()

    vars_dict = {}
    for p in valid_products:
        var = sub_scip.addVar(vtype="I", lb=0, name=f"q_{p.name}")
        vars_dict[p] = var

    sub_scip.addCons(sum(vars_dict[p] * p.size for p in valid_products) <= capacity)

    obj_expr = fixed_cost

    for p in valid_products:
        interest_per_unit = CostCalculator.calculate_interest(
            p.value, duration, settings
        )
        mu_val = duals.get((route.transport_link, p), 0.0)
        obj_expr += vars_dict[p] * (interest_per_unit - mu_val)

    sub_scip.setObjective(obj_expr, sense="minimize")
    sub_scip.optimize()

    min_rc = sub_scip.getObjVal()

    # Check Result using settings.epsilon
    if min_rc < -settings.epsilon:
        pattern = {p.id: sub_scip.getVal(vars_dict[p]) for p in valid_products}
        return {
            "route": route,
            "pattern_data": pattern,
            "duration": duration,
            "fixed_cost": fixed_cost,
            "reduced_cost": min_rc,
        }
    return None


@BasePricer.register("scip")
class ScipKnapsackPricer(BasePricer):
    def find_patterns(self, duals):
        tasks = []
        for route in self.routes:
            cap, dur, f_cost, valid_prods = self.prepare_subproblem_data(route)

            if not valid_prods:
                continue

            tasks.append(
                {
                    "route": route,
                    "valid_products": valid_prods,
                    "capacity": cap,
                    "duration": dur,
                    "fixed_cost": f_cost,
                    "duals": duals,
                    "settings": self.settings,
                }
            )

        with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
            results = pool.map(solve_subproblem_worker, tasks)

        formatted_results = []
        prod_map = {p.id: p for p in self.products}
        best_rc = 0.0

        for res in results:
            if res and res["reduced_cost"] < -self.settings.epsilon:
                if res["reduced_cost"] < best_rc:
                    best_rc = res["reduced_cost"]

                pattern_obj = {
                    prod_map[p_id]: qty for p_id, qty in res["pattern_data"].items()
                }

                formatted_results.append(
                    {
                        "route": res["route"],
                        "pattern": pattern_obj,
                        "duration": res["duration"],
                        "fixed_cost": res["fixed_cost"],
                    }
                )

        if best_rc < 0:
            logger.info(f"Best Reduced Cost: {best_rc:.4f}")

        return formatted_results
