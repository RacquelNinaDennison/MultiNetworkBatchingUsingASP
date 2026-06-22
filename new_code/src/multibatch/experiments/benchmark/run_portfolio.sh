#!/usr/bin/env bash
# Portfolio-robustness experiment: clingo configuration presets x threads,
# on the one-shot solvers, size-by-size, with ntfy.sh pings.
#
# Crash-safe: rows append per completed run; every invocation passes
# --resume, so rerunning continues where it left off. Bins are FIXED
# (default 3) — the bins effect belongs to the main benchmark experiment.
#
# Usage:
#   NTFY_TOPIC=racquel-exp-xxxx ./run_portfolio.sh          # small medium
#   ./run_portfolio.sh small                                # one size
#   REPS=2 THREADS_SWEEP="1 4" ./run_portfolio.sh small     # tweak via env
#
# Sizes: paper small medium large xlarge industrylite

set -u

# ── Config ────────────────────────────────────────────────────────────

NTFY_TOPIC="${NTFY_TOPIC:-}"
NTFY_URL="${NTFY_URL:-https://ntfy.sh}"

RUN_TAG="${RUN_TAG:-}"
REPS="${REPS:-3}"
MAX_FREQ="${MAX_FREQ:-20}"
SOLVERS="${SOLVERS:-naive_optimised clingcon clingcon_optimised}"
BINS="${BINS:-3}"
CONFIGS="${CONFIGS:-default frumpy handy trendy many}"
THREADS_SWEEP="${THREADS_SWEEP:-1 4}"

# Per-size time limits (seconds)
TIME_PAPER=60
TIME_SMALL=60
TIME_MEDIUM=120
TIME_LARGE=300
TIME_XLARGE=600
TIME_INDUSTRYLITE=1200

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
NEW_CODE_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
LOG_DIR="$RESULTS_DIR/logs"

mkdir -p "$RESULTS_DIR" "$LOG_DIR"

# uv 0.9.7 marks .venv contents hidden on macOS and Python >=3.13.9 then
# skips the editable-install .pth -> ModuleNotFoundError mid-batch.
# PYTHONPATH bypasses the .pth entirely. Remove once uv is upgraded.
export PYTHONPATH="$NEW_CODE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

# ── ntfy helper ───────────────────────────────────────────────────────

ntfy() {
    [ -z "$NTFY_TOPIC" ] && return 0
    local title="$1" prio="$2" tags="$3" msg="$4"
    curl -s -m 10 \
        -H "Title: $title" \
        -H "Priority: $prio" \
        -H "Tags: $tags" \
        -d "$msg" \
        "$NTFY_URL/$NTFY_TOPIC" >/dev/null || true
}

human_time() {
    local s=$1
    printf '%dh%02dm%02ds' $((s/3600)) $((s%3600/60)) $((s%60))
}

# ── Single-size runner ────────────────────────────────────────────────

run_size() {
    local size="$1" time_limit="$2"
    local tag="portfolio_${size}${RUN_TAG:+_$RUN_TAG}"
    local log="$LOG_DIR/run_${tag}.log"
    local t0 t1 elapsed exit_code

    echo
    echo "============================================================"
    echo "  portfolio size:   $size"
    echo "  time_limit:       ${time_limit}s"
    echo "  configs:          $CONFIGS"
    echo "  threads:          $THREADS_SWEEP"
    echo "  out files:        $RESULTS_DIR/{benchmark_raw,benchmark_summary}_${tag}.csv"
    echo "  log:              $log"
    echo "============================================================"

    ntfy "portfolio:$size start" default "rocket" \
         "host=$(hostname) configs=$CONFIGS threads=$THREADS_SWEEP reps=$REPS time=${time_limit}s"

    t0=$(date +%s)

    (
        cd "$NEW_CODE_DIR" && \
        uv run python -m multibatch.experiments.benchmark.main \
            --sizes "$size" \
            --solvers $SOLVERS \
            --bins $BINS \
            --config-sweep $CONFIGS \
            --thread-sweep $THREADS_SWEEP \
            --reps "$REPS" \
            --time-limit "$time_limit" \
            --max-freq "$MAX_FREQ" \
            --output-dir "$RESULTS_DIR" \
            --tag "$tag" \
            --resume
    ) >"$log" 2>&1 </dev/null
    exit_code=$?

    t1=$(date +%s)
    elapsed=$((t1 - t0))

    local raw="$RESULTS_DIR/benchmark_raw_${tag}.csv"

    if [ $exit_code -eq 0 ]; then
        ntfy "portfolio:$size done" default "white_check_mark" \
             "elapsed=$(human_time $elapsed) rows=$(wc -l <"$raw" 2>/dev/null || echo ?) tag=$tag"
        echo "  [$size] OK in $(human_time $elapsed)"
    else
        local tail_log
        tail_log=$(tail -n 20 "$log" 2>/dev/null | tr '\n' ' ' | cut -c1-400)
        ntfy "portfolio:$size FAILED exit=$exit_code" high "warning,skull" \
             "elapsed=$(human_time $elapsed) tail: $tail_log"
        echo "  [$size] FAILED exit=$exit_code  (see $log)"
    fi

    return $exit_code
}

run_one() {
    case "$1" in
        paper)        run_size paper        "$TIME_PAPER" ;;
        small)        run_size small        "$TIME_SMALL" ;;
        medium)       run_size medium       "$TIME_MEDIUM" ;;
        large)        run_size large        "$TIME_LARGE" ;;
        xlarge)       run_size xlarge       "$TIME_XLARGE" ;;
        industrylite) run_size industrylite "$TIME_INDUSTRYLITE" ;;
        *) echo "unknown size: $1" >&2; return 2 ;;
    esac
}

# ── Main ──────────────────────────────────────────────────────────────

if [ "$#" -gt 0 ]; then
    SIZES=("$@")
else
    SIZES=(small medium)
fi

if [ -z "$NTFY_TOPIC" ]; then
    echo "WARN: NTFY_TOPIC not set — no notifications will be sent."
fi

echo "SIZES = ${SIZES[*]}"

ntfy "portfolio:batch start" default "rocket" \
     "host=$(hostname) sizes=${SIZES[*]}"

T_BATCH=$(date +%s)
declare -a OK_SIZES FAIL_SIZES

for size in "${SIZES[@]}"; do
    if run_one "$size"; then
        OK_SIZES+=("$size")
    else
        FAIL_SIZES+=("$size")
    fi
done

ELAPSED=$(( $(date +%s) - T_BATCH ))

if [ ${#FAIL_SIZES[@]} -eq 0 ]; then
    ntfy "portfolio:batch DONE" high "tada" \
         "all OK in $(human_time $ELAPSED). sizes: ${OK_SIZES[*]}"
    echo
    echo "ALL DONE in $(human_time $ELAPSED)"
    exit 0
else
    ntfy "portfolio:batch PARTIAL" high "warning" \
         "ok=${OK_SIZES[*]:-none} fail=${FAIL_SIZES[*]} elapsed=$(human_time $ELAPSED)"
    echo
    echo "PARTIAL: ok=(${OK_SIZES[*]:-none})  fail=(${FAIL_SIZES[*]})"
    exit 1
fi
