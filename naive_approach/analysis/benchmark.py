#!/usr/bin/env python3
"""
fixed_benchmark_runner.py

Benchmark a fixed suite of ASP instances across:
- multiple encodings
- multiple solver backends / presets
- multiple solver configurations

Outputs one flat CSV for easy analysis in pandas/Jupyter.
"""

from __future__ import annotations

import argparse
import csv
import glob
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


PRESETS: Dict[str, Dict[str, Any]] = {
    "clingo_default": {
        "executable": "clingo",
        "extra_args": [],
        "supports_stats": True,
    },
    "clingo_tweety": {
        "executable": "clingo",
        "extra_args": ["--configuration=tweety"],
        "supports_stats": True,
    },
    "clingo_usc": {
        "executable": "clingo",
        "extra_args": ["--opt-strategy=usc"],
        "supports_stats": True,
    },
     "clingo_handy": {
        "executable": "clingo",
        "extra_args": ["--configuration=handy"],
        "supports_stats": True,
    },
    "clingo_tweety_usc": {
        "executable": "clingo",
        "extra_args": ["--configuration=tweety", "--opt-strategy=usc"],
        "supports_stats": True,
    },
    "clingcon_default": {
        "executable": "clingcon",
        "extra_args": [],
        "supports_stats": True,
    },
    "clingcon_tweety": {
        "executable": "clingcon",
        "extra_args": ["--configuration=tweety"],
        "supports_stats": True,
    },
    "flingo_default": {
        "executable": "flingo",
        "extra_args": [],
        "supports_stats": True,
    },
}


def ensure_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, bytes):
        return x.decode("utf-8", errors="replace")
    return str(x)


