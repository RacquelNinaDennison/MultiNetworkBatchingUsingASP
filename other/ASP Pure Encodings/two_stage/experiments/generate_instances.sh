#!/bin/bash
# Generate benchmark instances for the two-stage resilience experiments
#
# Uses --capacity-scale to reduce transport capacities and part sizes,
# ensuring demand quantities require multiple trips per arc (enabling
# meaningful resilience diversification).

GENERATOR="/Users/racqueldennison/Desktop/realdeal_masters/combined_encodings/nonmonotonic-generator/generate.py"
OUTDIR="$(dirname "$0")/instances"

mkdir -p "$OUTDIR"

echo "Generating instances..."

# Small instances: 2 harbors, 4 prodlocs, 2 hubs, 8 parts
# capacity-scale=5 brings caps from 65-1800 down to 13-360
for seed in 1 2 3 4 5; do
    echo "  small_seed${seed}"
    python "$GENERATOR" --seed $seed \
        --harbors 2 --prodlocs 4 --hubs 2 --parts 8 --min-trs 2 \
        --capacity-scale 5 --disruptions 0 \
        --output "$OUTDIR/small_seed${seed}.lp"
done

# Medium instances: 3 harbors, 6 prodlocs, 3 hubs, 15 parts
for seed in 1 2 3 4 5; do
    echo "  medium_seed${seed}"
    python "$GENERATOR" --seed $seed \
        --harbors 3 --prodlocs 6 --hubs 3 --parts 15 --min-trs 2 \
        --capacity-scale 5 --disruptions 0 \
        --output "$OUTDIR/medium_seed${seed}.lp"
done

# Large instances: 4 harbors, 8 prodlocs, 3 hubs, 25 parts
for seed in 1 2 3 4 5; do
    echo "  large_seed${seed}"
    python "$GENERATOR" --seed $seed \
        --harbors 4 --prodlocs 8 --hubs 3 --parts 25 --min-trs 2 \
        --capacity-scale 5 --disruptions 0 \
        --output "$OUTDIR/large_seed${seed}.lp"
done

echo "Done. Generated $(ls "$OUTDIR"/*.lp | wc -l) instances in $OUTDIR"
