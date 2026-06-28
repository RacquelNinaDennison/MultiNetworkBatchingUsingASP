"""Console reporting — pretty-print solver results.

Solvers return data, this module formats it for human reading.
Keeps display logic out of solver implementations.
"""

from __future__ import annotations

from collections import defaultdict

from ..models import Instance, OneShotResult, Stage2Result, TwoStageResult


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


def print_stage2_packings(s2: Stage2Result, instance: Instance) -> None:
    """Display Stage 2 per-trip packings.

    Shared by the full two-stage report and the milp_flow / twostage_clingcon
    stage CLIs so every entry point shows packings identically.

    Format:
        STAGE 2 — PER-TRIP PACKINGS
          [l1 -> l2] via tr1  (cap=19, 3 trips used):
            trip 1: [p1 x5, p2 x2]  (weight=15/19)
            trip 2: [p2 x3]         (weight=9/19)
    """
    print()
    print("─" * 55)
    print("  STAGE 2 — PER-TRIP PACKINGS")
    print("─" * 55)

    # Group trip_loads by route → trip → {part: qty}
    trips: dict[tuple[str, str, str], dict[int, dict[str, int]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for (f, t, tr, p, k), q in s2.trip_loads.items():
        trips[(f, t, tr)][k][p] = q

    if not trips:
        print("  (no packings)")
        return

    for (f, t, tr) in sorted(trips):
        cap = instance.transport_capacity.get(tr, 0)
        n_trips = len(trips[(f, t, tr)])
        print(f"  [{f} -> {t}] via {tr}  (cap={cap}, {n_trips} trips used):")

        for k in sorted(trips[(f, t, tr)]):
            parts = trips[(f, t, tr)][k]
            items = ", ".join(f"{p} x{q}" for p, q in sorted(parts.items()))
            weight = sum(
                q * instance.part_size.get(p, 0) for p, q in parts.items()
            )
            print(f"    trip {k}: [{items}]  (weight={weight}/{cap})")
        print()


def print_twostage_result(result: TwoStageResult, instance: Instance) -> None:
    """Display a two-stage result with stage 1 flows and stage 2 packings.

    Format:
        STAGE 1 — ROUTE FREQUENCIES
          l1 -> l2 via tr1  freq=3  totalCap=57  (per-trip cap=19)

        STAGE 1 — AGGREGATE LOADS
          [l1 -> l2] via tr1: p1=5, p2=3

        STAGE 2 — PER-TRIP PACKINGS
          [l1 -> l2] via tr1  (cap=19, 3 trips used):
            trip 1: [5xp1, 2xp2]  (weight=15/19)
            trip 2: [3xp2]        (weight=9/19)
    """
    s1 = result.stage1
    s2 = result.stage2

    # ── Stage 1: Route frequencies ─────────────────────────────────────
    print()
    print("─" * 55)
    print("  STAGE 1 — ROUTE FREQUENCIES")
    print("─" * 55)

    if not s1.route_freqs:
        print("  (no active routes)")
    else:
        for rf in sorted(s1.route_freqs, key=lambda r: (r.origin, r.destination, r.transport)):
            cap = instance.transport_capacity.get(rf.transport, 0)
            print(f"  {rf.origin} -> {rf.destination} via {rf.transport}  "
                  f"freq={rf.frequency}  totalCap={rf.total_capacity}  "
                  f"(per-trip cap={cap})")

    # ── Stage 1: Aggregate loads ───────────────────────────────────────
    print()
    print("─" * 55)
    print("  STAGE 1 — AGGREGATE LOADS")
    print("─" * 55)

    route_loads: dict[tuple[str, str, str], dict[str, int]] = defaultdict(dict)
    for (f, t, tr, p), n in s1.loads.items():
        route_loads[(f, t, tr)][p] = n

    if not route_loads:
        print("  (no loads)")
    else:
        for (f, t, tr) in sorted(route_loads):
            parts = route_loads[(f, t, tr)]
            items = ", ".join(f"{p}={n}" for p, n in sorted(parts.items()))
            print(f"  [{f} -> {t}] via {tr}: {items}")

    if s1.high_exposure:
        print()
        print(f"  High-exposure arcs: {len(s1.high_exposure)}")
        for (ef, et, etr, ep) in s1.high_exposure:
            print(f"    {ef} -> {et} via {etr}, part {ep}")

    # ── Stage 2: Per-trip packings ─────────────────────────────────────
    print_stage2_packings(s2, instance)

    # ── Statistics ─────────────────────────────────────────────────────
    print("─" * 55)
    print("  STATISTICS")
    print("─" * 55)

    print(f"  Active routes:     {len(s1.route_freqs)}")
    print(f"  Non-zero loads:    {len(s1.loads)}")
    total_trips_used = len(s2.used_trips)
    print(f"  Trips used:        {total_trips_used}")
    print(f"  Mono-part trips:   {s2.mono_count}")
    print(f"  Concentrated:      {s2.concentrated_count}")
    print()
    print(f"  S1 ground time:    {s1.metadata.ground_time}s")
    print(f"  S1 solve time:     {s1.metadata.solve_time}s")
    print(f"  S1 total time:     {s1.metadata.total_time}s")
    print(f"  S1 optimum:        {s1.metadata.optimum}")
    print(f"  S1 cost:           {s1.metadata.cost}")
    print()
    print(f"  S2 ground time:    {s2.metadata.ground_time}s")
    print(f"  S2 solve time:     {s2.metadata.solve_time}s")
    print(f"  S2 total time:     {s2.metadata.total_time}s")
    print(f"  S2 optimum:        {s2.metadata.optimum}")
    print(f"  S2 cost:           {s2.metadata.cost}")
    print()
    print(f"  Combined time:     {result.total_time:.3f}s")
    print(f"  Both optimal:      {result.optimum}")
    print()
