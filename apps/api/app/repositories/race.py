from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Driver,
    Event,
    Lap,
    PitStop,
    RaceControlMessage,
    RaceEntry,
    RaceSession,
    StrategySimulation,
    WeatherSample,
)


class RaceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def session(self, session_id: int) -> RaceSession | None:
        return self.db.get(RaceSession, session_id)

    def event(self, event_id: int) -> Event | None:
        return self.db.get(Event, event_id)

    def driver(self, driver_id: int) -> Driver | None:
        return self.db.get(Driver, driver_id)

    def entry(self, session_id: int, driver_id: int) -> RaceEntry | None:
        return self.db.scalar(
            select(RaceEntry).where(
                RaceEntry.session_id == session_id, RaceEntry.driver_id == driver_id
            )
        )

    def entries(self, session_id: int) -> list[tuple[RaceEntry, Driver]]:
        query = (
            select(RaceEntry, Driver)
            .join(Driver, Driver.id == RaceEntry.driver_id)
            .where(RaceEntry.session_id == session_id)
        )
        return list(self.db.execute(query).all())

    def laps_to(self, session_id: int, lap_number: int) -> list[Lap]:
        query = (
            select(Lap)
            .where(Lap.session_id == session_id, Lap.lap_number <= lap_number)
            .order_by(Lap.driver_id, Lap.lap_number)
        )
        return list(self.db.scalars(query))

    def driver_laps(self, session_id: int, driver_id: int) -> list[Lap]:
        query = (
            select(Lap)
            .where(Lap.session_id == session_id, Lap.driver_id == driver_id)
            .order_by(Lap.lap_number)
        )
        return list(self.db.scalars(query))

    def session_laps(self, session_id: int) -> list[Lap]:
        query = select(Lap).where(Lap.session_id == session_id).order_by(Lap.lap_number)
        return list(self.db.scalars(query))

    def pit_stops(self, session_id: int, driver_id: int | None = None) -> list[PitStop]:
        query = select(PitStop).where(PitStop.session_id == session_id)
        if driver_id is not None:
            query = query.where(PitStop.driver_id == driver_id)
        return list(self.db.scalars(query.order_by(PitStop.driver_id, PitStop.lap_number)))

    def weather_before(self, session_id: int, timestamp_ms: int) -> WeatherSample | None:
        query = (
            select(WeatherSample)
            .where(
                WeatherSample.session_id == session_id,
                WeatherSample.timestamp_ms <= timestamp_ms,
            )
            .order_by(WeatherSample.timestamp_ms.desc())
            .limit(1)
        )
        return self.db.scalar(query)

    def weather_samples(self, session_id: int) -> list[WeatherSample]:
        query = (
            select(WeatherSample)
            .where(WeatherSample.session_id == session_id)
            .order_by(WeatherSample.timestamp_ms)
        )
        return list(self.db.scalars(query))

    def messages_to_lap(self, session_id: int, lap_number: int) -> list[RaceControlMessage]:
        query = (
            select(RaceControlMessage)
            .where(
                RaceControlMessage.session_id == session_id,
                RaceControlMessage.lap_number <= lap_number,
            )
            .order_by(RaceControlMessage.timestamp_ms.desc())
            .limit(5)
        )
        return list(self.db.scalars(query))

    def historical_pit_stops_for_location(self, location: str) -> list[PitStop]:
        query = (
            select(PitStop)
            .join(RaceSession, RaceSession.id == PitStop.session_id)
            .join(Event, Event.id == RaceSession.event_id)
            .where(Event.location == location)
        )
        return list(self.db.scalars(query))

    def historical_laps_for_location(self, location: str, session_id: int) -> list[Lap]:
        query = (
            select(Lap)
            .join(RaceSession, RaceSession.id == Lap.session_id)
            .join(Event, Event.id == RaceSession.event_id)
            .where(Event.location == location, Lap.session_id != session_id)
            .order_by(Lap.session_id, Lap.driver_id, Lap.lap_number)
        )
        return list(self.db.scalars(query))

    def simulation(self, simulation_id: int) -> StrategySimulation | None:
        return self.db.get(StrategySimulation, simulation_id)

    def add_simulation(self, simulation: StrategySimulation) -> StrategySimulation:
        self.db.add(simulation)
        self.db.commit()
        self.db.refresh(simulation)
        return simulation
