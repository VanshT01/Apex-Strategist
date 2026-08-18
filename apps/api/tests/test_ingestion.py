from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from app.core.config import Settings
from app.db.models import Lap, RaceControlMessage, RaceEntry, RaceSession, WeatherSample
from app.ingestion.service import RaceIngestionService
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class FakeClient:
    def __init__(self, session: object) -> None:
        self.session = session

    def load_race(self, year: int, event: str | int) -> object:
        assert year == 2024
        assert event == "Test Grand Prix"
        return self.session


def fake_session() -> SimpleNamespace:
    event = pd.Series(
        {
            "RoundNumber": 10,
            "EventName": "Test Grand Prix",
            "Country": "Testland",
            "Location": "Test City",
            "EventDate": pd.Timestamp("2024-07-07"),
            "OfficialEventName": "Test Formula 1 Grand Prix",
            "EventFormat": "conventional",
        }
    )
    results = pd.DataFrame(
        [
            {
                "DriverNumber": "4",
                "Abbreviation": "TST",
                "FullName": "Test Driver",
                "TeamName": "Test Racing",
                "CountryCode": "TST",
                "GridPosition": 2.0,
                "Position": 1.0,
                "Status": "Finished",
                "Points": 25.0,
            }
        ]
    )
    laps = pd.DataFrame(
        [
            {
                "DriverNumber": "4",
                "LapNumber": 1.0,
                "Position": 2.0,
                "LapTime": pd.Timedelta(seconds=90),
                "Sector1Time": pd.Timedelta(seconds=30),
                "Sector2Time": pd.Timedelta(seconds=29),
                "Sector3Time": pd.Timedelta(seconds=31),
                "Compound": "MEDIUM",
                "TyreLife": 1.0,
                "Stint": 1.0,
                "FreshTyre": True,
                "PitInTime": pd.NaT,
                "PitOutTime": pd.NaT,
                "TrackStatus": "1",
                "Deleted": False,
                "IsAccurate": True,
                "Time": pd.Timedelta(seconds=90),
                "SpeedI1": 280.0,
                "SpeedI2": 290.0,
                "SpeedFL": 300.0,
                "SpeedST": 320.0,
                "IsPersonalBest": True,
                "LapStartDate": pd.Timestamp("2024-07-07 13:00:00"),
                "LapStartTime": pd.Timedelta(seconds=0),
            },
            {
                "DriverNumber": "4",
                "LapNumber": 2.0,
                "Position": 1.0,
                "LapTime": pd.NaT,
                "Compound": "MEDIUM",
                "TyreLife": 2.0,
                "Stint": 1.0,
                "PitInTime": pd.Timedelta(seconds=175),
                "PitOutTime": pd.NaT,
                "TrackStatus": "1",
                "Deleted": False,
                "IsAccurate": False,
                "Time": pd.Timedelta(seconds=180),
            },
            {
                "DriverNumber": "4",
                "LapNumber": 3.0,
                "Position": 1.0,
                "LapTime": pd.Timedelta(seconds=110),
                "Compound": "HARD",
                "TyreLife": 1.0,
                "Stint": 2.0,
                "PitInTime": pd.NaT,
                "PitOutTime": pd.Timedelta(seconds=200),
                "TrackStatus": "1",
                "Deleted": False,
                "IsAccurate": True,
                "Time": pd.Timedelta(seconds=290),
            },
        ]
    )
    weather = pd.DataFrame(
        [
            {
                "Time": pd.Timedelta(seconds=60),
                "AirTemp": 20.5,
                "TrackTemp": 31.0,
                "Humidity": 55.0,
                "Pressure": 1000.0,
                "Rainfall": False,
                "WindDirection": 180,
                "WindSpeed": 2.4,
            }
        ]
    )
    messages = pd.DataFrame(
        [
            {
                "Time": pd.Timestamp("2024-07-07 13:01:10"),
                "Lap": 1,
                "Category": "Flag",
                "Flag": "GREEN",
                "Scope": "Track",
                "Message": "GREEN LIGHT",
            }
        ]
    )
    return SimpleNamespace(
        event=event,
        date=datetime(2024, 7, 7, 14),
        total_laps=3,
        results=results,
        laps=laps,
        weather_data=weather,
        race_control_messages=messages,
    )


def test_ingestion_normalizes_provider_frames_and_is_idempotent(
    db: Session, tmp_path: Path
) -> None:
    settings = Settings(database_url="sqlite://", fastf1_cache_dir=tmp_path)
    service = RaceIngestionService(db, settings, FakeClient(fake_session()))  # type: ignore[arg-type]
    result = service.ingest(2024, "Test Grand Prix")
    repeated = service.ingest(2024, 10)

    assert result.status == "complete"
    assert repeated.session_id == result.session_id
    assert db.scalar(select(func.count()).select_from(RaceEntry)) == 1
    entry = db.scalar(select(RaceEntry))
    assert entry is not None and entry.team_name == "Test Racing"
    assert entry.abbreviation == "TST"
    assert entry.full_name == "Test Driver"
    assert db.scalar(select(func.count()).select_from(Lap)) == 3
    assert db.scalar(select(func.count()).select_from(WeatherSample)) == 1
    assert db.scalar(select(func.count()).select_from(RaceControlMessage)) == 1
    message = db.scalar(select(RaceControlMessage))
    assert message is not None and message.timestamp_ms == 70_000
    second_lap = db.scalar(select(Lap).where(Lap.lap_number == 2))
    assert second_lap is not None
    assert second_lap.lap_time_ms is None
    assert second_lap.pit_in is True
    assert second_lap.inaccurate is True
    session = db.get(RaceSession, result.session_id)
    assert session and session.ingestion_status == "complete"
