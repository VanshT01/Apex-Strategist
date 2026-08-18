from dataclasses import dataclass
from statistics import median

import numpy as np

from app.db.models import Lap
from app.schemas.strategy import TyreEstimateRead

DEFAULT_DEGRADATION = {
    "SOFT": 110,
    "MEDIUM": 75,
    "HARD": 50,
    "INTERMEDIATE": 90,
    "WET": 110,
}
COMPOUND_OFFSET_PRIOR = {
    "SOFT": -350,
    "MEDIUM": 0,
    "HARD": 350,
    "INTERMEDIATE": 1_200,
    "WET": 2_500,
}
SUPPORTED_AGE_FALLBACK = {
    "SOFT": 25,
    "MEDIUM": 35,
    "HARD": 45,
    "INTERMEDIATE": 30,
    "WET": 35,
}
MIN_STINT_LAPS = 4


@dataclass(frozen=True)
class TyrePerformanceConfig:
    """Gameplay pace curve expressed in seconds lost per lap.

    Historical data calibrates how quickly health is consumed.  This curve converts
    that health into pace, so a weak historical slope cannot make destroyed tyres
    unrealistically competitive.
    """

    linear_coeff_seconds: float = 0.015
    quadratic_coeff_seconds: float = 0.00225
    cliff_start_wear_pct: float = 50.0
    cliff_coeff_seconds: float = 0.006
    automatic_failure_health_pct: float = 5.0
    coefficient_scale_min: float = 0.9
    coefficient_scale_max: float = 1.1


DEFAULT_TYRE_PERFORMANCE_CONFIG = TyrePerformanceConfig()


@dataclass(frozen=True)
class TyreHealthTransition:
    start_health_pct: float
    end_health_pct: float
    wear_pct: float
    failed: bool


def clamp_tyre_health(tyre_health_pct: float) -> float:
    return float(np.clip(tyre_health_pct, 0.0, 100.0))


def tyre_wear_pct(tyre_health_pct: float) -> float:
    return 100.0 - clamp_tyre_health(tyre_health_pct)


def tyre_pace_loss_seconds(
    tyre_health_pct: float,
    config: TyrePerformanceConfig = DEFAULT_TYRE_PERFORMANCE_CONFIG,
    coefficient_scale: float = 1.0,
    cliff_start_wear_pct: float | None = None,
) -> float:
    """Return the smooth nonlinear tyre-only pace loss for one lap."""
    wear = tyre_wear_pct(tyre_health_pct)
    scale = float(
        np.clip(coefficient_scale, config.coefficient_scale_min, config.coefficient_scale_max)
    )
    cliff_start = (
        config.cliff_start_wear_pct
        if cliff_start_wear_pct is None
        else float(np.clip(cliff_start_wear_pct, 45.0, 55.0))
    )
    base_loss = config.linear_coeff_seconds * wear + config.quadratic_coeff_seconds * wear**2
    cliff_wear = max(0.0, wear - cliff_start)
    cliff_loss = config.cliff_coeff_seconds * cliff_wear**2
    return (base_loss + cliff_loss) * scale


def tyre_state(tyre_health_pct: float) -> str:
    health = clamp_tyre_health(tyre_health_pct)
    if health < DEFAULT_TYRE_PERFORMANCE_CONFIG.automatic_failure_health_pct:
        return "FAILED"
    if health < 10.0:
        return "FAILURE_IMMINENT"
    if health < 30.0:
        return "CRITICAL"
    if health < 50.0:
        return "SEVERE"
    if health < 60.0:
        return "SEVERE"
    if health < 70.0:
        return "HIGH_DEGRADATION"
    if health < 80.0:
        return "DEGRADING"
    return "HEALTHY"


def is_automatic_tyre_failure(
    tyre_health_pct: float,
    config: TyrePerformanceConfig = DEFAULT_TYRE_PERFORMANCE_CONFIG,
) -> bool:
    """The gameplay threshold is deliberately strict: 5.0 survives, 4.999 fails."""
    return clamp_tyre_health(tyre_health_pct) < config.automatic_failure_health_pct


