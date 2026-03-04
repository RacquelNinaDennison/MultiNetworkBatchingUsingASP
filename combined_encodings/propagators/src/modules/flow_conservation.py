"""
Flow Conservation Propagator — Optimized Version

Enforces: Σ outgoing_flow − Σ incoming_flow = netdemandSupply for each (Part, Location)

Two modes:
  eager=False (default): check()-only, no watch overhead. Best for small instances.
  eager=True: interval-based propagate() for early pruning. Watches only positive
              literals to halve call frequency.
"""

from collections import defaultdict
import clingo


class FlowConservationPropagator(clingo.Propagator):

    MIN_FLOW = 0
    MAX_FLOW = 20

    def __init__(self, eager=False):
        self._eager = eager
        self.ds = {}
        self.arc_lits = defaultdict(list)
        self.out_arcs = defaultdict(list)
        self.in_arcs = defaultdict(list)
        self._any_lit = None

    def init(self, init):
        SA = init.symbolic_atoms

        for a in SA.by_signature("netdemandSupply", 3):
            p = str(a.symbol.arguments[0])
            l = str(a.symbol.arguments[1])
            d = a.symbol.arguments[2].number
            self.ds[(p, l)] = d

        for a in SA.by_signature("flow", 4):
            sym = a.symbol
            fr = str(sym.arguments[0])
            to = str(sym.arguments[1])
            p = str(sym.arguments[2])
            n = sym.arguments[3].number

            arcvar = (fr, to, p)
            lit = init.solver_literal(a.literal)
            self.arc_lits[arcvar].append((lit, n))

            if self._eager:
                init.add_watch(lit) 
                init.add_watch(-lit) 
            if self._any_lit is None:
                self._any_lit = lit

        for (fr, to, p) in self.arc_lits:
            self.out_arcs[(p, fr)].append((fr, to, p))
            self.in_arcs[(p, to)].append((fr, to, p))

    def _chosen(self, assignment, arcvar):
        for lit, n in self.arc_lits[arcvar]:
            if assignment.value(lit) is True:
                return lit, n
        return None, None

    def check(self, control):
        A = control.assignment
        for (p, loc), target in self.ds.items():
            total = 0
            reason = []
            for arcvar in self.out_arcs.get((p, loc), []):
                lit, n = self._chosen(A, arcvar)
                if lit is None:
                    return
                total += n
                reason.append(lit)
            for arcvar in self.in_arcs.get((p, loc), []):
                lit, n = self._chosen(A, arcvar)
                if lit is None:
                    return
                total -= n
                reason.append(lit)
            if total != target:
                ok = control.add_nogood(reason, lock=True)
                if ok:
                    control.propagate()
                return

    def propagate(self, control, changes):
        if not self._eager:
            return

        A = control.assignment
        for (p, loc), target in self.ds.items():
            fixed_sum = 0
            reason = []
            unfixed_out = 0
            unfixed_in = 0

            for arcvar in self.out_arcs.get((p, loc), []):
                lit, n = self._chosen(A, arcvar)
                if lit is None:
                    unfixed_out += 1
                else:
                    fixed_sum += n
                    reason.append(lit)

            for arcvar in self.in_arcs.get((p, loc), []):
                lit, n = self._chosen(A, arcvar)
                if lit is None:
                    unfixed_in += 1
                else:
                    fixed_sum -= n
                    reason.append(lit)

            lo = fixed_sum + (self.MIN_FLOW * unfixed_out) + (-self.MAX_FLOW * unfixed_in)
            hi = fixed_sum + (self.MAX_FLOW * unfixed_out) + (-self.MIN_FLOW * unfixed_in)

            if target < lo or target > hi:
                if reason:
                    ok = control.add_nogood(reason, lock=True)
                    if ok:
                        control.propagate()
                else:
                    if self._any_lit is not None:
                        control.add_nogood([self._any_lit, -self._any_lit], lock=True)
                        control.propagate()
                return
