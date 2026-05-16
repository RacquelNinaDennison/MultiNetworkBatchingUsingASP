"""Resilience metrics — R_TR, R_1, R_alpha.

These measure worst-case supply coverage under disruption scenarios:
- R_TR: entire transport arc removed
- R_1: single trip lost
- R_alpha: fraction (1-alpha) of trips lost on an arc
"""

# TODO: Port from src/main.py (compute_r_tr, compute_r1, compute_r_alpha)
# Uses scipy.sparse.csgraph.maximum_flow for network flow computations.

from __future__ import annotations

from ..models import Instance, Stage1Result, Stage2Result


def compute_r_tr(
    stage1: Stage1Result,
    instance: Instance,
) -> tuple[float, list[dict]]:
    """Worst-case coverage when an entire arc-TR is removed."""
    # TODO: implement
    raise NotImplementedError


def compute_r1(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
) -> tuple[float, list[dict]]:
    """Worst-case coverage when a single trip is lost."""
    # TODO: implement
    raise NotImplementedError


def compute_r_alpha(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
    alpha: float = 0.2,
    mode: str = "single",
    strategy: str = "heaviest",
) -> tuple[float, list[dict]]:
    """Worst-case coverage under partial arc disruption."""
    # TODO: implement
    raise NotImplementedError
