#!/usr/bin/env python3
"""
_large_clingcon_worker.py — isolated subprocess worker for alternative_clingcon.lp
on large instances (generated_instances_large/).

Called by large_instance_benchmark.py via subprocess.run().  Accepts arguments:
    encoding_path instance_path time_limit [config_arg ...]

Key differences from _clingcon_worker.py:
  - No numBins / maxFreq / maxItems constants (alternative_clingcon.lp doesn't use them)
  - Extended adapter: also injects partTR/2 (instances don't declare it)
  - cap_size_divide=1 is passed as a config_arg by the parent

Prints a single JSON object to stdout with run statistics, then exits.
"""

import json
import sys
import threading
import time

import clingo
import clingo.ast
from clingcon import ClingconTheory

# Large instances declare transportCapacity/2 but not transportResource/1 or partTR/2.
# cap_size_divide is overridden to 1 via -c so raw capacity values are used.
_ADAPTER = (
    "transportResource(TR) :- transportCapacity(TR, _)."
    "partTR(P,TR) :- part(P), transportCapacity(TR,_)."
)


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
    time_limit    = int(sys.argv[3])
    config_args   = sys.argv[4:]   # e.g. ["-c", "cap_size_divide=1", "--configuration=jumpy"]

    theory = ClingconTheory()
    ctl = clingo.Control(["--stats=2", *config_args])
    theory.register(ctl)

    with clingo.ast.ProgramBuilder(ctl) as builder:
        def on_rule(stm):
            theory.rewrite_ast(stm, builder.add)
        clingo.ast.parse_string(_ADAPTER, on_rule)
        clingo.ast.parse_files([encoding_path, instance_path], on_rule)

    t0 = time.perf_counter()
    ctl.ground([("base", [])])
    theory.prepare(ctl)
    wall_ground = time.perf_counter() - t0

    has_model      = False
    optimum_proven = False

    with ctl.solve(yield_=True) as handle:
        timer = threading.Timer(time_limit, handle.cancel)
        timer.start()
        try:
            for model in handle:
                theory.on_model(model)
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
    elif optimum_proven or (has_model and not interrupted):
        result = "OPTIMUM"
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
