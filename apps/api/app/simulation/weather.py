from dataclasses import dataclass
from enum import StrEnum

from app.db.models import Lap, WeatherSample

DRY_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}
WET_COMPOUNDS = {"INTERMEDIATE", "WET"}


class TrackCondition(StrEnum):
    DRY = "DRY"
    DAMP = "DAMP"
    WET = "WET"


@dataclass(frozen=True)
class TyreWeatherEffect:
    pace_penalty_ms: int
    wear_multiplier: float
    risk: float
    unsafe: bool = False


class TyreWeatherModel:
    """Small, explicit tyre/track compatibility model for public timing data."""

    def __init__(self, laps: list[Lap], weather: list[WeatherSample]) -> None:
        self.laps = laps
        self.weather = sorted(weather, key=lambda sample: sample.timestamp_ms)

    def condition(self, lap_number: int) -> TrackCondition:
        lap_rows = [lap for lap in self.laps if lap.lap_number == lap_number]
        timestamps = sorted(lap.timestamp_ms for lap in lap_rows if lap.timestamp_ms is not None)
        timestamp = timestamps[len(timestamps) // 2] if timestamps else 0
        observation = next(
            (sample for sample in reversed(self.weather) if sample.timestamp_ms <= timestamp),
            None,
        )
        compounds = [lap.compound for lap in lap_rows if lap.compound]
        wet_count = sum(compound in WET_COMPOUNDS for compound in compounds)
        full_wet_count = sum(compound == "WET" for compound in compounds)
        wet_share = wet_count / max(len(compounds), 1)

        if observation and observation.rainfall:
            if full_wet_count >= 2 and full_wet_count >= wet_count / 2:
                return TrackCondition.WET
            return TrackCondition.DAMP
        if wet_share >= 0.25:
            return TrackCondition.DAMP
        return TrackCondition.DRY

    @staticmethod
    def effect(compound: str, condition: TrackCondition) -> TyreWeatherEffect:
        if condition == TrackCondition.DRY:
            if compound == "INTERMEDIATE":
                return TyreWeatherEffect(4_500, 1.7, 0.7)
            if compound == "WET":
                return TyreWeatherEffect(8_000, 2.1, 0.9)
            return TyreWeatherEffect(0, 1.0, 0.0)
        if condition == TrackCondition.DAMP:
            if compound in DRY_COMPOUNDS:
                return TyreWeatherEffect(3_500, 1.25, 0.55)
            if compound == "WET":
                return TyreWeatherEffect(2_500, 1.2, 0.35)
            return TyreWeatherEffect(0, 1.0, 0.05)
        if compound in DRY_COMPOUNDS:
            return TyreWeatherEffect(12_000, 1.6, 0.95, unsafe=True)
        if compound == "INTERMEDIATE":
            return TyreWeatherEffect(1_500, 1.1, 0.2)
        return TyreWeatherEffect(0, 1.0, 0.05)
