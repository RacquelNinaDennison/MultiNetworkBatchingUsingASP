#!/usr/bin/env python3
"""
experiment_benchmark.py – Compare encoding_route vs optimised_encoding
across five experimental series using the Clingo Python API.

Metrics collected per run
--------------------------
  atoms, rules          grounded program size
  choices, conflicts,   search statistics
  restarts
  ground_time_s,        timing breakdown
  solve_time_s,
  total_time_s
  result                OPTIMUM | SAT_TIMEOUT | UNSAT | TIMEOUT | ERROR

Series
------
  A  Location scaling               L ∈ {4,6,8,10}, P=1, TR=2, bins=1
  B  Product scaling                L=6, P ∈ {1,2,3}, TR=2, bins=1
  C  Transport scaling              L=6, P=2, TR ∈ {1,2,3}, bins=1
  D  Bin scaling                    L=6, P=2, TR=2, bins ∈ {1,2,3}
  E  Capacity tightness             L=6, P=2, TR=2, bins=1 (tight/medium/loose)
  F  Location × bin scaling         same instances as A, bins ∈ {1,2,3}
  G  Product × bin scaling          same instances as B, bins ∈ {1,2,3}
  H  Transport × bin scaling        same instances as C, bins ∈ {1,2,3}
  I  Capacity tightness × bins      same instances as E, bins ∈ {1,2,3}

Usage
-----
    uv run experiment_benchmark.py                         # all series
    uv run experiment_benchmark.py --series A B C          # subset
    uv run experiment_benchmark.py --series F G H I        # cross-bin series only
    uv run experiment_benchmark.py --time-limit 30         # shorter timeout
    uv run experiment_benchmark.py --output-dir my_results
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

import clingo
import openpyxl
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ── paths ─────────────────────────────────────────────────────────────────────
HERE     = Path(__file__).parent
DATA_DIR = HERE / "data"

ENCODINGS: dict[str, Path] = {
    "encoding_route":     HERE / "encodings" / "encoding_route.lp",
    "optimised_encoding": HERE / "encodings" / "optimised_encoding.lp",
}

# Series configuration
#   series_dir : subdirectory under DATA_DIR containing the .lp instances
#   bins       : list of bin counts to test (each becomes a separate run)
SERIES_CONFIG: dict[str, dict] = {
    "A": {
        "description": "Location scaling  (P=1, TR=2, bins=1)",
        "series_dir":  "series_A",
        "bins":        [1],
    },
    "B": {
        "description": "Product scaling  (L=6, TR=2, bins=1)",
        "series_dir":  "series_B",
        "bins":        [1],
    },
    "C": {
        "description": "Transport type scaling  (L=6, P=2, bins=1)",
        "series_dir":  "series_C",
        "bins":        [1],
    },
    "D": {
        "description": "Bin scaling  (L=6, P=2, TR=2, bins=1–3)",
        "series_dir":  "series_D",
        "bins":        [1, 2, 3],
    },
    "E": {
        "description": "Capacity tightness  (L=6, P=2, TR=2, bins=1)",
        "series_dir":  "series_E",
        "bins":        [1],
    },
    # Cross-bin series: same instances as A–C, E but bins ∈ {1,2,3}
    "F": {
        "description": "Location × bin scaling  (P=1, TR=2, bins=1–3)",
        "series_dir":  "series_A",
        "bins":        [1, 2, 3],
    },
    "G": {
        "description": "Product × bin scaling  (L=6, TR=2, bins=1–3)",
        "series_dir":  "series_B",
        "bins":        [1, 2, 3],
    },
    "H": {
        "description": "Transport × bin scaling  (L=6, P=2, bins=1–3)",
        "series_dir":  "series_C",
        "bins":        [1, 2, 3],
    },
    "I": {
        "description": "Capacity tightness × bin scaling  (L=6, P=2, TR=2, bins=1–3)",
        "series_dir":  "series_E",
        "bins":        [1, 2, 3],
    },
}


# ── result record ─────────────────────────────────────────────────────────────

@dataclass
class RunRecord:
    timestamp:     str
    series:        str
    instance:      str
    encoding:      str
    bins:          int
    result:        str          # OPTIMUM | SAT_TIMEOUT | UNSAT | TIMEOUT | ERROR
    # Grounded program
    atoms:         Optional[int]
    rules:         Optional[int]
    # Search statistics
    choices:       Optional[int]
    conflicts:     Optional[int]
    restarts:      Optional[int]
    # Timing (seconds)
    ground_time_s: Optional[float]
    solve_time_s:  Optional[float]
    total_time_s:  Optional[float]


# ── statistics helpers ────────────────────────────────────────────────────────

def _get(d: dict, *keys, default=None):
    """Safely traverse a nested dict, returning default on any missing key."""
    v = d
    for k in keys:
        if not isinstance(v, dict):
            return default
        v = v.get(k, default)
        if v is default:
            return default
    return v


def _extract_stats(ctl: clingo.Control, wall_ground: float, wall_total: float) -> dict:
    """Pull grounding/search/timing stats from ctl.statistics."""
    s = ctl.statistics

    # Grounded program size
    atoms = _get(s, "problem", "lp", "atoms")
    rules = _get(s, "problem", "lp", "rules")

    # Search stats — clingo reports these per solver thread; sum for totals
    solvers_raw = _get(s, "solving", "solvers", default={})
    if isinstance(solvers_raw, list):
        choices   = sum(int(_get(sv, "choices",   default=0)) for sv in solvers_raw)
        conflicts = sum(int(_get(sv, "conflicts",  default=0)) for sv in solvers_raw)
        restarts  = sum(int(_get(sv, "restarts",   default=0)) for sv in solvers_raw)
    else:
        choices   = _get(solvers_raw, "choices",   default=None)
        conflicts = _get(solvers_raw, "conflicts",  default=None)
        restarts  = _get(solvers_raw, "restarts",   default=None)

    # Timing — prefer clingo's internal counters, fall back to wall-clock
    ground_t = _get(s, "times", "ground") or wall_ground
    solve_t  = _get(s, "times", "solve")
    total_t  = _get(s, "times", "total")  or wall_total

    return dict(
        atoms         = int(atoms)         if atoms    is not None else None,
        rules         = int(rules)         if rules    is not None else None,
        choices       = int(choices)       if choices  is not None else None,
        conflicts     = int(conflicts)     if conflicts is not None else None,
        restarts      = int(restarts)      if restarts is not None else None,
        ground_time_s = round(float(ground_t), 4),
        solve_time_s  = round(float(solve_t),  4) if solve_t is not None else None,
        total_time_s  = round(float(total_t),  4),
    )


# ── solver ────────────────────────────────────────────────────────────────────

def run_instance(
    encoding_path: Path,
    instance_path: Path,
    num_bins:      int,
    time_limit:    int,
) -> dict:
    """
    Solve one (encoding, instance, bins) combination and return a stats dict.

    bins(1..num_bins) is injected inline so that encoding_route.lp (which
    has no bins rule) and optimised_encoding.lp (which generates bins via
    bins(1..numBins)) both see the identical set {1..num_bins}.
    """
    ctl = clingo.Control([
        "--stats=2",
        f"-c", f"numBins={num_bins}",
    ])

    ctl.load(str(encoding_path))
    ctl.load(str(instance_path))

    # Provide bins for encoding_route (has no bins rule);
    # optimised_encoding's bins(1..numBins) gives the same set — union is identical.
    ctl.add("base", [], f"bins(1..{num_bins}).")

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    wall_ground = time.perf_counter() - t0

    has_model      = False
    optimum_proven = False

    with ctl.solve(yield_=True) as handle:
        for model in handle:
            has_model = True
            if model.optimality_proven:
                optimum_proven = True
        solve_result = handle.get()

    wall_total = time.perf_counter() - t0

    # Classify result
    interrupted = getattr(solve_result, "interrupted", not solve_result.exhausted)
    if solve_result.satisfiable is False:
        result = "UNSAT"
    elif optimum_proven:
        result = "OPTIMUM"
    elif has_model and interrupted:
        result = "SAT_TIMEOUT"
    elif interrupted:
        result = "TIMEOUT"
    else:
        result = "SATISFIABLE"   # model found, search exhausted but no optimality flag

    stats = _extract_stats(ctl, wall_ground, wall_total)
    stats["result"] = result
    return stats


# ── benchmark runner ──────────────────────────────────────────────────────────

def run_benchmarks(
    series_names: list[str],
    time_limit:   int,
    output_dir:   Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[RunRecord] = []
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Count total runs upfront for progress display
    total_runs = 0
    for s in series_names:
        cfg  = SERIES_CONFIG[s]
        insts = list((DATA_DIR / cfg["series_dir"]).glob("*.lp"))
        total_runs += len(insts) * len(ENCODINGS) * len(cfg["bins"])

    run_n = 0

    for series in series_names:
        cfg       = SERIES_CONFIG[series]
        series_dir = DATA_DIR / cfg["series_dir"]
        instances  = sorted(series_dir.glob("*.lp"))

        if not instances:
            print(f"WARNING: no instances in {series_dir} — did you run generate_instances.py?",
                  file=sys.stderr)
            continue

        print(f"\n{'─'*70}")
        print(f"Series {series}: {cfg['description']}")
        print(f"{'─'*70}")

        for inst_path in instances:
            for enc_name, enc_path in ENCODINGS.items():
                for bins in cfg["bins"]:
                    run_n += 1
                    tag = (f"[{run_n:>3}/{total_runs}] "
                           f"enc={enc_name:<22} bins={bins} "
                           f"inst={inst_path.name}")
                    print(f"  {tag}", end=" … ", flush=True)

                    try:
                        stats = run_instance(enc_path, inst_path, bins, time_limit)
                    except Exception as exc:
                        print(f"ERROR: {exc}")
                        stats = dict(
                            result        = "ERROR",
                            atoms         = None, rules      = None,
                            choices       = None, conflicts  = None,
                            restarts      = None,
                            ground_time_s = None,
                            solve_time_s  = None,
                            total_time_s  = None,
                        )

                    res = stats["result"]
                    t   = stats["total_time_s"]
                    ch  = stats["choices"]
                    print(f"{res:<12}  {f'{t:.3f}s' if t is not None else '-':>8}"
                          f"  choices={ch if ch is not None else '-'}")

                    all_records.append(RunRecord(
                        timestamp = dt.datetime.now().isoformat(),
                        series    = series,
                        instance  = inst_path.name,
                        encoding  = enc_name,
                        bins      = bins,
                        **stats,
                    ))

    # ── write CSV ─────────────────────────────────────────────────────────────
    csv_path = output_dir / f"results_{timestamp}.csv"
    fieldnames = [f.name for f in fields(RunRecord)]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for rec in all_records:
            writer.writerow(asdict(rec))

    print(f"\nResults saved → {csv_path}")

    # ── Excel export ───────────────────────────────────────────────────────────
    xlsx_path = csv_path.with_suffix(".xlsx")
    export_excel(all_records, xlsx_path)

    # ── print summary ─────────────────────────────────────────────────────────
    _print_summary(all_records)

    return csv_path


# ── summary table ─────────────────────────────────────────────────────────────

def _avg(vals: list) -> Optional[float]:
    clean = [v for v in vals if v is not None]
    return statistics.mean(clean) if clean else None


def _fmt(v, fmt=".3f") -> str:
    return f"{v:{fmt}}" if v is not None else "-"


def _print_summary(records: list[RunRecord]) -> None:
    print(f"\n{'═'*90}")
    print("SUMMARY")
    print(f"{'═'*90}")

    groups: dict[tuple, list[RunRecord]] = defaultdict(list)
    for r in records:
        groups[(r.series, r.encoding, r.bins)].append(r)

    col = "{:<6} {:<22} {:>4} {:>8} {:>8} {:>10} {:>11} {:>10} {:>10}"
    header = col.format(
        "Series", "Encoding", "bins", "N", "OPTIMUM",
        "avg_t(s)", "avg_choices", "avg_atoms", "avg_rules",
    )
    print(header)
    print("─" * 90)

    for (series, enc, bins), grp in sorted(groups.items()):
        n      = len(grp)
        n_opt  = sum(1 for r in grp if r.result == "OPTIMUM")
        avg_t  = _avg([r.total_time_s for r in grp])
        avg_ch = _avg([r.choices      for r in grp])
        avg_at = _avg([r.atoms        for r in grp])
        avg_ru = _avg([r.rules        for r in grp])

        print(col.format(
            series, enc, bins, n, n_opt,
            _fmt(avg_t,  ".3f"),
            _fmt(avg_ch, ".0f"),
            _fmt(avg_at, ".0f"),
            _fmt(avg_ru, ".0f"),
        ))

    print(f"{'═'*90}")

    # Per-series breakdown: optimised vs baseline ratio
    print("\nKey ratios  (optimised_encoding / encoding_route, lower is better)")
    print("─" * 60)
    by_series: dict[str, dict[str, list[RunRecord]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        by_series[r.series][r.encoding].append(r)

    for series in sorted(by_series):
        base = by_series[series].get("encoding_route", [])
        opt  = by_series[series].get("optimised_encoding", [])
        if not base or not opt:
            continue

        def ratio(attr):
            b = _avg([getattr(r, attr) for r in base])
            o = _avg([getattr(r, attr) for r in opt])
            if b and o and b > 0:
                return f"{o/b:.2f}×"
            return "-"

        print(f"  Series {series}:  "
              f"choices={ratio('choices')}  "
              f"atoms={ratio('atoms')}  "
              f"time={ratio('total_time_s')}")


# ── Excel export ──────────────────────────────────────────────────────────────

# Column groups and display names used across sheets
_RAW_COLS = [f.name for f in fields(RunRecord)]

_HEADER_FILL   = PatternFill("solid", fgColor="1F4E79")   # dark blue
_SUBHEAD_FILL  = PatternFill("solid", fgColor="2E75B6")   # mid blue
_ALT_FILL      = PatternFill("solid", fgColor="D6E4F0")   # light blue
_OPT_FILL      = PatternFill("solid", fgColor="C6EFCE")   # green
_BASE_FILL     = PatternFill("solid", fgColor="FCE4D6")   # salmon
_WHITE_FONT    = Font(color="FFFFFF", bold=True)
_BOLD_FONT     = Font(bold=True)

# Columns to apply colour-scale conditional formatting on (1-based index in raw sheet)
_HEAT_COLS = {"choices", "conflicts", "restarts", "total_time_s", "atoms", "rules"}


def _set_col_widths(ws, widths: dict[int, int]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def _write_raw_sheet(wb: openpyxl.Workbook, records: list[RunRecord]) -> None:
    ws = wb.active
    ws.title = "Raw Data"

    # Header
    for ci, name in enumerate(_RAW_COLS, 1):
        cell = ws.cell(row=1, column=ci, value=name)
        cell.fill  = _HEADER_FILL
        cell.font  = _WHITE_FONT
        cell.alignment = Alignment(horizontal="center")

    ws.freeze_panes = "A2"

    # Rows
    for ri, rec in enumerate(records, 2):
        row = asdict(rec)
        for ci, name in enumerate(_RAW_COLS, 1):
            ws.cell(row=ri, column=ci, value=row[name])

    # Colour-scale on numeric columns
    max_row = len(records) + 1
    for ci, name in enumerate(_RAW_COLS, 1):
        if name in _HEAT_COLS and max_row > 2:
            col_letter = get_column_letter(ci)
            ws.conditional_formatting.add(
                f"{col_letter}2:{col_letter}{max_row}",
                ColorScaleRule(
                    start_type="min",        start_color="63BE7B",
                    mid_type="percentile",   mid_value=50, mid_color="FFEB84",
                    end_type="max",          end_color="F8696B",
                ),
            )

    _set_col_widths(ws, {1: 26, 2: 8, 3: 28, 4: 22, 5: 5, 6: 14,
                         7: 9, 8: 9, 9: 10, 10: 10, 11: 9,
                         12: 13, 13: 13, 14: 13})


def _write_summary_sheet(wb: openpyxl.Workbook, records: list[RunRecord]) -> None:
    """One row per (series, encoding, bins) with averaged metrics."""
    ws = wb.create_sheet("Summary")

    headers = [
        "series", "description", "encoding", "bins", "N", "OPTIMUM",
        "avg_total_s", "avg_ground_s", "avg_choices", "avg_conflicts",
        "avg_restarts", "avg_atoms", "avg_rules",
    ]
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.fill  = _HEADER_FILL
        cell.font  = _WHITE_FONT
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"

    groups: dict[tuple, list[RunRecord]] = defaultdict(list)
    for r in records:
        groups[(r.series, r.encoding, r.bins)].append(r)

    ri = 2
    for (series, enc, bins), grp in sorted(groups.items()):
        n      = len(grp)
        n_opt  = sum(1 for r in grp if r.result == "OPTIMUM")
        desc   = SERIES_CONFIG.get(series, {}).get("description", "")
        fill   = _OPT_FILL if enc == "optimised_encoding" else _BASE_FILL

        row_vals = [
            series, desc, enc, bins, n, n_opt,
            _avg([r.total_time_s  for r in grp]),
            _avg([r.ground_time_s for r in grp]),
            _avg([r.choices       for r in grp]),
            _avg([r.conflicts     for r in grp]),
            _avg([r.restarts      for r in grp]),
            _avg([r.atoms         for r in grp]),
            _avg([r.rules         for r in grp]),
        ]
        for ci, v in enumerate(row_vals, 1):
            cell = ws.cell(row=ri, column=ci,
                           value=round(v, 4) if isinstance(v, float) else v)
            cell.fill = fill
        ri += 1

    # Colour-scale on numeric summary columns (avg_total_s … avg_rules)
    max_row = ri - 1
    for ci in range(7, 14):
        col_letter = get_column_letter(ci)
        ws.conditional_formatting.add(
            f"{col_letter}2:{col_letter}{max_row}",
            ColorScaleRule(
                start_type="min",       start_color="63BE7B",
                mid_type="percentile",  mid_value=50, mid_color="FFEB84",
                end_type="max",         end_color="F8696B",
            ),
        )

    _set_col_widths(ws, {1: 8, 2: 45, 3: 22, 4: 5, 5: 4, 6: 8,
                         7: 12, 8: 12, 9: 12, 10: 12, 11: 10, 12: 10, 13: 10})


def _write_ratios_sheet(wb: openpyxl.Workbook, records: list[RunRecord]) -> None:
    """Speedup ratios: optimised_encoding / encoding_route per (series, bins)."""
    ws = wb.create_sheet("Ratios (opt÷base)")

    headers = [
        "series", "bins", "description",
        "ratio_choices", "ratio_conflicts", "ratio_atoms",
        "ratio_ground_t", "ratio_total_t",
        "base_avg_total_s", "opt_avg_total_s",
        "base_avg_choices", "opt_avg_choices",
    ]
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.fill  = _HEADER_FILL
        cell.font  = _WHITE_FONT
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"

    # Group by (series, bins, encoding)
    by_key: dict[tuple, dict[str, list[RunRecord]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        by_key[(r.series, r.bins)][r.encoding].append(r)

    ri = 2
    for (series, bins), enc_map in sorted(by_key.items()):
        base = enc_map.get("encoding_route", [])
        opt  = enc_map.get("optimised_encoding", [])
        if not base or not opt:
            continue

        def _ratio(attr):
            b = _avg([getattr(r, attr) for r in base])
            o = _avg([getattr(r, attr) for r in opt])
            return round(o / b, 4) if b and o and b > 0 else None

        desc = SERIES_CONFIG.get(series, {}).get("description", "")
        row_vals = [
            series, bins, desc,
            _ratio("choices"), _ratio("conflicts"), _ratio("atoms"),
            _ratio("ground_time_s"), _ratio("total_time_s"),
            _avg([r.total_time_s for r in base]),
            _avg([r.total_time_s for r in opt]),
            _avg([r.choices      for r in base]),
            _avg([r.choices      for r in opt]),
        ]
        for ci, v in enumerate(row_vals, 1):
            cell = ws.cell(row=ri, column=ci,
                           value=round(v, 4) if isinstance(v, float) else v)
            # Highlight ratios < 1 (optimised wins) in green, > 1 in red
            if ci in (4, 5, 6, 7, 8) and isinstance(v, float):
                if v < 1.0:
                    cell.fill = PatternFill("solid", fgColor="C6EFCE")
                elif v > 1.0:
                    cell.fill = PatternFill("solid", fgColor="FFC7CE")
        ri += 1

    _set_col_widths(ws, {1: 8, 2: 5, 3: 45, 4: 14, 5: 14, 6: 12,
                         7: 14, 8: 14, 9: 16, 10: 15, 11: 16, 12: 15})


def _write_per_series_sheet(wb: openpyxl.Workbook, series: str,
                             records: list[RunRecord]) -> None:
    """Detailed sheet for one series: instance × encoding × bins side-by-side."""
    ws = wb.create_sheet(f"Series {series}")
    desc = SERIES_CONFIG.get(series, {}).get("description", "")
    ws.cell(row=1, column=1, value=f"Series {series}: {desc}").font = _BOLD_FONT

    headers = ["instance", "bins", "encoding", "result",
               "total_time_s", "choices", "conflicts", "restarts", "atoms", "rules"]
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=ci, value=h)
        cell.fill  = _SUBHEAD_FILL
        cell.font  = _WHITE_FONT
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A3"

    series_recs = [r for r in records if r.series == series]
    for ri, rec in enumerate(series_recs, 3):
        row_vals = [rec.instance, rec.bins, rec.encoding, rec.result,
                    rec.total_time_s, rec.choices, rec.conflicts,
                    rec.restarts, rec.atoms, rec.rules]
        fill = _OPT_FILL if rec.encoding == "optimised_encoding" else _BASE_FILL
        for ci, v in enumerate(row_vals, 1):
            cell = ws.cell(row=ri, column=ci, value=v)
            cell.fill = fill

    # Colour-scale on numeric columns
    max_row = len(series_recs) + 2
    for ci, name in enumerate(headers, 1):
        if name in _HEAT_COLS and max_row > 3:
            col_letter = get_column_letter(ci)
            ws.conditional_formatting.add(
                f"{col_letter}3:{col_letter}{max_row}",
                ColorScaleRule(
                    start_type="min",       start_color="63BE7B",
                    mid_type="percentile",  mid_value=50, mid_color="FFEB84",
                    end_type="max",         end_color="F8696B",
                ),
            )

    _set_col_widths(ws, {1: 30, 2: 5, 3: 22, 4: 14,
                         5: 12, 6: 10, 7: 10, 8: 9, 9: 10, 10: 9})


def export_excel(records: list[RunRecord], path: Path) -> None:
    """Write a multi-sheet Excel workbook analysing all benchmark records."""
    wb = openpyxl.Workbook()

    _write_raw_sheet(wb, records)
    _write_summary_sheet(wb, records)
    _write_ratios_sheet(wb, records)

    seen_series = sorted({r.series for r in records})
    for s in seen_series:
        _write_per_series_sheet(wb, s, records)

    wb.save(path)
    print(f"Excel workbook saved → {path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark encoding_route vs optimised_encoding across five "
            "experiment series using the Clingo Python API."
        )
    )
    parser.add_argument(
        "--series", nargs="+",
        choices=sorted(SERIES_CONFIG),
        default=sorted(SERIES_CONFIG),
        help="Series to run (default: all).",
    )
    parser.add_argument(
        "--time-limit", type=int, default=60,
        help="Per-run wall-clock time limit in seconds (default: 60).",
    )
    parser.add_argument(
        "--output-dir", default="benchmark_results",
        help="Directory for CSV output (default: benchmark_results/).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    # Validate encoding files exist
    for name, path in ENCODINGS.items():
        if not path.exists():
            print(f"Error: encoding not found: {path}", file=sys.stderr)
            return 1

    run_benchmarks(
        series_names = args.series,
        time_limit   = args.time_limit,
        output_dir   = HERE / args.output_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
