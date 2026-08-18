from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.catalog import DriverRead, EventRead, LapPage, SeasonRead, SessionRead
from app.services.catalog import CatalogService

router = APIRouter(tags=["race catalog"])
Db = Annotated[Session, Depends(get_db)]


@router.get("/seasons", response_model=list[SeasonRead], summary="List ingested seasons")
def seasons(db: Db) -> list[SeasonRead]:
    return CatalogService(db).list_seasons()


@router.get("/events", response_model=list[EventRead], summary="List ingested events")
def events(db: Db, season: int | None = Query(None, ge=2018, le=2100)) -> list[EventRead]:
    return CatalogService(db).list_events(season)


@router.get("/events/{event_id}", response_model=EventRead, summary="Get event details")
def event(event_id: int, db: Db) -> EventRead:
    return CatalogService(db).get_event(event_id)


@router.get(
    "/events/{event_id}/sessions", response_model=list[SessionRead], summary="List event sessions"
)
def sessions(event_id: int, db: Db) -> list[SessionRead]:
    return CatalogService(db).list_sessions(event_id)


@router.get(
    "/sessions/{session_id}/drivers", response_model=list[DriverRead], summary="List race drivers"
)
def drivers(session_id: int, db: Db) -> list[DriverRead]:
    return CatalogService(db).list_drivers(session_id)


@router.get("/sessions/{session_id}/laps", response_model=LapPage, summary="List normalized laps")
def laps(
    session_id: int,
    db: Db,
    driver_id: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
) -> LapPage:
    return CatalogService(db).list_laps(session_id, driver_id, page, page_size)
