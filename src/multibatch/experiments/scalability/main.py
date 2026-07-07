"""Scalability harness: one-shot vs two-stage encodings.

Compares naive_oneshot, clingcon_oneshot, naive_twostage, clingcon_twostage
on the same instances across sizes paper -> industrylite.

Time-limit semantics
--------------------
One-shot solvers: a single ``time_limit`` budget (seconds).
Two-stage solvers: ``time_limit`` is applied PER STAGE. Stage 1 runs its
multi-shot bound-tightening within that budget, then Stage 2 gets a fresh
``time_limit`` budget. Combined wall time can therefore reach ~2x the
one-shot budget. This is intentional: each stage's encoding deserves its
own optimisation budget. ``wall_time`` (measured around ``solver.solve()``)
captures the real combined wall clock.

Cost comparability
------------------
One-shot ``cost`` is the transport cost objective. Two-stage Stage 1 also
minimises transport cost; Stage 2 minimises used trips. The ``cost`` column
records the transport-cost objective for both families (= one-shot cost,
= ``s1_cost`` for two-stage). ``s2_cost`` is kept in a separate column.

Usage
-----
    cd new_code
    uv run python -m multibatch.experiments.scalability.main
    uv run python -m multibatch.experiments.scalability.main --help
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, fields, asdict
from pathlib import Path

from multibatch.instance import parse_instance
from multibatch.models import (
    NaiveOneShotConfig,
    ClingconOneShotConfig,
    TwoStageNaiveConfig,
    TwoStageClingconConfig,
)
from multibatch.solvers.naive import NaiveOneShotSolver
from multibatch.solvers.clingcon import ClingconOneShotSolver
from multibatch.solvers.twostage_naive import NaiveTwoStageSolver
from multibatch.solvers.twostage_clingcon import ClingconTwoStageSolver

from ..twostage.config import classify_instance, compute_instance_properties


INSTANCE_DIR = Path(__file__).resolve().parent.parent.parent / "instances" / "generated"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

SIZE_ORDER = ["paper", "small", "medium", "large", "xlarge", "industrylite"]

DEFAULT_TIME_LIMITS = {
    "paper": 30,
    "small": 30,
    "medium": 60,
    "large": 120,
    "xlarge": 300,
    "industrylite": 600,
}

SOLVER_NAMES = [
    "naive_oneshot",
    "clingcon_oneshot",
    "naive_twostage",
    "clingcon_twostage",
]

ENCODING_FAMILY = {
    "naive_oneshot": "one-shot",
    "clingcon_oneshot": "one-shot",
    "naive_twostage": "two-stage",
    "clingcon_twostage": "two-stage",
}

BACKEND = {
    "naive_oneshot": "naive",
    "clingcon_oneshot": "clingcon",
    "naive_twostage": "naive",
    "clingcon_twostage": "clingcon",
}


@dataclass
class ScalabilityRow:
    solver: str
    encoding_family: str
    backend: str
    instance: str
    instance_size: str
    seed: int
    n_locations: int
    n_parts: int
    n_routes: int
    n_transports: int
    density: float
    capacity_tightness: float
    num_bins: int | None
    time_limit: int
    run: int
    status: str
    wall_time: float | None
    total_time: float | None
    ground_time: float | None
    solve_time: float | None
    cost: int | None
    optimum: bool
    satisfiable: bool
    choices: int | None
    conflicts: int | None
    restarts: int | None
    atoms: int | None
    # Two-stage extras (None for one-shot)
    s1_time: float | None
    s2_time: float | None
    s1_atoms: int | None
    s2_atoms: int | None
    s1_cost: int | None
    s2_cost: int | None
    s1_optimum: bool | None
    s2_optimum: bool | None


def get_instance_size(path: Path) -> str:
    name = path.stem
    for size in SIZE_ORDER:
        if size in name:
            return size
    return "unknown"


def discover_instances(
    instance_dir: Path,
    include_sizes: set[str],
    instance_filter: str | None,
) -> list[Path]:
    paths = sorted(instance_dir.glob("*.lp"))
    paths = [p for p in paths if get_instance_size(p) in include_sizes]
    if instance_filter:
        paths = [p for p in paths if instance_filter in p.stem]
    if not paths:
        sys.exit(f"No instances found in {instance_dir}")
    return paths


def _empty_row(
    solver_name: str,
    instance_path: Path,
    instance_size: str,
    num_bins: int | None,
    time_limit: int,
    status: str,
) -> ScalabilityRow:
    return ScalabilityRow(
        solver=solver_name,
        encoding_family=ENCODING_FAMILY[solver_name],
        backend=BACKEND[solver_name],
        instance=instance_path.stem,
        instance_size=instance_size,
        seed=0,
        n_locations=0, n_parts=0, n_routes=0, n_transports=0,
        density=0.0, capacity_tightness=0.0,
        num_bins=num_bins,
        time_limit=time_limit,
        run=0,
        status=status,
        wall_time=None, total_time=None,
        ground_time=None, solve_time=None,
        cost=None, optimum=False, satisfiable=False,
        choices=None, conflicts=None, restarts=None, atoms=None,
        s1_time=None, s2_time=None,
        s1_atoms=None, s2_atoms=None,
        s1_cost=None, s2_cost=None,
        s1_optimum=None, s2_optimum=None,
    )


def _attach_properties(row: ScalabilityRow, instance_path: Path) -> None:
    meta = classify_instance(instance_path)
    inst = parse_instance(instance_path)
    compute_instance_properties(meta, inst)
    row.seed = meta.seed
    row.n_locations = meta.n_locations
    row.n_parts = meta.n_parts
    row.n_routes = meta.n_routes
    row.n_transports = meta.n_transports
    row.density = meta.density
    row.capacity_tightness = meta.capacity_tightness


def run_single(
    solver_name: str,
    instance_path: Path,
    num_bins: int,
    time_limit: int,
    max_freq: int,
) -> ScalabilityRow:
    instance_size = get_instance_size(instance_path)
    bins_for_row = num_bins if solver_name.endswith("oneshot") else None
    row = _empty_row(solver_name, instance_path, instance_size, bins_for_row,
                     time_limit, status="ERROR")
    try:
        _attach_properties(row, instance_path)
    except Exception as e:
        print(f"  property-fetch failed: {e}")

    try:
        if solver_name == "naive_oneshot":
            cfg = NaiveOneShotConfig(
                num_bins=num_bins, time_limit=time_limit,
                max_freq=max_freq, optimised=True,
            )
            solver = NaiveOneShotSolver(instance_path, cfg)
            t0 = time.perf_counter()
            result = solver.solve()
            wall = time.perf_counter() - t0
            _fill_oneshot(row, result, wall)

        elif solver_name == "clingcon_oneshot":
            cfg = ClingconOneShotConfig(
                num_bins=num_bins, time_limit=time_limit,
                max_freq=max_freq, optimised=True,
            )
            solver = ClingconOneShotSolver(instance_path, cfg)
            t0 = time.perf_counter()
            result = solver.solve()
            wall = time.perf_counter() - t0
            _fill_oneshot(row, result, wall)

        elif solver_name == "naive_twostage":
            cfg = TwoStageNaiveConfig(
                time_limit=time_limit, max_freq=max_freq,
                weight=0, hetero_on=0, concentrated_on=0,
            )
            solver = NaiveTwoStageSolver(instance_path, cfg)
            t0 = time.perf_counter()
            result = solver.solve()
            wall = time.perf_counter() - t0
            _fill_twostage(row, result, wall)

        elif solver_name == "clingcon_twostage":
            cfg = TwoStageClingconConfig(
                time_limit=time_limit, max_freq=max_freq,
                weight=0, hetero_on=0, concentrated_on=0,
            )
            solver = ClingconTwoStageSolver(instance_path, cfg)
            t0 = time.perf_counter()
            result = solver.solve()
            wall = time.perf_counter() - t0
            _fill_twostage(row, result, wall)

        else:
            row.status = "ERROR"
            print(f"  unknown solver: {solver_name}")

    except Exception as e:
        row.status = "ERROR"
        print(f"  exception: {e}")

    return row


def _fill_oneshot(row: ScalabilityRow, result, wall_time: float) -> None:
    row.wall_time = round(wall_time, 3)
    if result is None:
        row.status = "TIMEOUT"
        return
    m = result.metadata
    row.satisfiable = bool(m.satisfiable) if m.satisfiable else (m.cost is not None)
    row.total_time = m.total_time
    row.ground_time = m.ground_time
    row.solve_time = m.solve_time
    row.cost = m.cost
    row.optimum = m.optimum
    row.choices = m.choices
    row.conflicts = m.conflicts
    row.restarts = m.restarts
    row.atoms = m.atoms
    row.status = "OK" if row.satisfiable else "TIMEOUT"


def _fill_twostage(row: ScalabilityRow, result, wall_time: float) -> None:
    row.wall_time = round(wall_time, 3)
    if result is None:
        row.status = "S1_UNSAT"
        return
    s1 = result.stage1.metadata
    s2 = result.stage2.metadata
    row.total_time = round(s1.total_time + s2.total_time, 3)
    row.ground_time = round(s1.ground_time + s2.ground_time, 3)
    row.solve_time = round(s1.solve_time + s2.solve_time, 3)
    row.cost = s1.cost
    row.optimum = bool(s1.optimum and s2.optimum)
    row.satisfiable = True
    row.choices = (s1.choices or 0) + (s2.choices or 0)
    row.conflicts = (s1.conflicts or 0) + (s2.conflicts or 0)
    row.restarts = (s1.restarts or 0) + (s2.restarts or 0)
    row.atoms = (s1.atoms or 0) + (s2.atoms or 0)
    row.s1_time = s1.total_time
    row.s2_time = s2.total_time
    row.s1_atoms = s1.atoms
    row.s2_atoms = s2.atoms
    row.s1_cost = s1.cost
    row.s2_cost = s2.cost
    row.s1_optimum = s1.optimum
    row.s2_optimum = s2.optimum
    row.status = "OK"


def write_raw_csv(rows: list[ScalabilityRow], path: Path) -> None:
    fieldnames = [f.name for f in fields(ScalabilityRow)]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _safe_avg(values) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 3)


def write_summary_csv(rows: list[ScalabilityRow], path: Path) -> None:
    groups: dict[tuple, list[ScalabilityRow]] = defaultdict(list)
    for row in rows:
        key = (row.solver, row.instance, row.instance_size, row.num_bins,
               row.time_limit)
        groups[key].append(row)

    fieldnames = [
        "solver", "encoding_family", "backend",
        "instance", "instance_size", "seed",
        "n_locations", "n_parts", "n_routes", "n_transports",
        "density", "capacity_tightness",
        "num_bins", "time_limit", "num_runs",
        "avg_wall_time", "avg_total_time",
        "avg_ground_time", "avg_solve_time",
        "cost", "optimum", "satisfiable",
        "avg_choices", "avg_conflicts", "avg_restarts", "atoms",
        "avg_s1_time", "avg_s2_time", "s1_atoms", "s2_atoms",
        "s1_cost", "s2_cost", "s1_optimum", "s2_optimum",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(groups.keys(),
                          key=lambda k: (SIZE_ORDER.index(k[2])
                                         if k[2] in SIZE_ORDER else 99,
                                         k[1], k[0])):
            group = groups[key]
            sat = [r for r in group if r.satisfiable]
            ref = sat[-1] if sat else group[0]
            n_sat = len(sat)
            writer.writerow({
                "solver": ref.solver,
                "encoding_family": ref.encoding_family,
                "backend": ref.backend,
                "instance": ref.instance,
                "instance_size": ref.instance_size,
                "seed": ref.seed,
                "n_locations": ref.n_locations,
                "n_parts": ref.n_parts,
                "n_routes": ref.n_routes,
                "n_transports": ref.n_transports,
                "density": ref.density,
                "capacity_tightness": ref.capacity_tightness,
                "num_bins": ref.num_bins,
                "time_limit": ref.time_limit,
                "num_runs": len(group),
                "avg_wall_time": _safe_avg([r.wall_time for r in sat]),
                "avg_total_time": _safe_avg([r.total_time for r in sat]),
                "avg_ground_time": _safe_avg([r.ground_time for r in sat]),
                "avg_solve_time": _safe_avg([r.solve_time for r in sat]),
                "cost": ref.cost if n_sat else None,
                "optimum": all(r.optimum for r in sat) if n_sat else False,
                "satisfiable": n_sat > 0,
                "avg_choices": _safe_avg([r.choices for r in sat]),
                "avg_conflicts": _safe_avg([r.conflicts for r in sat]),
                "avg_restarts": _safe_avg([r.restarts for r in sat]),
                "atoms": ref.atoms if n_sat else None,
                "avg_s1_time": _safe_avg([r.s1_time for r in sat]),
                "avg_s2_time": _safe_avg([r.s2_time for r in sat]),
                "s1_atoms": ref.s1_atoms if n_sat else None,
                "s2_atoms": ref.s2_atoms if n_sat else None,
                "s1_cost": ref.s1_cost if n_sat else None,
                "s2_cost": ref.s2_cost if n_sat else None,
                "s1_optimum": ref.s1_optimum if n_sat else None,
                "s2_optimum": ref.s2_optimum if n_sat else None,
            })


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Scalability: one-shot vs two-stage encodings",
    )
    p.add_argument("--instance-dir", type=Path, default=INSTANCE_DIR)
    p.add_argument("--instance-filter", type=str, default=None)
    p.add_argument("--sizes", nargs="+", default=SIZE_ORDER,
                   choices=SIZE_ORDER)
    p.add_argument("--solvers", nargs="+", default=SOLVER_NAMES,
                   choices=SOLVER_NAMES)
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--num-bins", type=int, default=3,
                   help="Bins for one-shot solvers (ignored by two-stage)")
    p.add_argument("--max-freq", type=int, default=20)
    for size, default in DEFAULT_TIME_LIMITS.items():
        p.add_argument(f"--time-{size}", type=int, default=default,
                       dest=f"time_{size}")
    p.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--tag", type=str, default=None,
                   help="Suffix added to output filenames")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    include = set(args.sizes)
    instances = discover_instances(args.instance_dir, include,
                                   args.instance_filter)
    time_limits = {s: getattr(args, f"time_{s}") for s in DEFAULT_TIME_LIMITS}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tag = f"_{args.tag}" if args.tag else ""
    raw_path = args.output_dir / f"scalability_raw{tag}.csv"
    summary_path = args.output_dir / f"scalability_summary{tag}.csv"

    total_runs = len(args.solvers) * len(instances) * args.reps
    print(f"Scalability: {len(args.solvers)} solvers x {len(instances)} "
          f"instances x {args.reps} reps = {total_runs} runs")
    print(f"  Solvers:     {args.solvers}")
    print(f"  Sizes:       {sorted(include, key=lambda s: SIZE_ORDER.index(s))}")
    print(f"  Time limits: {time_limits}")
    print(f"  Bins:        {args.num_bins} (one-shot only)")
    print(f"  Output:      {raw_path}")
    print()

    rows: list[ScalabilityRow] = []
    completed = 0
    for solver_name in args.solvers:
        print(f"{'=' * 60}")
        print(f"  Solver: {solver_name}")
        print(f"{'=' * 60}")
        for instance_path in instances:
            size = get_instance_size(instance_path)
            time_limit = time_limits.get(size, 120)
            for rep in range(1, args.reps + 1):
                completed += 1
                tag_str = f"[{completed}/{total_runs}]"
                print(
                    f"  {tag_str} {instance_path.stem} (t={time_limit}s) "
                    f"run {rep}/{args.reps}",
                    end=" ... ", flush=True,
                )
                row = run_single(
                    solver_name, instance_path,
                    num_bins=args.num_bins,
                    time_limit=time_limit,
                    max_freq=args.max_freq,
                )
                row.run = rep
                rows.append(row)
                if row.satisfiable:
                    mark = "OPT" if row.optimum else "SAT"
                    print(f"{mark} cost={row.cost} "
                          f"wall={row.wall_time}s")
                else:
                    print(row.status)

    write_raw_csv(rows, raw_path)
    write_summary_csv(rows, summary_path)

    print(f"\nDone! {len(rows)} runs completed.")
    print(f"  Raw:     {raw_path}")
    print(f"  Summary: {summary_path}")


if __name__ == "__main__":
    main()
