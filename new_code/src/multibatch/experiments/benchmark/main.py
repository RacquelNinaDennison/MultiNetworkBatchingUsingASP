"""Benchmark harness for one-shot solvers.

Runs naive (basic), naive (optimised), and clingcon solvers across
all instances with varying bin counts. Outputs raw and averaged CSVs.

Usage:
    cd new_code
    uv run python -m multibatch.experiments.benchmark.main
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, fields, asdict
from pathlib import Path

from multibatch.models import NaiveOneShotConfig, ClingconOneShotConfig
from multibatch.solvers.naive import NaiveOneShotSolver
from multibatch.solvers.clingcon import ClingconOneShotSolver

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

INSTANCE_DIR = Path(__file__).resolve().parent.parent.parent / "instances" / "generated"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

BIN_RANGE = range(1, 4)  # 1-3
REPETITIONS = 5
TIME_LIMIT = 60
MAX_FREQ = 20


# ─────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────

@dataclass
class BenchmarkRow:
    solver: str
    instance: str
    instance_size: str
    num_bins: int
    run: int
    ground_time: float | None
    solve_time: float | None
    total_time: float | None
    cost: int | None
    optimum: bool
    satisfiable: bool
    choices: int | None
    conflicts: int | None
    restarts: int | None
    atoms: int | None


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

SIZE_ORDER = ["paper", "small", "medium", "large", "xlarge", "industrylite"]


def get_instance_size(path: Path) -> str:
    name = path.stem
    for size in SIZE_ORDER:
        if size in name:
            return size
    return "unknown"


INCLUDE_SIZES = {"paper", "small", "medium"}


def discover_instances() -> list[Path]:
    instances = sorted(INSTANCE_DIR.glob("*.lp"))
    instances = [p for p in instances if get_instance_size(p) in INCLUDE_SIZES]
    if not instances:
        print(f"No instances found in {INSTANCE_DIR}", file=sys.stderr)
        sys.exit(1)
    return instances


def run_single(solver_name: str, instance_path: Path, num_bins: int) -> BenchmarkRow:
    """Run a single solver invocation and return metrics."""
    instance_size = get_instance_size(instance_path)

    try:
        if solver_name in ("clingcon", "clingcon_optimised"):
            optimised = solver_name == "clingcon_optimised"
            config = ClingconOneShotConfig(
                num_bins=num_bins,
                time_limit=TIME_LIMIT,
                max_freq=MAX_FREQ,
                optimised=optimised,
            )
            solver = ClingconOneShotSolver(instance_path, config)
        else:
            optimised = solver_name == "naive_optimised"
            config = NaiveOneShotConfig(
                num_bins=num_bins,
                time_limit=TIME_LIMIT,
                max_freq=MAX_FREQ,
                optimised=optimised,
            )
            solver = NaiveOneShotSolver(instance_path, config)

        result = solver.solve()
    except Exception as e:
        print(f"ERROR: {e}")
        return BenchmarkRow(
            solver=solver_name,
            instance=instance_path.stem,
            instance_size=instance_size,
            num_bins=num_bins,
            run=0,
            ground_time=None,
            solve_time=None,
            total_time=None,
            cost=None,
            optimum=False,
            satisfiable=False,
            choices=None,
            conflicts=None,
            restarts=None,
            atoms=None,
        )

    if result is not None:
        m = result.metadata
        return BenchmarkRow(
            solver=solver_name,
            instance=instance_path.stem,
            instance_size=instance_size,
            num_bins=num_bins,
            run=0,
            ground_time=m.ground_time,
            solve_time=m.solve_time,
            total_time=m.total_time,
            cost=m.cost,
            optimum=m.optimum,
            satisfiable=True,
            choices=m.choices,
            conflicts=m.conflicts,
            restarts=m.restarts,
            atoms=m.atoms,
        )
    else:
        return BenchmarkRow(
            solver=solver_name,
            instance=instance_path.stem,
            instance_size=instance_size,
            num_bins=num_bins,
            run=0,
            ground_time=None,
            solve_time=None,
            total_time=None,
            cost=None,
            optimum=False,
            satisfiable=False,
            choices=None,
            conflicts=None,
            restarts=None,
            atoms=None,
        )


# ─────────────────────────────────────────────────────────────────────
# CSV output
# ─────────────────────────────────────────────────────────────────────

def write_raw_csv(rows: list[BenchmarkRow], path: Path) -> None:
    fieldnames = [f.name for f in fields(BenchmarkRow)]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _safe_avg(values: list[float | int | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 3)


def write_summary_csv(rows: list[BenchmarkRow], path: Path) -> None:
    from collections import defaultdict

    groups: dict[tuple, list[BenchmarkRow]] = defaultdict(list)
    for row in rows:
        key = (row.solver, row.instance, row.instance_size, row.num_bins)
        groups[key].append(row)

    fieldnames = [
        "solver", "instance", "instance_size", "num_bins", "num_runs",
        "avg_ground_time", "avg_solve_time", "avg_total_time",
        "cost", "optimum", "satisfiable",
        "avg_choices", "avg_conflicts", "avg_restarts", "atoms",
    ]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for key in sorted(groups.keys()):
            group = groups[key]
            solver, instance, size, bins = key
            sat_runs = [r for r in group if r.satisfiable]
            n = len(sat_runs)

            if n == 0:
                writer.writerow({
                    "solver": solver,
                    "instance": instance,
                    "instance_size": size,
                    "num_bins": bins,
                    "num_runs": len(group),
                    "avg_ground_time": None,
                    "avg_solve_time": None,
                    "avg_total_time": None,
                    "cost": None,
                    "optimum": False,
                    "satisfiable": False,
                    "avg_choices": None,
                    "avg_conflicts": None,
                    "avg_restarts": None,
                    "atoms": None,
                })
            else:
                writer.writerow({
                    "solver": solver,
                    "instance": instance,
                    "instance_size": size,
                    "num_bins": bins,
                    "num_runs": len(group),
                    "avg_ground_time": _safe_avg([r.ground_time for r in sat_runs]),
                    "avg_solve_time": _safe_avg([r.solve_time for r in sat_runs]),
                    "avg_total_time": _safe_avg([r.total_time for r in sat_runs]),
                    "cost": sat_runs[-1].cost,
                    "optimum": all(r.optimum for r in sat_runs),
                    "satisfiable": True,
                    "avg_choices": _safe_avg([r.choices for r in sat_runs]),
                    "avg_conflicts": _safe_avg([r.conflicts for r in sat_runs]),
                    "avg_restarts": _safe_avg([r.restarts for r in sat_runs]),
                    "atoms": sat_runs[0].atoms,  # deterministic across runs
                })


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

SOLVER_NAMES = ["naive_basic", "naive_optimised", "clingcon", "clingcon_optimised"]


def main() -> None:
    instances = discover_instances()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    total_runs = len(SOLVER_NAMES) * len(instances) * len(BIN_RANGE) * REPETITIONS
    print(f"Benchmark: {len(SOLVER_NAMES)} solvers x {len(instances)} instances "
          f"x {len(BIN_RANGE)} bin sizes x {REPETITIONS} reps = {total_runs} runs")
    print(f"Time limit: {TIME_LIMIT}s | Max freq: {MAX_FREQ} | Bins: {list(BIN_RANGE)}")
    print(f"Instances: {INSTANCE_DIR}")
    print()

    rows: list[BenchmarkRow] = []
    completed = 0

    for solver_name in SOLVER_NAMES:
        print(f"{'='*60}")
        print(f"  Solver: {solver_name}")
        print(f"{'='*60}")

        for instance_path in instances:
            for num_bins in BIN_RANGE:
                for rep in range(1, REPETITIONS + 1):
                    completed += 1
                    tag = f"[{completed}/{total_runs}]"
                    print(
                        f"  {tag} {instance_path.stem} | bins={num_bins} | "
                        f"run {rep}/{REPETITIONS}",
                        end=" ... ",
                        flush=True,
                    )

                    row = run_single(solver_name, instance_path, num_bins)
                    row.run = rep
                    rows.append(row)

                    if row.satisfiable:
                        opt = "OPT" if row.optimum else "SAT"
                        print(f"{opt} cost={row.cost} t={row.total_time}s")
                    else:
                        print("UNSAT/ERROR")

    # Write results
    raw_path = RESULTS_DIR / "benchmark_raw.csv"
    summary_path = RESULTS_DIR / "benchmark_summary.csv"

    write_raw_csv(rows, raw_path)
    write_summary_csv(rows, summary_path)

    print(f"\nDone! {len(rows)} runs completed.")
    print(f"  Raw:     {raw_path}")
    print(f"  Summary: {summary_path}")


if __name__ == "__main__":
    main()
