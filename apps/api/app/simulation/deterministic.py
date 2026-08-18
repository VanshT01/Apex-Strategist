from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median
from typing import TYPE_CHECKING

import numpy as np

from app.db.models import Lap, RaceEntry, WeatherSample
from app.schemas.race_state import PitLossEstimate
from app.schemas.strategy import (
    PaceMode,
    ProjectedLapRead,
    SimulationContext,
    StrategyCandidate,
    StrategyOutcome,
)
from app.simulation.tyres import (
    DEFAULT_TYRE_PERFORMANCE_CONFIG,
    TyreDegradationEstimator,
    advance_tyre_health,
    is_automatic_tyre_failure,
    tyre_pace_loss_seconds,
    tyre_state,
    tyre_wear_pct,
)
from app.simulation.weather import TyreWeatherModel

if TYPE_CHECKING:
    from app.simulation.pace_model import SessionPacePredictor

PACE_OFFSET_MS = {
    PaceMode.CONSERVATIVE: 300,
    PaceMode.BALANCED: 0,
    PaceMode.AGGRESSIVE: -250,
}
PACE_DEGRADATION_MULTIPLIER = {
    PaceMode.CONSERVATIVE: 0.85,
    PaceMode.BALANCED: 1.0,
    PaceMode.AGGRESSIVE: 1.2,
}


@dataclass(frozen=True)
class FieldTrace:
    entry: RaceEntry
    laps: list[Lap]


