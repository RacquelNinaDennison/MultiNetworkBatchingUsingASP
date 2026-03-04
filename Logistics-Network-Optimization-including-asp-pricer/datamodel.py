from dataclasses import dataclass, field
from typing import List, Dict


@dataclass(frozen=True)
class Location:
    name: str

    def __repr__(self):
        return self.name


@dataclass(frozen=True)
class TransportResource:
    name: str
    capacity: float
    cost: float
    emissions: float
    speed: float


@dataclass(frozen=True)
class TransportLink:
    origin: Location
    destination: Location

    def __hash__(self):
        return hash((self.origin.name, self.destination.name))

    def __eq__(self, other):
        if not isinstance(other, TransportLink):
            return False
        return self.origin == other.origin and self.destination == other.destination

    def __repr__(self):
        return f"{self.origin.name}->{self.destination.name}"


@dataclass(frozen=True)
class Route:
    transport_link: TransportLink
    transport_resource: TransportResource
    distance: float

    @property
    def origin(self):
        return self.transport_link.origin

    @property
    def destination(self):
        return self.transport_link.destination

    def __hash__(self):
        return hash((self.transport_link, self.transport_resource.name))

    def __eq__(self, other):
        if not isinstance(other, Route):
            return False
        return (
            self.transport_link == other.transport_link
            and self.transport_resource.name == other.transport_resource.name
        )


@dataclass
class Product:
    id: int
    name: str
    size: float
    value: float
    valid_transport_resources: List[str] = field(default_factory=list)
    net_supply_demand: Dict[Location, float] = field(default_factory=dict)

    def get_net_flow(self, location: Location) -> float:
        return self.net_supply_demand.get(location, 0.0)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Product):
            return False
        return self.id == other.id


@dataclass(frozen=True)
class Settings:
    co2_costs: float
    capital_costs: float

    # --- Cost Components (Flags) ---
    enable_transport: bool = True
    enable_co2: bool = True
    enable_interest: bool = True

    # --- Solver Defaults ---
    epsilon: float = 1e-6
    big_m: float = 100_000.0
    print_cutoff: float = 1e-5
