from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from threading import Lock
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Driver, Event, Lap, ModelArtifact, RaceEntry, RaceSession, Season

MODEL_NAME = "historical-lap-pace"
MODEL_VERSION = "hgb-pace-v2"
MIN_TRAINING_ROWS = 2_000
COMPOUND_CODES = {
    "SOFT": 0,
    "MEDIUM": 1,
    "HARD": 2,
    "INTERMEDIATE": 3,
    "WET": 4,
}


@dataclass(frozen=True)
class PaceModelMetrics:
    training_rows: int
    validation_rows: int
    validation_mae_ms: float
    field_median_mae_ms: float
    prior_session_count: int

    def as_dict(self) -> dict[str, int | float]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class PaceModelBundle:
    estimator: HistGradientBoostingRegressor
    driver_codes: dict[str, int]
    circuit_codes: dict[str, int]
    metrics: PaceModelMetrics
    cutoff_session_id: int


@dataclass(frozen=True)
class TrainingRow:
    session_id: int
    driver: str
    circuit: str
    compound: str
    lap_number: int
    total_laps: int
    tyre_age: float
    stint_number: int
    position: int
    lap_time_ms: int


class HistoricalPaceModel:
    """Leakage-safe, CPU-friendly expected-pace model.

    The target is a clean driver's delta to the same-lap field median. The
    surrounding deterministic simulator remains responsible for pit loss,
    weather/compound safety, classification, and tyre failure rules.
    """

    def __init__(self, bundle: PaceModelBundle) -> None:
        self.bundle = bundle

    @property
    def source(self) -> str:
        metrics = self.bundle.metrics
        return (
            f"{MODEL_VERSION}; {metrics.training_rows} prior clean laps; "
            f"validation MAE {metrics.validation_mae_ms:.0f} ms"
        )

    def predict_delta_ms(
        self,
        *,
        driver: str,
        circuit: str,
        compound: str,
        tyre_age: float,
        lap_number: int,
        total_laps: int,
        position: int,
        stint_number: int,
    ) -> float:
        features = _features(
            [
                TrainingRow(
                    session_id=0,
                    driver=driver,
                    circuit=circuit,
                    compound=compound,
                    lap_number=lap_number,
                    total_laps=total_laps,
                    tyre_age=tyre_age,
                    stint_number=stint_number,
                    position=position,
                    lap_time_ms=0,
                )
            ],
            self.bundle.driver_codes,
            self.bundle.circuit_codes,
        )
        return float(np.clip(self.bundle.estimator.predict(features)[0], -5_000, 5_000))


class SessionPacePredictor:
    """Adapt a historical model to the selected race using completed laps only."""

    def __init__(
        self,
        model: HistoricalPaceModel,
        laps: list[Lap],
        driver_id: int,
        driver: str,
        circuit: str,
        total_laps: int,
        control_lap: int,
    ) -> None:
        self.model = model
        self.driver_id = driver_id
        self.driver = driver
        self.circuit = circuit
        self.total_laps = total_laps
        self.field_reference = _field_reference(laps, driver_id)
        self.local_offset_ms = self._completed_lap_offset(laps, control_lap)

    @property
    def source(self) -> str:
        return f"{self.model.source}; completed lap adaptation {self.local_offset_ms:+.0f} ms"

    def predict_lap_ms(
        self,
        *,
        lap_number: int,
        compound: str,
        tyre_age: float,
        position: int,
        stint_number: int,
    ) -> float | None:
        reference = self.field_reference.get(lap_number)
        if reference is None:
            return None
        delta = self.model.predict_delta_ms(
            driver=self.driver,
            circuit=self.circuit,
            compound=compound,
            tyre_age=tyre_age,
            lap_number=lap_number,
            total_laps=self.total_laps,
            position=position,
            stint_number=stint_number,
        )
        return float(reference + delta + self.local_offset_ms)

    def _completed_lap_offset(self, laps: list[Lap], control_lap: int) -> float:
        completed = [
            lap
            for lap in laps
            if lap.driver_id == self.driver_id
            and lap.lap_number <= control_lap
            and lap.lap_time_ms is not None
            and lap.tyre_life is not None
            and lap.compound in COMPOUND_CODES
            and not lap.pit_in
            and not lap.pit_out
            and not lap.deleted
            and not lap.inaccurate
            and lap.track_status in {None, "1", "2"}
            and lap.lap_number in self.field_reference
        ][-5:]
        residuals = []
        for lap in completed:
            expected_delta = self.model.predict_delta_ms(
                driver=self.driver,
                circuit=self.circuit,
                compound=lap.compound or "MEDIUM",
                tyre_age=float(lap.tyre_life or 1),
                lap_number=lap.lap_number,
                total_laps=self.total_laps,
                position=lap.position or 10,
                stint_number=lap.stint_number or 1,
            )
            residuals.append(
                float(lap.lap_time_ms) - self.field_reference[lap.lap_number] - expected_delta
            )
        return float(np.clip(median(residuals), -3_000, 3_000)) if residuals else 0.0


