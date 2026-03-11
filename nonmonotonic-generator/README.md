# Nonmonotonic Benchmark Instance Generator

Generates reproducible multibatching benchmark instances by recycling
industry-calibrated data from a real logistics instance and varying the
network topology using Answer Set Programming.

---

## Concept

The core idea is a clean separation between **what to ship** and **how to ship it**.

**What to ship** (recycled from real data):
- Part sizes and transport compatibility
- Transport resource profiles (capacity, cost, CO2, speed)
- Supply and demand amounts per part

**How to ship it** (generated fresh per instance):
- Which locations exist (harbors + production locations)
- Which routes connect them and via which transport types
- Which locations serve as relay hubs
- Which arcs are disrupted

This lets you generate many structurally distinct benchmark instances that all
share the same industry-calibrated product and transport data, making results
comparable across instances.

---

## Architecture

### Python (`generate.py`)

Owns everything that does not benefit from combinatorial search:

1. **Parse** `instances.lp` to extract the data pool: transport resource
   profiles, part sizes, transport compatibility, and supply/demand patterns.
   Location names are stripped from demand patterns — only the signed amounts
   are kept (e.g. `[+53, +27, -46, -20, -14]`).

2. **Assign demand** — randomly map each part's abstract supply/demand amounts
   to new location names. Supply slots go to production locations; amounts are
   preserved exactly so balance is guaranteed.

3. **Seed route candidates** — generate `route_attr` facts for every directed
   location pair. Distances are sampled from the real data's distribution.
   Costs are derived as `distance x cost_rate`. Harbor-to-harbor pairs get
   backbone transport types (maritime/rail); other pairs get land/mixed types.

4. **Emit fixed facts** directly to the output file, bypassing clingo. These
   never change across instances: `transportCapacity`, `partSize`,
   `valid_transport`, `demandOffer`.

### ASP (`generator.lp`)

Owns the combinatorial structural decisions, where nonmonotonicity is useful:

1. **Hub designation** — choose exactly K locations as hubs from all locations.

2. **Route topology** — choose which candidate arcs (from `route_attr`) become
   active routes. At most 2 transport types per directed pair.

3. **Disruptions** (nonmonotonic) — choose exactly ND arcs to disrupt.
   Adding `disrupted(L1,L2)` causes `active_route(L1,L2,TR)` to retract via
   negation-as-failure, which can retract `p_reachable` conclusions, which
   triggers the feasibility constraint. This is the core nonmonotonic behaviour.

4. **Feasibility constraints** — hubs must be mutually reachable; every
   supplier must be able to reach every consumer for its product via active
   routes using that product's valid transport types.

---

## Usage

```
python generate.py --seed SEED [options]
```

| Option | Default | Description |
|---|---|---|
| `--seed` | required | Reproducibility seed (Python RNG + clingo) |
| `--instances-file` | `instances.lp` | Source file to recycle data from |
| `--harbors N` | 5 | Number of harbor (backbone) locations |
| `--prodlocs M` | 15 | Number of production locations |
| `--hubs K` | 3 | Number of hub locations ASP designates |
| `--disruptions D` | 0 | Number of arcs to disrupt (nonmonotonic difficulty) |
| `--output PATH` | stdout | Write instance to this `.lp` file |
| `--solutions N` | 1 | Number of distinct instances to generate |

### Example

```bash
# Small instance, no disruptions
python generate.py --seed 42 --harbors 4 --prodlocs 10 --hubs 3

# Larger instance with disruptions
python generate.py --seed 42 --harbors 8 --prodlocs 20 --hubs 5 \
                   --disruptions 3 --output instances/instance_42.lp

# Generate a batch with different seeds
for seed in 1 2 3 4 5; do
    python generate.py --seed $seed --harbors 6 --prodlocs 15 --hubs 4 \
                       --output instances/instance_${seed}.lp
done
```

---

## Difficulty Levers

| Lever | Parameter | Direction | Mechanism |
|---|---|---|---|
| Routing | `--disruptions` | more = harder | Fewer active arcs, tighter feasibility |
| Relay | `--hubs` | fewer = harder | Less relay capacity in the network |
| Scale | `--harbors` / `--prodlocs` | more = larger | More locations, more routing decisions |

---

## Output Format

The generated `.lp` file is a self-contained instance in the format expected
by the solver encodings:

```
location(L).                        % all locations
transportCapacity(TR, C).           % recycled from real data
transportCO2(TR, C).
transportCost(TR, C).
transportSpeed(TR, C).
part(P).
partSize(P, S).                     % recycled from real data
valid_transport(P, TR).             % recycled from real data
demandOffer(P, L, V).               % recycled amounts, new locations
route(L1, L2, TR, Dist, Cost).      % ASP-generated topology
hub(L).                             % ASP-designated hubs
```

---

## Source Data (`instances.lp`)

The source file contains one real industry logistics instance with:
- 51 named locations (17 harbors, 34 production locations)
- 16 transport resources with real-world capacity, cost, CO2, and speed values
- 35 parts with sizes ranging from 1 to 627 units
- 31 parts with supply/demand patterns (balanced per part)

Part and transport data are treated as ground truth and recycled unchanged.
Only the network topology changes between generated instances.