def advance_tyre_health(
    start_health_pct: float,
    lap_wear_pct: float,
) -> TyreHealthTransition:
    start = clamp_tyre_health(start_health_pct)
    end = clamp_tyre_health(start - max(float(lap_wear_pct), 0.0))
    return TyreHealthTransition(
        start_health_pct=start,
        end_health_pct=end,
        wear_pct=start - end,
        failed=is_automatic_tyre_failure(end),
    )


@dataclass(frozen=True)
class StintLifeObservation:
    driver_id: int
    stint_number: int
    compound: str
    end_age: float
    lap_count: int
    changed_tyre: bool


@dataclass(frozen=True)
class TyreLifeEstimate:
    performance_life_laps: float
    durability_laps: float
    stint_sample_count: int
    completed_stint_count: int
    observed_max_age: float
    source: str


@dataclass(frozen=True)
class TyreEstimate:
    compound: str
    initial_offset_ms: int
    degradation_per_lap_ms: int
    sample_count: int
    source: str
    uncertainty_ms: int
    degradation_uncertainty_per_lap_ms: int
    performance_life_laps: float
    durability_laps: float
    stint_sample_count: int
    life_source: str

    def to_schema(self) -> TyreEstimateRead:
        return TyreEstimateRead(**self.__dict__)


