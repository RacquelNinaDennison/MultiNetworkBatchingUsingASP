"""Per-arc Stage-2 packing stress test.

Drives the real ClingconTwoStageSolver._solve_stage2 on a single synthetic arc
of increasing size to find where ASP packing stops being tractable. This
de-risks the "ASP packing at industry (Airbus) scale" plan before any MILP
flow-oracle work begins.
"""
