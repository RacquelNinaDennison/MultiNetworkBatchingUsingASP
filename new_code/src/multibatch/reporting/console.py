"""Console reporting — pretty-print solver results.

Solvers return data, this module formats it for human reading.
Keeps display logic out of solver implementations.
"""

from __future__ import annotations

from ..models import Instance, OneShotResult, TwoStageResult


def print_oneshot_result(result: OneShotResult, instance: Instance) -> None:
    """Display a one-shot solver result with packing, flow, and stats."""
    # TODO: Port from base_solver.print_results
    raise NotImplementedError


def print_twostage_result(result: TwoStageResult, instance: Instance) -> None:
    """Display a two-stage result with stage 1 flows, stage 2 packings, metrics."""
    # TODO: Port from run_two_stage_naive.run() display logic
    raise NotImplementedError
