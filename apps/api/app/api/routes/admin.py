from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.ingestion.service import IngestionError, RaceIngestionService
from app.schemas.ingestion import IngestionRequest, IngestionResponse

router = APIRouter(prefix="/admin", tags=["administration"])
Db = Annotated[Session, Depends(get_db)]


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a historical race",
)
def ingest(payload: IngestionRequest, db: Db) -> IngestionResponse:
    if get_settings().app_env.casefold() in {"production", "prod"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "HTTP ingestion is disabled in production; use the ingestion CLI before deployment",
        )
    try:
        return RaceIngestionService(db).ingest(payload.year, payload.event, payload.force)
    except IngestionError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
