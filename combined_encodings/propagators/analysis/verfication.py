"""
ASP Encoding Verifier and Benchmarking Suite for Multi commodity flow problem

This script:
1. Parses clingo output (answer sets) and the instance file
2. Verifies flow conservation, demand/supply satisfaction, capacity constraints
4. Provides benchmarking utilities for grounding/solving time analysis

Usage:
    # Verify a solution from clingo output:
    clingo instance.lp encoding.lp --outf=2 | python3 verify_and_bench.py --verify

    # Or pipe a saved answer set:
    python3 verify_and_bench.py --verify --solution solution.txt --instance instance.lp

    # Benchmark grounding and solving:
    python3 verify_and_bench.py --benchmark --instance instance.lp --encoding encoding.lp
"""

import argparse
import json
import re
import subprocess
import sys
import time
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class TransportResource:
    name: str
    capacity: int
    co2emissions: int
    cost: int
    speed: int  # note: in your instance this is multiplied by 10 (3 means 0.3)


@dataclass
class Part:
    name: str
    size: int
    value: int
    valid_tr: Set[str] = field(default_factory=set)


@dataclass
class Route:
    from_loc: str
    to_loc: str
    tr: str
    distance: int
    cost: int  # precomputed: tr.cost * distance


@dataclass
class Instance:
    locations: Set[str] = field(default_factory=set)
    transport_resources: Dict[str, TransportResource] = field(default_factory=dict)
    parts: Dict[str, Part] = field(default_factory=dict)
    demand_offer: Dict[Tuple[str, str], int] = field(default_factory=dict)  # (part, loc) -> rate
    routes: List[Route] = field(default_factory=list)

    def net_supply_demand(self, part: str, loc: str) -> int:
        return self.demand_offer.get((part, loc), 0)


@dataclass
class Solution:
    """Parsed answer set from clingo."""
    flows: Dict[Tuple[str, str, str], int] = field(default_factory=dict)  # (from, to, part) -> amount
    packs: Dict[Tuple[str, str, int], int] = field(default_factory=dict)  # (part, tr, id) -> quantity
    transport_links: Dict[Tuple[str, str, str, int], int] = field(default_factory=dict)  # (from, to, tr, id) -> freq
    objective: Optional[int] = None


# =============================================================================
# Parsing
# =============================================================================

def parse_instance(filepath: str) -> Instance:
    """Parse an ASP instance file into structured data."""
    inst = Instance()

    with open(filepath, 'r') as f:
        content = f.read()

    # Parse locations
    for m in re.finditer(r'location\((\w+)\)', content):
        inst.locations.add(m.group(1))

    # Parse transport resources (collect attributes)
    for m in re.finditer(r'transportResource\((\w+)\)', content):
        name = m.group(1)
        inst.transport_resources[name] = TransportResource(name=name, capacity=0, co2emissions=0, cost=0, speed=0)

    for m in re.finditer(r'transportCapacity\((\w+),(\d+)\)', content):
        inst.transport_resources[m.group(1)].capacity = int(m.group(2))
    for m in re.finditer(r'transportCO2\((\w+),(\d+)\)', content):
        inst.transport_resources[m.group(1)].co2emissions = int(m.group(2))
    for m in re.finditer(r'transportCost\((\w+),(\d+)\)', content):
        inst.transport_resources[m.group(1)].cost = int(m.group(2))
    for m in re.finditer(r'transportSpeed\((\w+),(\d+)\)', content):
        inst.transport_resources[m.group(1)].speed = int(m.group(2))

    # Parse parts
    for m in re.finditer(r'part\((\w+)\)', content):
        name = m.group(1)
        inst.parts[name] = Part(name=name, size=0, value=0)

    for m in re.finditer(r'partSize\((\w+),(\d+)\)', content):
        inst.parts[m.group(1)].size = int(m.group(2))
    for m in re.finditer(r'partVal\((\w+),(\d+)\)', content):
        inst.parts[m.group(1)].value = int(m.group(2))
    for m in re.finditer(r'partTR\((\w+),(\w+)\)', content):
        inst.parts[m.group(1)].valid_tr.add(m.group(2))

    # Parse demand/offer
    for m in re.finditer(r'demandOffer\((\w+),(\w+),(-?\d+)\)', content):
        inst.demand_offer[(m.group(1), m.group(2))] = int(m.group(3))

    # Parse routes
    for m in re.finditer(r'route\((\w+),(\w+),(\w+),(\d+),(\d+)\)', content):
        inst.routes.append(Route(
            from_loc=m.group(1), to_loc=m.group(2), tr=m.group(3),
            distance=int(m.group(4)), cost=int(m.group(5))
        ))

    return inst


