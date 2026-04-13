#!/usr/bin/env python3
"""
evaluate.py — Packing diversity experiment runner and Jaccard comparator.

Runs multiple objective variants against the same instance using clingcon,
parses the solutions, and computes:
  - Pairwise Jaccard similarity at three granularities
    (route structure, active flows, frequency match)
  - Per-solution quality metrics
    (parts per route, fill rate, active routes, total frequency)
  - Solver performance (time, models found)

Usage:
    python evaluate.py --instance ../data/paper_instances.lp
    python evaluate.py --instance ../data/paper_instances.lp --time-limit 30
    python evaluate.py --instance ../data/paper_instances.lp --variants E1_baseline E3_full
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from statistics import mean


HERE = Path(__file__).parent
ENCODINGS_DIR = HERE / "encodings"
RESULTS_DIR = HERE / "results"
BASE_ENCODING = ENCODINGS_DIR / "base_flow.lp"

# Objective variants in experiment order
VARIANTS: dict[str, Path] = {
    "E1_baseline":   ENCODINGS_DIR / "obj_baseline.lp",
    "E2_cost_co2":   ENCODINGS_DIR / "obj_cost_co2.lp",
    "E3_full":       ENCODINGS_DIR / "obj_full.lp",        # cost@3 > co2@2 > hold@1
    "E4_hold_first": ENCODINGS_DIR / "obj_hold_first.lp",  # hold@3 > cost@2 > co2@1
    "E5_co2_first":  ENCODINGS_DIR / "obj_co2_first.lp",   # co2@3 > cost@2 > hold@1
}


# ── Data structures ──────────────────────────────────────────────────────

@dataclass
class Solution:
    """Parsed clingcon solution."""
    variant: str
    route_freqs: dict[tuple, tuple] = field(default_factory=dict)
    loads: dict[tuple, int] = field(default_factory=dict)
    solve_time: float = 0.0
    models_found: int = 0
    optimization: list[int] = field(default_factory=list)


@dataclass
class QualityMetrics:
    """Per-solution quality metrics."""
    variant: str
    active_route_count: int = 0
    total_frequency: int = 0
    avg_parts_per_route: float = 0.0
    min_parts_per_route: int = 0
    mono_sku_routes: int = 0
    avg_fill_rate: float = 0.0
    min_fill_rate: float = 0.0
    avg_max_part_share: float = 0.0


@dataclass
class JaccardResult:
    """Pairwise Jaccard comparison."""
    variant_a: str
    variant_b: str
    jaccard_routes: float = 0.0
    jaccard_flows: float = 0.0
    jaccard_freq: float = 0.0


# ── Solver ───────────────────────────────────────────────────────────────

def run_clingcon(
    instance_path: Path,
    objective_path: Path,
    time_limit: int,
    extra_args: list[str],
) -> tuple[str, float]:
    """Run clingcon and return (combined_output, wall_time)."""
    cmd = [
        "clingcon",
        str(BASE_ENCODING),
        str(objective_path),
        str(instance_path),
        f"--time-limit={time_limit}",
        *extra_args,
    ]

    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=time_limit + 30)
    wall = time.perf_counter() - t0

    return proc.stdout + proc.stderr, wall


# ── Parser ───────────────────────────────────────────────────────────────

def parse_solution(output: str, variant: str, wall_time: float) -> Solution:
    """Parse clingcon text output into a Solution.

    clingcon output format per answer:
        Answer: N (Time: X.XXXs)
        routeFreq(...) routeFreq(...)
        Assignment:
        load(...)=N load(...)=N ...
        Optimization: V1 V2 ...
    """
    sol = Solution(variant=variant, solve_time=round(wall_time, 3))

    # Split output into lines for line-by-line parsing
    lines = output.split('\n')

    # Find all answer blocks
    answer_starts = []
    for i, line in enumerate(lines):
        if re.match(r'Answer:\s*\d+', line):
            answer_starts.append(i)

    if not answer_starts:
        print(f"  WARNING: no answer found for {variant}", file=sys.stderr)
        return sol

    sol.models_found = len(answer_starts)

    # Parse the LAST answer block (best solution found)
    last_start = answer_starts[-1]
    atoms_line = ""
    assign_line = ""
    opt_line = ""

    # Line after "Answer: N ..." is the atoms line
    if last_start + 1 < len(lines):
        atoms_line = lines[last_start + 1]

    # Look for Assignment: and Optimization: after the atoms line
    for i in range(last_start + 2, min(last_start + 10, len(lines))):
        line = lines[i]
        if line.startswith("Assignment:"):
            # Assignment values are on the next line
            if i + 1 < len(lines):
                assign_line = lines[i + 1]
        elif line.startswith("Optimization:"):
            opt_line = line

    # Parse routeFreq atoms
    for m in re.finditer(r'routeFreq\(([^,]+),([^,]+),([^,]+),(\d+),(\d+)\)', atoms_line):
        f, t, tr = m.group(1), m.group(2), m.group(3)
        freq, cap = int(m.group(4)), int(m.group(5))
        sol.route_freqs[(f, t, tr)] = (freq, cap)

    # Parse load assignments
    for m in re.finditer(r'load\(([^,]+),([^,]+),([^,]+),([^)]+)\)=(\d+)', assign_line):
        f, t, tr, p = m.group(1), m.group(2), m.group(3), m.group(4)
        sol.loads[(f, t, tr, p)] = int(m.group(5))

    # Fallback: check atoms_line for load assignments too
    if not sol.loads:
        for m in re.finditer(r'load\(([^,]+),([^,]+),([^,]+),([^)]+)\)=(\d+)', atoms_line):
            f, t, tr, p = m.group(1), m.group(2), m.group(3), m.group(4)
            sol.loads[(f, t, tr, p)] = int(m.group(5))

    # Parse optimization values
    opt_m = re.search(r'Optimization:\s*([\d\s]+)', opt_line)
    if opt_m:
        sol.optimization = [int(x) for x in opt_m.group(1).strip().split()]

    return sol


# ── Quality metrics ──────────────────────────────────────────────────────

def compute_quality(sol: Solution, instance_data: dict) -> QualityMetrics:
    """Compute packing quality metrics from a solution."""
    qm = QualityMetrics(variant=sol.variant)

    # Active routes and flows
    active_routes: dict[tuple, set] = defaultdict(set)
    for (f, t, tr, p), n in sol.loads.items():
        if n > 0:
            active_routes[(f, t, tr)].add(p)

    qm.active_route_count = len(active_routes)

    # Parts per route
    if active_routes:
        counts = [len(ps) for ps in active_routes.values()]
        qm.avg_parts_per_route = round(mean(counts), 2)
        qm.min_parts_per_route = min(counts)
        qm.mono_sku_routes = sum(1 for c in counts if c == 1)

    # Total frequency
    qm.total_frequency = sum(freq for freq, _ in sol.route_freqs.values())

    # Fill rate per route
    fill_rates = []
    for (f, t, tr), (freq, total_cap) in sol.route_freqs.items():
        if total_cap <= 0:
            continue
        used = sum(
            sol.loads.get((f, t, tr, p), 0) * instance_data["part_size"].get(p, 0)
            for p in instance_data["parts"]
        )
        fill_rates.append(used / total_cap)

    if fill_rates:
        qm.avg_fill_rate = round(mean(fill_rates), 3)
        qm.min_fill_rate = round(min(fill_rates), 3)

    # Max single-part share (concentration)
    shares = []
    for (f, t, tr), parts in active_routes.items():
        if len(parts) < 2:
            continue
        volumes = {
            p: sol.loads.get((f, t, tr, p), 0) * instance_data["part_size"].get(p, 1)
            for p in parts
        }
        total = sum(volumes.values())
        if total > 0:
            shares.append(max(volumes.values()) / total)

    qm.avg_max_part_share = round(mean(shares), 3) if shares else 1.0

    return qm


# ── Jaccard ──────────────────────────────────────────────────────────────

def jaccard(a: set, b: set) -> float:
    """Jaccard index: |A ∩ B| / |A ∪ B|."""
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def compute_jaccard(sol_a: Solution, sol_b: Solution) -> JaccardResult:
    """Compute pairwise Jaccard at three granularities."""
    jr = JaccardResult(variant_a=sol_a.variant, variant_b=sol_b.variant)

    # 1. Route structure: which (F,T,TR) arcs are used?
    routes_a = {(f, t, tr) for (f, t, tr, _), n in sol_a.loads.items() if n > 0}
    routes_b = {(f, t, tr) for (f, t, tr, _), n in sol_b.loads.items() if n > 0}
    jr.jaccard_routes = round(jaccard(routes_a, routes_b), 4)

    # 2. Active flows: which (F,T,TR,P) tuples have load > 0?
    flows_a = {k for k, n in sol_a.loads.items() if n > 0}
    flows_b = {k for k, n in sol_b.loads.items() if n > 0}
    jr.jaccard_flows = round(jaccard(flows_a, flows_b), 4)

    # 3. Frequency match: which (F,T,TR,Freq) tuples match?
    freq_a = {(f, t, tr, freq) for (f, t, tr), (freq, _) in sol_a.route_freqs.items()}
    freq_b = {(f, t, tr, freq) for (f, t, tr), (freq, _) in sol_b.route_freqs.items()}
    jr.jaccard_freq = round(jaccard(freq_a, freq_b), 4)

    return jr


# ── Instance parser ──────────────────────────────────────────────────────

def parse_instance(path: Path) -> dict:
    """Extract parts and part sizes from instance file."""
    text = path.read_text()
    data: dict = {"parts": set(), "part_size": {}, "part_val": {}}

    for m in re.finditer(r'\bpart\((\w+)\)', text):
        data["parts"].add(m.group(1))
    for m in re.finditer(r'\bpartSize\((\w+),(\d+)\)', text):
        data["part_size"][m.group(1)] = int(m.group(2))
    for m in re.finditer(r'\bpartVal\((\w+),(\d+)\)', text):
        data["part_val"][m.group(1)] = int(m.group(2))

    return data


# ── Reporting ────────────────────────────────────────────────────────────

def print_solution_summary(sol: Solution) -> None:
    """Print a compact summary of one solution."""
    nonzero = {k: v for k, v in sol.loads.items() if v > 0}
    routes = {(f, t, tr) for (f, t, tr, _) in nonzero}
    print(f"  Active routes : {len(routes)}")
    print(f"  Non-zero loads: {len(nonzero)}")
    print(f"  Route freqs   : {len(sol.route_freqs)}")
    print(f"  Optimization  : {sol.optimization}")
    print(f"  Solve time    : {sol.solve_time:.2f}s")
    print(f"  Models found  : {sol.models_found}")


def print_quality_table(metrics: list[QualityMetrics]) -> None:
    """Print quality metrics as a table."""
    header = (
        f"{'Variant':<16} {'Routes':>6} {'TotFreq':>7} "
        f"{'AvgPPR':>6} {'MinPPR':>6} {'MonoSKU':>7} "
        f"{'AvgFill':>7} {'MinFill':>7} {'MaxShare':>8}"
    )
    print(header)
    print("─" * len(header))
    for qm in metrics:
        print(
            f"{qm.variant:<16} {qm.active_route_count:>6} {qm.total_frequency:>7} "
            f"{qm.avg_parts_per_route:>6.2f} {qm.min_parts_per_route:>6} {qm.mono_sku_routes:>7} "
            f"{qm.avg_fill_rate:>7.3f} {qm.min_fill_rate:>7.3f} {qm.avg_max_part_share:>8.3f}"
        )


def print_jaccard_table(results: list[JaccardResult]) -> None:
    """Print Jaccard comparisons as a table."""
    header = f"{'Pair':<35} {'J_routes':>8} {'J_flows':>8} {'J_freq':>8}"
    print(header)
    print("─" * len(header))
    for jr in results:
        pair = f"{jr.variant_a} vs {jr.variant_b}"
        print(f"{pair:<35} {jr.jaccard_routes:>8.4f} {jr.jaccard_flows:>8.4f} {jr.jaccard_freq:>8.4f}")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run packing diversity experiments and compute Jaccard comparisons."
    )
    parser.add_argument("--instance", "-i", required=True,
                        help="Path to the instance .lp file")
    parser.add_argument("--time-limit", "-t", type=int, default=60,
                        help="Per-variant time limit in seconds (default: 60)")
    parser.add_argument("-c", action="append", default=[], dest="constants",
                        help="Constants to pass to clingcon (e.g. -c cap_size_divide=10000)")
    parser.add_argument("--config", default="",
                        help="Clingo configuration (default: none)")
    parser.add_argument("--threads", type=int, default=1,
                        help="Number of threads (default: 1)")
    parser.add_argument("--variants", nargs="+",
                        choices=list(VARIANTS.keys()),
                        default=list(VARIANTS.keys()),
                        help="Which variants to run (default: all)")
    args = parser.parse_args()

    instance_path = Path(args.instance)
    if not instance_path.exists():
        print(f"Error: instance not found: {instance_path}", file=sys.stderr)
        return 1

    extra_args = [f"--configuration={args.config}", f"-t{args.threads}"]
    for c in args.constants:
        extra_args.extend(["-c", c])

    instance_data = parse_instance(instance_path)

    # Run each variant
    solutions: dict[str, Solution] = {}

    for variant in args.variants:
        obj_path = VARIANTS[variant]
        if not obj_path.exists():
            print(f"  SKIP {variant}: {obj_path} not found")
            continue

        print(f"{'─'*60}")
        print(f"Running {variant} ...")
        print(f"Objective: {obj_path.name}")

        try:
            output, wall = run_clingcon(
                instance_path, obj_path, args.time_limit, extra_args
            )
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT after {args.time_limit + 30}s")
            continue

        sol = parse_solution(output, variant, wall)
        solutions[variant] = sol
        print_solution_summary(sol)
        print()

    if len(solutions) < 1:
        print("No solutions found.")
        return 1

    # Quality metrics
    print(f"\n{'═'*60}")
    print("QUALITY METRICS")
    print(f"{'═'*60}")

    quality_results = []
    for sol in solutions.values():
        quality_results.append(compute_quality(sol, instance_data))

    print_quality_table(quality_results)

    # Pairwise Jaccard
    jaccard_results = []
    if len(solutions) >= 2:
        print(f"\n{'═'*60}")
        print("JACCARD SIMILARITY (pairwise)")
        print(f"{'═'*60}")

        variant_names = list(solutions.keys())
        for a, b in combinations(variant_names, 2):
            jaccard_results.append(compute_jaccard(solutions[a], solutions[b]))

        print_jaccard_table(jaccard_results)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    inst_stem = instance_path.stem

    q_path = RESULTS_DIR / f"quality_{inst_stem}_{timestamp}.csv"
    with q_path.open("w", newline="") as f:
        fns = ["variant", "active_route_count", "total_frequency",
               "avg_parts_per_route", "min_parts_per_route", "mono_sku_routes",
               "avg_fill_rate", "min_fill_rate", "avg_max_part_share"]
        w = csv.DictWriter(f, fieldnames=fns)
        w.writeheader()
        for qm in quality_results:
            w.writerow({k: getattr(qm, k) for k in fns})

    if jaccard_results:
        j_path = RESULTS_DIR / f"jaccard_{inst_stem}_{timestamp}.csv"
        with j_path.open("w", newline="") as f:
            fns = ["variant_a", "variant_b", "jaccard_routes", "jaccard_flows", "jaccard_freq"]
            w = csv.DictWriter(f, fieldnames=fns)
            w.writeheader()
            for jr in jaccard_results:
                w.writerow({k: getattr(jr, k) for k in fns})
        print(f"\nJaccard CSV  → {j_path}")

    s_path = RESULTS_DIR / f"solutions_{inst_stem}_{timestamp}.json"
    sol_data = {}
    for variant, sol in solutions.items():
        sol_data[variant] = {
            "route_freqs": {
                f"{k[0]},{k[1]},{k[2]}": {"freq": v[0], "cap": v[1]}
                for k, v in sol.route_freqs.items()
            },
            "loads": {
                f"{k[0]},{k[1]},{k[2]},{k[3]}": v
                for k, v in sol.loads.items() if v > 0
            },
            "optimization": sol.optimization,
            "solve_time": sol.solve_time,
            "models_found": sol.models_found,
        }
    s_path.write_text(json.dumps(sol_data, indent=2))

    print(f"Quality CSV  → {q_path}")
    print(f"Solutions    → {s_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
