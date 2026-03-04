import json
import os
import logging
from datamodel import (
    Location,
    TransportResource,
    Product,
    Route,
    TransportLink,
    Settings,
)

logger = logging.getLogger(__name__)


def read_problem(filename):
    if not os.path.exists(filename):
        logger.error(f"File not found: {filename}")
        return None

    try:
        with open(filename, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse JSON structure: {e}")
        return None

    # --- Settings ---
    s_data = data.get("settings", {})
    settings = Settings(
        co2_costs=s_data.get("co2Costs", 0.0),
        capital_costs=s_data.get("capitalCosts", 0.0),
    )

    # --- Locations ---
    locations_map = {
        key: Location(name=val["name"])
        for key, val in data.get("locations", {}).items()
    }
    locations = list(locations_map.values())

    # --- Transport Resources ---
    tr_map = {}
    for key, val in data.get("transportResources", {}).items():
        tr_map[key] = TransportResource(
            name=val["name"],
            capacity=val.get("capacity", 0.0),
            emissions=val.get("co2Emissions", 0.0),
            cost=val.get("cost", 0.0),
            speed=val.get("speed", 0.0),
        )

    # --- Products ---
    products = []
    for idx, (key, val) in enumerate(data.get("products", {}).items()):
        net_flow = {
            locations_map[l_k]: amt
            for l_k, amt in val.get("netSupplyDemand", {}).items()
            if l_k in locations_map
        }

        raw_valid_tr_keys = val.get("validTR", [])
        resolved_tr_names = [
            tr_map[tr_uuid].name for tr_uuid in raw_valid_tr_keys if tr_uuid in tr_map
        ]

        products.append(
            Product(
                id=idx,
                name=val["name"],
                size=val.get("size", 1.0),
                value=val.get("value", 0.0),
                valid_transport_resources=resolved_tr_names,
                net_supply_demand=net_flow,
            )
        )

    # --- Links and Routes ---
    # NEW LOGIC: Separate Links from Routes
    links = []
    routes = []

    for key, val in data.get("routes", {}).items():
        origin = locations_map.get(val.get("from"))
        dest = locations_map.get(val.get("to"))

        if not origin or not dest:
            logger.warning(f"Skipping route {key}: invalid locations.")
            continue

        # Create the Abstract Link
        link = TransportLink(origin=origin, destination=dest)
        links.append(link)

        # Create Specific Routes (Link + Resource)
        for tr_key, tr_data in val.get("transportResources", {}).items():
            if tr_key in tr_map:
                routes.append(
                    Route(
                        transport_link=link,  # Reference the link
                        distance=tr_data.get("distance", 0.0),
                        transport_resource=tr_map[tr_key],
                    )
                )

    # Return links as well, as Master Problem needs to iterate over them
    return settings, locations, products, links, routes
