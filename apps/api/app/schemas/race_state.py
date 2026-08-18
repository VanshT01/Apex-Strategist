from pydantic import BaseModel, Field


class RunningOrderItem(BaseModel):
    driver_id: int
    driver_number: str
    abbreviation: str
    full_name: str
    team_name: str | None
    position: int | None
    completed_laps: int
    compound: str | None
    tyre_life: float | None
    stint_number: int | None
    last_lap_time_ms: int | None
    timestamp_ms: int | None = None
    gap_to_leader_ms: int | None
    gap_to_selected_ms: int | None
    status: str | None
    in_pit: bool = False


class PitStopState(BaseModel):
    lap_number: int
    pit_entry_time_ms: int | None
    pit_exit_time_ms: int | None
    pit_duration_ms: int | None


class WeatherState(BaseModel):
    timestamp_ms: int
    air_temperature: float | None
    track_temperature: float | None
    humidity: float | None
    rainfall: bool | None
    wind_speed: float | None


class RaceControlState(BaseModel):
    track_status: str | None
    status_label: str
    latest_messages: list[str]
    intervention_start_lap: int | None = None
    boxed_driver_ids: list[int] = Field(default_factory=list)


class PitLossEstimate(BaseModel):
    estimated_ms: int
    sample_count: int
    source: str
    uncertainty_ms: int


class DriverRaceState(BaseModel):
    driver_id: int
    abbreviation: str
    full_name: str
    position: int | None
    completed_laps: int
    compound: str | None
    tyre_life: float | None
    tyre_health_percent: float | None = Field(default=None, ge=0, le=100)
    tyre_wear_pct: float | None = Field(default=None, ge=0, le=100)
    tyre_pace_loss_seconds: float | None = Field(default=None, ge=0)
    tyre_state: str | None = None
    tyre_performance_life_laps: float | None = None
    tyre_durability_laps: float | None = None
    tyre_stint_sample_count: int = 0
    tyre_life_source: str | None = None
    stint_number: int | None
    last_lap_time_ms: int | None
    recent_pace_ms: int | None
    recent_pace_sample_count: int
    timestamp_ms: int | None = None
    pit_history: list[PitStopState]


class RaceStateResponse(BaseModel):
    session_id: int
    control_lap: int
    total_laps: int
    selected_driver: DriverRaceState
    running_order: list[RunningOrderItem]
    weather: WeatherState | None
    race_control: RaceControlState
    pit_loss: PitLossEstimate
    likely_rejoin_position: int | None
    nearby_driver_ids: list[int]
    data_quality: str


class StintSummary(BaseModel):
    stint_number: int
    compound: str | None
    start_lap: int
    end_lap: int
    lap_count: int


class TimelineResponse(BaseModel):
    session_id: int
    driver_id: int
    total_laps: int
    stints: list[StintSummary]
    pit_laps: list[int]


class ActualStop(BaseModel):
    pit_lap: int
    next_compound: str | None
    pit_duration_ms: int | None


class ActualStrategyResponse(BaseModel):
    session_id: int
    driver_id: int
    control_lap: int = Field(ge=1)
    actual_finish: int | None
    actual_status: str | None
    actual_total_time_ms: int | None
    remaining_stops: list[ActualStop]