class TyreDegradationEstimator:
    """Fit pace loss and usable life from every driver's stints in one event."""

    def __init__(self, laps: list[Lap]) -> None:
        self.laps = laps
        self.clean = [
            lap
            for lap in laps
            if lap.lap_time_ms is not None
            and lap.tyre_life is not None
            and lap.compound in DEFAULT_DEGRADATION
            and not lap.pit_in
            and not lap.pit_out
            and not lap.deleted
            and not lap.inaccurate
            and lap.track_status in {None, "1", "2"}
        ]
        lap_times = [lap.lap_time_ms for lap in self.clean if lap.lap_time_ms is not None]
        self.event_median = round(median(lap_times)) if lap_times else 90_000
        self.field_median_by_lap = self._field_medians()
        self.stints = self._stint_observations()
        self._life_cache: dict[str, TyreLifeEstimate] = {}
        self._estimate_cache: dict[str, TyreEstimate] = {}

    def available_compounds(self) -> list[str]:
        return sorted({*DEFAULT_DEGRADATION, *(lap.compound for lap in self.clean if lap.compound)})

    def supported_age(self, compound: str) -> tuple[int, str]:
        """Return the field-calibrated age where the performance cliff begins."""
        life = self.life_estimate(compound)
        return max(round(life.performance_life_laps), 1), life.source

    def performance_life(self, compound: str) -> float:
        """Field-calibrated age where the nonlinear performance cliff begins."""
        return self.life_estimate(compound).performance_life_laps

    def durability_age(self, compound: str) -> float:
        """Conservative terminal age, kept beyond every observed surviving stint."""
        return self.life_estimate(compound).durability_laps

    def life_estimate(self, compound: str) -> TyreLifeEstimate:
        cached = self._life_cache.get(compound)
        if cached is not None:
            return cached

        prior = float(SUPPORTED_AGE_FALLBACK.get(compound, 35))
        observations = [item for item in self.stints if item.compound == compound]
        completed = [item.end_age for item in observations if item.changed_tyre]
        observed_max = max((item.end_age for item in observations), default=0.0)

        if len(completed) >= 3:
            # Pit-ended stints tell us where teams stopped using the compound. Race-ending
            # stints are right-censored: they prove survival, not that the tyre was exhausted.
            field_service_age = float(np.quantile(completed, 0.75))
            evidence_weight = min(0.75, len(completed) / 12)
            performance_life = (1 - evidence_weight) * prior + evidence_weight * field_service_age
            performance_life = float(np.clip(performance_life, prior * 0.65, prior * 1.3))
            source = "event_field_stint_model"
        elif len(observations) >= 3:
            performance_life = prior
            source = "event_censored_stint_fallback"
        else:
            performance_life = prior
            source = "compound_life_fallback"

        # Never predict failure before an observed set survived. A short three-lap buffer
        # beyond the longest observed age prevents one extreme stint from granting the old
        # additional 40% of life, while keeping the rule conservative and explainable.
        durability = max(
            performance_life + max(6.0, performance_life * 0.25),
            observed_max + 3.0 if observed_max else 0.0,
        )
        estimate = TyreLifeEstimate(
            performance_life_laps=round(performance_life, 1),
            durability_laps=round(durability, 1),
            stint_sample_count=len(observations),
            completed_stint_count=len(completed),
            observed_max_age=round(observed_max, 1),
            source=source,
        )
        self._life_cache[compound] = estimate
        return estimate

    def cliff_progress(self, compound: str, age: float) -> float:
        """Smooth progress from 0 to 1 between the performance cliff and terminal reserve."""
        performance_life = self.performance_life(compound)
        durability_age = self.durability_age(compound)
        raw = float(
            np.clip(
                (age - performance_life) / max(durability_age - performance_life, 1),
                0,
                1,
            )
        )
        return raw * raw * (3 - 2 * raw)

    def estimate(self, compound: str) -> TyreEstimate:
        cached = self._estimate_cache.get(compound)
        if cached is not None:
            return cached
        samples = [lap for lap in self.clean if lap.compound == compound]
        life = self.life_estimate(compound)
        stint_slopes = self._stint_slopes(compound)
        if len(samples) >= 8 and len({lap.tyre_life for lap in samples}) >= 4:
            ages = np.asarray([lap.tyre_life for lap in samples], dtype=float)
            times = np.asarray([lap.lap_time_ms for lap in samples], dtype=float)
            lower, upper = np.quantile(times, [0.1, 0.9])
            mask = (times >= lower) & (times <= upper)
            pooled_slope, intercept = np.polyfit(ages[mask], times[mask], 1)
            slope = float(np.median(stint_slopes)) if len(stint_slopes) >= 3 else pooled_slope
            bounded_slope = round(float(np.clip(slope, 20, 220)))
            predicted = intercept + bounded_slope * ages[mask]
            residuals = times[mask] - predicted
            uncertainty = round(float(np.median(np.abs(residuals))))
            centred_ages = ages[mask] - float(np.mean(ages[mask]))
            slope_denominator = float(np.sum(centred_ages**2))
            if len(stint_slopes) >= 3:
                slope_centre = float(np.median(stint_slopes))
                slope_uncertainty = round(
                    float(
                        np.clip(
                            1.4826 * np.median(np.abs(stint_slopes - slope_centre)),
                            5,
                            80,
                        )
                    )
                )
            elif len(residuals) > 2 and slope_denominator > 0:
                residual_variance = float(np.sum(residuals**2)) / (len(residuals) - 2)
                slope_uncertainty = round(
                    float(np.clip(np.sqrt(residual_variance / slope_denominator), 5, 80))
                )
            else:
                slope_uncertainty = 45
            compound_median = round(float(np.median(times[mask])))
            observed_offset = float(np.clip(compound_median - self.event_median, -800, 800))
            observed_weight = min(len(samples) / 400, 0.5)
            blended_offset = round(
                COMPOUND_OFFSET_PRIOR[compound] * (1 - observed_weight)
                + observed_offset * observed_weight
            )
            estimate = TyreEstimate(
                compound=compound,
                initial_offset_ms=blended_offset,
                degradation_per_lap_ms=bounded_slope,
                sample_count=len(samples),
                source=(
                    "event_compound_stint_model"
                    if len(stint_slopes) >= 3
                    else "event_compound_pooled_fit"
                ),
                uncertainty_ms=max(uncertainty, 250),
                degradation_uncertainty_per_lap_ms=slope_uncertainty,
                performance_life_laps=life.performance_life_laps,
                durability_laps=life.durability_laps,
                stint_sample_count=life.stint_sample_count,
                life_source=life.source,
            )
            self._estimate_cache[compound] = estimate
            return estimate

        estimate = TyreEstimate(
            compound=compound,
            initial_offset_ms=0,
            degradation_per_lap_ms=DEFAULT_DEGRADATION.get(compound, 75),
            sample_count=len(samples),
            source="compound_fallback",
            uncertainty_ms=1_200,
            degradation_uncertainty_per_lap_ms=45,
            performance_life_laps=life.performance_life_laps,
            durability_laps=life.durability_laps,
            stint_sample_count=life.stint_sample_count,
            life_source=life.source,
        )
        self._estimate_cache[compound] = estimate
        return estimate

    def health_percent(self, compound: str, age: float) -> float:
        """Return cumulative health; field stints calibrate how quickly it is consumed."""
        if age <= 1:
            return 100.0
        performance_life = self.performance_life(compound)
        if age <= performance_life:
            progress = float(np.clip((age - 1) / max(performance_life - 1, 1), 0, 1))
            # Early-life loss is gentle and accelerates toward the field-derived service
            # age. This is the same operating-life boundary used by the pace cliff.
            # The field-derived competitive service age maps to 60% health: this
            # makes the typical observed stop region strategically expensive without
            # turning it into a mandatory pit threshold.
            consumed = 40 * (0.45 * progress + 0.55 * progress**2)
            return round(clamp_tyre_health(100 - consumed), 3)
        durability = self.durability_age(compound)
        if age <= durability:
            return round(clamp_tyre_health(60 - 55 * self.cliff_progress(compound, age)), 3)
        # Exactly at durability the tyre retains 5%; crossing beyond it consumes the
        # final reserve over one effective lap and therefore triggers the strict <5 rule.
        return round(clamp_tyre_health(5.0 - 5.0 * (age - durability)), 3)

    def wear_for_lap(
        self,
        compound: str,
        effective_age: float,
        wear_multiplier: float = 1.0,
    ) -> float:
        """Consume health cumulatively; changing conditions can never restore it."""
        start = self.health_percent(compound, effective_age)
        end = self.health_percent(compound, effective_age + max(wear_multiplier, 0.0))
        return max(0.0, start - end)

    def pace_loss_seconds(self, tyre_health_pct: float) -> float:
        return tyre_pace_loss_seconds(tyre_health_pct)

    def _field_medians(self) -> dict[int, float]:
        grouped: dict[int, list[int]] = {}
        for lap in self.clean:
            grouped.setdefault(lap.lap_number, []).append(int(lap.lap_time_ms or 0))
        return {lap: float(np.median(times)) for lap, times in grouped.items() if times}

    def _stint_observations(self) -> list[StintLifeObservation]:
        grouped: dict[tuple[int, int, str], list[Lap]] = {}
        last_lap_by_driver: dict[int, int] = {}
        for lap in self.laps:
            last_lap_by_driver[lap.driver_id] = max(
                last_lap_by_driver.get(lap.driver_id, 0), lap.lap_number
            )
            if lap.tyre_life is None or lap.compound not in DEFAULT_DEGRADATION or lap.deleted:
                continue
            grouped.setdefault((lap.driver_id, lap.stint_number or 0, lap.compound), []).append(lap)

        observations = []
        for (driver_id, stint_number, compound), stint_laps in grouped.items():
            if len(stint_laps) < MIN_STINT_LAPS:
                continue
            end_lap = max(item.lap_number for item in stint_laps)
            end_age = max(float(item.tyre_life or 0) for item in stint_laps)
            observations.append(
                StintLifeObservation(
                    driver_id=driver_id,
                    stint_number=stint_number,
                    compound=compound,
                    end_age=end_age,
                    lap_count=len(stint_laps),
                    changed_tyre=end_lap < last_lap_by_driver.get(driver_id, end_lap),
                )
            )
        return observations

    def _stint_slopes(self, compound: str) -> np.ndarray:
        grouped: dict[tuple[int, int], list[Lap]] = {}
        for lap in self.clean:
            if lap.compound == compound:
                grouped.setdefault((lap.driver_id, lap.stint_number or 0), []).append(lap)
        slopes = []
        for stint_laps in grouped.values():
            if len(stint_laps) < MIN_STINT_LAPS:
                continue
            ages = np.asarray([float(lap.tyre_life or 0) for lap in stint_laps])
            residuals = np.asarray(
                [
                    float(lap.lap_time_ms or 0)
                    - self.field_median_by_lap.get(lap.lap_number, self.event_median)
                    for lap in stint_laps
                ]
            )
            if len(np.unique(ages)) < MIN_STINT_LAPS:
                continue
            slope, _ = np.polyfit(ages, residuals, 1)
            slopes.append(float(np.clip(slope, -100, 400)))
        return np.asarray(slopes, dtype=float)
