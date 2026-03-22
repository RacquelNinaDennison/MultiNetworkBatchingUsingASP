"""
Nonmonotonic Benchmark Instance Generator (v2)
===============================================
Generates multibatching benchmark instances by recycling industry-calibrated
data from a real instance file and varying the network topology.

Python's role:
  - Parse the real instance to build a data pool (parts, transport resources,
    supply/demand patterns)
  - Generate new location names (harbors + prodlocs)
  - Assign supply/demand patterns to new locations
  - Emit route_attr candidates with seeded distances and costs
  - Emit all fixed facts (transportCapacity, partSize, valid_transport, demandOffer)
    directly to the output — no grounding over integer domains

Clingo's role (--seed controls combinatorial choices):
  - Hub designation
  - Route topology (which candidate arcs become active)
  - Disruptions (nonmonotonic: removing an arc can invalidate reachability)
  - Feasibility constraints

Usage:
  python generate.py --seed 42 --harbors 5 --prodlocs 15 --hubs 3 \\
                     --parts 10 --min-trs 2 --disruptions 2 \\
                     --output instances/instance_42.lp
"""

import argparse
import re
import random
import sys
from collections import defaultdict
from pathlib import Path

import clingo


GENERATOR_LP = Path(__file__).parent / "generator.lp"
DEFAULT_INSTANCES = Path(__file__).parent / "instances.lp"


def parse_instances(path: Path) -> dict:
    """
    Parse a real instance file to build a recyclable data pool.

    Returns a dict with:
      tr_profiles:     {tr_id: {capacity, co2, cost_rate, speed}}
      parts:           {part_id: {size, valid_trs: [tr_id, ...]}}
      demand_patterns: {part_id: [signed_amount, ...]}  (sums to 0 per part)
      hh_trs:          set of TR IDs seen on harbor-harbor arcs
      non_hh_trs:      set of TR IDs seen on non-harbor-harbor arcs
      hh_dists:        list of distances from harbor-harbor routes
      non_hh_dists:    list of distances from non-harbor-harbor routes
    """
    text = path.read_text()

    harbor_set = set()
    for m in re.finditer(r'\bharbor\(([^).]+)\)', text):
        for loc in re.split(r'[;,]', m.group(1)):
            loc = loc.strip()
            if loc:
                harbor_set.add(loc)
    for m in re.finditer(r'\blocation\((\w+)\)', text):
        loc = m.group(1)
        if loc.startswith('harbor'):
            harbor_set.add(loc)

    tr_profiles: dict[str, dict] = {}
    for pred, key in [
        ('transportCapacity', 'capacity'),
        ('transportCO2',      'co2'),
        ('transportCost',     'cost_rate'),
        ('transportSpeed',    'speed'),
    ]:
        for m in re.finditer(rf'\b{pred}\((\w+),(\d+)\)', text):
            tr_id, val = m.group(1), int(m.group(2))
            tr_profiles.setdefault(tr_id, {})[key] = val

    parts: dict[str, dict] = {}
    for m in re.finditer(r'\bpartSize\((\w+),(\d+)\)', text):
        part_id, size = m.group(1), int(m.group(2))
        parts.setdefault(part_id, {'size': size, 'valid_trs': []})['size'] = size
    for m in re.finditer(r'\bpartVal\((\w+),(\d+)\)', text):
        part_id, val = m.group(1), int(m.group(2))
        if part_id in parts:
            parts[part_id]['value'] = val
    for m in re.finditer(r'\bpartTR\((\w+),(\w+)\)', text):
        part_id, tr_id = m.group(1), m.group(2)
        entry = parts.setdefault(part_id, {'size': 1, 'valid_trs': []})
        if tr_id not in entry['valid_trs']:
            entry['valid_trs'].append(tr_id)

    demand_patterns: dict[str, list[int]] = defaultdict(list)
    for m in re.finditer(r'\bdemandOffer\((\w+),\w+,(-?\d+)\)', text):
        demand_patterns[m.group(1)].append(int(m.group(2)))

    hh_trs: set[str] = set()
    non_hh_trs: set[str] = set()
    hh_dists: list[int] = []
    non_hh_dists: list[int] = []

    for m in re.finditer(r'\broute\((\w+),(\w+),(\w+),(\d+),\d+\)', text):
        l1, l2, tr_id, dist = m.group(1), m.group(2), m.group(3), int(m.group(4))
        if l1 in harbor_set and l2 in harbor_set:
            hh_trs.add(tr_id)
            hh_dists.append(dist)
        else:
            non_hh_trs.add(tr_id)
            non_hh_dists.append(dist)

    return {
        'tr_profiles':     tr_profiles,
        'parts':           parts,
        'demand_patterns': dict(demand_patterns),
        'hh_trs':          hh_trs or {'tr11', 'tr13'},
        'non_hh_trs':      non_hh_trs or {'tr2', 'tr4', 'tr12', 'tr14'},
        'hh_dists':        hh_dists or [1000, 5000, 10000, 20000],
        'non_hh_dists':    non_hh_dists or [100, 500, 1000, 3000],
    }



