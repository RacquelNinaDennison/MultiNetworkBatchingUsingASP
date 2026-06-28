#!/usr/bin/env bash
# Run one-shot benchmark size-by-size, with ntfy.sh pings.
#
# Each invocation gets a unique RUN_TAG (timestamp) so CSV outputs from
# different runs never overwrite each other. Per-size also tagged in name.
#
# Usage:
#   NTFY_TOPIC=racquel-exp-xxxx ./run_all.sh                # run all sizes
#   NTFY_TOPIC=racquel-exp-xxxx ./run_all.sh paper small    # subset
#   RUN_TAG=mytag ./run_all.sh                              # custom tag
#
# Sizes: paper small medium large xlarge industrylite

set -u

# ── Config ────────────────────────────────────────────────────────────

NTFY_TOPIC="${NTFY_TOPIC:-}"
NTFY_URL="${NTFY_URL:-https://ntfy.sh}"

RUN_TAG="${RUN_TAG:-$(date +%Y%m%d_%H%M%S)}"
REPS="${REPS:-5}"
MAX_FREQ="${MAX_FREQ:-20}"
SOLVERS="${SOLVERS:-naive_basic naive_optimised clingcon clingcon_optimised}"
BINS="${BINS:-1 2 3}"

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
    local tag="benchmark_${size}_${RUN_TAG}"
    local log="$LOG_DIR/run_${tag}.log"
    local t0 t1 elapsed exit_code

    echo
    echo "============================================================"
    echo "  benchmark size:   $size"
    echo "  run_tag:          $RUN_TAG"
    echo "  time_limit:       ${time_limit}s"
    echo "  out files:        $RESULTS_DIR/{benchmark_raw,benchmark_summary}_${tag}.csv"
    echo "  log:              $log"
    echo "============================================================"

    ntfy "benchmark:$size start" default "rocket" \
         "host=$(hostname) tag=$RUN_TAG reps=$REPS bins=$BINS time=${time_limit}s"

    t0=$(date +%s)

    (
        cd "$NEW_CODE_DIR" && \
        uv run python -m multibatch.experiments.benchmark.main \
            --sizes "$size" \
            --solvers $SOLVERS \
            --bins $BINS \
            --reps "$REPS" \
            --time-limit "$time_limit" \
            --max-freq "$MAX_FREQ" \
            --output-dir "$RESULTS_DIR" \
            --tag "$tag"
    ) >"$log" 2>&1
    exit_code=$?

    t1=$(date +%s)
    elapsed=$((t1 - t0))

    local raw="$RESULTS_DIR/benchmark_raw_${tag}.csv"

    if [ $exit_code -eq 0 ]; then
        ntfy "benchmark:$size done" default "white_check_mark" \
             "elapsed=$(human_time $elapsed) rows=$(wc -l <"$raw" 2>/dev/null || echo ?) tag=$tag"
        echo "  [$size] OK in $(human_time $elapsed)"
    else
        local tail_log
        tail_log=$(tail -n 20 "$log" 2>/dev/null | tr '\n' ' ' | cut -c1-400)
        ntfy "benchmark:$size FAILED exit=$exit_code" high "warning,skull" \
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
    SIZES=(paper small medium large xlarge industrylite)
fi

if [ -z "$NTFY_TOPIC" ]; then
    echo "WARN: NTFY_TOPIC not set — no notifications will be sent."
fi

echo "RUN_TAG = $RUN_TAG"
echo "SIZES   = ${SIZES[*]}"

ntfy "benchmark:batch start" default "rocket" \
     "host=$(hostname) tag=$RUN_TAG sizes=${SIZES[*]}"

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
    ntfy "benchmark:batch DONE" high "tada" \
         "tag=$RUN_TAG all OK in $(human_time $ELAPSED). sizes: ${OK_SIZES[*]}"
    echo
    echo "ALL DONE in $(human_time $ELAPSED) — tag=$RUN_TAG"
    exit 0
else
    ntfy "benchmark:batch PARTIAL" high "warning" \
         "tag=$RUN_TAG ok=${OK_SIZES[*]:-none} fail=${FAIL_SIZES[*]} elapsed=$(human_time $ELAPSED)"
    echo
    echo "PARTIAL — tag=$RUN_TAG  ok=(${OK_SIZES[*]:-none})  fail=(${FAIL_SIZES[*]})"
    exit 1
fi
