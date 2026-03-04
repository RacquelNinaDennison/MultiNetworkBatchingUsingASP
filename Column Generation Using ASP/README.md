# Logistics Network Optimization Solver

A modular, Column Generation-based solver for complex logistics network problems. This tool optimizes multi-commodity flows across a network, balancing transport costs, CO2 emissions, and capital tying costs (inventory interest).

It uses **SCIP** (via `PySCIPOpt`) for the Master Problem and supports pluggable Pricing Solvers (SCIP, Greedy Heuristic, ASP, etc.) to handle the subproblems.

## 🚀 Features

* **Column Generation Algorithm:** Efficiently solves large-scale instances by generating routes dynamically.
* **Modular Pricing Engine:**
    * `scip`: Exact Knapsack solver using PySCIPOpt.
    * `greedy`: Fast heuristic based on efficiency density.
    * `template`: Boilerplate for adding custom solvers (e.g., ASP/Clingo, Gurobi).
* **Granular Cost Control:** Toggle specific cost components (Transport, CO2, Interest) via CLI.
* **Dual Mode:** Switch between Linear Relaxation (`lp`) and Integer Pricing (`ip`) for the lambda values / pattern frequencies.
* **Math Export:** Export the generated Master Problem formulation to `.lp` files for inspection.

## 🏃 Usage

The entry point is `main.py`. You must provide an instance file and choose a pricing engine.

### Basic Run
```bash
python main.py instances/example1.json --pricer scip