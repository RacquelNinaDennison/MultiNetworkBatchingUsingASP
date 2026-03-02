#!/usr/bin/env python3
"""
analysis/generator.py

Feasible instance generator for the logistics multi-batching ASP encoding.

Design goals
------------
- Avoid random fake-UNSAT instances.
- Produce paper-like layered transport networks.
- Keep producer -> consumer reachability valid for each product.
- Compute safe domain bounds for maxFlow / maxFreq / maxParts so the
  encoding is not made UNSAT by too-small domains.
"""

import argparse
import random
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple


def split_amount(total: int, parts: int, rng: random.Random) -> List[int]:
    if parts <= 0 or total <= 0:
        return [0] * max(parts, 0)
    if parts == 1:
        return [total]
    if total < parts:
        out = [1] * total + [0] * (parts - total)
        rng.shuffle(out)
        return out

    cuts = sorted(rng.sample(range(1, total), parts - 1))
    cuts = [0] + cuts + [total]
    return [cuts[i + 1] - cuts[i] for i in range(len(cuts) - 1)]


def generate_transport_resources(
    n: int,
    capacity_range: Tuple[int, int],
    rng: random.Random,
    cost_range: Tuple[int, int] = (30, 80),
    co2_range: Tuple[int, int] = (30, 80),
) -> List[Dict]:
    trs = []
    for i in range(n):
        trs.append({
            "name": f"tr{i+1}",
            "capacity": rng.randint(*capacity_range),
            "cost": rng.randint(*cost_range),
            "co2": rng.randint(*co2_range),
        })
    return trs


