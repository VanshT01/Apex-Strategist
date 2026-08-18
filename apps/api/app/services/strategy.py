import logging
from time import perf_counter

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import StrategySimulation
from app.repositories.race import RaceRepository
from app.schemas.strategy import (
    RecommendationRead,
    StrategyCandidate,
    StrategyCompareRequest,
    StrategyComparisonResponse,
    StrategyOutcome,
)
from app.services.race_state import RaceStateService
from app.simulation.calibration import UncertaintyCalibrator
from app.simulation.deterministic import DeterministicStrategyEngine
from app.simulation.monte_carlo import MonteCarloStrategyEngine
from app.simulation.pace_model import build_session_pace_predictor
from app.simulation.pit_loss import PitLossEstimator
from app.simulation.tyres import TyreDegradationEstimator

DISCLAIMER = (
    "Historical counterfactual simulation using public timing data. Probabilities are frequencies "
    "inside this model, not bookmaker odds, guaranteed real-world confidence, or proof that an "
    "alternative decision would have produced the simulated result."
)

SIMULATION_ASSUMPTIONS = [
    "The deterministic engine remains the central expected value projection.",
    "Competitors remain anchored to recorded trajectories with modest pace uncertainty.",
    "Competitors do not strategically react to the user's counterfactual choice.",
    "No new mechanical failure or unclassified outcome is simulated.",
    "No new Safety Car or VSC is sampled; recorded interventions remain in the historical anchor.",
    "Traffic loss uses a bounded, mean centred rejoin window heuristic.",
]

logger = logging.getLogger(__name__)


