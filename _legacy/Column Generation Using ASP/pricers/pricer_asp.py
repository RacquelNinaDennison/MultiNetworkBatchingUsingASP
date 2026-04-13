import logging
import multiprocessing
import os
from typing import Dict, Optional, Any, Set, List

import clingo
import clingo.ast
from clingcon import ClingconTheory

from pricers.base_pricer import BasePricer
from logic import CostCalculator

logger = logging.getLogger(__name__)

# scaling for ASP
SCALE = 1000
MIN_RC_THRESHOLD = 0.01


def _to_int_scaled(x: float) -> int:
    """Scale float -> int for clingcon."""
    return int(round(float(x) * SCALE))


def _build_facts(
    capacity: float,
    fixed_cost: float,
    valid_products,
    route,
    duals: Dict,
    duration: float,
    settings,
) -> str:
    """
    Builing facts for the ASP knapsack problem. This includes route capacity, fixed cost, and product-specific data like size, interest, and dual values.
    """
    cap_i = int(round(capacity))
    fixed_i = _to_int_scaled(fixed_cost)

    lines = []
    lines.append(f"scale({SCALE}).")
    lines.append(f"capacity({cap_i}).")
    lines.append(f"fixed_cost({fixed_i}).")

    for p in valid_products:
        pid = int(p.id)
        size_i = int(round(p.size))

        interest_per_unit = CostCalculator.calculate_interest(
            p.value, duration, settings
        )
        mu_val = duals.get((route.transport_link, p), 0.0)

        logger.debug(
            f"Product {p.id}: size={size_i}, interest/unit={interest_per_unit:.4f}, mu={mu_val:.4f}"
        )

        lines.append(f"valid({pid}).")
        lines.append(f"size({pid},{size_i}).")
        lines.append(f"interest({pid},{_to_int_scaled(interest_per_unit)}).")
        lines.append(f"mu({pid},{_to_int_scaled(mu_val)}).")

    return "\n".join(lines) + "\n"


def _create_pattern_key_from_ids(route, pattern_data: Dict[int, int]) -> tuple:
    """
    Create a hashable, serializable key for deduplication.
    Uses string representations instead of object ids.

    The main purpose for this was to detect duplicated patterns across different worker processes, since object ids are not consistent across processes.
    By using a string representation of the route and product IDs, we can reliably identify duplicates regardless of which process they were generated in.

    Args:
        route: Route object
        pattern_data: Dict mapping product_id (int) -> quantity (int)

    Returns:
        Hashable tuple identifying this unique pattern
    """
    items = tuple(sorted((pid, qty) for pid, qty in pattern_data.items() if qty > 0))
    route_key = (repr(route.transport_link), route.transport_resource.name)
    return (route_key, items)


