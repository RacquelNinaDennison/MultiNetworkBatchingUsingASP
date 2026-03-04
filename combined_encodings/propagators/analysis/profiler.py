"""
ASP Encoding Profiler — using the Clingo Python API

Usage:
    # Full bottleneck diagnosis:
    python3 profiler.py --profile \
        --instance orginal_asp_approach/instances.lp \
        --encoding orginal_asp_approach/encoding.lp

    # Scaling wall (vary parameters to find where it breaks):
    python3 profiler.py --scaling-wall \
        --instance orginal_asp_approach/instances.lp \
        --encoding orginal_asp_approach/encoding.lp \
        --output-csv data/scaling_results.csv

    # Grounding anatomy (what blows up):
    python3 profiler.py --grounding-anatomy \
        --instance orginal_asp_approach/instances.lp \
        --encoding orginal_asp_approach/encoding.lp
"""

import argparse
import csv
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import clingo


# =============================================================================
# Stats Data Structure
# =============================================================================

@dataclass
class ProfileResult:
    """All measurable data from one clingo run."""

    grounding_time: float = 0.0
    solving_time: float = 0.0
    total_time: float = 0.0

    atoms: int = 0
    rules: int = 0
    bodies: int = 0
    equivalences: int = 0

    # Solver size (from ctl.statistics after solving)
    variables: int = 0
    eliminated: int = 0
    constraints: int = 0

    # Search (from ctl.statistics after solving)
    choices: int = 0
    conflicts: int = 0
    restarts: int = 0

    # Extra grounding detail
    constraints_binary: int = 0
    constraints_ternary: int = 0
    complexity: int = 0
    rules_choice: int = 0
    rules_normal: int = 0
    sum_bodies: int = 0  # number of #sum aggregate bodies

    # Learned clauses detail
    lemmas: int = 0
    lemmas_deleted: int = 0
    lits_learnt: int = 0

    # Result
    models: int = 0
    optimum_found: bool = False
    optimal_cost: Optional[int] = None
    satisfiable: bool = False
    timed_out: bool = False

    # clingo's own timing (from statistics)
    clingo_total: float = 0.0
    clingo_solve: float = 0.0
    clingo_unsat: float = 0.0
    clingo_sat: float = 0.0
    clingo_cpu: float = 0.0

    # Configuration used
    config: Dict[str, int] = field(default_factory=dict)

    # --- Derived Metrics ---

    @property
    def conflict_rate(self) -> float:
        return self.conflicts / max(self.choices, 1)

    @property
    def grounding_fraction(self) -> float:
        return self.grounding_time / max(self.total_time, 0.001)

    @property
    def solving_fraction(self) -> float:
        return self.solving_time / max(self.total_time, 0.001)

    @property
    def choices_per_variable(self) -> float:
        return self.choices / max(self.variables, 1)

    @property
    def avg_learnt_clause_length(self) -> float:
        """Average literals per learned clause — longer = harder conflicts."""
        return self.lits_learnt / max(self.lemmas, 1)

    def to_dict(self) -> dict:
        return {
            "grounding_time": self.grounding_time,
            "solving_time": self.solving_time,
            "total_time": self.total_time,
            "atoms": self.atoms,
            "rules": self.rules,
            "bodies": self.bodies,
            "variables": self.variables,
            "eliminated": self.eliminated,
            "constraints": self.constraints,
            "constraints_binary": self.constraints_binary,
            "constraints_ternary": self.constraints_ternary,
            "complexity": self.complexity,
            "sum_bodies": self.sum_bodies,
            "choices": self.choices,
            "conflicts": self.conflicts,
            "restarts": self.restarts,
            "conflict_rate": self.conflict_rate,
            "lemmas": self.lemmas,
            "avg_learnt_clause_len": self.avg_learnt_clause_length,
            "models": self.models,
            "optimum_found": self.optimum_found,
            "optimal_cost": self.optimal_cost,
            "satisfiable": self.satisfiable,
            "timed_out": self.timed_out,
            **{f"cfg_{k}": v for k, v in self.config.items()},
        }


