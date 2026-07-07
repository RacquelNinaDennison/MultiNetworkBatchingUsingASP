"""Driver for the per-arc Stage-2 packing stress test.

Sweeps the three scaling axes (parts / trips / load) in isolation from a common
baseline arc, running each cell at the cheapest config (`baseline`) and the
hardest (`full`). Each trial runs in its own subprocess with a wall-clock
timeout, so a runaway grounding is killed cleanly and recorded as a timeout
rather than hanging the sweep.

Usage:
    uv run python -m multibatch.experiments.packing_stress.sweep \
        --axes parts trips load --timeout 60 -o results/stress.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from .trial import RESULT_PREFIX

# src/ dir (parents: packing_stress→experiments→multibatch→src). Injected as
# PYTHONPATH for child trials so they import `multibatch` even if a `uv sync`
# re-hides the venv and breaks the editable .pth (see project memory).
_SRC_DIR = str(Path(__file__).resolve().parents[3])


def _child_env() -> dict:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _SRC_DIR + (os.pathsep + existing if existing else "")
    return env

# Baseline arc — roughly an "industrylite" single lane. Other axes perturb one
# dimension at a time while holding the derived trip count near BASE_FREQ.
BASE_PARTS = 4
BASE_UNITS = 20
BASE_SIZE = 1
BASE_FREQ = 8

# (config_name, hetero_on, concentrated_on): the floor and the hardest case.
CONFIGS = [("baseline", 0, 0), ("full", 1, 1)]

CSV_FIELDS = [
    "axis", "config", "n_parts", "units_per_part", "capacity", "part_size",
    "total_volume", "freq", "min_freq", "hetero_on", "concentrated_on",
    "time_limit", "threads", "configuration", "status", "wall_time", "peak_mb",
    "ground_time", "solve_time", "total_time", "atoms", "choices", "conflicts",
    "restarts", "optimum", "cost", "n_solutions", "first_solution_time",
    "best_solution_time", "trips_used", "mono_count",
    "concentrated_count", "returncode", "note",
]


def _cap_for_freq(n_parts: int, units: int, size: int, target_freq: int) -> int:
    """Per-trip capacity that yields ≈ target_freq trips for this load."""
    return max(size, math.ceil(n_parts * units * size / target_freq))


def parts_axis(values: list[int]) -> list[dict]:
    """Grow part types; scale capacity to hold trips ≈ BASE_FREQ."""
    cells = []
    for p in values:
        cap = _cap_for_freq(p, BASE_UNITS, BASE_SIZE, BASE_FREQ)
        cells.append({"n_parts": p, "units_per_part": BASE_UNITS,
                      "capacity": cap, "part_size": BASE_SIZE, "freq": 0})
    return cells


def trips_axis(values: list[int]) -> list[dict]:
    """Grow trip count; hold parts at BASE_PARTS, size load to hit target freq."""
    cells = []
    for f in values:
        units = max(1, math.ceil(f * 10 / BASE_PARTS))  # capacity fixed at 10
        cells.append({"n_parts": BASE_PARTS, "units_per_part": units,
                      "capacity": 10, "part_size": BASE_SIZE, "freq": f})
    return cells


def load_axis(values: list[int]) -> list[dict]:
    """Grow per-part units (CSP domain 0..N); hold trips ≈ BASE_FREQ and parts."""
    cells = []
    for n in values:
        cap = _cap_for_freq(BASE_PARTS, n, BASE_SIZE, BASE_FREQ)
        cells.append({"n_parts": BASE_PARTS, "units_per_part": n,
                      "capacity": cap, "part_size": BASE_SIZE, "freq": 0})
    return cells


AXES = {
    "parts": (parts_axis, [2, 4, 8, 16, 32, 64]),
    "trips": (trips_axis, [4, 8, 16, 32, 64, 128, 256]),
    "load": (load_axis, [10, 50, 100, 500, 1000, 5000]),
}


def run_cell(cell: dict, cfg: tuple[str, int, int], axis: str,
             timeout: int, time_limit: int, threads: int, mem_cap_mb: int,
             configuration: str) -> dict:
    name, hetero, conc = cfg
    cmd = [
        sys.executable, "-m", "multibatch.experiments.packing_stress.trial",
        "--n-parts", str(cell["n_parts"]),
        "--units-per-part", str(cell["units_per_part"]),
        "--capacity", str(cell["capacity"]),
        "--part-size", str(cell["part_size"]),
        "--freq", str(cell["freq"]),
        "--hetero-on", str(hetero),
        "--concentrated-on", str(conc),
        "--config-name", name,
        "--configuration", configuration,
        "--time-limit", str(time_limit),
        "--threads", str(threads),
        "--mem-cap-mb", str(mem_cap_mb),
    ]
    base = {"axis": axis, "config": name, "returncode": None, "note": ""}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout, env=_child_env())
    except subprocess.TimeoutExpired:
        return {**base, "status": "timeout", "n_parts": cell["n_parts"],
                "units_per_part": cell["units_per_part"], "capacity": cell["capacity"],
                "part_size": cell["part_size"], "freq": cell["freq"],
                "hetero_on": hetero, "concentrated_on": conc, "time_limit": time_limit,
                "threads": threads}

    line = next((ln for ln in reversed(proc.stdout.splitlines())
                 if ln.startswith(RESULT_PREFIX)), None)
    if line is None:
        # No result line => the trial process died (likely OOM / killed).
        return {**base, "status": "crash", "returncode": proc.returncode,
                "note": proc.stderr.strip().splitlines()[-1][:200] if proc.stderr.strip() else "",
                "n_parts": cell["n_parts"], "units_per_part": cell["units_per_part"],
                "capacity": cell["capacity"], "part_size": cell["part_size"],
                "freq": cell["freq"], "hetero_on": hetero, "concentrated_on": conc,
                "time_limit": time_limit, "threads": threads}

    row = json.loads(line[len(RESULT_PREFIX):])
    row.update(base)
    row["returncode"] = proc.returncode
    return row


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Per-arc Stage-2 packing stress sweep")
    p.add_argument("--axes", nargs="+", default=["parts", "trips", "load"],
                   choices=list(AXES))
    p.add_argument("--configs", nargs="+", default=["baseline", "full"],
                   choices=[c[0] for c in CONFIGS])
    p.add_argument("--timeout", type=int, default=90,
                   help="Hard wall-clock kill per trial (seconds)")
    p.add_argument("--time-limit", type=int, default=60,
                   help="Solver's own search time limit (seconds)")
    p.add_argument("--configuration", type=str, default="many",
                   help="clingo configuration preset (production uses 'many')")
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--mem-cap-mb", type=int, default=0)
    p.add_argument("-o", "--out", type=str,
                   default=str(Path(__file__).resolve().parent / "results" / "stress.csv"))
    args = p.parse_args(argv)

    configs = [c for c in CONFIGS if c[0] in args.configs]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    print(f"Writing to {out_path}\n")
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for axis in args.axes:
            builder, values = AXES[axis]
            cells = builder(values)
            print(f"── axis={axis}  values={values}")
            for cell in cells:
                for cfg in configs:
                    t0 = time.perf_counter()
                    row = run_cell(cell, cfg, axis, args.timeout,
                                   args.time_limit, args.threads, args.mem_cap_mb,
                                   args.configuration)
                    writer.writerow(row)
                    fh.flush()
                    rows.append(row)
                    dt = time.perf_counter() - t0
                    print(
                        f"   {cfg[0]:8s} parts={cell['n_parts']:<4} "
                        f"freq={row.get('freq', cell['freq']):<5} "
                        f"units={cell['units_per_part']:<6} cap={cell['capacity']:<6} "
                        f"-> {row['status']:18s} "
                        f"grnd={row.get('ground_time', '?')!s:>7} "
                        f"solv={row.get('solve_time', '?')!s:>7} "
                        f"peak={row.get('peak_mb', '?')!s:>7}MB "
                        f"atoms={row.get('atoms', '?')!s:>8}  ({dt:.1f}s)"
                    )
    print(f"\nDone. {len(rows)} trials -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