def generate_locations(num_harbors: int, num_prodlocs: int) -> tuple[list[str], list[str]]:
    harbor_names  = [f"harbor{i}"  for i in range(num_harbors)]
    prodloc_names = [f"prodloc{i}" for i in range(num_prodlocs)]
    return harbor_names, prodloc_names



def assign_demand(
    demand_patterns: dict[str, list[int]],
    prodloc_names: list[str],
    rng: random.Random,
) -> list[str]:
    """
    Assign each part's abstract supply/demand amounts to new prodloc names.
    Supply and demand slots are assigned to distinct locations where possible.
    Returns a list of demandOffer fact strings.
    """
    facts = []
    for part_id in sorted(demand_patterns):
        amounts = demand_patterns[part_id]
        supply = [v for v in amounts if v > 0]
        demand = [v for v in amounts if v < 0]

        # Skip parts with no supply or no demand (nothing to route)
        if not supply or not demand:
            continue

        n_total = len(supply) + len(demand)

        # Sample distinct locations if possible, fall back to replacement
        if len(prodloc_names) >= n_total:
            locs = rng.sample(prodloc_names, n_total)
        else:
            locs = rng.choices(prodloc_names, k=n_total)

        supply_locs = locs[:len(supply)]
        demand_locs = locs[len(supply):]

        # Aggregate amounts per location to avoid duplicate ground atoms in ASP
        # (ASP set semantics collapse identical facts, breaking supply/demand balance)
        loc_totals: dict[str, int] = defaultdict(int)
        for loc, amt in zip(supply_locs, supply):
            loc_totals[loc] += amt
        for loc, amt in zip(demand_locs, demand):
            loc_totals[loc] += amt

        for loc, total in sorted(loc_totals.items()):
            if total != 0:
                facts.append(f"demandOffer({part_id},{loc},{total}).")

    return facts



def assign_part_values(pool: dict, rng: random.Random) -> None:
    """
    Assign monetary values to parts that lack a 'value' key in the pool.

    Uses an inverse-size heuristic reflecting real logistics:
      - Small parts (size 1-5): high value (2000-8000) — sensors, electronics
      - Medium parts (size 6-50): medium value (500-3000) — housings, assemblies
      - Large parts (size 50+): lower value (100-1000) — frames, panels

    Values are jittered by the seeded RNG for variation across instances.
    """
    for part_id, p in pool['parts'].items():
        if 'value' in p:
            continue
        size = p['size']
        if size <= 5:
            base, spread = 5000, 3000
        elif size <= 50:
            base, spread = 1750, 1250
        else:
            base, spread = 550, 450
        p['value'] = max(50, base + rng.randint(-spread, spread))


def generate_route_attrs(
    harbor_names: list[str],
    prodloc_names: list[str],
    pool: dict,
    rng: random.Random,
    min_trs: int = 1,
) -> list[str]:
    """
    Generate route_attr candidates for all directed location pairs.

    Harbor-to-harbor pairs use the TR types observed on H-H arcs in the
    real instance (typically maritime/rail backbone TRs).
    All other pairs use the TR types observed on non-H-H arcs (land/mixed).

    Distance is sampled from the real data range for each arc type.
    Cost is derived as dist * cost_rate (matching the real data structure).
    """
    facts = []
    harbor_set = set(harbor_names)
    all_locs = harbor_names + prodloc_names
    tr_profiles = pool['tr_profiles']

    hh_trs    = sorted(pool['hh_trs'])
    non_hh_trs = sorted(pool['non_hh_trs'])

    hh_dists     = pool['hh_dists']
    non_hh_dists = pool['non_hh_dists']
    hh_range     = (min(hh_dists), max(hh_dists))
    non_hh_range = (min(non_hh_dists), max(non_hh_dists))

    for l1 in all_locs:
        for l2 in all_locs:
            if l1 == l2:
                continue
            is_hh = (l1 in harbor_set and l2 in harbor_set)
            trs       = hh_trs    if is_hh else non_hh_trs
            dist_range = hh_range if is_hh else non_hh_range

            # Ensure at least min_trs transport resources per route
            if len(trs) < min_trs:
                # Pad with additional TRs from the full pool
                all_trs = sorted(pool['tr_profiles'].keys())
                extra = [t for t in all_trs if t not in trs]
                rng.shuffle(extra)
                trs = list(trs) + extra[:min_trs - len(trs)]

            # One distance per arc (geography), cost varies by TR
            dist = rng.randint(*dist_range)
            for tr in trs:
                cost_rate = tr_profiles.get(tr, {}).get('cost_rate', 1)
                facts.append(f"route_attr({l1},{l2},{tr},{dist},{dist * cost_rate}).")

    return facts



