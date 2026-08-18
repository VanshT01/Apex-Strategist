from pathlib import Path

import pandas as pd
from app.ingestion.fastf1_client import FastF1Client, ScheduledRace
from pytest import MonkeyPatch


def test_list_races_excludes_testing_and_sorts_rounds(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, object] = {}

    def fake_schedule(year: int, *, include_testing: bool) -> pd.DataFrame:
        calls.update(year=year, include_testing=include_testing)
        return pd.DataFrame(
            [
                {"RoundNumber": 2, "EventName": "Second Grand Prix"},
                {"RoundNumber": 0, "EventName": "Pre-Season Test"},
                {"RoundNumber": 1, "EventName": "First Grand Prix"},
            ]
        )

    monkeypatch.setattr("fastf1.Cache.enable_cache", lambda _: None)
    monkeypatch.setattr("fastf1.get_event_schedule", fake_schedule)

    assert FastF1Client(tmp_path).list_races(2024) == [
        ScheduledRace(round_number=1, event_name="First Grand Prix"),
        ScheduledRace(round_number=2, event_name="Second Grand Prix"),
    ]
    assert calls == {"year": 2024, "include_testing": False}
