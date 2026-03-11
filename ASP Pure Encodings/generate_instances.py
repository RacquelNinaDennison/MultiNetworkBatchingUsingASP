#!/usr/bin/env python3
"""
generate_instances.py – Generate ASP instance files for benchmark experiments.

Creates five series of instances in data/series_[A-E]/ based on the
multibatching-ex-generator. Domain predicates (numFlow, numParts, numFreq)
are computed dynamically from each instance so the encodings see tight,
accurate domains rather than a fixed over-approximation.

Series overview
---------------
  A  Location scaling      L ∈ {4,6,8,10}, P=1, TR=2, bins=1
  B  Product scaling       L=6, P ∈ {1,2,3}, TR=2, bins=1
  C  Transport scaling     L=6, P=2, TR ∈ {1,2,3}, bins=1
  D  Bin scaling           L=6, P=2, TR=2  (bins varied at benchmark time)
  E  Capacity tightness    L=6, P=2, TR=2, bins=1; tight/medium/loose regimes

Usage
-----
    uv run generate_instances.py
"""

from __future__ import annotations

import sys
from collections import deque, defaultdict
from pathlib import Path

# ── generator path ────────────────────────────────────────────────────────────
REPO_ROOT     = Path(__file__).parent.parent
GENERATOR_DIR = REPO_ROOT / "multibatching-ex-generator"
sys.path.insert(0, str(GENERATOR_DIR))

from utils   import generate_multibatching_problem  # noqa: E402
from problem import MultibatchingProblem             # noqa: E402

# ── paths ─────────────────────────────────────────────────────────────────────
HERE     = Path(__file__).parent
DATA_DIR = HERE / "data"

SEEDS = [1, 2, 3]

# Capacity regimes for Series E
CAPACITY_PARAMS: dict[str, dict] = {
    "tight":  {"min_capacity": 10, "max_capacity": 10,
               "min_product_size": 4, "max_product_size": 4},
    "medium": {"min_capacity": 15, "max_capacity": 15,
               "min_product_size": 3, "max_product_size": 3},
    "loose":  {"min_capacity": 20, "max_capacity": 20,
               "min_product_size": 1, "max_product_size": 1},
}

# Default capacity used for series A–D
DEFAULT_CAP = CAPACITY_PARAMS["medium"]

# Common generation kwargs
GEN_DEFAULTS = dict(
    demand_sparsity = 0.6,
    max_demand_abs  = 10,
    min_dist        = 1,
    max_dist        = 10,
    min_tt_cost     = 10,
    max_tt_cost     = 100,
    min_tt_speed    = 1,
    max_tt_speed    = 5,
    min_tt_emissions = 10,
    max_tt_emissions = 100,
    max_links_per_pair = 1,   # one link per (loc_pair, TR) keeps routes clean
)


# ── feasibility check (no networkx dependency) ────────────────────────────────

def _is_feasible(problem: MultibatchingProblem) -> bool:
    """BFS reachability: every consumer of each product must be reachable
    from at least one producer via the transport network."""
    adj: dict[str, set[str]] = defaultdict(set)
    for link in problem.transport_links:
        adj[link.location_l1.id].add(link.location_l2.id)

    for prod in problem.products:
        producers = {
            loc.id for loc in problem.locations
            if loc.net_supply.get(prod, 0) > 0
        }
        consumers = {
            loc.id for loc in problem.locations
            if loc.net_supply.get(prod, 0) < 0
        }
        if not producers or not consumers:
            continue

        reachable: set[str] = set(producers)
        queue: deque[str] = deque(producers)
        while queue:
            node = queue.popleft()
            for nb in adj[node]:
                if nb not in reachable:
                    reachable.add(nb)
                    queue.append(nb)

        if not consumers.issubset(reachable):
            return False
    return True


# ── active product helpers ────────────────────────────────────────────────────

def _active_products(problem: MultibatchingProblem) -> list[tuple]:
    """Return [(product, total_supply), ...] for products with supply > 0."""
    result = []
    for prod in problem.products:
        total = sum(
            loc.net_supply.get(prod, 0)
            for loc in problem.locations
            if loc.net_supply.get(prod, 0) > 0
        )
        if total > 0:
            result.append((prod, total))
    return result


# ── ASP serialiser ────────────────────────────────────────────────────────────

