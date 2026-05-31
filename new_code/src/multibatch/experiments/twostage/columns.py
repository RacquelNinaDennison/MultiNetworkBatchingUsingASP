"""CSV column definitions for two-stage experiment results.

Single source of truth for column names and R_alpha column generation.
"""

from __future__ import annotations

from .config import ALPHA_VALUES, R_ALPHA_STRATEGIES, R_ALPHA_MODES


def r_alpha_col(strategy: str, mode: str, alpha: float) -> str:
    """Generate column name for an R_alpha variant."""
    return f"r_{strategy}_{mode}_{alpha}"


def _r_alpha_columns() -> list[str]:
    return [
        r_alpha_col(s, m, a)
        for s in R_ALPHA_STRATEGIES
        for m in R_ALPHA_MODES
        for a in ALPHA_VALUES
    ]


def _first_r_alpha_columns() -> list[str]:
    return [f"first_{c}" for c in _r_alpha_columns()]


R_ALPHA_COLUMNS = _r_alpha_columns()
FIRST_R_ALPHA_COLUMNS = _first_r_alpha_columns()

COLUMNS = [
    # Instance metadata
    "instance_name",
    "instance_type",
    "instance_size",
    "seed",
    # Post-hoc instance properties
    "n_locations",
    "n_parts",
    "n_routes",
    "n_transports",
    "density",
    "capacity_tightness",
    # Experiment parameters
    "weight",
    "exposure_n",
    "threads",
    "solver_config",
    "s2_config",
    "hetero_on",
    "concentrated_on",
    # Stage 1 results
    "nominal_cost",
    "exposure_count",
    "s1_optimal",
    "s1_time",
    "s1_trajectory",
    "s1_dispatch_cost",
    # Resilience metrics (best solution)
    "r_tr",
    "worst_arc",
    "r_1",
    "worst_trip",
    "k_1",
    "kit_bottleneck_trip",
    "kit_bottleneck_part",
    # Packing quality
    "mono_count",
    "concentrated_count",
    "s2_dispatch_cost",
    "cost_saving",
    # R_alpha columns (24 variants)
    *R_ALPHA_COLUMNS,
    # Stage 2 metadata
    "s2_optimal",
    "s2_time",
    "s2_trajectory",
    # First-solution metrics
    "first_s1_time",
    "first_s1_cost",
    "first_r_tr",
    "first_s2_time",
    "first_s2_cost",
    "first_r_1",
    "first_k_1",
    "first_mono_count",
    "first_concentrated_count",
    "first_s1_dispatch_cost",
    "first_s2_dispatch_cost",
    *FIRST_R_ALPHA_COLUMNS,
    # Status
    "status",
]
