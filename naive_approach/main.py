import clingo
import time
import sys

class IterativeSolver:
    def __init__(self, files, timeout=60, improvement_timeout=30):
        """
        files: list of ASP files to load
        timeout: total time budget in seconds
        improvement_timeout: time to wait for improvement before adding bound
        """
        self.files = files
        self.timeout = timeout
        self.improvement_timeout = improvement_timeout
        self.best_costs = None
        self.best_model = None
        self.last_improvement_time = None
        self.models_found = 0
        self.start_time = None

    def on_model(self, model):
        """Callback when solver finds a model."""
        self.models_found += 1
        self.best_costs = model.cost
        self.best_model = [str(atom) for atom in model.symbols(shown=True)]
        self.last_improvement_time = time.time()
        
        elapsed = time.time() - self.start_time
        print(f"\n--- Model #{self.models_found} found at {elapsed:.1f}s ---")
        print(f"  Costs: {self.best_costs}")
        print(f"  Shown atoms: {len(self.best_model)}")

    def solve_with_timeout(self, ctl, timeout_sec):
        """
        Solve with a timeout. Returns:
          'SAT' if optimal found
          'INTERRUPTED' if timed out (but may have model)
          'UNSAT' if no solution
        """
        result = None
        
        def on_finish(res):
            nonlocal result
            result = res
        
        self.last_improvement_time = time.time()
        
        handle = ctl.solve(
            on_model=self.on_model,
            on_finish=on_finish,
            async_=True
        )
        
        deadline = time.time() + timeout_sec
        
        while not handle.wait(1.0):
            now = time.time()
            
            # Hard timeout
            if now >= deadline:
                print(f"\n  Hard timeout ({timeout_sec}s) reached, interrupting...")
                handle.cancel()
                handle.wait()
                return 'INTERRUPTED'
            
            # Improvement timeout — if we have a model but no improvement
            if (self.best_costs is not None and 
                self.last_improvement_time is not None and
                now - self.last_improvement_time > self.improvement_timeout):
                print(f"\n  No improvement for {self.improvement_timeout}s, interrupting...")
                handle.cancel()
                handle.wait()
                return 'INTERRUPTED'
        
        if result and result.satisfiable:
            return 'SAT'
        elif result and result.unsatisfiable:
            return 'UNSAT'
        return 'INTERRUPTED'

  
    def add_cost_bound(self, ctl, costs, step):
        parts = []
        
        for i, cost in enumerate(costs):
            priority = len(costs) - 1 - i
            bound_name = f"bound_p{priority}_s{step}"
            
            # if priority == 1:
            #     # Maximize pack: negated internally, so enforce at least as good
            #     rule = (f":- #sum{{N*Size,P,ID,From,To,TR : "
            #             f"pack(N,P,ID,From,To,TR), partSize(P,Size)}} < {-cost}.")
            if priority == 0:
                # Minimize transport: strictly better
                rule = (f":- #sum{{F*Distance*Cost,ID,From,To,TR : "
                        f"freq(ID,From,To,TR,F), route(From,To,TR,Distance,Cost)}} >= {cost}.")
            else:
                rule = (f":- #sum{{F*Distance*Cost,ID,From,To,TR : "
                        f"freq(ID,From,To,TR,F), route(From,To,TR,Distance,Cost)}} < {cost}.")

            
            print(f"  Adding bound [{bound_name}]: {rule}")
            ctl.add(bound_name, [], rule)
            parts.append((bound_name, []))
        
        return parts

    def run(self):
        """Main solving loop."""
        self.start_time = time.time()
        step = 0
        ground_parts = []
        
        # Initial setup
        ctl = clingo.Control([
            "--configuration=trendy", # Unsatisfiable core based (good for optimization)
            "-t", "4,split",        # 4 threads with splitting
            "--stats"
        ])
        
        for f in self.files:
            ctl.load(f)
        
        print("=== Grounding base program ===")
        ctl.ground([("base", [])])
        
        total_deadline = self.start_time + self.timeout
        
        while True:
            remaining = total_deadline - time.time()
            if remaining <= 0:
                print("\nTotal time budget exhausted.")
                break
            
            step += 1
            print(f"\n{'='*50}")
            print(f"=== Iteration {step} | {remaining:.1f}s remaining ===")
            print(f"{'='*50}")
            
            # Ground any new bound constraints
            if ground_parts:
                print(f"  Grounding {len(ground_parts)} new bound(s)...")
                ctl.ground(ground_parts)
                ground_parts = []
            
            # Solve
            prev_best = self.best_costs
            status = self.solve_with_timeout(ctl, min(remaining, self.improvement_timeout))
            
            print(f"\n  Status: {status}")
            print(f"  Best costs so far: {self.best_costs}")
            
            if status == 'SAT':
                print("\n*** OPTIMAL solution found! ***")
                break
            
            if status == 'UNSAT' and self.best_model is None:
                print("\n*** Problem is UNSATISFIABLE ***")
                break
            
            if status == 'UNSAT' and self.best_model is not None:
                print("\n*** Previous solution was optimal (bound made it UNSAT) ***")
                break
            
            if status == 'INTERRUPTED' and self.best_costs is not None:
                # We have a solution but timed out trying to improve
                # Add the current costs as a bound to guide the next iteration
                print(f"\n  Adding cost bounds from current best...")
                ground_parts = self.add_cost_bound(ctl, self.best_costs, step)
            
            elif status == 'INTERRUPTED' and self.best_costs is None:
                print("\n  Timed out with no solution found. Try increasing timeout.")
                break
        
        # Final report
        elapsed = time.time() - self.start_time
        print(f"\n{'='*50}")
        print(f"=== FINAL REPORT ===")
        print(f"{'='*50}")
        print(f"  Total time: {elapsed:.1f}s")
        print(f"  Models found: {self.models_found}")
        print(f"  Best costs: {self.best_costs}")
        
        if self.best_model:
            print(f"\n  Best solution ({len(self.best_model)} atoms):")
            for atom in sorted(self.best_model):
                print(f"    {atom}")
        
        return self.best_model, self.best_costs


if __name__ == "__main__":
    files = sys.argv[1:] if len(sys.argv) > 1 else ["encoding_route.lp", "instances.lp"]
    
    solver = IterativeSolver(
        files=files,
        timeout=300,           
        improvement_timeout=30  
    )
    
    model, costs = solver.run()