#!/usr/bin/env python3
"""
run_two_stage_subprocess.py — Two-stage pipeline using OS-level solver calls.

Measures raw wall-clock time by invoking ``clingcon`` as a subprocess for
both Stage 1 and Stage 2, with a temp file bridging the two stages.
Uses ``--outf=2`` (JSON output) for reliable parsing.

Stage 1 encoding: encoding/twostage/clingcon/stage_1_clingcon_flow.lp
Stage 2 encoding: encoding/twostage/clingcon/stage_2_packing.lp
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .base_solver import BaseSolver

# ─────────────────────────────────────────────────────────────────────────
# Encoding paths (relative to src/)
# ─────────────────────────────────────────────────────────────────────────

_SRC = Path(__file__).resolve().parent.parent
STAGE1_LP = _SRC / "encoding" / "twostage" / "clingcon" / "stage_1_clingcon_flow.lp"
STAGE2_LP = (
    _SRC / "encoding" / "twostage" / "clingcon" / "stage_2_packing.lp"
)

# ─────────────────────────────────────────────────────────────────────────
# Regex for parsing __csp atoms from JSON Value arrays
# ─────────────────────────────────────────────────────────────────────────

# __csp(load(F,T,TR,P),N)  — clingcon theory variable in JSON output
_RE_CSP_LOAD = re.compile(
    r"__csp\(load\(([^,]+),([^,]+),([^,]+),([^)]+)\),(\d+)\)"
)
# routeFreq(From, To, TR, Freq, TotalCap)  — regular shown atom
_RE_ROUTE_FREQ = re.compile(
    r"routeFreq\(([^,]+),([^,]+),([^,]+),(\d+),(\d+)\)"
)
# __csp(tripLoad(F,T,TR,P,K),V)  — clingcon theory variable for Stage 2
_RE_CSP_TRIP_LOAD = re.compile(
    r"__csp\(tripLoad\(([^,]+),([^,]+),([^,]+),([^,]+),(\d+)\),(\d+)\)"
)
# usedTrip(F,T,TR,K)
_RE_USED_TRIP = re.compile(
    r"usedTrip\(([^,]+),([^,]+),([^,]+),(\d+)\)"
)
# actualFrequency(F,T,TR,Count)
_RE_ACTUAL_FREQ = re.compile(
    r"actualFrequency\(([^,]+),([^,]+),([^,]+),(\d+)\)"
)
# highExposure(F,T,TR,P)
_RE_HIGH_EXPOSURE = re.compile(
    r"highExposure\(([^,]+),([^,]+),([^,]+),([^)]+)\)"
)
# monoTrip(F,T,TR,K)
_RE_MONO_TRIP = re.compile(
    r"monoTrip\(([^,]+),([^,]+),([^,]+),(\d+)\)"
)
# concentrated(F,T,TR,P,K)
_RE_CONCENTRATED = re.compile(
    r"concentrated\(([^,]+),([^,]+),([^,]+),([^,]+),(\d+)\)"
)


class SubprocessTwoStage(BaseSolver):
    """Two-stage solver that calls clingcon via OS subprocesses."""

    def __init__(
        self,
        instance_path: str,
        time_limit: int = 30,
        max_freq: int = 20,
        weight: int = 1,
        exposure_n: int = 3,
        stage1_encoding: str | None = None,
        stage2_encoding: str | None = None,
        threads: int = 1,
        configuration: str | None = None,
        cap_size_divide: int = 1,
    ):
        super().__init__(instance_path, time_limit)
        self.max_freq = max_freq
        self.weight = weight
        self.exposure_n = exposure_n
        self.stage1_lp = Path(stage1_encoding) if stage1_encoding else STAGE1_LP
        self.stage2_lp = Path(stage2_encoding) if stage2_encoding else STAGE2_LP
        self.threads = threads
        self.configuration = configuration
        self.cap_size_divide = cap_size_divide

    # ═════════════════════════════════════════════════════════════════════
    # Stage 1 — clingcon subprocess
    # ═════════════════════════════════════════════════════════════════════

    def run_stage1_subprocess(self) -> tuple[dict | None, float, str]:
        """Run Stage 1 via ``clingcon`` subprocess with JSON output.

        Returns ``(parsed_result, wall_clock_seconds, raw_stdout)``.
        """
        print("Calling clingcon for Stage 1...")
        cmd = [
            "clingcon",
            str(self.stage1_lp),
            str(self.instance_path),
            "-c", f"weight={self.weight}",
            "-c", f"max_freq={self.max_freq}",
            "-c", f"exposure_n={self.exposure_n}",
            "-c", "use_exposure=1",
            "-c", f"cap_size_divide={self.cap_size_divide}",
            f"--time-limit={self.time_limit}",
            "--outf=2",
            "-t", str(self.threads),
        ]
        if self.configuration:
            cmd.append(f"--configuration={self.configuration}")

        print(f"  cmd: {' '.join(cmd)}")

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.time_limit + 30,
            )
        except FileNotFoundError:
            print("  ERROR: 'clingcon' binary not found on PATH")
            return None, time.perf_counter() - t0, ""
        except subprocess.TimeoutExpired:
            print("  ERROR: subprocess hard-timeout expired")
            return None, time.perf_counter() - t0, ""

        wall_time = time.perf_counter() - t0

        if proc.stderr:
            for line in proc.stderr.strip().splitlines()[-5:]:
                print(f"  [clingcon stderr] {line}")

        result = self._parse_stage1_json(proc.stdout)
        return result, wall_time, proc.stdout

    @staticmethod
    def _extract_stage1_atoms(atoms: list[str]) -> tuple[dict, list, list]:
        """Extract loads, route_freqs, high_exposure from Stage 1 atom strings."""
        loads: dict[tuple, int] = {}
        route_freqs: list[dict] = []
        high_exposure: list[tuple] = []

        for atom_str in atoms:
            m = _RE_CSP_LOAD.match(atom_str)
            if m:
                fr, to, tr, p = m.group(1), m.group(2), m.group(3), m.group(4)
                n = int(m.group(5))
                if n > 0:
                    loads[(fr, to, tr, p)] = n
                continue

            m = _RE_ROUTE_FREQ.match(atom_str)
            if m:
                fr, to, tr = m.group(1), m.group(2), m.group(3)
                freq, total_cap = int(m.group(4)), int(m.group(5))
                route_freqs.append({
                    "from": fr, "to": to, "tr": tr,
                    "freq": freq, "total_cap": total_cap,
                })
                continue

            m = _RE_HIGH_EXPOSURE.match(atom_str)
            if m:
                high_exposure.append(
                    (m.group(1), m.group(2), m.group(3), m.group(4))
                )

        return loads, route_freqs, high_exposure

    @staticmethod
    def _parse_stage1_json(stdout: str) -> dict | None:
        """Parse clingcon JSON output (--outf=2) for Stage 1."""
        try:
            data = json.loads(stdout)
            print(data)
        except json.JSONDecodeError:
            print("  ERROR: could not parse JSON output")
            return None

        result_str = data.get("Result", "")
        if "UNSATISFIABLE" in result_str:
            return None

        calls = data.get("Call", [])
        if not calls:
            return None

        witnesses = calls[0].get("Witnesses", [])
        if not witnesses:
            return None

        last_witness = witnesses[-1]
        atoms = last_witness.get("Value", [])
        costs = last_witness.get("Costs", [])

        loads, route_freqs, high_exposure = (
            SubprocessTwoStage._extract_stage1_atoms(atoms)
        )

        cost = costs[0] if costs else None
        optimum = "OPTIMUM FOUND" in result_str

        solver_time = data.get("Time", {})

        result = {
            "loads":          loads,
            "route_freqs":    route_freqs,
            "high_exposure":  high_exposure,
            "cost":           cost,
            "optimum":        optimum,
            "time":           solver_time.get("Total"),
            "trajectory":     [],
            "solver_total":   solver_time.get("Total"),
            "solver_solve":   solver_time.get("Solve"),
            "solver_cpu":     solver_time.get("CPU"),
        }

        first_witness = witnesses[0]
        first_atoms = first_witness.get("Value", [])
        first_costs = first_witness.get("Costs", [])
        first_loads, first_route_freqs, first_high_exposure = (
            SubprocessTwoStage._extract_stage1_atoms(first_atoms)
        )
        result["first_solution"] = {
            "loads":          first_loads,
            "route_freqs":    first_route_freqs,
            "high_exposure":  first_high_exposure,
            "cost":           first_costs[0] if first_costs else None,
            "time":           first_witness.get("Time"),
        }

        return result

    # ═════════════════════════════════════════════════════════════════════
    # Bridge — Stage 1 output → Stage 2 input facts (temp .lp file)
    # ═════════════════════════════════════════════════════════════════════

    def build_stage2_facts(self, stage1: dict) -> str:
        """Convert Stage 1 result + instance data into Stage 2 input facts.

        Generates:
            totalLoad(From, To, TR, P, N).
            activeRoute(From, To, TR, Freq, PerTripCap).
            transportCapacity(TR, Cap).
            partSize(P, S).
            partVal(P, V).
            routeCost(From, To, TR, C).
        """
        inst = self.instance_data
        lines: list[str] = []

        for (fr, to, tr, p), n in sorted(stage1["loads"].items()):
            lines.append(f"totalLoad({fr},{to},{tr},{p},{n}).")

        for rf in stage1["route_freqs"]:
            per_trip_cap = inst["transport_cap"].get(rf["tr"], 0)
            lines.append(
                f"activeRoute({rf['from']},{rf['to']},{rf['tr']},"
                f"{rf['freq']},{per_trip_cap})."
            )

        for tr, cap in sorted(inst["transport_cap"].items()):
            lines.append(f"transportCapacity({tr},{cap}).")

        for p, s in sorted(inst["part_size"].items()):
            lines.append(f"partSize({p},{s}).")

        for p, v in sorted(inst["part_val"].items()):
            lines.append(f"partVal({p},{v}).")

        for (fr, to, tr), cost in sorted(inst["route_cost"].items()):
            lines.append(f"routeCost({fr},{to},{tr},{cost}).")

        return "\n".join(lines)

    # ═════════════════════════════════════════════════════════════════════
    # Stage 2 — clingcon subprocess
    # ═════════════════════════════════════════════════════════════════════

    def run_stage2_subprocess(
        self,
        facts_path: str,
        hetero_on: int = 1,
        concentrated_on: int = 1,
        stage2_encoding: str | None = None,
    ) -> tuple[dict | None, float, str]:
        """Run Stage 2 via ``clingcon`` subprocess with JSON output.

        Returns ``(parsed_result, wall_clock_seconds, raw_stdout)``.
        """
        s2_lp = Path(stage2_encoding) if stage2_encoding else self.stage2_lp
        cmd = [
            "clingcon",
            facts_path,
            str(s2_lp),
            "-c", f"weight={self.weight}",
            "-c", f"hetero_on={hetero_on}",
            "-c", f"concentrated_on={concentrated_on}",
            f"--time-limit={self.time_limit}",
            "--outf=2",
            "-t", str(self.threads),
        ]
        if self.configuration:
            cmd.append(f"--configuration={self.configuration}")

        print(f"  cmd: {' '.join(cmd)}")

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.time_limit + 30,
            )
        except FileNotFoundError:
            print("  ERROR: 'clingcon' binary not found on PATH")
            return None, time.perf_counter() - t0, ""
        except subprocess.TimeoutExpired:
            print("  ERROR: subprocess hard-timeout expired")
            return None, time.perf_counter() - t0, ""

        wall_time = time.perf_counter() - t0

        if proc.stderr:
            for line in proc.stderr.strip().splitlines()[-5:]:
                print(f"  [clingcon stderr] {line}")

        result = self._parse_stage2_json(proc.stdout)
        return result, wall_time, proc.stdout

    @staticmethod
    def _extract_stage2_atoms(atoms: list[str]) -> tuple[dict, set, dict, set, set]:
        """Extract trip_loads, used_trips, actual_freqs, mono_trips, concentrated from Stage 2 atoms."""
        trip_loads: dict[tuple, int] = {}
        used_trips: set[tuple] = set()
        actual_freqs: dict[tuple, int] = {}
        mono_trips: set[tuple] = set()
        concentrated_set: set[tuple] = set()

        for atom_str in atoms:
            m = _RE_CSP_TRIP_LOAD.match(atom_str)
            if m:
                fr, to, tr, p = m.group(1), m.group(2), m.group(3), m.group(4)
                k, v = int(m.group(5)), int(m.group(6))
                if v > 0:
                    trip_loads[(fr, to, tr, p, k)] = v
                continue

            m = _RE_USED_TRIP.match(atom_str)
            if m:
                fr, to, tr = m.group(1), m.group(2), m.group(3)
                used_trips.add((fr, to, tr, int(m.group(4))))
                continue

            m = _RE_ACTUAL_FREQ.match(atom_str)
            if m:
                fr, to, tr = m.group(1), m.group(2), m.group(3)
                actual_freqs[(fr, to, tr)] = int(m.group(4))
                continue

            m = _RE_MONO_TRIP.match(atom_str)
            if m:
                mono_trips.add(
                    (m.group(1), m.group(2), m.group(3), int(m.group(4)))
                )
                continue

            m = _RE_CONCENTRATED.match(atom_str)
            if m:
                concentrated_set.add(
                    (m.group(1), m.group(2), m.group(3),
                     m.group(4), int(m.group(5)))
                )

        return trip_loads, used_trips, actual_freqs, mono_trips, concentrated_set

    @staticmethod
    def _parse_stage2_json(stdout: str) -> dict | None:
        """Parse clingcon JSON output (--outf=2) for Stage 2."""
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            print("  ERROR: could not parse JSON output")
            return None

        result_str = data.get("Result", "")
        if "UNSATISFIABLE" in result_str:
            return None

        calls = data.get("Call", [])
        if not calls:
            return None

        witnesses = calls[0].get("Witnesses", [])
        if not witnesses:
            return None

        last_witness = witnesses[-1]
        atoms = last_witness.get("Value", [])
        costs = last_witness.get("Costs", [])

        trip_loads, used_trips, actual_freqs, mono_trips, concentrated_set = (
            SubprocessTwoStage._extract_stage2_atoms(atoms)
        )

        cost = costs[0] if costs else None
        optimum = "OPTIMUM FOUND" in result_str

        solver_time = data.get("Time", {})

        result = {
            "trip_loads":         trip_loads,
            "used_trips":         used_trips,
            "actual_freqs":       actual_freqs,
            "mono_count":         len(mono_trips),
            "concentrated_count": len(concentrated_set),
            "cost":               cost,
            "optimum":            optimum,
            "time":               solver_time.get("Total"),
            "trajectory":         [],
            "solver_total":       solver_time.get("Total"),
            "solver_solve":       solver_time.get("Solve"),
            "solver_cpu":         solver_time.get("CPU"),
        }

        first_witness = witnesses[0]
        first_atoms = first_witness.get("Value", [])
        first_costs = first_witness.get("Costs", [])
        ft_loads, ft_used, ft_freqs, ft_mono, ft_conc = (
            SubprocessTwoStage._extract_stage2_atoms(first_atoms)
        )
        result["first_solution"] = {
            "trip_loads":         ft_loads,
            "used_trips":         ft_used,
            "actual_freqs":       ft_freqs,
            "mono_count":         len(ft_mono),
            "concentrated_count": len(ft_conc),
            "cost":               first_costs[0] if first_costs else None,
            "time":               first_witness.get("Time"),
        }

        return result

    # ═════════════════════════════════════════════════════════════════════
    # Quality metrics  (computed in Python from parsed Stage 2 output)
    # ═════════════════════════════════════════════════════════════════════

    def compute_metrics(self, stage1: dict, stage2: dict) -> dict:
        inst = self.instance_data

        trip_cap: dict[tuple, int] = {}
        for rf in stage1["route_freqs"]:
            cap = inst["transport_cap"].get(rf["tr"], 0)
            for k in range(1, rf["freq"] + 1):
                trip_cap[(rf["from"], rf["to"], rf["tr"], k)] = cap

        # ── Parts per trip ────────────────────────────────────────────
        parts_per_trip: dict[tuple, set] = defaultdict(set)
        for (fr, to, tr, p, k) in stage2["trip_loads"]:
            parts_per_trip[(fr, to, tr, k)].add(p)

        trip_part_counts = [len(ps) for ps in parts_per_trip.values()]
        non_empty = [c for c in trip_part_counts if c > 0]
        mono_trips = sum(1 for c in trip_part_counts if c == 1)

        # ── Fill rate ─────────────────────────────────────────────────
        trip_volumes: dict[tuple, int] = defaultdict(int)
        for (fr, to, tr, p, k), v in stage2["trip_loads"].items():
            size = inst["part_size"].get(p, 0)
            trip_volumes[(fr, to, tr, k)] += size * v

        fill_rates: list[float] = []
        for trip_key, vol in trip_volumes.items():
            cap = trip_cap.get(trip_key, 0)
            if cap > 0:
                fill_rates.append(vol / cap)

        # ── Max single-part share per trip ────────────────────────────
        trip_part_vols: dict[tuple, dict[str, int]] = defaultdict(dict)
        for (fr, to, tr, p, k), v in stage2["trip_loads"].items():
            size = inst["part_size"].get(p, 0)
            trip_part_vols[(fr, to, tr, k)][p] = size * v

        max_shares: list[float] = []
        for trip_key, pvols in trip_part_vols.items():
            total = sum(pvols.values())
            if total > 0 and len(pvols) > 1:
                max_shares.append(max(pvols.values()) / total)

        # ── Dispatch costs ────────────────────────────────────────────
        s1_cost = 0
        for rf in stage1["route_freqs"]:
            key = (rf["from"], rf["to"], rf["tr"])
            s1_cost += rf["freq"] * inst["route_cost"].get(key, 0)

        trips_per_route: dict[tuple, set] = defaultdict(set)
        for (fr, to, tr, p, k) in stage2["trip_loads"]:
            trips_per_route[(fr, to, tr)].add(k)

        s2_cost = 0
        for (fr, to, tr), trip_ids in trips_per_route.items():
            s2_cost += len(trip_ids) * inst["route_cost"].get((fr, to, tr), 0)

        # ── Per-route breakdown ───────────────────────────────────────
        route_details: list[dict] = []
        for rf in stage1["route_freqs"]:
            key = (rf["from"], rf["to"], rf["tr"])
            s1_freq = rf["freq"]
            s2_freq = len(trips_per_route.get(key, set()))
            cost_per_trip = inst["route_cost"].get(key, 0)
            route_details.append({
                "route": f"{rf['from']}→{rf['to']} via {rf['tr']}",
                "s1_freq": s1_freq,
                "s2_freq": s2_freq,
                "saved_trips": s1_freq - s2_freq,
                "cost_per_trip": cost_per_trip,
                "s1_cost": s1_freq * cost_per_trip,
                "s2_cost": s2_freq * cost_per_trip,
            })

        return {
            "total_trips":        len(stage2["used_trips"]),
            "non_empty_trips":    len(non_empty),
            "mono_sku_trips":     mono_trips,
            "avg_parts_per_trip": round(mean(non_empty), 2) if non_empty else 0,
            "min_parts_per_trip": min(non_empty) if non_empty else 0,
            "max_parts_per_trip": max(non_empty) if non_empty else 0,
            "avg_fill_rate":      round(mean(fill_rates), 3) if fill_rates else 0,
            "min_fill_rate":      round(min(fill_rates), 3) if fill_rates else 0,
            "max_fill_rate":      round(max(fill_rates), 3) if fill_rates else 0,
            "avg_max_part_share": round(mean(max_shares), 3) if max_shares else 0,
            "s1_dispatch_cost":   s1_cost,
            "s2_dispatch_cost":   s2_cost,
            "cost_saving":        s1_cost - s2_cost,
            "route_details":      route_details,
        }

    # ═════════════════════════════════════════════════════════════════════
    # Full pipeline
    # ═════════════════════════════════════════════════════════════════════

    def solve(self) -> dict | None:
        """BaseSolver interface — delegates to ``run_pipeline``."""
        return self.run_pipeline()

    def run_pipeline(self) -> dict | None:
        """Orchestrate Stage 1 → bridge → temp file → Stage 2 with timing."""

        print("═" * 65)
        print("  SUBPROCESS TWO-STAGE PIPELINE  (clingcon --outf=2)")
        print("═" * 65)
        print()

        # ── Stage 1 ──────────────────────────────────────────────────
        print("─" * 65)
        print("  STAGE 1: Network Flow  (clingcon subprocess)")
        print("─" * 65)

        stage1, s1_time, _ = self.run_stage1_subprocess()

        if stage1 is None:
            print(f"  UNSATISFIABLE / no model found  ({s1_time:.3f}s)")
            return None

        print(f"  Active routes:  {len(stage1['route_freqs'])}")
        print(f"  Non-zero loads: {len(stage1['loads'])}")
        print(f"  Cost:           {stage1['cost']}")
        print(f"  Optimum:        {stage1['optimum']}")
        print(f"  Wall time:      {s1_time:.3f}s")
        print(f"  Solver time:    {stage1['solver_total']}s  "
              f"(solve: {stage1['solver_solve']}s)")
        print()

        # ── Bridge → temp file ───────────────────────────────────────
        t_bridge = time.perf_counter()
        facts_str = self.build_stage2_facts(stage1)
        bridge_time = time.perf_counter() - t_bridge

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".lp", prefix="s2_facts_", delete=False,
        )
        tmp.write(facts_str)
        tmp.close()
        tmp_path = tmp.name

        print(f"  Bridge facts:   {tmp_path}")
        print(f"  Bridge time:    {bridge_time:.6f}s")
        print()

        # ── Stage 2 ──────────────────────────────────────────────────
        print("─" * 65)
        print("  STAGE 2: Per-Trip Packing  (clingcon subprocess)")
        print("─" * 65)

        stage2, s2_time, _ = self.run_stage2_subprocess(tmp_path)

        Path(tmp_path).unlink(missing_ok=True)

        if stage2 is None:
            print(f"  UNSATISFIABLE / no model found  ({s2_time:.3f}s)")
            return None

        print(f"  Used trips:     {len(stage2['used_trips'])}")
        print(f"  Trip loads:     {len(stage2['trip_loads'])}")
        print(f"  Cost:           {stage2['cost']}")
        print(f"  Optimum:        {stage2['optimum']}")
        print(f"  Wall time:      {s2_time:.3f}s")
        print(f"  Solver time:    {stage2['solver_total']}s  "
              f"(solve: {stage2['solver_solve']}s)")
        print()

        # ── Per-trip packings ─────────────────────────────────────────
        self._print_packings(stage1, stage2)

        # ── Metrics ──────────────────────────────────────────────────
        print("─" * 65)
        print("  QUALITY METRICS")
        print("─" * 65)

        metrics = self.compute_metrics(stage1, stage2)

        print(f"  Total trips:         {metrics['total_trips']}")
        print(f"  Non-empty trips:     {metrics['non_empty_trips']}")
        print(f"  Mono-SKU trips:      {metrics['mono_sku_trips']}")
        print(f"  Parts per trip:      "
              f"avg={metrics['avg_parts_per_trip']}  "
              f"min={metrics['min_parts_per_trip']}  "
              f"max={metrics['max_parts_per_trip']}")
        print(f"  Fill rate:           "
              f"avg={metrics['avg_fill_rate']}  "
              f"min={metrics['min_fill_rate']}  "
              f"max={metrics['max_fill_rate']}")
        if metrics["avg_max_part_share"] > 0:
            print(f"  Max part share:      "
                  f"avg={metrics['avg_max_part_share']}  (lower = more balanced)")
        print()
        print(f"  S1 dispatch cost:    {metrics['s1_dispatch_cost']}")
        print(f"  S2 dispatch cost:    {metrics['s2_dispatch_cost']}")
        print(f"  Cost saving:         {metrics['cost_saving']}  "
              f"({round(metrics['cost_saving'] / max(1, metrics['s1_dispatch_cost']) * 100, 1)}%)")
        print()
        print("  Per-route frequency comparison:")
        for rd in metrics["route_details"]:
            saved = f"  (-{rd['saved_trips']})" if rd["saved_trips"] > 0 else ""
            print(f"    {rd['route']:>30}  "
                  f"S1: {rd['s1_freq']} trips → S2: {rd['s2_freq']} trips{saved}  "
                  f"cost: {rd['s1_cost']} → {rd['s2_cost']}")
        print()

        # ── Timing summary ───────────────────────────────────────────
        total = s1_time + bridge_time + s2_time

        print("═" * 65)
        print("  TIMING SUMMARY")
        print("═" * 65)
        print(f"  Stage 1 wall:        {s1_time:.3f}s  "
              f"(solver: {stage1['solver_total']}s)")
        print(f"  Bridge:              {bridge_time:.6f}s")
        print(f"  Stage 2 wall:        {s2_time:.3f}s  "
              f"(solver: {stage2['solver_total']}s)")
        print(f"  ─────────────────────────────")
        print(f"  Total pipeline:      {total:.3f}s")
        print()

        return {
            "_stage1":     stage1,
            "_stage2":     stage2,
            "metrics":     metrics,
            "s1_time":     round(s1_time, 3),
            "s2_time":     round(s2_time, 3),
            "bridge_time": round(bridge_time, 6),
            "total_time":  round(total, 3),
        }

    # ─────────────────────────────────────────────────────────────────
    # Display helpers
    # ─────────────────────────────────────────────────────────────────

    def _print_packings(self, stage1: dict, stage2: dict) -> None:
        """Pretty-print per-trip packings from Stage 2."""
        inst = self.instance_data

        routes: dict[tuple, dict[int, dict[str, int]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for (fr, to, tr, p, k), v in stage2["trip_loads"].items():
            routes[(fr, to, tr)][k][p] = v

        print("─" * 65)
        print("  PER-TRIP PACKINGS")
        print("─" * 65)

        for (fr, to, tr) in sorted(routes):
            cap = inst["transport_cap"].get(tr, "?")
            freq = stage2["actual_freqs"].get((fr, to, tr), "?")
            print(f"  {fr}→{to} via {tr}  "
                  f"(cap={cap}, {freq} trips used)")

            for k in sorted(routes[(fr, to, tr)]):
                parts = routes[(fr, to, tr)][k]
                items: list[str] = []
                total_vol = 0
                for p, n in sorted(parts.items()):
                    size = inst["part_size"].get(p, 0)
                    vol = size * n
                    total_vol += vol
                    items.append(f"{p}×{n} (vol {vol})")
                print(f"    trip {k}: {', '.join(items)}  | total vol={total_vol}")
            print()

    # ─────────────────────────────────────────────────────────────────
    # CLI entry point  (overrides BaseSolver.run to skip check step)
    # ─────────────────────────────────────────────────────────────────

    def run(self) -> int:
        result = self.run_pipeline()
        return 0 if result is not None else 1
