"""Two-stage resilience experiment configuration.

Defines the Stage 2 packing configurations, instance classification,
and experiment grid parameters.

Stage 2 configs form a 2x2 factorial design:
    hetero_on  x  concentrated_on  (value-weighted evenness)

    baseline  = cost-focused, minimises dispatches only
    mixed     = penalises mono-part trips (hetero_on=1)
    even      = penalises fair-share violation, weighted by part value (concentrated_on=1)
    full      = both soft constraints active
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ── Stage 2 packing configurations (2x2 factorial) ────────────────────

@dataclass(frozen=True)
class S2Config:
    """A Stage 2 soft-constraint configuration."""
    name: str
    label: str
    hetero_on: int
    concentrated_on: int


S2_CONFIGS: dict[str, S2Config] = {
    "baseline": S2Config("baseline", "Baseline", hetero_on=0, concentrated_on=0),
    "mixed":    S2Config("mixed",    "Mixed",    hetero_on=1, concentrated_on=0),
    "even":     S2Config("even",     "Even",     hetero_on=0, concentrated_on=1),
    "full":     S2Config("full",     "Full",     hetero_on=1, concentrated_on=1),
}

# Mapping from old code names to new names
LEGACY_CONFIG_MAP: dict[str, str] = {
    "off_off": "baseline",
    "hetero": "mixed",
    "conc": "even",
    "both": "full",
}

DEFAULT_S2_CONFIGS = ["baseline", "mixed", "even", "full"]


# ── R_alpha parameters ────────────────────────────────────────────────

ALPHA_VALUES = [0.2, 0.4, 0.6, 0.8]
R_ALPHA_STRATEGIES = ["heaviest"]
R_ALPHA_MODES = ["single", "global"]


# ── Instance classification ───────────────────────────────────────────

_RE_LAYERED = re.compile(r"layered_(small|medium|large|xlarge|industrylite)_seed(\d+)")
_RE_INDUSTRY = re.compile(r"industry_test_(\d+)")

SIZE_ORDER = ["paper", "small", "medium", "large", "xlarge", "industrylite", "industry"]


@dataclass
class InstanceMeta:
    """Metadata for a problem instance."""
    name: str
    instance_type: str  # "layered" or "industry"
    size: str
    seed: int
    path: Path
    # Post-hoc computed properties
    n_locations: int = 0
    n_parts: int = 0
    n_routes: int = 0
    n_transports: int = 0
    density: float = 0.0
    capacity_tightness: float = 0.0


def classify_instance(path: Path) -> InstanceMeta:
    """Classify an instance file into type/size/seed metadata."""
    name = path.stem

    m = _RE_LAYERED.match(name)
    if m:
        return InstanceMeta(
            name=name, instance_type="layered",
            size=m.group(1), seed=int(m.group(2)), path=path,
        )

    if name == "layered_paper":
        return InstanceMeta(
            name=name, instance_type="layered",
            size="paper", seed=0, path=path,
        )

    m = _RE_INDUSTRY.match(name)
    if m:
        return InstanceMeta(
            name=name, instance_type="industry",
            size="industry", seed=int(m.group(1)), path=path,
        )

    return InstanceMeta(
        name=name, instance_type="custom",
        size="custom", seed=0, path=path,
    )


def compute_instance_properties(meta: InstanceMeta, instance) -> InstanceMeta:
    """Fill post-hoc properties from a parsed Instance model."""
    meta.n_locations = len(instance.locations)
    meta.n_parts = len(instance.parts)
    meta.n_routes = len(instance.routes)
    meta.n_transports = len(instance.transport_capacity)

    # Density: actual routes / possible directed arcs
    # Possible = locations * (locations - 1) * transports
    n = meta.n_locations
    possible = n * (n - 1) * meta.n_transports
    meta.density = round(meta.n_routes / possible, 3) if possible > 0 else 0.0

    # Capacity tightness: total capacity / total demand volume
    total_demand_vol = sum(
        abs(do.quantity) * instance.part_size.get(do.part, 1)
        for do in instance.demand_offers
        if do.quantity < 0
    )
    total_cap = sum(
        r.cost  # Using route count as proxy — real capacity depends on freq
        for r in instance.routes
    )
    # Better proxy: sum of transport capacities * route count
    avg_cap = (
        sum(instance.transport_capacity.values()) / meta.n_transports
        if meta.n_transports > 0 else 0
    )
    total_cap_proxy = avg_cap * meta.n_routes
    meta.capacity_tightness = (
        round(total_cap_proxy / total_demand_vol, 3)
        if total_demand_vol > 0 else 0.0
    )

    return meta


# ── Experiment grid defaults ──────────────────────────────────────────

@dataclass
class ExperimentConfig:
    """Full experiment grid configuration."""
    weights: list[int] = field(default_factory=lambda: [0, 1000])
    exposure_n: int = 3
    s2_configs: list[str] = field(default_factory=lambda: list(DEFAULT_S2_CONFIGS))
    max_freq: int = 20
    cap_size_divide: int = 1
    threads: int = 1
    configuration: str = "many"
    # None -> single-shot: one solve with the full time limit. Setting a
    # value re-enables multi-shot bound tightening with that round length.
    round_timeout: int | None = None
    time_limits: dict[str, int] = field(default_factory=lambda: {
        "paper": 30,
        "small": 30,
        "medium": 60,
        "large": 120,
        "xlarge": 300,
        "industrylite": 600,
        "industry": 20000,
        "custom": 30,
        "default": 120,
    })

    def get_time_limit(self, size: str) -> int:
        return self.time_limits.get(size, self.time_limits.get("default", 120))
