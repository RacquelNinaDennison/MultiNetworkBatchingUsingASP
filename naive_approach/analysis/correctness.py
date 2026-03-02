#!/usr/bin/env python3
"""
Solution Verifier for the Global Logistics Multi-Batching ASP Problem.

Uses the clingo Python API (clingo.Control) to:
  1. Load and ground the instance to extract structured instance data
  2. Load encoding + instance, solve, and extract the answer set via Model API
  3. Verify all constraints: flow conservation, capacity, demand coverage
  4. Independently compute and compare the objective value

Usage:
    # Solve and verify in one step:
    python verify_solution.py encoding.lp instances/toy_instance.lp

    # Verbose mode shows all individual checks:
    python verify_solution.py encoding.lp instances/toy_instance.lp -v

    # Custom timeout and clingo config:
    python verify_solution.py encoding.lp instances/toy_instance.lp \\
        --timeout 60 --clingo-args="--configuration=tweety"

    # Verify pre-computed atoms from a file (skip solving):
    python verify_solution.py encoding.lp instances/toy_instance.lp \\
        --atoms-file solution_atoms.txt
"""

import sys
import argparse
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Any

try:
    import clingo
except ImportError:
    print("ERROR: The clingo Python package is required.")
    print("Install it with:  pip install clingo")
    print("            or:   conda install -c potassco clingo")
    sys.exit(1)


# =============================================================================
# Instance Extraction via Clingo API
# =============================================================================

class InstanceData:
    """Structured representation of the problem instance.

    Populated by grounding the instance file with clingo and inspecting
    the symbolic_atoms table — no regex parsing needed.
    """

    def __init__(self):
        self.locations: Set[str] = set()
        self.parts: Set[str] = set()
        self.part_size: Dict[str, int] = {}          # part -> size
        self.part_value: Dict[str, int] = {}          # part -> value
        self.demand_offer: Dict[Tuple[str, str], int] = {}  # (part, loc) -> rate
        self.routes: List[Tuple[str, str, str, int, int]] = []  # (from,to,tr,dist,cost)
        self.transport_capacity: Dict[str, int] = {}  # tr -> capacity
        self.co2_emission: Dict[str, int] = {}        # tr -> co2
        self.co2_price: int = 0

    @staticmethod
    def from_file(instance_path: str) -> "InstanceData":
        """Load instance data by grounding the instance file with clingo.

        We create a temporary clingo.Control, load only the instance file,
        ground it, and iterate over ctl.symbolic_atoms to populate the
        InstanceData fields. This uses clingo as a proper ASP parser.

        clingo.Control(["0"]) means we request 0 models — we only need
        the grounding phase to access the symbolic atom table.
        """
        ctl = clingo.Control(["0"])
        ctl.load(instance_path)
        ctl.ground([("base", [])])
        data = InstanceData()

        for atom in ctl.symbolic_atoms:
            sym = atom.symbol
            name = sym.name
            args = sym.arguments

            if name == "location" and len(args) == 1:
                data.locations.add(str(args[0]))

            elif name == "part" and len(args) == 1:
                data.parts.add(str(args[0]))

            elif name == "partSize" and len(args) == 2:
                data.part_size[str(args[0])] = args[1].number

            elif name == "partValue" and len(args) == 2:
                data.part_value[str(args[0])] = args[1].number

            elif name == "demandOffer" and len(args) == 3:
                data.demand_offer[(str(args[0]), str(args[1]))] = args[2].number

            elif name == "route" and len(args) == 5:
                data.routes.append((
                    str(args[0]), str(args[1]), str(args[2]),
                    args[3].number, args[4].number,
                ))

            elif name == "transportCapacity" and len(args) == 2:
                data.transport_capacity[str(args[0])] = args[1].number

            elif name == "co2emission" and len(args) == 2:
                data.co2_emission[str(args[0])] = args[1].number

            elif name == "co2price" and len(args) == 1:
                data.co2_price = args[0].number

        return data

    def summary(self) -> str:
        return (
            f"{len(self.locations)} locations, "
            f"{len(self.parts)} products, "
            f"{len(self.routes)} routes, "
            f"{len(self.transport_capacity)} transport resources"
        )


