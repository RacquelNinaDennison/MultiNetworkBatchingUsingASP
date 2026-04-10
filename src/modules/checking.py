#!/usr/bin/env python3
"""
checking.py – Solution verifier for multi-network batching ASP encodings.

Supports two encoding families:

  * ``naive``     – a single monolithic ASP encoding whose model exposes
                    ``flow/4``, ``pack/6`` and ``freq/5`` atoms.
  * ``twostage``  – a pure-ASP two-stage pipeline:
                      stage 1 produces ``load/5`` and ``routeFreq/5``;
                      stage 2, fed with stage 1's output as facts, produces
                      ``tripLoad/6``.

In both cases the solution is normalised into a common
``{flow, pack, freq}`` shape so the same invariants can be checked:

  1. Flow conservation  — for every (part, location), outflow − inflow equals
                          the net demand/supply declared in the instance.
  2. Bin capacity       — for every (bin, route), the total packed weight does
                          not exceed the transport resource's capacity.
  3. Flow satisfaction  — for every arc with positive required flow, the total
                          units dispatched across all bins (pack × freq) is at
                          least the required flow value.

For ``twostage`` a fourth check is added:

  4. Load/trip consistency — for every stage-1 ``load(N,P,TR,F,T)``, the sum of
                             ``tripLoad`` quantities over trips matches ``N``.

Usage
-----
    # Naive monolithic encoding
    uv run checking.py --mode naive \\
                       --encoding encoding/naive/encoding_route.lp \\
                       --instance instances/paper.lp

    # Two-stage pure-ASP encoding
    uv run checking.py --mode twostage \\
                       --stage1 encoding/twostage/naive/stage1_flow.lp \\
                       --stage2 encoding/twostage/naive/stage2_packing.lp \\
                       --instance instances/paper.lp
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import clingo


# ─────────────────────────────────────────────────────────────────────────────
# Instance extraction
# ─────────────────────────────────────────────────────────────────────────────

def load_instance(path: str) -> dict:
    """Parse instance facts into Python structures using the Clingo API.

    Returns a dict with keys:
        parts            : set[str]
        locations        : set[str]
        demand_offer     : dict[(part, loc), int]   – signed; positive = supply
        transport_cap    : dict[tr, int]
        part_size        : dict[part, int]
        routes           : list[(from, to, tr, dist, cost)]
    """
    ctl = clingo.Control()
    ctl.load(path)
    ctl.ground([("base", [])])

    instance: dict = {
        "parts":         set(),
        "locations":     set(),
        "demand_offer":  {},
        "transport_cap": {},
        "part_size":     {},
        "routes":        [],
    }

    for atom in ctl.symbolic_atoms:
        sym  = atom.symbol
        name = sym.name
        args = sym.arguments

        if name == "part" and len(args) == 1:
            instance["parts"].add(str(args[0]))

        elif name == "location" and len(args) == 1:
            instance["locations"].add(str(args[0]))

        elif name == "demandOffer" and len(args) == 3:
            p, l, d = str(args[0]), str(args[1]), args[2].number
            instance["demand_offer"].setdefault((p, l), []).append(d)

        elif name == "transportCapacity" and len(args) == 2:
            tr, c = str(args[0]), args[1].number
            instance["transport_cap"][tr] = c

        elif name == "partSize" and len(args) == 2:
            p, s = str(args[0]), args[1].number
            instance["part_size"][p] = s

        elif name == "route" and len(args) == 5:
            fr   = str(args[0])
            to   = str(args[1])
            tr   = str(args[2])
            dist = args[3].number
            cost = args[4].number
            instance["routes"].append((fr, to, tr, dist, cost))

    return instance


# ─────────────────────────────────────────────────────────────────────────────
# Solving
# ─────────────────────────────────────────────────────────────────────────────

def _parse_model(model: clingo.Model) -> dict:
    """Extract pack/freq/flow atoms from a Clingo model into Python tuples."""
    atoms: dict[str, list] = {"pack": [], "freq": [], "flow": []}

    for sym in model.symbols(shown=True):
        name = sym.name
        a    = sym.arguments

        if name == "pack" and len(a) == 6:
            atoms["pack"].append((
                a[0].number,   # N
                str(a[1]),     # P
                a[2].number,   # ID
                str(a[3]),     # From
                str(a[4]),     # To
                str(a[5]),     # TR
            ))

        elif name == "freq" and len(a) == 5:
            atoms["freq"].append((
                a[0].number,   # ID
                str(a[1]),     # From
                str(a[2]),     # To
                str(a[3]),     # TR
                a[4].number,   # F
            ))

        elif name == "flow" and len(a) == 4:
            atoms["flow"].append((
                str(a[0]),     # From
                str(a[1]),     # To
                str(a[2]),     # Part
                a[3].number,   # N
            ))

    return atoms


def solve(encoding: str, instance: str, num_bins: int) -> dict | None:
    """Run the monolithic (naive) encoding and return its optimal answer set."""
    ctl = clingo.Control(["-c", f"numBins={num_bins}"])
    ctl.load(encoding)
    ctl.load(instance)
    ctl.ground([("base", [])])

    last_model: dict | None = None

    with ctl.solve(yield_=True) as handle:
        for model in handle:
            last_model = _parse_model(model)
            if model.optimality_proven:
                break

    return last_model


# ─────────────────────────────────────────────────────────────────────────────
# Two-stage solving
# ─────────────────────────────────────────────────────────────────────────────

def _parse_stage1_model(model: clingo.Model) -> dict:
    """Extract ``load/5`` and ``routeFreq/5`` from a stage-1 model."""
    out: dict[str, list] = {"load": [], "routeFreq": []}
    for sym in model.symbols(shown=True):
        a = sym.arguments
        if sym.name == "load" and len(a) == 5:
            out["load"].append((
                a[0].number,   # N
                str(a[1]),     # P
                str(a[2]),     # TR
                str(a[3]),     # From
                str(a[4]),     # To
            ))
        elif sym.name == "routeFreq" and len(a) == 5:
            out["routeFreq"].append((
                str(a[0]),     # From
                str(a[1]),     # To
                str(a[2]),     # TR
                a[3].number,   # Freq
                a[4].number,   # TotalCap
            ))
    return out


def _parse_stage2_model(model: clingo.Model) -> list[tuple]:
    """Extract ``tripLoad/6`` from a stage-2 model."""
    trips: list[tuple] = []
    for sym in model.symbols(shown=True):
        a = sym.arguments
        if sym.name == "tripLoad" and len(a) == 6:
            trips.append((
                str(a[0]),     # From
                str(a[1]),     # To
                str(a[2]),     # TR
                str(a[3]),     # Part
                a[4].number,   # Q
                a[5].number,   # K (trip id)
            ))
    return trips


def _stage1_to_facts(stage1: dict) -> str:
    """Serialise a stage-1 solution as ground facts to feed into stage 2."""
    lines: list[str] = []
    for (n, p, tr, fr, to) in stage1["load"]:
        lines.append(f"load({n},{p},{tr},{fr},{to}).")
    for (fr, to, tr, freq, cap) in stage1["routeFreq"]:
        lines.append(f"routeFreq({fr},{to},{tr},{freq},{cap}).")
    return "\n".join(lines)


def solve_twostage(stage1_path: str, stage2_path: str, instance: str) -> dict | None:
    """Run the two-stage pure-ASP pipeline.

    Returns a dict with raw stage-1 and stage-2 atoms, or ``None`` if either
    stage is UNSAT.
    """
    # ── Stage 1 ──────────────────────────────────────────────────────────────
    ctl1 = clingo.Control()
    ctl1.load(stage1_path)
    ctl1.load(instance)
    ctl1.ground([("base", [])])

    stage1: dict | None = None
    with ctl1.solve(yield_=True) as handle:
        for model in handle:
            stage1 = _parse_stage1_model(model)
            if model.optimality_proven:
                break

    if stage1 is None:
        return None

    # ── Stage 2 ──────────────────────────────────────────────────────────────
    ctl2 = clingo.Control()
    ctl2.load(stage2_path)
    ctl2.load(instance)
    ctl2.add("stage1_output", [], _stage1_to_facts(stage1))
    ctl2.ground([("base", []), ("stage1_output", [])])

    trip_loads: list[tuple] | None = None
    with ctl2.solve(yield_=True) as handle:
        for model in handle:
            trip_loads = _parse_stage2_model(model)
            if model.optimality_proven:
                break

    if trip_loads is None:
        return None

    return {
        "load":      stage1["load"],
        "routeFreq": stage1["routeFreq"],
        "tripLoad":  trip_loads,
    }


def canonicalize_twostage(raw: dict) -> dict:
    """Convert a two-stage solution into the common ``{flow, pack, freq}`` shape.

    Each stage-2 trip id ``K`` is treated as a bin with ``freq = 1`` so that
    the existing checkers apply unchanged.
    """
    # flow(From, To, Part, N)  ← aggregate load over transport resources
    flow_agg: dict[tuple, int] = defaultdict(int)
    for (n, p, _tr, fr, to) in raw["load"]:
        if n > 0:
            flow_agg[(fr, to, p)] += n
    flow = [(fr, to, p, n) for (fr, to, p), n in flow_agg.items()]

    # pack(N, P, ID=K, From, To, TR) ← tripLoad (drop zero-quantity entries)
    pack = [
        (q, p, k, fr, to, tr)
        for (fr, to, tr, p, q, k) in raw["tripLoad"]
        if q > 0
    ]

    # freq(ID=K, From, To, TR, 1) — one entry per distinct used trip
    freq_keys: set[tuple] = set()
    for (fr, to, tr, _p, q, k) in raw["tripLoad"]:
        if q > 0:
            freq_keys.add((k, fr, to, tr))
    freq_list = [(k, fr, to, tr, 1) for (k, fr, to, tr) in freq_keys]

    return {"flow": flow, "pack": pack, "freq": freq_list}


def check_load_trip_consistency(raw: dict) -> list[str]:
    """Verify ``Σ_K tripLoad(F,T,TR,P,Q,K) == N`` for every ``load(N,P,TR,F,T)``."""
    errors: list[str] = []

    trip_sum: dict[tuple, int] = defaultdict(int)
    for (fr, to, tr, p, q, _k) in raw["tripLoad"]:
        trip_sum[(p, tr, fr, to)] += q

    seen: set[tuple] = set()
    for (n, p, tr, fr, to) in raw["load"]:
        key = (p, tr, fr, to)
        seen.add(key)
        total = trip_sum.get(key, 0)
        if total != n:
            errors.append(
                f"  load/trip FAIL  part={p} tr={tr} route=({fr}→{to}): "
                f"Σ tripLoad={total}  ≠  load N={n}"
            )

    for key, total in trip_sum.items():
        if key not in seen and total != 0:
            p, tr, fr, to = key
            errors.append(
                f"  load/trip FAIL  part={p} tr={tr} route=({fr}→{to}): "
                f"tripLoad={total} but no matching load atom"
            )

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Checkers
# ─────────────────────────────────────────────────────────────────────────────

def check_flow_conservation(solution: dict, instance: dict) -> list[str]:
    """
    For every (part, location) pair, verify:
        outflow(P, L) − inflow(P, L) = netDemandSupply(P, L)

    where netDemandSupply(P, L) = demandOffer(P, L) if declared, else 0.
    """
    errors: list[str] = []

    # Build outflow / inflow maps indexed by (part, location)
    outflow: dict[tuple, int] = defaultdict(int)
    inflow:  dict[tuple, int] = defaultdict(int)

    for (fr, to, part, n) in solution["flow"]:
        outflow[(part, fr)] += n
        inflow[ (part, to)] += n

    for part in instance["parts"]:
        for loc in instance["locations"]:
            ds      = sum(instance["demand_offer"].get((part, loc), []))
            net     = outflow[(part, loc)] - inflow[(part, loc)]
            if net != ds:
                errors.append(
                    f"  flow conservation FAIL  part={part} loc={loc}: "
                    f"outflow({outflow[(part,loc)]}) − inflow({inflow[(part,loc)]}) "
                    f"= {net}  ≠  netDemandSupply={ds}"
                )

    return errors


def check_capacity(solution: dict, instance: dict) -> list[str]:
    """
    For every (bin, route) combination, verify:
        Σ N * partSize(P)  ≤  transportCapacity(TR)
    """
    errors: list[str] = []

    # Aggregate packed weight per (ID, From, To, TR)
    weight: dict[tuple, int] = defaultdict(int)
    for (n, p, id_, fr, to, tr) in solution["pack"]:
        size = instance["part_size"].get(p, 0)
        weight[(id_, fr, to, tr)] += n * size

    for (id_, fr, to, tr), total in weight.items():
        cap = instance["transport_cap"].get(tr)
        if cap is None:
            errors.append(
                f"  capacity FAIL  bin={id_} route=({fr}→{to},{tr}): "
                f"unknown transport resource '{tr}'"
            )
        elif total > cap:
            errors.append(
                f"  capacity FAIL  bin={id_} route=({fr}→{to},{tr}): "
                f"packed weight {total} > capacity {cap}"
            )

    return errors


def check_flow_satisfaction(solution: dict, instance: dict) -> list[str]:
    """
    For every arc (From, To, Part) with flow value > 0, verify:
        Σ_{bins, TR}  pack(N, P, ID, From, To, TR) * freq(ID, From, To, TR, F)  ≥  flow value
    """
    errors: list[str] = []

    # Index freq by (ID, From, To, TR) → F
    freq_map: dict[tuple, int] = {}
    for (id_, fr, to, tr, f) in solution["freq"]:
        freq_map[(id_, fr, to, tr)] = f

    # Index pack by (P, ID, From, To, TR) → N
    pack_map: dict[tuple, int] = {}
    for (n, p, id_, fr, to, tr) in solution["pack"]:
        pack_map[(p, id_, fr, to, tr)] = n

    # Collect all (ID, TR) combinations per route (From, To)
    bins_per_route: dict[tuple, list[tuple]] = defaultdict(list)
    for (id_, fr, to, tr, _) in solution["freq"]:
        bins_per_route[(fr, to)].append((id_, tr))

    for (fr, to, part, value) in solution["flow"]:
        if value <= 0:
            continue

        dispatched = 0
        for (id_, tr) in bins_per_route.get((fr, to), []):
            n = pack_map.get((part, id_, fr, to, tr), 0)
            f = freq_map.get((id_, fr, to, tr), 0)
            dispatched += n * f

        if dispatched < value:
            errors.append(
                f"  flow satisfaction FAIL  arc=({fr}→{to}) part={part}: "
                f"dispatched {dispatched} < required flow {value}"
            )

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Reporting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _report(label: str, errors: list[str]) -> bool:
    """Print check result. Returns True if the check passed."""
    if errors:
        print(f"  [FAIL] {label}")
        for e in errors:
            print(e)
        return False
    print(f"  [PASS] {label}")
    return True


def _print_solution_summary(solution: dict) -> None:
    print(f"  pack atoms : {len(solution['pack'])}")
    print(f"  freq atoms : {len(solution['freq'])}")
    print(f"  flow atoms : {len(solution['flow'])}")

    nonzero_flow = [(f, t, p, n) for (f, t, p, n) in solution["flow"] if n > 0]
    nonzero_pack = [(n, p, id_, f, t, tr) for (n, p, id_, f, t, tr) in solution["pack"] if n > 0]
    print(f"  non-zero flow : {len(nonzero_flow)}")
    print(f"  non-zero pack : {len(nonzero_pack)}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that an ASP multi-batching encoding produces a valid solution "
            "for a given instance, checking flow conservation, bin capacity, and "
            "flow satisfaction. Supports both the naive monolithic encoding and "
            "the two-stage pure-ASP encoding."
        )
    )
    parser.add_argument(
        "--mode", "-m",
        choices=("naive", "twostage"),
        default="naive",
        help="Which encoding family to verify (default: naive).",
    )
    parser.add_argument(
        "--encoding", "-e",
        help="[naive mode] Path to the monolithic encoding .lp file.",
    )
    parser.add_argument(
        "--stage1",
        help="[twostage mode] Path to the stage 1 (flow) encoding .lp file.",
    )
    parser.add_argument(
        "--stage2",
        help="[twostage mode] Path to the stage 2 (packing) encoding .lp file.",
    )
    parser.add_argument(
        "--instance", "-i",
        required=True,
        help="Path to the instance .lp file.",
    )
    parser.add_argument(
        "--bins", "-b",
        type=int,
        default=1,
        help="[naive mode] Number of bins (sets the numBins constant, default: 1).",
    )
    return parser


def _validate_paths(paths: list[Path]) -> bool:
    ok = True
    for p in paths:
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            ok = False
    return ok


def _run_checks(solution: dict, instance: dict, extra: list[tuple[str, list[str]]] | None = None) -> bool:
    print("Running checks …")
    fc_errors  = check_flow_conservation(solution, instance)
    cap_errors = check_capacity(solution, instance)
    fs_errors  = check_flow_satisfaction(solution, instance)

    results = [
        _report("Flow conservation", fc_errors),
        _report("Bin capacity",      cap_errors),
        _report("Flow satisfaction", fs_errors),
    ]
    for label, errors in (extra or []):
        results.append(_report(label, errors))

    return all(results)


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    instance_path = Path(args.instance)

    if args.mode == "naive":
        if not args.encoding:
            print("Error: --encoding is required in naive mode.", file=sys.stderr)
            return 1
        encoding_path = Path(args.encoding)
        if not _validate_paths([encoding_path, instance_path]):
            return 1

        print(f"Mode     : naive")
        print(f"Encoding : {encoding_path}")
        print(f"Instance : {instance_path}")
        print(f"Bins     : {args.bins}")
        print()

    else:  # twostage
        if not args.stage1 or not args.stage2:
            print("Error: --stage1 and --stage2 are required in twostage mode.", file=sys.stderr)
            return 1
        stage1_path = Path(args.stage1)
        stage2_path = Path(args.stage2)
        if not _validate_paths([stage1_path, stage2_path, instance_path]):
            return 1

        print(f"Mode     : twostage")
        print(f"Stage 1  : {stage1_path}")
        print(f"Stage 2  : {stage2_path}")
        print(f"Instance : {instance_path}")
        print()

    # ── Load instance facts ──────────────────────────────────────────────────
    print("Loading instance facts …")
    instance = load_instance(str(instance_path))
    print(f"  parts          : {sorted(instance['parts'])}")
    print(f"  locations      : {sorted(instance['locations'])}")
    print(f"  routes         : {len(instance['routes'])}")
    print(f"  demand/supply  : {dict(sorted(instance['demand_offer'].items()))}")
    print()

    # ── Solve ────────────────────────────────────────────────────────────────
    print("Solving …")
    if args.mode == "naive":
        solution = solve(str(encoding_path), str(instance_path), args.bins)
        if solution is None:
            print("  Result: UNSATISFIABLE — no solution to check.")
            return 1
        print("  Result: solution found")
        _print_solution_summary(solution)
        print()

        passed = _run_checks(solution, instance)

    else:  # twostage
        raw = solve_twostage(str(stage1_path), str(stage2_path), str(instance_path))
        if raw is None:
            print("  Result: UNSATISFIABLE — no solution to check.")
            return 1
        print("  Result: solution found")
        print(f"  load atoms      : {len(raw['load'])}")
        print(f"  routeFreq atoms : {len(raw['routeFreq'])}")
        print(f"  tripLoad atoms  : {len(raw['tripLoad'])}")

        solution = canonicalize_twostage(raw)
        _print_solution_summary(solution)
        print()

        consistency_errors = check_load_trip_consistency(raw)
        passed = _run_checks(
            solution,
            instance,
            extra=[("Load/trip consistency", consistency_errors)],
        )

    print()
    if passed:
        print("All checks PASSED.")
        return 0
    print("One or more checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
