from datetime import date

import numpy as np
from app.db.models import (
    Driver,
    Event,
    Lap,
    PitStop,
    RaceControlMessage,
    RaceEntry,
    RaceSession,
    Season,
    WeatherSample,
)
from app.repositories.race import RaceRepository
from app.schemas.race_state import PitLossEstimate
from app.simulation.calibration import UncertaintyCalibrator
from app.simulation.deterministic import DeterministicStrategyEngine
from app.simulation.distributions import sample_degradation_slopes, sample_pit_losses
from app.simulation.interventions import InterventionKind, InterventionScenarioSampler
from app.simulation.pit_loss import GLOBAL_PIT_LOSS_MS, PitLossEstimator
from app.simulation.tyres import TyreDegradationEstimator
from app.simulation.weather import TrackCondition, TyreWeatherModel
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session


def seed_race(db: Session) -> tuple[int, int]:
    season = Season(year=2025)
    db.add(season)
    db.flush()
    event = Event(
        season_id=season.id,
        round_number=1,
        event_name="Baseline Grand Prix",
        location="Test Circuit",
        event_date=date(2025, 3, 1),
        total_laps=15,
        metadata_json={},
    )
    db.add(event)
    db.flush()
    race = RaceSession(event_id=event.id, session_type="RACE", ingestion_status="complete")
    db.add(race)
    db.flush()

    drivers = []
    for index, abbreviation in enumerate(("AAA", "BBB", "CCC", "DDD"), start=1):
        driver = Driver(
            driver_number=str(index),
            abbreviation=abbreviation,
            full_name=f"Driver {abbreviation}",
            team_name=f"Team {index}",
        )
        db.add(driver)
        db.flush()
        drivers.append(driver)
        db.add(
            RaceEntry(
                session_id=race.id,
                driver_id=driver.id,
                team_name=f"Race Team {index}",
                grid_position=index,
                finishing_position=index,
                status="Finished",
                points=max(0, 26 - index * 3),
            )
        )
        for lap_number in range(1, 16):
            hard_stint = lap_number > 7
            tyre_age = lap_number - 7 if hard_stint else lap_number
            lap_time = 90_000 + index * 250 + tyre_age * (45 if hard_stint else 70)
            db.add(
                Lap(
                    session_id=race.id,
                    driver_id=driver.id,
                    lap_number=lap_number,
                    position=index,
                    lap_time_ms=lap_time,
                    compound="HARD" if hard_stint else "MEDIUM",
                    tyre_life=float(tyre_age),
                    stint_number=2 if hard_stint else 1,
                    pit_in=lap_number == 7,
                    pit_out=lap_number == 8,
                    track_status="1",
                    deleted=False,
                    inaccurate=False,
                    timestamp_ms=lap_number * 90_000 + index * 2_000,
                )
            )
        db.add(
            PitStop(
                session_id=race.id,
                driver_id=driver.id,
                lap_number=7,
                pit_entry_time_ms=620_000 + index * 2_000,
                pit_exit_time_ms=640_000 + index * 2_000,
                pit_duration_ms=20_000 + index * 100,
            )
        )

    db.add(
        WeatherSample(
            session_id=race.id,
            timestamp_ms=400_000,
            air_temperature=24,
            track_temperature=35,
            humidity=50,
            rainfall=False,
            wind_speed=2,
        )
    )
    db.add(
        RaceControlMessage(
            session_id=race.id,
            timestamp_ms=350_000,
            lap_number=4,
            category="Flag",
            flag="GREEN",
            scope="Track",
            message="TRACK CLEAR",
        )
    )
    db.commit()
    return race.id, drivers[1].id


def comparison_payload(session_id: int, driver_id: int) -> dict[str, object]:
    return {
        "session_id": session_id,
        "driver_id": driver_id,
        "control_lap": 5,
        "strategies": [
            {
                "name": "Pit now",
                "pit_lap": 5,
                "next_compound": "HARD",
                "pace_mode": "BALANCED",
            },
            {
                "name": "Wait two laps",
                "pit_lap": 7,
                "next_compound": "MEDIUM",
                "pace_mode": "BALANCED",
            },
            {
                "name": "Stay out",
                "pit_lap": None,
                "next_compound": None,
                "pace_mode": "CONSERVATIVE",
            },
        ],
    }


