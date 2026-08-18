from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fastf1


@dataclass(frozen=True)
class ScheduledRace:
    round_number: int
    event_name: str


class FastF1Client:
    """Small provider adapter so ingestion is testable without network access."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def load_race(self, year: int, event: str | int) -> Any:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(self.cache_dir))
        session = fastf1.get_session(year, event, "R")
        session.load(telemetry=False, weather=True, messages=True)
        return session

    def load_race_results(self, year: int, event: str | int) -> Any:
        """Load only session metadata/results for a lightweight historical backfill."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(self.cache_dir))
        session = fastf1.get_session(year, event, "R")
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        return session

    def list_races(self, year: int) -> list[ScheduledRace]:
        """Return every championship round, excluding pre-season tests."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(self.cache_dir))
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        races = [
            ScheduledRace(round_number=int(row["RoundNumber"]), event_name=str(row["EventName"]))
            for _, row in schedule.iterrows()
            if int(row["RoundNumber"]) > 0
        ]
        return sorted(races, key=lambda race: race.round_number)