class DeterministicStrategyEngine:
    version = "deterministic-v2"

    def __init__(
        self,
        all_laps: list[Lap],
        entries: list[RaceEntry],
        driver_id: int,
        control_lap: int,
        total_laps: int,
        pit_loss: PitLossEstimate,
        degradation_multiplier: float = 1.0,
        simulation_context: SimulationContext | None = None,
        weather_samples: list[WeatherSample] | None = None,
        pace_predictor: SessionPacePredictor | None = None,
    ) -> None:
        grouped: dict[int, list[Lap]] = defaultdict(list)
        for lap in all_laps:
            grouped[lap.driver_id].append(lap)
        for values in grouped.values():
            values.sort(key=lambda lap: lap.lap_number)
        self.grouped = grouped
        self.entries = entries
        self.driver_id = driver_id
        self.control_lap = control_lap
        self.total_laps = total_laps
        self.pit_loss = pit_loss
        self.degradation_multiplier = degradation_multiplier
        self.simulation_context = simulation_context
        self.driver_laps = grouped[driver_id]
        self.control = next(lap for lap in self.driver_laps if lap.lap_number == control_lap)
        self.tyres = TyreDegradationEstimator(all_laps)
        self.weather = TyreWeatherModel(all_laps, weather_samples or [])
        self.pace_predictor = pace_predictor
        self.base_pace_ms = self._recent_pace()
        final_lap = self.driver_laps[-1]
        self.actual_total_ms = (
            final_lap.timestamp_ms if final_lap.lap_number >= self.total_laps else None
        )
        self.leader_finish_ms = min(
            (
                lap.timestamp_ms
                for laps in self.grouped.values()
                for lap in laps
                if lap.lap_number >= self.total_laps and lap.timestamp_ms is not None
            ),
            default=None,
        )

    def simulate(self, candidate: StrategyCandidate, baseline_time_ms: int) -> StrategyOutcome:
        current_compound = (
            str(self.simulation_context.current_compound)
            if self.simulation_context and self.simulation_context.current_compound
            else self.control.compound or "MEDIUM"
        )
        current_age = (
            self.simulation_context.current_tyre_age
            if self.simulation_context and self.simulation_context.current_tyre_age is not None
            else self.control.tyre_life or 1.0
        )
        current_effective_age = (
            self.simulation_context.current_effective_tyre_age
            if self.simulation_context
            and self.simulation_context.current_effective_tyre_age is not None
            else float(current_age)
        )
        current_health = (
            self.simulation_context.current_tyre_health_pct
            if self.simulation_context
            and self.simulation_context.current_tyre_health_pct is not None
            else self.tyres.health_percent(current_compound, current_effective_age)
        )
        starting_delta = (
            self.simulation_context.cumulative_time_delta_ms if self.simulation_context else 0
        )
        next_compound = str(candidate.next_compound) if candidate.next_compound else None
        selected_estimate = self.tyres.estimate(next_compound or current_compound)
        elapsed = (
            self.simulation_context.current_timestamp_ms
            if self.simulation_context and self.simulation_context.current_timestamp_ms is not None
            else (self.control.timestamp_ms or self._elapsed_proxy()) + starting_delta
        )
        remaining_ms = 0.0
        final_age = float(current_age)
        final_health = float(current_health)
        baseline_elapsed = float(elapsed)
        cumulative_delta = float(starting_delta)
        projected_laps: list[ProjectedLapRead] = []
        did_dnf = False
        reached_chequered = False
        maximum_weather_risk = 0.0
        player_elapsed = float(elapsed)
        player_position = (
            self.simulation_context.current_position
            if self.simulation_context and self.simulation_context.current_position
            else self.control.position or 10
        )
        current_stint = (
            self.simulation_context.current_stint_number
            if self.simulation_context and self.simulation_context.current_stint_number
            else self.control.stint_number or 1
        )
        driver_laps_by_number = {lap.lap_number: lap for lap in self.driver_laps}
        active_compound = current_compound
        active_age = float(current_age)
        active_effective_age = float(current_effective_age)
        active_health = float(current_health)

        for racing_lap in range(self.control_lap + 1, self.total_laps + 1):
            recorded_lap = driver_laps_by_number.get(racing_lap)
            pit_stop = candidate.pit_lap is not None and racing_lap == candidate.pit_lap + 1
            if pit_stop:
                active_compound = next_compound or current_compound
                active_age = 1.0
                active_effective_age = 1.0
                start_health = 100.0
                end_health = 100.0
                stint_number = current_stint + 1
            else:
                start_health = active_health
                active_age += 1.0
                stint_number = current_stint + (1 if active_compound != current_compound else 0)
            compound = active_compound
            estimate = self.tyres.estimate(compound)
            condition = self.weather.condition(racing_lap)
            weather_effect = self.weather.effect(compound, condition)
            maximum_weather_risk = max(maximum_weather_risk, weather_effect.risk)
            if not pit_stop:
                wear_exposure = (
                    weather_effect.wear_multiplier
                    * PACE_DEGRADATION_MULTIPLIER[candidate.pace_mode]
                    * self.degradation_multiplier
                )
                health_consumed = self.tyres.wear_for_lap(
                    compound, active_effective_age, wear_exposure
                )
                active_effective_age += wear_exposure
                end_health = advance_tyre_health(start_health, health_consumed).end_health_pct
            effective_age = active_effective_age
            average_health = (start_health + end_health) / 2
            degradation = tyre_pace_loss_seconds(average_health) * 1_000
            pace_delta = PACE_OFFSET_MS[candidate.pace_mode]
            warmup = 800 if pit_stop else 0
            learned_pace = (
                self.pace_predictor.predict_lap_ms(
                    lap_number=racing_lap,
                    compound=compound,
                    tyre_age=1.0,
                    position=player_position,
                    stint_number=stint_number,
                )
                if self.pace_predictor
                else None
            )
            if learned_pace is None:
                projected_lap_time = max(
                    self.base_pace_ms
                    + estimate.initial_offset_ms
                    + degradation
                    + pace_delta
                    + warmup
                    + weather_effect.pace_penalty_ms,
                    60_000,
                )
            else:
                projected_lap_time = max(
                    learned_pace
                    + PACE_OFFSET_MS[candidate.pace_mode]
                    + degradation
                    + warmup
                    + weather_effect.pace_penalty_ms,
                    60_000,
                )
            final_age = active_age
            final_health = end_health

            recorded_compound = (
                recorded_lap.compound
                if recorded_lap and recorded_lap.compound
                else current_compound
            )
            recorded_age = (
                recorded_lap.tyre_life
                if recorded_lap and recorded_lap.tyre_life is not None
                else current_age + (racing_lap - self.control_lap)
            )
            recorded_estimate = self.tyres.estimate(recorded_compound)
            recorded_weather_effect = self.weather.effect(recorded_compound, condition)
            recorded_health = self.tyres.health_percent(recorded_compound, recorded_age)
            recorded_degradation = tyre_pace_loss_seconds(recorded_health) * 1_000
            recorded_pit_stop = bool(recorded_lap and recorded_lap.pit_out)
            recorded_warmup = 800 if recorded_pit_stop else 0
            learned_recorded_pace = (
                self.pace_predictor.predict_lap_ms(
                    lap_number=racing_lap,
                    compound=recorded_compound,
                    tyre_age=1.0,
                    position=recorded_lap.position
                    if recorded_lap and recorded_lap.position
                    else 10,
                    stint_number=(
                        recorded_lap.stint_number
                        if recorded_lap and recorded_lap.stint_number
                        else 1
                    ),
                )
                if self.pace_predictor
                else None
            )
            if learned_recorded_pace is None:
                recorded_model_lap_time = max(
                    self.base_pace_ms
                    + recorded_estimate.initial_offset_ms
                    + recorded_degradation
                    + recorded_warmup
                    + recorded_weather_effect.pace_penalty_ms,
                    60_000,
                )
            else:
                recorded_model_lap_time = max(
                    learned_recorded_pace
                    + recorded_degradation
                    + recorded_warmup
                    + recorded_weather_effect.pace_penalty_ms,
                    60_000,
                )
            baseline_elapsed += recorded_model_lap_time
            tyre_failure = is_automatic_tyre_failure(end_health)
            lap_fraction = 1.0
            if tyre_failure:
                health_drop = max(start_health - end_health, 0.0)
                lap_fraction = (
                    float(np.clip((start_health - 5.0) / health_drop, 0.0, 1.0))
                    if health_drop > 0
                    else 0.0
                )
            elapsed_lap_time = projected_lap_time * lap_fraction
            remaining_ms += elapsed_lap_time
            cumulative_delta += elapsed_lap_time - recorded_model_lap_time * lap_fraction
            if pit_stop:
                cumulative_delta += self.pit_loss.estimated_ms
            if recorded_pit_stop:
                cumulative_delta -= self.pit_loss.estimated_ms
            historical_anchor = (
                float(recorded_lap.timestamp_ms)
                if recorded_lap and recorded_lap.timestamp_ms is not None
                else baseline_elapsed
            )
            player_elapsed += elapsed_lap_time + (self.pit_loss.estimated_ms if pit_stop else 0)
            projected_cumulative = (
                round(player_elapsed)
                if self.simulation_context is not None
                else round(historical_anchor + cumulative_delta)
            )
            reached_chequered = bool(
                not tyre_failure
                and self.leader_finish_ms is not None
                and projected_cumulative >= self.leader_finish_ms
            )
            predicted_position = (
                len(self.entries)
                if tyre_failure
                else self._classification_position(racing_lap, projected_cumulative)
                if reached_chequered
                else self._position_at_lap(racing_lap, projected_cumulative)
            )
            projected_laps.append(
                ProjectedLapRead(
                    lap_number=racing_lap,
                    compound=compound,
                    tyre_age=round(active_age, 3),
                    stint_number=stint_number,
                    effective_tyre_age=round(effective_age, 3),
                    tyre_health_percent=round(end_health, 3),
                    tyre_wear_pct=round(tyre_wear_pct(end_health), 3),
                    tyre_pace_loss_seconds=round(tyre_pace_loss_seconds(end_health), 3),
                    tyre_state=tyre_state(end_health),
                    lap_time_ms=round(
                        elapsed_lap_time + (self.pit_loss.estimated_ms if pit_stop else 0)
                    ),
                    cumulative_time_ms=projected_cumulative,
                    historical_time_ms=round(historical_anchor),
                    predicted_position=predicted_position,
                    pit_stop=pit_stop,
                    dnf=tyre_failure,
                    status=(
                        "TYRE FAILURE"
                        if tyre_failure
                        else "CHEQUERED"
                        if reached_chequered
                        else None
                    ),
                    retirement_reason="TYRE_FAILURE" if tyre_failure else None,
                    lap_completed=not tyre_failure,
                )
            )
            player_position = projected_laps[-1].predicted_position
            active_health = end_health
            if tyre_failure:
                did_dnf = True
                break
            if reached_chequered:
                break

        applied_pit_loss = (
            self.pit_loss.estimated_ms if any(lap.pit_stop for lap in projected_laps) else 0
        )
        raw_total = round(elapsed + remaining_ms + applied_pit_loss)
        if did_dnf:
            classified_times = [
                laps[-1].timestamp_ms
                for driver_id, laps in self.grouped.items()
                if driver_id != self.driver_id and laps and laps[-1].timestamp_ms is not None
            ]
            predicted_total = max(classified_times, default=raw_total) + 3_600_000
        elif projected_laps:
            predicted_total = projected_laps[-1].cumulative_time_ms
        elif baseline_time_ms == 0:
            predicted_total = raw_total
        else:
            recorded_anchor = (self.actual_total_ms or baseline_time_ms) + starting_delta
            predicted_total = recorded_anchor + (raw_total - baseline_time_ms)
        completed_laps = (
            projected_laps[-1].lap_number
            if projected_laps and projected_laps[-1].lap_completed
            else projected_laps[-1].lap_number - 1
            if projected_laps
            else self.control_lap
        )
        finish = (
            len(self.entries)
            if did_dnf
            else self._classification_position(completed_laps, predicted_total)
        )
        rejoin_position, traffic_risk = self._rejoin(candidate)
        supported_age, supported_age_source = self.tyres.supported_age(
            next_compound or current_compound
        )
        degradation_risk = float(
            np.clip(
                (70.0 - final_health) / 65.0 + maximum_weather_risk,
                0,
                1,
            )
        )
        assumptions = [
            "Competitors follow their recorded historical race trajectories.",
            "Counterfactual time is anchored to the recorded result and historical conditions.",
            "No unrecorded Safety Car, weather, damage, or team order response is introduced.",
            (
                f"Pit loss uses {self.pit_loss.source.replace('_', ' ')} "
                f"({self.pit_loss.sample_count} samples)."
            ),
            f"Tyre estimate uses {selected_estimate.source.replace('_', ' ')} data.",
            f"Scenario tyre degradation multiplier is {self.degradation_multiplier:.2f}×.",
            (
                "Tyre/track compatibility uses lap weather and field compound choice; "
                "tyres in the wrong conditions receive explicit pace, wear, and safety penalties."
            ),
            (
                "Field stints calibrate health consumption "
                f"({supported_age_source.replace('_', ' ')}; "
                f"performance life {supported_age} laps, durability "
                f"{selected_estimate.durability_laps:.1f} laps). Health converts to seconds lost "
                "through the shared nonlinear tyre curve, with a cliff below 50% health."
            ),
            (
                "Exactly 5.0% tyre health remains running; strictly below 5.0% retires "
                "with tyre failure."
            ),
            (
                "The player is classified at the first finish line crossing after the recorded "
                "leader takes the chequered flag; completed laps rank ahead of elapsed time."
            ),
        ]
        if self.pace_predictor:
            assumptions.append(
                "Expected clean lap pace uses a CPU gradient boosting model trained only on "
                f"earlier races: {self.pace_predictor.source}."
            )
            assumptions.append(
                "The selected driver's future laps are excluded; only completed laps adapt the "
                "driver offset. Recorded competitors provide the documented field/track anchor."
            )
        return StrategyOutcome(
            name=candidate.name,
            pit_lap=candidate.pit_lap,
            next_compound=next_compound,
            pace_mode=candidate.pace_mode,
            predicted_finish=finish,
            predicted_total_time_ms=predicted_total,
            time_vs_actual_ms=(
                predicted_total - self.actual_total_ms if self.actual_total_ms is not None else None
            ),
            time_vs_baseline_ms=raw_total - baseline_time_ms,
            likely_rejoin_position=rejoin_position,
            traffic_risk=round(traffic_risk, 2),
            degradation_risk=round(degradation_risk, 2),
            final_tyre_age=round(final_age, 1),
            pit_loss_ms=applied_pit_loss,
            tyre_estimate=selected_estimate.to_schema(),
            assumptions=assumptions,
            projected_laps=projected_laps,
            dnf=did_dnf,
            current_tyre_health_pct=round(float(current_health), 3),
            current_tyre_wear_pct=round(tyre_wear_pct(current_health), 3),
            current_tyre_pace_loss_seconds=round(tyre_pace_loss_seconds(current_health), 3),
            projected_next_lap_health_pct=(
                projected_laps[0].tyre_health_percent if projected_laps else None
            ),
            projected_next_lap_pace_loss_seconds=(
                projected_laps[0].tyre_pace_loss_seconds if projected_laps else None
            ),
            cliff_start_health_pct=(100.0 - DEFAULT_TYRE_PERFORMANCE_CONFIG.cliff_start_wear_pct),
            tyre_state=tyre_state(current_health),
            retirement_reason="TYRE_FAILURE" if did_dnf else None,
            calibration_source=selected_estimate.life_source,
        )

    def baseline_time(self) -> int:
        baseline = StrategyCandidate(name="Deterministic baseline")
        return self._raw_total(baseline)

    def _raw_total(self, candidate: StrategyCandidate) -> int:
        # A zero reference avoids recursively requiring an outcome baseline.
        return self.simulate(candidate, 0).predicted_total_time_ms

    def effective_tyre_age(self, compound: str, age: float) -> float:
        """Compatibility helper: effective age is now a cumulative state value."""
        return max(float(age), 0.0)

    def degradation_penalty_ms(self, compound: str, age: float) -> float:
        """Compatibility API exposing the first-class health penalty in milliseconds."""
        health = self.tyres.health_percent(compound, age)
        return tyre_pace_loss_seconds(health) * 1_000

    def _tyre_life_cliff_penalty(self, compound: str, age: float) -> float:
        """Deprecated compatibility alias; the health curve already includes the cliff."""
        return self.degradation_penalty_ms(compound, age)

    def _recent_pace(self) -> int:
        eligible = [
            lap
            for lap in self.driver_laps
            if lap.lap_number <= self.control_lap
            and lap.lap_time_ms is not None
            and not lap.pit_in
            and not lap.pit_out
            and not lap.deleted
            and lap.track_status in {None, "1", "2"}
        ][-3:]
        if eligible:
            # Normalize observed laps back to a fresh reference. The explicit health curve
            # is added later, avoiding both double-counting and an anchor that hides wear.
            fresh_equivalents = [
                float(lap.lap_time_ms or 0)
                - self.tyres.estimate(lap.compound or "MEDIUM").initial_offset_ms
                - tyre_pace_loss_seconds(
                    self.tyres.health_percent(lap.compound or "MEDIUM", lap.tyre_life or 1)
                )
                * 1_000
                for lap in eligible
            ]
            return round(mean(fresh_equivalents))
        session_times = [
            lap.lap_time_ms
            for values in self.grouped.values()
            for lap in values
            if lap.lap_time_ms is not None and not lap.pit_in and not lap.pit_out
        ]
        return round(median(session_times)) if session_times else 90_000

    def _elapsed_proxy(self) -> int:
        times = [
            lap.lap_time_ms
            for lap in self.driver_laps
            if lap.lap_number <= self.control_lap and lap.lap_time_ms
        ]
        return sum(times)

    def _classification_position(self, completed_laps: int, predicted_total: int) -> int:
        ahead = 0
        for entry in self.entries:
            if entry.driver_id == self.driver_id:
                continue
            laps = self.grouped.get(entry.driver_id, [])
            if not laps:
                continue
            final = laps[-1]
            if final.lap_number > completed_laps:
                ahead += 1
            elif (
                final.lap_number == completed_laps
                and final.timestamp_ms is not None
                and final.timestamp_ms <= predicted_total
            ):
                ahead += 1
        return max(1, min(ahead + 1, len(self.entries)))

    def _position_at_lap(self, lap_number: int, projected_time_ms: int) -> int:
        ahead = 0
        comparable = 0
        for driver_id, laps in self.grouped.items():
            if driver_id == self.driver_id:
                continue
            lap = next((item for item in laps if item.lap_number == lap_number), None)
            if lap is None or lap.timestamp_ms is None:
                continue
            comparable += 1
            # At end-of-lap timing precision, an exact timestamp tie means the
            # counterfactual leader has no defensible gap left. Resolve it in favor
            # of the recorded competitor instead of displaying 0.000s while keeping
            # the simulated driver ahead.
            ahead += lap.timestamp_ms <= projected_time_ms
        if comparable == 0:
            return (
                self.simulation_context.current_position
                if self.simulation_context and self.simulation_context.current_position
                else self.control.position or 1
            )
        return max(1, min(ahead + 1, len(self.entries)))

    def _rejoin(self, candidate: StrategyCandidate) -> tuple[int | None, float]:
        if candidate.pit_lap is None:
            return (
                self.simulation_context.current_position
                if self.simulation_context and self.simulation_context.current_position
                else self.control.position,
                0.0,
            )
        selected_at_pit = next(
            (lap for lap in self.driver_laps if lap.lap_number == candidate.pit_lap), None
        )
        if selected_at_pit is None or selected_at_pit.timestamp_ms is None:
            return None, 0.5
        target = (
            selected_at_pit.timestamp_ms
            + self.pit_loss.estimated_ms
            + (self.simulation_context.cumulative_time_delta_ms if self.simulation_context else 0)
        )
        comparable = [
            values[candidate.pit_lap - 1]
            for driver_id, values in self.grouped.items()
            if driver_id != self.driver_id
            and len(values) >= candidate.pit_lap
            and values[candidate.pit_lap - 1].lap_number == candidate.pit_lap
            and values[candidate.pit_lap - 1].timestamp_ms is not None
        ]
        position = 1 + sum((lap.timestamp_ms or 0) < target for lap in comparable)
        close_cars = sum(abs((lap.timestamp_ms or 0) - target) <= 4_000 for lap in comparable)
        return position, float(np.clip(close_cars / 4, 0, 1))