def parse_clingo_json(json_str: str) -> List[Solution]:
    """Parse clingo JSON output (--outf=2) into Solution objects."""
    data = json.loads(json_str)
    solutions = []

    for witness in data.get('Call', [{}])[0].get('Witnesses', []):
        sol = Solution()
        for atom in witness.get('Value', []):
            # Parse flow(From,To,Part,N)
            m = re.match(r'flow\((\w+),(\w+),(\w+),(\d+)\)', atom)
            if m:
                sol.flows[(m.group(1), m.group(2), m.group(3))] = int(m.group(4))
                continue

            # Parse pack(N,P,TR,ID)
            m = re.match(r'pack\((\d+),(\w+),(\w+),(\d+)\)', atom)
            if m:
                sol.packs[(m.group(2), m.group(3), int(m.group(4)))] = int(m.group(1))
                continue

            # Parse transportLink(From,To,TR,Freq,ID)
            m = re.match(r'transportLink\((\w+),(\w+),(\w+),(\d+),(\d+)\)', atom)
            if m:
                sol.transport_links[(m.group(1), m.group(2), m.group(3), int(m.group(5)))] = int(m.group(4))
                continue

        # Get objective if available
        costs = witness.get('Costs', [])
        if costs:
            sol.objective = costs[0]

        solutions.append(sol)

    return solutions


def parse_clingo_text(text: str) -> Solution:
    """Parse clingo plain text output into a Solution object."""
    sol = Solution()

    # Find answer set atoms
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('%') or line.startswith('Answer') or line.startswith('SATISFIABLE') or line.startswith('OPTIMUM') or line.startswith('Optimization'):
            if line.startswith('Optimization:'):
                try:
                    sol.objective = int(line.split(':')[1].strip())
                except (ValueError, IndexError):
                    pass
            continue

        for atom in line.split():
            m = re.match(r'flow\((\w+),(\w+),(\w+),(\d+)\)', atom)
            if m:
                sol.flows[(m.group(1), m.group(2), m.group(3))] = int(m.group(4))
                continue

            m = re.match(r'pack\((\d+),(\w+),(\w+),(\d+)\)', atom)
            if m:
                sol.packs[(m.group(2), m.group(3), int(m.group(4)))] = int(m.group(1))
                continue

            m = re.match(r'transportLink\((\w+),(\w+),(\w+),(\d+),(\d+)\)', atom)
            if m:
                sol.transport_links[(m.group(1), m.group(2), m.group(3), int(m.group(5)))] = int(m.group(4))
                continue

    return sol


# =============================================================================
# Verification
# =============================================================================

class VerificationResult:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def log(self, msg: str):
        self.info.append(msg)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def report(self) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("VERIFICATION REPORT")
        lines.append("=" * 70)

        if self.info:
            lines.append("\n--- Info ---")
            for msg in self.info:
                lines.append(f"  [INFO] {msg}")

        if self.warnings:
            lines.append("\n--- Warnings ---")
            for msg in self.warnings:
                lines.append(f"  [WARN] {msg}")

        if self.errors:
            lines.append("\n--- Errors ---")
            for msg in self.errors:
                lines.append(f"  [ERROR] {msg}")

        lines.append("\n" + "=" * 70)
        if self.passed:
            lines.append(f"RESULT: PASSED ({len(self.warnings)} warnings)")
        else:
            lines.append(f"RESULT: FAILED ({len(self.errors)} errors, {len(self.warnings)} warnings)")
        lines.append("=" * 70)
        return '\n'.join(lines)


