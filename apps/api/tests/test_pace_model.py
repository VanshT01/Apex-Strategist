from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from app.db.models import Lap
from app.simulation.pace_model import (
    HistoricalPaceModel,
    PaceModelBundle,
    PaceModelMetrics,
    SessionPacePredictor,
    TrainingRow,
    _fit_bundle,
)


def test_historical_pace_model_learns_driver_and_nonlinear_tyre_shape() -> None:
    rows: list[TrainingRow] = []
    drivers = ["A", "B", "C", "D", "E", "F"]
    offsets = [-900, -500, -150, 150, 500, 900]
    for session_id in range(1, 13):
        for lap_number in range(2, 32):
            for driver, offset in zip(drivers, offsets, strict=True):
                compound = "HARD" if driver in {"A", "C", "E"} else "MEDIUM"
                age = ((lap_number + drivers.index(driver)) % 24) + 1
                tyre_loss = 1.5 * age**2 if compound == "HARD" else 2.4 * age**2
                rows.append(
                    TrainingRow(
                        session_id=session_id,
                        driver=driver,
                        circuit="Montreal",
                        compound=compound,
                        lap_number=lap_number,
                        total_laps=70,
                        tyre_age=age,
                        stint_number=2,
                        position=drivers.index(driver) + 1,
                        lap_time_ms=round(79_000 - 38 * lap_number + offset + tyre_loss),
                    )
                )

    bundle = _fit_bundle(rows, cutoff_session_id=99)
    model = HistoricalPaceModel(bundle)
    young = model.predict_delta_ms(
        driver="A",
        circuit="Montreal",
        compound="HARD",
        tyre_age=3,
        lap_number=35,
        total_laps=70,
        position=1,
        stint_number=2,
    )
    old = model.predict_delta_ms(
        driver="A",
        circuit="Montreal",
        compound="HARD",
        tyre_age=22,
        lap_number=54,
        total_laps=70,
        position=1,
        stint_number=2,
    )

    assert bundle.metrics.validation_mae_ms < bundle.metrics.field_median_mae_ms
    assert not np.isclose(old - young, 20 * (22 - 3), atol=5)


@dataclass
class _CurvedEstimator:
    def predict(self, values: np.ndarray) -> np.ndarray:
        age = values[:, 3]
        return age**2 * 2


def test_session_predictor_excludes_selected_driver_future_from_field_anchor() -> None:
    bundle = PaceModelBundle(
        estimator=_CurvedEstimator(),  # type: ignore[arg-type]
        driver_codes={"STR": 0},
        circuit_codes={"Montreal": 0},
        metrics=PaceModelMetrics(3_000, 500, 400, 700, 10),
        cutoff_session_id=76,
    )
    laps = []
    for lap_number in range(1, 5):
        for driver_id in range(1, 7):
            laps.append(
                Lap(
                    session_id=76,
                    driver_id=driver_id,
                    lap_number=lap_number,
                    lap_time_ms=75_000 + lap_number * 100 + driver_id * 10,
                    compound="HARD",
                    tyre_life=float(lap_number),
                    stint_number=1,
                    position=driver_id,
                    pit_in=False,
                    pit_out=False,
                    deleted=False,
                    inaccurate=False,
                    track_status="1",
                )
            )
    selected_future = next(lap for lap in laps if lap.driver_id == 1 and lap.lap_number == 4)
    selected_future.lap_time_ms = 200_000
    predictor = SessionPacePredictor(
        HistoricalPaceModel(bundle),
        laps,
        driver_id=1,
        driver="STR",
        circuit="Montreal",
        total_laps=70,
        control_lap=2,
    )

    prediction = predictor.predict_lap_ms(
        lap_number=4,
        compound="HARD",
        tyre_age=4,
        position=1,
        stint_number=1,
    )

    assert prediction is not None
    assert prediction < 80_000
