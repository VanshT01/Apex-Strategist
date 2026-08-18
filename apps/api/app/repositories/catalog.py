from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Driver, Event, Lap, RaceEntry, RaceSession, Season


class CatalogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def seasons(self) -> list[Season]:
        return list(self.db.scalars(select(Season).order_by(Season.year.desc())))

    def events(self, season_year: int | None) -> list[Event]:
        query = select(Event).join(Season)
        if season_year is not None:
            query = query.where(Season.year == season_year)
        return list(self.db.scalars(query.order_by(Season.year.desc(), Event.round_number)))

    def event(self, event_id: int) -> Event | None:
        return self.db.get(Event, event_id)

    def sessions(self, event_id: int) -> list[RaceSession]:
        query = select(RaceSession).where(RaceSession.event_id == event_id)
        return list(self.db.scalars(query.order_by(RaceSession.session_date)))

    def session(self, session_id: int) -> RaceSession | None:
        return self.db.get(RaceSession, session_id)

    def drivers(self, session_id: int) -> list[dict[str, object]]:
        query = (
            select(Driver, RaceEntry)
            .join(RaceEntry, RaceEntry.driver_id == Driver.id)
            .where(RaceEntry.session_id == session_id)
            .order_by(RaceEntry.finishing_position.asc().nullslast(), Driver.abbreviation)
        )
        return [
            {
                "id": driver.id,
                "driver_number": driver.driver_number,
                "abbreviation": entry.abbreviation or driver.abbreviation,
                "full_name": entry.full_name or driver.full_name,
                "team_name": entry.team_name or driver.team_name,
                "country_code": entry.country_code or driver.country_code,
                "grid_position": entry.grid_position,
                "finishing_position": entry.finishing_position,
                "status": entry.status,
                "points": entry.points,
            }
            for driver, entry in self.db.execute(query).all()
        ]

    def laps(
        self, session_id: int, driver_id: int | None, page: int, page_size: int
    ) -> tuple[list[Lap], int]:
        filters = [Lap.session_id == session_id]
        if driver_id is not None:
            filters.append(Lap.driver_id == driver_id)
        total = self.db.scalar(select(func.count()).select_from(Lap).where(*filters)) or 0
        query = (
            select(Lap)
            .where(*filters)
            .order_by(Lap.lap_number, Lap.driver_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(query)), total
