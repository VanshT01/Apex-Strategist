from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class InterventionKind(StrEnum):
    NONE = "NO_INTERVENTION"
    VSC = "VSC"
    SAFETY_CAR = "SAFETY_CAR"


@dataclass(frozen=True)
class InterventionSamples:
    kinds: np.ndarray
    pit_loss_adjustment_ms: np.ndarray


class InterventionScenarioSampler:
    """Explicit Phase 5 extension point; incident sampling is disabled by default."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    def sample(self, simulation_count: int, rng: np.random.Generator) -> InterventionSamples:
        if self.enabled:
            raise NotImplementedError(
                "Safety Car/VSC sampling requires a calibrated scenario model"
            )
        return InterventionSamples(
            kinds=np.full(simulation_count, InterventionKind.NONE.value, dtype="U15"),
            pit_loss_adjustment_ms=np.zeros(simulation_count, dtype=np.int64),
        )
