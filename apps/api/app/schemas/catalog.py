from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SeasonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    year: int


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    season_id: int
    round_number: int
    event_name: str
    country: str | None
    location: str | None
    circuit_name: str | None
    event_date: date | None
    total_laps: int | None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    session_type: str
    session_date: datetime | None
    source: str
    ingestion_status: str
    ingested_at: datetime | None
    data_version: str


class DriverRead(BaseModel):
    id: int
    driver_number: str
    abbreviation: str
    full_name: str
    team_name: str | None
    country_code: str | None
    grid_position: int | None
    finishing_position: int | None
    status: str | None
    points: float | None


class LapRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    driver_id: int
    lap_number: int
    position: int | None
    lap_time_ms: int | None
    sector_1_ms: int | None
    sector_2_ms: int | None
    sector_3_ms: int | None
    compound: str | None
    tyre_life: float | None
    stint_number: int | None
    fresh_tyre: bool | None
    pit_in: bool
    pit_out: bool
    track_status: str | None
    deleted: bool
    inaccurate: bool
    timestamp_ms: int | None
    speed_i1: float | None
    speed_i2: float | None
    speed_fl: float | None
    speed_st: float | None
    personal_best: bool | None


class LapPage(BaseModel):
    items: list[LapRead]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str
