from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.catalog import CatalogRepository
from app.schemas.catalog import DriverRead, EventRead, LapPage, SeasonRead, SessionRead


class CatalogService:
    def __init__(self, db: Session) -> None:
        self.repo = CatalogRepository(db)

    def list_seasons(self) -> list[SeasonRead]:
        return [SeasonRead.model_validate(item) for item in self.repo.seasons()]

    def list_events(self, season: int | None) -> list[EventRead]:
        return [EventRead.model_validate(item) for item in self.repo.events(season)]

    def get_event(self, event_id: int) -> EventRead:
        event = self.repo.event(event_id)
        if event is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
        return EventRead.model_validate(event)

    def list_sessions(self, event_id: int) -> list[SessionRead]:
        if self.repo.event(event_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
        return [SessionRead.model_validate(item) for item in self.repo.sessions(event_id)]

    def list_drivers(self, session_id: int) -> list[DriverRead]:
        self._require_session(session_id)
        return [DriverRead.model_validate(item) for item in self.repo.drivers(session_id)]

    def list_laps(
        self, session_id: int, driver_id: int | None, page: int, page_size: int
    ) -> LapPage:
        self._require_session(session_id)
        items, total = self.repo.laps(session_id, driver_id, page, page_size)
        return LapPage(items=items, total=total, page=page, page_size=page_size)

    def _require_session(self, session_id: int) -> None:
        if self.repo.session(session_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
