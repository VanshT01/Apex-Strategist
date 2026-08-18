import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ErrorState } from "@/components/State";
import { StrategyBuilder } from "@/components/StrategyBuilder";
import { StrategyResults } from "@/components/StrategyResults";
import { api } from "@/lib/api";
import type { MonteCarloAggregate, StrategyComparison } from "@/types/api";

function aggregate(
  overrides: Partial<MonteCarloAggregate> = {},
): MonteCarloAggregate {
  return {
    mean_predicted_finish: 3.1,
    median_predicted_finish: 3,
    most_likely_finish: 3,
    expected_total_time_ms: 5_000_100,
    median_total_time_ms: 5_000_000,
    mean_time_vs_deterministic_baseline_ms: -2100,
    median_time_vs_deterministic_baseline_ms: -2200,
    win_probability: 0.124,
    podium_probability: 0.67,
    points_probability: 0.95,
    improve_actual_probability: 0.72,
    improve_stay_out_probability: 0.68,
    race_time_p05_ms: 4_995_000,
    race_time_p25_ms: 4_998_000,
    race_time_p75_ms: 5_002_000,
    race_time_p95_ms: 5_006_000,
    finish_position_p05: 2,
    finish_position_p95: 5,
    likely_rejoin_position: 8,
    traffic_risk: 0.2,
    degradation_risk: 0.3,
    finish_position_distribution: [
      { position: 2, count: 200, probability: 0.2 },
      { position: 3, count: 500, probability: 0.5 },
      { position: 4, count: 300, probability: 0.3 },
    ],
    time_delta_histogram: [
      { lower_ms: -5000, upper_ms: -2500, count: 400, probability: 0.4 },
      { lower_ms: -2500, upper_ms: 0, count: 600, probability: 0.6 },
    ],
    simulation_count: 1000,
    random_seed: 42,
    engine_version: "monte-carlo-v1",
    data_quality: "HIGH",
    ...overrides,
  };
}

function comparisonFixture(): StrategyComparison {
  const tyre = {
    compound: "HARD",
    initial_offset_ms: 250,
    degradation_per_lap_ms: 55,
    sample_count: 40,
    source: "event_compound",
    uncertainty_ms: 900,
    degradation_uncertainty_per_lap_ms: 20,
  };
  return {
    comparison_id: 1,
    engine_version: "monte-carlo-v1",
    deterministic: false,
    session_id: 1,
    driver_id: 4,
    control_lap: 20,
    pit_loss: {
      estimated_ms: 21_500,
      sample_count: 18,
      source: "current_session",
      uncertainty_ms: 700,
    },
    available_compounds: ["SOFT", "MEDIUM", "HARD"],
    outcomes: [
      {
        name: "Pit now · HARD",
        pit_lap: 20,
        next_compound: "HARD",
        pace_mode: "BALANCED",
        predicted_finish: 3,
        predicted_total_time_ms: 5_000_000,
        time_vs_actual_ms: -2200,
        time_vs_baseline_ms: -2200,
        likely_rejoin_position: 8,
        traffic_risk: 0.2,
        degradation_risk: 0.3,
        final_tyre_age: 32,
        pit_loss_ms: 21_500,
        tyre_estimate: tyre,
        assumptions: ["Historical field"],
        monte_carlo: aggregate(),
      },
      {
        name: "Stay out",
        pit_lap: null,
        next_compound: null,
        pace_mode: "BALANCED",
        predicted_finish: 4,
        predicted_total_time_ms: 5_002_200,
        time_vs_actual_ms: 0,
        time_vs_baseline_ms: 0,
        likely_rejoin_position: 4,
        traffic_risk: 0,
        degradation_risk: 0.8,
        final_tyre_age: 40,
        pit_loss_ms: 0,
        tyre_estimate: { ...tyre, compound: "MEDIUM" },
        assumptions: ["Historical field"],
        monte_carlo: aggregate({
          median_predicted_finish: 4,
          win_probability: 0.05,
          podium_probability: 0.3,
          points_probability: 0.9,
          improve_stay_out_probability: 0,
          median_time_vs_deterministic_baseline_ms: 0,
          finish_position_p05: 3,
          finish_position_p95: 6,
        }),
      },
    ],
    recommendation: {
      strategy_name: "Pit now · HARD",
      explanation: "Pit now wins the strongest risk-adjusted outcome.",
      primary_advantage: "Beats stay out in 68% of simulations.",
      key_risk: "Traffic risk is low.",
      uncertainty_note: "The 90% range spans P2 to P5.",
    },
    actual_strategy: {
      session_id: 1,
      driver_id: 4,
      control_lap: 20,
      actual_finish: 4,
      actual_status: "Finished",
      actual_total_time_ms: 5_002_200,
      remaining_stops: [
        { pit_lap: 27, next_compound: "HARD", pit_duration_ms: 21_500 },
      ],
    },
    disclaimer: "Historical counterfactual simulation.",
    simulation_count: 1000,
    random_seed: 42,
    calculation_time_ms: 12.5,
    uncertainty_sources: [
      {
        variable: "lap_time_residual",
        source: "driver_current_session",
        sample_count: 18,
        scale_ms: 650,
        fallback: false,
        assumption: "Robust residual scale.",
      },
    ],
    assumptions: [
      "Competitors do not strategically react to the user's counterfactual choice.",
      "No new mechanical failure or unclassified outcome is simulated.",
    ],
  };
}