def verify_solution(inst: Instance, sol: Solution) -> VerificationResult:
    """Verify all constraints of the logistics problem against a solution."""
    vr = VerificationResult()

    # -------------------------------------------------------------------
    # 1. Flow conservation: for each location and part,
    #    sum of outgoing flow - sum of incoming flow == netSupplyDemand
    # -------------------------------------------------------------------
    vr.log("Checking flow conservation constraints...")

    for part_name in inst.parts:
        for loc in inst.locations:
            outgoing = 0
            incoming = 0
            for (f, t, p), amount in sol.flows.items():
                if p == part_name:
                    if f == loc:
                        outgoing += amount
                    if t == loc:
                        incoming += amount

            net = outgoing - incoming
            expected = inst.net_supply_demand(part_name, loc)

            if net != expected:
                vr.error(
                    f"Flow conservation violated at {loc} for {part_name}: "
                    f"outgoing={outgoing} - incoming={incoming} = {net}, expected={expected}"
                )
            else:
                vr.log(f"  {loc}/{part_name}: out={outgoing} in={incoming} net={net} expected={expected} ✓")

    # -------------------------------------------------------------------
    # 2. Capacity constraints: for each packing, total size <= capacity
    # -------------------------------------------------------------------
    vr.log("\nChecking packing capacity constraints...")

    # Group packs by (tr, id)
    packings_by_tr_id = defaultdict(dict)
    for (part, tr, pid), qty in sol.packs.items():
        packings_by_tr_id[(tr, pid)][part] = qty

    for (tr, pid), parts_in_pack in packings_by_tr_id.items():
        total_size = sum(qty * inst.parts[p].size for p, qty in parts_in_pack.items() if qty > 0)
        capacity = inst.transport_resources[tr].capacity

        if total_size > capacity:
            vr.error(
                f"Capacity violated for TR={tr}, ID={pid}: "
                f"total_size={total_size} > capacity={capacity}, "
                f"contents={dict(parts_in_pack)}"
            )
        else:
            vr.log(f"  TR={tr} ID={pid}: size={total_size}/{capacity} contents={dict(parts_in_pack)} ✓")

    # -------------------------------------------------------------------
    # 3. Flow-packing linkage: for each edge and part,
    #    sum over all TRs and IDs of (pack_qty * freq) >= flow
    # -------------------------------------------------------------------
    vr.log("\nChecking flow-packing linkage constraints...")

    # Collect all (from, to) pairs with flow
    flow_edges = set()
    for (f, t, p) in sol.flows:
        flow_edges.add((f, t))

    for (f, t, p), flow_amount in sol.flows.items():
        if flow_amount == 0:
            continue

        total_transported = 0
        for (lf, lt, tr, pid), freq in sol.transport_links.items():
            if lf == f and lt == t:
                pack_qty = sol.packs.get((p, tr, pid), 0)
                total_transported += pack_qty * freq

        if total_transported < flow_amount:
            vr.error(
                f"Flow-packing linkage violated on ({f},{t}) for {p}: "
                f"transported={total_transported} < flow={flow_amount}"
            )
        elif total_transported > flow_amount:
            vr.warn(
                f"Over-transport on ({f},{t}) for {p}: "
                f"transported={total_transported} > flow={flow_amount} (waste)"
            )
        else:
            vr.log(f"  ({f},{t})/{p}: transported={total_transported} == flow={flow_amount} ✓")

    # -------------------------------------------------------------------
    # 4. No phantom transport: transport links should only exist if
    #    there's corresponding flow
    # -------------------------------------------------------------------
    vr.log("\nChecking for phantom transport (transport without flow)...")

    for (f, t, tr, pid), freq in sol.transport_links.items():
        if freq == 0:
            continue
        # Check if any part has non-zero pack qty for this TR/ID
        has_useful_content = False
        for part_name in inst.parts:
            pack_qty = sol.packs.get((part_name, tr, pid), 0)
            flow_amount = sol.flows.get((f, t, part_name), 0)
            if pack_qty > 0 and flow_amount > 0:
                has_useful_content = True
                break

        if not has_useful_content:
            vr.warn(
                f"Phantom transport: transportLink({f},{t},{tr},freq={freq},id={pid}) "
                f"has no useful content being transported"
            )

    # -------------------------------------------------------------------
    # 5. Valid transport resources: parts should only use valid TRs
    # -------------------------------------------------------------------
    vr.log("\nChecking valid transport resource assignments...")

    for (part, tr, pid), qty in sol.packs.items():
        if qty > 0 and tr not in inst.parts[part].valid_tr:
            vr.error(
                f"Invalid TR assignment: {part} packed in {tr} (ID={pid}) "
                f"but validTR={inst.parts[part].valid_tr}"
            )

    # -------------------------------------------------------------------
    # 6. Route existence: transport links should correspond to actual routes
    # -------------------------------------------------------------------
    vr.log("\nChecking route existence...")

    route_set = set()
    for r in inst.routes:
        route_set.add((r.from_loc, r.to_loc, r.tr))

    for (f, t, tr, pid), freq in sol.transport_links.items():
        if freq > 0 and (f, t, tr) not in route_set:
            vr.error(f"Transport link ({f},{t},{tr}) does not correspond to any route")



    # -------------------------------------------------------------------
    # 8. Summary statistics
    # -------------------------------------------------------------------
    vr.log("\n--- Solution Summary ---")
    active_flows = {k: v for k, v in sol.flows.items() if v > 0}
    active_links = {k: v for k, v in sol.transport_links.items() if v > 0}
    active_packs = {k: v for k, v in sol.packs.items() if v > 0}

    vr.log(f"  Active flows: {len(active_flows)}")
    vr.log(f"  Active transport links: {len(active_links)}")
    vr.log(f"  Non-zero packings: {len(active_packs)}")

    for (f, t, p), amount in sorted(active_flows.items()):
        vr.log(f"    flow({f},{t},{p}) = {amount}")

    for (f, t, tr, pid), freq in sorted(active_links.items()):
        parts_str = ", ".join(
            f"{qty}×{p}" for (p, tr2, pid2), qty in sorted(sol.packs.items())
            if tr2 == tr and pid2 == pid and qty > 0
        )
        vr.log(f"    transportLink({f},{t},{tr},freq={freq},id={pid}) [{parts_str}]")

    return vr


