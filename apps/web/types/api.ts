export type Season = { id: number; year: number };
export type Event = {
  id: number;
  season_id: number;
  round_number: number;
  event_name: string;
  country: string | null;
  location: string | null;
  circuit_name: string | null;
  event_date: string | null;
  total_laps: number | null;
};
export type RaceSession = {
  id: number;
  event_id: number;
  session_type: string;
  session_date: string | null;
  source: string;
  ingestion_status: string;
  ingested_at: string | null;
  data_version: string;
};
export type Driver = {
  id: number;
  driver_number: string;
  abbreviation: string;
  full_name: string;
  team_name: string | null;
  country_code: string | null;
  grid_position: number | null;
  finishing_position: number | null;
  status: string | null;
  points: number | null;
};
export type Lap = {
  id: number;
  session_id: number;
  driver_id: number;
  lap_number: number;
  position: number | null;
  lap_time_ms: number | null;
  sector_1_ms: number | null;
  sector_2_ms: number | null;
  sector_3_ms: number | null;
  compound: string | null;
  tyre_life: number | null;
  stint_number: number | null;
  fresh_tyre: boolean | null;
  pit_in: boolean;
  pit_out: boolean;
  track_status: string | null;
  deleted: boolean;
  inaccurate: boolean;
  timestamp_ms: number | null;
  speed_i1: number | null;
  speed_i2: number | null;
  speed_fl: number | null;
  speed_st: number | null;
  personal_best: boolean | null;
};
export type LapPage = {
  items: Lap[];
  total: number;
  page: number;
  page_size: number;
};

export type PitLossEstimate = {
  estimated_ms: number;
  sample_count: number;
  source: string;
  uncertainty_ms: number;
};

export type RunningOrderItem = {
  driver_id: number;
  driver_number: string;
  abbreviation: string;
  full_name: string;
  team_name: string | null;
  position: number | null;
  completed_laps: number;
  compound: string | null;
  tyre_life: number | null;
  stint_number: number | null;
  last_lap_time_ms: number | null;
  timestamp_ms?: number | null;
  gap_to_leader_ms: number | null;
  gap_to_selected_ms: number | null;
  status: string | null;
  in_pit?: boolean;
};

export type RaceState = {
  session_id: number;
  control_lap: number;
  total_laps: number;
  selected_driver: {
    driver_id: number;
    abbreviation: string;
    full_name: string;
    position: number | null;
    completed_laps: number;
    compound: string | null;
    tyre_life: number | null;
    tyre_health_percent?: number | null;
    tyre_wear_pct?: number | null;
    tyre_pace_loss_seconds?: number | null;
    tyre_state?: string | null;
    tyre_performance_life_laps?: number | null;
    tyre_durability_laps?: number | null;
    tyre_stint_sample_count?: number;
    tyre_life_source?: string | null;
    stint_number: number | null;
    last_lap_time_ms: number | null;
    recent_pace_ms: number | null;
    recent_pace_sample_count: number;
    timestamp_ms?: number | null;
    pit_history: Array<{
      lap_number: number;
      pit_entry_time_ms: number | null;
      pit_exit_time_ms: number | null;
      pit_duration_ms: number | null;
    }>;
  };
  running_order: RunningOrderItem[];
  weather: {
    timestamp_ms: number;
    air_temperature: number | null;
    track_temperature: number | null;
    humidity: number | null;
    rainfall: boolean | null;
    wind_speed: number | null;
  } | null;
  race_control: {
    track_status: string | null;
    status_label: string;
    latest_messages: string[];
    intervention_start_lap?: number | null;
    boxed_driver_ids?: number[];
  };
  pit_loss: PitLossEstimate;
  likely_rejoin_position: number | null;
  nearby_driver_ids: number[];
  data_quality: string;
};

export type Timeline = {
  session_id: number;
  driver_id: number;
  total_laps: number;
  stints: Array<{
    stint_number: number;
    compound: string | null;
    start_lap: number;
    end_lap: number;
    lap_count: number;
  }>;
  pit_laps: number[];
};

export type StrategyCandidate = {
  name: string;
  pit_lap: number | null;
  next_compound: "SOFT" | "MEDIUM" | "HARD" | "INTERMEDIATE" | "WET" | null;
  pace_mode: "CONSERVATIVE" | "BALANCED" | "AGGRESSIVE";
};

export type SimulationSubmission = {
  strategies: StrategyCandidate[];
  simulation_count: number;
  random_seed: number;
  scenario?: {
    pit_loss_delta_ms: number;
    tyre_degradation_multiplier: number;
  };
  selected_strategy_name?: string;
  simulation_context?: SimulationContext;
};

