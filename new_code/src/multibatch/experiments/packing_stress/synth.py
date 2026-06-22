"""Synthetic single-arc problem generator for the packing stress test.

We never run Stage 1 here. We hand-build a fixed Stage-1 flow on ONE arc plus
the minimal Instance fields that Stage 2 reads (part sizes/values, transport
capacity, route cost), then feed them straight into the real Stage-2 packing
solver.
"""

from __future__ import annotations

import math

from multibatch.models.instance import Instance, Route
from multibatch.models.solution import RouteFreq, SolveMetadata, Stage1Result

ORIGIN = "o"
DESTINATION = "d"
TRANSPORT = "tr"


def min_feasible_freq(n_parts: int, units_per_part: int, capacity: int, part_size: int) -> int:
    """Smallest number of trips that can volumetrically hold the whole load."""
    total_volume = n_parts * units_per_part * part_size
    return max(1, math.ceil(total_volume / capacity))


def make_single_arc(
    *,
    n_parts: int,
    units_per_part: int,
    capacity: int,
    part_size: int = 1,
    part_value: int = 1,
    freq: int | None = None,
    freq_slack: int = 0,
    distance: int = 10,
    route_cost: int = 1,
) -> tuple[Instance, Stage1Result]:
    """Build (Instance, Stage1Result) for one arc carrying `n_parts` parts.

    Each part has `units_per_part` units of size `part_size`; the transport has
    per-trip `capacity`. `freq` is how many trips Stage 2 packs into; if None it
    defaults to the minimum feasible frequency plus `freq_slack`.
    """
    parts = [f"p{i}" for i in range(n_parts)]
    if freq is None:
        freq = min_feasible_freq(n_parts, units_per_part, capacity, part_size) + freq_slack

    instance = Instance(
        parts=set(parts),
        locations={ORIGIN, DESTINATION},
        routes=[
            Route(
                origin=ORIGIN,
                destination=DESTINATION,
                transport=TRANSPORT,
                distance=distance,
                cost=route_cost,
            )
        ],
        demand_offers=[],  # unused by Stage 2
        transport_capacity={TRANSPORT: capacity},
        part_size={p: part_size for p in parts},
        part_value={p: part_value for p in parts},
    )

    loads = {(ORIGIN, DESTINATION, TRANSPORT, p): units_per_part for p in parts}
    stage1 = Stage1Result(
        metadata=SolveMetadata(satisfiable=True, optimum=True),
        loads=loads,
        route_freqs=[
            RouteFreq(
                origin=ORIGIN,
                destination=DESTINATION,
                transport=TRANSPORT,
                frequency=freq,
                total_capacity=freq * capacity,
            )
        ],
        high_exposure=[],
    )
    return instance, stage1
