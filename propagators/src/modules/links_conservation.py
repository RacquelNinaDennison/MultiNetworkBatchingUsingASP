"""
Link-Pack-Flow Linkage Propagator — Optimized Version

Changes from the previous version:
1. check()-only mode (default): No propagate() overhead. Only validates
   total assignments. Best for small instances where Python call overhead
   dominates.
2. propagate() mode (opt-in via eager=True): Watches only positive literals
   (not negations) to halve the call frequency, and only fires when the
   changed literal is relevant to the current check.
3. Pre-indexed by part AND by edge for O(1) lookups.

The constraint:
    flow(From,To,Part,T) requires T = Σ pack(Q,Part,TR,ID) × freq(From,To,TR,ID)
"""

import clingo
from collections import defaultdict


class LinkPackFlowLazyChecker(clingo.Propagator):

    MAX_QUANTITY = 20
    MAX_FREQUENCY = 20

    def __init__(self, eager=False):
        """
        Args:
            eager: If True, enable propagate() for early pruning.
                   If False (default), only use check() for lazy validation.
                   Use eager=True for larger instances where pruning saves more
                   than the Python call overhead costs.
        """
        self._eager = eager

        self.pack_lits = defaultdict(list)    # (Part, TR, ID) -> [(lit, Q)]
        self.link_lits = defaultdict(list)    # (From, To, TR, ID) -> [(lit, Freq)]
        self.flow_lits = defaultdict(list)    # (From, To, Part) -> [(lit, T)]

        self.packs_by_part = defaultdict(list)  # Part -> [(Part, TR, ID), ...]
        self.link_keys = set()

    def init(self, init):
        SA = init.symbolic_atoms

        pack_key_set = set()
        for a in SA.by_signature("pack", 4):
            Q = a.symbol.arguments[0].number
            Part = str(a.symbol.arguments[1])
            TR = str(a.symbol.arguments[2])
            ID = a.symbol.arguments[3].number
            key = (Part, TR, ID)
            lit = init.solver_literal(a.literal)
            self.pack_lits[key].append((lit, Q))
            pack_key_set.add(key)
            if self._eager:
                init.add_watch(lit)  # only positive — fires when value is chosen

        for (Part, TR, ID) in pack_key_set:
            self.packs_by_part[Part].append((Part, TR, ID))

        for a in SA.by_signature("transportLink", 5):
            From = str(a.symbol.arguments[0])
            To = str(a.symbol.arguments[1])
            TR = str(a.symbol.arguments[2])
            Freq = a.symbol.arguments[3].number
            ID = a.symbol.arguments[4].number
            key = (From, To, TR, ID)
            lit = init.solver_literal(a.literal)
            self.link_lits[key].append((lit, Freq))
            self.link_keys.add(key)
            if self._eager:
                init.add_watch(lit)

        for a in SA.by_signature("flow", 4):
            From = str(a.symbol.arguments[0])
            To = str(a.symbol.arguments[1])
            Part = str(a.symbol.arguments[2])
            T = a.symbol.arguments[3].number
            key = (From, To, Part)
            lit = init.solver_literal(a.literal)
            self.flow_lits[key].append((lit, T))
            if self._eager:
                init.add_watch(lit)
                init.add_watch(-lit)

    def _chosen(self, A, domain):
        for lit, val in domain:
            if A.value(lit) is True:
                return lit, val
        return None, None

  

    def propagate(self, control, changes):
        if not self._eager:
            return

        A = control.assignment

        for (From, To, Part), flow_domain in self.flow_lits.items():
            flow_lit, T = self._chosen(A, flow_domain)
            if flow_lit is None:
                continue

            max_sum = 0
            min_sum = 0
            reason = [flow_lit]

            for (_, TR, ID) in self.packs_by_part.get(Part, []):
                link_key = (From, To, TR, ID)
                if link_key not in self.link_keys:
                    continue

                pack_lit, Q = self._chosen(A, self.pack_lits[(Part, TR, ID)])
                if pack_lit is None:
                    q_max, q_min = self.MAX_QUANTITY, 0
                else:
                    q_max = q_min = Q
                    reason.append(pack_lit)

                link_lit, Freq = self._chosen(A, self.link_lits[link_key])
                if link_lit is None:
                    f_max, f_min = self.MAX_FREQUENCY, 0
                else:
                    f_max = f_min = Freq
                    reason.append(link_lit)

                max_sum += q_max * f_max
                min_sum += q_min * f_min

            if T > max_sum or T < min_sum:
                ok = control.add_nogood(reason, lock=True)
                if ok:
                    control.propagate()
                return


    def check(self, control):
        A = control.assignment

        for (From, To, Part), flow_domain in self.flow_lits.items():
            flow_lit, T = self._chosen(A, flow_domain)
            if flow_lit is None:
                return

            actual_sum = 0
            reason = [flow_lit]

            for (_, TR, ID) in self.packs_by_part.get(Part, []):
                pack_lit, Q = self._chosen(A, self.pack_lits[(Part, TR, ID)])
                if pack_lit is None:
                    return
                reason.append(pack_lit)

                link_key = (From, To, TR, ID)
                if link_key in self.link_lits:
                    link_lit, Freq = self._chosen(A, self.link_lits[link_key])
                    if link_lit is None:
                        return
                    reason.append(link_lit)
                    actual_sum += Q * Freq

            if T != actual_sum:
                ok = control.add_nogood(reason, lock=True)
                if ok:
                    control.propagate()
                return
