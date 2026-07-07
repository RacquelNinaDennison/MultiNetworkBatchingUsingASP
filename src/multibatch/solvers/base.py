"""Base solver — abstract interface all solver variants implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import Instance, OneShotResult, TwoStageResult
from ..instance import parse_instance


class BaseSolver(ABC):
    """Abstract base for all multi-commodity batching solvers.

    Subclasses implement `solve()` which returns a typed result.
    Solvers do NOT print — they return data. Reporting is separate.
    """

    def __init__(self, instance_path: str | Path):
        self.instance_path = Path(instance_path)
        self.instance: Instance = parse_instance(self.instance_path)

    @abstractmethod
    def solve(self) -> OneShotResult | TwoStageResult | None:
        """Run the solver. Returns typed result or None if UNSAT."""
        ...