# =============================================================================
# Core: Run clingo via API with separate grounding/solving measurement
# =============================================================================

def walk_stats(stats_map, prefix="") -> Dict[str, Any]:
    """
    Recursively walk the clingo statistics object and flatten it.

    Handles two cases:
    - Newer clingo: stats_map is a clingo.Statistics object with .type attribute
    - Older clingo / some builds: stats_map is a plain Python dict/list/float
    """
    result = {}

    # Case 1: plain Python types (older clingo returns native dicts)
    if isinstance(stats_map, (int, float)):
        return {prefix: stats_map}
    elif isinstance(stats_map, dict):
        for key, val in stats_map.items():
            child = walk_stats(val, f"{prefix}.{key}" if prefix else key)
            result.update(child)
        return result
    elif isinstance(stats_map, (list, tuple)):
        for i, val in enumerate(stats_map):
            child = walk_stats(val, f"{prefix}[{i}]")
            result.update(child)
        return result
    elif isinstance(stats_map, str):
        return {prefix: stats_map}

    # Case 2: clingo.Statistics object (newer clingo)
    if hasattr(stats_map, 'type'):
        stype = stats_map.type
        if stype == clingo.StatisticsType.Value:
            return {prefix: stats_map.value}
        elif stype == clingo.StatisticsType.Array:
            for i in range(len(stats_map)):
                child = walk_stats(stats_map[i], f"{prefix}[{i}]")
                result.update(child)
        elif stype == clingo.StatisticsType.Map:
            for key in stats_map.keys():
                child = walk_stats(stats_map[key],
                                 f"{prefix}.{key}" if prefix else key)
                result.update(child)
        return result

    # Fallback
    return {prefix: str(stats_map)}


def safe_get(flat_stats: dict, key: str, default=0, cast=None):
    """Get a value from flat stats, trying common path variations."""
    val = flat_stats.get(key, default)
    if cast and val is not default:
        try:
            return cast(val)
        except (ValueError, TypeError):
            return default
    return val


