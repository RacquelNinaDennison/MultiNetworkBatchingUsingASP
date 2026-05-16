"""Data models for problem instances.

An Instance represents a multi-commodity logistics network:
- Locations (warehouses, factories, customers)
- Parts (SKUs/commodities to be shipped)
- Routes connecting locations via transport resources
- Demand/supply declarations at each location
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Route(BaseModel):
    """A transport arc between two locations."""

    origin: str
    destination: str
    transport: str 
    distance: int
    cost: int 


class DemandOffer(BaseModel):
    """Supply or demand of a part at a location.

    Positive quantity = supply (offer), negative = demand.
    """

    part: str
    location: str
    quantity: int  


class Instance(BaseModel):
    """A fully parsed multi-commodity batching problem instance.

    This is the single source of truth for instance data —
    all solvers, metrics, and verification use this model.
    """

    parts: set[str] = Field(default_factory=set)
    locations: set[str] = Field(default_factory=set)
    routes: list[Route] = Field(default_factory=list)
    demand_offers: list[DemandOffer] = Field(default_factory=list)
    transport_capacity: dict[str, int] = Field(default_factory=dict)
    part_size: dict[str, int] = Field(default_factory=dict)
    part_value: dict[str, int] = Field(default_factory=dict)

    @property
    def route_cost(self) -> dict[tuple[str, str, str], int]:
        """Lookup: (origin, destination, transport) → cost per trip."""
        return {
            (r.origin, r.destination, r.transport): r.cost
            for r in self.routes
        }

    @property
    def demands(self) -> dict[tuple[str, str], int]:
        """Lookup: (part, location) → total demand quantity (positive int)."""
        result: dict[tuple[str, str], int] = {}
        for demand in self.demand_offers:
            if demand.quantity < 0:
                key = (demand.part, demand.location)
                result[key] = result.get(key, 0) + (-demand.quantity)
        return result

    @property
    def offers(self) -> dict[tuple[str, str], int]:
        """Lookup: (part, location) → total supply quantity (positive int)."""
        result: dict[tuple[str, str], int] = {}
        for do in self.demand_offers:
            if do.quantity > 0:
                key = (do.part, do.location)
                result[key] = result.get(key, 0) + do.quantity
        return result

    @property
    def net_demand_offer(self) -> dict[tuple[str, str], int]:
        """Lookup: (part, location) → net signed value (sum of all declarations)."""
        result: dict[tuple[str, str], int] = {}
        for do in self.demand_offers:
            key = (do.part, do.location)
            result[key] = result.get(key, 0) + do.quantity
        return result

    @property
    def max_capacity(self) -> int:
        """Largest transport capacity across all resources."""
        return max(self.transport_capacity.values()) if self.transport_capacity else 0

    @property
    def min_part_size(self) -> int:
        """Smallest part size."""
        return min(self.part_size.values()) if self.part_size else 1

    @property
    def max_items_per_bin(self) -> int:
        """Upper bound on items that fit in one bin."""
        if not self.transport_capacity or not self.part_size:
            return 0
        return self.max_capacity // self.min_part_size