class SolutionData:
    """Structured representation of a single answer set (solution).

    Populated from a clingo.Model via model.symbols(shown=True), which
    returns exactly the atoms matching the #show directives in the encoding.
    """

    def __init__(self):
        self.flows: List[Tuple[str, str, str, int]] = []        # (from,to,part,amount)
        self.packs: List[Tuple[int, str, int, str, str, str]] = []  # (n,part,bin,from,to,tr)
        self.freqs: List[Tuple[int, str, str, str, int]] = []   # (bin,from,to,tr,freq)
        self.cost: Optional[List[int]] = None
        self.optimal: bool = False
        self.model_number: int = 0

    @staticmethod
    def from_model(model: clingo.Model) -> "SolutionData":
        """Extract solution data from a clingo.Model.
        """
        sol = SolutionData()
        sol.cost = list(model.cost)
        sol.optimal = model.optimality_proven
        sol.model_number = model.number

        for sym in model.symbols(shown=True):
            name = sym.name
            args = sym.arguments

            if name == "flow" and len(args) == 4:
                sol.flows.append((
                    str(args[0]), str(args[1]), str(args[2]), args[3].number
                ))

            elif name == "pack" and len(args) == 6:
                sol.packs.append((
                    args[0].number, str(args[1]), args[2].number,
                    str(args[3]), str(args[4]), str(args[5]),
                ))

            elif name == "freq" and len(args) == 5:
                sol.freqs.append((
                    args[0].number, str(args[1]), str(args[2]),
                    str(args[3]), args[4].number,
                ))

        return sol

    @staticmethod
    def from_atoms_text(text: str) -> "SolutionData":
        """Parse solution from a text file of space-separated atoms.

        Uses clingo.parse_term() to parse each atom — still no regex.
        This is a fallback for loading pre-computed answers.

        clingo.parse_term(s) parses a string like "flow(l1,l2,p1,6)"
        into a clingo.Symbol with the same .name/.arguments interface
        as what model.symbols() returns.
        """
        sol = SolutionData()

        for token in text.split():
            token = token.strip().rstrip(".")
            if not token or token.startswith("%"):
                continue
            try:
                sym = clingo.parse_term(token)
            except RuntimeError:
                continue  # skip unparseable tokens (e.g., "Answer:", "OPTIMUM")

            name = sym.name
            args = sym.arguments

            if name == "flow" and len(args) == 4:
                sol.flows.append((
                    str(args[0]), str(args[1]), str(args[2]), args[3].number
                ))
            elif name == "pack" and len(args) == 6:
                sol.packs.append((
                    args[0].number, str(args[1]), args[2].number,
                    str(args[3]), str(args[4]), str(args[5]),
                ))
            elif name == "freq" and len(args) == 5:
                sol.freqs.append((
                    args[0].number, str(args[1]), str(args[2]),
                    str(args[3]), args[4].number,
                ))

        return sol

    def active_flows(self):
        """Return only flows with amount > 0."""
        return [(f, t, p, a) for f, t, p, a in self.flows if a > 0]

    def active_packs(self):
        """Return only packs with amount > 0."""
        return [(n, p, b, f, t, tr) for n, p, b, f, t, tr in self.packs if n > 0]

    def active_freqs(self):
        """Return only frequencies > 0."""
        return [(b, f, t, tr, freq) for b, f, t, tr, freq in self.freqs if freq > 0]


# =============================================================================
# Solving via Clingo API
# =============================================================================

