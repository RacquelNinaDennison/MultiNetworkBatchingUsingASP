#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p results

echo "=== div_weight sweep experiment ==="
echo "Started: $(date)"
echo ""

python run_experiment.py --output results/div_weight_sweep.csv 2>&1 \
    | tee "results/experiment_$(date +%Y%m%d_%H%M%S).log"

echo ""
echo "=== Generating plots ==="
python plot_results.py --input results/div_weight_sweep.csv

echo ""
echo "=== Done: $(date) ==="
