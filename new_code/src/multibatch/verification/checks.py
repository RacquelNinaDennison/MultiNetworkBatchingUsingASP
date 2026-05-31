"""Solution verification checks.

One-shot invariants:
1. Flow conservation — outflow - inflow = net demand/supply at each node
2. Bin capacity — packed weight per bin ≤ transport capacity
3. Flow satisfaction — dispatched units (pack × freq) ≥ required flow

Two-stage invariants:
4. Load conservation — S1 aggregate loads satisfy net demand at each node
5. Trip capacity — per-trip packed weight ≤ transport capacity
6. Load satisfaction — S2 tripLoad totals match S1 aggregate loads
"""

from __future__ import annotations

from collections import defaultdict

from ..models import Instance, OneShotResult, Stage1Result, Stage2Result


def check_flow_conservation(solution: OneShotResult, instance: Instance) -> list[str]:
    """Verify outflow - inflow = net demand/supply for every (part, location)."""
    errors: list[str] = []

    outflow: dict[tuple[str, str], int] = {}
    inflow: dict[tuple[str, str], int] = {}

    for f in solution.flow:
        key_out = (f.part, f.origin)
        key_in = (f.part, f.destination)
        outflow[key_out] = outflow.get(key_out, 0) + f.quantity
        inflow[key_in] = inflow.get(key_in, 0) + f.quantity

    net_do = instance.net_demand_offer

    for part in instance.parts:
        for loc in instance.locations:
            expected = net_do.get((part, loc), 0)
            actual = outflow.get((part, loc), 0) - inflow.get((part, loc), 0)
            if actual != expected:
                errors.append(
                    f"flow conservation FAIL part={part} loc={loc}: "
                    f"net={actual} != expected={expected}"
                )

    return errors


def check_capacity(solution: OneShotResult, instance: Instance) -> list[str]:
    """Verify packed weight per bin ≤ transport capacity."""
    errors: list[str] = []

    weight: dict[tuple[int, str, str, str], int] = {}
    for p in solution.pack:
        key = (p.bin_id, p.origin, p.destination, p.transport)
        size = instance.part_size.get(p.part, 0)
        weight[key] = weight.get(key, 0) + p.quantity * size

    for (bin_id, origin, dest, transport), total in weight.items():
        cap = instance.transport_capacity.get(transport)
        if cap is None:
            errors.append(
                f"capacity FAIL bin={bin_id} route=({origin}→{dest},{transport}): "
                f"unknown transport '{transport}'"
            )
        elif total > cap:
            errors.append(
                f"capacity FAIL bin={bin_id} route=({origin}→{dest},{transport}): "
                f"weight {total} > capacity {cap}"
            )

    return errors


def check_flow_satisfaction(solution: OneShotResult, instance: Instance) -> list[str]:
    """Verify dispatched units (pack × freq) ≥ required flow for each arc."""
    errors: list[str] = []

    freq_map: dict[tuple[int, str, str, str], int] = {}
    for f in solution.freq:
        freq_map[(f.bin_id, f.origin, f.destination, f.transport)] = f.frequency

    pack_map: dict[tuple[str, int, str, str, str], int] = {}
    for p in solution.pack:
        pack_map[(p.part, p.bin_id, p.origin, p.destination, p.transport)] = p.quantity

    bins_per_route: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for f in solution.freq:
        key = (f.origin, f.destination)
        bins_per_route.setdefault(key, []).append((f.bin_id, f.transport))

    for f in solution.flow:
        if f.quantity <= 0:
            continue

        dispatched = 0
        for (bin_id, tr) in bins_per_route.get((f.origin, f.destination), []):
            n = pack_map.get((f.part, bin_id, f.origin, f.destination, tr), 0)
            freq = freq_map.get((bin_id, f.origin, f.destination, tr), 0)
            dispatched += n * freq

        if dispatched < f.quantity:
            errors.append(
                f"flow satisfaction FAIL arc=({f.origin}→{f.destination}) "
                f"part={f.part}: dispatched {dispatched} < required {f.quantity}"
            )

    return errors


def verify_solution(solution: OneShotResult, instance: Instance) -> tuple[bool, list[str]]:
    """Run all checks. Returns (passed, list_of_errors)."""
    errors: list[str] = []
    errors.extend(check_flow_conservation(solution, instance))
    errors.extend(check_capacity(solution, instance))
    errors.extend(check_flow_satisfaction(solution, instance))
    return len(errors) == 0, errors