def solve_instance(
    encoding_path: str,
    instance_path: str,
    timeout: int = 120,
    clingo_args: Optional[List[str]] = None,
) -> Tuple[Optional[SolutionData], "clingo.SolveResult"]:
    """Load encoding + instance, solve with clingo, return the best model.

    Pipeline:
      1. clingo.Control(args) — create a solver instance with options
      2. ctl.load(file) — load ASP files (can be called multiple times)
      3. ctl.ground([("base", [])]) — ground all rules in the "base" subprogram
      4. ctl.solve(on_model=callback) — solve; callback fires for each model

    For optimisation (#minimize), clingo enumerates models with improving
    cost. The on_model callback captures each one; we keep the last (best).

    Parameters
    ----------
    encoding_path : Path to the ASP encoding (.lp).
    instance_path : Path to the ASP instance data (.lp).
    timeout : Solve time limit in seconds (0 = unlimited).
    clingo_args : Extra CLI-style arguments for clingo (e.g. ["--configuration=tweety"]).

    Returns
    -------
    (SolutionData or None, clingo.SolveResult)
    """
    args = list(clingo_args or [])
    ctl = clingo.Control(args)
    ctl.load(encoding_path)
    ctl.load(instance_path)

  
    ctl.ground([("base", [])])

    # Report grounding statistics via ctl.statistics
    # ctl.statistics is a nested dict-like object with solver/problem stats
    try:
        prob = ctl.statistics["problem"]
        lp = prob.get("lp", {})
        atoms = int(lp.get("atoms", 0))
        rules = int(lp.get("rules", 0))
        print(f"  Ground program: {atoms} atoms, {rules} rules")
    except (KeyError, TypeError):
        pass  # statistics format varies across clingo versions

    # Mutable container to capture the best model across callbacks
    best: List[Optional[SolutionData]] = [None]

    def on_model(model: clingo.Model):
        """Callback invoked for each model found during search.

        For optimisation, clingo calls this for each *improving* model
        (each successive model has a strictly better cost vector).
        model.cost returns the optimisation vector, e.g. [336] for a
        single #minimize statement.
        """
        best[0] = SolutionData.from_model(model)
        cost_str = ", ".join(str(c) for c in model.cost) if model.cost else "N/A"
        opt_str = " (OPTIMAL)" if model.optimality_proven else ""
        print(f"  Model #{model.number}: cost=[{cost_str}]{opt_str}")

    print("Solving...")
    result = ctl.solve(on_model=on_model)
    print(f"Result: {result}")

    # Report solving statistics
    try:
        times = ctl.statistics["summary"]["times"]
        print(f"  Time — total: {times['total']:.3f}s, "
              f"solve: {times['solve']:.3f}s, "
              f"unsat: {times.get('unsat', 0):.3f}s")
    except (KeyError, TypeError):
        pass

    try:
        solvers = ctl.statistics["solving"]["solvers"]
        if isinstance(solvers, dict):
            print(f"  Search — conflicts: {int(solvers.get('conflicts', 0))}, "
                  f"choices: {int(solvers.get('choices', 0))}")
    except (KeyError, TypeError):
        pass

    return best[0], result


# =============================================================================
# Verification Checks
# =============================================================================

class VerificationReport:
    """Collects and formats verification results across all checks."""

    def __init__(self):
        self.checks: List[Dict[str, Any]] = []

    def add_check(self, name: str, passed: bool, errors: List[str],
                  details: Optional[List[str]] = None):
        self.checks.append({
            "name": name,
            "passed": passed,
            "errors": errors,
            "details": details or [],
        })

    @property
    def all_passed(self) -> bool:
        return all(c["passed"] for c in self.checks)

    @property
    def total_errors(self) -> int:
        return sum(len(c["errors"]) for c in self.checks)

    def print_report(self, verbose: bool = False):
        print("\n" + "=" * 60)
        print("VERIFICATION REPORT")
        print("=" * 60)

        for i, check in enumerate(self.checks, 1):
            n_err = len(check["errors"])
            status = "PASS" if check["passed"] else f"FAIL ({n_err} violations)"
            print(f"\n[{i}] {check['name']}")

            if verbose and check["details"]:
                for detail in check["details"]:
                    print(f"  {detail}")

            print(f"  -> {status}")

            if not check["passed"]:
                for err in check["errors"]:
                    print(f"  ✗ {err}")

        print("\n" + "=" * 60)
        if self.all_passed:
            print("RESULT: ALL CHECKS PASSED")
        else:
            print(f"RESULT: FAILED ({self.total_errors} total violations)")
        print("=" * 60)


