"""Instance parser — single place to load .lp files into Instance models.

Uses the Clingo API to ground the instance facts and extract all relevant
atoms (part/1, location/1, route/5, demandOffer/3, etc.).
"""

from __future__ import annotations

from pathlib import Path

import clingo

from ..models import Instance, Route, DemandOffer


def parse_instance(path: str | Path) -> Instance:
    """Parse an instance .lp file into a typed Instance model.

    This replaces the three separate parsing implementations that existed
    in the original codebase (base_solver, checking, run_two_stage).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Instance file not found: {path}")

    ctl = clingo.Control()
    ctl.load(str(path))
    ctl.ground([("base", [])])

    parts: set[str] = set()
    locations: set[str] = set()
    routes: list[Route] = []
    demand_offers: list[DemandOffer] = []
    transport_capacity: dict[str, int] = {}
    part_size: dict[str, int] = {}
    part_value: dict[str, int] = {}

    for atom in ctl.symbolic_atoms:
        sym = atom.symbol
        name = sym.name
        args = sym.arguments

        if name == "part" and len(args) == 1:
            parts.add(str(args[0]))

        elif name == "location" and len(args) == 1:
            locations.add(str(args[0]))

        elif name == "demandOffer" and len(args) == 3:
            demand_offers.append(DemandOffer(
                part=str(args[0]),
                location=str(args[1]),
                quantity=args[2].number,
            ))

        elif name == "transportCapacity" and len(args) == 2:
            transport_capacity[str(args[0])] = args[1].number

        elif name == "partSize" and len(args) == 2:
            part_size[str(args[0])] = args[1].number

        elif name == "partVal" and len(args) == 2:
            part_value[str(args[0])] = args[1].number

        elif name == "route" and len(args) == 5:
            routes.append(Route(
                origin=str(args[0]),
                destination=str(args[1]),
                transport=str(args[2]),
                distance=args[3].number,
                cost=args[4].number,
            ))

    return Instance(
        parts=parts,
        locations=locations,
        routes=routes,
        demand_offers=demand_offers,
        transport_capacity=transport_capacity,
        part_size=part_size,
        part_value=part_value,
    )
