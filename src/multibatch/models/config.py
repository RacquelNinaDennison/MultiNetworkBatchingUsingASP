"""Solver configuration models.

Each solver variant has its own config with sensible defaults.
Common parameters (time_limit, max_freq) are shared via BaseConfig.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SolverType(str, Enum):
    """Available solver variants."""

    NAIVE_ONESHOT = "naive_oneshot"
    CLINGCON_ONESHOT = "clingcon_oneshot"
    TWOSTAGE_NAIVE = "twostage_naive"
    TWOSTAGE_CLINGCON = "twostage_clingcon"
    MILPFLOW_TWOSTAGE = "milpflow_twostage"

    def __str__(self) -> str:
        # So argparse renders choices/help as "naive_oneshot", not "SolverType.NAIVE_ONESHOT".
        return self.value


class BaseConfig(BaseModel):
    """Parameters common to all solvers."""

    time_limit: int = Field(default=30, description="Max solve time in seconds")
    max_freq: int = Field(default=20, description="Maximum transport frequency")


class NaiveOneShotConfig(BaseConfig):
    """Config for the pure-ASP one-shot solver."""

    num_bins: int = Field(default=1, description="Number of bin configurations per route")
    optimised: bool = Field(default=True, description="Use optimised encoding variant")


class ClingconOneShotConfig(BaseConfig):
    """Config for the clingcon one-shot solver."""

    num_bins: int = Field(default=1, description="Number of bin configurations per route")
    optimised: bool = Field(default=True, description="Use optimised encoding variant")


class TwoStageNaiveConfig(BaseConfig):
    """Config for the pure-ASP two-stage solver."""

    weight: int = Field(default=1, description="Objective weight for soft constraints")
    exposure_n: int = Field(default=3, description="High-exposure threshold")
    hetero_on: int = Field(default=1, description="Enable heterogeneity constraint (1/0)")
    concentrated_on: int = Field(default=1, description="Enable concentration penalty (1/0)")
    round_timeout: int = Field(default=30, description="Per-round timeout for multi-shot")
    multishot: bool = Field(default=True, description="Use iterative bound tightening")


class TwoStageClingconConfig(BaseConfig):
    """Config for the clingcon two-stage solver (in-process or subprocess)."""

    weight: int = Field(default=1, description="Objective weight for soft constraints")
    exposure_n: int = Field(default=3, description="High-exposure threshold")
    cap_size_divide: int = Field(default=1, description="Capacity scaling divisor")
    hetero_on: int = Field(default=1, description="Enable heterogeneity constraint (1/0)")
    concentrated_on: int = Field(default=1, description="Enable concentration penalty (1/0)")
    w_hetero: int = Field(default=1, description="Heterogeneity weight (weighted Stage-2 encoding)")
    w_conc: int = Field(default=1, description="Anti-concentration weight (weighted Stage-2 encoding)")
    round_timeout: int = Field(default=30, description="Per-round timeout for multi-shot")
    threads: int = Field(default=1, description="Solver threads")
    configuration: str | None = Field(default=None, description="Clingo configuration preset")
    stage1_encoding: str | None = Field(default=None, description="Override stage 1 .lp path")
    stage2_encoding: str | None = Field(default=None, description="Override stage 2 .lp path")
