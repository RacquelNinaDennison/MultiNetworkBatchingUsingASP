"""Strategy-sensitivity probe for the parametric R_alpha/CVaR_alpha metrics.

Question: is the "packing soft constraints HURT partial-loss resilience" result on
the layered instances real, or an artefact of strategy="heaviest" (which removes the
most-loaded trips first and so structurally penalises concentration)?

Method: isolate the survivor-selection strategy as the ONLY variable. Per instance we
load the cached MILP flow, solve each packing config ONCE, then score the alpha-triple
(R_alpha=min, CVaR_alpha=10% tail, NRI_alpha=mean) on that *identical* packing under
each of {heaviest, first, last}. Same packing => any sign change is the strategy, not
packing noise. Reports per-strategy win-rate of each config vs baseline on CVaR_alpha
(single mode), aggregated across instances.

    PYTHONPATH=src .venv/bin/python -m multibatch.experiments.milp_resilience.strategy_probe \
      --instance-glob 'layered_small_*.lp' 'layered_medium_*.lp' --stage2-time-limit 30
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from ...metrics.coverage import cvar_alpha_from_details, nri_alpha_from_details
from ...metrics.resilience import compute_r_alpha
from ...models import TwoStageClingconConfig
from ...solvers.milp_flow import MilpFlowTwoStageSolver
from ..twostage.config import ALPHA_VALUES
from .runner import _synth_values
from .suite import INSTANCE_DIR, WEIGHTED_ENC, _load_flow, discover_instances

STRATEGIES = ["heaviest", "first", "last"]
COMBOS = [("baseline", 0, 0), ("hetero_w8", 8, 0), ("conc_w8", 0, 8), ("full_w8_8", 8, 8)]
CACHE = Path("src/multibatch/experiments/milp_resilience/results/flows")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="R_alpha strategy-sensitivity probe")
    p.add_argument("--instance-glob", nargs="+",
                   default=["layered_small_*.lp", "layered_medium_*.lp"])
    p.add_argument("--instance-dir", type=Path, default=INSTANCE_DIR)
    p.add_argument("--instance-filter", default=None)
    p.add_argument("--synth-values", choices=["none", "uniform", "size"], default="size")
    p.add_argument("--backend", default="SCIP")
    p.add_argument("--flow-time-limit", type=int, default=120)
    p.add_argument("--stage2-time-limit", type=int, default=30)
    p.add_argument("--configuration", default="many")
    p.add_argument("-o", "--out",
                   default="src/multibatch/experiments/milp_resilience/results/strategy_probe.csv")
    args = p.parse_args(argv)

    instances = discover_instances(args.instance_dir, args.instance_glob, args.instance_filter)
    if not instances:
        print("No instances found."); return 1
    print(f"Instances ({len(instances)}): {[p.stem for p in instances]}")
    print(f"Strategies: {STRATEGIES}\n")

    rows: list[dict] = []
    for inst_path in instances:
        stem = inst_path.stem
        cfg = TwoStageClingconConfig(
            weight=0, max_freq=20, cap_size_divide=1,
            time_limit=args.stage2_time_limit, round_timeout=args.stage2_time_limit,
            configuration=args.configuration)
        solver = MilpFlowTwoStageSolver(
            inst_path, config=cfg, backend=args.backend,
            flow_time_limit=args.flow_time_limit, stage2_encoding=WEIGHTED_ENC)
        _synth_values(solver.instance, args.synth_values)

        cache_path = CACHE / f"flow_milp_ln0.0_lf0.0_{stem}.json"
        if not cache_path.exists():
            print(f"[{stem}] no cached flow at {cache_path} — skip (run the suite first)."); continue
        stage1 = _load_flow(cache_path)
        print(f"=== {stem} (flow from cache: {len(stage1.route_freqs)} arcs) ===")

        for name, wh, wc in COMBOS:
            solver.config.w_hetero, solver.config.w_conc = wh, wc
            stage2 = solver._solve_stage2(stage1)
            if stage2 is None:
                print(f"  {name:10s} -> UNSAT packing"); continue
            for strat in STRATEGIES:
                row = {"instance": stem, "config": name, "strategy": strat}
                for a in ALPHA_VALUES:
                    ra, details = compute_r_alpha(
                        stage1, stage2, solver.instance, alpha=a, mode="single", strategy=strat)
                    row[f"r_alpha_{a}"] = ra
                    row[f"nri_alpha_{a}"] = nri_alpha_from_details(details, "single")
                    row[f"cvar_alpha_{a}"] = cvar_alpha_from_details(details, "single", q=0.10)
                rows.append(row)
            # compact per-config print: CVaR_alpha under each strategy
            for strat in STRATEGIES:
                r = next(x for x in rows if x["instance"] == stem and x["config"] == name
                         and x["strategy"] == strat)
                cells = "  ".join(f"a{a}={r[f'cvar_alpha_{a}']}" for a in ALPHA_VALUES)
                print(f"  {name:10s} cvar_alpha[{strat:8s}]: {cells}")

    # write CSV
    out = Path(args.out)
    fields = (["instance", "config", "strategy"]
              + [f"{m}_{a}" for a in ALPHA_VALUES for m in ("r_alpha", "nri_alpha", "cvar_alpha")])
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    _winrate_summary(rows)
    print(f"\n-> {out}")
    return 0


def _winrate_summary(rows: list[dict]) -> None:
    """Per-strategy win-rate of each config vs baseline on CVaR_alpha (single)."""
    # (instance, strategy) -> {config: row}
    groups: dict = defaultdict(dict)
    for r in rows:
        groups[(r["instance"], r["strategy"])][r["config"]] = r
    print("\n=== CVaR_alpha WIN-RATE vs baseline, per strategy (the artefact test) ===")
    for strat in STRATEGIES:
        print(f"\n  strategy = {strat}")
        for a in ALPHA_VALUES:
            col = f"cvar_alpha_{a}"
            wins: dict = defaultdict(lambda: [0, 0, 0.0])  # config -> [wins, n, sumDelta]
            for (inst, s), cfgs in groups.items():
                if s != strat:
                    continue
                base = cfgs.get("baseline", {}).get(col)
                if base is None:
                    continue
                for name, r in cfgs.items():
                    if name == "baseline" or r.get(col) is None:
                        continue
                    d = r[col] - base
                    wins[name][1] += 1
                    wins[name][0] += int(d > 1e-9)
                    wins[name][2] += d
            cells = "   ".join(
                f"{name}: {w}/{n} ({sd / n:+.4f})" for name, (w, n, sd) in sorted(wins.items()) if n)
            print(f"    a={a}: {cells}")


if __name__ == "__main__":
    sys.exit(main())