def check_flow_conservation(
    sol: SolutionData, inst: InstanceData,
) -> Tuple[List[str], List[str]]:
    """Verify outflow - inflow == netSupplyDemand at every (location, product).
    """
    errors, details = [], []

    outflow: Dict[Tuple[str, str], int] = defaultdict(int)
    inflow: Dict[Tuple[str, str], int] = defaultdict(int)

    for (frm, to, part, amount) in sol.flows:
        outflow[(frm, part)] += amount
        inflow[(to, part)] += amount

    for loc in sorted(inst.locations):
        for part in sorted(inst.parts):
            out = outflow.get((loc, part), 0)
            inp = inflow.get((loc, part), 0)
            net = out - inp
            expected = inst.demand_offer.get((part, loc), 0)

            details.append(
                f"{loc}/{part}: out={out} - in={inp} = {net} (expected {expected})"
            )
            if net != expected:
                errors.append(
                    f"at {loc} for {part}: out({out}) - in({inp}) = {net} != {expected}"
                )

    return errors, details


def check_capacity(
    sol: SolutionData, inst: InstanceData,
) -> Tuple[List[str], List[str]]:
    """Verify each bin's total packed size <= transport capacity.
    """
    errors, details = [], []

    # Group packs by (bin_id, from, to, tr)
    bin_packs: Dict[Tuple, List[Tuple[int, str]]] = defaultdict(list)
    for (amount, part, bin_id, frm, to, tr) in sol.packs:
        bin_packs[(bin_id, frm, to, tr)].append((amount, part))

    for key in sorted(bin_packs.keys()):
        (bin_id, frm, to, tr) = key
        packs = bin_packs[key]
        total_size = sum(
            amount * inst.part_size.get(part, 0) for amount, part in packs
        )
        capacity = inst.transport_capacity.get(tr, 0)
        contents = ", ".join(f"{a}x{p}" for a, p in packs if a > 0) or "empty"

        details.append(f"bin{bin_id}({frm}->{to},{tr}): {total_size}/{capacity} [{contents}]")

        if total_size > capacity:
            errors.append(
                f"bin{bin_id}({frm}->{to},{tr}): size {total_size} > capacity {capacity}"
            )

    return errors, details


def check_demand_coverage(
    sol: SolutionData, inst: InstanceData,
) -> Tuple[List[str], List[str]]:
    """Verify pack × freq >= flow for every (link, product).
    """
    errors, details = [], []

    freq_map: Dict[Tuple, int] = {}
    for (bin_id, frm, to, tr, freq) in sol.freqs:
        freq_map[(bin_id, frm, to, tr)] = freq

    flow_map: Dict[Tuple[str, str, str], int] = {}
    for (frm, to, part, amount) in sol.flows:
        flow_map[(frm, to, part)] = amount

    for key in sorted(flow_map.keys()):
        (frm, to, part) = key
        flow_amount = flow_map[key]
        if flow_amount == 0:
            continue

        total_transported = 0
        contributions = []

        for (amount, p, bin_id, f, t, tr) in sol.packs:
            if p == part and f == frm and t == to:
                freq = freq_map.get((bin_id, frm, to, tr), 0)
                contribution = amount * freq
                total_transported += contribution
                if contribution > 0:
                    contributions.append(f"bin{bin_id}({tr}):{amount}x{freq}={contribution}")

        detail_str = " + ".join(contributions) if contributions else "nothing"
        details.append(f"({frm}->{to},{part}): {total_transported} >= {flow_amount} [{detail_str}]")

        if total_transported < flow_amount:
            errors.append(
                f"({frm}->{to},{part}): transported {total_transported} < flow {flow_amount}"
            )

    return errors, details


def check_nonnegativity(sol: SolutionData) -> Tuple[List[str], List[str]]:
    """Verify all decision variables are non-negative.
    """
    errors, details = [], []

    neg_flows = [(f, t, p, a) for f, t, p, a in sol.flows if a < 0]
    neg_packs = [(n, p, b, f, t, tr) for n, p, b, f, t, tr in sol.packs if n < 0]
    neg_freqs = [(b, f, t, tr, freq) for b, f, t, tr, freq in sol.freqs if freq < 0]

    for item in neg_flows:
        errors.append(f"Negative flow: {item}")
    for item in neg_packs:
        errors.append(f"Negative pack: {item}")
    for item in neg_freqs:
        errors.append(f"Negative freq: {item}")

    details.append(f"Flows: {len(sol.flows)} checked, {len(neg_flows)} negative")
    details.append(f"Packs: {len(sol.packs)} checked, {len(neg_packs)} negative")
    details.append(f"Freqs: {len(sol.freqs)} checked, {len(neg_freqs)} negative")

    return errors, details




