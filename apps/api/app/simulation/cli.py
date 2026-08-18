from __future__ import annotations

import json
from time import perf_counter

import typer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import Driver, Event, RaceEntry, RaceSession, Season
from app.db.session import SessionLocal
from app.repositories.race import RaceRepository
from app.schemas.strategy import StrategyCandidate, StrategyCompareRequest
from app.services.strategy import StrategyService
from app.simulation.calibration import UncertaintyCalibrator
from app.simulation.pace_model import build_session_pace_predictor
from app.simulation.pit_loss import PitLossEstimator
from app.simulation.tyres import (
    DEFAULT_TYRE_PERFORMANCE_CONFIG,
    TyreDegradationEstimator,
    tyre_pace_loss_seconds,
    tyre_wear_pct,
)
from app.simulation.validation import run_engineer_validation_sweep

app = typer.Typer(help="Inspect and benchmark Apex Strategist uncertainty inputs.")


@app.command("train-pace")
def train_pace(
    year: int = typer.Option(2023, min=2018, max=2100),
    event: str = typer.Option("Canadian Grand Prix"),
    driver_number: str = typer.Option("18"),
    control_lap: int = typer.Option(32, min=1),
) -> None:
    """Fit/load the leakage-safe expected-pace artifact for one race cutoff."""
    configure_logging()
    with SessionLocal() as db:
        session, resolved_event, driver = _resolve(db, year, event, driver_number)
        selected_control = _control_lap(resolved_event, control_lap)
        predictor = build_session_pace_predictor(
            db,
            session=session,
            event=resolved_event,
            laps=RaceRepository(db).session_laps(session.id),
            driver_id=driver.id,
            driver=driver,
            driver_code=(
                RaceRepository(db).entry(session.id, driver.id).abbreviation or driver.abbreviation
            ),
            control_lap=selected_control,
            model_path=get_settings().model_path,
        )
        if predictor is None:
            raise typer.BadParameter(
                "Fewer than 2,000 eligible laps exist before this race; "
                "deterministic fallback applies"
            )
        db.commit()
        typer.echo(
            json.dumps(
                {
                    "year": year,
                    "event": resolved_event.event_name,
                    "session_id": session.id,
                    "control_lap": selected_control,
                    "pace_model": predictor.source,
                },
                indent=2,
            )
        )


def _resolve(
    db: Session, year: int, event_name: str, driver_number: str
) -> tuple[RaceSession, Event, Driver]:
    event = db.scalar(
        select(Event)
        .join(Season, Season.id == Event.season_id)
        .where(
            Season.year == year,
            func.lower(Event.event_name).contains(event_name.casefold()),
        )
        .order_by(Event.round_number)
        .limit(1)
    )
    if event is None:
        raise typer.BadParameter(f"No event matching {year} {event_name!r}")
    session = db.scalar(
        select(RaceSession).where(
            RaceSession.event_id == event.id,
            RaceSession.session_type == "RACE",
            RaceSession.ingestion_status == "complete",
        )
    )
    if session is None:
        raise typer.BadParameter("The selected race has not been fully ingested")
    driver = db.scalar(
        select(Driver)
        .join(RaceEntry, RaceEntry.driver_id == Driver.id)
        .where(
            RaceEntry.session_id == session.id,
            Driver.driver_number == driver_number,
        )
    )
    if driver is None:
        raise typer.BadParameter(f"Driver number {driver_number} is not in the race")
    return session, event, driver


def _control_lap(event: Event, requested: int) -> int:
    maximum = max((event.total_laps or 0) - 10, 1)
    if requested > maximum:
        raise typer.BadParameter(f"control lap must be at or before {maximum}")
    return requested


