from __future__ import annotations

import numpy as np

from app.schemas.strategy import (
    FinishPositionBucket,
    HistogramBin,
    MonteCarloAggregate,
)


def _rounded_ms(value: float) -> int:
    """Round model output to 0.1 seconds to avoid false millisecond precision."""
    return int(round(value / 100) * 100)


def _probability(mask: np.ndarray) -> float:
    return round(float(np.mean(mask)), 4)


def aggregate_candidate(
    *,
    total_times_ms: np.ndarray,
    finish_positions: np.ndarray,
    deterministic_baseline_ms: int,
    stay_out_times_ms: np.ndarray,
    stay_out_positions: np.ndarray,
    actual_finish: int | None,
    simulation_count: int,
    random_seed: int,
    engine_version: str,
    likely_rejoin_position: int | None,
    traffic_risk: float,
    degradation_risk: float,
    data_quality: str,
) -> MonteCarloAggregate:
    time_delta = total_times_ms - deterministic_baseline_ms
    unique_positions, position_counts = np.unique(finish_positions, return_counts=True)
    finish_distribution = [
        FinishPositionBucket(
            position=int(position),
            count=int(count),
            probability=round(int(count) / simulation_count, 4),
        )
        for position, count in zip(unique_positions, position_counts, strict=True)
    ]

    lower = float(np.min(time_delta))
    upper = float(np.max(time_delta))
    if np.isclose(lower, upper):
        lower -= 500
        upper += 500
    counts, edges = np.histogram(time_delta, bins=12, range=(lower, upper))
    histogram = [
        HistogramBin(
            lower_ms=_rounded_ms(float(edges[index])),
            upper_ms=_rounded_ms(float(edges[index + 1])),
            count=int(count),
            probability=round(int(count) / simulation_count, 4),
        )
        for index, count in enumerate(counts)
    ]

    position_frequency = np.bincount(finish_positions.astype(int))
    most_likely = int(np.flatnonzero(position_frequency == position_frequency.max())[0])
    better_than_stay_out = (finish_positions < stay_out_positions) | (
        (finish_positions == stay_out_positions) & (total_times_ms < stay_out_times_ms)
    )
    percentiles = np.quantile(total_times_ms, [0.05, 0.25, 0.5, 0.75, 0.95])
    finish_percentiles = np.quantile(finish_positions, [0.05, 0.5, 0.95], method="nearest").astype(
        int
    )
    return MonteCarloAggregate(
        mean_predicted_finish=round(float(np.mean(finish_positions)), 2),
        median_predicted_finish=round(float(finish_percentiles[1]), 1),
        most_likely_finish=most_likely,
        expected_total_time_ms=_rounded_ms(float(np.mean(total_times_ms))),
        median_total_time_ms=_rounded_ms(float(percentiles[2])),
        mean_time_vs_deterministic_baseline_ms=_rounded_ms(float(np.mean(time_delta))),
        median_time_vs_deterministic_baseline_ms=_rounded_ms(float(np.median(time_delta))),
        win_probability=_probability(finish_positions == 1),
        podium_probability=_probability(finish_positions <= 3),
        points_probability=_probability(finish_positions <= 10),
        improve_actual_probability=(
            _probability(finish_positions < actual_finish) if actual_finish is not None else None
        ),
        improve_stay_out_probability=_probability(better_than_stay_out),
        race_time_p05_ms=_rounded_ms(float(percentiles[0])),
        race_time_p25_ms=_rounded_ms(float(percentiles[1])),
        race_time_p75_ms=_rounded_ms(float(percentiles[3])),
        race_time_p95_ms=_rounded_ms(float(percentiles[4])),
        finish_position_p05=int(finish_percentiles[0]),
        finish_position_p95=int(finish_percentiles[2]),
        likely_rejoin_position=likely_rejoin_position,
        traffic_risk=round(traffic_risk, 3),
        degradation_risk=round(degradation_risk, 3),
        finish_position_distribution=finish_distribution,
        time_delta_histogram=histogram,
        simulation_count=simulation_count,
        random_seed=random_seed,
        engine_version=engine_version,
        data_quality=data_quality,
    )