_artifact_lock = Lock()
_bundle_cache: dict[Path, PaceModelBundle] = {}


def build_session_pace_predictor(
    db: Session,
    *,
    session: RaceSession,
    event: Event,
    laps: list[Lap],
    driver_id: int,
    driver: Driver,
    driver_code: str | None = None,
    control_lap: int,
    model_path: Path,
) -> SessionPacePredictor | None:
    """Load or fit a model whose training cutoff precedes the selected race."""
    if session.session_date is None or not event.total_laps:
        return None
    artifact_path = model_path / f"{MODEL_VERSION}-before-session-{session.id}.joblib"
    with _artifact_lock:
        bundle = _load_bundle(artifact_path)
        if bundle is None:
            rows = _training_rows(db, session)
            if len(rows) < MIN_TRAINING_ROWS:
                return None
            bundle = _fit_bundle(rows, session.id)
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(bundle, artifact_path)
            _bundle_cache[artifact_path.resolve()] = bundle
            _register_artifact(db, bundle, artifact_path)
    return SessionPacePredictor(
        HistoricalPaceModel(bundle),
        laps,
        driver_id,
        driver_code or driver.abbreviation,
        event.location or event.circuit_name or event.event_name,
        event.total_laps,
        control_lap,
    )


def _load_bundle(path: Path) -> PaceModelBundle | None:
    cache_key = path.resolve()
    if cache_key in _bundle_cache:
        return _bundle_cache[cache_key]
    if not path.exists():
        return None
    loaded = joblib.load(path)
    if not isinstance(loaded, PaceModelBundle):
        return None
    _bundle_cache[cache_key] = loaded
    return loaded


def _training_rows(db: Session, cutoff: RaceSession) -> list[TrainingRow]:
    query = (
        select(
            Lap.session_id,
            func.coalesce(RaceEntry.abbreviation, Driver.abbreviation).label("abbreviation"),
            Event.location,
            Event.circuit_name,
            Event.event_name,
            Event.total_laps,
            Lap.lap_number,
            Lap.compound,
            Lap.tyre_life,
            Lap.stint_number,
            Lap.position,
            Lap.lap_time_ms,
        )
        .join(RaceSession, RaceSession.id == Lap.session_id)
        .join(Event, Event.id == RaceSession.event_id)
        .join(Season, Season.id == Event.season_id)
        .join(Driver, Driver.id == Lap.driver_id)
        .join(
            RaceEntry,
            (RaceEntry.session_id == Lap.session_id) & (RaceEntry.driver_id == Lap.driver_id),
        )
        .where(
            RaceSession.session_type == "RACE",
            RaceSession.ingestion_status == "complete",
            RaceSession.session_date < cutoff.session_date,
            Lap.lap_time_ms.is_not(None),
            Lap.tyre_life.is_not(None),
            Lap.compound.in_(COMPOUND_CODES),
            Lap.pit_in.is_(False),
            Lap.pit_out.is_(False),
            Lap.deleted.is_(False),
            Lap.inaccurate.is_(False),
            (Lap.track_status.is_(None) | Lap.track_status.in_(["1", "2"])),
        )
        .order_by(RaceSession.session_date, Lap.session_id, Lap.lap_number)
    )
    rows = []
    for item in db.execute(query):
        lap_time = int(item.lap_time_ms)
        total_laps = int(item.total_laps or 0)
        if not 55_000 <= lap_time <= 180_000 or total_laps <= 0:
            continue
        rows.append(
            TrainingRow(
                session_id=int(item.session_id),
                driver=str(item.abbreviation),
                circuit=str(item.location or item.circuit_name or item.event_name),
                compound=str(item.compound),
                lap_number=int(item.lap_number),
                total_laps=total_laps,
                tyre_age=float(item.tyre_life),
                stint_number=int(item.stint_number or 1),
                position=int(item.position or 10),
                lap_time_ms=lap_time,
            )
        )
    return rows