class StrategyService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = RaceRepository(db)
        self.race_state = RaceStateService(db)
        self.settings = get_settings()

    def compare(self, payload: StrategyCompareRequest) -> StrategyComparisonResponse:
        if payload.simulation_count > self.settings.max_simulation_count:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"simulation_count cannot exceed configured maximum "
                f"{self.settings.max_simulation_count}",
            )
        session = self.repo.session(payload.session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
        event = self.repo.event(session.event_id)
        total_laps = event.total_laps if event and event.total_laps else 0
        if payload.control_lap >= total_laps:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Choose a control lap before the final lap ({max(total_laps - 1, 1)} or earlier)",
            )
        if self.repo.entry(payload.session_id, payload.driver_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver is not in this session")
        driver_laps = self.repo.driver_laps(payload.session_id, payload.driver_id)
        if not any(lap.lap_number == payload.control_lap for lap in driver_laps):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Driver did not complete the selected control lap",
            )
        names = [strategy.name.casefold() for strategy in payload.strategies]
        if len(names) != len(set(names)):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Strategy names must be unique"
            )
        for candidate in payload.strategies:
            if candidate.pit_lap is not None and not (
                payload.control_lap <= candidate.pit_lap < total_laps
            ):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Pit lap must be from {payload.control_lap} to {total_laps - 1}",
                )

        laps = self.repo.session_laps(payload.session_id)
        available = TyreDegradationEstimator(laps).available_compounds()
        # The estimator has conservative hierarchical priors for compounds that were not
        # used in the recorded race. Engineer mode therefore keeps wet-weather tyres
        # selectable even when the historical session contains no clean samples for them.
        entry_pairs = self.repo.entries(payload.session_id)
        entries = [entry for entry, _ in entry_pairs]
        selected_entry, selected_driver = next(
            (entry, driver) for entry, driver in entry_pairs if entry.driver_id == payload.driver_id
        )
        pit_estimator = PitLossEstimator(self.repo)
        pit_loss = pit_estimator.estimate(payload.session_id)
        pit_samples, _ = pit_estimator.distribution(payload.session_id)
        if payload.scenario.pit_loss_delta_ms:
            pit_loss = pit_loss.model_copy(
                update={
                    "estimated_ms": max(
                        10_000,
                        min(60_000, pit_loss.estimated_ms + payload.scenario.pit_loss_delta_ms),
                    ),
                    "source": f"scenario_adjusted_{pit_loss.source}",
                }
            )
        pace_predictor = None
        try:
            pace_predictor = build_session_pace_predictor(
                self.db,
                session=session,
                event=event,
                laps=laps,
                driver_id=payload.driver_id,
                driver=selected_driver,
                driver_code=selected_entry.abbreviation or selected_driver.abbreviation,
                control_lap=payload.control_lap,
                model_path=self.settings.model_path,
            )
        except Exception:
            logger.exception("Learned pace model unavailable; using deterministic fallback")
        engine = DeterministicStrategyEngine(
            laps,
            entries,
            payload.driver_id,
            payload.control_lap,
            total_laps,
            pit_loss,
            payload.scenario.tyre_degradation_multiplier,
            payload.simulation_context,
            self.repo.weather_samples(payload.session_id),
            pace_predictor,
        )
        baseline = engine.baseline_time()
        outcomes = [engine.simulate(candidate, baseline) for candidate in payload.strategies]
        actual = self.race_state.actual_strategy(
            payload.session_id, payload.driver_id, payload.control_lap
        )
        stay_out_index = next(
            (
                index
                for index, candidate in enumerate(payload.strategies)
                if candidate.pit_lap is None
            ),
            None,
        )
        if stay_out_index is None:
            stay_out_candidate = StrategyCandidate(name="Stay out baseline")
            stay_out_outcome = engine.simulate(stay_out_candidate, baseline)
        else:
            stay_out_candidate = payload.strategies[stay_out_index]
            stay_out_outcome = outcomes[stay_out_index]

        historical_laps = []
        if event and event.location:
            historical_laps = self.repo.historical_laps_for_location(
                event.location, payload.session_id
            )
        calibration = UncertaintyCalibrator(
            laps,
            entry_pairs,
            payload.driver_id,
            payload.control_lap,
            pit_loss,
            pit_samples,
            historical_laps,
        ).calibrate()
        monte_carlo = MonteCarloStrategyEngine(
            engine,
            entries,
            payload.session_id,
            calibration,
            payload.simulation_count,
            payload.random_seed,
        )
        calculation_started = perf_counter()
        aggregates = monte_carlo.compare(
            payload.strategies,
            outcomes,
            stay_out_candidate,
            stay_out_outcome,
            actual.actual_finish,
        )
        calculation_time_ms = (perf_counter() - calculation_started) * 1000
        outcomes = [
            outcome.model_copy(update={"monte_carlo": aggregate})
            for outcome, aggregate in zip(outcomes, aggregates, strict=True)
        ]
        ranked = sorted(outcomes, key=self._ranking_key)
        recommendation = self._recommend(ranked[0], outcomes, stay_out_outcome)

        simulation = self.repo.add_simulation(
            StrategySimulation(
                session_id=payload.session_id,
                driver_id=payload.driver_id,
                control_lap=payload.control_lap,
                strategy_payload_json=payload.model_dump(mode="json"),
                simulation_count=payload.simulation_count,
                random_seed=payload.random_seed,
                model_version=monte_carlo.version,
                result_payload_json={},
            )
        )
        response = StrategyComparisonResponse(
            comparison_id=simulation.id,
            engine_version=monte_carlo.version,
            deterministic=False,
            session_id=payload.session_id,
            driver_id=payload.driver_id,
            control_lap=payload.control_lap,
            pit_loss=pit_loss,
            available_compounds=available,
            outcomes=outcomes,
            recommendation=recommendation,
            actual_strategy=actual,
            disclaimer=DISCLAIMER,
            simulation_count=payload.simulation_count,
            random_seed=payload.random_seed,
            calculation_time_ms=round(calculation_time_ms, 3),
            uncertainty_sources=calibration.sources,
            assumptions=SIMULATION_ASSUMPTIONS,
        )
        simulation.result_payload_json = response.model_dump(mode="json")
        self.db.commit()
        return response

    def get(self, comparison_id: int) -> StrategyComparisonResponse:
        simulation = self.repo.simulation(comparison_id)
        if simulation is None or not simulation.result_payload_json:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Comparison not found")
        return StrategyComparisonResponse.model_validate(simulation.result_payload_json)

    @staticmethod
    def _ranking_key(outcome: StrategyOutcome) -> tuple[float, float, int, int, int]:
        aggregate = outcome.monte_carlo
        if aggregate is None:
            return (float(outcome.predicted_finish), 0, outcome.predicted_total_time_ms, 20, 0)
        return (
            aggregate.median_predicted_finish,
            -aggregate.improve_stay_out_probability,
            aggregate.median_total_time_ms,
            aggregate.finish_position_p95,
            aggregate.race_time_p95_ms,
        )

    @staticmethod
    def _recommend(
        best: StrategyOutcome,
        outcomes: list[StrategyOutcome],
        stay_out: StrategyOutcome,
    ) -> RecommendationRead:
        aggregate = best.monte_carlo
        if aggregate is None:
            return RecommendationRead(
                strategy_name=best.name,
                explanation="The deterministic projection ranks this strategy first.",
            )
        action = (
            "staying out"
            if best.pit_lap is None
            else f"pitting on lap {best.pit_lap} for {best.next_compound.title()} tyres"
        )
        stay_out_aggregate = next(
            (
                outcome.monte_carlo
                for outcome in outcomes
                if outcome.pit_lap is None and outcome.monte_carlo is not None
            ),
            None,
        )
        stay_out_median = (
            stay_out_aggregate.median_total_time_ms
            if stay_out_aggregate
            else stay_out.predicted_total_time_ms
        )
        median_advantage = (stay_out_median - aggregate.median_total_time_ms) / 1000
        traffic_label = StrategyService._risk_label(aggregate.traffic_risk)
        degradation_label = StrategyService._risk_label(aggregate.degradation_risk)
        beats_baseline = round(aggregate.improve_stay_out_probability * 100)
        if stay_out.dnf and not best.dnf:
            time_summary = "avoids the tyre failure retirement projected for staying out"
        elif stay_out.dnf and best.dnf:
            time_summary = "also reaches a tyre failure retirement before the finish"
        elif median_advantage >= 0:
            time_summary = f"improves median race time by {median_advantage:.1f}s"
        else:
            time_summary = f"is {-median_advantage:.1f}s slower on median race time"
        main_advantage = (
            f"It beats the stay out baseline in {beats_baseline}% of paired simulations and "
            f"{time_summary}."
        )
        key_risk = (
            f"Rejoin traffic risk is {traffic_label}; end of stint degradation risk is "
            f"{degradation_label}."
        )
        tyre_economics = (
            f"Current tyre health is {best.current_tyre_health_pct:.1f}% "
            f"(+{best.current_tyre_pace_loss_seconds:.1f}s/lap); the next lap projection is "
            f"{best.projected_next_lap_health_pct:.1f}% "
            f"(+{best.projected_next_lap_pace_loss_seconds:.1f}s/lap)."
            if best.projected_next_lap_health_pct is not None
            and best.projected_next_lap_pace_loss_seconds is not None
            else ""
        )
        uncertainty = (
            f"The 90% simulated finish range spans P{aggregate.finish_position_p05} to "
            f"P{aggregate.finish_position_p95}."
        )
        explanation = (
            f"{best.name} is recommended: {action} produces the strongest risk adjusted outcome "
            f"across {aggregate.simulation_count:,} seeded simulations, with a median finish of "
            f"P{aggregate.median_predicted_finish:.0f}. {tyre_economics} "
            f"{main_advantage} {key_risk} {uncertainty}"
        )
        return RecommendationRead(
            strategy_name=best.name,
            explanation=explanation,
            primary_advantage=main_advantage,
            key_risk=key_risk,
            uncertainty_note=uncertainty,
        )

    @staticmethod
    def _risk_label(value: float) -> str:
        if value < 0.34:
            return "low"
        if value < 0.67:
            return "medium"
        return "high"
