#!/usr/bin/env python3
"""Run and analyze clingcon runtime benchmarks for encoding_alternative.lp."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import shlex
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PRESET_CONFIGS: dict[str, list[str]] = {
    "naive": [],
    "frumpy": ["--configuration=frumpy"],
    "jumpy": ["--configuration=jumpy"],
    "trendy": ["--configuration=trendy"],
    "handy": ["--configuration=handy"],
}

TIME_RE = re.compile(
    r"^Time\s*:\s*(?P<total>\d+(?:\.\d+)?)s\s*"
    r"\(Solving:\s*(?P<solve>\d+(?:\.\d+)?)s",
    re.MULTILINE,
)
CPU_RE = re.compile(r"^CPU Time\s*:\s*(?P<cpu>\d+(?:\.\d+)?)s", re.MULTILINE)
RESULT_RE = re.compile(
    r"^(OPTIMUM FOUND|SATISFIABLE|UNSATISFIABLE|UNKNOWN)$", re.MULTILINE
)
MODELS_RE = re.compile(r"^Models\s*:\s*(?P<models>[0-9+]+)", re.MULTILINE)


@dataclass
class RunRecord:
    timestamp: str
    bins: int
    config: str
    config_args: str
    run_index: int
    exit_code: int
    result: str
    timed_out: bool
    total_time_s: float | None
    solving_time_s: float | None
    grounding_time_s: float | None
    cpu_time_s: float | None
    models: str
    command: str
    log_file: str


def parse_custom_config(spec: str) -> tuple[str, list[str]]:
    if "::" not in spec:
        raise ValueError(
            f"Invalid --custom-config '{spec}'. Expected format: name::arg string"
        )
    name, raw_args = spec.split("::", maxsplit=1)
    clean_name = name.strip()
    if not clean_name:
        raise ValueError(f"Invalid --custom-config '{spec}'. Name cannot be empty")
    return clean_name, shlex.split(raw_args)


def parse_metrics(output: str) -> tuple[float | None, float | None, float | None, float | None]:
    total = solve = grounding = cpu = None

    time_match = TIME_RE.search(output)
    if time_match:
        total = float(time_match.group("total"))
        solve = float(time_match.group("solve"))
        grounding = max(total - solve, 0.0)

    cpu_match = CPU_RE.search(output)
    if cpu_match:
        cpu = float(cpu_match.group("cpu"))

    return total, solve, grounding, cpu


def get_result(output: str) -> str:
    match = RESULT_RE.search(output)
    return match.group(1) if match else "UNKNOWN"


def get_models(output: str) -> str:
    match = MODELS_RE.search(output)
    return match.group("models") if match else ""


def write_csv(path: Path, rows: Iterable[RunRecord]) -> None:
    fieldnames = [
        "timestamp",
        "bins",
        "config",
        "config_args",
        "run_index",
        "exit_code",
        "result",
        "timed_out",
        "total_time_s",
        "solving_time_s",
        "grounding_time_s",
        "cpu_time_s",
        "models",
        "command",
        "log_file",
    ]
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def f(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def summarize(rows: list[RunRecord]) -> list[dict[str, str]]:
    grouped: dict[tuple[int, str], list[RunRecord]] = {}
    for row in rows:
        grouped.setdefault((row.bins, row.config), []).append(row)

    summary: list[dict[str, str]] = []
    for (bins, config), group_rows in sorted(grouped.items()):
        total_values = [r.total_time_s for r in group_rows if r.total_time_s is not None]
        solve_values = [r.solving_time_s for r in group_rows if r.solving_time_s is not None]
        ground_values = [r.grounding_time_s for r in group_rows if r.grounding_time_s is not None]
        timeouts = sum(1 for r in group_rows if r.timed_out)

        row = {
            "bins": str(bins),
            "config": config,
            "runs": str(len(group_rows)),
            "timeouts": str(timeouts),
            "avg_total_s": f(statistics.mean(total_values)) if total_values else "-",
            "avg_solving_s": f(statistics.mean(solve_values)) if solve_values else "-",
            "avg_grounding_s": f(statistics.mean(ground_values)) if ground_values else "-",
            "median_total_s": f(statistics.median(total_values)) if total_values else "-",
            "stdev_total_s": f(statistics.stdev(total_values)) if len(total_values) > 1 else "-",
        }
        summary.append(row)
    return summary


def format_markdown_table(rows: list[dict[str, str]]) -> str:
    headers = [
        "bins",
        "config",
        "runs",
        "timeouts",
        "avg_total_s",
        "avg_solving_s",
        "avg_grounding_s",
        "median_total_s",
        "stdev_total_s",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row[h] for h in headers) + " |")
    return "\n".join(lines)


def run_benchmarks(args: argparse.Namespace) -> int:
    if not Path(args.encoding).exists():
        raise FileNotFoundError(f"Encoding file not found: {args.encoding}")
    if not Path(args.instance).exists():
        raise FileNotFoundError(f"Instance file not found: {args.instance}")

    configs: dict[str, list[str]] = {name: PRESET_CONFIGS[name] for name in args.configs}
    for custom in args.custom_config:
        name, config_args = parse_custom_config(custom)
        configs[name] = config_args

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / timestamp
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    rows: list[RunRecord] = []
    total_runs = len(args.bins) * len(configs) * args.runs
    run_counter = 0

    for bins in args.bins:
        for config_name, config_args in configs.items():
            for run_index in range(1, args.runs + 1):
                run_counter += 1
                command = [
                    args.clingcon_binary,
                    args.encoding,
                    args.instance,
                    "--stats=2",
                    "--quiet=1",
                    "-n",
                    str(args.model_limit),
                    "-c",
                    f"numBins={bins}",
                    *config_args,
                    *args.extra_args,
                ]
                if args.time_limit is not None:
                    command.extend(["--time-limit", str(args.time_limit)])

                print(
                    f"[{run_counter}/{total_runs}] bins={bins} config={config_name} run={run_index}",
                    flush=True,
                )
                proc = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )

                merged_output = proc.stdout
                if proc.stderr:
                    merged_output = f"{merged_output}\n{proc.stderr}"

                log_file = (
                    logs_dir
                    / f"bins{bins}_{config_name}_run{run_index}.log"
                )
                log_file.write_text(merged_output, encoding="utf-8")

                total, solving, grounding, cpu = parse_metrics(merged_output)
                timed_out = "TIME LIMIT" in merged_output
                rows.append(
                    RunRecord(
                        timestamp=dt.datetime.now().isoformat(),
                        bins=bins,
                        config=config_name,
                        config_args=" ".join(config_args),
                        run_index=run_index,
                        exit_code=proc.returncode,
                        result=get_result(merged_output),
                        timed_out=timed_out,
                        total_time_s=total,
                        solving_time_s=solving,
                        grounding_time_s=grounding,
                        cpu_time_s=cpu,
                        models=get_models(merged_output),
                        command=shlex.join(command),
                        log_file=str(log_file),
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
    print(f"\nSaved results CSV: {csv_path}")
    print(f"Saved summary table: {summary_path}")
    print(f"Saved run logs: {logs_dir}")
    return 0


def analyze_results(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    rows: list[RunRecord] = []
    with csv_path.open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for raw in reader:
            rows.append(
                RunRecord(
                    timestamp=raw["timestamp"],
                    bins=int(raw["bins"]),
                    config=raw["config"],
                    config_args=raw["config_args"],
                    run_index=int(raw["run_index"]),
                    exit_code=int(raw["exit_code"]),
                    result=raw["result"],
                    timed_out=raw["timed_out"].lower() == "true",
                    total_time_s=float(raw["total_time_s"]) if raw["total_time_s"] else None,
                    solving_time_s=float(raw["solving_time_s"]) if raw["solving_time_s"] else None,
                    grounding_time_s=float(raw["grounding_time_s"]) if raw["grounding_time_s"] else None,
                    cpu_time_s=float(raw["cpu_time_s"]) if raw["cpu_time_s"] else None,
                    models=raw["models"],
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark clingcon grounding/solving time for different bin counts and solver configurations."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a benchmark suite.")
    run_parser.add_argument("--encoding", default="encoding_alternative.lp")
    run_parser.add_argument("--instance", default="instances.lp")
    run_parser.add_argument("--output-dir", default="benchmark_results")
    run_parser.add_argument("--runs", type=int, default=3)
    run_parser.add_argument("--bins", type=int, nargs="+", default=[1, 2])
    run_parser.add_argument(
        "--configs",
        nargs="+",
        choices=sorted(PRESET_CONFIGS),
        default=["naive", "frumpy", "jumpy", "trendy"],
        help="Preset solver configurations to benchmark.",
    )
    run_parser.add_argument(
        "--custom-config",
        action="append",
        default=[],
        metavar="NAME::ARGS",
        help='Custom config, e.g. --custom-config "mycfg::--rand-freq=0.1 --seed=7"',
    )
    run_parser.add_argument("--model-limit", type=int, default=0, help="-n value passed to clingcon.")
    run_parser.add_argument("--time-limit", type=int, default=None, help="Optional --time-limit seconds.")
    run_parser.add_argument(
        "--extra-args",
        nargs="*",
        default=[],
        help="Extra clingcon args applied to all runs.",
    )
    run_parser.add_argument("--clingcon-binary", default="clingcon")
    run_parser.set_defaults(func=run_benchmarks)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze an existing results.csv.")
    analyze_parser.add_argument("--csv", required=True)
    analyze_parser.add_argument("--output", default=None, help="Optional output markdown path.")
    analyze_parser.set_defaults(func=analyze_results)

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