# ── Two-stage verification ───────────────────────────────────────────


def check_s1_load_conservation(
    stage1: Stage1Result, instance: Instance,
) -> list[str]:
    """Verify S1 loads satisfy flow conservation at every node.

    For each (part, location):
      sum of outgoing load - sum of incoming load = net demand/offer
    """
    errors: list[str] = []

    outflow: dict[tuple[str, str], int] = defaultdict(int)
    inflow: dict[tuple[str, str], int] = defaultdict(int)

    for (f, t, tr, p), qty in stage1.loads.items():
        outflow[(p, f)] += qty
        inflow[(p, t)] += qty

    net_do = instance.net_demand_offer

    for part in instance.parts:
        for loc in instance.locations:
            expected = net_do.get((part, loc), 0)
            actual = outflow.get((part, loc), 0) - inflow.get((part, loc), 0)
            if actual != expected:
                errors.append(
                    f"S1 load conservation FAIL part={part} loc={loc}: "
                    f"net={actual} != expected={expected}"
                )

    return errors


def check_s2_trip_capacity(
    stage1: Stage1Result, stage2: Stage2Result, instance: Instance,
) -> list[str]:
    """Verify per-trip packed weight ≤ transport capacity.

    For each trip (F,T,TR,K):
      sum of partSize(P) * tripLoad(F,T,TR,P,K) ≤ capacity(TR)
    """
    errors: list[str] = []

    # Build per-trip weights
    trip_weight: dict[tuple[str, str, str, int], int] = defaultdict(int)
    trip_transport: dict[tuple[str, str, str, int], str] = {}

    for (f, t, tr, p, k), qty in stage2.trip_loads.items():
        trip_key = (f, t, tr, k)
        size = instance.part_size.get(p, 1)
        trip_weight[trip_key] += qty * size
        trip_transport[trip_key] = tr

    for trip_key, weight in trip_weight.items():
        f, t, tr, k = trip_key
        cap = instance.transport_capacity.get(tr)
        if cap is None:
            errors.append(
                f"S2 capacity FAIL trip=({f},{t},{tr},k{k}): "
                f"unknown transport '{tr}'"
            )
        elif weight > cap:
            errors.append(
                f"S2 capacity FAIL trip=({f},{t},{tr},k{k}): "
                f"weight {weight} > capacity {cap}"
            )

    return errors


def check_s2_load_satisfaction(
    stage1: Stage1Result, stage2: Stage2Result,
) -> list[str]:
    """Verify S2 tripLoad totals match S1 aggregate loads.

    For each (F,T,TR,P):
      sum over K of tripLoad(F,T,TR,P,K) = load(F,T,TR,P) from S1
    """
    errors: list[str] = []

    # Sum S2 trip loads per arc-part
    s2_totals: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for (f, t, tr, p, k), qty in stage2.trip_loads.items():
        s2_totals[(f, t, tr, p)] += qty

    # Check every S1 load has matching S2 total
    for (f, t, tr, p), s1_qty in stage1.loads.items():
        s2_qty = s2_totals.get((f, t, tr, p), 0)
        if s2_qty != s1_qty:
            errors.append(
                f"S2 load satisfaction FAIL arc=({f},{t},{tr}) part={p}: "
                f"S2 total={s2_qty} != S1 load={s1_qty}"
            )

    # Check no S2 loads exist without S1 counterpart
    for (f, t, tr, p), s2_qty in s2_totals.items():
        if (f, t, tr, p) not in stage1.loads:
            errors.append(
                f"S2 load satisfaction FAIL arc=({f},{t},{tr}) part={p}: "
                f"S2 has load={s2_qty} but no S1 load exists"
            )

    return errors


def verify_twostage(
    stage1: Stage1Result,
    stage2: Stage2Result,
    instance: Instance,
) -> tuple[bool, list[str]]:
    """Run all two-stage checks. Returns (passed, list_of_errors)."""
    errors: list[str] = []
    errors.extend(check_s1_load_conservation(stage1, instance))
    errors.extend(check_s2_trip_capacity(stage1, stage2, instance))
    errors.extend(check_s2_load_satisfaction(stage1, stage2))
    return len(errors) == 0, errors
