"""Initial normalized race schema."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260804_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("year", name="seasons_year_key"),
    )
    op.create_index("ix_seasons_year", "seasons", ["year"], unique=True)
    op.create_table(
        "drivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver_number", sa.String(4), nullable=False),
        sa.Column("abbreviation", sa.String(4), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("team_name", sa.String(120)),
        sa.Column("country_code", sa.String(5)),
        sa.UniqueConstraint("driver_number", name="uq_driver_number"),
    )
    op.create_index("ix_drivers_driver_number", "drivers", ["driver_number"])
    op.create_index("ix_drivers_abbreviation", "drivers", ["abbreviation"])
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(160), nullable=False),
        sa.Column("country", sa.String(80)),
        sa.Column("location", sa.String(120)),
        sa.Column("circuit_name", sa.String(160)),
        sa.Column("event_date", sa.Date()),
        sa.Column("total_laps", sa.Integer()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("season_id", "round_number", name="uq_event_round"),
    )
    op.create_index("ix_events_season_id", "events", ["season_id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_type", sa.String(30), nullable=False),
        sa.Column("session_date", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("ingestion_status", sa.String(30), nullable=False),
        sa.Column("ingestion_error", sa.Text()),
        sa.Column("ingested_at", sa.DateTime(timezone=True)),
        sa.Column("data_version", sa.String(50), nullable=False),
        sa.UniqueConstraint("event_id", "session_type", name="uq_event_session_type"),
    )
    op.create_index("ix_sessions_event_id", "sessions", ["event_id"])
    op.create_index("ix_sessions_session_type", "sessions", ["session_type"])
    op.create_index("ix_sessions_ingestion_status", "sessions", ["ingestion_status"])
    op.create_table(
        "race_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("grid_position", sa.Integer()),
        sa.Column("finishing_position", sa.Integer()),
        sa.Column("status", sa.String(100)),
        sa.Column("points", sa.Float()),
        sa.UniqueConstraint("session_id", "driver_id", name="uq_race_entry_driver"),
    )
    op.create_index("ix_race_entries_driver_id", "race_entries", ["driver_id"])
    op.create_index("ix_race_entry_session_finish", "race_entries", ["session_id", "finishing_position"])
    op.create_table(
        "laps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer()),
        sa.Column("lap_time_ms", sa.Integer()),
        sa.Column("sector_1_ms", sa.Integer()), sa.Column("sector_2_ms", sa.Integer()), sa.Column("sector_3_ms", sa.Integer()),
        sa.Column("compound", sa.String(30)), sa.Column("tyre_life", sa.Float()), sa.Column("stint_number", sa.Integer()),
        sa.Column("fresh_tyre", sa.Boolean()), sa.Column("pit_in", sa.Boolean(), nullable=False), sa.Column("pit_out", sa.Boolean(), nullable=False),
        sa.Column("track_status", sa.String(30)), sa.Column("deleted", sa.Boolean(), nullable=False), sa.Column("inaccurate", sa.Boolean(), nullable=False),
        sa.Column("timestamp_ms", sa.Integer()), sa.Column("speed_i1", sa.Float()), sa.Column("speed_i2", sa.Float()),
        sa.Column("speed_fl", sa.Float()), sa.Column("speed_st", sa.Float()), sa.Column("personal_best", sa.Boolean()),
        sa.UniqueConstraint("session_id", "driver_id", "lap_number", name="uq_lap_driver_number"),
    )
    op.create_index("ix_laps_driver_id", "laps", ["driver_id"])
    op.create_index("ix_laps_compound", "laps", ["compound"])
    op.create_index("ix_lap_session_driver_number", "laps", ["session_id", "driver_id", "lap_number"])
    op.create_table(
        "weather_samples",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=False), sa.Column("air_temperature", sa.Float()), sa.Column("track_temperature", sa.Float()),
        sa.Column("humidity", sa.Float()), sa.Column("pressure", sa.Float()), sa.Column("rainfall", sa.Boolean()),
        sa.Column("wind_direction", sa.Float()), sa.Column("wind_speed", sa.Float()),
        sa.UniqueConstraint("session_id", "timestamp_ms", name="uq_weather_time"),
    )
    op.create_index("ix_weather_samples_session_id", "weather_samples", ["session_id"])
    op.create_table(
        "race_control_messages",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp_ms", sa.Integer()), sa.Column("lap_number", sa.Integer()), sa.Column("category", sa.String(80)),
        sa.Column("flag", sa.String(40)), sa.Column("scope", sa.String(40)), sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("ix_race_control_session_lap", "race_control_messages", ["session_id", "lap_number"])
    op.create_table(
        "pit_stops",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=False), sa.Column("lap_number", sa.Integer(), nullable=False),
        sa.Column("pit_entry_time_ms", sa.Integer()), sa.Column("pit_exit_time_ms", sa.Integer()), sa.Column("pit_duration_ms", sa.Integer()),
        sa.Column("estimated_stationary_ms", sa.Integer()), sa.UniqueConstraint("session_id", "driver_id", "lap_number", name="uq_pit_stop_lap"),
    )
    op.create_index("ix_pit_stops_session_id", "pit_stops", ["session_id"])
    op.create_index("ix_pit_stops_driver_id", "pit_stops", ["driver_id"])
    op.create_table(
        "strategy_simulations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=False), sa.Column("control_lap", sa.Integer(), nullable=False),
        sa.Column("strategy_payload_json", sa.JSON(), nullable=False), sa.Column("simulation_count", sa.Integer(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False), sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("result_payload_json", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategy_simulations_session_id", "strategy_simulations", ["session_id"])
    op.create_index("ix_strategy_simulations_driver_id", "strategy_simulations", ["driver_id"])
    op.create_table(
        "model_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False), sa.Column("feature_schema_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False), sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("model_name", "model_version", name="uq_model_version"),
    )


def downgrade() -> None:
    for table in ("model_artifacts", "strategy_simulations", "pit_stops", "race_control_messages", "weather_samples", "laps", "race_entries", "sessions", "events", "drivers", "seasons"):
        op.drop_table(table)
