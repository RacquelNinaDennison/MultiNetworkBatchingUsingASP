import subprocess, re, os, tempfile
from .consts import CLINGCON_CMD


class Pricing:
    def __init__(self, pricing_lp, instance_lp):
        """
        Args:
            pricing_lp:  path to pricing.lp
            instance_lp: path to instance.lp
        """
        self.pricing_lp  = pricing_lp
        self.instance_lp = instance_lp

    def compute_shadow_prices(self, sol, inst):
        """
        Compute shadow prices pi_p for each part, aggregated across
        all edges.

        For each edge where a part has nonzero flow, the marginal
        cost of transporting one unit is approximated by the per-unit
        cost on that edge.  We sum across all edges weighted by the
        flow amount to get a global importance weight for each part.

        pi_p = sum over edges with flow(e,p)>0:
                  (total_cost_on_edge / total_flow_on_edge) * flow(e,p)
        """
        pi = {p: 0 for p in inst.parts}

        # Compute total frequency cost per edge
        edge_cost = {}
        for (frm, to, tr, pid), freq in sol.frequencies.items():
            if freq <= 0:
                continue
            rc = inst.route_cost(frm, to, tr)
            if rc is not None:
                edge_cost.setdefault((frm, to), 0)
                edge_cost[(frm, to)] += freq * rc

        # Compute total flow per edge
        edge_flow = {}
        for (frm, to, part), qty in sol.flows.items():
            if qty > 0:
                edge_flow.setdefault((frm, to), 0)
                edge_flow[(frm, to)] += qty

        # Shadow price per part
        for (frm, to, part), qty in sol.flows.items():
            if qty <= 0:
                continue
            total_flow = edge_flow.get((frm, to), 1)
            total_cost = edge_cost.get((frm, to), 0)
            if total_flow > 0:
                cost_per_unit = total_cost / total_flow
                pi[part] += cost_per_unit * qty

        # Scale to integers (clingcon needs integer coefficients)
        max_pi = max(pi.values()) if pi.values() else 1
        if max_pi > 0:
            scale = 100.0 / max_pi
            pi = {p: max(1, int(v * scale)) for p, v in pi.items()}
        else:
            pi = {p: 1 for p in inst.parts}

        return pi

    def build_nogood(self, packing, idx, parts, max_items=20):
        """
        Build ASP+clingcon rules to exclude a specific packing.

        For packing #idx with pack(p1)=Q1, pack(p2)=Q2, ...:
          differ_idx_p1 :- &sum{ pack(p1) } >= Q1+1.
          differ_idx_p1 :- &sum{ pack(p1) } <= Q1-1.
          ...
          :- not differ_idx_p1, not differ_idx_p2, ...

        Forces at least one part quantity to differ.
        """
        rules = []
        atoms = []

        for part in parts:
            qty = packing.get(part, 0)
            atom = f"differ_{idx}_{part}"
            atoms.append(atom)

            if qty < max_items:
                rules.append(f"{atom} :- &sum{{ pack({part}) }} >= {qty + 1}.")
            if qty > 0:
                rules.append(f"{atom} :- &sum{{ pack({part}) }} <= {qty - 1}.")

        # At least one must differ
        body = ", ".join(f"not {a}" for a in atoms)
        rules.append(f":- {body}.")

        return "\n".join(rules)

    def solve_pricing(self, tr, inst, shadow_prices, existing_packings):
        """
        Call clingcon on pricing.lp + instance + injected facts.
        Returns a packing dict {part: qty} or None if UNSAT.

        existing_packings: list of {part: qty} dicts already in pool for this TR
        """
        inject = []
        inject.append(f"targetTR({tr}).")
        for part, pi in shadow_prices.items():
            inject.append(f"shadowPrice({part}, {pi}).")

        for idx, prev in enumerate(existing_packings):
            inject.append(self.build_nogood(prev, idx, inst.parts))

        with tempfile.NamedTemporaryFile(mode='w', suffix='.lp',
                                         delete=False) as f:
            f.write("\n".join(inject))
            inject_path = f.name

        cmd = [*CLINGCON_CMD, self.pricing_lp, self.instance_lp, inject_path,
               "--models=1", "-q1"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        os.unlink(inject_path)

        output = result.stdout + result.stderr

        if "UNSATISFIABLE" in output:
            return None

        packing = {p: 0 for p in inst.parts}
        for m in re.finditer(r'pack\((\w+)\)=(\d+)', output):
            packing[m.group(1)] = int(m.group(2))

        if sum(packing.values()) == 0:
            return None

        return packing

    def has_negative_reduced_cost(self, packing, tr, inst, shadow_prices):
        """
        Check if this packing has negative reduced cost on any route
        using transport resource TR.

        reduced_cost(B, r) = tripCost(r) - sum_p alpha^B_p * pi_p

        If negative for any route -> packing is worth adding.
        """
        packing_value = sum(
            packing.get(p, 0) * shadow_prices.get(p, 0)
            for p in inst.parts
        )

        for frm, to, tr_r, d, c in inst.routes:
            if tr_r != tr:
                continue
            trip_cost = d * c
            scaled_trip_cost = trip_cost * 10
            reduced_cost = scaled_trip_cost - packing_value

            if reduced_cost < 0:
                return True, reduced_cost

        return False, 0
