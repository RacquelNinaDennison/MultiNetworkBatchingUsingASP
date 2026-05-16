"""Solution verification checks.

Three invariants that must hold for any valid solution:
1. Flow conservation — outflow - inflow = net demand/supply at each node
2. Bin capacity — packed weight per bin ≤ transport capacity
3. Flow satisfaction — dispatched units (pack × freq) ≥ required flow
"""

from __future__ import annotations

from ..models import Instance, OneShotResult


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
