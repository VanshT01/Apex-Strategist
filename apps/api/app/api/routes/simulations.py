from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.strategy import StrategyCompareRequest, StrategyComparisonResponse
from app.services.strategy import StrategyService

router = APIRouter(prefix="/simulations", tags=["strategy comparisons"])
Db = Annotated[Session, Depends(get_db)]


@router.post(
    "/compare",
    response_model=StrategyComparisonResponse,
    summary="Compare race strategies with seeded Monte Carlo simulation",
)
def compare(payload: StrategyCompareRequest, db: Db) -> StrategyComparisonResponse:
    return StrategyService(db).compare(payload)


@router.get(
    "/{comparison_id}",
    response_model=StrategyComparisonResponse,
    summary="Get a saved deterministic or Monte Carlo comparison",
)
def get_comparison(comparison_id: int, db: Db) -> StrategyComparisonResponse:
    return StrategyService(db).get(comparison_id)
