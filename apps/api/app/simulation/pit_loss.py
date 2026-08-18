from statistics import median

from app.repositories.race import RaceRepository
from app.schemas.race_state import PitLossEstimate

GLOBAL_PIT_LOSS_MS = 23_000


class PitLossEstimator:
    def __init__(self, repo: RaceRepository) -> None:
        self.repo = repo

    def estimate(self, session_id: int) -> PitLossEstimate:
        values, source = self.distribution(session_id)
        if values:
            return self._result(values, source)
        return PitLossEstimate(
            estimated_ms=GLOBAL_PIT_LOSS_MS,
            sample_count=0,
            source="global_fallback",
            uncertainty_ms=4_000,
        )

    def distribution(self, session_id: int) -> tuple[list[int], str]:
        """Return the accepted empirical sample used by the point estimator."""
        session = self.repo.session(session_id)
        if session is None:
            raise ValueError("Session not found")
        current = self._valid_durations(self.repo.pit_stops(session_id))
        if len(current) >= 3:
            return current, "current_session"

        event = self.repo.event(session.event_id)
        if event and event.location:
            historical = self._valid_durations(
                self.repo.historical_pit_stops_for_location(event.location)
            )
            if len(historical) >= 3:
                return historical, "same_location_history"
        return [], "global_fallback"

    @staticmethod
    def _valid_durations(stops: list[object]) -> list[int]:
        durations = [
            int(duration)
            for stop in stops
            if (duration := getattr(stop, "pit_duration_ms", None)) is not None
            and 10_000 <= duration <= 60_000
        ]
        if len(durations) < 4:
            return durations
        centre = median(durations)
        deviations = [abs(value - centre) for value in durations]
        mad = median(deviations) or 1_000
        return [value for value in durations if abs(value - centre) <= 4 * mad]

    @staticmethod
    def _result(values: list[int], source: str) -> PitLossEstimate:
        centre = round(median(values))
        uncertainty = round(median(abs(value - centre) for value in values))
        return PitLossEstimate(
            estimated_ms=centre,
            sample_count=len(values),
            source=source,
            uncertainty_ms=max(uncertainty, 500),
        )
