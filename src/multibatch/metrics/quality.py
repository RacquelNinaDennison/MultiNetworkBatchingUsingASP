"""Packing quality metrics — fill rate, parts per trip, dispatch costs."""

# TODO: Port compute_metrics from src/modules/run_two_stage_subprocess.py
# Operates on TwoStageResult + Instance → QualityMetrics dict


from __future__ import annotations

from ..models import Instance, TwoStageResult


def compute_quality_metrics(result: TwoStageResult, instance: Instance) -> dict:
    """Compute packing quality metrics from a two-stage solution.

    Returns dict with:
        total_trips, non_empty_trips, mono_sku_trips,
        avg/min/max_parts_per_trip, avg/min/max_fill_rate,
        s1_dispatch_cost, s2_dispatch_cost, cost_saving
    """
    # TODO: implement
    raise NotImplementedError