def to_asp(
    problem: MultibatchingProblem,
    series: str,
    label: str,
    seed: int,
) -> str:
    """Convert a MultibatchingProblem to an ASP .lp instance string.

    Domain predicates are computed from the instance:
      numFlow(0..S)   where S = total supply of the most-supplied product
      numParts(0..M)  where M = max floor(capacity / part_size)
      numFreq(0..S)   same as numFlow (worst case: 1 unit per dispatch)

    Note: bins are NOT included here. The benchmark script injects
          bins(1..numBins) at solve time so both encodings see the same set.
    """
    active = _active_products(problem)
    if not active:
        raise ValueError("no active products (all have zero total supply)")

    max_supply = max(s for _, s in active)

    max_pack = 0
    for prod, _ in active:
        if prod.size > 0:
            for tt in problem.transport_types:
                max_pack = max(max_pack, tt.capacity // prod.size)
    if max_pack == 0:
        raise ValueError("max_pack is 0 — parts are too large for all transports")

    tr_name = lambda tt_id: f"tr{tt_id}"

    lines: list[str] = [
        f"% ── Series {series}: {label}  seed={seed} ──────────────────────────",
        f"% locations={len(problem.locations)}"
        f"  active_products={len(active)}"
        f"  transport_types={len(problem.transport_types)}"
        f"  routes={len(problem.transport_links)}",
        f"% max_supply={max_supply}  max_pack={max_pack}",
        "",
        "% Domain bounds (computed from this instance)",
        f"numFlow(0..{max_supply}).",
        f"numParts(0..{max_pack}).",
        f"numFreq(0..{max_supply}).",
        "",
        "% Parts",
    ]

    for prod, _ in active:
        lines.append(f"part({prod.name}).")
    lines.append("")
    for prod, _ in active:
        lines.append(f"partSize({prod.name},{prod.size}).")
    lines.append("")

    lines.append("% Locations")
    for loc in problem.locations:
        lines.append(f"location({loc.id}).")
    lines.append("")

    lines.append("% Transport resources")
    for tt in problem.transport_types:
        lines.append(f"transportCapacity({tr_name(tt.id)},{tt.capacity}).")
    lines.append("")

    lines.append("% Routes")
    for link in problem.transport_links:
        fr   = link.location_l1.id
        to   = link.location_l2.id
        tr   = tr_name(link.transport_type.id)
        dist = max(1, round(link.distance))
        cost = link.transport_type.cost
        lines.append(f"route({fr},{to},{tr},{dist},{cost}).")
    lines.append("")

    lines.append("% Demand / supply  (non-zero entries only)")
    active_prod_set = {p for p, _ in active}
    for loc in problem.locations:
        for prod in active_prod_set:
            d = loc.net_supply.get(prod, 0)
            if d != 0:
                lines.append(f"demandOffer({prod.name},{loc.id},{d}).")

    return "\n".join(lines) + "\n"


# ── instance generation with retry ────────────────────────────────────────────

def generate_and_save(
    *,
    series: str,
    label: str,
    seed: int,
    num_locations: int,
    num_products: int,
    num_transport_types: int,
    cap_params: dict,
    out_dir: Path,
    out_name: str,
    max_retries: int = 15,
) -> Path:
    """Generate one instance, retrying on infeasibility, and write to disk."""
    for attempt in range(max_retries):
        actual_seed = seed + attempt * 97   # deterministic offset per retry

        problem = generate_multibatching_problem(
            num_locations       = num_locations,
            num_products        = num_products,
            num_transport_types = num_transport_types,
            seed                = actual_seed,
            **cap_params,
            **GEN_DEFAULTS,
        )

        if not _is_feasible(problem):
            continue

        try:
            asp_text = to_asp(problem, series, label, actual_seed)
        except ValueError:
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / out_name
        path.write_text(asp_text, encoding="utf-8")

        suffix = f"  (seed offset +{attempt * 97})" if attempt else ""
        print(f"    {path.name}{suffix}")
        return path

    raise RuntimeError(
        f"Could not generate feasible instance after {max_retries} attempts "
        f"for {label} seed={seed}"
    )


# ── series generators ─────────────────────────────────────────────────────────

def gen_series_A() -> None:
    """Location scaling: L ∈ {4,6,8,10}, P=1, TR=2, bins=1."""
    print("\nSeries A — Location scaling  (P=1, TR=2, bins=1)")
    for L in [4, 6, 8, 10]:
        for seed in SEEDS:
            generate_and_save(
                series="A", label=f"L={L}, P=1, TR=2", seed=seed,
                num_locations=L, num_products=1, num_transport_types=2,
                cap_params=DEFAULT_CAP,
                out_dir=DATA_DIR / "series_A",
                out_name=f"L{L:02d}_P01_TR2_s{seed}.lp",
            )


def gen_series_B() -> None:
    """Product scaling: L=6, P ∈ {1,2,3}, TR=2, bins=1."""
    print("\nSeries B — Product scaling  (L=6, TR=2, bins=1)")
    for P in [1, 2, 3]:
        for seed in SEEDS:
            generate_and_save(
                series="B", label=f"L=6, P={P}, TR=2", seed=seed,
                num_locations=6, num_products=P, num_transport_types=2,
                cap_params=DEFAULT_CAP,
                out_dir=DATA_DIR / "series_B",
                out_name=f"L06_P{P:02d}_TR2_s{seed}.lp",
            )


def gen_series_C() -> None:
    """Transport type scaling: L=6, P=2, TR ∈ {1,2,3}, bins=1."""
    print("\nSeries C — Transport type scaling  (L=6, P=2, bins=1)")
    for TR in [1, 2, 3]:
        for seed in SEEDS:
            generate_and_save(
                series="C", label=f"L=6, P=2, TR={TR}", seed=seed,
                num_locations=6, num_products=2, num_transport_types=TR,
                cap_params=DEFAULT_CAP,
                out_dir=DATA_DIR / "series_C",
                out_name=f"L06_P02_TR{TR}_s{seed}.lp",
            )


def gen_series_D() -> None:
    """Bin scaling: L=6, P=2, TR=2.  Bins are varied at benchmark time."""
    print("\nSeries D — Bin scaling  (L=6, P=2, TR=2)  bins varied at solve time")
    for seed in SEEDS:
        generate_and_save(
            series="D", label="L=6, P=2, TR=2", seed=seed,
            num_locations=6, num_products=2, num_transport_types=2,
            cap_params=DEFAULT_CAP,
            out_dir=DATA_DIR / "series_D",
            out_name=f"L06_P02_TR2_s{seed}.lp",
        )


def gen_series_E() -> None:
    """Capacity tightness: L=6, P=2, TR=2; tight / medium / loose regimes."""
    print("\nSeries E — Capacity tightness  (L=6, P=2, TR=2, bins=1)")
    for regime in ["tight", "medium", "loose"]:
        for seed in SEEDS:
            generate_and_save(
                series="E", label=f"L=6, P=2, TR=2, cap={regime}", seed=seed,
                num_locations=6, num_products=2, num_transport_types=2,
                cap_params=CAPACITY_PARAMS[regime],
                out_dir=DATA_DIR / "series_E",
                out_name=f"{regime}_L06_P02_TR2_s{seed}.lp",
            )


def gen_series_F() -> None:
    """Location scaling (larger range): L ∈ {4,6,8,10,12,15}, P=2, TR=2.
    Designed for bins=2 three-encoding comparison."""
    print("\nSeries F — Location scaling  (P=2, TR=2, bins=2 at solve time)")
    for L in [4, 6, 8, 10, 12, 15]:
        for seed in SEEDS:
            generate_and_save(
                series="F", label=f"L={L}, P=2, TR=2", seed=seed,
                num_locations=L, num_products=2, num_transport_types=2,
                cap_params=DEFAULT_CAP,
                out_dir=DATA_DIR / "series_F",
                out_name=f"L{L:02d}_P02_TR2_s{seed}.lp",
            )


def gen_series_G() -> None:
    """Product scaling: L=8, P ∈ {1,2,3,4,5}, TR=2.
    Designed for bins=2 three-encoding comparison."""
    print("\nSeries G — Product scaling  (L=8, TR=2, bins=2 at solve time)")
    for P in [1, 2, 3, 4, 5]:
        for seed in SEEDS:
            generate_and_save(
                series="G", label=f"L=8, P={P}, TR=2", seed=seed,
                num_locations=8, num_products=P, num_transport_types=2,
                cap_params=DEFAULT_CAP,
                out_dir=DATA_DIR / "series_G",
                out_name=f"L08_P{P:02d}_TR2_s{seed}.lp",
            )


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("Generating benchmark instances …")
    gen_series_A()
    gen_series_B()
    gen_series_C()
    gen_series_D()
    gen_series_E()
    gen_series_F()
    gen_series_G()
    print(f"\nAll instances written to {DATA_DIR}/series_[A-G]/")


if __name__ == "__main__":
    main()
