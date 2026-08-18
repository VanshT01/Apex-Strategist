from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

import numpy as np

from app.db.models import Driver, Lap, RaceEntry
from app.schemas.race_state import PitLossEstimate
from app.schemas.strategy import UncertaintySourceRead
from app.simulation.tyres import DEFAULT_DEGRADATION, TyreDegradationEstimator

GLOBAL_LAP_RESIDUAL_SIGMA_MS = 900.0
LAP_RESIDUAL_BOUNDS_MS = (250.0, 2_500.0)
DRIVER_PACE_BOUNDS_MS = (100.0, 500.0)
WARMUP_SIGMA_MS = {"SOFT": 350.0, "MEDIUM": 300.0, "HARD": 250.0}


@dataclass(frozen=True)
class UncertaintyCalibration:
    lap_residual_sigma_ms: float
    driver_pace_sigma_ms: float
    pit_loss_samples_ms: np.ndarray
    tyre_slope_sigma_ms: dict[str, float]
    warmup_sigma_ms: dict[str, float]
    sources: list[UncertaintySourceRead]
    data_quality: str


class UncertaintyCalibrator:
    """Build bounded, inspectable uncertainty inputs before simulation begins."""

    def __init__(
        self,
        all_laps: list[Lap],
        entries: list[tuple[RaceEntry, Driver]],
        driver_id: int,
        control_lap: int,
        pit_loss: PitLossEstimate,
        pit_loss_samples: list[int],
        historical_laps: list[Lap] | None = None,
    ) -> None:
        self.all_laps = all_laps
        self.entries = entries
        self.driver_id = driver_id
        self.control_lap = control_lap
        self.pit_loss = pit_loss
        self.pit_loss_samples = pit_loss_samples
        self.historical_laps = historical_laps or []

    def calibrate(self) -> UncertaintyCalibration:
        lap_scale, lap_source, lap_count, lap_fallback = self._lap_residual_scale()
        driver_scale = float(np.clip(lap_scale * 0.22, *DRIVER_PACE_BOUNDS_MS))
        tyre_estimator = TyreDegradationEstimator(self.all_laps)
        tyre_sigmas: dict[str, float] = {}
        sources = [
            UncertaintySourceRead(
                variable="lap_time_residual",
                source=lap_source,
                sample_count=lap_count,
                scale_ms=round(lap_scale, 1),
                fallback=lap_fallback,
                assumption="Robust residual scale after tyre age detrending within each stint.",
            ),
            UncertaintySourceRead(
                variable="persistent_driver_pace",
                source=f"derived_from_{lap_source}",
                sample_count=lap_count,
                scale_ms=round(driver_scale, 1),
                fallback=lap_fallback,
                assumption="Small bounded offset per lap shared across the race remainder.",
            ),
        ]
        empirical_tyre_sources = 0
        for compound in DEFAULT_DEGRADATION:
            estimate = tyre_estimator.estimate(compound)
            sigma = float(np.clip(estimate.degradation_uncertainty_per_lap_ms, 5, 80))
            tyre_sigmas[compound] = sigma
            empirical = estimate.source.startswith("event_compound_")
            empirical_tyre_sources += int(empirical)
            sources.append(
                UncertaintySourceRead(
                    variable=f"tyre_degradation_{compound.lower()}",
                    source=estimate.source,
                    sample_count=estimate.sample_count,
                    scale_ms=sigma,
                    fallback=not empirical,
                    assumption=(
                        "Historical slope supports compound/circuit health calibration; Monte "
                        "Carlo samples the shared curve at 0.9 to 1.1× severity and "
                        "45 to 55% cliff wear."
                    ),
                )
            )

        pit_samples = np.asarray(self.pit_loss_samples, dtype=float)
        sources.append(
            UncertaintySourceRead(
                variable="pit_loss",
                source=self.pit_loss.source,
                sample_count=len(pit_samples),
                scale_ms=float(self.pit_loss.uncertainty_ms),
                fallback=len(pit_samples) < 3,
                assumption=(
                    "Bootstrap accepted pit lane intervals when available; otherwise use a "
                    "bounded normal fallback."
                ),
            )
        )
        sources.extend(
            [
                UncertaintySourceRead(
                    variable="tyre_warmup",
                    source="bounded_compound_assumption",
                    sample_count=0,
                    scale_ms=max(WARMUP_SIGMA_MS.values()),
                    fallback=True,
                    assumption=(
                        "Centred variation over the first two laps; larger for softer compounds."
                    ),
                ),
                UncertaintySourceRead(
                    variable="traffic_loss",
                    source="rejoin_window_heuristic",
                    sample_count=0,
                    scale_ms=2_000,
                    fallback=True,
                    assumption=(
                        "Occurrence probability comes from cars within the recorded rejoin window; "
                        "sampled loss is bounded and mean centred."
                    ),
                ),
                UncertaintySourceRead(
                    variable="safety_car_vsc",
                    source="disabled_phase5_core",
                    sample_count=0,
                    scale_ms=0,
                    fallback=True,
                    assumption=(
                        "No new intervention is sampled; historical interventions remain in "
                        "the anchor."
                    ),
                ),
            ]
        )
        fallback_count = sum(
            source.fallback for source in sources[: 2 + len(DEFAULT_DEGRADATION) + 1]
        )
        if not lap_fallback and len(pit_samples) >= 3 and empirical_tyre_sources >= 2:
            quality = "HIGH"
        elif fallback_count <= 3:
            quality = "MEDIUM"
        else:
            quality = "LOW"
        return UncertaintyCalibration(
            lap_residual_sigma_ms=lap_scale,
            driver_pace_sigma_ms=driver_scale,
            pit_loss_samples_ms=pit_samples,
            tyre_slope_sigma_ms=tyre_sigmas,
            warmup_sigma_ms=dict(WARMUP_SIGMA_MS),
            sources=sources,
            data_quality=quality,
        )

    def _lap_residual_scale(self) -> tuple[float, str, int, bool]:
        current = [lap for lap in self.all_laps if lap.lap_number <= self.control_lap]
        selected = [lap for lap in current if lap.driver_id == self.driver_id]
        scale = self._eligible_scale(selected, 8)
        if scale is not None:
            return scale, "driver_current_session", len(self._residuals(selected)), False

        entry_by_id = {entry.driver_id: (entry, driver) for entry, driver in self.entries}
        selected_pair = entry_by_id.get(self.driver_id)
        selected_team = (
            selected_pair[0].team_name or selected_pair[1].team_name if selected_pair else None
        )
        team_ids = {
            driver_id
            for driver_id, (entry, driver) in entry_by_id.items()
            if selected_team and (entry.team_name or driver.team_name) == selected_team
        }
        team = [lap for lap in current if lap.driver_id in team_ids]
        scale = self._eligible_scale(team, 12)
        if scale is not None:
            return scale, "team_current_session", len(self._residuals(team)), False

        scale = self._eligible_scale(current, 30)
        if scale is not None:
            return scale, "all_drivers_current_session", len(self._residuals(current)), False

        scale = self._eligible_scale(self.historical_laps, 30)
        if scale is not None:
            return scale, "circuit_history", len(self._residuals(self.historical_laps)), False

        return GLOBAL_LAP_RESIDUAL_SIGMA_MS, "global_fallback", 0, True

    def _eligible_scale(self, laps: list[Lap], minimum: int) -> float | None:
        residuals = self._residuals(laps)
        if len(residuals) < minimum:
            return None
        centre = float(np.median(residuals))
        mad_sigma = 1.4826 * float(np.median(np.abs(residuals - centre)))
        lower, upper = np.quantile(residuals, [0.1, 0.9])
        trimmed = residuals[(residuals >= lower) & (residuals <= upper)]
        trimmed_sigma = float(np.std(trimmed, ddof=1)) if len(trimmed) > 1 else 0.0
        robust = max(mad_sigma, trimmed_sigma, LAP_RESIDUAL_BOUNDS_MS[0])
        return float(np.clip(robust, *LAP_RESIDUAL_BOUNDS_MS))

    @staticmethod
    def _residuals(laps: list[Lap]) -> np.ndarray:
        clean = [
            lap
            for lap in laps
            if lap.lap_time_ms is not None
            and lap.tyre_life is not None
            and not lap.pit_in
            and not lap.pit_out
            and not lap.deleted
            and not lap.inaccurate
            and lap.track_status in {None, "1"}
        ]
        grouped: dict[tuple[int, int, str | None, int | None], list[Lap]] = defaultdict(list)
        for lap in clean:
            grouped[(lap.session_id, lap.driver_id, lap.compound, lap.stint_number)].append(lap)
        residuals: list[float] = []
        for values in grouped.values():
            times = np.asarray([lap.lap_time_ms for lap in values], dtype=float)
            if len(values) >= 4 and len({lap.tyre_life for lap in values}) >= 3:
                ages = np.asarray([lap.tyre_life for lap in values], dtype=float)
                slope, intercept = np.polyfit(ages, times, 1)
                predicted = intercept + float(np.clip(slope, -300, 500)) * ages
                residuals.extend((times - predicted).tolist())
            elif len(values) >= 2:
                residuals.extend((times - median(times)).tolist())
        return np.asarray(residuals, dtype=float)
