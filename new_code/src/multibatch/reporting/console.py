"""Console reporting — pretty-print solver results.

Solvers return data, this module formats it for human reading.
Keeps display logic out of solver implementations.
"""

from __future__ import annotations

from collections import defaultdict

from ..models import Instance, OneShotResult, TwoStageResult


def print_oneshot_result(result: OneShotResult, instance: Instance) -> None:
    """Display a one-shot solver result grouped by route.

    Format:
        [l1 -> l2] via tr1 (cap=19)
          bin 1 (freq=3): p1 x4, p2 x1  (weight=15/19)
          bin 2 (freq=2): p1 x2          (weight=10/19)
    """
    # Build freq lookup: (bin_id, origin, dest, transport) → frequency
    freq_map: dict[tuple[int, str, str, str], int] = {}
    for f in result.freq:
        freq_map[(f.bin_id, f.origin, f.destination, f.transport)] = f.frequency

    # Group non-zero packs by route → bin → {part: qty}
    route_bins: dict[tuple[str, str, str], dict[int, dict[str, int]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for p in result.pack:
        if p.quantity > 0:
            route_bins[(p.origin, p.destination, p.transport)][p.bin_id][p.part] = p.quantity

    # Group non-zero flows by arc → {part: qty}
    flows: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for f in result.flow:
        if f.quantity > 0:
            flows[(f.origin, f.destination)][f.part] = f.quantity

    # Print packings
    print()
    print("─" * 55)
    print("  PACKING")
    print("─" * 55)

    if not route_bins:
        print("  (no packings)")
    else:
        for (origin, dest, tr) in sorted(route_bins):
            cap = instance.transport_capacity.get(tr, 0)
            print(f"  [{origin} -> {dest}] via {tr} (cap={cap})")

            for bin_id in sorted(route_bins[(origin, dest, tr)]):
                parts = route_bins[(origin, dest, tr)][bin_id]
                freq = freq_map.get((bin_id, origin, dest, tr), 0)

                items = ", ".join(f"{part} x{qty}" for part, qty in sorted(parts.items()))
                weight = sum(
                    qty * instance.part_size.get(part, 0)
                    for part, qty in parts.items()
                )
                print(f"    bin {bin_id} (freq={freq}): {items}  (weight={weight}/{cap})")
            print()

    # Print flows
    print("─" * 55)
    print("  FLOW")
    print("─" * 55)

    if not flows:
        print("  (no flows)")
    else:
        for (origin, dest) in sorted(flows):
            parts = flows[(origin, dest)]
            items = ", ".join(f"{part}={qty}" for part, qty in sorted(parts.items()))
            print(f"  [{origin} -> {dest}]: {items}")

    # Print stats
    print()
    print("─" * 55)
    print("  STATISTICS")
    print("─" * 55)

    nonzero_pack = [p for p in result.pack if p.quantity > 0]
    nonzero_flow = [f for f in result.flow if f.quantity > 0]
    meta = result.metadata

    print(f"  Pack atoms:    {len(result.pack)} (non-zero: {len(nonzero_pack)})")
    print(f"  Freq atoms:    {len(result.freq)}")
    print(f"  Flow atoms:    {len(result.flow)} (non-zero: {len(nonzero_flow)})")
    print(f"  Ground time:   {meta.ground_time}s")
    print(f"  Total time:    {meta.total_time}s")
    print(f"  Optimum:       {meta.optimum}")
    print()


def print_twostage_result(result: TwoStageResult, instance: Instance) -> None:
    """Display a two-stage result with stage 1 flows, stage 2 packings, metrics."""
    # TODO: implement when two-stage solvers are ported
    raise NotImplementedError