def build_layered_links(locations: List[str], target_links: int, rng: random.Random) -> List[Tuple[str, str]]:
    """
    Build a forward-only layered DAG:
      left -> middle -> right
    with optional forward skip edges.
    """
    n = len(locations)
    cut1 = max(1, n // 3)
    cut2 = max(cut1 + 1, (2 * n) // 3)

    left = locations[:cut1]
    middle = locations[cut1:cut2]
    right = locations[cut2:]

    if not middle:
        middle = [locations[min(len(locations) - 1, 1)]]
    if not right:
        right = [locations[-1]]

    links = set()

    for u in left:
        links.add((u, rng.choice(middle)))
    for u in middle:
        links.add((u, rng.choice(right)))

    candidates = []
    for u in left:
        for v in middle + right:
            if u != v:
                candidates.append((u, v))
    for u in middle:
        for v in right:
            if u != v:
                candidates.append((u, v))

    rng.shuffle(candidates)
    for e in candidates:
        if len(links) >= target_links:
            break
        links.add(e)

    return sorted(links)


def build_routes_for_links(
    links: List[Tuple[str, str]],
    transport_resources: List[Dict],
    target_routes: int,
    distance_range: Tuple[int, int],
    rng: random.Random,
) -> List[Dict]:
    """
    Create routes over links.
    By default: at most one route per (link, transport resource),
    which keeps the benchmark controlled and interpretable.
    """
    routes: List[Dict] = []

    # Ensure at least one route per link.
    for frm, to in links:
        tr = rng.choice(transport_resources)
        routes.append({
            "from": frm,
            "to": to,
            "tr": tr["name"],
            "distance": rng.randint(*distance_range),
            "cost": tr["cost"],
        })

    # Add additional routes on the same link using different TRs.
    remaining = max(0, target_routes - len(routes))
    idx = 0
    while remaining > 0 and links:
        frm, to = links[idx % len(links)]
        used = {r["tr"] for r in routes if r["from"] == frm and r["to"] == to}
        avail = [tr for tr in transport_resources if tr["name"] not in used]
        if avail:
            tr = rng.choice(avail)
            routes.append({
                "from": frm,
                "to": to,
                "tr": tr["name"],
                "distance": rng.randint(*distance_range),
                "cost": tr["cost"],
            })
            remaining -= 1
        idx += 1
        if idx > len(links) * max(1, len(transport_resources)):
            break

    return routes


def graph_from_routes(routes: List[Dict]) -> Dict[str, Set[str]]:
    g = defaultdict(set)
    for r in routes:
        g[r["from"]].add(r["to"])
    return g


def transitive_reachability(locations: List[str], routes: List[Dict]) -> Dict[str, Set[str]]:
    g = graph_from_routes(routes)
    reach = {loc: set() for loc in locations}
    for src in locations:
        seen = set()
        q = deque([src])
        while q:
            u = q.popleft()
            for v in g.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        seen.discard(src)
        reach[src] = seen
    return reach


def choose_producers_consumers(
    locations: List[str],
    routes: List[Dict],
    rng: random.Random,
    producer_range: Tuple[int, int] = (1, 2),
    consumer_range: Tuple[int, int] = (1, 3),
) -> Tuple[List[str], List[str]]:
    """
    Pick producers and consumers so every consumer is reachable from
    at least one producer.
    """
    reach = transitive_reachability(locations, routes)

    producer_candidates = [loc for loc in locations if len(reach[loc]) > 0]
    producer_candidates.sort(key=lambda x: len(reach[x]), reverse=True)
    if not producer_candidates:
        raise ValueError("No valid producer candidates in generated network.")

    n_prod = min(rng.randint(*producer_range), len(producer_candidates))
    producers = producer_candidates[:]
    rng.shuffle(producers)
    producers = producers[:n_prod]

    covered = set()
    for p in producers:
        covered |= reach[p]

    consumer_pool = [loc for loc in locations if loc not in producers and loc in covered]
    if not consumer_pool:
        raise ValueError("No reachable consumers for chosen producers.")

    n_cons = min(rng.randint(*consumer_range), len(consumer_pool))
    rng.shuffle(consumer_pool)
    consumers = consumer_pool[:n_cons]
    return producers, consumers


def generate_products(
    n: int,
    transport_resources: List[Dict],
    size_range: Tuple[int, int],
    value_range: Tuple[int, int],
    rng: random.Random,
) -> List[Dict]:
    min_capacity = min(tr["capacity"] for tr in transport_resources)
    size_hi = min(size_range[1], min_capacity)
    size_lo = min(size_range[0], size_hi)

    products = []
    for i in range(n):
        products.append({
            "name": f"p{i+1}",
            "size": rng.randint(size_lo, size_hi),
            "value": rng.randint(*value_range),
        })
    return products


def generate_demands(
    products: List[Dict],
    locations: List[str],
    routes: List[Dict],
    demand_range: Tuple[int, int],
    rng: random.Random,
) -> List[Dict]:
    demands = []

    for p in products:
        producers, consumers = choose_producers_consumers(locations, routes, rng)

        total_demand = rng.randint(*demand_range)
        consumer_amounts = split_amount(total_demand, len(consumers), rng)
        producer_amounts = split_amount(sum(consumer_amounts), len(producers), rng)

        for loc, amt in zip(consumers, consumer_amounts):
            if amt > 0:
                demands.append({"product": p["name"], "location": loc, "rate": -amt})

        for loc, amt in zip(producers, producer_amounts):
            if amt > 0:
                demands.append({"product": p["name"], "location": loc, "rate": amt})

    return demands


def compute_safe_bounds(
    products: List[Dict],
    transport_resources: List[Dict],
    demands: List[Dict],
    max_bins: int,
) -> Dict[str, int]:
    """
    Safe domain computation for your current encoding.

    Important:
    - bins(0..maxBins) means actual number of bins is maxBins + 1.
    - a single arc may need to carry the total downstream demand of a product.
    """
    total_demand_by_product = defaultdict(int)
    max_local_abs = 0

    for d in demands:
        max_local_abs = max(max_local_abs, abs(d["rate"]))
        if d["rate"] < 0:
            total_demand_by_product[d["product"]] += -d["rate"]

    max_total_product_demand = max(total_demand_by_product.values(), default=max_local_abs or 1)

    min_product_size = min(p["size"] for p in products)
    max_capacity = max(tr["capacity"] for tr in transport_resources)

    max_parts = max(1, max_capacity // max(1, min_product_size))

    actual_bins = max_bins + 1
    per_route_product_capacity = max(1, actual_bins * max_parts)

    max_flow = max(max_total_product_demand, max_local_abs) + 2
    max_freq = (max_total_product_demand + per_route_product_capacity - 1) // per_route_product_capacity + 2

    return {
        "maxFlow": max_flow,
        "maxFreq": max_freq,
        "maxParts": max_parts,
    }


def format_instance(
    locations: List[str],
    transport_resources: List[Dict],
    products: List[Dict],
    routes: List[Dict],
    demands: List[Dict],
    bounds: Dict[str, int],
    max_bins: int,
    co2_price: int = 90,
) -> str:
    lines = []
    link_count = len({(r["from"], r["to"]) for r in routes})

    lines.append("% ===============================================================")
    lines.append("% Auto-generated feasible paper-like instance")
    lines.append(f"% Locations={len(locations)} Links={link_count} Routes={len(routes)} Products={len(products)} TR={len(transport_resources)}")
    lines.append("% ===============================================================")
    lines.append("")
    lines.append("% --- Domain Overrides ---")
    lines.append(f"#const maxFlow = {bounds['maxFlow']}.")
    lines.append(f"#const maxFreq = {bounds['maxFreq']}.")
    lines.append(f"#const maxParts = {bounds['maxParts']}.")
    lines.append(f"#const maxBins = {max_bins}.")
    lines.append("")
    lines.append("% --- Instance domains ---")
    lines.append("numFlow(0..maxFlow).")
    lines.append("numFreq(0..maxFreq).")
    lines.append("numParts(0..maxParts).")
    lines.append("bins(0..maxBins).")
    lines.append("")

    lines.append("% --- Locations ---")
    for loc in locations:
        lines.append(f"location({loc}).")
    lines.append("")

    lines.append("% --- Products ---")
    for p in products:
        lines.append(f"part({p['name']}).")
        lines.append(f"partSize({p['name']}, {p['size']}).")
        lines.append(f"partValue({p['name']}, {p['value']}).")
    lines.append("")

    lines.append("% --- Transport Resources ---")
    for tr in transport_resources:
        lines.append(f"transportCapacity({tr['name']}, {tr['capacity']}).")
        lines.append(f"co2emission({tr['name']}, {tr['co2']}).")
    lines.append(f"co2price({co2_price}).")
    lines.append("")

    lines.append("% --- Supply / Demand ---")
    for d in demands:
        lines.append(f"demandOffer({d['product']}, {d['location']}, {d['rate']}).")
    lines.append("")

    lines.append("% --- Routes ---")
    grouped = defaultdict(list)
    for r in routes:
        grouped[(r["from"], r["to"])].append(r)
    for (frm, to), rs in sorted(grouped.items()):
        lines.append(f"% Link {frm} -> {to}")
        for r in rs:
            lines.append(f"route({frm}, {to}, {r['tr']}, {r['distance']}, {r['cost']}).")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Feasible generator for logistics ASP")
    parser.add_argument("--seed", type=int, default=42)

    parser.add_argument("--locations", type=int, default=6)
    parser.add_argument("--products", type=int, default=2)
    parser.add_argument("--transport-resources", type=int, default=2)

    parser.add_argument("--target-links", type=int, default=10)
    parser.add_argument("--target-routes", type=int, default=19)

    parser.add_argument("--capacity-min", type=int, default=10)
    parser.add_argument("--capacity-max", type=int, default=15)

    parser.add_argument("--size-min", type=int, default=2)
    parser.add_argument("--size-max", type=int, default=4)

    parser.add_argument("--value-min", type=int, default=100)
    parser.add_argument("--value-max", type=int, default=2000)

    parser.add_argument("--demand-min", type=int, default=10)
    parser.add_argument("--demand-max", type=int, default=40)

    parser.add_argument("--distance-min", type=int, default=1)
    parser.add_argument("--distance-max", type=int, default=8)

    parser.add_argument("--max-bins", type=int, default=1,
                        help="Actual bins are maxBins+1 because the encoding uses bins(0..maxBins).")

    args = parser.parse_args()
    rng = random.Random(args.seed)

    transport_resources = generate_transport_resources(
        args.transport_resources,
        capacity_range=(args.capacity_min, args.capacity_max),
        rng=rng,
    )

    locations = [f"l{i+1}" for i in range(args.locations)]
    links = build_layered_links(locations, args.target_links, rng)
    routes = build_routes_for_links(
        links=links,
        transport_resources=transport_resources,
        target_routes=args.target_routes,
        distance_range=(args.distance_min, args.distance_max),
        rng=rng,
    )

    products = generate_products(
        args.products,
        transport_resources,
        size_range=(args.size_min, args.size_max),
        value_range=(args.value_min, args.value_max),
        rng=rng,
    )

    demands = generate_demands(
        products=products,
        locations=locations,
        routes=routes,
        demand_range=(args.demand_min, args.demand_max),
        rng=rng,
    )

    bounds = compute_safe_bounds(
        products=products,
        transport_resources=transport_resources,
        demands=demands,
        max_bins=args.max_bins,
    )

    text = format_instance(
        locations=locations,
        transport_resources=transport_resources,
        products=products,
        routes=routes,
        demands=demands,
        bounds=bounds,
        max_bins=args.max_bins,
    )


if __name__ == "__main__":
    main()
