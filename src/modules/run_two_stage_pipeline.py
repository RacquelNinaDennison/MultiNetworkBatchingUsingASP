#!/usr/bin/env python3
"""
run_two_stage_pipeline.py — Two-stage pipeline that reads Stage 1 from a
pre-existing clingcon JSON output file (--outf=2) and pipes the last model
with data into Stage 2 via subprocess.

Usage
-----
    from modules.run_two_stage_pipeline import RunTwoStagePipeline

    solver = RunTwoStagePipeline(
        instance_path="instances/industry/industry_instances.lp",
        json_path="src/models.json",
        time_limit=60,
        weight=1,
    )
    result = solver.solve()

Or via main.py:
    python main.py --solver twostage-pipeline \\
        -i instances/industry/industry_instances.lp \\
        --json-model src/models.json
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from .run_two_stage_subprocess import SubprocessTwoStage


class RunTwoStagePipeline(SubprocessTwoStage):
    """Two-stage solver: Stage 1 loaded from JSON file, Stage 2 via subprocess."""

    def __init__(
        self,
        instance_path: str,
        json_path: str,
        time_limit: int = 30,
        weight: int = 1,
        exposure_n: int = 3,
        stage2_encoding: str | None = None,
        threads: int = 1,
        configuration: str | None = None,
        hetero_on: int = 1,
        concentrated_on: int = 1,
        facts_path: str | None = None,
    ):
        super().__init__(
            instance_path,
            time_limit=time_limit,
            weight=weight,
            exposure_n=exposure_n,
            stage2_encoding=stage2_encoding,
            threads=threads,
            configuration=configuration,
        )
        self.json_path = Path(json_path)
        self.hetero_on = hetero_on
        self.concentrated_on = concentrated_on
        # Persistent facts file path (default: <json_stem>_stage2_facts.lp)
        if facts_path:
            self.facts_path = Path(facts_path)
        else:
            self.facts_path = self.json_path.with_name(
                self.json_path.stem + "_stage2_facts.lp"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 1 — load from JSON file
    # ─────────────────────────────────────────────────────────────────────────

    def load_stage1_from_json(self) -> dict | None:
        """Parse Stage 1 result from a pre-existing clingcon JSON output file.

        Finds the last witness that has a non-empty ``Value`` array (i.e. an
        actual model, not a lower-bound-only entry) and parses it the same way
        ``_parse_stage1_json`` does for live subprocess output.
        """
        if not self.json_path.exists():
            print(f"  ERROR: JSON file not found: {self.json_path}")
            return None

        with open(self.json_path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"  ERROR: could not parse JSON file: {e}")
                return None

        result_str = data.get("Result", "")
        if "UNSATISFIABLE" in result_str:
            print("  Stage 1 JSON: UNSATISFIABLE")
            return None

        calls = data.get("Call", [])
        if not calls:
            print("  ERROR: no Call entries in JSON")
            return None

        witnesses = calls[0].get("Witnesses", [])
        if not witnesses:
            print("  ERROR: no witnesses in JSON")
            return None

        # Use last witness that has actual atoms (non-empty Value list)
        model_witnesses = [w for w in witnesses if w.get("Value")]
        if not model_witnesses:
            print("  ERROR: no witness with Value atoms found in JSON")
            return None

        last_witness = model_witnesses[-1]
        atoms = last_witness.get("Value", [])
        costs = last_witness.get("Costs", [])

        loads, route_freqs, high_exposure = self._extract_stage1_atoms(atoms)

        cost = costs[0] if costs else None
        optimum = "OPTIMUM FOUND" in result_str

        solver_time = data.get("Time", {})

        result = {
            "loads":         loads,
            "route_freqs":   route_freqs,
            "high_exposure": high_exposure,
            "cost":          cost,
            "optimum":       optimum,
            "time":          solver_time.get("Total"),
            "trajectory":    [],
            "solver_total":  solver_time.get("Total"),
            "solver_solve":  solver_time.get("Solve"),
            "solver_cpu":    solver_time.get("CPU"),
        }

        first_witness = model_witnesses[0]
        first_atoms = first_witness.get("Value", [])
        first_costs = first_witness.get("Costs", [])
        first_loads, first_route_freqs, first_high_exposure = (
            self._extract_stage1_atoms(first_atoms)
        )
        result["first_solution"] = {
            "loads":         first_loads,
            "route_freqs":   first_route_freqs,
            "high_exposure": first_high_exposure,
            "cost":          first_costs[0] if first_costs else None,
            "time":          first_witness.get("Time"),
        }

        print(f"  Loaded {len(model_witnesses)} model witnesses from JSON")
        print(f"  Using last model — {len(loads)} non-zero loads, "
              f"{len(route_freqs)} active routes, cost={cost}")

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Full pipeline
    # ─────────────────────────────────────────────────────────────────────────

    def solve(self) -> dict | None:
        return self.run_pipeline()

    def run_pipeline(self) -> dict | None:  # type: ignore[override]
        print("═" * 65)
        print("  JSON → STAGE 2 PIPELINE")
        print("═" * 65)
        print()

        # ── Stage 1 from JSON ─────────────────────────────────────────
        print("─" * 65)
        print(f"  STAGE 1: Loading from {self.json_path.name}")
        print("─" * 65)

        t0 = time.perf_counter()
        stage1 = self.load_stage1_from_json()
        s1_load_time = time.perf_counter() - t0

        if stage1 is None:
            print(f"  Failed to load Stage 1 ({s1_load_time:.3f}s)")
            return None

        print(f"  Load time: {s1_load_time:.6f}s")
        print()

        # ── Bridge → persistent + temp file ─────────────────────────
        t_bridge = time.perf_counter()
        facts_str = self.build_stage2_facts(stage1)
        bridge_time = time.perf_counter() - t_bridge

        # Write persistent copy for inspection / reuse
        self.facts_path.write_text(facts_str)
        print(f"  Facts written: {self.facts_path}")

        # Also write to temp file for subprocess
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".lp", prefix="s2_facts_", delete=False,
        )
        tmp.write(facts_str)
        tmp.close()
        tmp_path = tmp.name

        print(f"  Bridge time:  {bridge_time:.6f}s")
        print()

        # ── Stage 2 ──────────────────────────────────────────────────
        print("─" * 65)
        print("  STAGE 2: Per-Trip Packing  (clingcon subprocess)")
        print("─" * 65)

        stage2, s2_time, _ = self.run_stage2_subprocess(
            tmp_path,
            hetero_on=self.hetero_on,
            concentrated_on=self.concentrated_on,
        )

        Path(tmp_path).unlink(missing_ok=True)

        if stage2 is None:
            print(f"  UNSATISFIABLE / no model found  ({s2_time:.3f}s)")
            print(f"  Inspect facts file for debugging: {self.facts_path}")
            return None

        first_model_time = stage2.get("first_solution", {}).get("time")
        print(f"  Used trips:       {len(stage2['used_trips'])}")
        print(f"  Trip loads:       {len(stage2['trip_loads'])}")
        print(f"  Cost:             {stage2['cost']}")
        print(f"  First model time: {first_model_time}s")
        print(f"  Optimum:          {stage2['optimum']}")
        print(f"  Wall time:        {s2_time:.3f}s")
        print(f"  Solver time:      {stage2['solver_total']}s  "
              f"(solve: {stage2['solver_solve']}s)")
        print()

        # ── Per-trip packings ─────────────────────────────────────────
        self._print_packings(stage1, stage2)

        # ── Metrics ──────────────────────────────────────────────────
        print("─" * 65)
        print("  QUALITY METRICS")
        print("─" * 65)

        metrics = self.compute_metrics(stage1, stage2)

        print(f"  Total trips:     {metrics['total_trips']}")
        print(f"  Non-empty trips: {metrics['non_empty_trips']}")
        print(f"  Mono-SKU trips:  {metrics['mono_sku_trips']}")
        print(f"  Fill rate:       avg={metrics['avg_fill_rate']}  "
              f"min={metrics['min_fill_rate']}  max={metrics['max_fill_rate']}")
        print()
        print(f"  S1 dispatch cost: {metrics['s1_dispatch_cost']}")
        print(f"  S2 dispatch cost: {metrics['s2_dispatch_cost']}")
        print(f"  Cost saving:      {metrics['cost_saving']}")
        print()

        total = s1_load_time + bridge_time + s2_time

        print("═" * 65)
        print("  TIMING SUMMARY")
        print("═" * 65)
        print(f"  S1 JSON load: {s1_load_time:.6f}s")
        print(f"  Bridge:       {bridge_time:.6f}s")
        print(f"  Stage 2:      {s2_time:.3f}s  "
              f"(solver: {stage2['solver_total']}s)")
        print(f"  ─────────────────────────")
        print(f"  Total:        {total:.3f}s")
        print()

        return {
            "_stage1":            stage1,
            "_stage2":            stage2,
            "metrics":            metrics,
            "s1_load_time":       round(s1_load_time, 6),
            "s2_time":            round(s2_time, 3),
            "s2_first_model_time": first_model_time,
            "bridge_time":        round(bridge_time, 6),
            "total_time":         round(total, 3),
        }

    def run(self) -> int:  # type: ignore[override]
        result = self.run_pipeline()
        return 0 if result is not None else 1