def _fit_bundle(rows: list[TrainingRow], cutoff_session_id: int) -> PaceModelBundle:
    driver_codes = {value: index for index, value in enumerate(sorted({r.driver for r in rows}))}
    circuit_codes = {value: index for index, value in enumerate(sorted({r.circuit for r in rows}))}
    field_medians = _training_field_medians(rows)
    usable = [row for row in rows if (row.session_id, row.lap_number) in field_medians]
    targets = np.asarray(
        [
            np.clip(
                row.lap_time_ms - field_medians[(row.session_id, row.lap_number)],
                -5_000,
                5_000,
            )
            for row in usable
        ],
        dtype=float,
    )
    sessions = list(dict.fromkeys(row.session_id for row in usable))
    split_index = max(1, round(len(sessions) * 0.8))
    train_sessions = set(sessions[:split_index])
    train_mask = np.asarray([row.session_id in train_sessions for row in usable])
    validation_mask = ~train_mask
    if not np.any(validation_mask):
        validation_mask = train_mask.copy()
    features = _features(usable, driver_codes, circuit_codes)
    estimator = _new_estimator()
    estimator.fit(features[train_mask], targets[train_mask])
    predictions = estimator.predict(features[validation_mask])
    validation_targets = targets[validation_mask]
    validation_mae = float(np.mean(np.abs(validation_targets - predictions)))
    baseline_mae = float(np.mean(np.abs(validation_targets)))
    estimator = _new_estimator()
    estimator.fit(features, targets)
    metrics = PaceModelMetrics(
        training_rows=len(usable),
        validation_rows=int(np.sum(validation_mask)),
        validation_mae_ms=round(validation_mae, 1),
        field_median_mae_ms=round(baseline_mae, 1),
        prior_session_count=len(sessions),
    )
    return PaceModelBundle(
        estimator=estimator,
        driver_codes=driver_codes,
        circuit_codes=circuit_codes,
        metrics=metrics,
        cutoff_session_id=cutoff_session_id,
    )


def _new_estimator() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="absolute_error",
        learning_rate=0.06,
        max_iter=140,
        max_leaf_nodes=31,
        max_depth=6,
        min_samples_leaf=30,
        l2_regularization=2.0,
        categorical_features=[0, 1, 2],
        random_state=42,
    )


def _features(
    rows: list[TrainingRow],
    driver_codes: dict[str, int],
    circuit_codes: dict[str, int],
) -> np.ndarray:
    return np.asarray(
        [
            [
                COMPOUND_CODES.get(row.compound, -1),
                driver_codes.get(row.driver, -1),
                circuit_codes.get(row.circuit, -1),
                float(np.clip(row.tyre_age, 1, 80)),
                float(np.clip(row.tyre_age, 1, 80) ** 2),
                row.lap_number / max(row.total_laps, 1),
                float(np.clip(row.position, 1, 20)),
                float(np.clip(row.stint_number, 1, 8)),
            ]
            for row in rows
        ],
        dtype=float,
    )


def _training_field_medians(rows: list[TrainingRow]) -> dict[tuple[int, int], float]:
    grouped: dict[tuple[int, int], list[int]] = {}
    for row in rows:
        grouped.setdefault((row.session_id, row.lap_number), []).append(row.lap_time_ms)
    return {key: float(median(values)) for key, values in grouped.items() if len(values) >= 5}


def _field_reference(laps: list[Lap], excluded_driver_id: int) -> dict[int, float]:
    grouped: dict[int, list[int]] = {}
    for lap in laps:
        if (
            lap.driver_id == excluded_driver_id
            or lap.lap_time_ms is None
            or lap.pit_in
            or lap.pit_out
            or lap.deleted
            or not 55_000 <= lap.lap_time_ms <= 240_000
        ):
            continue
        grouped.setdefault(lap.lap_number, []).append(lap.lap_time_ms)
    return {
        lap_number: float(median(values))
        for lap_number, values in grouped.items()
        if len(values) >= 4
    }


def _register_artifact(db: Session, bundle: PaceModelBundle, path: Path) -> None:
    artifact_version = f"{MODEL_VERSION}-before-session-{bundle.cutoff_session_id}"
    existing = db.scalar(
        select(ModelArtifact).where(
            ModelArtifact.model_name == MODEL_NAME,
            ModelArtifact.model_version == artifact_version,
        )
    )
    values: dict[str, Any] = {
        "feature_schema_json": {
            "target": "clean_lap_delta_to_same_lap_field_median_ms",
            "features": [
                "compound",
                "driver",
                "circuit",
                "tyre_age",
                "tyre_age_squared",
                "race_progress",
                "position",
                "stint_number",
            ],
            "leakage_boundary": "sessions strictly before selected session date",
        },
        "metrics_json": bundle.metrics.as_dict(),
        "file_path": str(path),
        "trained_at": datetime.now(UTC),
    }
    if existing is None:
        db.add(
            ModelArtifact(
                model_name=MODEL_NAME,
                model_version=artifact_version,
                **values,
            )
        )
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    db.flush()
