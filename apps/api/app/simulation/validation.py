from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Driver, Event, Lap, RaceEntry, RaceSession, Season
from app.schemas.strategy import StrategyCandidate, StrategyCompareRequest
from app.services.strategy import StrategyService


@dataclass(frozen=True)
class EngineerValidationCase:
    year: int
    event: str
    driver_number: str


DEFAULT_ENGINEER_CASES = (
    EngineerValidationCase(2021, "Abu Dhabi Grand Prix", "33"),
    EngineerValidationCase(2021, "Abu Dhabi Grand Prix", "44"),
    EngineerValidationCase(2021, "Abu Dhabi Grand Prix", "7"),
    EngineerValidationCase(2022, "British Grand Prix", "55"),
    EngineerValidationCase(2022, "British Grand Prix", "1"),
    EngineerValidationCase(2022, "British Grand Prix", "6"),
    EngineerValidationCase(2023, "Canadian Grand Prix", "18"),
    EngineerValidationCase(2023, "Canadian Grand Prix", "23"),
    EngineerValidationCase(2023, "Canadian Grand Prix", "1"),
    EngineerValidationCase(2023, "Dutch Grand Prix", "1"),
    EngineerValidationCase(2023, "Dutch Grand Prix", "4"),
    EngineerValidationCase(2023, "Dutch Grand Prix", "14"),
    EngineerValidationCase(2024, "British Grand Prix", "44"),
    EngineerValidationCase(2024, "British Grand Prix", "4"),
    EngineerValidationCase(2024, "British Grand Prix", "3"),
    EngineerValidationCase(2024, "São Paulo Grand Prix", "1"),
    EngineerValidationCase(2024, "São Paulo Grand Prix", "22"),
    EngineerValidationCase(2024, "São Paulo Grand Prix", "77"),
    EngineerValidationCase(2025, "British Grand Prix", "4"),
    EngineerValidationCase(2025, "British Grand Prix", "31"),
)


def run_engineer_validation_sweep(
    db: Session,
    *,
    simulation_count: int = 100,
    random_seed: int = 42,
    cases: tuple[EngineerValidationCase, ...] = DEFAULT_ENGINEER_CASES,
) -> dict[str, Any]:
    """Exercise real Engineer Mode service calls and enforce cross-race invariants."""
    started = perf_counter()
    reports: list[dict[str, Any]] = []
    failures: list[str] = []
    service = StrategyService(db)

    for case_index, case in enumerate(cases):
        resolved = _resolve_case(db, case)
        if resolved is None:
            failures.append(f"{_label(case)}: race or driver is unavailable")
            continue
        session, event, entry, driver, control_lap = resolved
        payload = StrategyCompareRequest(
            session_id=session.id,
            driver_id=driver.id,
            control_lap=control_lap,
            simulation_count=simulation_count,
            random_seed=random_seed,
            strategies=[
                StrategyCandidate(name="Stay out"),
                StrategyCandidate(name="Box Hard", pit_lap=control_lap, next_compound="HARD"),
                StrategyCandidate(
                    name="Box Intermediate",
                    pit_lap=control_lap,
                    next_compound="INTERMEDIATE",
                ),
                StrategyCandidate(name="Box Wet", pit_lap=control_lap, next_compound="WET"),
            ],
        )
        case_started = perf_counter()
        try:
            response = service.compare(payload)
            case_failures = _validate_response(response, len(response.outcomes))
            if case_index in {0, 6, 12, 15, 18}:
                repeated = service.compare(payload)
                if _canonical_outcomes(response) != _canonical_outcomes(repeated):
                    case_failures.append("same seed/request changed aggregate or projection output")
            failures.extend(f"{_label(case)}: {failure}" for failure in case_failures)
            reports.append(
                {
                    "year": case.year,
                    "event": case.event,
                    "session_id": session.id,
                    "driver_number": case.driver_number,
                    "driver": entry.abbreviation or driver.abbreviation,
                    "control_lap": control_lap,
                    "actual_finish": entry.finishing_position,
                    "actual_status": entry.status,
                    "comparison_id": response.comparison_id,
                    "calculation_ms": response.calculation_time_ms,
                    "service_ms": round((perf_counter() - case_started) * 1000, 1),
                    "outcomes": [
                        {
                            "name": outcome.name,
                            "finish": outcome.predicted_finish,
                            "final_age": outcome.final_tyre_age,
                            "dnf": outcome.dnf,
                            "projected_laps": len(outcome.projected_laps),
                            "median_finish": (
                                outcome.monte_carlo.median_predicted_finish
                                if outcome.monte_carlo
                                else None
                            ),
                        }
                        for outcome in response.outcomes
                    ],
                    "failures": case_failures,
                }
            )
        except Exception as exc:
            db.rollback()
            failures.append(f"{_label(case)}: service exception: {exc}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "simulation_count": simulation_count,
        "random_seed": random_seed,
        "case_count": len(cases),
        "race_count": len({(case.year, case.event) for case in cases}),
        "driver_count": len(reports),
        "strategy_outcome_count": sum(len(report["outcomes"]) for report in reports),
        "reproducibility_repeats": 5,
        "elapsed_seconds": round(perf_counter() - started, 2),
        "failures": failures,
        "cases": reports,
    }


