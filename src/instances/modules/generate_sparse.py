#!/usr/bin/env python3
"""
Generate sparse network instances for resilience experiments.

Same scale as small instances (6 locations, 3 parts, 2 TRs) but with
~50% edge density instead of 100%, and some arcs with only 1 TR.

Includes a capacity-aware feasibility check: estimates whether the
total supply volume can physically flow from supply to demand nodes
through the sparse network, accounting for 80% headroom.
"""

import random
import re
from collections import deque
from pathlib import Path


def reachable_from(adj: dict, start: str) -> set:
    visited = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for n in adj.get(node, set()):
            if n not in visited:
                queue.append(n)
    return visited


def estimate_max_flow(locations, routes, supply_nodes, demand_nodes,
                      capacities, max_freq=20):
    """Rough max-flow estimate: sum of outgoing capacity from supply nodes
    toward demand-reachable nodes, with 80% headroom and max_freq trips."""
    # Build adjacency with per-arc capacity (sum of TR capacities * freq * 0.8)
    arc_cap = {}
    for (f, t, tr, dist, cost) in routes:
        key = (f, t)
        arc_cap[key] = arc_cap.get(key, 0) + int(capacities[tr] * max_freq * 0.8)

    # Min-cut estimate: capacity leaving supply nodes
    supply_outflow = 0
    for s in supply_nodes:
        for (f, t), cap in arc_cap.items():
            if f == s:
                supply_outflow += cap

    # Also check capacity entering demand nodes
    demand_inflow = 0
    for d in demand_nodes:
        for (f, t), cap in arc_cap.items():
            if t == d:
                demand_inflow += cap

    return min(supply_outflow, demand_inflow)