def solve_subproblem_worker_asp(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Multiprocessing worker: solve one route's knapsack pricing with clingcon.
    Returns dict if a negative reduced-cost column is found, else None.
    """
    route = task["route"]
    valid_products = task["valid_products"]
    duals = task["duals"]
    capacity = task["capacity"]
    duration = task["duration"]
    fixed_cost = task["fixed_cost"]
    settings = task["settings"]
    lp_path = task["lp_path"]
    already_added_keys: Set[tuple] = task.get("already_added_keys", set())

    if not valid_products:
        return None

    facts = _build_facts(
        capacity=capacity,
        fixed_cost=fixed_cost,
        valid_products=valid_products,
        route=route,
        duals=duals,
        duration=duration,
        settings=settings,
    )

    theory = ClingconTheory()
    ctl = clingo.Control(["0", "--opt-mode=optN"])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:

        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)

        clingo.ast.parse_string(facts, on_rule)
        clingo.ast.parse_files([lp_path], on_rule)

    ctl.ground([("base", [])])
    theory.prepare(ctl)

    all_solutions: List[Dict] = []
    eps_scaled = _to_int_scaled(MIN_RC_THRESHOLD)

    def on_model(model: clingo.Model):
        theory.on_model(model)

        q_by_id: Dict[int, int] = {}

        # Rebuilding the syntax tree 
        for name, value in theory.assignment(model.thread_id):
            s = str(name)
            if s.startswith("x(") and s.endswith(")"):
                try:
                    pid = int(s[2:-1])
                    qty = int(value)
                    if qty > 0:
                        q_by_id[pid] = qty
                except ValueError:
                    continue

        if not q_by_id:
            return

        pattern_key = _create_pattern_key_from_ids(route, q_by_id)

        if pattern_key in already_added_keys:
            return


        rc_i = _to_int_scaled(fixed_cost)

        for p in valid_products:
            q = q_by_id.get(int(p.id), 0)
            if q <= 0:
                continue

            interest_per_unit = CostCalculator.calculate_interest(
                p.value, duration, settings
            )
            mu_val = duals.get((route.transport_link, p), 0.0)
            rc_i += q * (_to_int_scaled(interest_per_unit) - _to_int_scaled(mu_val))

        all_solutions.append(
            {"rc_i": rc_i, "pattern": q_by_id.copy(), "pattern_key": pattern_key}
        )

    ctl.solve(on_model=on_model)

    if not all_solutions:
        return None
    best_solution = None
    for sol in all_solutions:
        if sol["rc_i"] < -eps_scaled:
            if best_solution is None or sol["rc_i"] < best_solution["rc_i"]:
                best_solution = sol

    if best_solution is None:
        return None

    return {
        "route": route,
        "pattern_data": best_solution["pattern"],
        "pattern_key": best_solution["pattern_key"],
        "duration": duration,
        "fixed_cost": fixed_cost,
        "reduced_cost": best_solution["rc_i"] / SCALE,
        "reduced_cost_scaled": best_solution["rc_i"],
    }


@BasePricer.register("asp")
class AspKnapsackPricer(BasePricer):
    """
    Column generation pricing via ASP/Clingcon knapsack.
    """

    def __init__(self, constraints, products, links, routes, settings, mode):
        super().__init__(constraints, products, links, routes, settings, mode)
        self._added_pattern_keys: Set[tuple] = set()

    def _pattern_key(self, route, pattern):
        """Override to use same key format as workers."""
        items = tuple(sorted((p.id, qty) for p, qty in pattern.items() if qty > 0))
        route_key = (repr(route.transport_link), route.transport_resource.name)
        return (route_key, items)

    def find_patterns(self, duals):
        here = os.path.dirname(__file__)
        lp_path = os.path.join(here, "asp", "knapsack.lp")

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
                    "lp_path": lp_path,
                    "already_added_keys": self._added_pattern_keys.copy(),
                }
            )

        if not tasks:
            return []

        with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
            results = pool.map(solve_subproblem_worker_asp, tasks)

        prod_map = {int(p.id): p for p in self.products}

        formatted_results = []
        best_rc = 0.0
        seen_in_this_round: Set[tuple] = set()

        for res in results:
            if not res:
                continue

            rc = float(res["reduced_cost"])
            pattern_key = res["pattern_key"]

            if rc >= -MIN_RC_THRESHOLD:
                continue

 
            if pattern_key in seen_in_this_round:
                logger.debug(f"Skipping duplicate pattern in round: {pattern_key}")
                continue
            if pattern_key in self._added_pattern_keys:
                logger.debug(f"Skipping previously added pattern: {pattern_key}")
                continue


            seen_in_this_round.add(pattern_key)

            self._added_pattern_keys.add(pattern_key)

            best_rc = min(best_rc, rc)

            pattern_obj = {}
            for pid, qty in res["pattern_data"].items():
                p_obj = prod_map.get(int(pid))
                if p_obj is not None:
                    pattern_obj[p_obj] = int(qty)

            formatted_results.append(
                {
                    "route": res["route"],
                    "pattern": pattern_obj,
                    "duration": res["duration"],
                    "fixed_cost": res["fixed_cost"],
                    "reduced_cost": rc,
                }
            )

        if best_rc < 0:
            logger.info(f"[AspKnapsackPricer] Best Reduced Cost: {best_rc:.6f}")

        return formatted_results
