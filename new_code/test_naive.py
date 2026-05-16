"""Quick test: parse instance → run naive solver → verify result."""

import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multibatch.instance import parse_instance
from multibatch.solvers.naive import NaiveOneShotSolver
from multibatch.models import NaiveOneShotConfig
from multibatch.verification import verify_solution

# Paths
INSTANCE = Path(__file__).parent.parent / "src" / "instances" / "generated" / "layered_small_seed1.lp"
ENCODING = Path(__file__).parent.parent / "src" / "encoding" / "naive" / "optimised_encoding_route.lp"


def main():
    print("=" * 60)
    print("  TEST: Parser + Naive Solver")
    print("=" * 60)

    # 1. Parse instance
    print(f"\n  Instance: {INSTANCE.name}")
    instance = parse_instance(INSTANCE)
    print(f"  Parts:      {sorted(instance.parts)}")
    print(f"  Locations:  {sorted(instance.locations)}")
    print(f"  Routes:     {len(instance.routes)}")
    print(f"  Max cap:    {instance.max_capacity}")
    print(f"  Min size:   {instance.min_part_size}")
    print(f"  Max items/bin: {instance.max_items_per_bin}")

    # 2. Configure & run solver
    config = NaiveOneShotConfig(
        num_bins=2,
        time_limit=30,
        max_freq=20,
        optimised=True,
    )
    print(f"\n  Config: bins={config.num_bins}, time_limit={config.time_limit}s")
    print(f"  Encoding: {ENCODING.name}")

    solver = NaiveOneShotSolver(
        instance_path=str(INSTANCE),
        config=config,
        encoding_path=str(ENCODING),
    )

    print("\n  Solving...", end="", flush=True)
    result = solver.solve()

    if result is None:
        print(" UNSAT")
        return 1

    # 3. Print result summary
    meta = result.metadata
    status = "OPTIMUM" if meta.optimum else "BEST MODEL"
    print(f" {status} ({meta.total_time}s)")

    nonzero_pack = [p for p in result.pack if p.quantity > 0]
    nonzero_flow = [f for f in result.flow if f.quantity > 0]
    print(f"\n  Pack atoms:  {len(result.pack)} (non-zero: {len(nonzero_pack)})")
    print(f"  Freq atoms:  {len(result.freq)}")
    print(f"  Flow atoms:  {len(result.flow)} (non-zero: {len(nonzero_flow)})")

    # Show some packing detail
    print("\n  Sample packings:")
    for p in nonzero_pack[:10]:
        print(f"    bin {p.bin_id}: {p.quantity}x {p.part} on {p.origin}→{p.destination} via {p.transport}")

    print("\n  Frequencies:")
    for f in result.freq:
        if f.frequency > 0:
            print(f"    bin {f.bin_id}: {f.origin}→{f.destination} via {f.transport} freq={f.frequency}")

    # 4. Verify
    print("\n" + "-" * 60)
    print("  VERIFICATION")
    print("-" * 60)
    passed, errors = verify_solution(result, instance)
    if passed:
        print("  All checks PASSED")
    else:
        print(f"  FAILED ({len(errors)} errors):")
        for e in errors[:10]:
            print(f"    {e}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