def run_profile(instance_path: str, encoding_path: str,
                timeout: int = 120,
                const_overrides: Dict[str, int] = None,
                solve_args: List[str] = None) -> ProfileResult:
    """
    Run clingo via the Python API with precise phase timing.

    Steps:
    1. Create control object with configuration
    2. Load files
    3. Ground (timed separately)
    4. Solve (timed separately)
    5. Extract statistics from ctl.statistics
    """
    result = ProfileResult()
    if const_overrides:
        result.config = const_overrides.copy()

    # --- 1. Create control object ---
    args = ["--stats=2"]
    if const_overrides:
        for name, value in const_overrides.items():
            args.extend(["-c", f"{name}={value}"])
    if solve_args:
        args.extend(solve_args)

    ctl = clingo.Control(args)

    # --- 2. Load files ---
    ctl.load(instance_path)
    ctl.load(encoding_path)

    # --- 3. Ground (timed) ---
    t0 = time.perf_counter()
    try:
        ctl.ground([("base", [])])
    except RuntimeError as e:
        print(f"  Grounding error: {e}")
        result.grounding_time = time.perf_counter() - t0
        result.total_time = result.grounding_time
        result.timed_out = True
        return result

    t1 = time.perf_counter()
    result.grounding_time = t1 - t0

    # --- 4. Solve (timed) ---
    best_cost = None
    model_count = 0

    def on_model(model):
        nonlocal best_cost, model_count
        model_count += 1
        if model.cost:
            best_cost = model.cost[0]

    t2 = time.perf_counter()
    try:
        solve_result = ctl.solve(on_model=on_model)
    except RuntimeError as e:
        print(f"  Solving error: {e}")
        result.solving_time = time.perf_counter() - t2
        result.total_time = result.grounding_time + result.solving_time
        result.timed_out = True
        return result

    t3 = time.perf_counter()
    result.solving_time = t3 - t2
    result.total_time = t3 - t0

    # --- 5. Extract result info ---
    result.models = model_count
    result.satisfiable = solve_result.satisfiable or False
    result.optimum_found = solve_result.exhausted and result.satisfiable
    result.optimal_cost = best_cost

    # --- 6. Extract statistics ---
    flat = walk_stats(ctl.statistics)

    def get_stat(key, default=0):
        """Get a stat by exact key."""
        val = flat.get(key, default)
        if isinstance(val, float) and val == int(val):
            return int(val)
        return val

    def get_first(*keys, default=0):
        """Try multiple exact keys, return first found."""
        for k in keys:
            if k in flat:
                val = flat[k]
                if isinstance(val, float) and val == int(val):
                    return int(val)
                return val
        return default

    # Grounding / LP stats
    # Your clingo uses: problem.lp.atoms, problem.lp.rules, problem.lp.bodies
    result.atoms = get_first("problem.lp.atoms", "problem.lpStep.atoms", default=0)
    result.rules = get_first("problem.lp.rules", "problem.lpStep.rules", default=0)
    result.bodies = get_first("problem.lp.bodies", "problem.lpStep.bodies", default=0)
    result.equivalences = get_first("problem.lp.eqs", "problem.lpStep.eqs", default=0)

    # Solver variables (after preprocessing)
    # Your clingo uses: problem.generator.vars, problem.generator.vars_eliminated
    result.variables = get_first("problem.generator.vars", default=0)
    result.eliminated = get_first("problem.generator.vars_eliminated", default=0)
    result.constraints = get_first("problem.generator.constraints", default=0)

    # Extra grounding detail (useful for thesis)
    result.constraints_binary = get_first("problem.generator.constraints_binary", default=0)
    result.constraints_ternary = get_first("problem.generator.constraints_ternary", default=0)
    result.complexity = get_first("problem.generator.complexity", default=0)
    result.rules_choice = get_first("problem.lp.rules_choice", default=0)
    result.rules_normal = get_first("problem.lp.rules_normal", default=0)
    result.sum_bodies = get_first("problem.lp.sum_bodies", default=0)

    # Search stats
    # Your clingo uses: solving.solvers.choices, solving.solvers.conflicts
    result.choices = get_first(
        "solving.solvers.choices", "accu.solving.solvers.choices", default=0)
    result.conflicts = get_first(
        "solving.solvers.conflicts", "accu.solving.solvers.conflicts", default=0)
    result.restarts = get_first(
        "solving.solvers.restarts", "accu.solving.solvers.restarts", default=0)

    # Learned clauses detail
    result.lemmas = get_first(
        "solving.solvers.extra.lemmas", "accu.solving.solvers.extra.lemmas", default=0)
    result.lemmas_deleted = get_first(
        "solving.solvers.extra.lemmas_deleted",
        "accu.solving.solvers.extra.lemmas_deleted", default=0)
    result.lits_learnt = get_first(
        "solving.solvers.extra.lits_learnt",
        "accu.solving.solvers.extra.lits_learnt", default=0)

    # Clingo's own timing
    # Your clingo uses: summary.times.total, summary.times.solve, etc.
    result.clingo_total = get_first("summary.times.total", "accu.times.total", default=0.0)
    result.clingo_solve = get_first("summary.times.solve", "accu.times.solve", default=0.0)
    result.clingo_unsat = get_first("summary.times.unsat", "accu.times.unsat", default=0.0)
    result.clingo_sat = get_first("summary.times.sat", "accu.times.sat", default=0.0)
    result.clingo_cpu = get_first("summary.times.cpu", "accu.times.cpu", default=0.0)

    return result


# =============================================================================
# Dump raw statistics tree (for exploration)
# =============================================================================

def dump_stats_tree(instance_path: str, encoding_path: str,
                    const_overrides: Dict[str, int] = None) -> dict:
    """
    Ground + solve, then dump the full clingo statistics tree.
    Useful for discovering what keys are available in your clingo version.
    """
    args = ["--stats=2"]
    if const_overrides:
        for name, value in const_overrides.items():
            args.extend(["-c", f"{name}={value}"])

    ctl = clingo.Control(args)
    ctl.load(instance_path)
    ctl.load(encoding_path)
    ctl.ground([("base", [])])
    ctl.solve()

    flat = walk_stats(ctl.statistics)
    return flat


