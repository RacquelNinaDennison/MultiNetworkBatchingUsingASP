#!/usr/bin/env bash
# Run two-stage resilience experiments size-by-size, with ntfy.sh pings.
#
# Usage:
#   NTFY_TOPIC=racquel-exp-xxxx ./run_all.sh                # run all sizes
#   NTFY_TOPIC=racquel-exp-xxxx ./run_all.sh small medium   # run subset
#
# Sizes: paper small medium large xlarge industrylite industry
#
# Re-runnable: each experiment writes its own CSV and uses --resume.

set -u  # don't set -e: a single failed size shouldn't kill the rest

# ── Config ────────────────────────────────────────────────────────────

NTFY_TOPIC="${NTFY_TOPIC:-}"
NTFY_URL="${NTFY_URL:-https://ntfy.sh}"

WEIGHTS=(0 500 10000 50000 75000 100000 150000)
THREADS="${THREADS:-4}"
CONFIGURATION="${CONFIGURATION:-many}"
EXPOSURE_N="${EXPOSURE_N:-3}"
CAP_SIZE_DIVIDE="${CAP_SIZE_DIVIDE:-1}"
CAP_SIZE_DIVIDE_INDUSTRY="${CAP_SIZE_DIVIDE_INDUSTRY:-10}"

# Per-size time limits (seconds)
TIME_PAPER=600
TIME_SMALL=600
TIME_MEDIUM=600
TIME_LARGE=1200
TIME_XLARGE=1200
TIME_INDUSTRYLITE=1200
TIME_INDUSTRY=200000

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
NEW_CODE_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
LOG_DIR="$RESULTS_DIR/logs"

mkdir -p "$RESULTS_DIR" "$LOG_DIR"

# ── ntfy helper ───────────────────────────────────────────────────────

ntfy() {
    # ntfy <title> <priority> <tags> <message>
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
    local size="$1" filter="$2" time_limit_flag="$3" time_limit_val="$4"
    local cap_divide="${5:-$CAP_SIZE_DIVIDE}"

    local out="$RESULTS_DIR/experiment_${size}.csv"
    local log="$LOG_DIR/run_${size}.log"
    local t0 t1 elapsed exit_code

    echo
    echo "============================================================"
    echo "  SIZE: $size"
    echo "  filter:           $filter"
    echo "  cap_size_divide:  $cap_divide"
    echo "  out:              $out"
    echo "  log:              $log"
    echo "============================================================"

    ntfy "exp:$size start" default "rocket" \
         "host=$(hostname) filter=$filter cap_divide=$cap_divide weights=${WEIGHTS[*]}"

    t0=$(date +%s)

    (
        cd "$NEW_CODE_DIR" && \
        uv run python -m multibatch.experiments.twostage \
            --weights "${WEIGHTS[@]}" \
            -t "$THREADS" \
            --configuration "$CONFIGURATION" \
            --exposure-n "$EXPOSURE_N" \
            --cap-size-divide "$cap_divide" \
            "$time_limit_flag" "$time_limit_val" \
            --instance-filter "$filter" \
            --resume \
            -o "$out"
    ) >"$log" 2>&1
    exit_code=$?

    t1=$(date +%s)
    elapsed=$((t1 - t0))

    if [ $exit_code -eq 0 ]; then
        ntfy "exp:$size done" default "white_check_mark" \
             "elapsed=$(human_time $elapsed) rows=$(wc -l <"$out" 2>/dev/null || echo ?) out=$out"
        echo "  [$size] OK in $(human_time $elapsed)"
    else
        local tail_log
        tail_log=$(tail -n 20 "$log" 2>/dev/null | tr '\n' ' ' | cut -c1-400)
        ntfy "exp:$size FAILED exit=$exit_code" high "warning,skull" \
             "elapsed=$(human_time $elapsed) tail: $tail_log"
        echo "  [$size] FAILED exit=$exit_code  (see $log)"
    fi

    return $exit_code
}

# ── Size dispatch ─────────────────────────────────────────────────────

run_one() {
    case "$1" in
        paper)        run_size paper        "paper"         --time-paper        "$TIME_PAPER" ;;
        small)        run_size small        "small"         --time-small        "$TIME_SMALL" ;;
        medium)       run_size medium       "medium"        --time-medium       "$TIME_MEDIUM" ;;
        large)        run_size large        "_large_"       --time-large        "$TIME_LARGE" ;;
        xlarge)       run_size xlarge       "xlarge"        --time-xlarge       "$TIME_XLARGE" ;;
        industrylite) run_size industrylite "industrylite"  --time-industrylite "$TIME_INDUSTRYLITE" ;;
        industry)     run_size industry     "industry_test" --time-industry     "$TIME_INDUSTRY"     "$CAP_SIZE_DIVIDE_INDUSTRY" ;;
        *) echo "unknown size: $1" >&2; return 2 ;;
    esac
}

# ── Main ──────────────────────────────────────────────────────────────

if [ "$#" -gt 0 ]; then
    SIZES=("$@")
else
    SIZES=(paper small medium large xlarge industrylite industry)
fi

if [ -z "$NTFY_TOPIC" ]; then
    echo "WARN: NTFY_TOPIC not set — no notifications will be sent."
    echo "      export NTFY_TOPIC=your-secret-topic to enable."
fi

ntfy "exp:batch start" default "rocket" \
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
    ntfy "exp:batch DONE" high "tada" \
         "all OK in $(human_time $ELAPSED). sizes: ${OK_SIZES[*]}"
    echo
    echo "ALL DONE in $(human_time $ELAPSED)"
    exit 0
else
    ntfy "exp:batch PARTIAL" high "warning" \
         "ok=${OK_SIZES[*]:-none} fail=${FAIL_SIZES[*]} elapsed=$(human_time $ELAPSED)"
    echo
    echo "PARTIAL: ok=(${OK_SIZES[*]:-none})  fail=(${FAIL_SIZES[*]})"
    exit 1
fi
