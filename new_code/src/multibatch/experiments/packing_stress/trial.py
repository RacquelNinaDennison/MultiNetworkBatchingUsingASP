"""Run ONE Stage-2 packing trial on a synthetic arc and emit a JSON result.

Designed to be launched as a subprocess (``python -m
multibatch.experiments.packing_stress.trial ...``) so that peak memory is
isolated per trial and an OOM / runaway grounding can't take down the sweep.

The result is printed to stdout as a single line prefixed with RESULT_PREFIX.
Everything else (solver chatter, errors) goes to stderr.
"""

from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
from pathlib import Path

from multibatch.models.config import TwoStageClingconConfig
from multibatch.solvers.twostage_clingcon import ENCODING_DIR, ClingconTwoStageSolver

from .synth import make_single_arc, min_feasible_freq

RESULT_PREFIX = "TRIAL_RESULT "


class _InjectedSolver(ClingconTwoStageSolver):
    """ClingconTwoStageSolver with a synthetic instance injected (no file parse).

    Reuses the real ``_solve_stage2`` / ``_build_stage2_facts`` / ``_extract_stage2``
    so the measured behaviour matches production exactly.
    """

    def __init__(self, instance, config: TwoStageClingconConfig):
        self.instance = instance
        self.instance_path = Path("<synthetic-arc>")
        self.config = config
        self.encoding_stage1 = ENCODING_DIR / "stage_1_clingcon_flow.lp"
        self.encoding_stage2 = ENCODING_DIR / "stage_2_packing.lp"


def _peak_rss_mb() -> float:
    """Peak resident set size in MB. ru_maxrss is bytes on macOS, KiB on Linux."""
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return round(rss / 1024 / 1024, 1)
    return round(rss / 1024, 1)


def _apply_mem_cap(mem_cap_mb: int) -> None:
    """Best-effort address-space cap so a runaway grounding aborts cleanly.

    RLIMIT_AS is honoured on Linux; on macOS it is frequently ignored, so this
    is a no-op safety net there (the driver's wall-clock timeout is the real
    guard on macOS).
    """
    if mem_cap_mb <= 0:
        return
    try:
        cap = mem_cap_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    except (ValueError, OSError):
        pass


def run_trial(args: argparse.Namespace) -> dict:
    freq = args.freq if args.freq > 0 else None
    instance, stage1 = make_single_arc(
        n_parts=args.n_parts,
        units_per_part=args.units_per_part,
        capacity=args.capacity,
        part_size=args.part_size,
        part_value=args.part_value,
        freq=freq,
        freq_slack=args.freq_slack,
    )
    eff_freq = stage1.route_freqs[0].frequency
    total_volume = args.n_parts * args.units_per_part * args.part_size

    config = TwoStageClingconConfig(
        hetero_on=args.hetero_on,
        concentrated_on=args.concentrated_on,
        threads=args.threads,
        time_limit=args.time_limit,
        configuration=(args.configuration or None),
    )
    solver = _InjectedSolver(instance, config)

    row: dict = {
        "config": args.config_name,
        "n_parts": args.n_parts,
        "units_per_part": args.units_per_part,
        "capacity": args.capacity,
        "part_size": args.part_size,
        "total_volume": total_volume,
        "freq": eff_freq,
        "min_freq": min_feasible_freq(args.n_parts, args.units_per_part, args.capacity, args.part_size),
        "hetero_on": args.hetero_on,
        "concentrated_on": args.concentrated_on,
        "time_limit": args.time_limit,
        "threads": args.threads,
    }

    t0 = time.perf_counter()
    result = solver._solve_stage2(stage1)
    wall = round(time.perf_counter() - t0, 3)

    row["wall_time"] = wall
    row["peak_mb"] = _peak_rss_mb()

    if result is None:
        # None == infeasible OR no model within the time limit.
        row["status"] = "infeasible_or_none"
        return row

    m = result.metadata
    # Anytime behaviour: for resilience we care more about how fast a good
    # packing appears than whether optimality is *proven*.
    traj = m.trajectory or []
    first_solution_time = traj[0]["time"] if traj else None
    best_solution_time = traj[-1]["time"] if traj else None
    row.update(
        status="ok",
        ground_time=m.ground_time,
        solve_time=m.solve_time,
        total_time=m.total_time,
        atoms=m.atoms,
        choices=m.choices,
        conflicts=m.conflicts,
        restarts=m.restarts,
        optimum=m.optimum,
        cost=m.cost,
        n_solutions=len(traj),
        first_solution_time=first_solution_time,
        best_solution_time=best_solution_time,
        trips_used=len(result.used_trips),
        mono_count=result.mono_count,
        concentrated_count=result.concentrated_count,
    )
    return row


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="One Stage-2 packing stress trial")
    p.add_argument("--n-parts", type=int, required=True)
    p.add_argument("--units-per-part", type=int, required=True)
    p.add_argument("--capacity", type=int, required=True)
    p.add_argument("--part-size", type=int, default=1)
    p.add_argument("--part-value", type=int, default=1)
    p.add_argument("--freq", type=int, default=0, help="0 = minimum feasible + slack")
    p.add_argument("--freq-slack", type=int, default=0)
    p.add_argument("--hetero-on", type=int, default=0)
    p.add_argument("--concentrated-on", type=int, default=0)
    p.add_argument("--config-name", type=str, default="custom")
    p.add_argument("--configuration", type=str, default="many",
                   help="clingo configuration preset (production uses 'many'); '' to disable")
    p.add_argument("--time-limit", type=int, default=60)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--mem-cap-mb", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _apply_mem_cap(args.mem_cap_mb)
    row = run_trial(args)
    print(RESULT_PREFIX + json.dumps(row), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