test("strategy builder defaults to 1000 simulations and seed 42", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(
    <StrategyBuilder
      controlLap={20}
      totalLaps={52}
      loading={false}
      onSubmit={submit}
    />,
  );

  expect(screen.getByLabelText("Simulations")).toHaveValue("1000");
  expect(screen.getByLabelText("Random seed")).toHaveValue(42);
  await user.selectOptions(screen.getByLabelText("Pace mode"), "AGGRESSIVE");
  await user.click(screen.getByRole("button", { name: "Compare strategies" }));

  expect(submit).toHaveBeenCalledOnce();
  expect(submit.mock.calls[0][0]).toMatchObject({
    simulation_count: 1000,
    random_seed: 42,
    scenario: {
      pit_loss_delta_ms: 0,
      tyre_degradation_multiplier: 1,
    },
    strategies: [
      { name: "Pit now · HARD", pit_lap: 20, pace_mode: "AGGRESSIVE" },
      { name: "Wait 3 laps · MEDIUM", pit_lap: 23, pace_mode: "AGGRESSIVE" },
      { name: "Stay out", pit_lap: null, pace_mode: "AGGRESSIVE" },
    ],
  });
});

test("decision mode immediately submits scenario sandbox adjustments", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(
    <StrategyBuilder
      controlLap={20}
      totalLaps={52}
      loading={false}
      onSubmit={submit}
    />,
  );
  await user.click(screen.getByText("Scenario sandbox"));
  fireEvent.change(screen.getByLabelText(/Pit lane loss adjustment/), {
    target: { value: "3" },
  });
  await user.click(screen.getByRole("button", { name: /Box this lap/ }));
  expect(submit).toHaveBeenCalledOnce();
  expect(submit.mock.calls[0][0]).toMatchObject({
    scenario: { pit_loss_delta_ms: 3000 },
    selected_strategy_name: "Pit now · HARD",
  });
});

test("strategy builder submits changed simulation count and seed", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(
    <StrategyBuilder
      controlLap={20}
      totalLaps={52}
      loading={false}
      onSubmit={submit}
    />,
  );
  await user.selectOptions(screen.getByLabelText("Simulations"), "2500");
  await user.clear(screen.getByLabelText("Random seed"));
  await user.type(screen.getByLabelText("Random seed"), "99");
  await user.click(screen.getByRole("button", { name: "Compare strategies" }));
  expect(submit.mock.calls[0][0]).toMatchObject({
    simulation_count: 2500,
    random_seed: 99,
  });
});

test("strategy builder permits a late-race decision before the final lap", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(
    <StrategyBuilder
      controlLap={45}
      totalLaps={52}
      loading={false}
      onSubmit={submit}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Compare strategies" }));
  expect(submit).toHaveBeenCalledOnce();
  expect(submit.mock.calls[0][0].strategies[1].pit_lap).toBe(48);
});

test("results render probabilities, distributions, intervals, and assumptions", () => {
  render(<StrategyResults result={comparisonFixture()} />);
  expect(
    screen.getAllByText("Pit now wins the strongest risk-adjusted outcome.")
      .length,
  ).toBeGreaterThan(0);
  expect(screen.getAllByText("12.4%").length).toBeGreaterThan(0);
  expect(screen.getAllByText("P2 to P5").length).toBeGreaterThan(0);
  expect(screen.getByText("monte-carlo-v1")).toBeInTheDocument();
  expect(
    screen.getByText(/Competitors do not strategically react/),
  ).toBeInTheDocument();
  expect(screen.getByLabelText(/most often finishes P3/)).toBeInTheDocument();
});

test("API validation error is surfaced and retry action renders", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: "simulation_count is too large" }),
        {
          status: 422,
          headers: { "Content-Type": "application/json" },
        },
      ),
    ),
  );
  await expect(api.compare(1, 4, 20, [], 10_000, 42)).rejects.toThrow(
    "simulation_count is too large",
  );
  render(
    <ErrorState
      message="simulation_count is too large"
      action={<button>Retry</button>}
    />,
  );
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

afterEach(() => {
  vi.unstubAllGlobals();
});
