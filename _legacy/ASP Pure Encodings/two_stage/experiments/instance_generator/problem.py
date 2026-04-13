import networkx as nx
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Hashable, Optional, List, Dict

@dataclass(frozen=True)
class TransportType:
    id: int = field(hash=True, repr=False)
    cost: int = field(hash=False)
    speed: int = field(hash=False)
    emissions: int = field(hash=False)
    capacity: int = field(hash=False, repr=True)
    name: str = field(hash=False, repr=True, default=None)

@dataclass
class Product:
    id: int = field(repr=False)
    name: str = field(repr=True, hash=False, default="")
    size: int = field(repr=True, default=0)
    value: int = field(repr=False, default=0)
    valid_transports: frozenset[TransportType] = field(default_factory=set, hash=False, repr=False)

    def __hash__(self):
        return hash(self.id)

@dataclass(frozen=True)
class Location:
    id: Hashable = field(repr=False, hash=True)
    name: str = field(repr=True, hash=False, default="")
    net_supply: Dict[Product, int] = field(repr=False, hash=False, default_factory=dict)

@dataclass(frozen=True)
class TransportLink:
    id: str
    location_l1: Location
    location_l2: Location
    distance: int
    transport_type: TransportType
    max_trips: Optional[int] = field(repr=True, hash=False, default=None)

@dataclass
class PackingTransport:
    transport_link: TransportLink
    product_packing: Dict[Product, int]
    nb_packing: int

class MultibatchingProblem:
    def __init__(self,
                 transport_types: List[TransportType],
                 products: List[Product],
                 locations: List[Location],
                 transport_links: List[TransportLink],
                 capital_factor: float = 0.1):
        self.transport_types = transport_types
        self.products = products
        self.locations = locations
        self.transport_links = transport_links
        self.capital_factor = capital_factor
        self.nb_products = len(self.products)
        self.nb_locations = len(self.locations)
        self.nb_transport_types = len(self.transport_types)
        self.nb_transport_links = len(self.transport_links)

        self.product_to_index = {self.products[i]: i for i in range(self.nb_products)}
        self.product_dict = {p.id: p for p in self.products}
        self.transport_types_to_index = {self.transport_types[i]: i for i in range(self.nb_transport_types)}
        self.locations_to_index = {self.locations[i]: i for i in range(self.nb_locations)}
        self.transport_links_to_index = {self.transport_links[i]: i for i in range(self.nb_transport_links)}

        self.transport_type_id_to_transport_type = {tt.id: tt for tt in self.transport_types}
        self.location_id_to_location = {loc.id: loc for loc in self.locations}

        self.loc_and_transport_type_to_transport_link = {
            (tl.location_l1.id, tl.location_l2.id, tl.transport_type.id): tl
            for tl in self.transport_links
        }

        self.transport_links_id_to_object = {tl.id: tl for tl in transport_links}
        self.locations_pos_demand = {}
        self.locations_neg_demand = {}

        for p in self.products:
            self.locations_pos_demand[p] = []
            self.locations_neg_demand[p] = []
            for l in self.locations:
                if p in l.net_supply.keys():
                    if l.net_supply[p] < 0:
                        self.locations_pos_demand[p].append(l)
                    else:
                        self.locations_neg_demand[p].append(l)

    def evaluate(self, variable: "MultibatchingSolution") -> Dict[str, float]:
        transport_cost = sum([flow.transport_link.transport_type.cost
                              * flow.transport_link.distance * flow.nb_packing
                              for flow in variable.list_flows])
        emission_co2 = sum([flow.transport_link.transport_type.emissions
                            * flow.transport_link.distance
                            * flow.nb_packing
                            for flow in variable.list_flows])
        compound = 0
        for flow in variable.list_flows:
            value = sum([p.value * flow.product_packing[p]
                         for p in flow.product_packing])
            speed = flow.transport_link.transport_type.speed
            time_val = flow.transport_link.distance / speed if speed > 0 else float('inf')

            coef = value * ((1 + self.capital_factor) ** time_val - 1)
            compound += flow.nb_packing * coef

        return {'transport': transport_cost,
                'emission': emission_co2,
                'capital': compound}

    def check_feasibility_per_product(self, verbose=False) -> bool:
        for product in self.products:
            if product.size <= 0:
                continue

            G = nx.DiGraph()
            source = 'source'
            sink = 'sink'
            G.add_nodes_from([source, sink])

            total_supply = 0
            total_demand = 0

            for loc in self.locations:
                G.add_node(loc.id)
                supply = loc.net_supply.get(product, 0)
                if supply > 0:
                    G.add_edge(source, loc.id, capacity=supply)
                    total_supply += supply
                elif supply < 0:
                    demand = -supply
                    G.add_edge(loc.id, sink, capacity=demand)
                    total_demand += demand

            if total_supply == 0:
                if verbose:
                    print(f"Product {product.id}: No supply or demand. Skipping.")
                continue

            for link in self.transport_links:
                if link.transport_type in product.valid_transports:
                    G.add_edge(link.location_l1.id, link.location_l2.id, capacity=1e15)

            try:
                max_flow_value = nx.maximum_flow_value(G, source, sink)
            except nx.NetworkXUnbounded:
                max_flow_value = float('inf')

            if max_flow_value < total_demand - 1e-9:
                if verbose:
                    print(f"Product {product.id}: Infeasible. Max flow ({max_flow_value}) < demand ({total_demand}).")
                return False
            else:
                if verbose:
                    print(f"Product {product.id}: Feasible.")

        return True

    def satisfy(self, variable: "MultibatchingSolution") -> bool:
        epsilon = 1e-6

        current_net_flows = defaultdict(float)
        for loc in self.locations:
            for product in self.products:
                current_net_flows[(loc.id, product.id)] = loc.net_supply.get(product, 0)

        for flow_item in variable.list_flows:
            link = flow_item.transport_link

            if flow_item.nb_packing < -epsilon:
                print(f"Validation Error: Negative nb_packing.")
                return False

            current_packing_volume = 0.0

            if flow_item.nb_packing > epsilon and not flow_item.product_packing:
                print(f"Validation Error: Empty packing with positive frequency.")
                return False

            for product, units in flow_item.product_packing.items():
                if units == 0:
                    continue
                if units < -epsilon:
                    return False
                if abs(units - round(units)) > epsilon:
                    print(f"Validation Error: Non-integer units.")
                    return False
                if link.transport_type not in product.valid_transports:
                    print(f"Validation Error: Incompatible transport.")
                    return False

                current_packing_volume += product.size * units

                current_net_flows[(link.location_l1.id, product.id)] -= units * flow_item.nb_packing
                current_net_flows[(link.location_l2.id, product.id)] += units * flow_item.nb_packing

            if current_packing_volume > link.transport_type.capacity + epsilon:
                print(f"Validation Error: Capacity exceeded.")
                return False

        any_imbalance = False
        for (loc_id, prod_id), net_flow in current_net_flows.items():
            if abs(net_flow) > epsilon:
                print(f"Validation Error: Flow imbalance {loc_id} {prod_id}: {net_flow}")
                any_imbalance = True

        return not any_imbalance

class MultibatchingSolution:
    def __init__(self, problem: MultibatchingProblem,
                 list_flows: List[PackingTransport]):
        self.problem = problem
        self.list_flows = list_flows

    def copy(self) -> "MultibatchingSolution":
        return MultibatchingSolution(problem=self.problem,
                                     list_flows=list(self.list_flows))