@app.command()
def diagnose(
    year: int = typer.Option(2024, min=2018, max=2100),
    event: str = typer.Option("British Grand Prix"),
    driver_number: str = typer.Option("4"),
    control_lap: int = typer.Option(20, min=1),
) -> None:
    """Report empirical scales, fallbacks, and heuristic uncertainty assumptions."""
    configure_logging()
    with SessionLocal() as db:
        session, resolved_event, driver = _resolve(db, year, event, driver_number)
        selected_control = _control_lap(resolved_event, control_lap)
        repo = RaceRepository(db)
        laps = repo.session_laps(session.id)
        pit_estimator = PitLossEstimator(repo)
        pit_loss = pit_estimator.estimate(session.id)
        pit_samples, _ = pit_estimator.distribution(session.id)
        historical = (
            repo.historical_laps_for_location(resolved_event.location, session.id)
            if resolved_event.location
            else []
        )
        calibration = UncertaintyCalibrator(
            laps,
            repo.entries(session.id),
            driver.id,
            selected_control,
            pit_loss,
            pit_samples,
            historical,
        ).calibrate()
        tyres = TyreDegradationEstimator(laps)
        output = {
            "year": year,
            "event": resolved_event.event_name,
            "session_id": session.id,
            "driver_number": driver_number,
            "control_lap": selected_control,
            "data_quality": calibration.data_quality,
            "uncertainty_sources": [source.model_dump() for source in calibration.sources],
            "tyre_estimates": [
                tyres.estimate(compound).to_schema().model_dump()
                for compound in tyres.available_compounds()
            ],
            "tyre_performance_config": DEFAULT_TYRE_PERFORMANCE_CONFIG.__dict__,
            "tyre_pace_calibration": [
                {
                    "health_pct": health,
                    "wear_pct": tyre_wear_pct(health),
                    "pace_loss_seconds": round(tyre_pace_loss_seconds(health), 3),
                }
                for health in (100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 5)
            ],
        }
    typer.echo(json.dumps(output, indent=2))


@app.command()
def benchmark(
    year: int = typer.Option(2024, min=2018, max=2100),
    event: str = typer.Option("British Grand Prix"),
    driver_number: str = typer.Option("4"),
    control_lap: int = typer.Option(20, min=1),
    simulation_count: int = typer.Option(1000, min=100, max=10_000),
    random_seed: int = typer.Option(42, min=0, max=2_147_483_647),
) -> None:
    """Run a reproducible three-strategy comparison and report honest timing."""
    configure_logging()
    with SessionLocal() as db:
        session, resolved_event, driver = _resolve(db, year, event, driver_number)
        selected_control = _control_lap(resolved_event, control_lap)
        available = TyreDegradationEstimator(
            RaceRepository(db).session_laps(session.id)
        ).available_compounds()
        hard = "HARD" if "HARD" in available else available[0]
        medium = "MEDIUM" if "MEDIUM" in available else available[0]
        payload = StrategyCompareRequest(
            session_id=session.id,
            driver_id=driver.id,
            control_lap=selected_control,
            simulation_count=simulation_count,
            random_seed=random_seed,
            strategies=[
                StrategyCandidate(
                    name=f"Pit now · {hard}", pit_lap=selected_control, next_compound=hard
                ),
                StrategyCandidate(
                    name=f"Wait 3 laps · {medium}",
                    pit_lap=selected_control + 3,
                    next_compound=medium,
                ),
                StrategyCandidate(name="Stay out"),
            ],
        )
        wall_started = perf_counter()
        result = StrategyService(db).compare(payload)
        wall_time_ms = (perf_counter() - wall_started) * 1000
    typer.echo(
        json.dumps(
            {
                "comparison_id": result.comparison_id,
                "engine_version": result.engine_version,
                "simulation_count": simulation_count,
                "random_seed": random_seed,
                "simulation_calculation_ms": result.calculation_time_ms,
                "end_to_end_service_ms": round(wall_time_ms, 3),
                "timing_note": (
                    "simulation_calculation_ms excludes ORM queries and uncertainty calibration"
                ),
            },
            indent=2,
        )
    )


@app.command("validate-engineer")
def validate_engineer(
    simulation_count: int = typer.Option(100, min=100, max=10_000),
    random_seed: int = typer.Option(42, min=0, max=2_147_483_647),
) -> None:
    """Run the multi-race Engineer Mode reliability and feasibility matrix."""
    configure_logging()
    with SessionLocal() as db:
        report = run_engineer_validation_sweep(
            db,
            simulation_count=simulation_count,
            random_seed=random_seed,
        )
    typer.echo(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