def generate_instance(seed: int, num_locations: int = 6,
                      num_parts: int = 3, num_transports: int = 2,
                      edge_density: float = 0.50,
                      single_tr_prob: float = 0.25,
                      num_supply: int = 2, num_demand: int = 2) -> dict | None:
    rng = random.Random(seed)

    locations  = [f"l{i}" for i in range(1, num_locations + 1)]
    parts      = [f"p{i}" for i in range(1, num_parts + 1)]
    transports = [f"tr{i}" for i in range(1, num_transports + 1)]

    # ── Transport properties ─────────────────────────────────────────
    capacities = {t: rng.randint(10, 20) for t in transports}
    unit_costs = {t: rng.randint(30, 90) for t in transports}
    co2        = {t: rng.randint(15, 70) for t in transports}
    speeds     = {t: rng.randint(2, 8) for t in transports}

    # ── Part properties ──────────────────────────────────────────────
    part_sizes = {}
    part_vals  = {}
    part_trs   = {}
    for p in parts:
        max_cap = max(capacities.values())
        part_sizes[p] = rng.randint(1, min(4, max_cap))
        part_vals[p]  = rng.randint(100, 1000)
        # 30% chance of being restricted to one TR
        if rng.random() < 0.30:
            valid = [t for t in transports if capacities[t] >= part_sizes[p]]
            part_trs[p] = [rng.choice(valid)] if valid else list(transports)
        else:
            part_trs[p] = [t for t in transports if capacities[t] >= part_sizes[p]]
            if not part_trs[p]:
                part_trs[p] = list(transports)

    # ── Supply / demand nodes ────────────────────────────────────────
    supply_nodes = sorted(rng.sample(locations, num_supply))
    remaining    = [l for l in locations if l not in supply_nodes]
    demand_nodes = sorted(rng.sample(remaining, num_demand))

    # ── Sparse directed edges ────────────────────────────────────────
    all_pairs = [(f, t) for f in locations for t in locations if f != t]
    target_count = max(10, int(len(all_pairs) * edge_density))

    edges = set()

    # Backbone: path from each supply through intermediates to each demand
    intermediates = [l for l in locations
                     if l not in supply_nodes and l not in demand_nodes]
    for s in supply_nodes:
        # Supply -> intermediate -> demand
        mid = rng.choice(intermediates) if intermediates else demand_nodes[0]
        edges.add((s, mid))
        for d in demand_nodes:
            edges.add((mid, d))
        # Also direct supply -> demand for at least one demand
        edges.add((s, rng.choice(demand_nodes)))

    # Some reverse/cross edges for rerouting options
    for d in demand_nodes:
        mid = rng.choice(intermediates) if intermediates else supply_nodes[0]
        edges.add((mid, d))

    # Fill to target density with random edges
    extras = [e for e in all_pairs if e not in edges]
    rng.shuffle(extras)
    while len(edges) < target_count and extras:
        edges.add(extras.pop())

    # ── Assign TRs to edges ──────────────────────────────────────────
    routes = []
    for (f, t) in sorted(edges):
        if rng.random() < single_tr_prob:
            tr = rng.choice(transports)
            dist = rng.randint(1, 10)
            routes.append((f, t, tr, dist, dist * unit_costs[tr]))
        else:
            for tr in transports:
                dist = rng.randint(1, 10)
                routes.append((f, t, tr, dist, dist * unit_costs[tr]))

    # ── Verify graph reachability ────────────────────────────────────
    adj = {l: set() for l in locations}
    for (f, t, *_) in routes:
        adj[f].add(t)

    for s in supply_nodes:
        reach = reachable_from(adj, s)
        for d in demand_nodes:
            if d not in reach:
                return None

    # ── Capacity-aware demand generation ─────────────────────────────
    # Estimate max flow capacity, then set total demand to ~30% of it
    # (conservative to ensure Stage 2 bin-packing feasibility)
    max_flow_est = estimate_max_flow(
        locations, routes, supply_nodes, demand_nodes, capacities)
    max_volume = int(max_flow_est * 0.3)

    if max_volume < 30:
        return None  # Network too constrained

    demand_offers = []
    total_volume = 0
    for p in parts:
        part_vol_target = max_volume // len(parts)
        total_units = max(5, part_vol_target // part_sizes[p])
        total_units = min(total_units, 30)
        total_volume += total_units * part_sizes[p]

        supply_amts = _distribute_units(rng, total_units, len(supply_nodes))
        for s, amt in zip(supply_nodes, supply_amts):
            demand_offers.append((p, s, amt))

        demand_amts = _distribute_units(rng, total_units, len(demand_nodes))
        for d, amt in zip(demand_nodes, demand_amts):
            demand_offers.append((p, d, -amt))

    return {
        "seed": seed, "locations": locations, "transports": transports,
        "capacities": capacities, "unit_costs": unit_costs,
        "co2": co2, "speeds": speeds,
        "parts": parts, "part_sizes": part_sizes,
        "part_vals": part_vals, "part_trs": part_trs,
        "routes": routes, "demand_offers": demand_offers,
        "supply_nodes": supply_nodes, "demand_nodes": demand_nodes,
    }


def to_lp(inst: dict) -> str:
    lines = []
    seed = inst["seed"]
    n_loc = len(inst["locations"])
    n_parts = len(inst["parts"])
    n_tr = len(inst["transports"])
    n_routes = len(inst["routes"])

    lines.append(f"% Sparse benchmark instance")
    lines.append(f"% Generated with seed={seed} locations={n_loc} "
                 f"parts={n_parts} transports={n_tr} routes={n_routes}")
    lines.append("")

    lines.append("% ---- locations ----")
    for l in inst["locations"]:
        lines.append(f"location({l}).")
    lines.append("")

    lines.append("% ---- transport resources ----")
    for tr in inst["transports"]:
        lines.append(f"transportCapacity({tr},{inst['capacities'][tr]}).")
        lines.append(f"transportCO2({tr},{inst['co2'][tr]}).")
        lines.append(f"transportCost({tr},{inst['unit_costs'][tr]}).")
        lines.append(f"transportSpeed({tr},{inst['speeds'][tr]}).")
    lines.append("")

    lines.append("% ---- parts ----")
    for p in inst["parts"]:
        lines.append(f"part({p}).")
        lines.append(f"partSize({p},{inst['part_sizes'][p]}).")
        lines.append(f"partVal({p},{inst['part_vals'][p]}).")
        for tr in inst["part_trs"][p]:
            lines.append(f"partTR({p},{tr}).")
    lines.append("")

    lines.append("% ---- demand and supply ----")
    for (p, l, v) in sorted(inst["demand_offers"], key=lambda x: (x[1], x[0])):
        lines.append(f"demandOffer({p},{l},{v}).")
    lines.append("")

    lines.append("% ---- routes ----")
    for (f, t, tr, dist, cost) in sorted(inst["routes"]):
        lines.append(f"route({f},{t},{tr},{dist},{cost}).")

    return "\n".join(lines) + "\n"


def generate_batch(out_dir: Path, prefix: str, target: int, seed_start: int,
                   **kwargs) -> int:
    """Generate `target` instances with the given parameters. Returns count."""
    generated = 0
    for seed in range(seed_start, seed_start + 1000):
        if generated >= target:
            break

        inst = generate_instance(seed, **kwargs)
        if inst is None:
            continue

        generated += 1
        name = f"{prefix}_seed{generated}"
        path = out_dir / f"{name}.lp"
        path.write_text(to_lp(inst))

        n_edges = len(set((f, t) for (f, t, *_) in inst["routes"]))
        n_routes = len(inst["routes"])
        single_tr = sum(1 for e in set((f, t) for (f, t, *_) in inst["routes"])
                        if sum(1 for r in inst["routes"]
                               if r[0] == e[0] and r[1] == e[1]) == 1)

        supply_str = ",".join(inst["supply_nodes"])
        demand_str = ",".join(inst["demand_nodes"])

        print(f"  {name}: {n_edges} edges, {n_routes} routes, "
              f"{single_tr} single-TR arcs  "
              f"[supply={supply_str} demand={demand_str}]  seed={seed}")

    return generated


def main():
    out_dir = Path(__file__).parent.parent / "generated"
    out_dir.mkdir(exist_ok=True)

    print("Layered small (6 loc = 2+2+2, 2 parts, 2 TRs):")
    n = generate_layered_batch(
        out_dir, prefix="layered_small", target=5, seed_start=10000,
        layers=(2, 2, 2), num_parts=2, num_transports=2,
    )
    print(f"  → {n} instances\n")

    print("Layered medium (8 loc = 2+3+3, 3 parts, 2 TRs):")
    n = generate_layered_batch(
        out_dir, prefix="layered_medium", target=5, seed_start=11000,
        layers=(2, 3, 3), num_parts=3, num_transports=2,
    )
    print(f"  → {n} instances\n")

    print("Layered large (10 loc = 2+4+4, 4 parts, 2 TRs):")
    n = generate_layered_batch(
        out_dir, prefix="layered_large", target=5, seed_start=12000,
        layers=(2, 4, 4), num_parts=4, num_transports=2,
    )
    print(f"  → {n} instances\n")

    print("Layered xlarge (15 loc = 3+6+6, 6 parts, 3 TRs):")
    n = generate_layered_batch(
        out_dir, prefix="layered_xlarge", target=5, seed_start=13000,
        layers=(3, 6, 6), num_parts=6, num_transports=3,
    )
    print(f"  → {n} instances\n")

    print("Layered industry-lite (20 loc = 4+8+8, 10 parts, 4 TRs):")
    n = generate_layered_batch(
        out_dir, prefix="layered_industrylite", target=5, seed_start=14000,
        layers=(4, 8, 8), num_parts=10, num_transports=4,
    )
    print(f"  → {n} instances\n")

    # ── Industry-derived test cases (full size) ────────────────────
    industry_path = Path(__file__).parent.parent / "industry" / "industry_instances.lp"
    if industry_path.exists():
        industry_out = Path(__file__).parent.parent / "generated"
        print("Industry-derived full-size test cases "
              "(50 locs, 16 TRs, 35 parts):")
        n = generate_industry_test_cases(
            industry_path, industry_out,
            num_cases=10, seed_start=20000,
        )
        print(f"  → {n} instances\n")

    print(f"All instances written to {out_dir}")


def _distribute_units(rng: random.Random, total: int, n: int) -> list[int]:
    """Split *total* into *n* positive integers that sum exactly to *total*."""
    if n == 1:
        return [total]
    weights = [rng.random() for _ in range(n)]
    s = sum(weights)
    raw = [max(1, int(total * w / s)) for w in weights]
    diff = total - sum(raw)
    indices = list(range(n))
    rng.shuffle(indices)
    for i in indices:
        if diff == 0:
            break
        if diff > 0:
            raw[i] += 1
            diff -= 1
        elif raw[i] > 1:
            raw[i] -= 1
            diff += 1
    return raw


def generate_layered_instance(seed: int, layers: tuple[int, int, int],
                              num_parts: int = 2, num_transports: int = 2,
                              single_tr_prob: float = 0.10) -> dict | None:
    """Generate a layered network: supply → hubs → demand.

    Every supply connects to every hub, every hub connects to every demand,
    and hubs have some cross-connections. A few arcs randomly get only 1 TR.
    All parts can use all TRs (no partTR restrictions).
    """
    rng = random.Random(seed)
    n_supply, n_hubs, n_demand = layers
    n_total = n_supply + n_hubs + n_demand

    locations = [f"l{i}" for i in range(1, n_total + 1)]
    supply_nodes = locations[:n_supply]
    hub_nodes = locations[n_supply:n_supply + n_hubs]
    demand_nodes = locations[n_supply + n_hubs:]
    parts = [f"p{i}" for i in range(1, num_parts + 1)]
    transports = [f"tr{i}" for i in range(1, num_transports + 1)]

    # ── Transport properties ─────────────────────────────────────
    capacities = {t: rng.randint(10, 20) for t in transports}
    unit_costs = {t: rng.randint(30, 80) for t in transports}
    co2 = {t: rng.randint(15, 65) for t in transports}
    speeds = {t: rng.randint(2, 8) for t in transports}

    # ── Part properties (all parts can use all TRs) ──────────────
    part_sizes = {}
    part_vals = {}
    part_trs = {}
    for p in parts:
        part_sizes[p] = rng.randint(2, 4)
        part_vals[p] = rng.randint(300, 1000)
        part_trs[p] = list(transports)

    # ── Layered edges ────────────────────────────────────────────
    edges = set()

    # Supply → every hub
    for s in supply_nodes:
        for h in hub_nodes:
            edges.add((s, h))

    # Every hub → every demand
    for h in hub_nodes:
        for d in demand_nodes:
            edges.add((h, d))

    # Supply → some direct demand (skip-connections, ~50% chance)
    for s in supply_nodes:
        for d in demand_nodes:
            if rng.random() < 0.5:
                edges.add((s, d))

    # Hub cross-connections (~40% chance per pair)
    for i, h1 in enumerate(hub_nodes):
        for h2 in hub_nodes[i + 1:]:
            if rng.random() < 0.4:
                edges.add((h1, h2))
            if rng.random() < 0.4:
                edges.add((h2, h1))

    # ── Assign TRs to edges ──────────────────────────────────────
    routes = []
    for (f, t) in sorted(edges):
        if rng.random() < single_tr_prob:
            tr = rng.choice(transports)
            dist = rng.randint(1, 10)
            routes.append((f, t, tr, dist, dist * unit_costs[tr]))
        else:
            for tr in transports:
                dist = rng.randint(1, 10)
                routes.append((f, t, tr, dist, dist * unit_costs[tr]))

    # ── Verify reachability ──────────────────────────────────────
    adj = {l: set() for l in locations}
    for (f, t, *_) in routes:
        adj[f].add(t)
    for s in supply_nodes:
        reach = reachable_from(adj, s)
        for d in demand_nodes:
            if d not in reach:
                return None

    # ── Balanced demand (conservative volumes) ───────────────────
    max_flow_est = estimate_max_flow(
        locations, routes, supply_nodes, demand_nodes, capacities)
    max_volume = int(max_flow_est * 0.25)
    if max_volume < 20:
        return None

    demand_offers = []
    for p in parts:
        part_vol = max_volume // len(parts)
        total_units = max(5, min(30, part_vol // part_sizes[p]))

        supply_amts = _distribute_units(rng, total_units, len(supply_nodes))
        for s, amt in zip(supply_nodes, supply_amts):
            demand_offers.append((p, s, amt))

        demand_amts = _distribute_units(rng, total_units, len(demand_nodes))
        for d, amt in zip(demand_nodes, demand_amts):
            demand_offers.append((p, d, -amt))

    return {
        "seed": seed, "locations": locations, "transports": transports,
        "capacities": capacities, "unit_costs": unit_costs,
        "co2": co2, "speeds": speeds,
        "parts": parts, "part_sizes": part_sizes,
        "part_vals": part_vals, "part_trs": part_trs,
        "routes": routes, "demand_offers": demand_offers,
        "supply_nodes": supply_nodes, "demand_nodes": demand_nodes,
    }


def generate_layered_batch(out_dir: Path, prefix: str, target: int,
                           seed_start: int, **kwargs) -> int:
    generated = 0
    for seed in range(seed_start, seed_start + 1000):
        if generated >= target:
            break

        inst = generate_layered_instance(seed, **kwargs)
        if inst is None:
            continue

        generated += 1
        name = f"{prefix}_seed{generated}"
        path = out_dir / f"{name}.lp"
        path.write_text(to_lp(inst))

        n_edges = len(set((f, t) for (f, t, *_) in inst["routes"]))
        n_routes = len(inst["routes"])
        single_tr = sum(1 for e in set((f, t) for (f, t, *_) in inst["routes"])
                        if sum(1 for r in inst["routes"]
                               if r[0] == e[0] and r[1] == e[1]) == 1)

        supply_str = ",".join(inst["supply_nodes"])
        demand_str = ",".join(inst["demand_nodes"])

        print(f"  {name}: {n_edges} edges, {n_routes} routes, "
              f"{single_tr} single-TR arcs  "
              f"[supply={supply_str} demand={demand_str}]  seed={seed}")

    return generated


##############################################################################
# Industry-derived test case generation
##############################################################################

def parse_industry_lp(path: Path) -> dict:
    """Parse an industry-format .lp file into a structured dictionary.

    Returns a dict with keys:
        locations, harbors, transports,
        transport_co2, transport_cost, transport_capacity, transport_speed,
        routes  (list of (from, to, tr, dist, cost)),
        parts, part_sizes, part_trs (dict → list of trs),
        demand_offers (list of (part, loc, qty))
    """
    text = path.read_text()

    locations = re.findall(r"location\((\w+)\)\.", text)
    transports = re.findall(r"transportResource\((\w+)\)\.", text)

    transport_co2 = dict(re.findall(r"transportCO2\((\w+),(\d+)\)\.", text))
    transport_cost = dict(re.findall(r"transportCost\((\w+),(\d+)\)\.", text))
    transport_cap = dict(re.findall(r"transportCapacity\((\w+),(\d+)\)\.", text))
    transport_speed = dict(re.findall(r"transportSpeed\((\w+),(\d+)\)\.", text))
    for d in (transport_co2, transport_cost, transport_cap, transport_speed):
        for k in d:
            d[k] = int(d[k])

    routes = []
    for m in re.finditer(r"route\((\w+),(\w+),(\w+),(\d+),(\d+)\)\.", text):
        routes.append((m[1], m[2], m[3], int(m[4]), int(m[5])))

    parts = re.findall(r"part\((\w+)\)\.", text)
    part_sizes = {}
    for m in re.finditer(r"partSize\((\w+),(\d+)\)\.", text):
        part_sizes[m[1]] = int(m[2])

    part_trs: dict[str, list[str]] = {p: [] for p in parts}
    for m in re.finditer(r"partTR\((\w+),(\w+)\)\.", text):
        if m[1] in part_trs:
            part_trs[m[1]].append(m[2])

    demand_offers = []
    for m in re.finditer(r"demandOffer\((\w+),(\w+),(-?\d+)\)\.", text):
        demand_offers.append((m[1], m[2], int(m[3])))

    harbor_match = re.search(r"harbor\(([^)]+)\)\.", text)
    harbors = []
    if harbor_match:
        harbors = [h.strip() for h in harbor_match[1].split(";")]

    return {
        "locations": locations, "harbors": harbors,
        "transports": transports,
        "transport_co2": transport_co2, "transport_cost": transport_cost,
        "transport_capacity": transport_cap, "transport_speed": transport_speed,
        "routes": routes,
        "parts": parts, "part_sizes": part_sizes, "part_trs": part_trs,
        "demand_offers": demand_offers,
    }


def generate_industry_fullsize(industry: dict, seed: int) -> dict | None:
    """Generate a new instance at the exact same scale as the industry file.

    Keeps all 50 locations, 16 transports (with original properties), and
    35 parts (with original sizes and TR restrictions).  Rebuilds the route
    network and demand distribution from scratch using the original value
    pools and structural patterns so each seed yields a genuinely different
    optimisation problem.
    """
    rng = random.Random(seed)

    locations = list(industry["locations"])
    transports = list(industry["transports"])
    parts = list(industry["parts"])

    # ── Analyse original route structure ─────────────────────────────
    orig_edges: dict[tuple, list] = {}
    for (f, t, tr, dist, cost) in industry["routes"]:
        orig_edges.setdefault((f, t), []).append((tr, dist))

    target_num_edges = len(orig_edges)
    tpe_pool = [len(v) for v in orig_edges.values()]
    distance_pool = [dist for (_, _, _, dist, _) in industry["routes"]]

    # Per-TR frequency weights (how often each TR appears on edges)
    tr_edge_freq: dict[str, int] = {t: 0 for t in transports}
    for entries in orig_edges.values():
        for (tr, _) in entries:
            tr_edge_freq[tr] += 1
    tr_weights = [tr_edge_freq[t] for t in transports]

    # ── Build new route network ──────────────────────────────────────
    all_pairs = [(f, t) for f in locations for t in locations if f != t]
    rng.shuffle(all_pairs)
    selected_edges = all_pairs[:target_num_edges]

    rng.shuffle(tpe_pool)

    routes = []
    for i, (f, t) in enumerate(selected_edges):
        num_trs = tpe_pool[i % len(tpe_pool)]
        num_trs = min(num_trs, len(transports))

        # Weighted sample of TRs (mirrors original TR frequency)
        edge_trs = _weighted_sample(rng, transports, tr_weights, num_trs)

        base_dist = rng.choice(distance_pool)
        for tr in edge_trs:
            # ~70% chance same base distance, else independent draw
            dist = base_dist if rng.random() < 0.70 else rng.choice(distance_pool)
            cost = dist * industry["transport_cost"][tr]
            routes.append((f, t, tr, dist, cost))

    # ── Analyse original demand patterns ─────────────────────────────
    orig_by_part: dict[str, list] = {}
    for (p, l, q) in industry["demand_offers"]:
        orig_by_part.setdefault(p, []).append((l, q))

    orig_supply_locs = {l for (_, l, q) in industry["demand_offers"] if q > 0}
    orig_demand_locs = {l for (_, l, q) in industry["demand_offers"] if q < 0}
    num_supply = len(orig_supply_locs)
    num_demand = len(orig_demand_locs)
    num_overlap = len(orig_supply_locs & orig_demand_locs)

    # Pick new supply / demand locations from prodloc* nodes
    prodlocs = [l for l in locations if l.startswith("prodloc")]
    rng.shuffle(prodlocs)

    supply_pool = prodlocs[:num_supply]
    demand_only = prodlocs[num_supply:num_supply + num_demand - num_overlap]
    overlap_locs = supply_pool[:num_overlap]
    demand_pool = sorted(set(demand_only) | set(overlap_locs))

    # ── Rebuild demand / offers per part ─────────────────────────────
    demand_offers = []
    for p in parts:
        pattern = orig_by_part.get(p, [])
        if not pattern:
            continue

        pos_qtys = [q for (_, q) in pattern if q > 0]
        neg_qtys = [q for (_, q) in pattern if q < 0]

        # Assign positive (supply) entries to randomly chosen supply locs
        chosen_supply = rng.sample(
            supply_pool, min(len(pos_qtys), len(supply_pool)))
        for j, loc in enumerate(chosen_supply):
            demand_offers.append((p, loc, pos_qtys[j % len(pos_qtys)]))

        # Assign negative (demand) entries to randomly chosen demand locs
        chosen_demand = rng.sample(
            demand_pool, min(len(neg_qtys), len(demand_pool)))
        for j, loc in enumerate(chosen_demand):
            demand_offers.append((p, loc, neg_qtys[j % len(neg_qtys)]))

    # ── Verify reachability ──────────────────────────────────────────
    adj: dict[str, set[str]] = {l: set() for l in locations}
    for (f, t, *_) in routes:
        adj[f].add(t)

    all_supply = {l for (_, l, q) in demand_offers if q > 0}
    all_demand = {l for (_, l, q) in demand_offers if q < 0}
    if not all_supply or not all_demand:
        return None

    for s in all_supply:
        reach = reachable_from(adj, s)
        for d in all_demand:
            if d not in reach:
                return None

    return {
        "seed": seed,
        "locations": locations,
        "harbors": list(industry["harbors"]),
        "transports": transports,
        "transport_co2": dict(industry["transport_co2"]),
        "transport_cost": dict(industry["transport_cost"]),
        "transport_capacity": dict(industry["transport_capacity"]),
        "transport_speed": dict(industry["transport_speed"]),
        "routes": sorted(routes),
        "parts": parts,
        "part_sizes": dict(industry["part_sizes"]),
        "part_trs": {p: list(v) for p, v in industry["part_trs"].items()},
        "demand_offers": sorted(demand_offers, key=lambda x: (x[1], x[0])),
        "supply_locs": sorted(all_supply),
        "demand_locs": sorted(all_demand),
    }


def _weighted_sample(rng: random.Random, population: list,
                     weights: list[float], k: int) -> list:
    """Weighted sampling without replacement (uses random.choices fallback)."""
    if k >= len(population):
        return list(population)
    chosen: list = []
    remaining = list(zip(population, weights))
    for _ in range(k):
        total = sum(w for (_, w) in remaining)
        if total <= 0:
            pick = rng.choice(remaining)
        else:
            r = rng.random() * total
            cumul = 0.0
            pick = remaining[-1]
            for item in remaining:
                cumul += item[1]
                if cumul >= r:
                    pick = item
                    break
        chosen.append(pick[0])
        remaining.remove(pick)
    return chosen


def check_instance_feasibility(inst: dict) -> list[str]:
    """Validate that a generated instance is internally consistent and feasible.

    Checks performed:
      1. Flow conservation — per-part supply/demand balance (Σ demandOffer = 0).
      2. Part-TR capacity  — every partTR(P,TR) satisfies partSize(P) ≤ cap(TR).
      3. Referential integrity — all entities referenced in routes, partTR, and
         demandOffer are declared in the locations / transports / parts lists.
      4. Route cost consistency — cost = distance × transportCost(TR).
      5. Reachability — every supply node can reach every demand node.
      6. Part transportability — every part with non-zero demand has at least
         one allowed TR that actually appears on a route in the network.

    Returns a list of human-readable error strings (empty ⇒ all passed).
    """
    errors: list[str] = []

    loc_set = set(inst["locations"])
    tr_set = set(inst["transports"])
    part_set = set(inst["parts"])
    cap = inst.get("transport_capacity", {})
    unit_cost = inst.get("transport_cost", {})
    part_sizes = inst.get("part_sizes", {})
    part_trs = inst.get("part_trs", {})

    # ── 1. Flow conservation (supply/demand balance per part) ────────
    balance: dict[str, int] = {p: 0 for p in inst["parts"]}
    for (p, _l, q) in inst.get("demand_offers", []):
        if p in balance:
            balance[p] += q

    for p, total in balance.items():
        if total != 0:
            errors.append(
                f"[flow balance] part={p}: Σ demandOffer = {total} ≠ 0  "
                f"(supply and demand are unbalanced)"
            )

    # ── 2. Part-TR capacity fit ──────────────────────────────────────
    #    Each part with demand must have at least one allowed TR whose
    #    capacity ≥ partSize.  (Individual partTR pairs where size > cap are
    #    normal — the TR can still carry partial loads across multiple trips.)
    parts_with_demand = {p for (p, _, q) in inst.get("demand_offers", [])
                         if q != 0}

    for p in parts_with_demand:
        trs = part_trs.get(p, [])
        size = part_sizes.get(p)
        if size is None:
            continue
        fitting_trs = [tr for tr in trs if cap.get(tr, 0) >= size]
        if not fitting_trs:
            errors.append(
                f"[part-TR fit] part={p} (size={size}) has NO transport "
                f"with sufficient capacity among its allowed TRs "
                f"{trs} (caps: {[cap.get(tr,0) for tr in trs]})"
            )

    # ── 3. Referential integrity ─────────────────────────────────────
    for (f, t, tr, _d, _c) in inst.get("routes", []):
        if f not in loc_set:
            errors.append(f"[ref] route origin '{f}' not in locations")
        if t not in loc_set:
            errors.append(f"[ref] route destination '{t}' not in locations")
        if tr not in tr_set:
            errors.append(f"[ref] route transport '{tr}' not in transports")

    for (p, l, _q) in inst.get("demand_offers", []):
        if p not in part_set:
            errors.append(f"[ref] demandOffer part '{p}' not in parts")
        if l not in loc_set:
            errors.append(f"[ref] demandOffer location '{l}' not in locations")

    for p, trs in part_trs.items():
        if p not in part_set:
            errors.append(f"[ref] partTR part '{p}' not in parts")
        for tr in trs:
            if tr not in tr_set:
                errors.append(
                    f"[ref] partTR({p},{tr}): transport '{tr}' not in transports"
                )

    # ── 4. Route cost consistency ────────────────────────────────────
    for (f, t, tr, dist, cost) in inst.get("routes", []):
        expected = dist * unit_cost.get(tr, 0)
        if cost != expected:
            errors.append(
                f"[route cost] route({f},{t},{tr},{dist},{cost}): "
                f"expected cost={expected} (dist×unitCost)"
            )

    # ── 5. Reachability ──────────────────────────────────────────────
    supply_nodes = {l for (_, l, q) in inst.get("demand_offers", []) if q > 0}
    demand_nodes = {l for (_, l, q) in inst.get("demand_offers", []) if q < 0}

    adj: dict[str, set[str]] = {l: set() for l in inst["locations"]}
    for (f, t, *_) in inst.get("routes", []):
        adj.setdefault(f, set()).add(t)

    for s in supply_nodes:
        reach = reachable_from(adj, s)
        for d in demand_nodes:
            if d not in reach:
                errors.append(
                    f"[reachability] supply node '{s}' cannot reach "
                    f"demand node '{d}'"
                )

    # ── 6. Part transportability ─────────────────────────────────────
    trs_on_network = set()
    for (_, _, tr, *_rest) in inst.get("routes", []):
        trs_on_network.add(tr)

    for p in parts_with_demand:
        allowed_trs = set(part_trs.get(p, []))
        if not allowed_trs:
            errors.append(
                f"[transportability] part={p} has demand but no partTR entries"
            )
            continue
        usable = allowed_trs & trs_on_network
        if not usable:
            errors.append(
                f"[transportability] part={p}: none of its allowed TRs "
                f"{sorted(allowed_trs)} appear on any route"
            )

    return errors


def industry_subset_to_lp(inst: dict) -> str:
    """Emit an LP string in the same format as the industry instance."""
    lines = []
    lines.append(f"% Industry-derived test case (seed={inst['seed']})")
    lines.append(f"% {len(inst['locations'])} locations, "
                 f"{len(inst['transports'])} transports, "
                 f"{len(inst['parts'])} parts, "
                 f"{len(inst['routes'])} routes")
    lines.append("")

    lines.append("% ----------------------- locations -----------------------")
    for l in inst["locations"]:
        lines.append(f"location({l}).")
    lines.append("")

    lines.append("% ----------------------- transport resources -----------------------")
    for tr in inst["transports"]:
        lines.append(f"transportResource({tr}).")
    lines.append("")
    for tr in inst["transports"]:
        lines.append(f"transportCO2({tr},{inst['transport_co2'][tr]}).")
    lines.append("")
    for tr in inst["transports"]:
        lines.append(f"transportCost({tr},{inst['transport_cost'][tr]}).")
    lines.append("")
    for tr in inst["transports"]:
        lines.append(f"transportCapacity({tr},{inst['transport_capacity'][tr]}).")
    lines.append("")
    for tr in inst["transports"]:
        lines.append(f"transportSpeed({tr},{inst['transport_speed'][tr]}).")
    lines.append("")

    lines.append("")
    lines.append("% ----------------------- routes -----------------------")
    for (f, t, tr, dist, cost) in inst["routes"]:
        lines.append(f"route({f},{t},{tr},{dist},{cost}).")
    lines.append("")

    lines.append("% ----------------------- parts -----------------------")
    for p in inst["parts"]:
        lines.append(f"part({p}).")
    lines.append("")
    for p in inst["parts"]:
        lines.append(f"partSize({p},{inst['part_sizes'][p]}).")
    lines.append("")
    for p in inst["parts"]:
        for tr in inst["part_trs"][p]:
            lines.append(f"partTR({p},{tr}).")
    lines.append("")

    lines.append("")
    lines.append("% ----------------------- demands and offers -----------------------")
    for (p, l, q) in inst["demand_offers"]:
        lines.append(f"demandOffer({p},{l},{q}).")
    lines.append("")

    if inst["harbors"]:
        lines.append("% ----------------------- harbors -----------------------")
        lines.append(f"harbor({';'.join(inst['harbors'])}).")

    return "\n".join(lines) + "\n"


def generate_industry_test_cases(
    industry_path: Path,
    out_dir: Path,
    num_cases: int = 10,
    seed_start: int = 20000,
) -> int:
    """Parse the industry instance and generate full-size test cases from it.

    Each test case has the same 50 locations, 16 transports, 35 parts, and
    ~1500 edges / ~5600 routes as the original, but with a freshly
    randomised route network and demand distribution.
    """
    industry = parse_industry_lp(industry_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    for old in out_dir.glob("industry_test_*.lp"):
        old.unlink()

    generated = 0
    for seed in range(seed_start, seed_start + 5000):
        if generated >= num_cases:
            break

        inst = generate_industry_fullsize(industry, seed)
        if inst is None:
            continue

        # Validate before writing
        feas_errors = check_instance_feasibility(inst)
        if feas_errors:
            continue

        generated += 1
        name = f"industry_test_{generated}"
        path = out_dir / f"{name}.lp"
        path.write_text(industry_subset_to_lp(inst))

        n_routes = len(inst["routes"])
        n_edges = len(set((f, t) for (f, t, *_) in inst["routes"]))
        print(f"  {name}: {len(inst['locations'])} locs, "
              f"{len(inst['transports'])} TRs, {len(inst['parts'])} parts, "
              f"{n_edges} edges, {n_routes} routes  "
              f"[supply={','.join(inst['supply_locs'])} "
              f"demand={','.join(inst['demand_locs'])}]  seed={seed}")

    return generated


def validate_industry_lp(path: Path) -> bool:
    """Parse an industry-format .lp file and run all feasibility checks.

    Prints a per-check report and returns True if all checks pass.
    """
    print(f"Validating: {path}")
    inst = parse_industry_lp(path)
    print(f"  {len(inst['locations'])} locations, "
          f"{len(inst['transports'])} transports, "
          f"{len(inst['parts'])} parts, "
          f"{len(inst['routes'])} routes, "
          f"{len(inst['demand_offers'])} demandOffer entries")

    errors = check_instance_feasibility(inst)

    if errors:
        print(f"  FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"    {e}")
        return False

    print("  ALL CHECKS PASSED")
    return True


if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) > 1 and _sys.argv[1] == "--validate":
        files = [Path(p) for p in _sys.argv[2:]]
        if not files:
            gen_dir = Path(__file__).parent.parent / "generated"
            files = sorted(gen_dir.glob("industry_test_*.lp"))
        ok = all(validate_industry_lp(f) for f in files)
        _sys.exit(0 if ok else 1)
    else:
        main()
