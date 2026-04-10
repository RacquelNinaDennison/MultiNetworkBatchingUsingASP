#!/usr/bin/env python3
"""
run_two_stage_naive.py — Pure-ASP two-stage solver with separate stage APIs.

Stage 1: network flow + frequency (stage1_flow.lp)
Stage 2: per-trip bin packing with diversification (stage2_packing.lp)
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from pathlib import Path

import clingo

from .base_solver import BaseSolver

ENCODING_DIR = Path(__file__).resolve().parent.parent / "encoding" / "twostage" / "naive"


class RunNaiveTwoStage(BaseSolver):

    def __init__(
        self,
        instance_path: str,
        time_limit: int = 30,
        max_freq: int = 20,
        weight: int = 1,
        exposure_n: int = 3,
    ):
        super().__init__(instance_path, time_limit)
        self.max_freq = max_freq
        self.weight = weight
        self.exposure_n = exposure_n
        self.encoding_stage1 = ENCODING_DIR / "stage1_flow.lp"
        self.encoding_stage2 = ENCODING_DIR / "stage2_packing.lp"

    # ─────────────────────────────────────────────────────────────────────
    # Domain fact generation
    # ─────────────────────────────────────────────────────────────────────

    def _generate_domain_facts(self) -> str:
        data = self.instance_data
        max_cap  = max(data["transport_cap"].values())
        min_size = min(data["part_size"].values())
        max_items = max_cap // min_size

        supply_by_part: dict[str, int] = defaultdict(int)
        for (part, _loc), vals in data["demand_offer"].items():
            for d in vals:
                if d > 0:
                    supply_by_part[part] += d
        max_supply = max(supply_by_part.values()) if supply_by_part else 0

        lines: list[str] = []

        for i in range(max_items + 1):
            lines.append(f"numParts({i}).")
        for i in range(max_supply + 1):
            lines.append(f"numFlow({i}).")
        for i in range(self.max_freq + 1):
            lines.append(f"numFreq({i}).")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Stage 1: Network flow + frequency
    # ─────────────────────────────────────────────────────────────────────

    def solve_stage1(self) -> dict | None:
        """Solve stage 1 only. Returns structured dict or None if UNSAT."""
        clingo_args: list[str] = [
            "-c", f"weight={self.weight}",
            "-c", f"exposure_n={self.exposure_n}",
        ]

        ctl = clingo.Control(clingo_args)
        ctl.load(str(self.encoding_stage1))
        ctl.load(str(self.instance_path))

        domain_facts = self._generate_domain_facts()
        ctl.add("domain", [], domain_facts)

        t0 = time.perf_counter()
        ctl.ground([("base", []), ("domain", [])])
        ground_time = time.perf_counter() - t0

        print(f"--- STAGE 1 ---")
        print(f"  Encoding : {self.encoding_stage1.name}")
        print(f"  Grounding: {ground_time:.3f}s")
        print(f"  Solving (up to {self.time_limit}s)...", end="", flush=True)

        best: dict | None = None
        best_cost: int | None = None
        optimum = False
        trajectory: list[dict] = []

        timer = threading.Timer(self.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    best = self._extract_stage1(model)
                    best_cost = model.cost[0] if model.cost else None
                    trajectory.append({
                        "cost": best_cost,
                        "time": round(time.perf_counter() - t0, 3),
                    })
                    if model.optimality_proven:
                        optimum = True
                        break
        except RuntimeError:
            pass
        finally:
            timer.cancel()

        total_time = time.perf_counter() - t0

        if optimum:
            print(f" OPTIMUM ({total_time:.3f}s)")
        elif best is not None:
            print(f" BEST ({total_time:.3f}s)")
        else:
            print(f" NO MODEL ({total_time:.3f}s)")

        if best is not None:
            best["ground_time"] = round(ground_time, 3)
            best["time"]        = round(total_time, 3)
            best["optimum"]     = optimum
            best["cost"]        = best_cost
            best["trajectory"]  = trajectory

        return best

    # ─────────────────────────────────────────────────────────────────────
    # Stage 2: Per-trip bin packing
    # ─────────────────────────────────────────────────────────────────────

    def solve_stage2(
        self,
        stage1_facts_str: str,
        hetero_on: int = 1,
        concentrated_on: int = 1,
    ) -> dict | None:
        """Solve stage 2 with piped stage 1 facts. Returns structured dict or None."""
        clingo_args: list[str] = [
            "-c", f"weight={self.weight}",
            "-c", f"hetero_on={hetero_on}",
            "-c", f"concentrated_on={concentrated_on}",
        ]

        ctl = clingo.Control(clingo_args)
        ctl.load(str(self.encoding_stage2))
        ctl.load(str(self.instance_path))

        ctl.add("stage1_output", [], stage1_facts_str)

        t0 = time.perf_counter()
        ctl.ground([("base", []), ("stage1_output", [])])
        ground_time = time.perf_counter() - t0

        print(f"\n--- STAGE 2 ---")
        print(f"  Encoding : {self.encoding_stage2.name}")
        print(f"  Grounding: {ground_time:.3f}s")
        print(f"  Solving (up to {self.time_limit}s)...", end="", flush=True)

        best: dict | None = None
        best_cost: int | None = None
        optimum = False
        trajectory: list[dict] = []

        timer = threading.Timer(self.time_limit, ctl.interrupt)
        timer.start()

        try:
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    best = self._extract_stage2(model)
                    best_cost = model.cost[0] if model.cost else None
                    trajectory.append({
                        "cost": best_cost,
                        "time": round(time.perf_counter() - t0, 3),
                    })
                    if model.optimality_proven:
                        optimum = True
                        break
        except RuntimeError:
            pass
        finally:
            timer.cancel()

        total_time = time.perf_counter() - t0

        if optimum:
            print(f" OPTIMUM ({total_time:.3f}s)")
        elif best is not None:
            print(f" BEST ({total_time:.3f}s)")
        else:
            print(f" NO MODEL ({total_time:.3f}s)")

        if best is not None:
            best["ground_time"] = round(ground_time, 3)
            best["time"]        = round(total_time, 3)
            best["optimum"]     = optimum
            best["cost"]        = best_cost
            best["trajectory"]  = trajectory

        return best

    # ─────────────────────────────────────────────────────────────────────
    # Combined solve  (both encodings, multi-shot with iterative bounds)
    # ─────────────────────────────────────────────────────────────────────

    # Mirrors the #minimize terms in stage1_flow.lp + stage2_packing.lp
    _BOUND = (
        ":- #sum {{ "
        "V, trans, From, To, TR : transCost(From,To,TR,V); "
        "Count, trips, F, T, TR : usedTripCount(F,T,TR,Count) "
        "}} >= {bound}."
    )

    def solve_combined(
        self,
        hetero_on: int = 1,
        concentrated_on: int = 1,
        round_timeout: int = 30,
        multishot: bool = True,
    ) -> dict | None:
        """Solve stage 1 + stage 2 together.

        When *multishot* is True (default), uses iterative bound tightening:
        each round gets ``round_timeout`` seconds, and the number of rounds
        is ``time_limit // round_timeout``.

        When *multishot* is False, does a single solve call with the full
        ``time_limit`` as the timeout — useful for benchmarking raw runtime.
        """
        num_rounds = 1 if not multishot else max(1, self.time_limit // round_timeout)

        clingo_args: list[str] = [
            "-c", f"weight={self.weight}",
            "-c", f"exposure_n={self.exposure_n}",
            "-c", f"hetero_on={hetero_on}",
            "-c", f"concentrated_on={concentrated_on}",
        ]

        ctl = clingo.Control(clingo_args)
        ctl.load(str(self.encoding_stage1))
        ctl.load(str(self.encoding_stage2))
        ctl.load(str(self.instance_path))

        domain_facts = self._generate_domain_facts()
        ctl.add("domain", [], domain_facts)

        t0 = time.perf_counter()
        ctl.ground([("base", []), ("domain", [])])
        ground_time = time.perf_counter() - t0

        effective_timeout = self.time_limit if not multishot else round_timeout

        print(f"  Encodings: {self.encoding_stage1.name} + {self.encoding_stage2.name}")
        print(f"  Grounding: {ground_time:.3f}s")
        if multishot:
            print(f"  Rounds: {num_rounds} × {round_timeout}s "
                  f"(time_limit={self.time_limit}s)")
        else:
            print(f"  Single-shot solve (up to {self.time_limit}s)")

        best_s1: dict | None = None
        best_s2: dict | None = None
        best_cost: int | None = None
        optimum = False
        trajectory: list[dict] = []

        for round_num in range(1, num_rounds + 1):
            if multishot:
                bound_str = (f" [bound < {best_cost}]"
                             if best_cost is not None else " [no bound]")
                print(f"  Round {round_num}/{num_rounds}: solving "
                      f"(up to {effective_timeout}s){bound_str}",
                      end="", flush=True)
            else:
                print(f"  Solving (up to {effective_timeout}s)...",
                      end="", flush=True)

            found_s1: dict | None = None
            found_s2: dict | None = None
            found_cost: int | None = None

            timer = threading.Timer(effective_timeout, ctl.interrupt)
            timer.start()

            try:
                with ctl.solve(yield_=True) as handle:
                    for model in handle:
                        found_s1 = self._extract_stage1(model)
                        found_s2 = self._extract_stage2(model)
                        found_cost = model.cost[0] if model.cost else None
                        trajectory.append({
                            "cost": found_cost,
                            "time": round(time.perf_counter() - t0, 3),
                        })
                        if model.optimality_proven:
                            optimum = True
                            break
                    solve_result = handle.get()
            except RuntimeError:
                solve_result = None
            finally:
                timer.cancel()

            # ── Analyse this round ────────────────────────────────────
            if optimum:
                best_s1, best_s2, best_cost = found_s1, found_s2, found_cost
                print(f" → OPTIMUM (cost={best_cost})", flush=True)
                break

            if (solve_result is not None
                    and getattr(solve_result, "unsatisfiable", False)):
                print(f" → UNSAT (previous cost={best_cost} is optimal)",
                      flush=True)
                optimum = True
                break

            if found_s1 is None:
                print(f" → no new model (using best cost={best_cost})",
                      flush=True)
                break

            best_s1, best_s2, best_cost = found_s1, found_s2, found_cost
            print(f" → model found (cost={best_cost})", flush=True)

            bound_rule = self._BOUND.format(bound=best_cost)
            section = f"bound_{round_num}"
            ctl.add(section, [], bound_rule)
            ctl.ground([(section, [])])

        total_time = time.perf_counter() - t0

        if best_s1 is None or best_s2 is None:
            print(f"  NO MODEL ({total_time:.3f}s)", flush=True)
            return None

        best_s1["ground_time"] = round(ground_time, 3)
        best_s1["time"]        = round(total_time, 3)
        best_s1["optimum"]     = optimum
        best_s1["cost"]        = best_cost
        best_s1["trajectory"]  = trajectory

        result = dict(best_s2)
        result["_stage1"]     = best_s1
        result["ground_time"] = round(ground_time, 3)
        result["time"]        = round(total_time, 3)
        result["optimum"]     = optimum
        result["cost"]        = best_cost
        result["trajectory"]  = trajectory
        return result

    def solve(self, multishot: bool = True) -> dict | None:
        """Combined solve with default s2 config (backward-compatible)."""
        return self.solve_combined(multishot=multishot)

    # ─────────────────────────────────────────────────────────────────────
    # Standalone run  (overrides BaseSolver.run for two-stage display)
    # ─────────────────────────────────────────────────────────────────────

    def run(self) -> int:
        print("=" * 60)
        print("  NAIVE TWO-STAGE SOLVER")
        print("=" * 60)

        result = self.solve()
        if result is None:
            print("\n  UNSATISFIABLE — no solution found.")
            return 1

        stage1 = result["_stage1"]
        inst   = self.instance_data

        # ── Stage 1: Route frequencies ───────────────────────────────
        print()
        print("-" * 60)
        print("  STAGE 1 — ROUTE FREQUENCIES")
        print("-" * 60)
        print(f"  Cost:     {stage1['cost']}")
        print(f"  Optimum:  {stage1['optimum']}")
        print(f"  Time:     {stage1['time']}s")
        print()

        for rf in sorted(stage1["route_freqs"],
                         key=lambda r: (r["from"], r["to"], r["tr"])):
            cap = inst["transport_cap"].get(rf["tr"], "?")
            print(f"  {rf['from']} → {rf['to']} via {rf['tr']}  "
                  f"freq={rf['freq']}  totalCap={rf['total_cap']}  "
                  f"(per-trip cap={cap})")

        # ── Stage 1: Aggregate loads ─────────────────────────────────
        print()
        print("-" * 60)
        print("  STAGE 1 — AGGREGATE LOADS")
        print("-" * 60)

        route_loads: dict[tuple, dict[str, int]] = defaultdict(dict)
        for (f, t, tr, p), n in stage1["loads"].items():
            route_loads[(f, t, tr)][p] = n

        for (f, t, tr) in sorted(route_loads):
            parts = route_loads[(f, t, tr)]
            items = ", ".join(f"{p}={n}" for p, n in sorted(parts.items()))
            print(f"  {f} → {t} via {tr}: {items}")

        if stage1["high_exposure"]:
            print()
            print(f"  High-exposure arcs: {len(stage1['high_exposure'])}")
            for (ef, et, etr, ep) in stage1["high_exposure"]:
                print(f"    {ef} → {et} via {etr}, part {ep}")

        # ── Stage 2: Per-trip packings ───────────────────────────────
        print()
        print("-" * 60)
        print("  STAGE 2 — PER-TRIP PACKINGS")
        print("-" * 60)
        print(f"  Optimum:          {result['optimum']}")
        print(f"  Time:             {result['time']}s")
        print(f"  Mono-part routes: {result['mono_count']}")
        print(f"  Concentrated:     {result['concentrated_count']}")
        print()

        trips: dict[tuple, dict[int, dict[str, int]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for (f, t, tr, p, k), q in result["trip_loads"].items():
            trips[(f, t, tr)][k][p] = q

        for (f, t, tr) in sorted(trips):
            cap = inst["transport_cap"].get(tr, "?")
            n_trips = len(trips[(f, t, tr)])
            print(f"  {f} → {t} via {tr}  (cap={cap}, {n_trips} trips used):")

            for k in sorted(trips[(f, t, tr)]):
                parts = trips[(f, t, tr)][k]
                items = ", ".join(
                    f"{q}x{p}" for p, q in sorted(parts.items())
                )
                vol = sum(
                    q * inst["part_size"].get(p, 0) for p, q in parts.items()
                )
                print(f"    trip {k}: [{items}]  (weight={vol}/{cap})")
            print()

        # ── Summary ──────────────────────────────────────────────────
        print("-" * 60)
        print("  SUMMARY")
        print("-" * 60)
        print(f"  Active routes:    {len(stage1['route_freqs'])}")
        print(f"  Non-zero loads:   {len(stage1['loads'])}")
        total_trips_used = sum(len(ks) for ks in trips.values())
        print(f"  Trips used:       {total_trips_used}")
        print(f"  S1 ground time:   {stage1['ground_time']}s")
        print(f"  S1 solve time:    {stage1['time']}s")
        print(f"  S2 ground time:   {result['ground_time']}s")
        print(f"  S2 solve time:    {result['time']}s")
        print()

        return 0

    # ─────────────────────────────────────────────────────────────────────
    # Stage 1 model extraction
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_stage1(model: clingo.Model) -> dict:
        """Extract structured data from a stage 1 answer set."""
        loads: dict[tuple, int] = {}
        route_freqs: list[dict] = []
        high_exposure: list[tuple] = []
        stage1_facts: list[str] = []

        for sym in model.symbols(shown=True):
            name = sym.name
            a    = sym.arguments

            if name == "load" and len(a) == 5:
                n  = a[0].number
                p  = str(a[1])
                tr = str(a[2])
                f  = str(a[3])
                t  = str(a[4])
                if n > 0:
                    loads[(f, t, tr, p)] = n
                stage1_facts.append(f"{sym}.")

            elif name == "routeFreq" and len(a) == 5:
                route_freqs.append({
                    "from":      str(a[0]),
                    "to":        str(a[1]),
                    "tr":        str(a[2]),
                    "freq":      a[3].number,
                    "total_cap": a[4].number,
                })
                stage1_facts.append(f"{sym}.")

            elif name == "highExposure" and len(a) == 4:
                high_exposure.append(
                    (str(a[0]), str(a[1]), str(a[2]), str(a[3]))
                )

        return {
            "loads":              loads,
            "route_freqs":        route_freqs,
            "high_exposure":      high_exposure,
            "_stage1_facts_str":  "\n".join(stage1_facts),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Stage 2 model extraction
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_stage2(model: clingo.Model) -> dict:
        """Extract structured data from a stage 2 answer set."""
        trip_loads: dict[tuple, int] = {}
        used_trips: set[tuple] = set()
        mono_parts: set[tuple] = set()
        concentrated: set[tuple] = set()

        for sym in model.symbols(shown=True):
            name = sym.name
            a    = sym.arguments

            if name == "tripLoad" and len(a) == 6:
                f, t, tr = str(a[0]), str(a[1]), str(a[2])
                p = str(a[3])
                q = a[4].number
                k = a[5].number
                if q > 0:
                    trip_loads[(f, t, tr, p, k)] = q

            elif name == "usedTrip" and len(a) == 4:
                used_trips.add(
                    (str(a[0]), str(a[1]), str(a[2]), a[3].number)
                )

            elif name == "monoTripPart" and len(a) == 4:
                mono_parts.add(
                    (str(a[0]), str(a[1]), str(a[2]), str(a[3]))
                )

            elif name == "concentratedLoad" and len(a) == 5:
                concentrated.add(
                    (str(a[0]), str(a[1]), str(a[2]), str(a[3]), a[4].number)
                )

        return {
            "trip_loads":         trip_loads,
            "used_trips":         used_trips,
            "mono_count":         len(mono_parts),
            "concentrated_count": len(concentrated),
        }
