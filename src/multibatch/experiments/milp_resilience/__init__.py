"""MILP-flow + ASP-packing resilience comparison.

Runs the hybrid pipeline (MILP network flow, fixed, then ASP per-arc packing)
across the four Stage-2 soft-constraint configs (baseline / mixed / even / full)
and computes the resilience metrics (R_1, K_1, R_alpha) on each. Demonstrates
that the resilience soft constraints actually improve packing resilience — on
the MILP flow, at industry scale.
"""