def expand_patterns(patterns: List[str]) -> List[Path]:
    paths: List[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            for m in matches:
                p = Path(m).resolve()
                if p.is_file():
                    paths.append(p)
        else:
            p = Path(pattern).resolve()
            if p.is_file():
                paths.append(p)

    seen = set()
    out: List[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)

    return sorted(out)


def parse_time_block(text: str) -> Dict[str, Optional[float]]:
    total_time = None
    solve_time = None

    m = re.search(r"Time\s*:\s*([0-9]+(?:\.[0-9]+)?)s", text)
    if m:
        total_time = float(m.group(1))

    m2 = re.search(r"Solving:\s*([0-9]+(?:\.[0-9]+)?)s", text)
    if m2:
        solve_time = float(m2.group(1))

    ground_time = None
    if total_time is not None and solve_time is not None:
        ground_time = max(0.0, total_time - solve_time)

    return {
        "reported_total_time": total_time,
        "reported_solve_time": solve_time,
        "reported_ground_time": ground_time,
    }


def parse_stat_line(text: str, key: str) -> Optional[int]:
    m = re.search(rf"{re.escape(key)}\s*:\s*([0-9]+)", text, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def parse_status(text: str) -> str:
    upper = text.upper()
    if "OPTIMUM FOUND" in upper:
        return "OPTIMUM"
    if "UNSATISFIABLE" in upper:
        return "UNSAT"
    if "SATISFIABLE" in upper:
        return "SAT"
    if "UNKNOWN" in upper:
        return "UNKNOWN"
    return "NO_STATUS"


def parse_optimum(text: str) -> Optional[float]:
    m = re.search(r"Optimization\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)", text)
    if m:
        raw = m.group(1)
        try:
            return float(raw) if "." in raw else int(raw)
        except Exception:
            return None
    return None


def classify_axis(instance_name: str) -> str:
    lower = instance_name.lower()
    if lower.startswith("a"):
        return "vary_parts"
    if lower.startswith("b"):
        return "vary_transport_resources"
    if lower.startswith("c"):
        return "vary_locations"
    return "other"


def extract_step(instance_name: str) -> str:
    stem = Path(instance_name).stem
    return stem.split("_")[0]


def run_one(
    preset_name: str,
    preset: Dict[str, Any],
    encoding: Path,
    instance: Path,
    timeout: int,
    repeat_index: int,
) -> Dict[str, Any]:
    cmd = [preset["executable"], str(encoding), str(instance)]
    if preset.get("supports_stats", False):
        cmd.append("--stats=2")
    cmd.extend(preset.get("extra_args", []))

    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        ended = time.perf_counter()

        stdout = ensure_text(proc.stdout)
        stderr = ensure_text(proc.stderr)
        combined = stdout + "\n" + stderr

        times = parse_time_block(combined)
        status = parse_status(combined)

        atoms = parse_stat_line(combined, "Atoms")
        rules = parse_stat_line(combined, "Rules")
        choices = parse_stat_line(combined, "Choices")
        conflicts = parse_stat_line(combined, "Conflicts")
        restarts = parse_stat_line(combined, "Restarts")
        optimum = parse_optimum(combined)

        return {
            "preset": preset_name,
            "backend_executable": preset["executable"],
            "encoding": encoding.name,
            "encoding_path": str(encoding),
            "instance": instance.name,
            "instance_path": str(instance),
            "axis": classify_axis(instance.name),
            "step": extract_step(instance.name),
            "repeat": repeat_index,
            "command": " ".join(shlex.quote(c) for c in cmd),
            "status": status,
            "returncode": proc.returncode,
            "wall_time": round(ended - started, 6),
            "reported_total_time": times["reported_total_time"],
            "reported_ground_time": times["reported_ground_time"],
            "reported_solve_time": times["reported_solve_time"],
            "ground_time": times["reported_ground_time"],
            "solve_time": times["reported_solve_time"],
            "total_time": (
                times["reported_total_time"]
                if times["reported_total_time"] is not None
                else round(ended - started, 6)
            ),
            "atoms": atoms,
            "rules": rules,
            "choices": choices,
            "conflicts": conflicts,
            "restarts": restarts,
            "optimum": optimum,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
            "parse_ok": any(
                v is not None
                for v in [
                    times["reported_total_time"],
                    atoms,
                    rules,
                    choices,
                    conflicts,
                ]
            ),
        }

    except subprocess.TimeoutExpired as e:
        ended = time.perf_counter()

        stdout = ensure_text(e.stdout)
        stderr = ensure_text(e.stderr)
        combined = stdout + "\n" + stderr

        return {
            "preset": preset_name,
            "backend_executable": preset["executable"],
            "encoding": encoding.name,
            "encoding_path": str(encoding),
            "instance": instance.name,
            "instance_path": str(instance),
            "axis": classify_axis(instance.name),
            "step": extract_step(instance.name),
            "repeat": repeat_index,
            "command": " ".join(shlex.quote(c) for c in cmd),
            "status": "TIMEOUT",
            "returncode": None,
            "wall_time": round(ended - started, 6),
            "reported_total_time": None,
            "reported_ground_time": None,
            "reported_solve_time": None,
            "ground_time": None,
            "solve_time": None,
            "total_time": round(ended - started, 6),
            "atoms": None,
            "rules": None,
            "choices": None,
            "conflicts": None,
            "restarts": None,
            "optimum": None,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
            "parse_ok": False,
        }


def summarize(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in rows:
        key = (row["encoding"], row["preset"], row["axis"], row["instance"])
        groups.setdefault(key, []).append(row)

    summary_rows: List[Dict[str, Any]] = []

    def mean(vals: List[Optional[float]]) -> Optional[float]:
        nums = [v for v in vals if isinstance(v, (int, float))]
        if not nums:
            return None
        return round(sum(nums) / len(nums), 6)

    def std(vals: List[Optional[float]]) -> Optional[float]:
        nums = [v for v in vals if isinstance(v, (int, float))]
        if len(nums) < 2:
            return 0.0 if nums else None
        m = sum(nums) / len(nums)
        return round((sum((v - m) ** 2 for v in nums) / (len(nums) - 1)) ** 0.5, 6)

    for (encoding, preset, axis, instance), items in sorted(groups.items()):
        n = len(items)
        summary_rows.append({
            "encoding": encoding,
            "preset": preset,
            "axis": axis,
            "instance": instance,
            "runs": n,
            "sat_rate": round(sum(1 for x in items if x["status"] in ("SAT", "OPTIMUM")) / n, 6),
            "unsat_rate": round(sum(1 for x in items if x["status"] == "UNSAT") / n, 6),
            "timeout_rate": round(sum(1 for x in items if x["status"] == "TIMEOUT") / n, 6),
            "ground_time_mean": mean([x["ground_time"] for x in items]),
            "ground_time_std": std([x["ground_time"] for x in items]),
            "solve_time_mean": mean([x["solve_time"] for x in items]),
            "solve_time_std": std([x["solve_time"] for x in items]),
            "total_time_mean": mean([x["total_time"] for x in items]),
            "total_time_std": std([x["total_time"] for x in items]),
            "atoms_mean": mean([x["atoms"] for x in items]),
            "rules_mean": mean([x["rules"] for x in items]),
            "choices_mean": mean([x["choices"] for x in items]),
            "conflicts_mean": mean([x["conflicts"] for x in items]),
            "restarts_mean": mean([x["restarts"] for x in items]),
        })

    return summary_rows


def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames: List[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark fixed ASP instance suite across backends and presets."
    )
    parser.add_argument(
        "--encodings",
        nargs="+",
        required=True,
        help="One or more encoding files, e.g. encoding_route.lp encoding_clingcon.lp",
    )
    parser.add_argument(
        "--instances",
        nargs="+",
        default=["fixed_benchmark_suite/*.lp"],
        help="One or more instance files or glob patterns. Default: fixed_benchmark_suite/*.lp",
    )
    parser.add_argument(
        "--presets",
        nargs="+",
        default=["clingo_default", "clingo_tweety", "clingo_usc"],
        help=f"Preset names. Available: {', '.join(sorted(PRESETS))}",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-run timeout in seconds. Default: 120",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Repeat each experiment this many times.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="fixed_benchmark_results.csv",
        help="Raw CSV output path.",
    )
    parser.add_argument(
        "--summary-output",
        type=str,
        default="fixed_benchmark_summary.csv",
        help="Summary CSV output path.",
    )
    args = parser.parse_args()

    encodings = [Path(p).resolve() for p in args.encodings]
    for e in encodings:
        if not e.is_file():
            print(f"ERROR: encoding not found: {e}")
            return 1

    instances = expand_patterns(args.instances)
    if not instances:
        print("ERROR: no instance files found.")
        return 1

    chosen_presets = []
    for name in args.presets:
        if name not in PRESETS:
            print(f"ERROR: unknown preset '{name}'.")
            return 1
        chosen_presets.append((name, PRESETS[name]))

    rows: List[Dict[str, Any]] = []

    print("=" * 100)
    print("FIXED BENCHMARK RUN")
    print("=" * 100)
    print(f"Encodings : {[e.name for e in encodings]}")
    print(f"Instances : {[i.name for i in instances]}")
    print(f"Presets   : {[p[0] for p in chosen_presets]}")
    print(f"Timeout   : {args.timeout}s")
    print(f"Repeats   : {args.repeats}")
    print("-" * 100)

    for encoding in encodings:
        for preset_name, preset in chosen_presets:
            for instance in instances:
                for repeat in range(1, args.repeats + 1):
                    row = run_one(
                        preset_name=preset_name,
                        preset=preset,
                        encoding=encoding,
                        instance=instance,
                        timeout=args.timeout,
                        repeat_index=repeat,
                    )
                    rows.append(row)

                    gt = row["ground_time"]
                    st = row["solve_time"]
                    print(
                        f"{encoding.name:<24} "
                        f"{preset_name:<20} "
                        f"{instance.name:<28} "
                        f"{row['status']:<8} "
                        f"G={gt if gt is not None else '-'} "
                        f"S={st if st is not None else '-'}"
                    )

    raw_path = Path(args.output).resolve()
    summary_path = Path(args.summary_output).resolve()

    write_csv(rows, raw_path)
    write_csv(summarize(rows), summary_path)

    print("-" * 100)
    print(f"Raw CSV     : {raw_path}")
    print(f"Summary CSV : {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())