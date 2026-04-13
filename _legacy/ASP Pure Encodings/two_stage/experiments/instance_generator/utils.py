import random
from collections import defaultdict
from typing import List, Dict, Optional

from problem import (
    MultibatchingProblem,
    MultibatchingSolution,
    TransportType,
    Product,
    Location,
    TransportLink
)

def generate_multibatching_problem(
        num_locations: int = 6,
        num_transport_types: int = 2,
        num_products: int = 2,
        min_dist: int = 1,
        max_dist: int = 10,
        min_capacity: int = 10,
        max_capacity: int = 20,
        min_product_size: int = 1,
        max_product_size: int = 5,
        min_product_value: int = 100,
        max_product_value: int = 1000,
        min_tt_cost: int = 10,
        max_tt_cost: int = 100,
        min_tt_speed: float = 0.1,
        max_tt_speed: float = 1.0,
        min_tt_emissions: int = 10,
        max_tt_emissions: int = 100,
        max_links_per_pair: int = 2,
        demand_sparsity: float = 0.5,
        max_demand_abs: int = 50,
        seed: int = None
) -> MultibatchingProblem:
    if seed is not None:
        random.seed(seed)

    # 1. Generate TransportType instances
    transport_types_list = []
    for i in range(num_transport_types):
        tt = TransportType(
            id=i + 1,
            cost=random.randint(min_tt_cost, max_tt_cost),
            speed=round(random.uniform(min_tt_speed, max_tt_speed), 1),
            emissions=random.randint(min_tt_emissions, max_tt_emissions),
            capacity=random.randint(min_capacity, max_capacity),
            name=f"transport_{i}"
        )
        transport_types_list.append(tt)

    # 2. Generate Product instances
    products_list = []
    for i in range(num_products):
        num_valid_tts = random.randint(1, len(transport_types_list))
        valid_transports = frozenset(random.sample(transport_types_list, num_valid_tts))
        prod = Product(
            id=i + 1,
            size=random.randint(min_product_size, max_product_size),
            value=random.randint(min_product_value, max_product_value),
            valid_transports=valid_transports,
            name=f"p{i+1}"
        )
        products_list.append(prod)

    # 3. Generate Location instances with balanced net_supply
    locations_list = []
    product_global_demands = defaultdict(int)

    temp_demands = defaultdict(lambda: defaultdict(int))
    for i in range(num_locations):
        loc_id = f'l{i + 1}'
        for prod in products_list:
            if random.random() < demand_sparsity:
                demand_val = random.randint(-max_demand_abs, max_demand_abs)
                if demand_val != 0:
                    temp_demands[loc_id][prod] = demand_val
                    product_global_demands[prod] += demand_val

    # Adjust last location's demand to balance totals
    if num_locations > 0:
        last_loc_id = f'l{num_locations}'
        for prod in products_list:
            if product_global_demands[prod] != 0:
                temp_demands[last_loc_id][prod] -= product_global_demands[prod]
                product_global_demands[prod] = 0

    for i in range(num_locations):
        loc_id = f'l{i + 1}'
        loc = Location(id=loc_id, net_supply=dict(temp_demands[loc_id]), name=loc_id)
        locations_list.append(loc)

    # 4. Generate TransportLink instances
    transport_links_list = []
    current_link_id = 0
    for i in range(num_locations):
        for j in range(num_locations):
            if i == j:
                continue

            loc1 = locations_list[i]
            loc2 = locations_list[j]

            available_tts_for_pair = list(transport_types_list)
            random.shuffle(available_tts_for_pair)

            links_created_for_pair = 0
            for tt in available_tts_for_pair:
                if links_created_for_pair >= max_links_per_pair:
                    break

                link = TransportLink(
                    id=str(current_link_id),
                    location_l1=loc1,
                    location_l2=loc2,
                    distance=random.randint(min_dist, max_dist),
                    transport_type=tt
                )
                transport_links_list.append(link)
                current_link_id += 1
                links_created_for_pair += 1

    # 5. Create MultibatchingProblem Instance
    problem_instance = MultibatchingProblem(
        transport_types=transport_types_list,
        products=products_list,
        locations=locations_list,
        transport_links=transport_links_list
    )

    return problem_instance

def basic_sanity_check(problem: MultibatchingProblem):
    total_flow_per_product = defaultdict(int)
    details = defaultdict(list)
    for location in problem.locations:
        for p, qty in location.net_supply.items():
            total_flow_per_product[p] += qty
            if qty != 0:
                details[p].append((location.id, qty))

    print("\n--- Sanity Check: Supply/Demand Balance ---")
    all_balanced = True
    for p in problem.products:
        balance = total_flow_per_product[p]
        print(f"Product {p.name}: Global Net Flow = {balance}")
        if balance != 0:
            print(f"  -> WARNING: Imbalance detected for {p.name}. Nodes: {details[p]}")
            all_balanced = False

    if all_balanced:
        print(">> All products are perfectly balanced.")
    return total_flow_per_product