def build_clingo_facts(
    args: argparse.Namespace,
    pool: dict,
    harbor_names: list[str],
    prodloc_names: list[str],
    demand_facts: list[str],
    route_attr_facts: list[str],
) -> list[str]:
    """
    Facts passed to clingo for structural decisions.
    Includes location domain, parameters, route candidates,
    and the demand/transport facts needed for feasibility constraints.
    """
    facts = []

    # Location domain
    for loc in harbor_names + prodloc_names:
        facts.append(f"location({loc}).")

    # Parameters
    facts.append(f"num_hubs({args.hubs}).")
    facts.append(f"num_disruptions({args.disruptions}).")

    # Demand and valid_transport (consumed by feasibility constraints in ASP)
    facts.extend(demand_facts)
    for part_id, p in sorted(pool['parts'].items()):
        for tr in p['valid_trs']:
            facts.append(f"valid_transport({part_id},{tr}).")

    # Route candidates
    facts.extend(route_attr_facts)

    return facts


def build_fixed_facts(pool: dict, demand_facts: list[str]) -> list[str]:
    """
    Fixed facts written directly to the output file (no clingo processing).
    These are the recycled industry values that do not change across instances.
    """
    lines = []

    lines.append("% ---- transport resources ----")
    for tr_id, p in sorted(pool['tr_profiles'].items()):
        lines.append(f"transportCapacity({tr_id},{p['capacity']}).")
        if 'co2' in p:
            lines.append(f"transportCO2({tr_id},{p['co2']}).")
        if 'cost_rate' in p:
            lines.append(f"transportCost({tr_id},{p['cost_rate']}).")
        if 'speed' in p:
            lines.append(f"transportSpeed({tr_id},{p['speed']}).")

    lines.append("")
    lines.append("% ---- parts ----")
    for part_id, p in sorted(pool['parts'].items()):
        lines.append(f"part({part_id}).")
        lines.append(f"partSize({part_id},{p['size']}).")
        lines.append(f"partVal({part_id},{p['value']}).")
        for tr in p['valid_trs']:
            lines.append(f"valid_transport({part_id},{tr}).")

    lines.append("")
    lines.append("% ---- demand ----")
    lines.extend(demand_facts)

    return lines



def run_generator(facts: list[str], seed: int, n_solutions: int = 1, min_transport_resources: int = 1) -> list[str] | None:
    """Use the clingo API to solve generator.lp with the given facts.

    Returns the symbols of the last answer set as a list of strings, or None
    if the problem is UNSATISFIABLE.
    """
    ctl = clingo.Control([str(n_solutions), f"--seed={seed}", f"-c min_transport_resources={min_transport_resources}"])
    ctl.load(str(GENERATOR_LP))
    ctl.add("base", [], "\n".join(facts))
    ctl.ground([("base", [])])

    last_model: list[str] | None = None
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            last_model = [str(sym) for sym in model.symbols(shown=True)]
        solve_result = handle.get()

    if solve_result.unsatisfiable:
        print("UNSATISFIABLE: No valid topology for these parameters.", file=sys.stderr)
        print("Try: fewer disruptions, more locations, or more hubs.", file=sys.stderr)
        return None

    return last_model


