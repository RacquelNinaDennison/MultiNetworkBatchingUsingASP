#!/usr/bin/env python3
"""
Column Generation Driver for Logistics Optimisation
====================================================

Implements the column-generation loop:

  1.  Solve the MASTER (flow + frequency) with the current packing pool
  2.  Compute shadow prices from the master solution
  3.  Solve the PRICING subproblem for each TR to find the best new packing
  4.  If the packing has negative reduced cost -> add it to the pool and go to 1
  5.  Otherwise -> converged

Uses clingcon as the solver for both master and pricing subproblems.
"""

import subprocess, re, os, tempfile
from .consts import (CLINGCON_CMD, MAX_CG_ITERATIONS,
                     MAX_PACKINGS_PER_TR, CONVERGENCE_PATIENCE)
from .Structures import Instance, MasterSolution, PackingPool
from .Pricing import Pricing


class ColumnGeneration:
    def __init__(self, master_lp, pricing_lp, instance_lp):
        """
        Args:
            master_lp:   path to master.lp   (ASP encoding)
            pricing_lp:  path to pricing.lp  (ASP encoding)
            instance_lp: path to instance.lp (problem data)
        """
        self.master_lp   = master_lp
        self.pricing_lp  = pricing_lp
        self.instance_lp = instance_lp
        self.pricer = Pricing(pricing_lp, instance_lp)

    # ────────────────────────────────────────────────────────
    #  INSTANCE PARSER
    # ────────────────────────────────────────────────────────

    def parse_instance(self):
        """Read the instance .lp file and extract facts."""
        inst = Instance()
        text = open(self.instance_lp).read()

        for m in re.finditer(r'part\((\w+)\)\.', text):
            p = m.group(1)
            if p not in inst.parts:
                inst.parts.append(p)

        for m in re.finditer(r'partSize\((\w+),\s*(\d+)\)\.', text):
            inst.part_sizes[m.group(1)] = int(m.group(2))

        for m in re.finditer(r'location\((\w+)\)\.', text):
            if m.group(1) not in inst.locations:
                inst.locations.append(m.group(1))

        for m in re.finditer(
                r'route\((\w+),\s*(\w+),\s*(\w+),\s*(\d+),\s*(\d+)\)\.', text):
            inst.routes.append((m.group(1), m.group(2), m.group(3),
                                int(m.group(4)), int(m.group(5))))

        for m in re.finditer(
                r'demandSupply\((\w+),\s*(\w+),\s*(-?\d+)\)\.', text):
            inst.demands[(m.group(1), m.group(2))] = int(m.group(3))

        for m in re.finditer(r'transportResource\((\w+)\)\.', text):
            tr = m.group(1)
            if tr not in inst.tr_list:
                inst.tr_list.append(tr)

        for m in re.finditer(
                r'transportCapacity\((\w+),\s*(\d+)\)\.', text):
            inst.tr_capacity[m.group(1)] = int(m.group(2))

        return inst

    # ────────────────────────────────────────────────────────
    #  INITIAL PACKINGS
    # ────────────────────────────────────────────────────────

    def generate_initial_packings(self, inst, pool):
        """
        Seed the pool with trivial single-item packings so the
        master is always feasible (slack handles the rest via Big-M).
        """
        for tr in inst.tr_list:
            cap = inst.tr_capacity[tr]
            for part in inst.parts:
                size = inst.part_sizes[part]
                qty = cap // size
                if qty > 0:
                    pack = {p: 0 for p in inst.parts}
                    pack[part] = qty
                    pool.add(tr, pack)
        print(f"[init] Seeded pool with {len(pool)} initial packings")

    # ────────────────────────────────────────────────────────
    #  SOLVE MASTER
    # ────────────────────────────────────────────────────────

    def solve_master(self, inst, pool):
        """
        Call clingcon on master.lp + instance.lp + pool facts.
        Returns a MasterSolution.
        """
        pool_facts = pool.to_asp_facts()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.lp',
                                         delete=False) as f:
            f.write(pool_facts)
            pool_path = f.name

        cmd = [*CLINGCON_CMD, self.master_lp, self.instance_lp, pool_path,
               "--models=1", "-q1"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        os.unlink(pool_path)

        solution = MasterSolution()
        output = result.stdout + result.stderr

        for m in re.finditer(
                r'flow\((\w+),(\w+),(\w+)\)=(\d+)', output):
            solution.flows[(m.group(1), m.group(2), m.group(3))] = int(m.group(4))

        for m in re.finditer(
                r'frequency\((\w+),(\w+),(\w+),(\w+)\)=(\d+)', output):
            solution.frequencies[(m.group(1), m.group(2),
                                  m.group(3), m.group(4))] = int(m.group(5))

        for m in re.finditer(
                r'slack\((\w+),(\w+),(\w+)\)=(\d+)', output):
            solution.slacks[(m.group(1), m.group(2), m.group(3))] = int(m.group(4))

        obj_match = re.search(r'Optimization:\s*(\d+)', output)
        if obj_match:
            solution.objective = int(obj_match.group(1))

        return solution

    # ────────────────────────────────────────────────────────
    #  COLUMN GENERATION MAIN LOOP
    # ────────────────────────────────────────────────────────

    def column_generation(self, inst):
        """Run the full column generation algorithm."""
        pool = PackingPool()

        # Step 0: seed pool with initial packings
        self.generate_initial_packings(inst, pool)

        best_cost = float('inf')
        patience  = 0

        for iteration in range(MAX_CG_ITERATIONS):
            print(f"\n{'='*60}")
            print(f"  ITERATION {iteration}")
            print(f"{'='*60}")
            print(f"  Pool size: {len(pool)}")

            # ── Step 1: Solve master ──
            sol = self.solve_master(inst, pool)

            if sol.objective is None:
                print("  [master] No solution found!")
                break

            print(f"  [master] Objective = {sol.objective}")

            for (frm, to, part), qty in sorted(sol.flows.items()):
                if qty > 0:
                    print(f"    flow({frm},{to},{part}) = {qty}")

            for (frm, to, tr, pid), freq in sorted(sol.frequencies.items()):
                if freq > 0:
                    print(f"    freq({frm},{to},{tr},{pid}) = {freq}")

            for (frm, to, part), s in sorted(sol.slacks.items()):
                if s > 0:
                    print(f"    slack({frm},{to},{part}) = {s}  <- INFEASIBLE!")

            # Check convergence
            if sol.objective < best_cost:
                best_cost = sol.objective
                patience  = 0
            else:
                patience += 1
                if patience >= CONVERGENCE_PATIENCE:
                    print(f"\n  Converged (no improvement for "
                          f"{CONVERGENCE_PATIENCE} iterations)")
                    break

            # ── Step 2: Compute shadow prices ──
            pi = self.pricer.compute_shadow_prices(sol, inst)
            print(f"  [pricing] Shadow prices: {pi}")

            # ── Step 3: Solve pricing for each TR ──
            found_new = False

            for tr in inst.tr_list:
                existing = [pack for pid, pack in pool.all_packings_for_tr(tr)]

                for attempt in range(MAX_PACKINGS_PER_TR):
                    candidate = self.pricer.solve_pricing(
                        tr, inst, pi, existing)

                    if candidate is None:
                        print(f"    [{tr}] No more feasible packings")
                        break

                    has_neg, rc = self.pricer.has_negative_reduced_cost(
                        candidate, tr, inst, pi)

                    contents = ", ".join(
                        f"{q}x{p}" for p, q in candidate.items() if q > 0)

                    if has_neg:
                        pid = pool.add(tr, candidate)
                        existing.append(candidate)
                        found_new = True
                        print(f"    [{tr}] Added {pid}: [{contents}]"
                              f"  (reduced cost ~ {rc})")
                    else:
                        print(f"    [{tr}] Rejected [{contents}]"
                              f"  (reduced cost ~ {rc} >= 0)")
                        break

            if not found_new:
                print(f"\n  Converged (no packing with negative reduced cost)")
                break

        # ── Final result ──
        print(f"\n{'='*60}")
        print(f"  FINAL RESULT")
        print(f"{'='*60}")
        print(f"  Optimal cost: {best_cost}")
        print(f"  Pool size: {len(pool)}")
        print(pool)

        return best_cost, sol, pool