def test_race_state_reconstructs_order_weather_gaps_and_pit_loss(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    response = client.get(f"/api/v1/sessions/{session_id}/race-state?lap=5&driver_id={driver_id}")

    assert response.status_code == 200
    state = response.json()
    assert state["selected_driver"]["position"] == 2
    assert state["selected_driver"]["recent_pace_sample_count"] == 3
    assert state["selected_driver"]["timestamp_ms"] == 454_000
    assert state["running_order"][1]["timestamp_ms"] == 454_000
    assert 0 < state["selected_driver"]["tyre_health_percent"] < 100
    assert state["selected_driver"]["tyre_performance_life_laps"] > 0
    assert (
        state["selected_driver"]["tyre_durability_laps"]
        > state["selected_driver"]["tyre_performance_life_laps"]
    )
    assert state["selected_driver"]["tyre_stint_sample_count"] > 0
    assert [item["position"] for item in state["running_order"]] == [1, 2, 3, 4]
    assert state["running_order"][1]["gap_to_leader_ms"] == 2_000
    assert state["running_order"][1]["team_name"] == "Race Team 2"
    assert state["weather"]["rainfall"] is False
    assert state["race_control"]["status_label"] == "GREEN"
    assert state["pit_loss"]["source"] == "current_session"
    assert state["pit_loss"]["sample_count"] == 4


def test_timeline_and_actual_strategy(client: TestClient, db: Session) -> None:
    session_id, driver_id = seed_race(db)
    timeline = client.get(f"/api/v1/sessions/{session_id}/timeline?driver_id={driver_id}").json()
    actual = client.get(
        f"/api/v1/sessions/{session_id}/actual-strategy/{driver_id}?control_lap=5"
    ).json()

    assert [
        (stint["compound"], stint["start_lap"], stint["end_lap"]) for stint in timeline["stints"]
    ] == [
        ("MEDIUM", 1, 7),
        ("HARD", 8, 15),
    ]
    assert actual["remaining_stops"][0]["pit_lap"] == 7
    assert actual["remaining_stops"][0]["next_compound"] == "HARD"


def test_final_lap_race_state_returns_classification(client: TestClient, db: Session) -> None:
    session_id, driver_id = seed_race(db)

    response = client.get(f"/api/v1/sessions/{session_id}/race-state?lap=15&driver_id={driver_id}")

    assert response.status_code == 200
    assert response.json()["control_lap"] == 15
    assert response.json()["selected_driver"]["position"] == 2


def test_exact_timing_crossover_resolves_as_an_overtake(db: Session) -> None:
    session_id, driver_id = seed_race(db)
    repo = RaceRepository(db)
    entries = [entry for entry, _ in repo.entries(session_id)]
    engine = DeterministicStrategyEngine(
        repo.session_laps(session_id),
        entries,
        driver_id,
        5,
        15,
        PitLossEstimator(repo).estimate(session_id),
    )

    # Driver AAA's recorded lap-six timestamp is exactly 542 seconds. A tie at
    # the timing line is treated as the pass being completed, never as P1 +0.000s.
    assert engine._position_at_lap(6, 542_000) == 2


def test_race_state_reports_active_vsc_pit_activity(client: TestClient, db: Session) -> None:
    session_id, driver_id = seed_race(db)
    selected_intervention_laps = (
        db.query(Lap)
        .filter(
            Lap.session_id == session_id,
            Lap.driver_id == driver_id,
            Lap.lap_number.in_([4, 5]),
        )
        .all()
    )
    for lap in selected_intervention_laps:
        lap.track_status = "6"
    boxed_lap = (
        db.query(Lap)
        .filter(
            Lap.session_id == session_id,
            Lap.driver_id != driver_id,
            Lap.lap_number == 5,
        )
        .first()
    )
    assert boxed_lap is not None
    boxed_lap.pit_in = True
    db.commit()

    response = client.get(f"/api/v1/sessions/{session_id}/race-state?lap=5&driver_id={driver_id}")

    assert response.status_code == 200
    state = response.json()
    assert state["race_control"]["status_label"] == "VSC"
    assert state["race_control"]["intervention_start_lap"] == 4
    assert state["race_control"]["boxed_driver_ids"] == [boxed_lap.driver_id]
    boxed_row = next(
        row for row in state["running_order"] if row["driver_id"] == boxed_lap.driver_id
    )
    assert boxed_row["in_pit"] is True


def test_monte_carlo_comparison_is_reproducible_and_persisted(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    first = client.post(
        "/api/v1/simulations/compare", json=comparison_payload(session_id, driver_id)
    )
    second = client.post(
        "/api/v1/simulations/compare", json=comparison_payload(session_id, driver_id)
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["deterministic"] is False
    assert first.json()["engine_version"] == "monte-carlo-v2"
    assert first.json()["outcomes"] == second.json()["outcomes"]
    assert first.json()["simulation_count"] == 1000
    assert first.json()["random_seed"] == 42
    assert first.json()["outcomes"][0]["predicted_finish"] >= 1
    assert first.json()["outcomes"][0]["monte_carlo"] is not None
    for outcome in first.json()["outcomes"]:
        aggregate = outcome["monte_carlo"]
        assert aggregate is not None
        observed_delta = aggregate["expected_total_time_ms"] - outcome["predicted_total_time_ms"]
        assert abs(observed_delta - aggregate["mean_time_vs_deterministic_baseline_ms"]) <= 100
    projection = first.json()["outcomes"][0]["projected_laps"]
    assert len(projection) == 10
    assert projection[0]["lap_number"] == 6
    assert projection[0]["pit_stop"] is True
    assert projection[0]["tyre_health_percent"] == 100
    assert all(1 <= lap["predicted_position"] <= 4 for lap in projection)
    comparison_id = first.json()["comparison_id"]
    saved = client.get(f"/api/v1/simulations/{comparison_id}")
    assert saved.status_code == 200
    assert saved.json()["recommendation"] == first.json()["recommendation"]
    assert saved.json()["outcomes"] == first.json()["outcomes"]


def test_strategy_validation_rejects_impossible_pit_lap(client: TestClient, db: Session) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload["strategies"][0]["pit_lap"] = 15  # type: ignore[index]
    response = client.post("/api/v1/simulations/compare", json=payload)
    assert response.status_code == 422
    assert "Pit lap must be" in response.json()["detail"]


def test_interactive_simulation_continues_from_prior_counterfactual_state(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload["control_lap"] = 6
    payload["strategies"] = [
        {
            "name": "Stay out",
            "pit_lap": None,
            "next_compound": None,
            "pace_mode": "BALANCED",
        },
        {
            "name": "Box hard",
            "pit_lap": 6,
            "next_compound": "HARD",
            "pace_mode": "BALANCED",
        },
    ]
    payload["simulation_context"] = {
        "current_compound": "INTERMEDIATE",
        "current_tyre_age": 3,
        "current_position": 3,
        "cumulative_time_delta_ms": 5_000,
    }

    response = client.post("/api/v1/simulations/compare", json=payload)

    assert response.status_code == 200
    projection = response.json()["outcomes"][0]["projected_laps"]
    assert projection[0]["compound"] == "INTERMEDIATE"
    assert projection[0]["tyre_age"] == 4
    assert projection[0]["historical_time_ms"] == 634_000
    assert projection[0]["cumulative_time_ms"] != projection[0]["historical_time_ms"]


def test_chequered_flag_stops_lapped_player_and_classifies_by_completed_laps(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    lapped_driver = db.query(Driver).filter(Driver.abbreviation == "DDD").one()
    lapped_final = (
        db.query(Lap)
        .filter(
            Lap.session_id == session_id,
            Lap.driver_id == lapped_driver.id,
            Lap.lap_number == 15,
        )
        .one()
    )
    db.delete(lapped_final)
    lapped_lap_14 = (
        db.query(Lap)
        .filter(
            Lap.session_id == session_id,
            Lap.driver_id == lapped_driver.id,
            Lap.lap_number == 14,
        )
        .one()
    )
    lapped_lap_14.timestamp_ms = 1_360_000
    db.commit()

    payload = comparison_payload(session_id, driver_id)
    payload["control_lap"] = 13
    payload["simulation_count"] = 100
    payload["strategies"] = [
        {
            "name": "Stay out",
            "pit_lap": None,
            "next_compound": None,
            "pace_mode": "BALANCED",
        },
        {
            "name": "Box hard",
            "pit_lap": 13,
            "next_compound": "HARD",
            "pace_mode": "BALANCED",
        },
    ]
    payload["simulation_context"] = {
        "current_compound": "HARD",
        "current_tyre_age": 6,
        "current_position": 4,
        "current_stint_number": 2,
        "current_completed_laps": 13,
        "current_timestamp_ms": 1_300_000,
        "cumulative_time_delta_ms": 126_000,
    }

    response = client.post("/api/v1/simulations/compare", json=payload)

    assert response.status_code == 200
    stay_out = response.json()["outcomes"][0]
    assert stay_out["projected_laps"][-1]["lap_number"] == 14
    assert stay_out["projected_laps"][-1]["status"] == "CHEQUERED"
    assert stay_out["projected_laps"][-1]["stint_number"] == 2
    assert stay_out["predicted_finish"] == 4
    assert stay_out["monte_carlo"]["finish_position_distribution"] == [
        {"position": 4, "count": 100, "probability": 1.0}
    ]
    assert response.json()["outcomes"][1]["projected_laps"][0]["stint_number"] == 3


def test_long_soft_stint_loses_pace_and_health(client: TestClient, db: Session) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload["strategies"] = [
        {
            "name": "Stay on old soft",
            "pit_lap": None,
            "next_compound": None,
            "pace_mode": "BALANCED",
        },
        {
            "name": "Box hard",
            "pit_lap": 5,
            "next_compound": "HARD",
            "pace_mode": "BALANCED",
        },
    ]
    payload["simulation_context"] = {
        "current_compound": "SOFT",
        "current_tyre_age": 25,
        "current_position": 2,
        "cumulative_time_delta_ms": 0,
    }

    response = client.post("/api/v1/simulations/compare", json=payload)

    assert response.status_code == 200
    outcome = response.json()["outcomes"][0]
    projection = outcome["projected_laps"]
    assert all(lap["compound"] == "SOFT" for lap in projection)
    completed = [lap for lap in projection if lap["lap_completed"]]
    assert completed[-1]["lap_time_ms"] > completed[0]["lap_time_ms"]
    lap_time_steps = [
        right["lap_time_ms"] - left["lap_time_ms"]
        for left, right in zip(completed, completed[1:], strict=False)
    ]
    assert max(lap_time_steps) < 10_000
    assert lap_time_steps[-1] > lap_time_steps[0]
    assert len(set(lap_time_steps)) > 1
    assert projection[-1]["tyre_health_percent"] < projection[0]["tyre_health_percent"]
    assert projection[-1]["dnf"] is True
    assert projection[-1]["status"] == "TYRE FAILURE"
    assert projection[-1]["retirement_reason"] == "TYRE_FAILURE"
    assert projection[-1]["lap_completed"] is False
    assert [lap["dnf"] for lap in projection].count(True) == 1
    assert outcome["dnf"] is True
    assert outcome["predicted_finish"] == 4
    assert outcome["time_vs_actual_ms"] > 0
    assert outcome["monte_carlo"]["points_probability"] == 0


def test_sixty_percent_health_can_make_a_pit_stop_economically_rational(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload["control_lap"] = 1
    payload["strategies"] = [
        {
            "name": "Stay on degraded soft",
            "pit_lap": None,
            "next_compound": None,
            "pace_mode": "BALANCED",
        },
        {
            "name": "Box hard on economics",
            "pit_lap": 1,
            "next_compound": "HARD",
            "pace_mode": "BALANCED",
        },
    ]
    payload["simulation_context"] = {
        "current_compound": "SOFT",
        "current_tyre_age": 18,
        "current_effective_tyre_age": 18,
        "current_tyre_health_pct": 60,
        "current_position": 2,
        "current_completed_laps": 1,
        "cumulative_time_delta_ms": 0,
    }

    response = client.post("/api/v1/simulations/compare", json=payload)

    assert response.status_code == 200
    stay_out, pit = response.json()["outcomes"]
    assert stay_out["current_tyre_pace_loss_seconds"] > 4.0
    assert pit["pit_loss_ms"] > 0
    assert pit["predicted_total_time_ms"] < stay_out["predicted_total_time_ms"]


def test_explainable_fallbacks_are_explicit(db: Session) -> None:
    repo = RaceRepository(db)
    assert PitLossEstimator(repo)._result([20_000, 21_000, 22_000], "test").estimated_ms == 21_000
    tyre = TyreDegradationEstimator([]).estimate("SOFT")
    assert tyre.source == "compound_fallback"
    assert tyre.sample_count == 0
    assert GLOBAL_PIT_LOSS_MS == 23_000


def test_simple_tyre_weather_compatibility_rules() -> None:
    wet_on_dry = TyreWeatherModel.effect("WET", TrackCondition.DRY)
    dry_on_wet = TyreWeatherModel.effect("SOFT", TrackCondition.WET)
    wet_on_wet = TyreWeatherModel.effect("WET", TrackCondition.WET)

    assert wet_on_dry.pace_penalty_ms == 8_000
    assert wet_on_dry.wear_multiplier > 2
    assert dry_on_wet.pace_penalty_ms == 12_000
    assert dry_on_wet.unsafe is True
    assert wet_on_wet.pace_penalty_ms == 0
    assert wet_on_wet.wear_multiplier == 1


def test_intermediate_and_wet_strategies_use_labelled_fallbacks(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload["strategies"][0]["next_compound"] = "INTERMEDIATE"  # type: ignore[index]
    payload["strategies"][1]["next_compound"] = "WET"  # type: ignore[index]

    response = client.post("/api/v1/simulations/compare", json=payload)

    assert response.status_code == 200
    assert {"INTERMEDIATE", "WET"}.issubset(response.json()["available_compounds"])
    assert response.json()["outcomes"][0]["tyre_estimate"]["source"] == "compound_fallback"
    assert response.json()["outcomes"][1]["tyre_estimate"]["source"] == "compound_fallback"


def test_full_wet_is_much_slower_than_hard_on_recorded_dry_track(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload["strategies"] = [
        {
            "name": "Wrong full wet",
            "pit_lap": 5,
            "next_compound": "WET",
            "pace_mode": "BALANCED",
        },
        {
            "name": "Correct hard",
            "pit_lap": 5,
            "next_compound": "HARD",
            "pace_mode": "BALANCED",
        },
    ]

    response = client.post("/api/v1/simulations/compare", json=payload)

    assert response.status_code == 200
    wet_projection = response.json()["outcomes"][0]["projected_laps"]
    hard_projection = response.json()["outcomes"][1]["projected_laps"]
    wet_lap = wet_projection[0]
    hard_lap = hard_projection[0]
    assert wet_lap["lap_time_ms"] - hard_lap["lap_time_ms"] >= 7_000
    assert wet_lap["tyre_health_percent"] == hard_lap["tyre_health_percent"] == 100
    assert wet_projection[1]["tyre_health_percent"] < hard_projection[1]["tyre_health_percent"]


def test_monte_carlo_probabilities_percentiles_and_distributions(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload.update(simulation_count=500, random_seed=7)
    response = client.post("/api/v1/simulations/compare", json=payload)

    assert response.status_code == 200
    for outcome in response.json()["outcomes"]:
        aggregate = outcome["monte_carlo"]
        assert 0 <= aggregate["win_probability"] <= 1
        assert aggregate["podium_probability"] >= aggregate["win_probability"]
        assert aggregate["points_probability"] >= aggregate["podium_probability"]
        assert aggregate["race_time_p05_ms"] <= aggregate["race_time_p25_ms"]
        assert aggregate["race_time_p25_ms"] <= aggregate["median_total_time_ms"]
        assert aggregate["median_total_time_ms"] <= aggregate["race_time_p75_ms"]
        assert aggregate["race_time_p75_ms"] <= aggregate["race_time_p95_ms"]
        assert aggregate["finish_position_p05"] <= aggregate["finish_position_p95"]
        probability_sum = sum(
            bucket["probability"] for bucket in aggregate["finish_position_distribution"]
        )
        assert abs(probability_sum - 1) < 0.01
        assert sum(bucket["count"] for bucket in aggregate["finish_position_distribution"]) == 500


def test_different_seed_changes_aggregate_output(client: TestClient, db: Session) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload.update(simulation_count=500, random_seed=1)
    first = client.post("/api/v1/simulations/compare", json=payload).json()
    payload["random_seed"] = 2
    second = client.post("/api/v1/simulations/compare", json=payload).json()

    assert first["outcomes"][0]["monte_carlo"] != second["outcomes"][0]["monte_carlo"]


def test_candidate_order_does_not_change_strategy_samples(client: TestClient, db: Session) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload.update(simulation_count=500, random_seed=99)
    first = client.post("/api/v1/simulations/compare", json=payload).json()
    payload["strategies"] = list(reversed(payload["strategies"]))  # type: ignore[arg-type]
    second = client.post("/api/v1/simulations/compare", json=payload).json()

    first_by_name = {item["name"]: item["monte_carlo"] for item in first["outcomes"]}
    second_by_name = {item["name"]: item["monte_carlo"] for item in second["outcomes"]}
    assert first_by_name == second_by_name


def test_simulation_count_validation(client: TestClient, db: Session) -> None:
    session_id, driver_id = seed_race(db)
    payload = comparison_payload(session_id, driver_id)
    payload["simulation_count"] = 99
    assert client.post("/api/v1/simulations/compare", json=payload).status_code == 422
    payload["simulation_count"] = 10_001
    assert client.post("/api/v1/simulations/compare", json=payload).status_code == 422


def test_sampled_pit_loss_and_degradation_are_bounded() -> None:
    rng = np.random.default_rng(42)
    pit = sample_pit_losses(rng, 1000, 23_000, 4_000, np.asarray([]))
    degradation = sample_degradation_slopes(rng, 1000, 75, 45)
    assert np.all((pit >= 10_000) & (pit <= 60_000))
    assert np.all((degradation >= 10) & (degradation <= 250))


def test_tyre_life_uses_field_stints_instead_of_single_max_age(
    db: Session,
) -> None:
    session_id, _ = seed_race(db)
    estimator = TyreDegradationEstimator(RaceRepository(db).session_laps(session_id))
    life = estimator.life_estimate("MEDIUM")

    assert estimator.supported_age("MEDIUM") == (26, "event_field_stint_model")
    assert life.stint_sample_count == 4
    assert life.completed_stint_count == 4
    assert life.durability_laps > life.performance_life_laps


def test_field_stint_model_keeps_observed_survival_but_rejects_unbounded_hard_life() -> None:
    laps: list[Lap] = []
    stint_ends = [30, 34, 38, 42, 58]
    for driver_id, end_age in enumerate(stint_ends, start=1):
        for age in range(1, end_age + 1):
            laps.append(
                Lap(
                    session_id=1,
                    driver_id=driver_id,
                    lap_number=age,
                    position=driver_id,
                    lap_time_ms=80_000 + driver_id * 100 + age * 45,
                    compound="HARD",
                    tyre_life=float(age),
                    stint_number=1,
                    pit_in=age == end_age,
                    pit_out=False,
                    track_status="1",
                    deleted=False,
                    inaccurate=False,
                    timestamp_ms=age * 80_000 + driver_id * 100,
                )
            )
        # A subsequent stint proves the Hard was changed instead of merely being
        # right-censored by the chequered flag.
        laps.append(
            Lap(
                session_id=1,
                driver_id=driver_id,
                lap_number=end_age + 1,
                position=driver_id,
                lap_time_ms=81_000,
                compound="MEDIUM",
                tyre_life=1.0,
                stint_number=2,
                pit_in=False,
                pit_out=True,
                track_status="1",
                deleted=False,
                inaccurate=False,
                timestamp_ms=(end_age + 1) * 80_000 + driver_id * 100,
            )
        )

    estimator = TyreDegradationEstimator(laps)
    estimate = estimator.estimate("HARD")

    assert estimate.life_source == "event_field_stint_model"
    assert estimate.stint_sample_count == 5
    assert 35 <= estimate.performance_life_laps <= 45
    assert estimate.durability_laps == 61
    assert estimator.health_percent("HARD", 10) > estimator.health_percent("HARD", 30)
    assert 30 < estimator.health_percent("HARD", 50) < 60
    assert estimator.health_percent("HARD", 58) > 5
    assert estimator.health_percent("HARD", 61) == 5
    assert estimator.health_percent("HARD", 62) < 5


def test_missing_uncertainty_data_uses_labelled_fallbacks() -> None:
    calibration = UncertaintyCalibrator(
        [],
        [],
        driver_id=1,
        control_lap=5,
        pit_loss=PitLossEstimate(
            estimated_ms=23_000,
            sample_count=0,
            source="global_fallback",
            uncertainty_ms=4_000,
        ),
        pit_loss_samples=[],
    ).calibrate()
    assert calibration.data_quality == "LOW"
    assert calibration.sources[0].source == "global_fallback"
    assert calibration.sources[0].fallback is True


def test_retired_competitor_is_handled_without_new_dnf_claims(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    retired_entry, _ = RaceRepository(db).entries(session_id)[-1]
    retired_entry.status = "Retired"
    retired_entry.finishing_position = 4
    db.execute(
        delete(Lap).where(
            Lap.session_id == session_id,
            Lap.driver_id == retired_entry.driver_id,
            Lap.lap_number > 8,
        )
    )
    db.commit()
    payload = comparison_payload(session_id, driver_id)
    payload.update(simulation_count=1000, random_seed=42)
    response = client.post("/api/v1/simulations/compare", json=payload)
    assert response.status_code == 200
    assert all(outcome["monte_carlo"] for outcome in response.json()["outcomes"])
    assert any("No new mechanical failure" in item for item in response.json()["assumptions"])


def test_intervention_sampler_is_explicitly_disabled_by_default() -> None:
    samples = InterventionScenarioSampler().sample(100, np.random.default_rng(42))

    assert set(samples.kinds) == {InterventionKind.NONE.value}
    assert np.all(samples.pit_loss_adjustment_ms == 0)


def test_explicit_scenario_adjustments_change_the_simulation_inputs(
    client: TestClient, db: Session
) -> None:
    session_id, driver_id = seed_race(db)
    baseline_payload = comparison_payload(session_id, driver_id)
    baseline_payload.update(simulation_count=500, random_seed=42)
    baseline = client.post("/api/v1/simulations/compare", json=baseline_payload).json()

    scenario_payload = comparison_payload(session_id, driver_id)
    scenario_payload.update(
        simulation_count=500,
        random_seed=42,
        scenario={"pit_loss_delta_ms": 3_000, "tyre_degradation_multiplier": 1.2},
    )
    scenario = client.post("/api/v1/simulations/compare", json=scenario_payload).json()

    assert scenario["pit_loss"]["estimated_ms"] == baseline["pit_loss"]["estimated_ms"] + 3_000
    assert (
        scenario["outcomes"][0]["predicted_total_time_ms"]
        != baseline["outcomes"][0]["predicted_total_time_ms"]
    )
    assert scenario["outcomes"][0]["assumptions"] != baseline["outcomes"][0]["assumptions"]
