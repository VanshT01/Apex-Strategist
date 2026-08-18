from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import fastf1
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import (
    Driver,
    Event,
    Lap,
    PitStop,
    RaceControlMessage,
    RaceEntry,
    RaceSession,
    Season,
    WeatherSample,
)
from app.ingestion.fastf1_client import FastF1Client
from app.schemas.ingestion import IngestionResponse
from app.utils.serialization import (
    field,
    json_safe,
    optional_bool,
    optional_date,
    optional_datetime,
    optional_float,
    optional_int,
    optional_str,
    timedelta_ms,
)

logger = logging.getLogger(__name__)


class IngestionError(RuntimeError):
    pass


class RaceIngestionService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        client: FastF1Client | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.client = client or FastF1Client(self.settings.fastf1_cache_dir)

    def ingest(
        self, year: int, event_selector: str | int, force: bool = False
    ) -> IngestionResponse:
        if isinstance(event_selector, int) and not force:
            completed = self.db.scalar(
                select(RaceSession)
                .join(Event, RaceSession.event_id == Event.id)
                .join(Season, Event.season_id == Season.id)
                .where(
                    Season.year == year,
                    Event.round_number == event_selector,
                    RaceSession.session_type == "RACE",
                    RaceSession.ingestion_status == "complete",
                )
            )
            if completed is not None:
                return IngestionResponse(
                    session_id=completed.id,
                    status="complete",
                    message="Race is already ingested; use --force to refresh it.",
                )

        logger.info("Loading FastF1 race year=%s event=%s", year, event_selector)
        try:
            source = self.client.load_race(year, event_selector)
        except Exception as exc:
            logger.exception("FastF1 could not load the requested race")
            raise IngestionError(f"FastF1 could not load {year} {event_selector}: {exc}") from exc

        season, event = self._upsert_event(year, source)
        del season
        race_session = self.db.scalar(
            select(RaceSession).where(
                RaceSession.event_id == event.id, RaceSession.session_type == "RACE"
            )
        )
        if race_session and race_session.ingestion_status == "complete" and not force:
            return IngestionResponse(
                session_id=race_session.id,
                status="complete",
                message="Race is already ingested; use --force to refresh it.",
            )
        if race_session is None:
            race_session = RaceSession(event_id=event.id, session_type="RACE")
            self.db.add(race_session)

        race_session.session_date = optional_datetime(getattr(source, "date", None))
        race_session.source = "fastf1"
        race_session.data_version = f"fastf1-{fastf1.__version__}"
        race_session.ingestion_status = "loading"
        race_session.ingestion_error = None
        self.db.commit()
        self.db.refresh(race_session)

        try:
            self._clear_session(race_session.id)
            drivers = self._ingest_drivers_and_results(race_session.id, source)
            laps = self._ingest_laps(race_session.id, source, drivers)
            self._ingest_weather(race_session.id, source)
            self._ingest_messages(race_session.id, source)
            self._ingest_pit_stops(race_session.id, source, drivers)
            event.total_laps = optional_int(getattr(source, "total_laps", None)) or max(
                (lap.lap_number for lap in laps), default=None
            )
            race_session.ingestion_status = "complete"
            race_session.ingestion_error = None
            race_session.ingested_at = datetime.now(UTC)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            persisted = self.db.get(RaceSession, race_session.id)
            if persisted is not None:
                persisted.ingestion_status = "failed"
                persisted.ingestion_error = str(exc)[:4000]
                self.db.commit()
            logger.exception("Normalization failed for session_id=%s", race_session.id)
            raise IngestionError(f"Race loaded but normalization failed: {exc}") from exc

        logger.info("Ingested session_id=%s laps=%s", race_session.id, len(laps))
        return IngestionResponse(
            session_id=race_session.id,
            status="complete",
            message=f"Ingested {len(drivers)} drivers and {len(laps)} laps.",
        )

    def _upsert_event(self, year: int, source: Any) -> tuple[Season, Event]:
        season = self.db.scalar(select(Season).where(Season.year == year))
        if season is None:
            season = Season(year=year)
            self.db.add(season)
            self.db.flush()

        event_data = source.event
        round_number = optional_int(field(event_data, "RoundNumber")) or 0
        event = self.db.scalar(
            select(Event).where(Event.season_id == season.id, Event.round_number == round_number)
        )
        if event is None:
            event = Event(
                season_id=season.id, round_number=round_number, event_name="Unknown event"
            )
            self.db.add(event)
        event.event_name = optional_str(field(event_data, "EventName")) or str(source.event)
        event.country = optional_str(field(event_data, "Country"))
        event.location = optional_str(field(event_data, "Location"))
        # FastF1's documented Event schedule has location but no canonical circuit-name column.
        # Keep this nullable until a verified source is added rather than relabeling location.
        event.circuit_name = None
        event.event_date = optional_date(field(event_data, "EventDate"))
        event.metadata_json = json_safe(
            {
                "official_event_name": field(event_data, "OfficialEventName"),
                "event_format": field(event_data, "EventFormat"),
            }
        )
        self.db.flush()
        return season, event

    def _clear_session(self, session_id: int) -> None:
        for model in (PitStop, RaceControlMessage, WeatherSample, Lap, RaceEntry):
            self.db.execute(delete(model).where(model.session_id == session_id))
        self.db.flush()

    def _ingest_drivers_and_results(self, session_id: int, source: Any) -> dict[str, Driver]:
        drivers: dict[str, Driver] = {}
        results = getattr(source, "results", pd.DataFrame())
        for _, row in results.iterrows():
            number = optional_str(field(row, "DriverNumber"))
            if not number:
                logger.warning("Skipping result without DriverNumber")
                continue
            driver = self.db.scalar(select(Driver).where(Driver.driver_number == number))
            if driver is None:
                driver = Driver(
                    driver_number=number, abbreviation="UNK", full_name=f"Driver {number}"
                )
                self.db.add(driver)
            abbreviation = optional_str(field(row, "Abbreviation"))
            full_name = optional_str(field(row, "FullName"))
            country_code = optional_str(field(row, "CountryCode"))
            driver.abbreviation = abbreviation or driver.abbreviation
            driver.full_name = full_name or driver.full_name
            team_name = optional_str(field(row, "TeamName"))
            driver.team_name = team_name
            driver.country_code = country_code
            self.db.flush()
            self.db.add(
                RaceEntry(
                    session_id=session_id,
                    driver_id=driver.id,
                    abbreviation=abbreviation,
                    full_name=full_name,
                    country_code=country_code,
                    team_name=team_name,
                    grid_position=optional_int(field(row, "GridPosition")),
                    finishing_position=optional_int(field(row, "Position")),
                    status=optional_str(field(row, "Status")),
                    points=optional_float(field(row, "Points")),
                )
            )
            drivers[number] = driver
        self.db.flush()
        return drivers

    def backfill_entry_teams(self, session_id: int, source: Any) -> int:
        """Update immutable per-race identity without replacing normalized lap data."""
        entries = {
            driver.driver_number: entry
            for entry, driver in self.db.execute(
                select(RaceEntry, Driver)
                .join(Driver, Driver.id == RaceEntry.driver_id)
                .where(RaceEntry.session_id == session_id)
            ).all()
        }
        updated = 0
        for _, row in getattr(source, "results", pd.DataFrame()).iterrows():
            number = optional_str(field(row, "DriverNumber"))
            team_name = optional_str(field(row, "TeamName"))
            entry = entries.get(number or "")
            if entry is None:
                continue
            entry.abbreviation = optional_str(field(row, "Abbreviation")) or entry.abbreviation
            entry.full_name = optional_str(field(row, "FullName")) or entry.full_name
            entry.country_code = optional_str(field(row, "CountryCode")) or entry.country_code
            entry.team_name = team_name or entry.team_name
            updated += 1
        self.db.flush()
        return updated

    def _ingest_laps(self, session_id: int, source: Any, drivers: dict[str, Driver]) -> list[Lap]:
        normalized: list[Lap] = []
        laps = getattr(source, "laps", pd.DataFrame())
        for _, row in laps.iterrows():
            number = optional_str(field(row, "DriverNumber"))
            lap_number = optional_int(field(row, "LapNumber"))
            driver = drivers.get(number or "")
            if driver is None or lap_number is None:
                continue
            lap = Lap(
                session_id=session_id,
                driver_id=driver.id,
                lap_number=lap_number,
                position=optional_int(field(row, "Position")),
                lap_time_ms=timedelta_ms(field(row, "LapTime")),
                sector_1_ms=timedelta_ms(field(row, "Sector1Time")),
                sector_2_ms=timedelta_ms(field(row, "Sector2Time")),
                sector_3_ms=timedelta_ms(field(row, "Sector3Time")),
                compound=optional_str(field(row, "Compound")),
                tyre_life=optional_float(field(row, "TyreLife")),
                stint_number=optional_int(field(row, "Stint")),
                fresh_tyre=optional_bool(field(row, "FreshTyre")),
                pit_in=field(row, "PitInTime") is not None,
                pit_out=field(row, "PitOutTime") is not None,
                track_status=optional_str(field(row, "TrackStatus")),
                deleted=optional_bool(field(row, "Deleted")) or False,
                inaccurate=not (optional_bool(field(row, "IsAccurate")) is not False),
                timestamp_ms=timedelta_ms(field(row, "Time")),
                speed_i1=optional_float(field(row, "SpeedI1")),
                speed_i2=optional_float(field(row, "SpeedI2")),
                speed_fl=optional_float(field(row, "SpeedFL")),
                speed_st=optional_float(field(row, "SpeedST")),
                personal_best=optional_bool(field(row, "IsPersonalBest")),
            )
            normalized.append(lap)
        self.db.add_all(normalized)
        self.db.flush()
        return normalized

    def _ingest_weather(self, session_id: int, source: Any) -> None:
        weather = getattr(source, "weather_data", pd.DataFrame())
        samples = []
        for _, row in weather.iterrows():
            timestamp = timedelta_ms(field(row, "Time"))
            if timestamp is None:
                continue
            samples.append(
                WeatherSample(
                    session_id=session_id,
                    timestamp_ms=timestamp,
                    air_temperature=optional_float(field(row, "AirTemp")),
                    track_temperature=optional_float(field(row, "TrackTemp")),
                    humidity=optional_float(field(row, "Humidity")),
                    pressure=optional_float(field(row, "Pressure")),
                    rainfall=optional_bool(field(row, "Rainfall")),
                    wind_direction=optional_float(field(row, "WindDirection")),
                    wind_speed=optional_float(field(row, "WindSpeed")),
                )
            )
        self.db.add_all(samples)

    def _ingest_messages(self, session_id: int, source: Any) -> None:
        messages = getattr(source, "race_control_messages", pd.DataFrame())
        origin = self._session_time_origin(source)
        normalized = []
        for _, row in messages.iterrows():
            message = optional_str(field(row, "Message"))
            if not message:
                continue
            raw_time = field(row, "Time")
            if isinstance(raw_time, (pd.Timestamp, datetime)):
                timestamp = (
                    timedelta_ms(pd.Timestamp(raw_time) - origin) if origin is not None else None
                )
            else:
                timestamp = timedelta_ms(raw_time)
            normalized.append(
                RaceControlMessage(
                    session_id=session_id,
                    timestamp_ms=timestamp,
                    lap_number=optional_int(field(row, "Lap")),
                    category=optional_str(field(row, "Category")),
                    flag=optional_str(field(row, "Flag")),
                    scope=optional_str(field(row, "Scope")),
                    message=message,
                )
            )
        self.db.add_all(normalized)

    @staticmethod
    def _session_time_origin(source: Any) -> pd.Timestamp | None:
        """Infer session-time zero from FastF1's documented lap date/time pair."""
        laps = getattr(source, "laps", pd.DataFrame())
        if laps.empty or "LapStartDate" not in laps.columns or "LapStartTime" not in laps.columns:
            return None
        for _, row in laps.iterrows():
            lap_date = field(row, "LapStartDate")
            lap_time = field(row, "LapStartTime")
            if lap_date is not None and lap_time is not None:
                return pd.Timestamp(lap_date) - pd.Timedelta(lap_time)
        return None

    def _ingest_pit_stops(self, session_id: int, source: Any, drivers: dict[str, Driver]) -> None:
        laps = getattr(source, "laps", pd.DataFrame())
        stops: list[PitStop] = []
        if laps.empty or "DriverNumber" not in laps.columns:
            return
        for number, driver_laps in laps.groupby("DriverNumber"):
            driver = drivers.get(str(number))
            if driver is None:
                continue
            ordered = driver_laps.sort_values("LapNumber")
            rows = list(ordered.iterrows())
            for index, (_, row) in enumerate(rows):
                entry = timedelta_ms(field(row, "PitInTime"))
                lap_number = optional_int(field(row, "LapNumber"))
                if entry is None or lap_number is None:
                    continue
                exit_time = None
                for _, candidate in rows[index + 1 : index + 3]:
                    exit_time = timedelta_ms(field(candidate, "PitOutTime"))
                    if exit_time is not None:
                        break
                duration = (
                    exit_time - entry if exit_time is not None and exit_time >= entry else None
                )
                stops.append(
                    PitStop(
                        session_id=session_id,
                        driver_id=driver.id,
                        lap_number=lap_number,
                        pit_entry_time_ms=entry,
                        pit_exit_time_ms=exit_time,
                        pit_duration_ms=duration,
                        estimated_stationary_ms=None,
                    )
                )
        self.db.add_all(stops)