# =============================================================================
# Grounding Anatomy — inspect the ground program via API
# =============================================================================

def grounding_anatomy(instance_path: str, encoding_path: str,
                      const_overrides: Dict[str, int] = None) -> str:
    """
    Use clingo's API to inspect the ground program.
    Counts symbolic atoms by predicate to see what's blowing up.
    """
    args = []
    if const_overrides:
        for name, value in const_overrides.items():
            args.extend(["-c", f"{name}={value}"])

    ctl = clingo.Control(args)
    ctl.load(instance_path)
    ctl.load(encoding_path)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    ground_time = time.perf_counter() - t0

    # Count atoms by predicate signature
    pred_counts = defaultdict(int)
    total_atoms = 0

    for atom in ctl.symbolic_atoms:
        sig = f"{atom.symbol.name}/{len(atom.symbol.arguments)}"
        pred_counts[sig] += 1
        total_atoms += 1

    # Also count which are facts vs choice atoms
    fact_counts = defaultdict(int)
    for atom in ctl.symbolic_atoms:
        sig = f"{atom.symbol.name}/{len(atom.symbol.arguments)}"
        if atom.is_fact:
            fact_counts[sig] += 1

    lines = []
    lines.append(f"\n{'GROUNDING ANATOMY (via clingo API)':=^72}")
    lines.append(f"  Grounding time: {ground_time:.3f}s")
    lines.append(f"  Total symbolic atoms: {total_atoms:,}")
    lines.append(f"\n  {'Predicate':<30} {'Total':>8} {'Facts':>8} {'Choice':>8} {'%':>6}")
    lines.append(f"  {'─'*30} {'─'*8} {'─'*8} {'─'*8} {'─'*6}")

    for sig, count in sorted(pred_counts.items(), key=lambda x: -x[1]):
        facts = fact_counts.get(sig, 0)
        choice = count - facts
        pct = count / max(total_atoms, 1) * 100
        bar = '█' * max(1, int(pct / 2))
        lines.append(f"  {sig:<30} {count:>8,} {facts:>8,} {choice:>8,} {pct:>5.1f}% {bar}")

    # Identify the biggest offenders
    lines.append(f"\n  Key observations:")
    top3 = sorted(pred_counts.items(), key=lambda x: -x[1])[:3]
    for sig, count in top3:
        pct = count / max(total_atoms, 1) * 100
        lines.append(f"    {sig} has {count:,} atoms ({pct:.0f}% of program)")

    # Estimate aggregate contribution
    lines.append(f"\n  Note: Aggregates (#sum) don't appear as atoms but create")
    lines.append(f"  internal solver constraints. Use --profile to see constraint count.")

    return '\n'.join(lines)


# =============================================================================
# Bottleneck Diagnosis
# =============================================================================

