#!/usr/bin/env python3
"""Show answer-set packings side-by-side for different Stage 2 configurations.

Runs Stage 1 once, then Stage 2 for each requested config, and pretty-prints
the trip-load assignments grouped by arc. Produces both plain-text and
LaTeX-ready output for inclusion in a thesis.

Usage (from repo root):
    uv run python src/experiments/two_stage/final/show_answer_sets.py \
        --instance src/instances/generated/layered_small_seed1.lp \
        --weight 300 --time-limit 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(SRC))

import main as api  # noqa: E402

CONFIGS = {
    "off_off": (0, 0),
    "hetero":  (1, 0),
    "conc":    (0, 1),
    "both":    (1, 1),
}

DEFAULT_S1 = str(SRC / "experiments" / "two_stage" / "final" / "encodings" / "stage_1_flow.lp")
DEFAULT_S2 = str(SRC / "experiments" / "two_stage" / "final" / "encodings" / "stage2_packing.lp")


def format_packing(result: dict, config_name: str) -> str:
    """Format a Stage 2 result into a human-readable packing summary."""
    trip_loads: dict[tuple, int] = result["trip_loads"]
    used_trips: set[tuple] = result["used_trips"]
    stage1 = result["_stage1"]

    arcs: dict[tuple, dict] = {}
    for (fr, to, tr, p, k), v in sorted(trip_loads.items()):
        arc_key = (fr, to, tr)
        if arc_key not in arcs:
            arcs[arc_key] = {}
        trip_key = k
        if trip_key not in arcs[arc_key]:
            arcs[arc_key][trip_key] = {}
        arcs[arc_key][trip_key][p] = v

    route_caps = {}
    route_freqs_map = {}
    for rf in stage1.get("route_freqs", []):
        key = (rf["from"], rf["to"], rf["tr"])
        route_freqs_map[key] = rf["freq"]
        if rf["freq"] > 0:
            route_caps[key] = rf["total_cap"] // rf["freq"]
        else:
            route_caps[key] = rf["total_cap"]

    lines = []
    lines.append(f"=== Configuration: {config_name} ===")
    lines.append(f"S2 Cost: {result.get('cost', '?')}  |  "
                 f"Optimal: {result.get('optimum', '?')}  |  "
                 f"Mono trips: {result.get('mono_count', '?')}  |  "
                 f"Concentrated: {result.get('concentrated_count', '?')}")
    lines.append("")

    total_used = 0
    total_trips = 0
    total_mono = 0

    for arc_key in sorted(arcs.keys()):
        fr, to, tr = arc_key
        freq = route_freqs_map.get(arc_key, "?")
        cap = route_caps.get(arc_key, "?")
        lines.append(f"Arc ({fr}, {to}, {tr})  Freq={freq}, Cap={cap}")

        trip_data = arcs[arc_key]
        all_trips = sorted(trip_data.keys())

        arc_used = 0
        arc_mono = 0
        for k in all_trips:
            parts = trip_data[k]
            total_trips += 1
            part_strs = [f"{p}={v}" for p, v in sorted(parts.items())]
            total_load = sum(parts.values())
            n_parts = len(parts)

            is_used = (fr, to, tr, k) in used_trips or total_load > 0
            if is_used:
                arc_used += 1
                total_used += 1

            if not is_used or total_load == 0:
                lines.append(f"  Trip k{k}: [empty]")
                continue

            tag = ""
            if n_parts == 1:
                tag = "  << MONO"
                arc_mono += 1
                total_mono += 1

            lines.append(f"  Trip k{k}: {', '.join(part_strs)}  "
                         f"(total={total_load}){tag}")

        lines.append(f"  -> Used {arc_used}/{len(all_trips)} trips, "
                     f"mono={arc_mono}")
        lines.append("")

    lines.append(f"TOTAL: {total_used} used trips, {total_mono} mono trips")
    lines.append("")
    return "\n".join(lines)


def format_latex_listing(text: str, config_name: str) -> str:
    """Wrap a packing summary in a LaTeX lstlisting block."""
    escaped = config_name.replace("_", r"\_")
    return (
        f"\\begin{{lstlisting}}[caption={{{escaped}}},basicstyle=\\tiny\\ttfamily,breaklines=true]\n"
        f"{text}\n"
        f"\\end{{lstlisting}}\n"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Show answer-set packings")
    p.add_argument("--instance", required=True, help="Path to instance .lp file")
    p.add_argument("--weight", type=int, default=300)
    p.add_argument("--time-limit", type=int, default=60)
    p.add_argument("--max-freq", type=int, default=20)
    p.add_argument("--exposure-n", type=int, default=3)
    p.add_argument("--s1-encoding", default=DEFAULT_S1)
    p.add_argument("--s2-encoding", default=DEFAULT_S2)
    p.add_argument("--configs", nargs="+", default=["off_off", "hetero"],
                   choices=list(CONFIGS.keys()),
                   help="Stage 2 configs to compare (default: off_off hetero)")
    p.add_argument("--output-dir", default=None,
                   help="Directory to write output files (default: results/answer_sets/)")
    p.add_argument("--configuration", default="many")
    args = p.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else (
        Path(__file__).parent / "results" / "answer_sets"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    inst_name = Path(args.instance).stem

    print(f"Instance: {args.instance}")
    print(f"Weight:   {args.weight}")
    print(f"Configs:  {args.configs}")
    print()

    print("--- Stage 1 ---")
    solver, stage1 = api.solve_stage1(
        args.instance,
        weight=args.weight,
        time_limit=args.time_limit,
        max_freq=args.max_freq,
        exposure_n=args.exposure_n,
        stage1_encoding=args.s1_encoding,
        configuration=args.configuration,
    )

    if stage1 is None:
        print("ERROR: Stage 1 UNSAT or timed out")
        sys.exit(1)

    print(f"  S1 cost: {stage1.get('cost')}, "
          f"routes: {len(stage1.get('route_freqs', []))}, "
          f"time: {stage1.get('time')}s")
    print()

    all_texts = {}
    all_latex = {}

    for cfg_name in args.configs:
        hetero_on, conc_on = CONFIGS[cfg_name]
        print(f"--- Stage 2: {cfg_name} (hetero={hetero_on}, conc={conc_on}) ---")

        result = api.solve_stage2_from_stage1(
            solver, stage1,
            hetero_on=hetero_on,
            concentrated_on=conc_on,
            stage2_encoding=args.s2_encoding,
        )

        if result is None:
            print(f"  ERROR: Stage 2 UNSAT for config {cfg_name}")
            all_texts[cfg_name] = f"=== {cfg_name}: UNSAT ==="
            continue

        print(f"  S2 cost: {result.get('cost')}, "
              f"mono: {result.get('mono_count')}, "
              f"time: {result.get('time')}s")

        text = format_packing(result, cfg_name)
        all_texts[cfg_name] = text
        all_latex[cfg_name] = format_latex_listing(text, cfg_name)

        txt_path = out_dir / f"{inst_name}_w{args.weight}_{cfg_name}.txt"
        txt_path.write_text(text)
        print(f"  Wrote: {txt_path}")
        print()

    combined_txt = "\n\n".join(all_texts[c] for c in args.configs if c in all_texts)
    combined_path = out_dir / f"{inst_name}_w{args.weight}_comparison.txt"
    combined_path.write_text(combined_txt)
    print(f"Wrote combined comparison: {combined_path}")

    if all_latex:
        latex_parts = []
        cfgs = [c for c in args.configs if c in all_latex]
        if len(cfgs) == 2:
            latex_parts.append(r"\begin{figure}[ht]")
            for i, cfg in enumerate(cfgs):
                latex_parts.append(r"\begin{minipage}[t]{.48\textwidth}")
                latex_parts.append(all_latex[cfg].rstrip())
                latex_parts.append(r"\end{minipage}")
                if i == 0:
                    latex_parts.append(r"\hfill")
            escaped_inst = inst_name.replace("_", r"\_")
            latex_parts.append(r"\caption{Stage~2 packing comparison: "
                               + " vs ".join(c.replace("_", r"\_") for c in cfgs)
                               + f" ($w={args.weight}$, \\texttt{{{escaped_inst}}})" + "}")
            latex_parts.append(r"\label{fig:packing_comparison}")
            latex_parts.append(r"\end{figure}")
        else:
            for cfg in cfgs:
                latex_parts.append(all_latex[cfg])

        latex_str = "\n".join(latex_parts)
        latex_path = out_dir / f"{inst_name}_w{args.weight}_comparison.tex"
        latex_path.write_text(latex_str)
        print(f"Wrote LaTeX:  {latex_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