# =============================================================================
# Benchmarking
# =============================================================================

def run_clingo_benchmark(instance_path: str, encoding_path: str,
                         timeout: int = 300, extra_args: str = "") -> dict:
    """
    Run clingo with stats enabled and parse timing information.

    Returns a dict with grounding_time, solving_time, total_time, atoms, rules, etc.
    """
    cmd = f"clingo {instance_path} {encoding_path} --stats=2 --time-limit={timeout} {extra_args}"
    print(f"Running: {cmd}")

    start = time.time()
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True,
            text=True,
            timeout=timeout + 30
        )
        wall_time = time.time() - start
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "wall_time": timeout}
    except FileNotFoundError:
        return {"status": "error", "message": "clingo not found"}

    output = result.stdout + result.stderr
    stats = {"status": "ok", "wall_time": wall_time, "raw_output": output}

    # Parse clingo stats
    def extract_stat(pattern, text, cast=float):
        m = re.search(pattern, text)
        return cast(m.group(1)) if m else None

    stats["grounding_time"] = extract_stat(r'Time\s*:\s*([\d.]+)s\s*\(Solving', output)
    stats["solving_time"] = extract_stat(r'Solving:\s*([\d.]+)s', output)
    stats["total_time"] = extract_stat(r'Time\s*:\s*([\d.]+)s', output)

    # Grounding stats
    stats["atoms"] = extract_stat(r'Atoms\s*:\s*(\d+)', output, int)
    stats["rules"] = extract_stat(r'Rules\s*:\s*(\d+)', output, int)
    stats["bodies"] = extract_stat(r'Bodies\s*:\s*(\d+)', output, int)
    stats["variables"] = extract_stat(r'Variables\s*:\s*(\d+)', output, int)
    stats["constraints"] = extract_stat(r'Constraints\s*:\s*(\d+)', output, int)

    # Solving stats
    stats["choices"] = extract_stat(r'Choices\s*:\s*(\d+)', output, int)
    stats["conflicts"] = extract_stat(r'Conflicts\s*:\s*(\d+)', output, int)
    stats["models"] = extract_stat(r'Models\s*:\s*(\d+)', output, int)

    # Optimization
    stats["optimum"] = extract_stat(r'Optimization\s*:\s*(\d+)', output, int)

    return stats


def run_grounding_only(instance_path: str, encoding_path: str, timeout: int = 300) -> dict:
    """
    Run gringo (grounding only) and measure grounding time and program size.
    """
    cmd = f"gringo {instance_path} {encoding_path} --text"
    print(f"Running grounding only: {cmd}")

    start = time.time()
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        wall_time = time.time() - start
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "wall_time": timeout}
    except FileNotFoundError:
        return {"status": "error", "message": "gringo not found"}

    ground_program = result.stdout
    num_rules = ground_program.count('\n')

    return {
        "status": "ok",
        "wall_time": wall_time,
        "ground_rules": num_rules,
        "ground_size_bytes": len(ground_program),
    }


