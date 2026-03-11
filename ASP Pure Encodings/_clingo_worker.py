#!/usr/bin/env python3
"""
_clingo_worker.py — isolated subprocess worker for pure-ASP (clingo) solves.

Called by scaling_benchmark.py via subprocess.run().  Accepts arguments:
    encoding_path instance_path num_bins time_limit [config_arg ...]

Prints a single JSON object to stdout with the run statistics, then exits.
Any crash (segfault, SIGBUS, OOM) kills only this subprocess.
"""

import json
import sys
import threading
import time

import clingo


def _get(d, *keys, default=None):
    v = d
    for k in keys:
        try:
            v = v[k]
        except (KeyError, TypeError, IndexError):
            return default
    return v


def main():
    encoding_path = sys.argv[1]
    instance_path = sys.argv[2]
    num_bins      = int(sys.argv[3])
    time_limit    = int(sys.argv[4])
    config_args   = sys.argv[5:]

    ctl = clingo.Control([
        "--stats=2",
        "-c", f"numBins={num_bins}",
        *config_args,
    ])
    ctl.load(encoding_path)
    ctl.load(instance_path)
    ctl.add("base", [], f"bins(1..{num_bins}).")

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    wall_ground = time.perf_counter() - t0

    has_model = optimum_proven = False

    with ctl.solve(yield_=True) as handle:
        timer = threading.Timer(time_limit, handle.cancel)
        timer.start()
        try:
            for model in handle:
                has_model = True
                if model.optimality_proven:
                    optimum_proven = True
        finally:
            timer.cancel()
        solve_result = handle.get()

    wall_total = time.perf_counter() - t0

    interrupted = getattr(solve_result, "interrupted", not solve_result.exhausted)
    if solve_result.satisfiable is False:
        result = "UNSAT"
    elif optimum_proven:
        result = "OPTIMUM"
    elif has_model and not interrupted:
        result = "OPTIMUM"    # exhausted search with a model = optimal
    elif has_model and interrupted:
        result = "SAT_TIMEOUT"
    elif interrupted:
        result = "TIMEOUT"
    else:
        result = "SATISFIABLE"

    s = ctl.statistics
    solvers_raw = _get(s, "solving", "solvers", default={})
    if isinstance(solvers_raw, list):
        choices   = sum(int(_get(sv, "choices",   default=0)) for sv in solvers_raw)
        conflicts = sum(int(_get(sv, "conflicts",  default=0)) for sv in solvers_raw)
        restarts  = sum(int(_get(sv, "restarts",   default=0)) for sv in solvers_raw)
    else:
        choices   = _get(solvers_raw, "choices",  default=None)
        conflicts = _get(solvers_raw, "conflicts", default=None)
        restarts  = _get(solvers_raw, "restarts",  default=None)

    atoms = _get(s, "problem", "lp", "atoms")
    rules = _get(s, "problem", "lp", "rules")

    output = {
        "result":        result,
        "atoms":         int(atoms)     if atoms     is not None else None,
        "rules":         int(rules)     if rules     is not None else None,
        "choices":       int(choices)   if choices   is not None else None,
        "conflicts":     int(conflicts) if conflicts is not None else None,
        "restarts":      int(restarts)  if restarts  is not None else None,
        "ground_time_s": round(wall_ground, 4),
        "solve_time_s":  round(max(wall_total - wall_ground, 0.0), 4),
        "total_time_s":  round(wall_total, 4),
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