def extract_answer_set(symbols: list[str]) -> str | None:
    """Format a list of symbol strings as newline-separated facts."""
    if not symbols:
        return None
    return '\n'.join(sym + '.' for sym in symbols)


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate multibatching benchmark instances by recycling "
            "industry data and varying the network topology."
        )
    )

    # Reproducibility
    parser.add_argument('--seed', type=int, required=True,
                        help="Random seed (controls Python RNG and clingo)")

    # Data source
    parser.add_argument('--instances-file', type=Path, default=DEFAULT_INSTANCES,
                        dest='instances_file',
                        help="Real instance file to recycle data from")

    # Network structure
    parser.add_argument('--harbors',  type=int, default=5,
                        help="Number of harbor (backbone) locations")
    parser.add_argument('--prodlocs', type=int, default=15,
                        help="Number of production locations")
    parser.add_argument('--hubs',     type=int, default=3,
                        help="Number of hub locations ASP designates (≤ total locations)")

    # Parts and transport resources
    parser.add_argument('--parts', type=int, default=None,
                        help="Number of parts to include (default: all from source data)")
    parser.add_argument('--min-trs', type=int, default=1, dest='min_trs',
                        help="Minimum number of transport resources per route (default: 1)")

    # Difficulty
    parser.add_argument('--disruptions', type=int, default=0,
                        help="Number of directed arcs to disrupt (nonmonotonic)")

    # Output
    parser.add_argument('--output',    type=str, default=None,
                        help="Write instance to this .lp file (default: stdout)")
    parser.add_argument('--solutions', type=int, default=1,
                        help="Number of distinct instances to generate")

    args = parser.parse_args()

    # Validate
    if not args.instances_file.exists():
        print(f"Error: instances file not found: {args.instances_file}", file=sys.stderr)
        sys.exit(1)
    if args.hubs > args.harbors + args.prodlocs:
        print("Error: --hubs cannot exceed total number of locations.", file=sys.stderr)
        sys.exit(1)
    if args.hubs < 1:
        print("Error: --hubs must be at least 1.", file=sys.stderr)
        sys.exit(1)

    if args.min_trs < 1:
        print("Error: --min-trs must be at least 1.", file=sys.stderr)
        sys.exit(1)

    # --- Parse real instance ---
    print(f"Parsing {args.instances_file.name}...", file=sys.stderr)
    pool = parse_instances(args.instances_file)
    print(
        f"  Pool: {len(pool['tr_profiles'])} TRs, "
        f"{len(pool['parts'])} parts, "
        f"{len(pool['demand_patterns'])} parts with demand patterns",
        file=sys.stderr,
    )

    # --- Subset parts if --parts is specified ---
    if args.parts is not None:
        all_part_ids = sorted(pool['parts'].keys())
        if args.parts > len(all_part_ids):
            print(
                f"Error: --parts {args.parts} exceeds available parts ({len(all_part_ids)}).",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.parts < 1:
            print("Error: --parts must be at least 1.", file=sys.stderr)
            sys.exit(1)
        rng_parts = random.Random(args.seed)
        selected = set(rng_parts.sample(all_part_ids, args.parts))
        pool['parts'] = {k: v for k, v in pool['parts'].items() if k in selected}
        pool['demand_patterns'] = {
            k: v for k, v in pool['demand_patterns'].items() if k in selected
        }
        print(f"  Subsetted to {args.parts} parts.", file=sys.stderr)

    # Seeded RNG (Python owns: demand assignment and route distances)
    rng = random.Random(args.seed)

    # --- Generate new location set ---
    harbor_names, prodloc_names = generate_locations(args.harbors, args.prodlocs)

    # --- Assign demand patterns to new locations ---
    demand_facts = assign_demand(pool['demand_patterns'], prodloc_names, rng)

    # --- Assign part values (if not already in source data) ---
    assign_part_values(pool, rng)

    # --- Generate route candidates ---
    route_attr_facts = generate_route_attrs(harbor_names, prodloc_names, pool, rng, min_trs=args.min_trs)

    # --- Build clingo input ---
    clingo_facts = build_clingo_facts(
        args, pool, harbor_names, prodloc_names, demand_facts, route_attr_facts
    )

    # --- Build fixed output section ---
    fixed_facts = build_fixed_facts(pool, demand_facts)

    # --- Run clingo for structural decisions ---
    print(f"Generating topology (seed={args.seed})...", file=sys.stderr)
    clingo_output = run_generator(clingo_facts, seed=args.seed, n_solutions=args.solutions, min_transport_resources=args.min_trs)
    if clingo_output is None:
        sys.exit(1)

    structural_facts = extract_answer_set(clingo_output)
    if structural_facts is None:
        print("Error: could not parse clingo output.", file=sys.stderr)
        print(clingo_output, file=sys.stderr)
        sys.exit(1)

    # --- Assemble output file ---
    header = (
        f"% Multibatching benchmark instance\n"
        f"% Source: {args.instances_file.name}\n"
        f"% seed={args.seed}  harbors={args.harbors}  prodlocs={args.prodlocs}"
        f"  hubs={args.hubs}  parts={args.parts or 'all'}  min_trs={args.min_trs}"
        f"  disruptions={args.disruptions}\n"
    )

    loc_facts = "\n% ---- locations ----\n"
    for loc in harbor_names + prodloc_names:
        loc_facts += f"location({loc}).\n"

    output = (
        header
        + loc_facts
        + "\n"
        + "\n".join(fixed_facts)
        + "\n\n% ---- network (ASP-generated) ----\n"
        + structural_facts
        + "\n"
    )

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output)
        print(f"Instance written to {out_path}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
