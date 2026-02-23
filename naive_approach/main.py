import clingo

def main():
    # Load the logic program
    ctl = clingo.Control()
    ctl.load("logistics.lp")
    
    print("Grounding...")
    ctl.ground([("base", [])])
    
    print("Solving for Optimum...")
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            if model.optimality_proven:
                print("\n" + "="*40)
                print("      OPTIMAL LOGISTICS PLAN")
                print("="*40)
                
                # Group data for printing
                bins = {}
                links = []
                
                for atom in model.symbols(shown=True):
                    if atom.name == "bin_contains":
                        bid, part, n = atom.arguments
                        if n.number > 0:
                            bins.setdefault(bid.number, []).append(f"{n.number}x{part}")
                    
                    if atom.name == "transportLink":
                        bid = atom.arguments[0].arguments[0].number
                        route = atom.arguments[1].arguments
                        freq = atom.arguments[2].number
                        if freq > 0:
                            links.append(f"Route {route[0]}->{route[1]} ({route[2]}): Sending Bin {bid} x{freq} times")

                print("\n[Bin Configurations]")
                for bid, contents in bins.items():
                    print(f" Bin {bid}: {', '.join(contents)}")

                print("\n[Shipment Schedule]")
                for link in sorted(links):
                    print(f" {link}")
                
                print(f"\nTotal Cost (Optimization): {model.cost[0]}")

if __name__ == "__main__":
    main()