"""Data models for solver outputs.

All solvers produce typed results. One-shot solvers return OneShotResult;
two-stage solvers return TwoStageResult containing Stage1Result + Stage2Result.

These models replace the ad-hoc dicts used in the original codebase,
giving consistent field names and type safety.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared metadata
# ─────────────────────────────────────────────────────────────────────────────


class SolveMetadata(BaseModel):
    """Timing and optimality info attached to any solve result."""

    ground_time: float = 0.0
    total_time: float = 0.0
    optimum: bool = False
    cost: int | None = None
    trajectory: list[dict] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# One-shot solver atoms
# ─────────────────────────────────────────────────────────────────────────────


class PackAtom(BaseModel):
    """pack(N, Part, BinID, From, To, Transport) — items packed in a bin."""

    quantity: int
    part: str
    bin_id: int
    origin: str
    destination: str
    transport: str


class FreqAtom(BaseModel):
    """freq(BinID, From, To, Transport, F) — dispatch frequency of a bin."""

    bin_id: int
    origin: str
    destination: str
    transport: str
    frequency: int


class FlowAtom(BaseModel):
    """flow(From, To, Part, N) — aggregate flow on an arc."""

    origin: str
    destination: str
    part: str
    quantity: int


class OneShotResult(BaseModel):
    """Result from a one-shot solver (naive or clingcon)."""

    metadata: SolveMetadata
    pack: list[PackAtom] = Field(default_factory=list)
    freq: list[FreqAtom] = Field(default_factory=list)
    flow: list[FlowAtom] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Two-stage solver atoms
# ─────────────────────────────────────────────────────────────────────────────


class RouteFreq(BaseModel):
    """An active route with its assigned frequency from Stage 1."""

    origin: str
    destination: str
    transport: str
    frequency: int
    total_capacity: int  # freq × per-trip capacity


class Stage1Result(BaseModel):
    """Stage 1 output: aggregate network flow + frequency assignment.

    loads: (origin, dest, transport, part) → quantity allocated on that arc.
    """

    metadata: SolveMetadata
    loads: dict[tuple[str, str, str, str], int] = Field(default_factory=dict)
    route_freqs: list[RouteFreq] = Field(default_factory=list)
    high_exposure: list[tuple[str, str, str, str]] = Field(default_factory=list)


class TripLoad(BaseModel):
    """A single part allocation on a specific trip."""

    origin: str
    destination: str
    transport: str
    part: str
    trip_id: int
    quantity: int


class Stage2Result(BaseModel):
    """Stage 2 output: per-trip bin packing with diversification.

    trip_loads: (origin, dest, transport, part, trip_id) → quantity.
    """

    metadata: SolveMetadata
    trip_loads: dict[tuple[str, str, str, str, int], int] = Field(default_factory=dict)
    used_trips: set[tuple[str, str, str, int]] = Field(default_factory=set)
    mono_count: int = 0
    concentrated_count: int = 0


class TwoStageResult(BaseModel):
    """Combined result from a two-stage solver."""

    stage1: Stage1Result
    stage2: Stage2Result

    @property
    def total_time(self) -> float:
        return self.stage1.metadata.total_time + self.stage2.metadata.total_time

    @property
    def optimum(self) -> bool:
        return self.stage1.metadata.optimum and self.stage2.metadata.optimum