def _resolve_case(
    db: Session, case: EngineerValidationCase
) -> tuple[RaceSession, Event, RaceEntry, Driver, int] | None:
    row = db.execute(
        select(RaceSession, Event, RaceEntry, Driver)
        .join(Event, Event.id == RaceSession.event_id)
        .join(Season, Season.id == Event.season_id)
        .join(RaceEntry, RaceEntry.session_id == RaceSession.id)
        .join(Driver, Driver.id == RaceEntry.driver_id)
        .where(
            Season.year == case.year,
            Event.event_name == case.event,
            RaceSession.session_type == "RACE",
            RaceSession.ingestion_status == "complete",
            Driver.driver_number == case.driver_number,
        )
    ).first()
    if row is None:
        return None
    session, event, entry, driver = row
    final_lap = db.scalar(
        select(func.max(Lap.lap_number)).where(
            Lap.session_id == session.id,
            Lap.driver_id == driver.id,
        )
    )
    if final_lap is None or final_lap < 2:
        return None
    nominal = max(1, round((event.total_laps or final_lap) * 0.35))
    control_lap = min(nominal, final_lap - 1, max((event.total_laps or final_lap) - 1, 1))
    return session, event, entry, driver, control_lap


def _validate_response(response: Any, expected_outcomes: int) -> list[str]:
    failures: list[str] = []
    if len(response.outcomes) != expected_outcomes:
        failures.append(f"returned {len(response.outcomes)} outcomes, expected {expected_outcomes}")
    for outcome in response.outcomes:
        prefix = outcome.name
        aggregate = outcome.monte_carlo
        if aggregate is None:
            failures.append(f"{prefix}: Monte Carlo aggregate missing")
        else:
            if not (
                0
                <= aggregate.win_probability
                <= aggregate.podium_probability
                <= aggregate.points_probability
                <= 1
            ):
                failures.append(f"{prefix}: probability hierarchy is invalid")
            probability_sum = sum(
                bucket.probability for bucket in aggregate.finish_position_distribution
            )
            if abs(probability_sum - 1) > 0.011:
                failures.append(f"{prefix}: finish distribution sums to {probability_sum:.4f}")
            if not (
                aggregate.race_time_p05_ms
                <= aggregate.race_time_p25_ms
                <= aggregate.median_total_time_ms
                <= aggregate.race_time_p75_ms
                <= aggregate.race_time_p95_ms
            ):
                failures.append(f"{prefix}: race-time percentiles are unordered")

        projected = outcome.projected_laps
        if not projected:
            failures.append(f"{prefix}: no projected continuation")
            continue
        for previous, current in zip(projected, projected[1:], strict=False):
            if current.lap_number != previous.lap_number + 1:
                failures.append(f"{prefix}: projected lap numbers are discontinuous")
                break
            if current.cumulative_time_ms <= previous.cumulative_time_ms and not current.dnf:
                failures.append(f"{prefix}: elapsed time did not increase")
                break
            if current.compound == previous.compound and not current.pit_stop:
                if current.tyre_age != previous.tyre_age + 1:
                    failures.append(f"{prefix}: tyre age did not increase by one")
                    break
                if current.tyre_health_percent > previous.tyre_health_percent:
                    failures.append(f"{prefix}: tyre health recovered without a pit stop")
                    break
        if any(not lap.dnf and not 50_000 <= lap.lap_time_ms <= 360_000 for lap in projected):
            failures.append(f"{prefix}: projected lap time is outside feasibility bounds")
        if any(not 1 <= lap.predicted_position <= 20 for lap in projected):
            failures.append(f"{prefix}: projected position is outside the F1 field")
        if any(not 0 <= lap.tyre_health_percent <= 100 for lap in projected):
            failures.append(f"{prefix}: tyre health is outside modeled bounds")
        pit_laps = [lap for lap in projected if lap.pit_stop]
        if outcome.pit_lap is None and pit_laps:
            failures.append(f"{prefix}: stay out outcome inherited a historical pit")
        if outcome.pit_lap is not None:
            if len(pit_laps) != 1:
                failures.append(f"{prefix}: expected exactly one requested pit stop")
            elif pit_laps[0].tyre_age != 1 or pit_laps[0].tyre_health_percent != 100:
                failures.append(f"{prefix}: new tyre did not reset to age 1 and 100%")
        if outcome.dnf and (not projected[-1].dnf or projected[-1].status is None):
            failures.append(f"{prefix}: DNF outcome lacks a terminal projected event")
        if outcome.dnf and projected[-1].tyre_health_percent >= 5:
            failures.append(f"{prefix}: tyre DNF occurred without health crossing below 5%")
        if not outcome.dnf and any(lap.tyre_health_percent < 5 for lap in projected):
            failures.append(f"{prefix}: a car survived below the hard 5% threshold")
    return failures


def _canonical_outcomes(response: Any) -> list[dict[str, Any]]:
    return [outcome.model_dump(mode="json") for outcome in response.outcomes]


def _label(case: EngineerValidationCase) -> str:
    return f"{case.year} {case.event} #{case.driver_number}"