def print_analysis(analysis: dict):
    """Pretty-print the complexity analysis."""
    print("=" * 70)
    print("ENCODING COMPLEXITY ANALYSIS")
    print("=" * 70)

    print("\n--- Instance Statistics ---")
    for k, v in analysis["instance_stats"].items():
        print(f"  {k}: {v}")

    print("\n--- Grounding Estimates ---")
    for k, v in analysis["grounding_estimates"].items():
        print(f"  {k}: {v}")

    print("\n--- Search Space ---")
    for k, v in analysis["search_space"].items():
        print(f"  {k}: {v}")

    print("\n--- LP Comparison ---")
    for k, v in analysis["lp_comparison"].items():
        if isinstance(v, list):
            print(f"  {k}:")
            for item in v:
                print(f"    - {item}")
        else:
            print(f"  {k}: {v}")





def main():
    parser = argparse.ArgumentParser(description="ASP Logistics Verifier and Benchmarker")

    parser.add_argument("--verify", action="store_true", help="Verify a solution")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmarks")
    parser.add_argument("--analyze", action="store_true", help="Static complexity analysis")
    parser.add_argument("--bugs", action="store_true", help="Generate bug report")
    parser.add_argument("--generate", action="store_true", help="Generate scaled instance")
    parser.add_argument("--scaling", action="store_true", help="Run scaling experiments")

    parser.add_argument("--instance", type=str, default="instance.lp")
    parser.add_argument("--encoding", type=str, default="encoding.lp")
    parser.add_argument("--solution", type=str, help="Solution file (clingo text output)")
    parser.add_argument("--json", action="store_true", help="Parse JSON output (--outf=2)")
    parser.add_argument("--timeout", type=int, default=300)

    # Generation options
    parser.add_argument("--locations", type=int, default=6)
    parser.add_argument("--parts", type=int, default=2)
    parser.add_argument("--output", type=str, default="generated_instance.lp")

    args = parser.parse_args()

    if args.analyze or (not any([args.verify, args.benchmark, args.bugs, args.generate, args.scaling])):
        # Default action: static analysis
        inst = parse_instance(args.instance)
        analysis = analyze_encoding_complexity(inst)
        print_analysis(analysis)


    if args.verify:
        inst = parse_instance(args.instance)
        if args.solution:
            with open(args.solution, 'r') as f:
                text = f.read()
            if args.json:
                solutions = parse_clingo_json(text)
                if solutions:
                    sol = solutions[-1]  # last (best) solution
                else:
                    print("No solutions found in JSON output")
                    sys.exit(1)
            else:
                sol = parse_clingo_text(text)
        else:
            text = sys.stdin.read()
            if args.json:
                solutions = parse_clingo_json(text)
                sol = solutions[-1] if solutions else None
            else:
                sol = parse_clingo_text(text)

        if sol is None:
            print("No solution to verify")
            sys.exit(1)

        vr = verify_solution(inst, sol)
        print(vr.report())
        sys.exit(0 if vr.passed else 1)

    if args.benchmark:
        results = run_benchmark_suite(args.instance, args.encoding, args.timeout)
        print(json.dumps(results, indent=2, default=str))

    if args.scaling:
        results = run_scaling_experiment(args.encoding, timeout=args.timeout)
        print("\n\n" + "=" * 70)
        print("SCALING SUMMARY")
        print("=" * 70)
        for r in results:
            b = r["benchmark"]
            a = r["analysis"]["instance_stats"]
            print(f"\n{r['label']}:")
            print(f"  Routes: {a['routes']}, LP constraints: {r['analysis']['lp_comparison']['lp_constraints']}")
            if b.get("grounding_time"):
                print(f"  Ground: {b['grounding_time']:.3f}s, Solve: {b.get('solving_time', 'N/A')}s")
            if b.get("atoms"):
                print(f"  Atoms: {b['atoms']}, Rules: {b['rules']}, Vars: {b.get('variables', 'N/A')}")
            print(f"  Status: {b.get('status')}")


if __name__ == "__main__":
    main()
