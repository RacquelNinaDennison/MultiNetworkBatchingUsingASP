"""
Packing Capacity Propagator — Optimized Version

Enforces: Σ pack_qty × part_size ≤ capacity for each (TR, ID)

Two modes:
  eager=False (default): check()-only. Best for small instances.
  eager=True: monotone early detection via propagate(). Watches only positive
              literals since we only need to fire when a pack value is chosen.
"""

from collections import defaultdict
import clingo


class PackageCapacityPropagator(clingo.Propagator):

    def __init__(self, eager=False):
        self._eager = eager
        self.cap = {}
        self.size = {}
        self.var_lits = defaultdict(list)
        self.pkg_vars = defaultdict(list)
        self._any_lit = None

    def init(self, init):
        SA = init.symbolic_atoms

        for a in SA.by_signature("transportCapacity", 2):
            tr = str(a.symbol.arguments[0])
            cap = a.symbol.arguments[1].number
            self.cap[tr] = cap

        for a in SA.by_signature("partSize", 2):
            p = str(a.symbol.arguments[0])
            sz = a.symbol.arguments[1].number
            self.size[p] = sz

        for a in SA.by_signature("pack", 4):
            sym = a.symbol
            n = sym.arguments[0].number
            p = str(sym.arguments[1])
            tr = str(sym.arguments[2])
            id_ = (sym.arguments[3].number
                   if sym.arguments[3].type == clingo.SymbolType.Number
                   else str(sym.arguments[3]))

            var = (p, tr, id_)
            lit = init.solver_literal(a.literal)
            self.var_lits[var].append((lit, n))
            self.pkg_vars[(tr, id_)].append(var)

            if self._eager:
                init.add_watch(lit)
                init.add_watch(-lit)

            if self._any_lit is None:
                self._any_lit = lit

        for key in list(self.pkg_vars):
            self.pkg_vars[key] = list(dict.fromkeys(self.pkg_vars[key]))

    def _chosen(self, assignment, var):
        for lit, n in self.var_lits[var]:
            if assignment.value(lit) is True:
                return lit, n
        return None, None

    def check(self, control):
        A = control.assignment
        for (tr, id_), vars_ in self.pkg_vars.items():
            cap = self.cap.get(tr)
            if cap is None:
                continue
            total = 0
            reason = []
            for var in vars_:
                lit, n = self._chosen(A, var)
                if lit is None:
                    return
                p = var[0]
                total += n * self.size[p]
                reason.append(lit)
            if total > cap:
                ok = control.add_nogood(reason, lock=True)
                if ok:
                    control.propagate()
                return

    def propagate(self, control, changes):
        if not self._eager:
            return

        A = control.assignment
        for (tr, id_), vars_ in self.pkg_vars.items():
            cap = self.cap.get(tr)
            if cap is None:
                continue
            fixed_sum = 0
            reason = []
            for var in vars_:
                lit, n = self._chosen(A, var)
                if lit is None:
                    continueq1[=]
                p = var[0]
                fixed_sum += n * self.size[p]
                reason.append(lit)
            if fixed_sum > cap and reason:
                ok = control.add_nogood(reason, lock=True)
                if ok:
                    control.propagate()
                return
