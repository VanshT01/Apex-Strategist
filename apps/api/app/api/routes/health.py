from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.catalog import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service readiness")
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    database = "connected"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database = "unavailable"
    return HealthResponse(
        status="ok" if database == "connected" else "degraded", database=database, version="0.1.0"
    )
