#!/usr/bin/env python3
"""
Weight sweep: Stage 1 → R_TR only; writes CSV checkpoints.

Delegates to :mod:`clingcon_weight_pipeline`.

Usage
-----
    python main.py --instances instances/data.lp
    python main.py --instances instances/data.lp \\
        --weights 0 50 100 200 500 1000 \\
        --time-limit 60 --output results/experiment.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from clingcon_weight_pipeline import run_r_tr_weight_sweep


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage 1 → R_TR sweep")
    p.add_argument("--instances", "-i", required=True,
                   help="Path to instance .lp file")
    p.add_argument("--weights", type=int, nargs="+",
                   default=[0, 50, 100, 200, 500, 1000],
                   help="div_weight values to sweep")
    p.add_argument("--time-limit", type=int, default=30,
                   help="Seconds per solve stage (default: 30)")
    p.add_argument("--cap-divide", type=int, default=1)
    p.add_argument("--max-freq", type=int, default=20)
    p.add_argument("--output", "-o", type=Path,
                   default=Path("results/experiment.csv"),
                   help="Output CSV path (default: results/experiment.csv)")
    return p.parse_args()


def main() -> None:
    run_r_tr_weight_sweep(parse_args())


if __name__ == "__main__":
    main()