def diagnose(result: ProfileResult, label: str = "") -> str:
    """Interpret a ProfileResult and explain where and why it's slow."""
    lines = []
    lines.append(f"\n{'BOTTLENECK DIAGNOSIS':=^72}")
    if label:
        lines.append(f"  Instance: {label}")

    # --- Time ---
    lines.append(f"\n{'─ TIME ─':─^72}")
    lines.append(f"  Total:        {result.total_time:>8.3f}s")
    lines.append(f"  Grounding:    {result.grounding_time:>8.3f}s  ({result.grounding_fraction:>5.1%})")
    lines.append(f"  Solving:      {result.solving_time:>8.3f}s  ({result.solving_fraction:>5.1%})")
    if result.clingo_sat > 0:
        lines.append(f"  ├─ SAT (1st model):  {result.clingo_sat:.3f}s")
        lines.append(f"  └─ Optimization:     {result.clingo_unsat:.3f}s")

    # Primary bottleneck
    if result.timed_out:
        lines.append(f"\n  🔴 TIMED OUT — did not find {'optimum' if result.models > 0 else 'any solution'}.")
    elif result.grounding_fraction > 0.6:
        lines.append(f"\n  🔴 GROUNDING-BOUND ({result.grounding_fraction:.0%} in grounding)")
        lines.append(f"     The ground program is too large. Causes:")
        lines.append(f"       • Domain explosion: numFlow(0..{result.config.get('max_flow', '?')}) × "
                     f"num(0..{result.config.get('max_pack', '?')}) × "
                     f"package_id(0..{result.config.get('max_packages', '?') - 1 if 'max_packages' in result.config else '?'})")
        lines.append(f"       • Every combination becomes a ground atom in choice rules")
        lines.append(f"       • #sum aggregates expand to enumerate all body combinations")
        lines.append(f"     Propagator benefit: replaces grounded aggregates with lazy evaluation")
    elif result.solving_fraction > 0.7:
        lines.append(f"\n  🟡 SOLVING-BOUND ({result.solving_fraction:.0%} in search)")
        lines.append(f"     Ground program fits, but search space is too large.")
        if result.conflict_rate > 0.3:
            lines.append(f"     High conflict rate ({result.conflict_rate:.2f}) — solver hits many dead ends.")
        if result.choices_per_variable > 5:
            lines.append(f"     High branching ({result.choices_per_variable:.0f}× variables) — lots of backtracking.")
        lines.append(f"     Propagator benefit: prune infeasible branches early via theory propagation")
    else:
        lines.append(f"\n  🟢 BALANCED — no single dominant bottleneck")

    # --- Program Size ---
    lines.append(f"\n{'─ PROGRAM SIZE ─':─^72}")
    lines.append(f"  Atoms:          {result.atoms:>10,}")
    lines.append(f"  Rules:          {result.rules:>10,}  (choice: {result.rules_choice:,}, normal: {result.rules_normal:,})")
    lines.append(f"  Bodies:         {result.bodies:>10,}  (#sum aggregates: {result.sum_bodies:,})")
    lines.append(f"  Equivalences:   {result.equivalences:>10,}  (reduced away by preprocessor)")
    lines.append(f"  Solver vars:    {result.variables:>10,}  ({result.eliminated:,} eliminated, {result.variables - result.eliminated:,} frozen)")
    lines.append(f"  Constraints:    {result.constraints:>10,}  (binary: {result.constraints_binary:,}, ternary: {result.constraints_ternary:,})")
    lines.append(f"  Complexity:     {result.complexity:>10,}")

    # --- Search ---
    lines.append(f"\n{'─ SEARCH ─':─^72}")
    lines.append(f"  Choices:        {result.choices:>10,}")
    lines.append(f"  Conflicts:      {result.conflicts:>10,}  (rate: {result.conflict_rate:.3f})")
    lines.append(f"  Restarts:       {result.restarts:>10,}")
    lines.append(f"  Lemmas learned: {result.lemmas:>10,}  ({result.lemmas_deleted:,} deleted)")
    if result.lemmas > 0:
        lines.append(f"  Avg clause len: {result.avg_learnt_clause_length:>10.1f}  literals per learned clause")
    lines.append(f"  Models:         {result.models:>10}")

    # --- Result ---
    lines.append(f"\n{'─ RESULT ─':─^72}")
    if result.optimal_cost is not None:
        lines.append(f"  Best cost:    {result.optimal_cost}")
    lines.append(f"  Optimal:      {'Yes ✓' if result.optimum_found else 'No'}")
    lines.append(f"  Satisfiable:  {'Yes' if result.satisfiable else 'No'}")

    # --- The Core Problem ---
    lines.append(f"\n{'─ WHY YOUR ENCODING IS EXPENSIVE ─':─^72}")
    lines.append(f"  The linkage constraint is the key bottleneck:")
    lines.append(f"    :- flow(From,To,Part,T), T > 0,")
    lines.append(f"       T != #sum{{ Q*Freq,TR,ID :")
    lines.append(f"                   transportLink(From,To,TR,Freq,ID),")
    lines.append(f"                   pack(Q,Part,TR,ID) }}.")
    lines.append(f"")
    lines.append(f"  This constraint is quadratic in the choice variables:")
    lines.append(f"    • Q (pack quantity) is a choice variable: 0..max_pack")
    lines.append(f"    • Freq (transport frequency) is a choice variable: 0..max_flow")
    lines.append(f"    • Their PRODUCT Q*Freq must equal T (another choice variable)")
    lines.append(f"    • The grounder must enumerate all (Q, Freq) combinations")
    lines.append(f"    • The solver must propagate through multiplicative aggregate")
    lines.append(f"")
    lines.append(f"  What a propagator replaces:")
    lines.append(f"    • Instead of grounding all Q*Freq combos → watch flow assignments")
    lines.append(f"    • When flow(a,b,p,T) is decided → check if feasible packing exists")
    lines.append(f"    • If not → propagate UNSAT immediately (no search needed)")
    lines.append(f"    • If yes → lazily suggest frequencies (no enumeration needed)")

    lines.append(f"\n{'':─^72}")
    return '\n'.join(lines)


