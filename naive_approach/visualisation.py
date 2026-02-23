import sys
import argparse
import clingo
from graphviz import Digraph
from collections import defaultdict

def extract_data(model):
    """Dynamically extracts all facts and decisions from the clingo model."""
    data = {
        'locations': set(),
        'parts': set(),
        'part_sizes': {},
        'tr_caps': {},
        'raw_demands': {}, # (part, location) -> demand
        'flows': {},       # (from, to, part) -> amount
        'bins': defaultdict(dict), # bin_id -> {part: qty}
        'links': []        # list of (bin_id, from, to, tr, freq)
    }

    # Use atoms=True to capture base facts even if they aren't in #show
    for atom in model.symbols(atoms=True):
        name = atom.name
        args = atom.arguments
        
        if name == "location":
            data['locations'].add(str(args[0]))
        elif name == "part":
            data['parts'].add(str(args[0]))
        elif name == "partSize":
            data['part_sizes'][str(args[0])] = args[1].number
        elif name == "transportCapacity":
            data['tr_caps'][str(args[0])] = args[1].number
        elif name == "demandOffer":
            data['raw_demands'][(str(args[0]), str(args[1]))] = args[2].number
        elif name == "flow":
            data['flows'][(str(args[0]), str(args[1]), str(args[2]))] = args[3].number
        elif name == "bin_contains":
            bid, p, n = args[0].number, str(args[1]), args[2].number
            data['bins'][bid][p] = n
        elif name == "transportLink":
            # Handles transportLink(assigned_packings(ID), route(F,T,TR,D,C), Freq)
            bid = args[0].arguments[0].number
            f, t, tr = str(args[1].arguments[0]), str(args[1].arguments[1]), str(args[1].arguments[2])
            freq = args[2].number
            data['links'].append((bid, f, t, tr, freq))

    return data

def run_audit(data):
    """Mathematically verifies the constraints of the logistical model."""
    print("\n" + "="*50)
    print("      MATHEMATICAL VERIFICATION AUDIT")
    print("="*50)
    all_passed = True

    # --- CHECK 1: Capacity Constraint (Equation 31) ---
    print("\n[Check 1] Transport Capacity Constraint...")
    check_1 = True
    for bid, f, t, tr, freq in data['links']:
        if freq > 0:
            weight = sum(data['bins'][bid].get(p, 0) * data['part_sizes'].get(p, 0) for p in data['bins'][bid])
            cap = data['tr_caps'].get(tr, float('inf'))
            if weight > cap:
                print(f" ❌ FAIL: Bin {bid} on {tr} exceeds capacity! (Weight: {weight}, Cap: {cap})")
                check_1 = all_passed = False
    if check_1: print(" ✅ PASS: All transport links strictly respect resource capacities.")

    # --- CHECK 2: Flow Conservation (Equation 27) ---
    print("\n[Check 2] Flow Conservation (Net Supply/Demand)...")
    check_2 = True
    for p in data['parts']:
        for l in data['locations']:
            flow_out = sum(n for (f, t, part), n in data['flows'].items() if f == l and part == p)
            flow_in = sum(n for (f, t, part), n in data['flows'].items() if t == l and part == p)
            net_flow = flow_out - flow_in
            required_demand = data['raw_demands'].get((p, l), 0)
            
            if net_flow != required_demand:
                print(f" ❌ FAIL: Node {l} for part {p}. Net Flow ({net_flow}) != Required ({required_demand})")
                check_2 = all_passed = False
    if check_2: print(" ✅ PASS: Flow is perfectly conserved across all nodes for all parts.")

    # --- CHECK 3: Packing Matches Flow (Equation 28) ---
    print("\n[Check 3] Packed Items Match Route Flow...")
    check_3 = True
    for (f, t, p), required_flow in data['flows'].items():
        if required_flow > 0:
            packed_amount = sum(data['bins'][bid].get(p, 0) * freq 
                                for bid, lf, lt, tr, freq in data['links'] if lf == f and lt == t)
            if packed_amount < required_flow:
                print(f" ❌ FAIL: Route {f}->{t} for part {p}. Packed ({packed_amount}) < Flow ({required_flow})")
                check_3 = all_passed = False
    if check_3: print(" ✅ PASS: All required flows are physically packed into bins.")

    print("\n" + "="*50)
    if all_passed: print(" 🏆 MODEL AUDIT SUCCESSFUL")
    else: print(" 🚨 MODEL AUDIT FAILED")
    print("="*50 + "\n")

