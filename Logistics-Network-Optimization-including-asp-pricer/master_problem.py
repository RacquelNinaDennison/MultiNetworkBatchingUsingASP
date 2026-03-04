import logging
from pyscipopt import Model

logger = logging.getLogger(__name__)


class MasterProblem:
    r"""
    Solves the Logistics Network Optimization Master Problem (Linear Relaxation).

    Mathematical Formulation (Primal):
    ----------------------------------
    Min:
    $$ \sum_{r \in R} \sum_{B \in B_r} \lambda^B (C_{fixed} + C_{interest}) + \sum_{tl \in TL} \sum_{p \in P} M \cdot y_{tl,p} $$

    Subject To:

    1. Flow Conservation (Dual: $\pi_{l,p}$):
    $$ \forall l, p: \sum_{out} f_{tl,p} - \sum_{in} f_{tl,p} = NetSupply(l,p) $$

    2. Link Capacity / Convexity (Dual: $\mu_{tl,p}$):
    $$ \forall tl, p: -f_{tl,p} + \sum_{r} \sum_{B} \alpha_p^B \lambda^B + y_{tl,p} \ge 0 $$

    Variable Mapping:
    * $f_{tl,p}$   : `self.flow_vars[(link, product)]`
    * $y_{tl,p}$   : `self.dummy_vars[(link, product)]`
    * $\lambda^B$  : `self.pricer.pattern_registry` (Generated Columns)
    * $\pi_{l,p}$  : `self.model.getDualsolLinear(conserv_...)`
    * $\mu_{tl,p}$ : `self.model.getDualsolLinear(demand_...)`
    """

    def __init__(self, settings, locations, products, links, routes):
        self.settings = settings
        self.locations = locations
        self.products = products
        self.links = links
        self.routes = routes

        self.model = Model("LNO_Master")
        self.flow_vars = {}
        self.dummy_vars = {}
        self.demand_constraints = {}
        self.pricer = None

    def build_model(self):
        logger.info("Building Master Problem with Link Abstraction...")

        # 1. Create continuous flow variables per LINK (f_tl,p)
        for link in self.links:
            for product in self.products:
                name = f"flow_{repr(link)}_{product.name}"
                var = self.model.addVar(name=name, vtype="C", lb=0.0, obj=0.0)
                self.flow_vars[(link, product)] = var

        # 2. Flow Conservation
        for loc in self.locations:
            for prod in self.products:
                rhs = prod.get_net_flow(loc)
                incoming = [
                    self.flow_vars[(l, prod)]
                    for l in self.links
                    if l.destination == loc
                ]
                outgoing = [
                    self.flow_vars[(l, prod)] for l in self.links if l.origin == loc
                ]

                if not incoming and not outgoing and rhs == 0:
                    continue

                self.model.addCons(
                    sum(outgoing) - sum(incoming) == rhs,
                    name=f"conserv_{repr(loc)}_{prod.name}",
                )

        # 3. Link Demand Constraints
        for link in self.links:
            for product in self.products:
                flow_var = self.flow_vars[(link, product)]

                y_name = f"dummy_{repr(link)}_{product.name}"
                y_var = self.model.addVar(
                    name=y_name, vtype="C", lb=0.0, obj=self.settings.big_m
                )
                self.dummy_vars[(link, product)] = y_var

                c = self.model.addCons(
                    y_var - flow_var >= 0.0,
                    name=f"demand_{repr(link)}_{product.name}",
                    modifiable=True,
                    removable=True,
                )
                self.demand_constraints[(link, product)] = c

    def solve(self, pricer_class, mode="lp", export_lp=False):
        """
        Solves the master problem using Column Generation.
        Args:
            pricer_class: The pricer class to use (e.g. ScipKnapsackPricer).
            mode: 'lp' for continuous relaxation, 'ip' for integer solution.
            export_lp: If True, writes 'master_problem.lp' to disk before solving.
        """
        self.pricer = pricer_class(
            self.demand_constraints,
            self.products,
            self.links,
            self.routes,
            self.settings,
            mode=mode,
        )

        self.model.includePricer(self.pricer, "Pricer", "Column Generation", delay=True)

        if "ip" in mode:
            self.model.setLongintParam("limits/nodes", 1)

        if export_lp:
            logger.info("Exporting LP formulation to 'master_problem.lp'...")
            self.model.writeProblem("master_problem.lp")

        self.model.optimize()

    def print_results(self):
        status = self.model.getStatus()
        print(f"\nOptimization Status: {status}")

        if not (status == "optimal" or status == "nodelimit"):
            return

        print(f"Objective Value: {self.model.getObjVal():.2f}")

        print("\n=== 1. Generated Patterns (Lambda) ===")
        total_patterns = 0
        if self.pricer:
            total_patterns = len(self.pricer.pattern_registry)
            for var_name, data in self.pricer.pattern_registry.items():
                val = self.model.getVal(data["variable"])
                if val > self.settings.print_cutoff:
                    content = ", ".join(
                        [
                            f"{q:.0f}x {p.name}"
                            for p, q in data["pattern"].items()
                            if q > 0
                        ]
                    )
                    r = data["route"]
                    print(
                        f" {repr(r.transport_link)} ({r.transport_resource.name}): {val:.4f} units | [{content}]"
                    )

        print("\n=== 2. Unallocated Flows (y_tl,p) ===")
        found_unallocated = False
        for (link, product), y_var in self.dummy_vars.items():
            val = self.model.getVal(y_var)
            if val > self.settings.print_cutoff:
                print(
                    f" MISSING: {val:.2f} units of {product.name} on Link {repr(link)}"
                )
                found_unallocated = True

        if not found_unallocated:
            print(" All product flows successfully covered by patterns.")

        print("\n=== 3. Statistics ===")
        print(f" Total Patterns Generated: {total_patterns}")


def print_problem_stats(locations, products, links, routes):
    """
    Prints summary statistics about the loaded problem instance.
    """
    print("\n=== Problem Statistics ===")
    print(f" Locations:           {len(locations)}")
    print(f" Products:            {len(products)}")
    print(f" Transport Links:     {len(links)}")
    print(f" Total Route Options: {len(routes)}")
    print("==========================\n")
