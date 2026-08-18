from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.race_state import ActualStrategyResponse, PitLossEstimate


class Compound(StrEnum):
    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"


class PaceMode(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    BALANCED = "BALANCED"
    AGGRESSIVE = "AGGRESSIVE"


class StrategyCandidate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    pit_lap: int | None = Field(default=None, ge=1)
    next_compound: Compound | None = None
    pace_mode: PaceMode = PaceMode.BALANCED

    @model_validator(mode="after")
    def validate_stop(self) -> "StrategyCandidate":
        if (self.pit_lap is None) != (self.next_compound is None):
            raise ValueError("pit_lap and next_compound must either both be set or both be null")
        return self


class ScenarioAdjustments(BaseModel):
    pit_loss_delta_ms: int = Field(default=0, ge=-10_000, le=10_000)
    tyre_degradation_multiplier: float = Field(default=1.0, ge=0.5, le=1.5)


class SimulationContext(BaseModel):
    """Counterfactual state carried between interactive engineer decisions."""

    current_compound: Compound | None = None
    current_tyre_age: float | None = Field(default=None, ge=0, le=150)
    current_effective_tyre_age: float | None = Field(default=None, ge=0, le=250)
    current_tyre_health_pct: float | None = Field(default=None, ge=0, le=100)
    current_position: int | None = Field(default=None, ge=1, le=20)
    current_stint_number: int | None = Field(default=None, ge=1, le=20)
    current_completed_laps: int | None = Field(default=None, ge=0, le=200)
    current_timestamp_ms: int | None = Field(default=None, ge=0, le=50_000_000)
    cumulative_time_delta_ms: int = Field(default=0, ge=-300_000, le=300_000)


class StrategyCompareRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": 1,
                "driver_id": 4,
                "control_lap": 20,
                "simulation_count": 1000,
                "random_seed": 42,
                "strategies": [
                    {
                        "name": "Pit now · HARD",
                        "pit_lap": 20,
                        "next_compound": "HARD",
                        "pace_mode": "BALANCED",
                    },
                    {
                        "name": "Stay out",
                        "pit_lap": None,
                        "next_compound": None,
                        "pace_mode": "BALANCED",
                    },
                ],
            }
        }
    )
    session_id: int = Field(ge=1)
    driver_id: int = Field(ge=1)
    control_lap: int = Field(ge=1)
    strategies: list[StrategyCandidate] = Field(min_length=2, max_length=5)
    simulation_count: int = Field(default=1000, ge=100, le=10_000)
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)
    scenario: ScenarioAdjustments = Field(default_factory=ScenarioAdjustments)
    simulation_context: SimulationContext | None = None


class TyreEstimateRead(BaseModel):
    compound: str
    initial_offset_ms: int
    degradation_per_lap_ms: int
    sample_count: int
    source: str
    uncertainty_ms: int
    degradation_uncertainty_per_lap_ms: int = 45
    performance_life_laps: float = 35
    durability_laps: float = 49
    stint_sample_count: int = 0
    life_source: str = "compound_life_fallback"


class FinishPositionBucket(BaseModel):
    position: int = Field(ge=1)
    count: int = Field(ge=0)
    probability: float = Field(ge=0, le=1)


class HistogramBin(BaseModel):
    lower_ms: int
    upper_ms: int
    count: int = Field(ge=0)
    probability: float = Field(ge=0, le=1)


class MonteCarloAggregate(BaseModel):
    mean_predicted_finish: float
    median_predicted_finish: float
    most_likely_finish: int
    expected_total_time_ms: int
    median_total_time_ms: int
    mean_time_vs_deterministic_baseline_ms: int
    median_time_vs_deterministic_baseline_ms: int
    win_probability: float = Field(ge=0, le=1)
    podium_probability: float = Field(ge=0, le=1)
    points_probability: float = Field(ge=0, le=1)
    improve_actual_probability: float | None = Field(default=None, ge=0, le=1)
    improve_stay_out_probability: float = Field(ge=0, le=1)
    race_time_p05_ms: int
    race_time_p25_ms: int
    race_time_p75_ms: int
    race_time_p95_ms: int
    finish_position_p05: int
    finish_position_p95: int
    likely_rejoin_position: int | None
    traffic_risk: float = Field(ge=0, le=1)
    degradation_risk: float = Field(ge=0, le=1)
    finish_position_distribution: list[FinishPositionBucket]
    time_delta_histogram: list[HistogramBin]
    simulation_count: int
    random_seed: int
    engine_version: str
    data_quality: str


class UncertaintySourceRead(BaseModel):
    variable: str
    source: str
    sample_count: int = Field(ge=0)
    scale_ms: float = Field(ge=0)
    fallback: bool
    assumption: str


class ProjectedLapRead(BaseModel):
    lap_number: int
    compound: str
    tyre_age: float
    stint_number: int = Field(default=1, ge=1)
    effective_tyre_age: float = Field(default=1, ge=0)
    tyre_health_percent: float = Field(default=100, ge=0, le=100)
    tyre_wear_pct: float = Field(default=0, ge=0, le=100)
    tyre_pace_loss_seconds: float = Field(default=0, ge=0)
    tyre_state: str = "HEALTHY"
    lap_time_ms: int
    cumulative_time_ms: int
    historical_time_ms: int = 0
    predicted_position: int
    pit_stop: bool = False
    dnf: bool = False
    status: str | None = None
    retirement_reason: str | None = None
    lap_completed: bool = True


class StrategyOutcome(BaseModel):
    name: str
    pit_lap: int | None
    next_compound: str | None
    pace_mode: PaceMode
    predicted_finish: int
    predicted_total_time_ms: int
    time_vs_actual_ms: int | None
    time_vs_baseline_ms: int
    likely_rejoin_position: int | None
    traffic_risk: float = Field(ge=0, le=1)
    degradation_risk: float = Field(ge=0, le=1)
    final_tyre_age: float
    pit_loss_ms: int
    tyre_estimate: TyreEstimateRead
    assumptions: list[str]
    monte_carlo: MonteCarloAggregate | None = None
    projected_laps: list[ProjectedLapRead] = Field(default_factory=list)
    dnf: bool = False
    current_tyre_health_pct: float = Field(default=100, ge=0, le=100)
    current_tyre_wear_pct: float = Field(default=0, ge=0, le=100)
    current_tyre_pace_loss_seconds: float = Field(default=0, ge=0)
    projected_next_lap_health_pct: float | None = Field(default=None, ge=0, le=100)
    projected_next_lap_pace_loss_seconds: float | None = Field(default=None, ge=0)
    cliff_start_health_pct: float = Field(default=50, ge=0, le=100)
    tyre_state: str = "HEALTHY"
    retirement_reason: str | None = None
    calibration_source: str = "compound_life_fallback"


class RecommendationRead(BaseModel):
    strategy_name: str
    explanation: str
    primary_advantage: str | None = None
    key_risk: str | None = None
    uncertainty_note: str | None = None


class StrategyComparisonResponse(BaseModel):
    comparison_id: int
    engine_version: str
    deterministic: bool
    session_id: int
    driver_id: int
    control_lap: int
    pit_loss: PitLossEstimate
    available_compounds: list[str]
    outcomes: list[StrategyOutcome]
    recommendation: RecommendationRead
    actual_strategy: ActualStrategyResponse
    disclaimer: str
    simulation_count: int = 1
    random_seed: int = 0
    calculation_time_ms: float | None = None
    uncertainty_sources: list[UncertaintySourceRead] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
