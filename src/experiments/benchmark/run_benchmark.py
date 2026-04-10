#!/usr/bin/env python3
"""
run_benchmark.py — Benchmark grounding & solving time across all encodings.

Encoding configurations tested
-------------------------------
1. Naive one-shot          (clingo)   encoding/naive/encoding_route.lp
2. Naive optimised one-shot(clingcon) encoding/naive/optimised_encoding_route.lp
3. Clingcon one-shot       (clingcon) encoding/clingcon/clingcon_binpacking.lp
4. Two-stage naive         (clingo)   S1: twostage/naive/stage1_flow.lp
                                      S2: twostage/naive/stage2_packing.lp
5. Two-stage clingcon      (clingcon) S1: twostage/clingcon/stage_1_clingcon_flow.lp
                                      S2: twostage/clingcon/stage_2_packing.lp

Instances: layered_{small,medium,large}_seed{1,2,3}.lp

Usage
-----
    python experiments/benchmark/run_benchmark.py --time-limit 60
    python experiments/benchmark/run_benchmark.py --time-limit 300 -o results/full.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────

SRC = Path(__file__).resolve().parent.parent.parent  # src/
ENC = SRC / "encoding"
INST_DIR = SRC / "instances" / "generated"
INDUSTRY_INST_DIR = SRC / "instances" / "industry"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "results" / "benchmark_fullrun_industry.csv"


ONESHOT_CONFIGS = [
    {
        "name": "naive_oneshot",
        "label": "Naive (clingo)",
        "binary": "clingo",
        "files": [ENC / "naive" / "encoding_route.lp"],
        "extra_args": ["-t", "8", "--configuration=handy"],
    },
    {
        "name": "naive_optimised_oneshot",
        "label": "Naive optimised",
        "binary": "clingo",
        "files": [ENC / "naive" / "optimised_encoding_route.lp"],
        "extra_args": [],
    },
    {
        "name": "clingcon_oneshot",
        "label": "Clingcon one-shot",
        "binary": "clingcon",
        "files": [ENC / "clingcon" / "clingcon_binpacking.lp"],
        "extra_args": [],
    },
    {  "name": "naive_twostage",
        "label": "Naive two-stage",
        "binary": "clingcon",
        "files": [ENC / "twostage" / "naive" / "stage1_flow.lp" , ENC / "twostage" / "naive" / "stage2_packing.lp"],
        "extra_args": [],
    },
]

TWOSTAGE_CONFIGS = [
    {
        "name": "twostage_clingcon",
        "label": "Two-stage clingcon",
        "s1_binary": "clingcon",
        "s1_files": [ENC / "twostage" / "clingcon" / "stage_1_clingcon_flow.lp"],
        "s1_extra": ["-c", "max_freq=20"],
        "s2_binary": "clingcon",
        "s2_files": [ENC / "twostage" / "clingcon" / "stage_2_packing.lp"],
        "s2_extra": [],
        "bridge": "clingcon",
    },
]

SIZES = ["small", "medium", "large"]
SEEDS = [1, 2, 3]


def discover_instances(inst_dir: Path) -> list[dict]:
    """Find layered_{size}_seed{n}.lp instances, sorted by size then seed."""
    instances = []
    for size in SIZES:
        for seed in SEEDS:
            name = f"layered_{size}_seed{seed}.lp"
            path = inst_dir / name
            if path.exists():
                instances.append({
                    "path": path,
                    "name": name,
                    "size": size,
                    "seed": seed,
                })
    return instances


def discover_industry_instances(inst_dir: Path) -> list[dict]:
    """Find industry instances, sorted by size then seed."""
    instances = []
    for path in inst_dir.glob("*.lp"):
        instances.append({
            "path": path,
            "name": path.name,
        })
    return instances

def parse_solver_json(stdout: str) -> dict:
    """Parse clingcon/clingo JSON output into a timing/result dict.

    Returns dict with keys:
        result, cost, total_time, solve_time, ground_time,
        timed_out, atoms (list of str from last witness)
    """
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "result": "ERROR", "cost": None,
            "total_time": None, "solve_time": None, "ground_time": None,
            "timed_out": False, "atoms": [],
        }

    result_str = data.get("Result", "UNKNOWN")

    calls = data.get("Call", [])
    witnesses = calls[0].get("Witnesses", []) if calls else []
    last_atoms = witnesses[-1].get("Value", []) if witnesses else []
    last_costs = witnesses[-1].get("Costs", []) if witnesses else []

    timing = data.get("Time", {})
    total_t = timing.get("Total")
    solve_t = timing.get("Solve")
    ground_t = round(total_t - solve_t, 4) if total_t and solve_t else None

    cost = last_costs[0] if last_costs else None

    if "OPTIMUM" in result_str:
        result = "OPTIMUM"
    elif "SATISFIABLE" in result_str and "UN" not in result_str:
        result = "SATISFIABLE"
    elif "UNSATISFIABLE" in result_str:
        result = "UNSATISFIABLE"
    else:
        result = result_str

    timed_out = result == "SATISFIABLE"

    return {
        "result": result,
        "cost": cost,
        "total_time": total_t,
        "solve_time": solve_t,
        "ground_time": ground_t,
        "timed_out": timed_out,
        "atoms": last_atoms,
    }

def run_solver(
    binary: str,
    files: list[Path],
    instance: Path,
    time_limit: int,
    extra_args: list[str] | None = None,
) -> tuple[dict, float]:
    """Run a solver subprocess with --outf=2 and return (parsed, wall_time)."""
    cmd = [
        binary,
        *[str(f) for f in files],
        str(instance),
        f"--time-limit={time_limit}",
        "--outf=2",
        *(extra_args or []),
    ]

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=time_limit + 30,
        )
        wall = time.perf_counter() - t0
        parsed = parse_solver_json(proc.stdout)

        if proc.returncode not in (0, 10, 20, 30) and parsed["result"] == "ERROR":
            stderr_tail = proc.stderr.strip().splitlines()[-3:] if proc.stderr else []
            print(f"    stderr: {stderr_tail}")

    except FileNotFoundError:
        wall = time.perf_counter() - t0
        parsed = {
            "result": "BINARY_NOT_FOUND", "cost": None,
            "total_time": None, "solve_time": None, "ground_time": None,
            "timed_out": False, "atoms": [],
        }
    except subprocess.TimeoutExpired:
        wall = time.perf_counter() - t0
        parsed = {
            "result": "HARD_TIMEOUT", "cost": None,
            "total_time": None, "solve_time": None, "ground_time": None,
            "timed_out": True, "atoms": [],
        }

    return parsed, wall

_RE_NAIVE_LOAD = re.compile(r"load\((\d+),([^,]+),([^,]+),([^,]+),([^)]+)\)")
_RE_ROUTE_FREQ = re.compile(r"routeFreq\(([^,]+),([^,]+),([^,]+),(\d+),(\d+)\)")
_RE_CSP_LOAD = re.compile(r"__csp\(load\(([^,]+),([^,]+),([^,]+),([^)]+)\),(\d+)\)")
_RE_TRANSPORT_CAP = re.compile(r"transportCapacity\(([^,]+),(\d+)\)")


def build_naive_bridge(atoms: list[str]) -> str:
    """Extract load/routeFreq atoms from Stage 1 and format as .lp facts.

    Naive Stage 2 consumes the same atom names directly.
    """
    lines: list[str] = []
    for a in atoms:
        if a.startswith("load(") or a.startswith("routeFreq("):
            lines.append(f"{a}.")
    return "\n".join(lines)


def build_clingcon_bridge(atoms: list[str], instance_path: Path) -> str:
    """Convert clingcon Stage 1 output to Stage 2 input facts.

    Stage 1 outputs: __csp(load(F,T,TR,P),N) and routeFreq(F,T,TR,Freq,TotalCap)
    Stage 2 expects: totalLoad(F,T,TR,P,N) and activeRoute(F,T,TR,Freq,PerTripCap)
    """
    transport_cap: dict[str, int] = {}
    with open(instance_path) as f:
        for line in f:
            m = _RE_TRANSPORT_CAP.search(line)
            if m:
                transport_cap[m.group(1)] = int(m.group(2))

    lines: list[str] = []

    for a in atoms:
        m = _RE_CSP_LOAD.match(a)
        if m:
            fr, to, tr, p = m.group(1), m.group(2), m.group(3), m.group(4)
            n = int(m.group(5))
            if n > 0:
                lines.append(f"totalLoad({fr},{to},{tr},{p},{n}).")
            continue

        m = _RE_ROUTE_FREQ.match(a)
        if m:
            fr, to, tr = m.group(1), m.group(2), m.group(3)
            freq = int(m.group(4))
            per_trip_cap = transport_cap.get(tr, 0)
            lines.append(f"activeRoute({fr},{to},{tr},{freq},{per_trip_cap}).")

    return "\n".join(lines)


def bench_oneshot(
    config: dict,
    instance: dict,
    time_limit: int,
) -> dict:
    """Run a one-shot encoding and return a results row."""
    label = config["label"]
    inst_name = instance["name"]
    print(f"  [{label}] {inst_name} ... ", end="", flush=True)

    parsed, wall = run_solver(
        config["binary"],
        config["files"],
        instance["path"],
        time_limit,
        config.get("extra_args"),
    )

    cost_str = f"cost={parsed['cost']}" if parsed["cost"] is not None else "no model"
    print(f"{parsed['result']}  {cost_str}  "
          f"ground={parsed['ground_time']}s  solve={parsed['solve_time']}s  "
          f"wall={wall:.3f}s")

    return {
        "encoding":     config["name"],
        "instance":     inst_name,
        "size":         instance["size"],
        "seed":         instance["seed"],
        "stage":        "combined",
        "result":       parsed["result"],
        "cost":         parsed["cost"],
        "ground_time":  parsed["ground_time"],
        "solve_time":   parsed["solve_time"],
        "total_time":   parsed["total_time"],
        "wall_time":    round(wall, 3),
        "timed_out":    parsed["timed_out"],
    }



def bench_twostage_industry(
    config: dict,
    instance: dict,
    time_limit: int,
) -> list[dict]:
    """Run a two-stage pipeline and return result rows for S1, S2, and total."""
    label = config["label"]
    inst_name = instance["name"]

    # ── Stage 1 ──────────────────────────────────────────────────────
    print(f"  [{label} S1] {inst_name} ... ", end="", flush=True)

    s1_parsed, s1_wall = run_solver(
        config["s1_binary"],
        config["s1_files"],
        instance["path"],
        time_limit,
        config.get("s1_extra"),
    )

    s1_cost_str = (f"cost={s1_parsed['cost']}"
                   if s1_parsed["cost"] is not None else "no model")
    print(f"{s1_parsed['result']}  {s1_cost_str}  "
          f"ground={s1_parsed['ground_time']}s  solve={s1_parsed['solve_time']}s  "
          f"wall={s1_wall:.3f}s")

    s1_row = {
        "encoding":     config["name"],
        "instance":     inst_name,
        "size":         instance["size"],
        "seed":         instance["seed"],
        "stage":        "stage1",
        "result":       s1_parsed["result"],
        "cost":         s1_parsed["cost"],
        "ground_time":  s1_parsed["ground_time"],
        "solve_time":   s1_parsed["solve_time"],
        "total_time":   s1_parsed["total_time"],
        "wall_time":    round(s1_wall, 3),
        "timed_out":    s1_parsed["timed_out"],
    }

    if s1_parsed["result"] in ("UNSATISFIABLE", "HARD_TIMEOUT",
                                "BINARY_NOT_FOUND", "ERROR", "UNKNOWN"):
        print(f"  [{label} S2] {inst_name} ... SKIPPED (S1 failed)")
        return [s1_row]

    # ── Bridge ───────────────────────────────────────────────────────
    if config["bridge"] == "naive":
        bridge_facts = build_naive_bridge(s1_parsed["atoms"])
    else:
        bridge_facts = build_clingcon_bridge(s1_parsed["atoms"], instance["path"])

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".lp", prefix="bridge_", delete=False,
    )
    tmp.write(bridge_facts)
    tmp.close()
    bridge_path = Path(tmp.name)

    # ── Stage 2 ──────────────────────────────────────────────────────
    print(f"  [{label} S2] {inst_name} ... ", end="", flush=True)

    s2_files = list(config["s2_files"]) + [bridge_path]

    s2_parsed, s2_wall = run_solver(
        config["s2_binary"],
        s2_files,
        instance["path"],
        time_limit,
        config.get("s2_extra"),
    )

    bridge_path.unlink(missing_ok=True)

    s2_cost_str = (f"cost={s2_parsed['cost']}"
                   if s2_parsed["cost"] is not None else "no model")
    print(f"{s2_parsed['result']}  {s2_cost_str}  "
          f"ground={s2_parsed['ground_time']}s  solve={s2_parsed['solve_time']}s  "
          f"wall={s2_wall:.3f}s")

    s2_row = {
        "encoding":     config["name"],
        "instance":     inst_name,
        "size":         instance["size"],
        "seed":         instance["seed"],
        "stage":        "stage2",
        "result":       s2_parsed["result"],
        "cost":         s2_parsed["cost"],
        "ground_time":  s2_parsed["ground_time"],
        "solve_time":   s2_parsed["solve_time"],
        "total_time":   s2_parsed["total_time"],
        "wall_time":    round(s2_wall, 3),
        "timed_out":    s2_parsed["timed_out"],
    }

    # ── Combined row ─────────────────────────────────────────────────
    def _safe_add(a, b):
        if a is not None and b is not None:
            return round(a + b, 4)
        return None

    combined_row = {
        "encoding":     config["name"],
        "instance":     inst_name,
        "size":         instance["size"],
        "seed":         instance["seed"],
        "stage":        "combined",
        "result":       s2_parsed["result"],
        "cost":         s2_parsed["cost"],
        "ground_time":  _safe_add(s1_parsed["ground_time"], s2_parsed["ground_time"]),
        "solve_time":   _safe_add(s1_parsed["solve_time"], s2_parsed["solve_time"]),
        "total_time":   _safe_add(s1_parsed["total_time"], s2_parsed["total_time"]),
        "wall_time":    round(s1_wall + s2_wall, 3),
        "timed_out":    s1_parsed["timed_out"] or s2_parsed["timed_out"],
    }

    return [s1_row, s2_row, combined_row]


def bench_twostage(
    config: dict,
    instance: dict,
    time_limit: int,
) -> list[dict]:
    """Run a two-stage pipeline and return result rows for S1, S2, and total."""
    label = config["label"]
    inst_name = instance["name"]

    # ── Stage 1 ──────────────────────────────────────────────────────
    print(f"  [{label} S1] {inst_name} ... ", end="", flush=True)

    s1_parsed, s1_wall = run_solver(
        config["s1_binary"],
        config["s1_files"],
        instance["path"],
        time_limit,
        config.get("s1_extra"),
    )

    s1_cost_str = (f"cost={s1_parsed['cost']}"
                   if s1_parsed["cost"] is not None else "no model")
    print(f"{s1_parsed['result']}  {s1_cost_str}  "
          f"ground={s1_parsed['ground_time']}s  solve={s1_parsed['solve_time']}s  "
          f"wall={s1_wall:.3f}s")

    s1_row = {
        "encoding":     config["name"],
        "instance":     inst_name,
        "stage":        "stage1",
        "result":       s1_parsed["result"],
        "cost":         s1_parsed["cost"],
        "ground_time":  s1_parsed["ground_time"],
        "solve_time":   s1_parsed["solve_time"],
        "total_time":   s1_parsed["total_time"],
        "wall_time":    round(s1_wall, 3),
        "timed_out":    s1_parsed["timed_out"],
    }

    if s1_parsed["result"] in ("UNSATISFIABLE", "HARD_TIMEOUT",
                                "BINARY_NOT_FOUND", "ERROR", "UNKNOWN"):
        print(f"  [{label} S2] {inst_name} ... SKIPPED (S1 failed)")
        return [s1_row]

    # ── Bridge ───────────────────────────────────────────────────────
    if config["bridge"] == "naive":
        bridge_facts = build_naive_bridge(s1_parsed["atoms"])
    else:
        bridge_facts = build_clingcon_bridge(s1_parsed["atoms"], instance["path"])

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".lp", prefix="bridge_", delete=False,
    )
    tmp.write(bridge_facts)
    tmp.close()
    bridge_path = Path(tmp.name)

    # ── Stage 2 ──────────────────────────────────────────────────────
    print(f"  [{label} S2] {inst_name} ... ", end="", flush=True)

    s2_files = list(config["s2_files"]) + [bridge_path]

    s2_parsed, s2_wall = run_solver(
        config["s2_binary"],
        s2_files,
        instance["path"],
        time_limit,
        config.get("s2_extra"),
    )

    bridge_path.unlink(missing_ok=True)

    s2_cost_str = (f"cost={s2_parsed['cost']}"
                   if s2_parsed["cost"] is not None else "no model")
    print(f"{s2_parsed['result']}  {s2_cost_str}  "
          f"ground={s2_parsed['ground_time']}s  solve={s2_parsed['solve_time']}s  "
          f"wall={s2_wall:.3f}s")

    s2_row = {
        "encoding":     config["name"],
        "instance":     inst_name,
        "stage":        "stage2",
        "result":       s2_parsed["result"],
        "cost":         s2_parsed["cost"],
        "ground_time":  s2_parsed["ground_time"],
        "solve_time":   s2_parsed["solve_time"],
        "total_time":   s2_parsed["total_time"],
        "wall_time":    round(s2_wall, 3),
        "timed_out":    s2_parsed["timed_out"],
    }

    # ── Combined row ─────────────────────────────────────────────────
    def _safe_add(a, b):
        if a is not None and b is not None:
            return round(a + b, 4)
        return None

    combined_row = {
        "encoding":     config["name"],
        "instance":     inst_name,
        "stage":        "combined",
        "result":       s2_parsed["result"],
        "cost":         s2_parsed["cost"],
        "ground_time":  _safe_add(s1_parsed["ground_time"], s2_parsed["ground_time"]),
        "solve_time":   _safe_add(s1_parsed["solve_time"], s2_parsed["solve_time"]),
        "total_time":   _safe_add(s1_parsed["total_time"], s2_parsed["total_time"]),
        "wall_time":    round(s1_wall + s2_wall, 3),
        "timed_out":    s1_parsed["timed_out"] or s2_parsed["timed_out"],
    }

    return [s1_row, s2_row, combined_row]

# ─────────────────────────────────────────────────────────────────────────
# Summary printer
# ─────────────────────────────────────────────────────────────────────────

def print_summary(rows: list[dict]) -> None:
    """Print a compact summary table of combined results."""
    combined = [r for r in rows if r["stage"] == "combined"]
    if not combined:
        return

    print()
    print("═" * 95)
    print("  BENCHMARK SUMMARY  (combined stage rows only)")
    print("═" * 95)
    print(f"  {'Encoding':<28} {'Instance':<28} {'Result':<14} "
          f"{'Ground':>7} {'Solve':>7} {'Wall':>7} {'Cost':>8}")
    print("─" * 95)

    for r in combined:
        gt = f"{r['ground_time']:.3f}" if r["ground_time"] is not None else "—"
        st = f"{r['solve_time']:.3f}" if r["solve_time"] is not None else "—"
        wt = f"{r['wall_time']:.3f}"
        cost = str(r["cost"]) if r["cost"] is not None else "—"
        tag = " *" if r["timed_out"] else ""
        print(f"  {r['encoding']:<28} {r['instance']:<28} "
              f"{r['result'] + tag:<14} {gt:>7} {st:>7} {wt:>7} {cost:>8}")

    print("─" * 95)
    print("  * = timed out (best found, not proven optimal)")
    print()


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Benchmark grounding & solving time across all encodings."
    )
    p.add_argument(
        "--time-limit", "-t", type=int, default=60,
        help="Per-stage time limit in seconds (default: 60)",
    )
    p.add_argument(
        "--output", "-o", type=str, default=None,
        help=f"CSV output path (default: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--instances-dir", type=str, default=None,
        help=f"Instance directory (default: {INST_DIR})",
    )
    p.add_argument(
        "--sizes", nargs="+", default=SIZES,
        choices=SIZES,
        help="Instance sizes to benchmark (default: all)",
    )
    p.add_argument(
        "--seeds", nargs="+", type=int, default=SEEDS,
        help="Seeds to benchmark (default: 1 2 3)",
    )
    p.add_argument(
        "--encodings", nargs="+", default=None,
        help="Filter to specific encoding names (default: all)",
    )
    p.add_argument(
        "--run-twostage-industry", action="store_true", default=False,
        help="Run the two-stage industry encoding (default: False)",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    inst_dir = Path(args.instances_dir) if args.instances_dir else INST_DIR
    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)

    global SIZES, SEEDS
    SIZES = args.sizes
    SEEDS = args.seeds
    indusrty_instances = discover_industry_instances(INDUSTRY_INST_DIR)
    instances = discover_instances(inst_dir)
    if not instances:
        print(f"ERROR: no instances found in {inst_dir}", file=sys.stderr)
        return 1

    oneshots = ONESHOT_CONFIGS
    twostages = TWOSTAGE_CONFIGS
    if args.encodings:
        oneshots = [c for c in oneshots if c["name"] in args.encodings]
        twostages = [c for c in twostages if c["name"] in args.encodings]

    total_runs = (len(oneshots) + len(twostages)) * len(instances)

    print("═" * 65)
    print("  ENCODING BENCHMARK")
    print("═" * 65)
    print(f"  Time limit:  {args.time_limit}s per stage")
    print(f"  Instances:   {len(instances)}  ({', '.join(args.sizes)})")
    print(f"  Encodings:   {len(oneshots)} one-shot + {len(twostages)} two-stage")
    print(f"  Total runs:  ~{total_runs}")
    print(f"  Output:      {output_path}")
    print(f"  Started:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_rows: list[dict] = []
    if args.run_twostage_industry:
        for inst in indusrty_instances:
            for config in twostages:
                if(config["name"] == "twostage_clingcon"):
                    rows = bench_twostage(config, inst, args.time_limit)
                    all_rows.extend(rows)
    else:
        for inst in instances:
            print(f"\n{'─' * 65}")
            print(f"  Instance: {inst['name']}  (size={inst['size']}, seed={inst['seed']})")
            print(f"{'─' * 65}")

            for config in oneshots:
                row = bench_oneshot(config, inst, args.time_limit)
                all_rows.append(row)

            for config in twostages:
                rows = bench_twostage(config, inst, args.time_limit)
                all_rows.extend(rows)

    # ── Write CSV ────────────────────────────────────────────────────
    fieldnames = [
        "encoding", "instance", "size", "seed", "stage",
        "result", "cost", "ground_time", "solve_time",
        "total_time", "wall_time", "timed_out",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n  Results written to: {output_path}")

    print_summary(all_rows)

    return 0


if __name__ == "__main__":
    sys.exit(main())
