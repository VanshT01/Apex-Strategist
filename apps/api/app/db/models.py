from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    events: Mapped[list[Event]] = relationship(
        back_populates="season", cascade="all, delete-orphan"
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("season_id", "round_number", name="uq_event_round"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    round_number: Mapped[int] = mapped_column(Integer)
    event_name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(80))
    location: Mapped[str | None] = mapped_column(String(120))
    circuit_name: Mapped[str | None] = mapped_column(String(160))
    event_date: Mapped[date | None] = mapped_column(Date)
    total_laps: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    season: Mapped[Season] = relationship(back_populates="events")
    sessions: Mapped[list[RaceSession]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class RaceSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("event_id", "session_type", name="uq_event_session_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    session_type: Mapped[str] = mapped_column(String(30), index=True)
    session_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(30), default="fastf1")
    ingestion_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    ingestion_error: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_version: Mapped[str] = mapped_column(String(50), default="fastf1-v1")
    event: Mapped[Event] = relationship(back_populates="sessions")
    entries: Mapped[list[RaceEntry]] = relationship(cascade="all, delete-orphan")
    laps: Mapped[list[Lap]] = relationship(cascade="all, delete-orphan")
    weather_samples: Mapped[list[WeatherSample]] = relationship(cascade="all, delete-orphan")
    race_control_messages: Mapped[list[RaceControlMessage]] = relationship(
        cascade="all, delete-orphan"
    )
    pit_stops: Mapped[list[PitStop]] = relationship(cascade="all, delete-orphan")


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (UniqueConstraint("driver_number", name="uq_driver_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    driver_number: Mapped[str] = mapped_column(String(4), index=True)
    abbreviation: Mapped[str] = mapped_column(String(4), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    team_name: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(5))


class RaceEntry(Base):
    __tablename__ = "race_entries"
    __table_args__ = (
        UniqueConstraint("session_id", "driver_id", name="uq_race_entry_driver"),
        Index("ix_race_entry_session_finish", "session_id", "finishing_position"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    abbreviation: Mapped[str | None] = mapped_column(String(4))
    full_name: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(5))
    team_name: Mapped[str | None] = mapped_column(String(120))
    grid_position: Mapped[int | None] = mapped_column(Integer)
    finishing_position: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(100))
    points: Mapped[float | None] = mapped_column(Float)
    driver: Mapped[Driver] = relationship()


class Lap(Base):
    __tablename__ = "laps"
    __table_args__ = (
        UniqueConstraint("session_id", "driver_id", "lap_number", name="uq_lap_driver_number"),
        Index("ix_lap_session_driver_number", "session_id", "driver_id", "lap_number"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    lap_number: Mapped[int] = mapped_column(Integer)
    position: Mapped[int | None] = mapped_column(Integer)
    lap_time_ms: Mapped[int | None] = mapped_column(Integer)
    sector_1_ms: Mapped[int | None] = mapped_column(Integer)
    sector_2_ms: Mapped[int | None] = mapped_column(Integer)
    sector_3_ms: Mapped[int | None] = mapped_column(Integer)
    compound: Mapped[str | None] = mapped_column(String(30), index=True)
    tyre_life: Mapped[float | None] = mapped_column(Float)
    stint_number: Mapped[int | None] = mapped_column(Integer)
    fresh_tyre: Mapped[bool | None] = mapped_column(Boolean)
    pit_in: Mapped[bool] = mapped_column(Boolean, default=False)
    pit_out: Mapped[bool] = mapped_column(Boolean, default=False)
    track_status: Mapped[str | None] = mapped_column(String(30))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    inaccurate: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp_ms: Mapped[int | None] = mapped_column(Integer)
    speed_i1: Mapped[float | None] = mapped_column(Float)
    speed_i2: Mapped[float | None] = mapped_column(Float)
    speed_fl: Mapped[float | None] = mapped_column(Float)
    speed_st: Mapped[float | None] = mapped_column(Float)
    personal_best: Mapped[bool | None] = mapped_column(Boolean)
    driver: Mapped[Driver] = relationship()


class WeatherSample(Base):
    __tablename__ = "weather_samples"
    __table_args__ = (UniqueConstraint("session_id", "timestamp_ms", name="uq_weather_time"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    timestamp_ms: Mapped[int] = mapped_column(Integer)
    air_temperature: Mapped[float | None] = mapped_column(Float)
    track_temperature: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    pressure: Mapped[float | None] = mapped_column(Float)
    rainfall: Mapped[bool | None] = mapped_column(Boolean)
    wind_direction: Mapped[float | None] = mapped_column(Float)
    wind_speed: Mapped[float | None] = mapped_column(Float)


class RaceControlMessage(Base):
    __tablename__ = "race_control_messages"
    __table_args__ = (Index("ix_race_control_session_lap", "session_id", "lap_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    timestamp_ms: Mapped[int | None] = mapped_column(Integer)
    lap_number: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(80))
    flag: Mapped[str | None] = mapped_column(String(40))
    scope: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)


class PitStop(Base):
    __tablename__ = "pit_stops"
    __table_args__ = (
        UniqueConstraint("session_id", "driver_id", "lap_number", name="uq_pit_stop_lap"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    lap_number: Mapped[int] = mapped_column(Integer)
    pit_entry_time_ms: Mapped[int | None] = mapped_column(Integer)
    pit_exit_time_ms: Mapped[int | None] = mapped_column(Integer)
    pit_duration_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_stationary_ms: Mapped[int | None] = mapped_column(Integer)


class StrategySimulation(Base):
    __tablename__ = "strategy_simulations"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    control_lap: Mapped[int] = mapped_column(Integer)
    strategy_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    simulation_count: Mapped[int] = mapped_column(Integer)
    random_seed: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(50))
    result_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"
    __table_args__ = (UniqueConstraint("model_name", "model_version", name="uq_model_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(50))
    feature_schema_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    file_path: Mapped[str] = mapped_column(String(500))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
