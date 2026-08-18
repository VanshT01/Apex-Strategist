from datetime import date

from app.core.config import get_settings
from app.db.models import Driver, Event, Lap, RaceEntry, RaceSession, Season
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def seed_catalog(db: Session) -> None:
    season = Season(year=2024)
    db.add(season)
    db.flush()
    event = Event(
        season_id=season.id,
        round_number=12,
        event_name="British Grand Prix",
        event_date=date(2024, 7, 7),
        metadata_json={},
    )
    db.add(event)
    db.flush()
    session = RaceSession(event_id=event.id, session_type="RACE", ingestion_status="complete")
    driver = Driver(
        driver_number="4",
        abbreviation="NOR",
        full_name="Lando Norris",
        team_name="Future Team",
    )
    db.add_all([session, driver])
    db.flush()
    db.add(
        RaceEntry(
            session_id=session.id,
            driver_id=driver.id,
            abbreviation="NOR",
            full_name="Historical Lando Norris",
            country_code="GBR",
            team_name="McLaren",
            grid_position=3,
            finishing_position=3,
            status="Finished",
            points=15,
        )
    )
    db.add(
        Lap(
            session_id=session.id,
            driver_id=driver.id,
            lap_number=1,
            position=3,
            compound="MEDIUM",
            tyre_life=1,
            stint_number=1,
        )
    )
    db.commit()


def test_health_and_catalog_happy_path(client: TestClient, db: Session) -> None:
    seed_catalog(db)
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assert client.get("/api/v1/seasons").json() == [{"id": 1, "year": 2024}]
    events = client.get("/api/v1/events?season=2024").json()
    sessions = client.get(f"/api/v1/events/{events[0]['id']}/sessions").json()
    drivers = client.get(f"/api/v1/sessions/{sessions[0]['id']}/drivers").json()
    assert drivers[0]["team_name"] == "McLaren"
    assert drivers[0]["abbreviation"] == "NOR"
    assert drivers[0]["full_name"] == "Historical Lando Norris"
    assert drivers[0]["country_code"] == "GBR"
    laps = client.get(
        f"/api/v1/sessions/{sessions[0]['id']}/laps?driver_id={drivers[0]['id']}"
    ).json()
    assert laps["total"] == 1
    assert laps["items"][0]["compound"] == "MEDIUM"


def test_lap_pagination_validation(client: TestClient) -> None:
    response = client.get("/api/v1/sessions/1/laps?page_size=500")
    assert response.status_code == 422


def test_http_ingestion_is_disabled_in_production(client: TestClient, monkeypatch: object) -> None:
    monkeypatch.setenv("APP_ENV", "production")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/admin/ingest",
            json={"year": 2024, "event": "British Grand Prix"},
        )
        assert response.status_code == 403
        assert "disabled in production" in response.json()["detail"]
    finally:
        get_settings.cache_clear()