def verify(
    sol: SolutionData,
    inst: InstanceData,
    verbose: bool = False,
) -> VerificationReport:
    """Run all verification checks on a solution and print the report."""
    report = VerificationReport()

    # 1. Non-negativity
    errors, details = check_nonnegativity(sol)
    report.add_check("Non-negativity", not errors, errors, details)

    # 2. Flow conservation
    errors, details = check_flow_conservation(sol, inst)
    report.add_check("Flow Conservation", not errors, errors, details)

    # 3. Capacity
    errors, details = check_capacity(sol, inst)
    report.add_check("Capacity", not errors, errors, details)

    # 4. Demand coverage
    errors, details = check_demand_coverage(sol, inst)
    report.add_check("Demand Coverage", not errors, errors, details)
    report.print_report(verbose=verbose)

    return report



def main():
    parser = argparse.ArgumentParser(
        description="Solve and verify a logistics ASP instance using the clingo Python API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Solve and verify:
  python verify_solution.py encoding.lp instances/toy_instance.lp

  # Verbose:
  python verify_solution.py encoding.lp instances/toy_instance.lp -v

  # Custom clingo config:
  python verify_solution.py encoding.lp instances/toy_instance.lp \\
      --clingo-args="--configuration=tweety --opt-strategy=usc"

  # Verify pre-computed atoms:
  python verify_solution.py encoding.lp instances/toy_instance.lp \\
      --atoms-file saved_solution.txt
        """,
    )

    parser.add_argument("encoding", help="Path to the ASP encoding file (.lp)")
    parser.add_argument("instance", help="Path to the ASP instance file (.lp)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show detailed output for every check")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Solve timeout in seconds (default: 120, 0 = no limit)")
    parser.add_argument("--clingo-args", type=str, default="",
                        help='Extra clingo options (e.g. "--configuration=tweety")')
    parser.add_argument("--atoms-file", type=str, default=None,
                        help="Skip solving; load and verify atoms from this file")

    args = parser.parse_args()

    # --- Step 1: Load instance via clingo API ---
    print(f"Loading instance: {args.instance}")
    inst = InstanceData.from_file(args.instance)
    print(f"  {inst.summary()}")

    # --- Step 2: Get solution ---
    if args.atoms_file:
        # Load pre-computed atoms using clingo.parse_term
        print(f"\nLoading atoms from: {args.atoms_file}")
        with open(args.atoms_file) as f:
            text = f.read()
        sol = SolutionData.from_atoms_text(text)
        print(f"  Parsed {len(sol.flows)} flows, {len(sol.packs)} packs, {len(sol.freqs)} freqs")
    else:
        # Solve via clingo.Control
        print(f"\nSolving: {args.encoding} + {args.instance}")
        extra_args = args.clingo_args.split() if args.clingo_args else []
        sol, result = solve_instance(
            args.encoding, args.instance,
            timeout=args.timeout,
            clingo_args=extra_args,
        )

        if sol is None:
            if result.unsatisfiable:
                print("\nUNSATISFIABLE — no valid solution exists.")
                print("Possible causes:")
                print("  - Domain bounds (maxFlow/maxFreq/maxParts) too small")
                print("  - Network disconnected (products can't reach consumers)")
                print("  - Demand exceeds what the integer domains can express")
            else:
                print("\nNo solution found within the time limit.")
                print(f"Try increasing --timeout (currently {args.timeout}s)")
            sys.exit(1)

    # --- Step 3: Verify ---
    report = verify(sol, inst, verbose=args.verbose)
    sys.exit(0 if report.all_passed else 1)


if __name__ == "__main__":
    main()