def generate_graph(data, filename):
    """Generates a Graphviz PDF mapping the logistics flow."""
    dot = Digraph(comment='Logistics Network', format='pdf')
    dot.attr(rankdir='LR', size='12,8') # Left-to-Right topology
    
    # 1. Add Nodes
    # Identify which nodes are actively used in routes
    active_nodes = set()
    for _, f, t, _, freq in data['links']:
        if freq > 0: active_nodes.update([f, t])
        
    for l in data['locations']:
        # Format the demand labels for the node
        node_demands = [f"{p}: {d}" for (p, loc), d in data['raw_demands'].items() if loc == l and d != 0]
        
        if node_demands:
            # Producer or Consumer (Grey Node)
            d_str = "<BR/>".join(node_demands)
            label = f"<<TABLE BORDER='0' CELLBORDER='0' CELLSPACING='0'><TR><TD><FONT POINT-SIZE='16'>{l}</FONT></TD><TD ALIGN='LEFT'><FONT POINT-SIZE='10'>{d_str}</FONT></TD></TR></TABLE>>"
            dot.node(l, label=label, shape='circle', style='filled', fillcolor='lightgrey', width='0.9', fixedsize='true')
        elif l in active_nodes:
            # Intermediate Node (White Node)
            dot.node(l, label=l, shape='circle', style='filled', fillcolor='white', width='0.9', fixedsize='true')

    # 2. Consolidate Edges (Identical bins on the same route)
    edge_data = defaultdict(int)
    for bid, f, t, tr, freq in data['links']:
        if freq == 0: continue
        
        # Create a clean label of the bin's contents (e.g., "1 x p1, 2 x p2")
        contents = [f"{n} x {p}" for p in sorted(data['bins'][bid].keys()) if (n := data['bins'][bid][p]) > 0]
        if not contents: continue
        
        content_label = f"[{', '.join(contents)}]"
        edge_data[(f, t, tr, content_label)] += freq

    # 3. Add Edges to Graph
    for (f, t, tr, content_label), total_freq in edge_data.items():
        # Match thesis styling: tr2 is dashed, tr1 is solid
        style = 'dashed' if 'tr2' in tr else 'solid'
        edge_label = f"{tr}\n{content_label}\nat a frequency of {total_freq}"
        dot.edge(f, t, label=edge_label, style=style, fontsize='10')

    # 4. Render
    out_name = filename.replace('.lp', '_graph')
    dot.render(out_name, view=True)
    print(f"📈 Visual graph generated: {out_name}.pdf")

def main():
    parser = argparse.ArgumentParser(description="Solve and visualize ASP Logistics Models.")
    parser.add_argument("file", help="The ASP encoding file to solve (e.g., logistics.lp)")
    args = parser.parse_args()

    ctl = clingo.Control()
    ctl.load(args.file)
    print(f"Grounding {args.file}...")
    ctl.ground([("base", [])])
    
    optimal_model_data = None
    optimal_cost = None

    print("Solving for Optimum...")

    with ctl.solve(yield_=True) as handle:
        for model in handle:
            # Keep saving the data until we hit the proven optimal model
            optimal_model_data = extract_data(model)
            if hasattr(model, 'cost') and model.cost:
                optimal_cost = model.cost[0]
            final_model = None
            for model in handle:
                final_model = model

            result = handle.get()
        if result.satisfiable and final_model:
            print("\n" + "*"*50)
            print(f" OPTIMUM FOUND! Total Cost: {final_model.cost[0]}")
            print("*"*50)

              # Run the math verification
            run_audit(optimal_model_data)
                
                # Generate the PDF
            generate_graph(optimal_model_data, args.file)

if __name__ == "__main__":
    main()