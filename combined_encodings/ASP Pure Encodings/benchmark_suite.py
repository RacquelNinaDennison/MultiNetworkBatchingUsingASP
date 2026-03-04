#!/usr/bin/env python3
"""Benchmark suite for all combined_encodings variants.

Runs each encoding across a range of bin counts and solver configurations,
capturing grounding time, solving time, and search statistics (atoms, rules,
choices, conflicts, restarts, and CSP variables/constraints for clingcon encodings).

Usage 
___
    # Run benchmarks with default settings (all encodings, bins=1 and 2, preset configs)
    uv run benchmark_suite.py 

    # Run benchmarks with custom settings
    uv run benchmark_suite.py run \
        --encodings encoding_route encoding_alternative \
        --bins 1 2 3 \
        --configs naive frumpy 
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import shlex
import statistics
import subprocess
import sys
from dataclasses import dataclass, fields
from pathlib import Path


HERE = Path(__file__).parent
ENCODINGS_DIR = HERE / "encodings"
DATA_DIR = HERE / "data"

# Default instance file (uses demandOffer predicate)
DEFAULT_INSTANCE = DATA_DIR / "instances.lp"


ENCODING_REGISTRY: dict[str, dict] = {
    "encoding_alternative": {
        "file": ENCODINGS_DIR / "encoding_alternative.lp",
        "solver": "clingcon",
        "instance": HERE.parent / "clingcon_approach" / "instances.lp",
    },
    "encoding_route": {
        "file": ENCODINGS_DIR / "encoding_route.lp",
        "solver": "clingo",
    },
    "flingo_encoding": {
        "file": ENCODINGS_DIR / "flingo_encoding.lp",
        "solver": "flingo",
    },
    "optimised_encoding_route": {
        "file": ENCODINGS_DIR / "optimised_encoding_route.lp",
        "solver": "clingo",
    },
}


PRESET_CONFIGS: dict[str, list[str]] = {
    "naive": [],
    "frumpy": ["--configuration=frumpy"],
    "jumpy": ["--configuration=jumpy"],
    "trendy": ["--configuration=trendy"],
    "handy": ["--configuration=handy"],
}


TIME_RE = re.compile(
    r"^Time\s*:\s*(?P<total>\d+(?:\.\d+)?)s\s*\(Solving:\s*(?P<solve>\d+(?:\.\d+)?)s",
    re.MULTILINE,
)
CPU_RE = re.compile(r"^CPU Time\s*:\s*(?P<cpu>\d+(?:\.\d+)?)s", re.MULTILINE)
RESULT_RE = re.compile(
    r"^(OPTIMUM FOUND|SATISFIABLE|UNSATISFIABLE|UNKNOWN)$", re.MULTILINE
)

# Search statistics
_STATS: dict[str, re.Pattern] = {
    "models":      re.compile(r"^Models\s*:\s*(?P<v>[0-9+]+)", re.MULTILINE),
    "atoms":       re.compile(r"^Atoms\s*:\s*(?P<v>\d+)", re.MULTILINE),
    "rules":       re.compile(r"^Rules\s*:\s*(?P<v>\d+)", re.MULTILINE),
    "choices":     re.compile(r"^Choices\s*:\s*(?P<v>\d+)", re.MULTILINE),
    "conflicts":   re.compile(r"^Conflicts\s*:\s*(?P<v>\d+)", re.MULTILINE),
    "restarts":    re.compile(r"^Restarts\s*:\s*(?P<v>\d+)", re.MULTILINE),
    "variables":   re.compile(r"^Variables\s*:\s*(?P<v>\d+)", re.MULTILINE),
    "constraints": re.compile(r"^Constraints\s*:\s*(?P<v>\d+)", re.MULTILINE),
}


# ---------------------------------------------------------------------------
# Data record
# ---------------------------------------------------------------------------
@dataclass
class RunRecord:
    timestamp: str
    encoding: str
    solver: str
    bins: int
    config: str
    config_args: str
    run_index: int
    exit_code: int
    result: str
    timed_out: bool
    # Timing
    total_time_s: float | None
    solving_time_s: float | None
    grounding_time_s: float | None
    cpu_time_s: float | None
    # Answer set info
    models: str
    # Grounded program statistics
    atoms: int | None
    rules: int | None
    # Search statistics
    choices: int | None
    conflicts: int | None
    restarts: int | None
    # CSP statistics (clingcon only)
    variables: int | None
    constraints: int | None
    # Run metadata
    command: str
    log_file: str


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def parse_metrics(output: str) -> dict:
    """Extract all timing and search metrics from solver output."""
    total = solve = grounding = cpu = None

    m = TIME_RE.search(output)
    if m:
        total = float(m.group("total"))
        solve = float(m.group("solve"))
        grounding = max(total - solve, 0.0)

    m = CPU_RE.search(output)
    if m:
        cpu = float(m.group("cpu"))

    stats: dict = {}
    for key, pattern in _STATS.items():
        match = pattern.search(output)
        if match:
            raw = match.group("v")
            stats[key] = raw if key == "models" else int(raw)
        else:
            stats[key] = "" if key == "models" else None

    return dict(
        total_time_s=total,
        solving_time_s=solve,
        grounding_time_s=grounding,
        cpu_time_s=cpu,
        **stats,
    )


def get_result(output: str) -> str:
    m = RESULT_RE.search(output)
    return m.group(1) if m else "UNKNOWN"


def write_csv(path: Path, rows: list[RunRecord]) -> None:
    if not rows:
        return
    fieldnames = [f.name for f in fields(RunRecord)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)



def _f(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f}"


def _fi(v: float | None) -> str:
    return "-" if v is None else f"{v:.0f}"


def _avg(records: list[RunRecord], attr: str) -> float | None:
    vals = [getattr(r, attr) for r in records if getattr(r, attr) is not None]
    return statistics.mean(vals) if vals else None


def summarize(rows: list[RunRecord]) -> list[dict[str, str]]:
    grouped: dict[tuple, list[RunRecord]] = {}
    for row in rows:
        grouped.setdefault((row.encoding, row.bins, row.config), []).append(row)

    summary: list[dict[str, str]] = []
    for (enc, bins, cfg), grp in sorted(grouped.items()):
        total_vals = [r.total_time_s for r in grp if r.total_time_s is not None]
        summary.append({
            "encoding":        enc,
            "bins":            str(bins),
            "config":          cfg,
            "runs":            str(len(grp)),
            "timeouts":        str(sum(1 for r in grp if r.timed_out)),
            "avg_total_s":     _f(_avg(grp, "total_time_s")),
            "avg_solving_s":   _f(_avg(grp, "solving_time_s")),
            "avg_grounding_s": _f(_avg(grp, "grounding_time_s")),
            "avg_atoms":       _fi(_avg(grp, "atoms")),
            "avg_rules":       _fi(_avg(grp, "rules")),
            "avg_choices":     _fi(_avg(grp, "choices")),
            "avg_conflicts":   _fi(_avg(grp, "conflicts")),
            "avg_restarts":    _fi(_avg(grp, "restarts")),
            "median_total_s":  _f(statistics.median(total_vals)) if total_vals else "-",
            "stdev_total_s":   _f(statistics.stdev(total_vals)) if len(total_vals) > 1 else "-",
        })
    return summary


def format_markdown_table(rows: list[dict[str, str]]) -> str:
    headers = [
        "encoding", "bins", "config", "runs", "timeouts",
        "avg_total_s", "avg_solving_s", "avg_grounding_s",
        "avg_atoms", "avg_rules", "avg_choices", "avg_conflicts", "avg_restarts",
        "median_total_s", "stdev_total_s",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row[h] for h in headers) + " |")
    return "\n".join(lines)



def parse_custom_config(spec: str) -> tuple[str, list[str]]:
    if "::" not in spec:
        raise ValueError(
            f"Invalid --custom-config '{spec}'. Expected format: name::arg string"
        )
    name, raw_args = spec.split("::", maxsplit=1)
    clean = name.strip()
    if not clean:
        raise ValueError(f"Empty name in --custom-config '{spec}'")
    return clean, shlex.split(raw_args)



def run_benchmarks(args: argparse.Namespace) -> int:
    enc_names: list[str] = args.encodings or list(ENCODING_REGISTRY)
    for name in enc_names:
        if name not in ENCODING_REGISTRY:
            raise ValueError(
                f"Unknown encoding '{name}'. Available: {sorted(ENCODING_REGISTRY)}"
            )

    configs: dict[str, list[str]] = {n: PRESET_CONFIGS[n] for n in args.configs}
    for custom in args.custom_config:
        name, cfg_args = parse_custom_config(custom)
        configs[name] = cfg_args

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / timestamp
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    rows: list[RunRecord] = []
    total_runs = len(enc_names) * len(args.bins) * len(configs) * args.runs
    run_counter = 0

    for enc_name in enc_names:
        enc_cfg = ENCODING_REGISTRY[enc_name]
        enc_file = enc_cfg["file"]
        instance_file = enc_cfg.get("instance", DEFAULT_INSTANCE)
        solver = enc_cfg["solver"]
        binary_map = {
            "clingcon": args.clingcon_binary,
            "flingo":   args.flingo_binary,
            "clingo":   args.clingo_binary,
        }
        binary = binary_map.get(solver, args.clingo_binary)

        if not Path(enc_file).exists():
            print(f"WARNING: encoding not found, skipping: {enc_file}", file=sys.stderr)
            continue
        if not Path(instance_file).exists():
            print(f"WARNING: instance not found, skipping: {instance_file}", file=sys.stderr)
            continue

        for bins in args.bins:
            for cfg_name, cfg_args in configs.items():
                for run_idx in range(1, args.runs + 1):
                    run_counter += 1
                    command = [
                        *shlex.split(binary),
                        str(enc_file),
                        str(instance_file),
                        "--stats=2",
                        "--quiet=1",
                        "-n", str(args.model_limit),
                        "-c", f"numBins={bins}",
                        *cfg_args,
                        *args.extra_args,
                    ]
                    if args.time_limit is not None:
                        command.extend(["--time-limit", str(args.time_limit)])

                    print(
                        f"[{run_counter}/{total_runs}] "
                        f"encoding={enc_name} bins={bins} "
                        f"config={cfg_name} run={run_idx}",
                        flush=True,
                    )

                    proc = subprocess.run(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                    )
                    merged = proc.stdout
                    if proc.stderr:
                        merged = f"{merged}\n{proc.stderr}"

                    log_file = (
                        logs_dir / f"{enc_name}_bins{bins}_{cfg_name}_run{run_idx}.log"
                    )
                    log_file.write_text(merged, encoding="utf-8")

                    metrics = parse_metrics(merged)
                    rows.append(
                        RunRecord(
                            timestamp=dt.datetime.now().isoformat(),
                            encoding=enc_name,
                            solver=solver,
                            bins=bins,
                            config=cfg_name,
                            config_args=" ".join(cfg_args),
                            run_index=run_idx,
                            exit_code=proc.returncode,
                            result=get_result(merged),
                            timed_out="TIME LIMIT" in merged,
                            command=shlex.join(command),
                            log_file=str(log_file),
                            **metrics,
                        )
                    )

    csv_path = output_dir / "results.csv"
    write_csv(csv_path, rows)
    summary_rows = summarize(rows)
    summary_md = format_markdown_table(summary_rows)
    summary_path = output_dir / "summary.md"
    summary_path.write_text(summary_md + "\n", encoding="utf-8")

    print("\nSummary")
    print(summary_md)
    print(f"\nSaved results CSV : {csv_path}")
    print(f"Saved summary     : {summary_path}")
    print(f"Saved run logs    : {logs_dir}")
    return 0


# ---------------------------------------------------------------------------
# Analyze existing CSV
# ---------------------------------------------------------------------------
def analyze_results(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows: list[RunRecord] = []
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            def _float(k: str) -> float | None:
                return float(raw[k]) if raw.get(k) else None

            def _int(k: str) -> int | None:
                return int(raw[k]) if raw.get(k) else None

            rows.append(
                RunRecord(
                    timestamp=raw["timestamp"],
                    encoding=raw["encoding"],
                    solver=raw.get("solver", ""),
                    bins=int(raw["bins"]),
                    config=raw["config"],
                    config_args=raw["config_args"],
                    run_index=int(raw["run_index"]),
                    exit_code=int(raw["exit_code"]),
                    result=raw["result"],
                    timed_out=raw["timed_out"].lower() == "true",
                    total_time_s=_float("total_time_s"),
                    solving_time_s=_float("solving_time_s"),
                    grounding_time_s=_float("grounding_time_s"),
                    cpu_time_s=_float("cpu_time_s"),
                    models=raw.get("models", ""),
                    atoms=_int("atoms"),
                    rules=_int("rules"),
                    choices=_int("choices"),
                    conflicts=_int("conflicts"),
                    restarts=_int("restarts"),
                    variables=_int("variables"),
                    constraints=_int("constraints"),
                    command=raw["command"],
                    log_file=raw["log_file"],
                )
            )

    summary_rows = summarize(rows)
    summary_md = format_markdown_table(summary_rows)
    print(summary_md)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(summary_md + "\n", encoding="utf-8")
        print(f"\nSaved summary: {out_path}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark all combined_encodings variants across bin counts "
            "and solver configurations, reporting grounding/solving time "
            "and search statistics."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- run ----------------------------------------------------------------
    run_p = subparsers.add_parser("run", help="Run the benchmark suite.")
    run_p.add_argument(
        "--encodings",
        nargs="+",
        choices=sorted(ENCODING_REGISTRY),
        default=None,
        help="Encodings to benchmark (default: all four).",
    )
    run_p.add_argument(
        "--output-dir",
        default="benchmark_results",
        help="Directory for timestamped result folders.",
    )
    run_p.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of repeated runs per (encoding, bins, config) combination.",
    )
    run_p.add_argument(
        "--bins",
        type=int,
        nargs="+",
        default=[1, 2],
        help="Bin counts to test (default: 1 2).",
    )
    run_p.add_argument(
        "--configs",
        nargs="+",
        choices=sorted(PRESET_CONFIGS),
        default=["naive", "frumpy", "jumpy", "trendy"],
        help="Preset solver configurations to benchmark.",
    )
    run_p.add_argument(
        "--custom-config",
        action="append",
        default=[],
        metavar="NAME::ARGS",
        help='Custom solver config, e.g. --custom-config "mycfg::--rand-freq=0.1"',
    )
    run_p.add_argument(
        "--model-limit",
        type=int,
        default=0,
        help="-n value passed to the solver (0 = all optimal).",
    )
    run_p.add_argument(
        "--time-limit",
        type=int,
        default=None,
        help="Optional --time-limit in seconds.",
    )
    run_p.add_argument(
        "--extra-args",
        nargs="*",
        default=[],
        help="Extra solver args applied to every run.",
    )
    run_p.add_argument("--clingcon-binary", default="uv run clingcon")
    run_p.add_argument("--clingo-binary", default="uv run clingo")
    run_p.add_argument("--flingo-binary", default="uv run flingo")
    run_p.set_defaults(func=run_benchmarks)

    # ---- analyze ------------------------------------------------------------
    analyze_p = subparsers.add_parser(
        "analyze", help="Analyse an existing results.csv."
    )
    analyze_p.add_argument("--csv", required=True, help="Path to results.csv.")
    analyze_p.add_argument(
        "--output", default=None, help="Optional output path for summary markdown."
    )
    analyze_p.set_defaults(func=analyze_results)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
