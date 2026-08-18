from __future__ import annotations

import hashlib
import json

import numpy as np

from app.schemas.strategy import StrategyCandidate
from app.simulation.tyres import DEFAULT_TYRE_PERFORMANCE_CONFIG


def strategy_seed_sequence(
    random_seed: int,
    session_id: int,
    driver_id: int,
    control_lap: int,
    candidate: StrategyCandidate,
) -> np.random.SeedSequence:
    """Derive a stable child seed without depending on candidate list order or display name."""
    signature = json.dumps(
        {
            "pit_lap": candidate.pit_lap,
            "next_compound": str(candidate.next_compound) if candidate.next_compound else None,
            "pace_mode": str(candidate.pace_mode),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.blake2b(signature, digest_size=16, person=b"apex-mc-v1").digest()
    entropy = np.frombuffer(digest, dtype=np.uint32).astype(np.uint64).tolist()
    return np.random.SeedSequence(
        [random_seed, session_id, driver_id, control_lap, *(int(value) for value in entropy)]
    )


def sample_pit_losses(
    rng: np.random.Generator,
    simulation_count: int,
    estimated_ms: int,
    uncertainty_ms: int,
    empirical_samples_ms: np.ndarray,
) -> np.ndarray:
    if len(empirical_samples_ms) >= 3:
        sampled = rng.choice(empirical_samples_ms, size=simulation_count, replace=True)
    else:
        sampled = rng.normal(estimated_ms, max(uncertainty_ms, 500), size=simulation_count)
    return np.clip(sampled, 10_000, 60_000)


def sample_degradation_slopes(
    rng: np.random.Generator,
    simulation_count: int,
    centre_ms: float,
    sigma_ms: float,
) -> np.ndarray:
    return np.clip(
        rng.normal(centre_ms, max(sigma_ms, 5), size=simulation_count),
        10,
        250,
    )


def sample_tyre_curve_uncertainty(
    rng: np.random.Generator,
    simulation_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Bounded severity and cliff-onset samples for the configured health curve."""
    config = DEFAULT_TYRE_PERFORMANCE_CONFIG
    coefficient_scale = np.clip(
        rng.normal(1.0, 0.04, simulation_count),
        config.coefficient_scale_min,
        config.coefficient_scale_max,
    )
    cliff_start_wear_pct = np.clip(
        rng.normal(config.cliff_start_wear_pct, 1.5, simulation_count), 45.0, 55.0
    )
    return coefficient_scale, cliff_start_wear_pct