# =============================================================================
# Scaling Wall Experiment
# =============================================================================

def run_scaling_wall(instance_path: str, encoding_path: str,
                     timeout: int = 120, output_csv: str = None) -> List[dict]:
    """
    Vary encoding constants to find where the encoding breaks.
    Returns results for thesis tables/plots.
    """
    baseline = {"max_flow": 20, "max_packages": 5, "max_pack": 20}

    experiments = [
        ("max_flow",     [5, 10, 15, 20, 30, 40, 50]),
        ("max_packages", [1, 2, 3, 5, 7, 10]),
        ("max_pack",     [5, 10, 15, 20, 30]),
    ]

    all_rows = []

    for param_name, values in experiments:
        print(f"\n{'='*60}")
        print(f"  Varying: {param_name}")
        print(f"{'='*60}")
        print(f"  {'Value':>6} {'Total':>8} {'Ground':>8} {'Solve':>8} "
              f"{'Atoms':>9} {'Vars':>9} {'Choices':>10} {'Conflicts':>10} {'Status':>8}")

        for val in values:
            consts = baseline.copy()
            consts[param_name] = val

            result = run_profile(instance_path, encoding_path,
                                timeout=timeout, const_overrides=consts)

            status = ("TIMEOUT" if result.timed_out
                      else "OPT" if result.optimum_found
                      else "SAT" if result.satisfiable
                      else "UNSAT")

            print(f"  {val:>6} {result.total_time:>7.2f}s {result.grounding_time:>7.2f}s "
                  f"{result.solving_time:>7.2f}s {result.atoms:>9,} {result.variables:>9,} "
                  f"{result.choices:>10,} {result.conflicts:>10,} {status:>8}")

            row = {
                "experiment": param_name,
                "value": val,
                **result.to_dict(),
            }
            all_rows.append(row)

    # Write CSV
    if output_csv and all_rows:
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\n  Results written to {output_csv}")

    return all_rows


# =============================================================================
# Compare Encodings
# =============================================================================

