"""Interactive network visualisation using pyvis.

Generates an HTML file showing the logistics network with:
- Nodes = locations (colored by role: supplier/consumer/transit)
- Edges = routes (thickness ∝ flow, labeled with transport)
- Hover tooltips showing package assignments per edge/node
"""

from __future__ import annotations

import webbrowser
from collections import defaultdict
from pathlib import Path

from pyvis.network import Network

from ..models.instance import Instance
from ..models.solution import OneShotResult, TwoStageResult


def _node_role(location: str, instance: Instance) -> str:
    """Classify location as supplier, consumer, or transit."""
    net = instance.net_demand_offer
    total = sum(v for (_, loc), v in net.items() if loc == location)
    if total > 0:
        return "supplier"
    elif total < 0:
        return "consumer"
    return "transit"


_NODE_COLORS = {
    "supplier": "#4CAF50",   # green
    "consumer": "#F44336",   # red
    "transit": "#2196F3",    # blue
}


def _build_node_title(location: str, instance: Instance) -> str:
    """Build hover tooltip for a node."""
    lines = [f"<b>{location}</b>"]
    role = _node_role(location, instance)
    lines.append(f"Role: {role}")

    for do in instance.demand_offers:
        if do.location == location:
            if do.quantity > 0:
                lines.append(f"  Supply: {do.part} × {do.quantity}")
            else:
                lines.append(f"  Demand: {do.part} × {-do.quantity}")

    return "<br>".join(lines)


def _build_edge_label_oneshot(
    origin: str, destination: str, transport: str,
    result: OneShotResult, instance: Instance,
) -> str:
    """Build visible label for an edge (one-shot result)."""
    cap = instance.transport_capacity.get(transport, "?")
    lines = [transport]

    # Packing on this arc
    packs = [p for p in result.pack
             if p.origin == origin and p.destination == destination
             and p.transport == transport and p.quantity > 0]
    freqs = [f for f in result.freq
             if f.origin == origin and f.destination == destination and f.transport == transport]

    freq_map = {f.bin_id: f.frequency for f in freqs}

    if packs:
        bins: dict[int, list] = defaultdict(list)
        for p in packs:
            bins[p.bin_id].append(p)

        for bin_id, items in sorted(bins.items()):
            freq = freq_map.get(bin_id, 0)
            if freq == 0 and not items:
                continue
            parts_str = ", ".join(f"{p.part}×{p.quantity}" for p in items)
            weight = sum(p.quantity * instance.part_size.get(p.part, 1) for p in items)
            lines.append(f"bin{bin_id}(f={freq}): {parts_str} [{weight}/{cap}]")

    return "\n".join(lines)


def _build_edge_label_twostage(
    origin: str, destination: str, transport: str,
    result: TwoStageResult, instance: Instance,
) -> str:
    """Build visible label for an edge (two-stage result)."""
    cap = instance.transport_capacity.get(transport, "?")
    lines = [transport]

    # Route frequency
    for rf in result.stage1.route_freqs:
        if rf.origin == origin and rf.destination == destination and rf.transport == transport:
            lines.append(f"freq={rf.frequency}")

    # Stage 2: per-trip packing
    trips: dict[int, list] = defaultdict(list)
    for (o, d, tr, part, trip_id), qty in result.stage2.trip_loads.items():
        if o == origin and d == destination and tr == transport and qty > 0:
            trips[trip_id].append((part, qty))

    if trips:
        for trip_id, items in sorted(trips.items()):
            parts_str = ", ".join(f"{p}×{q}" for p, q in items)
            weight = sum(q * instance.part_size.get(p, 1) for p, q in items)
            lines.append(f"trip{trip_id}: {parts_str} [{weight}/{cap}]")

    return "\n".join(lines)


def _get_edge_flow_oneshot(origin: str, destination: str, result: OneShotResult) -> int:
    """Total flow on an arc."""
    return sum(f.quantity for f in result.flow
               if f.origin == origin and f.destination == destination and f.quantity > 0)


def _get_edge_flow_twostage(origin: str, destination: str, transport: str,
                            result: TwoStageResult) -> int:
    """Total load on an arc."""
    return sum(v for (o, d, tr, _), v in result.stage1.loads.items()
               if o == origin and d == destination and tr == transport and v > 0)


def _create_network(instance: Instance) -> Network:
    """Create base pyvis Network with nodes."""
    net = Network(
        height="750px",
        width="100%",
        directed=True,
        notebook=False,
        cdn_resources="in_line",
    )
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=200)

    for loc in sorted(instance.locations):
        role = _node_role(loc, instance)
        title = _build_node_title(loc, instance)
        net.add_node(
            loc,
            label=loc,
            title=title,
            color=_NODE_COLORS[role],
            size=25,
            font={"size": 14, "face": "monospace"},
        )

    return net


def visualise_oneshot(
    result: OneShotResult,
    instance: Instance,
    output_path: Path | None = None,
    open_browser: bool = True,
) -> Path:
    """Generate interactive HTML visualisation of a one-shot solution."""
    net = _create_network(instance)

    # Compute max flow for edge width scaling
    max_flow = max(
        (_get_edge_flow_oneshot(r.origin, r.destination, result) for r in instance.routes),
        default=1,
    ) or 1

    # Add edges grouped by (origin, dest) — one per transport
    for route in instance.routes:
        flow = _get_edge_flow_oneshot(route.origin, route.destination, result)
        edge_label = _build_edge_label_oneshot(
            route.origin, route.destination, route.transport, result, instance
        )
        width = max(1, int(6 * flow / max_flow)) if flow > 0 else 1
        color = "#888888" if flow == 0 else "#333333"

        net.add_edge(
            route.origin,
            route.destination,
            label=edge_label,
            width=width,
            color=color,
            arrows="to",
            font={"size": 10, "face": "monospace", "multi": "md", "align": "middle"},
            smooth={"type": "curvedCW", "roundness": 0.2},
        )

    if output_path is None:
        output_path = Path("multibatch_solution.html")

    net.write_html(str(output_path))

    if open_browser:
        webbrowser.open(f"file://{output_path.resolve()}")

    return output_path


def visualise_twostage(
    result: TwoStageResult,
    instance: Instance,
    output_path: Path | None = None,
    open_browser: bool = True,
) -> Path:
    """Generate interactive HTML visualisation of a two-stage solution."""
    net = _create_network(instance)

    max_flow = max(
        (_get_edge_flow_twostage(r.origin, r.destination, r.transport, result)
         for r in instance.routes),
        default=1,
    ) or 1

    for route in instance.routes:
        flow = _get_edge_flow_twostage(
            route.origin, route.destination, route.transport, result
        )
        edge_label = _build_edge_label_twostage(
            route.origin, route.destination, route.transport, result, instance
        )
        width = max(1, int(6 * flow / max_flow)) if flow > 0 else 1
        color = "#888888" if flow == 0 else "#333333"

        net.add_edge(
            route.origin,
            route.destination,
            label=edge_label,
            width=width,
            color=color,
            arrows="to",
            font={"size": 10, "face": "monospace", "multi": "md", "align": "middle"},
            smooth={"type": "curvedCW", "roundness": 0.2},
        )

    if output_path is None:
        output_path = Path("multibatch_solution.html")

    net.write_html(str(output_path))

    if open_browser:
        webbrowser.open(f"file://{output_path.resolve()}")

    return output_path
