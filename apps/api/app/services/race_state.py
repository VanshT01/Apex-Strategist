from collections import defaultdict
from statistics import mean

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Lap
from app.repositories.race import RaceRepository
from app.schemas.race_state import (
    ActualStop,
    ActualStrategyResponse,
    DriverRaceState,
    PitStopState,
    RaceControlState,
    RaceStateResponse,
    RunningOrderItem,
    StintSummary,
    TimelineResponse,
    WeatherState,
)
from app.simulation.pit_loss import PitLossEstimator
from app.simulation.tyres import TyreDegradationEstimator, tyre_state, tyre_wear_pct


class RaceStateService:
    def __init__(self, db: Session) -> None:
        self.repo = RaceRepository(db)

    def reconstruct(self, session_id: int, control_lap: int, driver_id: int) -> RaceStateResponse:
        session, total_laps = self._validate(session_id, driver_id, control_lap)
        all_laps = self.repo.laps_to(session_id, control_lap)
        grouped: dict[int, list[Lap]] = defaultdict(list)
        for lap in all_laps:
            grouped[lap.driver_id].append(lap)
        selected_laps = grouped.get(driver_id, [])
        if not selected_laps:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver has no laps at this point")

        entries = self.repo.entries(session_id)
        entry_by_driver = {entry.driver_id: (entry, driver) for entry, driver in entries}
        latest = {key: values[-1] for key, values in grouped.items() if values}
        selected_lap = latest[driver_id]
        leader = min(
            latest.values(),
            key=lambda lap: (
                lap.position is None,
                lap.position if lap.position is not None else 999,
                -lap.lap_number,
            ),
        )

        order = []
        for current_driver_id, lap in latest.items():
            pair = entry_by_driver.get(current_driver_id)
            if pair is None:
                continue
            entry, driver = pair
            same_leader_lap = lap.lap_number == leader.lap_number
            same_selected_lap = lap.lap_number == selected_lap.lap_number
            order.append(
                RunningOrderItem(
                    driver_id=driver.id,
                    driver_number=driver.driver_number,
                    abbreviation=entry.abbreviation or driver.abbreviation,
                    full_name=entry.full_name or driver.full_name,
                    team_name=entry.team_name or driver.team_name,
                    position=lap.position,
                    completed_laps=lap.lap_number,
                    compound=lap.compound,
                    tyre_life=lap.tyre_life,
                    stint_number=lap.stint_number,
                    last_lap_time_ms=lap.lap_time_ms,
                    timestamp_ms=lap.timestamp_ms,
                    gap_to_leader_ms=self._gap(lap, leader) if same_leader_lap else None,
                    gap_to_selected_ms=self._gap(lap, selected_lap) if same_selected_lap else None,
                    status=entry.status,
                    in_pit=(
                        lap.lap_number >= leader.lap_number - 2 and (lap.pit_in or lap.pit_out)
                    ),
                )
            )
        order.sort(
            key=lambda item: (item.position is None, item.position or 999, -item.completed_laps)
        )

        pit_loss = PitLossEstimator(self.repo).estimate(session_id)
        tyre_estimator = TyreDegradationEstimator(self.repo.session_laps(session_id))
        rejoin, nearby = self._rejoin_window(latest, driver_id, selected_lap, pit_loss.estimated_ms)
        weather = self.repo.weather_before(session_id, selected_lap.timestamp_ms or 0)
        recent = [
            lap.lap_time_ms
            for lap in selected_laps[-5:]
            if lap.lap_time_ms and not lap.pit_in and not lap.pit_out and not lap.deleted
        ][-3:]
        messages = self.repo.messages_to_lap(session_id, control_lap)
        intervention_start, boxed_driver_ids = self._intervention_context(
            selected_laps, all_laps, selected_lap.track_status
        )
        control = RaceControlState(
            track_status=selected_lap.track_status,
            status_label=self._track_status(selected_lap.track_status),
            latest_messages=[message.message for message in reversed(messages)],
            intervention_start_lap=intervention_start,
            boxed_driver_ids=boxed_driver_ids,
        )
        driver = entry_by_driver[driver_id][1]
        selected_tyre_life = (
            tyre_estimator.life_estimate(selected_lap.compound) if selected_lap.compound else None
        )
        selected_tyre_health = (
            tyre_estimator.health_percent(selected_lap.compound, selected_lap.tyre_life)
            if selected_lap.compound and selected_lap.tyre_life is not None
            else None
        )
        pit_history = [
            PitStopState.model_validate(stop, from_attributes=True)
            for stop in self.repo.pit_stops(session_id, driver_id)
            if stop.lap_number <= control_lap
        ]
        quality_inputs = [
            selected_lap.timestamp_ms is not None,
            weather is not None,
            len(order) >= 15,
        ]
        return RaceStateResponse(
            session_id=session_id,
            control_lap=control_lap,
            total_laps=total_laps,
            selected_driver=DriverRaceState(
                driver_id=driver.id,
                abbreviation=entry_by_driver[driver_id][0].abbreviation or driver.abbreviation,
                full_name=entry_by_driver[driver_id][0].full_name or driver.full_name,
                position=selected_lap.position,
                completed_laps=selected_lap.lap_number,
                compound=selected_lap.compound,
                tyre_life=selected_lap.tyre_life,
                tyre_health_percent=selected_tyre_health,
                tyre_wear_pct=(
                    round(tyre_wear_pct(selected_tyre_health), 3)
                    if selected_tyre_health is not None
                    else None
                ),
                tyre_pace_loss_seconds=(
                    round(tyre_estimator.pace_loss_seconds(selected_tyre_health), 3)
                    if selected_tyre_health is not None
                    else None
                ),
                tyre_state=(
                    tyre_state(selected_tyre_health) if selected_tyre_health is not None else None
                ),
                tyre_performance_life_laps=(
                    selected_tyre_life.performance_life_laps if selected_tyre_life else None
                ),
                tyre_durability_laps=(
                    selected_tyre_life.durability_laps if selected_tyre_life else None
                ),
                tyre_stint_sample_count=(
                    selected_tyre_life.stint_sample_count if selected_tyre_life else 0
                ),
                tyre_life_source=(selected_tyre_life.source if selected_tyre_life else None),
                stint_number=selected_lap.stint_number,
                last_lap_time_ms=selected_lap.lap_time_ms,
                recent_pace_ms=round(mean(recent)) if recent else None,
                recent_pace_sample_count=len(recent),
                timestamp_ms=selected_lap.timestamp_ms,
                pit_history=pit_history,
            ),
            running_order=order,
            weather=WeatherState.model_validate(weather, from_attributes=True) if weather else None,
            race_control=control,
            pit_loss=pit_loss,
            likely_rejoin_position=rejoin,
            nearby_driver_ids=nearby,
            data_quality="HIGH" if all(quality_inputs) else "MEDIUM",
        )

    def timeline(self, session_id: int, driver_id: int) -> TimelineResponse:
        _, total_laps = self._validate(session_id, driver_id, 1)
        laps = self.repo.driver_laps(session_id, driver_id)
        grouped: dict[int, list[Lap]] = defaultdict(list)
        for lap in laps:
            grouped[lap.stint_number or 0].append(lap)
        stints = [
            StintSummary(
                stint_number=number,
                compound=values[0].compound,
                start_lap=values[0].lap_number,
                end_lap=values[-1].lap_number,
                lap_count=len(values),
            )
            for number, values in sorted(grouped.items())
        ]
        return TimelineResponse(
            session_id=session_id,
            driver_id=driver_id,
            total_laps=total_laps,
            stints=stints,
            pit_laps=[stop.lap_number for stop in self.repo.pit_stops(session_id, driver_id)],
        )

    def actual_strategy(
        self, session_id: int, driver_id: int, control_lap: int
    ) -> ActualStrategyResponse:
        _, total_laps = self._validate(session_id, driver_id, control_lap)
        laps = self.repo.driver_laps(session_id, driver_id)
        lap_by_number = {lap.lap_number: lap for lap in laps}
        entry = self.repo.entry(session_id, driver_id)
        stops = []
        for stop in self.repo.pit_stops(session_id, driver_id):
            if stop.lap_number < control_lap:
                continue
            next_lap = lap_by_number.get(stop.lap_number + 1)
            stops.append(
                ActualStop(
                    pit_lap=stop.lap_number,
                    next_compound=next_lap.compound if next_lap else None,
                    pit_duration_ms=stop.pit_duration_ms,
                )
            )
        final_lap = laps[-1] if laps else None
        return ActualStrategyResponse(
            session_id=session_id,
            driver_id=driver_id,
            control_lap=control_lap,
            actual_finish=entry.finishing_position if entry else None,
            actual_status=entry.status if entry else None,
            actual_total_time_ms=(
                final_lap.timestamp_ms if final_lap and final_lap.lap_number >= total_laps else None
            ),
            remaining_stops=stops,
        )

    def _validate(self, session_id: int, driver_id: int, control_lap: int):
        session = self.repo.session(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
        if self.repo.entry(session_id, driver_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver is not in this session")
        event = self.repo.event(session.event_id)
        total_laps = event.total_laps if event and event.total_laps else 0
        if control_lap < 1 or control_lap > total_laps:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"control_lap must be between 1 and {max(total_laps, 1)}",
            )
        return session, total_laps

    @staticmethod
    def _gap(lap: Lap, reference: Lap) -> int | None:
        if lap.timestamp_ms is None or reference.timestamp_ms is None:
            return None
        return lap.timestamp_ms - reference.timestamp_ms

    @staticmethod
    def _track_status(value: str | None) -> str:
        if not value:
            return "UNKNOWN"
        for code, label in (
            ("5", "RED FLAG"),
            ("4", "SAFETY CAR"),
            ("6", "VSC"),
            ("7", "VSC ENDING"),
            ("2", "YELLOW"),
        ):
            if code in value:
                return label
        return "GREEN"

    @classmethod
    def _intervention_context(
        cls, selected_laps: list[Lap], all_laps: list[Lap], track_status: str | None
    ) -> tuple[int | None, list[int]]:
        current_label = cls._track_status(track_status)
        if current_label not in {"SAFETY CAR", "VSC", "VSC ENDING"}:
            return None, []
        intervention_kind = "VSC" if current_label.startswith("VSC") else current_label
        start_lap = selected_laps[-1].lap_number
        for lap in reversed(selected_laps):
            lap_label = cls._track_status(lap.track_status)
            lap_kind = "VSC" if lap_label.startswith("VSC") else lap_label
            if lap_kind != intervention_kind:
                break
            start_lap = lap.lap_number
        boxed = sorted(
            {
                lap.driver_id
                for lap in all_laps
                if start_lap <= lap.lap_number <= selected_laps[-1].lap_number and lap.pit_in
            }
        )
        return start_lap, boxed

    @staticmethod
    def _rejoin_window(
        latest: dict[int, Lap], driver_id: int, selected: Lap, pit_loss_ms: int
    ) -> tuple[int | None, list[int]]:
        if selected.timestamp_ms is None:
            return None, []
        target = selected.timestamp_ms + pit_loss_ms
        comparable = [
            lap
            for key, lap in latest.items()
            if key != driver_id
            and lap.lap_number == selected.lap_number
            and lap.timestamp_ms is not None
        ]
        position = 1 + sum(lap.timestamp_ms < target for lap in comparable)
        nearby = [
            lap.driver_id for lap in comparable if abs((lap.timestamp_ms or 0) - target) <= 5_000
        ]
        return position, nearby
