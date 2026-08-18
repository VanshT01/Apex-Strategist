from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.db.models import RaceEntry
from app.schemas.strategy import (
    MonteCarloAggregate,
    StrategyCandidate,
    StrategyOutcome,
)
from app.simulation.aggregation import aggregate_candidate
from app.simulation.calibration import UncertaintyCalibration
from app.simulation.deterministic import DeterministicStrategyEngine
from app.simulation.distributions import (
    sample_pit_losses,
    sample_tyre_curve_uncertainty,
    strategy_seed_sequence,
)
from app.simulation.interventions import InterventionScenarioSampler
from app.simulation.tyres import DEFAULT_TYRE_PERFORMANCE_CONFIG


@dataclass(frozen=True)
class CandidateSamples:
    total_times_ms: np.ndarray
    finish_positions: np.ndarray
    traffic_probability: float


class MonteCarloStrategyEngine:
    version = "monte-carlo-v2"
    lap_autocorrelation = 0.35

    def __init__(
        self,
        deterministic: DeterministicStrategyEngine,
        entries: list[RaceEntry],
        session_id: int,
        calibration: UncertaintyCalibration,
        simulation_count: int,
        random_seed: int,
    ) -> None:
        self.deterministic = deterministic
        self.entries = entries
        self.session_id = session_id
        self.calibration = calibration
        self.simulation_count = simulation_count
        self.random_seed = random_seed
        self.interventions = InterventionScenarioSampler(enabled=False)
        self.remaining_laps = deterministic.total_laps - deterministic.control_lap
        self._common_driver_delta, self._common_lap_delta = self._common_driver_draws()
        self._competitor_final_laps, self._competitor_times_ms = self._competitor_draws()

    def compare(
        self,
        candidates: list[StrategyCandidate],
        deterministic_outcomes: list[StrategyOutcome],
        stay_out_candidate: StrategyCandidate,
        stay_out_outcome: StrategyOutcome,
        actual_finish: int | None,
    ) -> list[MonteCarloAggregate]:
        stay_out_samples = self.sample_candidate(stay_out_candidate, stay_out_outcome)
        aggregates = []
        for candidate, outcome in zip(candidates, deterministic_outcomes, strict=True):
            samples = self.sample_candidate(candidate, outcome)
            aggregate = aggregate_candidate(
                total_times_ms=samples.total_times_ms,
                finish_positions=samples.finish_positions,
                # This delta describes stochastic spread around this candidate's own
                # deterministic projection. Stay-out comparisons are reported separately
                # through the paired improve_stay_out_probability field.
                deterministic_baseline_ms=outcome.predicted_total_time_ms,
                stay_out_times_ms=stay_out_samples.total_times_ms,
                stay_out_positions=stay_out_samples.finish_positions,
                actual_finish=actual_finish,
                simulation_count=self.simulation_count,
                random_seed=self.random_seed,
                engine_version=self.version,
                likely_rejoin_position=outcome.likely_rejoin_position,
                traffic_risk=samples.traffic_probability,
                degradation_risk=outcome.degradation_risk,
                data_quality=self.calibration.data_quality,
            )
            if outcome.dnf:
                aggregate = aggregate.model_copy(
                    update={
                        "win_probability": 0.0,
                        "podium_probability": 0.0,
                        "points_probability": 0.0,
                        "improve_actual_probability": 0.0,
                        "improve_stay_out_probability": 0.0,
                    }
                )
            aggregates.append(aggregate)
        return aggregates

    def sample_candidate(
        self, candidate: StrategyCandidate, outcome: StrategyOutcome
    ) -> CandidateSamples:
        rng = np.random.default_rng(
            strategy_seed_sequence(
                self.random_seed,
                self.session_id,
                self.deterministic.driver_id,
                self.deterministic.control_lap,
                candidate,
            )
        )
        total_delta = self._common_driver_delta + self._common_lap_delta
        total_delta = total_delta + self._degradation_delta(rng, candidate, outcome)
        if candidate.pit_lap is not None:
            pit_samples = sample_pit_losses(
                rng,
                self.simulation_count,
                self.deterministic.pit_loss.estimated_ms,
                self.deterministic.pit_loss.uncertainty_ms,
                self.calibration.pit_loss_samples_ms,
            )
            total_delta = total_delta + pit_samples - self.deterministic.pit_loss.estimated_ms
            intervention = self.interventions.sample(self.simulation_count, rng)
            total_delta = total_delta + intervention.pit_loss_adjustment_ms
            total_delta = total_delta + self._warmup_delta(rng, candidate)
            traffic_delta, traffic_probability = self._traffic_delta(rng, outcome.traffic_risk)
            total_delta = total_delta + traffic_delta
        else:
            traffic_probability = 0.0

        total_times = np.rint(outcome.predicted_total_time_ms + total_delta).astype(np.int64)
        if outcome.dnf:
            positions = np.full(self.simulation_count, len(self.entries), dtype=int)
        elif self._competitor_times_ms.shape[1]:
            completed_laps = (
                outcome.projected_laps[-1].lap_number
                if outcome.projected_laps
                else self.deterministic.control_lap
            )
            more_laps = int(np.sum(self._competitor_final_laps > completed_laps))
            same_lap = self._competitor_final_laps == completed_laps
            positions = np.full(self.simulation_count, 1 + more_laps, dtype=int)
            if np.any(same_lap):
                positions = positions + np.sum(
                    self._competitor_times_ms[:, same_lap] < total_times[:, np.newaxis],
                    axis=1,
                )
        else:
            positions = np.ones(self.simulation_count, dtype=int)
        positions = np.clip(positions, 1, len(self.entries)).astype(int)
        return CandidateSamples(total_times, positions, traffic_probability)

    def _common_driver_draws(self) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(
            np.random.SeedSequence(
                [
                    self.random_seed,
                    self.session_id,
                    self.deterministic.driver_id,
                    self.deterministic.control_lap,
                    0xA5E5,
                ]
            )
        )
        persistent_per_lap = np.clip(
            rng.normal(
                0,
                self.calibration.driver_pace_sigma_ms,
                size=self.simulation_count,
            ),
            -3 * self.calibration.driver_pace_sigma_ms,
            3 * self.calibration.driver_pace_sigma_ms,
        )
        persistent_total = persistent_per_lap * self.remaining_laps
        if self.remaining_laps <= 0:
            return persistent_total, np.zeros(self.simulation_count)

        sigma = self.calibration.lap_residual_sigma_ms
        innovations = rng.normal(
            0,
            sigma * np.sqrt(1 - self.lap_autocorrelation**2),
            size=(self.simulation_count, self.remaining_laps),
        )
        residuals = np.empty_like(innovations)
        residuals[:, 0] = rng.normal(0, sigma, size=self.simulation_count)
        for lap_index in range(1, self.remaining_laps):
            residuals[:, lap_index] = (
                self.lap_autocorrelation * residuals[:, lap_index - 1] + innovations[:, lap_index]
            )
        return persistent_total, np.sum(residuals, axis=1)

    def _competitor_draws(self) -> tuple[np.ndarray, np.ndarray]:
        final_times = []
        final_laps = []
        for entry in self.entries:
            if entry.driver_id == self.deterministic.driver_id:
                continue
            laps = self.deterministic.grouped.get(entry.driver_id, [])
            if not laps:
                continue
            final = laps[-1]
            if final.timestamp_ms is not None:
                final_laps.append(final.lap_number)
                final_times.append(final.timestamp_ms)
        if not final_times:
            return np.empty(0, dtype=int), np.empty((self.simulation_count, 0))

        rng = np.random.default_rng(
            np.random.SeedSequence(
                [
                    self.random_seed,
                    self.session_id,
                    self.deterministic.driver_id,
                    self.deterministic.control_lap,
                    0xC04F,
                ]
            )
        )
        competitor_count = len(final_times)
        persistent = (
            np.clip(
                rng.normal(
                    0,
                    self.calibration.driver_pace_sigma_ms * 0.75,
                    size=(self.simulation_count, competitor_count),
                ),
                -1_000,
                1_000,
            )
            * self.remaining_laps
        )
        aggregate_residual = rng.normal(
            0,
            self.calibration.lap_residual_sigma_ms * np.sqrt(max(self.remaining_laps, 1)) * 0.35,
            size=(self.simulation_count, competitor_count),
        )
        times = np.asarray(final_times)[np.newaxis, :] + persistent + aggregate_residual
        return np.asarray(final_laps, dtype=int), times

    def _degradation_delta(
        self,
        rng: np.random.Generator,
        candidate: StrategyCandidate,
        outcome: StrategyOutcome,
    ) -> np.ndarray:
        if not outcome.projected_laps:
            return np.zeros(self.simulation_count)

        coefficient_scale, cliff_start = sample_tyre_curve_uncertainty(rng, self.simulation_count)
        config = DEFAULT_TYRE_PERFORMANCE_CONFIG
        health = np.asarray(
            [lap.tyre_health_percent for lap in outcome.projected_laps], dtype=float
        )
        wear = 100.0 - np.clip(health, 0.0, 100.0)
        base = config.linear_coeff_seconds * wear + config.quadratic_coeff_seconds * wear**2
        sampled_cliff = np.maximum(0.0, wear[np.newaxis, :] - cliff_start[:, np.newaxis])
        sampled_loss_ms = (
            (base[np.newaxis, :] + config.cliff_coeff_seconds * sampled_cliff**2)
            * coefficient_scale[:, np.newaxis]
            * 1_000
        )
        deterministic_loss_ms = np.asarray(
            [lap.tyre_pace_loss_seconds * 1_000 for lap in outcome.projected_laps]
        )
        # The deterministic curve remains the expected-value anchor. Randomness changes
        # bounded curve severity/onset, never health or the hard failure decision.
        return np.sum(sampled_loss_ms - deterministic_loss_ms[np.newaxis, :], axis=1)

    def _warmup_delta(self, rng: np.random.Generator, candidate: StrategyCandidate) -> np.ndarray:
        compound = str(candidate.next_compound) if candidate.next_compound else "MEDIUM"
        sigma = self.calibration.warmup_sigma_ms.get(compound, 300)
        first_lap = np.clip(rng.normal(0, sigma, size=self.simulation_count), -2 * sigma, 2 * sigma)
        second_lap = np.clip(rng.normal(0, sigma * 0.5, size=self.simulation_count), -sigma, sigma)
        return first_lap + second_lap

    def _traffic_delta(
        self, rng: np.random.Generator, deterministic_risk: float
    ) -> tuple[np.ndarray, float]:
        probability = float(np.clip(0.05 + 0.65 * deterministic_risk, 0.05, 0.8))
        mean_loss = 1_200 + 2_800 * deterministic_risk
        losses = np.clip(
            rng.gamma(shape=2.0, scale=mean_loss / 2, size=self.simulation_count),
            300,
            7_000,
        )
        occurs = rng.random(self.simulation_count) < probability
        # Mean-centering retains the deterministic projection as the expected-value anchor.
        centred = occurs * losses - probability * float(np.mean(losses))
        return centred, probability