export type SimulationContext = {
  current_compound: StrategyCandidate["next_compound"];
  current_tyre_age: number | null;
  current_effective_tyre_age?: number | null;
  current_tyre_health_pct?: number | null;
  current_position: number | null;
  current_stint_number?: number | null;
  current_completed_laps?: number | null;
  current_timestamp_ms?: number | null;
  cumulative_time_delta_ms: number;
};

export type FinishPositionBucket = {
  position: number;
  count: number;
  probability: number;
};

export type HistogramBin = {
  lower_ms: number;
  upper_ms: number;
  count: number;
  probability: number;
};

export type MonteCarloAggregate = {
  mean_predicted_finish: number;
  median_predicted_finish: number;
  most_likely_finish: number;
  expected_total_time_ms: number;
  median_total_time_ms: number;
  mean_time_vs_deterministic_baseline_ms: number;
  median_time_vs_deterministic_baseline_ms: number;
  win_probability: number;
  podium_probability: number;
  points_probability: number;
  improve_actual_probability: number | null;
  improve_stay_out_probability: number;
  race_time_p05_ms: number;
  race_time_p25_ms: number;
  race_time_p75_ms: number;
  race_time_p95_ms: number;
  finish_position_p05: number;
  finish_position_p95: number;
  likely_rejoin_position: number | null;
  traffic_risk: number;
  degradation_risk: number;
  finish_position_distribution: FinishPositionBucket[];
  time_delta_histogram: HistogramBin[];
  simulation_count: number;
  random_seed: number;
  engine_version: string;
  data_quality: string;
};

export type StrategyComparison = {
  comparison_id: number;
  engine_version: string;
  deterministic: boolean;
  session_id: number;
  driver_id: number;
  control_lap: number;
  pit_loss: PitLossEstimate;
  available_compounds: string[];
  outcomes: Array<{
    name: string;
    pit_lap: number | null;
    next_compound: string | null;
    pace_mode: string;
    predicted_finish: number;
    predicted_total_time_ms: number;
    time_vs_actual_ms: number | null;
    time_vs_baseline_ms: number;
    likely_rejoin_position: number | null;
    traffic_risk: number;
    degradation_risk: number;
    final_tyre_age: number;
    pit_loss_ms: number;
    tyre_estimate: {
      compound: string;
      initial_offset_ms: number;
      degradation_per_lap_ms: number;
      sample_count: number;
      source: string;
      uncertainty_ms: number;
      degradation_uncertainty_per_lap_ms: number;
      performance_life_laps?: number;
      durability_laps?: number;
      stint_sample_count?: number;
      life_source?: string;
    };
    assumptions: string[];
    projected_laps?: Array<{
      lap_number: number;
      compound: string;
      tyre_age: number;
      stint_number?: number;
      tyre_health_percent?: number;
      effective_tyre_age?: number;
      tyre_wear_pct?: number;
      tyre_pace_loss_seconds?: number;
      tyre_state?: string;
      lap_time_ms: number;
      cumulative_time_ms: number;
      historical_time_ms?: number;
      predicted_position: number;
      pit_stop: boolean;
      dnf?: boolean;
      status?: string | null;
      retirement_reason?: string | null;
      lap_completed?: boolean;
    }>;
    monte_carlo: MonteCarloAggregate | null;
    dnf?: boolean;
    current_tyre_health_pct?: number;
    current_tyre_wear_pct?: number;
    current_tyre_pace_loss_seconds?: number;
    projected_next_lap_health_pct?: number | null;
    projected_next_lap_pace_loss_seconds?: number | null;
    cliff_start_health_pct?: number;
    tyre_state?: string;
    retirement_reason?: string | null;
    calibration_source?: string;
  }>;
  recommendation: {
    strategy_name: string;
    explanation: string;
    primary_advantage: string | null;
    key_risk: string | null;
    uncertainty_note: string | null;
  };
  actual_strategy: {
    session_id: number;
    driver_id: number;
    control_lap: number;
    actual_finish: number | null;
    actual_status: string | null;
    actual_total_time_ms: number | null;
    remaining_stops: Array<{
      pit_lap: number;
      next_compound: string | null;
      pit_duration_ms: number | null;
    }>;
  };
  disclaimer: string;
  simulation_count: number;
  random_seed: number;
  calculation_time_ms: number | null;
  uncertainty_sources: Array<{
    variable: string;
    source: string;
    sample_count: number;
    scale_ms: number;
    fallback: boolean;
    assumption: string;
  }>;
  assumptions: string[];
};
