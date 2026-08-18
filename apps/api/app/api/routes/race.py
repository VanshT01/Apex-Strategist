from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.race_state import ActualStrategyResponse, RaceStateResponse, TimelineResponse
from app.services.race_state import RaceStateService

router = APIRouter(tags=["race state"])
Db = Annotated[Session, Depends(get_db)]


@router.get(
    "/sessions/{session_id}/race-state",
    response_model=RaceStateResponse,
    summary="Reconstruct race state at the end of a lap",
)
def race_state(
    session_id: int,
    db: Db,
    lap: int = Query(..., ge=1),
    driver_id: int = Query(..., ge=1),
) -> RaceStateResponse:
    return RaceStateService(db).reconstruct(session_id, lap, driver_id)


@router.get(
    "/sessions/{session_id}/timeline",
    response_model=TimelineResponse,
    summary="Get a driver's tyre-stint timeline",
)
def timeline(session_id: int, db: Db, driver_id: int = Query(..., ge=1)) -> TimelineResponse:
    return RaceStateService(db).timeline(session_id, driver_id)


@router.get(
    "/sessions/{session_id}/actual-strategy/{driver_id}",
    response_model=ActualStrategyResponse,
    summary="Get the recorded strategy after a control lap",
)
def actual_strategy(
    session_id: int,
    driver_id: int,
    db: Db,
    control_lap: int = Query(..., ge=1),
) -> ActualStrategyResponse:
    return RaceStateService(db).actual_strategy(session_id, driver_id, control_lap)
