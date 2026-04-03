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
        # Target volume for this part (in capacity units)
        part_vol_target = max_volume // len(parts)
        # Convert to units: units = volume / part_size
        total_units = max(5, part_vol_target // part_sizes[p])
        total_units = min(total_units, 30)  # cap to keep manageable
        total_volume += total_units * part_sizes[p]

        # Distribute supply across supply nodes
        rem = total_units
        for i, s in enumerate(supply_nodes):
            if i == len(supply_nodes) - 1:
                amt = rem
            else:
                amt = rng.randint(max(1, rem // 3), max(1, 2 * rem // 3))
                rem -= amt
            demand_offers.append((p, s, amt))

        # Distribute demand across demand nodes
        rem = total_units
        for i, d in enumerate(demand_nodes):
            if i == len(demand_nodes) - 1:
                amt = rem
            else:
                amt = rng.randint(max(1, rem // 3), max(1, 2 * rem // 3))
                rem -= amt
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

    # Remove old sparse instances
    for old in out_dir.glob("sparse_*_seed*.lp"):
        old.unlink()
    # Also clean legacy names
    for old in out_dir.glob("sparse_seed*.lp"):
        old.unlink()

    # ── Small sparse: 6 locations, 3 parts, 2 TRs ───────────────────
    print("Small sparse (6 loc, 3 parts, 2 TRs):")
    n = generate_batch(
        out_dir, prefix="sparse_small", target=5, seed_start=5000,
        num_locations=6, num_parts=3, num_transports=2,
        edge_density=0.50, single_tr_prob=0.25,
        num_supply=2, num_demand=2,
    )
    print(f"  → {n} instances\n")

    # ── Medium sparse: 8 locations, 5 parts, 2 TRs ──────────────────
    print("Medium sparse (8 loc, 5 parts, 2 TRs):")
    n = generate_batch(
        out_dir, prefix="sparse_medium", target=5, seed_start=6000,
        num_locations=8, num_parts=5, num_transports=2,
        edge_density=0.40, single_tr_prob=0.25,
        num_supply=2, num_demand=3,
    )
    print(f"  → {n} instances\n")

    # ── Medium 60% density: 8 locations, 5 parts, 2 TRs ────────────
    print("Medium 60% (8 loc, 5 parts, 2 TRs, 60% density):")
    n = generate_batch(
        out_dir, prefix="sparse_medium60", target=5, seed_start=8000,
        num_locations=8, num_parts=5, num_transports=2,
        edge_density=0.60, single_tr_prob=0.20,
        num_supply=2, num_demand=3,
    )
    print(f"  → {n} instances\n")

    # ── Small 60% density: 6 locations, 3 parts, 2 TRs ──────────
    print("Small 60% (6 loc, 3 parts, 2 TRs, 60% density):")
    n = generate_batch(
        out_dir, prefix="sparse_small60", target=5, seed_start=9000,
        num_locations=6, num_parts=3, num_transports=2,
        edge_density=0.60, single_tr_prob=0.20,
        num_supply=2, num_demand=2,
    )
    print(f"  → {n} instances\n")

    # ── Semi-sparse: 10 locations, 5 parts, 2 TRs, ~65% density ────
    # Sits between sparse (50%) and complete (100%).
    # Enough paths for rerouting so R_1 < 1.0 but not saturated,
    # enough bottlenecks (single-TR arcs, missing edges) for R_TR < 1.0.
    print("Semi-sparse (10 loc, 5 parts, 2 TRs, 65% density):")
    n = generate_batch(
        out_dir, prefix="semisparse", target=5, seed_start=7000,
        num_locations=10, num_parts=5, num_transports=2,
        edge_density=0.65, single_tr_prob=0.15,
        num_supply=2, num_demand=3,
    )
    print(f"  → {n} instances\n")

    # ── Layered instances (paper-style) ─────────────────────────────
    # Layered topology: supply → hubs → demand, like the paper instance.
    # Most arcs have 2 TRs, a few have 1. All parts can use all TRs.
    # R_TR can improve with weight because alternative paths exist.

    for old in out_dir.glob("layered_*_seed*.lp"):
        old.unlink()

    print("Layered small (6 loc = 2+2+2, 2 parts, 2 TRs):")
    n = generate_layered_batch(
        out_dir, prefix="layered_small", target=3, seed_start=10000,
        layers=(2, 2, 2), num_parts=2, num_transports=2,
    )
    print(f"  → {n} instances\n")

    print("Layered medium (8 loc = 2+3+3, 3 parts, 2 TRs):")
    n = generate_layered_batch(
        out_dir, prefix="layered_medium", target=3, seed_start=11000,
        layers=(2, 3, 3), num_parts=3, num_transports=2,
    )
    print(f"  → {n} instances\n")

    print("Layered large (10 loc = 2+4+4, 4 parts, 2 TRs):")
    n = generate_layered_batch(
        out_dir, prefix="layered_large", target=3, seed_start=12000,
        layers=(2, 4, 4), num_parts=4, num_transports=2,
    )
    print(f"  → {n} instances\n")

    print(f"All instances written to {out_dir}")


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

        rem = total_units
        for i, s in enumerate(supply_nodes):
            if i == len(supply_nodes) - 1:
                amt = rem
            else:
                amt = rng.randint(max(1, rem // 3), max(1, 2 * rem // 3))
                rem -= amt
            demand_offers.append((p, s, amt))

        rem = total_units
        for i, d in enumerate(demand_nodes):
            if i == len(demand_nodes) - 1:
                amt = rem
            else:
                amt = rng.randint(max(1, rem // 3), max(1, 2 * rem // 3))
                rem -= amt
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


if __name__ == "__main__":
    main()