def compare_encodings(instance_path: str, enc1: str, enc2: str,
                      timeout: int = 120,
                      label1: str = "pure_asp", label2: str = "hybrid") -> None:
    """Run both encodings and print a side-by-side comparison table."""
    print(f"\n  Running {label1}...")
    r1 = run_profile(instance_path, enc1, timeout=timeout)

    print(f"  Running {label2}...")
    r2 = run_profile(instance_path, enc2, timeout=timeout)

    print(f"\n{'ENCODING COMPARISON':=^72}")
    print(f"  {'Metric':<25} {label1:>15} {label2:>15} {'Ratio':>10}")
    print(f"  {'─'*25} {'─'*15} {'─'*15} {'─'*10}")

    def row(name, v1, v2, fmt_float=True):
        if fmt_float and isinstance(v1, float):
            ratio = v1 / max(v2, 0.001)
            print(f"  {name:<25} {v1:>14.3f} {v2:>14.3f} {ratio:>9.1f}x")
        else:
            v1i, v2i = int(v1), int(v2)
            ratio = v1i / max(v2i, 1)
            print(f"  {name:<25} {v1i:>14,} {v2i:>14,} {ratio:>9.1f}x")

    row("Total time (s)", r1.total_time, r2.total_time)
    row("Grounding time (s)", r1.grounding_time, r2.grounding_time)
    row("Solving time (s)", r1.solving_time, r2.solving_time)
    row("Atoms", r1.atoms, r2.atoms, False)
    row("Rules", r1.rules, r2.rules, False)
    row("Variables", r1.variables, r2.variables, False)
    row("Constraints", r1.constraints, r2.constraints, False)
    row("Choices", r1.choices, r2.choices, False)
    row("Conflicts", r1.conflicts, r2.conflicts, False)

    c1 = str(r1.optimal_cost) if r1.optimal_cost is not None else "N/A"
    c2 = str(r2.optimal_cost) if r2.optimal_cost is not None else "N/A"
    print(f"  {'Optimal cost':<25} {c1:>15} {c2:>15}")
    print(f"  {'Optimum proven':<25} {str(r1.optimum_found):>15} {str(r2.optimum_found):>15}")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ASP Encoding Profiler (clingo Python API)")

    modes = parser.add_argument_group("modes")
    modes.add_argument("--profile", action="store_true",
                       help="Full bottleneck diagnosis")
    modes.add_argument("--scaling-wall", action="store_true",
                       help="Vary parameters to find breaking points")
    modes.add_argument("--compare", action="store_true",
                       help="Compare two encodings side-by-side")
    modes.add_argument("--grounding-anatomy", action="store_true",
                       help="Count ground atoms by predicate")
    modes.add_argument("--dump-stats", action="store_true",
                       help="Dump full clingo statistics tree (for exploration)")

    parser.add_argument("--instance", type=str, required=True)
    parser.add_argument("--encoding", type=str, required=True)
    parser.add_argument("--encoding2", type=str,
                       help="Second encoding for --compare")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output-csv", type=str,
                       help="Write scaling wall results to CSV")
    parser.add_argument("--label1", type=str, default="pure_asp")
    parser.add_argument("--label2", type=str, default="hybrid")

    args = parser.parse_args()

    # Default to --profile if no mode selected
    if not any([args.profile, args.scaling_wall, args.compare,
                args.grounding_anatomy, args.dump_stats]):
        args.profile = True

    if args.dump_stats:
        flat = dump_stats_tree(args.instance, args.encoding)
        print(f"\n{'FULL STATISTICS TREE':=^72}")
        for key in sorted(flat.keys()):
            print(f"  {key}: {flat[key]}")

    if args.grounding_anatomy:
        print(grounding_anatomy(args.instance, args.encoding))

    if args.profile:
        print(f"  Profiling {args.encoding} on {args.instance}...")
        result = run_profile(args.instance, args.encoding, timeout=args.timeout)
        print(diagnose(result, f"{args.instance} + {args.encoding}"))

        # Also show grounding anatomy
        print(grounding_anatomy(args.instance, args.encoding))

        # Show raw stats keys if program size came back as 0
        # (helps debug find_stat path mismatches)
        if result.rules == 0:
            print(f"\n{'─ RAW STATISTICS KEYS (for debugging) ─':─^72}")
            print(f"  atoms/rules/variables showed 0 — likely a key path mismatch.")
            print(f"  Dumping all stats keys so you can see what your clingo exposes:\n")
            flat = dump_stats_tree(args.instance, args.encoding)
            for key in sorted(flat.keys()):
                print(f"    {key}: {flat[key]}")

    if args.scaling_wall:
        run_scaling_wall(args.instance, args.encoding,
                        timeout=args.timeout, output_csv=args.output_csv)

    if args.compare:
        if not args.encoding2:
            print("ERROR: --compare requires --encoding2")
            sys.exit(1)
        compare_encodings(args.instance, args.encoding, args.encoding2,
                         timeout=args.timeout,
                         label1=args.label1, label2=args.label2)


if __name__ == "__main__":
    main()
