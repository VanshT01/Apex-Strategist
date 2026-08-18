import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import {
  EngineerMode,
  mergeEngineerLaps,
  simulatedOrder,
} from "@/components/EngineerMode";
import { api } from "@/lib/api";
import type { Lap, RaceState, StrategyComparison } from "@/types/api";

const state: RaceState = {
  session_id: 1,
  control_lap: 1,
  total_laps: 5,
  selected_driver: {
    driver_id: 4,
    abbreviation: "VER",
    full_name: "Max Verstappen",
    position: 1,
    completed_laps: 1,
    compound: "MEDIUM",
    tyre_life: 1,
    tyre_health_percent: 62,
    stint_number: 1,
    last_lap_time_ms: 90_000,
    recent_pace_ms: 90_000,
    recent_pace_sample_count: 1,
    timestamp_ms: 90_000,
    pit_history: [],
  },
  running_order: [],
  weather: {
    timestamp_ms: 90_000,
    air_temperature: 24.2,
    track_temperature: 34.8,
    humidity: 61,
    rainfall: false,
    wind_speed: 2.3,
  },
  race_control: {
    track_status: "1",
    status_label: "GREEN",
    latest_messages: [],
  },
  pit_loss: {
    estimated_ms: 22_000,
    sample_count: 10,
    source: "session",
    uncertainty_ms: 500,
  },
  likely_rejoin_position: 4,
  nearby_driver_ids: [5],
  data_quality: "HIGH",
};

function renderEngineer(onLapChange = vi.fn()) {
  render(
    <EngineerMode
      sessionId={1}
      driverId={4}
      lap={1}
      maxLap={5}
      state={state}
      selectedLaps={[]}
      onLapChange={onLapChange}
    />,
  );
  return onLapChange;
}

test("shows lap weather and simulates stay out independently", async () => {
  const compare = vi.spyOn(api, "compare").mockResolvedValue({
    outcomes: [
      {
        name: "Stay out",
        tyre_estimate: {
          source: "event_compound_stint_model",
          performance_life_laps: 38,
          durability_laps: 61,
          stint_sample_count: 28,
        },
        projected_laps: [
          {
            lap_number: 2,
            compound: "MEDIUM",
            tyre_age: 2,
            tyre_health_percent: 58,
            lap_time_ms: 90_400,
            cumulative_time_ms: 180_400,
            historical_time_ms: 180_000,
            predicted_position: 1,
            pit_stop: false,
            dnf: false,
          },
        ],
      },
    ],
  } as unknown as StrategyComparison);
  const onLapChange = renderEngineer();

  expect(screen.getByText("Live weather · lap 1")).toBeInTheDocument();
  expect(screen.getByText("34.8°C")).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "62",
  );
  fireEvent.click(
    screen.getByRole("button", { name: /Stay out · advance to lap 2/i }),
  );

  await waitFor(() => expect(onLapChange).toHaveBeenCalledWith(2));
  expect(
    screen.getByLabelText(
      "Tyre life model: 38 lap performance window, 61 lap terminal reserve, 28 event stints",
    ),
  ).toBeInTheDocument();
  expect(compare).toHaveBeenCalledWith(
    1,
    4,
    1,
    expect.arrayContaining([
      expect.objectContaining({ name: "Stay out", pit_lap: null }),
    ]),
    500,
    43,
    undefined,
    expect.any(Object),
  );
  compare.mockRestore();
});

test("submits one selected pit decision with the current race context", async () => {
  const compare = vi.spyOn(api, "compare").mockResolvedValue({
    outcomes: [
      {
        name: "Box · WET",
        likely_rejoin_position: 4,
        projected_laps: [
          {
            lap_number: 2,
            compound: "WET",
            tyre_age: 1,
            tyre_health_percent: 100,
            lap_time_ms: 94_000,
            cumulative_time_ms: 207_000,
            historical_time_ms: 180_000,
            predicted_position: 4,
            pit_stop: true,
          },
        ],
        monte_carlo: null,
      },
    ],
  } as unknown as StrategyComparison);
  const onLapChange = renderEngineer();

  fireEvent.click(screen.getByRole("button", { name: "WET" }));
  fireEvent.click(screen.getByRole("button", { name: /Box for WET/i }));

  await waitFor(() => expect(onLapChange).toHaveBeenCalledWith(2));
  expect(screen.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  expect(compare).toHaveBeenCalledWith(
    1,
    4,
    1,
    expect.arrayContaining([expect.objectContaining({ next_compound: "WET" })]),
    500,
    43,
    undefined,
    expect.objectContaining({
      current_compound: "MEDIUM",
      current_tyre_age: 1,
    }),
  );
  compare.mockRestore();
});

test("shows an active intervention and drivers boxed under it", () => {
  const vscState: RaceState = {
    ...state,
    race_control: {
      track_status: "6",
      status_label: "VSC",
      latest_messages: ["VIRTUAL SAFETY CAR DEPLOYED"],
      intervention_start_lap: 1,
      boxed_driver_ids: [5],
    },
    running_order: [
      {
        driver_id: 5,
        driver_number: "4",
        abbreviation: "NOR",
        full_name: "Lando Norris",
        team_name: "McLaren",
        position: 2,
        completed_laps: 1,
        compound: "HARD",
        tyre_life: 1,
        stint_number: 2,
        last_lap_time_ms: 91_000,
        gap_to_leader_ms: 2_100,
        gap_to_selected_ms: 2_100,
        status: "Finished",
        in_pit: true,
      },
    ],
  };

  render(
    <EngineerMode
      sessionId={1}
      driverId={4}
      lap={1}
      maxLap={5}
      state={vscState}
      selectedLaps={[]}
      onLapChange={vi.fn()}
    />,
  );

  expect(screen.getByText("VSC")).toBeInTheDocument();
  expect(
    screen.getByText(/Boxed during this intervention: NOR/),
  ).toBeInTheDocument();
  expect(screen.getByText("IN PIT")).toBeInTheDocument();
});

test("ends the independent race when tyre health triggers a failure", async () => {
  const compare = vi.spyOn(api, "compare").mockResolvedValue({
    outcomes: [
      {
        name: "Stay out",
        projected_laps: [
          {
            lap_number: 2,
            compound: "SOFT",
            tyre_age: 30,
            tyre_health_percent: 4.9,
            tyre_pace_loss_seconds: 33.9,
            tyre_state: "FAILED",
            lap_time_ms: 94_000,
            cumulative_time_ms: 184_000,
            historical_time_ms: 180_000,
            predicted_position: 20,
            pit_stop: false,
            dnf: true,
            status: "TYRE FAILURE",
            retirement_reason: "TYRE_FAILURE",
            lap_completed: false,
          },
        ],
      },
    ],
  } as unknown as StrategyComparison);
  renderEngineer();

  fireEvent.click(
    screen.getByRole("button", { name: /Stay out · advance to lap 2/i }),
  );

  expect(await screen.findByText("DNF: TYRE FAILURE")).toBeInTheDocument();
  expect(screen.getByText(/tyre penalty \+34.0s\/lap/i)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /advance to lap/i }),
  ).not.toBeInTheDocument();
  compare.mockRestore();
});

test("resolves an overtake when the projected timestamp crosses the trailing car", () => {
  const crossingState: RaceState = {
    ...state,
    selected_driver: {
      ...state.selected_driver,
      completed_laps: 2,
      timestamp_ms: 180_000,
    },
    running_order: [
      {
        driver_id: 4,
        driver_number: "1",
        abbreviation: "VER",
        full_name: "Max Verstappen",
        team_name: "Red Bull Racing",
        position: 1,
        completed_laps: 2,
        compound: "MEDIUM",
        tyre_life: 1,
        stint_number: 1,
        last_lap_time_ms: 90_000,
        timestamp_ms: 180_000,
        gap_to_leader_ms: 0,
        gap_to_selected_ms: 0,
        status: "Finished",
        in_pit: false,
      },
      {
        driver_id: 5,
        driver_number: "4",
        abbreviation: "NOR",
        full_name: "Lando Norris",
        team_name: "McLaren",
        position: 2,
        completed_laps: 2,
        compound: "HARD",
        tyre_life: 1,
        stint_number: 1,
        last_lap_time_ms: 90_500,
        timestamp_ms: 181_000,
        gap_to_leader_ms: 1_000,
        gap_to_selected_ms: 1_000,
        status: "Finished",
        in_pit: false,
      },
    ],
  };
  const order = simulatedOrder(crossingState, 4, {
    current_compound: "MEDIUM",
    current_tyre_age: 2,
    current_position: 2,
    current_stint_number: 1,
    current_completed_laps: 2,
    current_timestamp_ms: 181_500,
    cumulative_time_delta_ms: 1_500,
  });

  expect(order.map((driver) => driver.abbreviation)).toEqual(["NOR", "VER"]);
  expect(order.find((driver) => driver.driver_id === 4)?.gap_to_leader_ms).toBe(
    500,
  );
});

test("normalizes duplicate source positions and derives the selected leader gap", () => {
  const duplicateState: RaceState = {
    ...state,
    selected_driver: { ...state.selected_driver, timestamp_ms: 90_000 },
    running_order: [
      {
        driver_id: 5,
        driver_number: "4",
        abbreviation: "NOR",
        full_name: "Lando Norris",
        team_name: "McLaren",
        position: 1,
        completed_laps: 1,
        compound: "HARD",
        tyre_life: 1,
        stint_number: 1,
        last_lap_time_ms: 90_000,
        timestamp_ms: 90_000,
        gap_to_leader_ms: 0,
        gap_to_selected_ms: 0,
        status: "Finished",
        in_pit: false,
      },
      {
        driver_id: 6,
        driver_number: "55",
        abbreviation: "SAI",
        full_name: "Carlos Sainz",
        team_name: "Williams",
        position: 1,
        completed_laps: 1,
        compound: "HARD",
        tyre_life: 1,
        stint_number: 1,
        last_lap_time_ms: 90_500,
        timestamp_ms: 91_500,
        gap_to_leader_ms: 1_500,
        gap_to_selected_ms: 1_500,
        status: "Finished",
        in_pit: false,
      },
      {
        driver_id: 4,
        driver_number: "1",
        abbreviation: "VER",
        full_name: "Max Verstappen",
        team_name: "Red Bull Racing",
        position: 4,
        completed_laps: 1,
        compound: "MEDIUM",
        tyre_life: 1,
        stint_number: 1,
        last_lap_time_ms: 91_000,
        timestamp_ms: 90_000,
        gap_to_leader_ms: 0,
        gap_to_selected_ms: 0,
        status: "Finished",
        in_pit: false,
      },
    ],
  };

  const order = simulatedOrder(duplicateState, 4, {
    current_compound: "MEDIUM",
    current_tyre_age: 8,
    current_position: 4,
    cumulative_time_delta_ms: 2_000,
  });

  expect(order.map((driver) => driver.position)).toEqual([1, 2, 3]);
  expect(order.filter((driver) => driver.position === 1)).toHaveLength(1);
  expect(order.find((driver) => driver.driver_id === 4)?.gap_to_leader_ms).toBe(
    2_000,
  );
});

test("timing records use player-owned stint numbers and retain intervention flags", () => {
  const historical = [
    {
      id: 2,
      session_id: 1,
      driver_id: 4,
      lap_number: 2,
      position: 10,
      lap_time_ms: 120_000,
      sector_1_ms: null,
      sector_2_ms: null,
      sector_3_ms: null,
      compound: "MEDIUM",
      tyre_life: 12,
      stint_number: 7,
      fresh_tyre: null,
      pit_in: false,
      pit_out: false,
      track_status: "4",
      deleted: false,
      inaccurate: true,
      timestamp_ms: 180_000,
      speed_i1: null,
      speed_i2: null,
      speed_fl: null,
      speed_st: null,
      personal_best: null,
    },
  ] satisfies Lap[];
  const merged = mergeEngineerLaps(
    historical,
    {
      2: {
        lap_number: 2,
        compound: "SOFT",
        tyre_age: 1,
        stint_number: 2,
        tyre_health_percent: 100,
        lap_time_ms: 95_000,
        cumulative_time_ms: 175_000,
        historical_time_ms: 180_000,
        predicted_position: 11,
        pit_stop: true,
      },
    },
    2,
  );

  expect(merged[0]).toMatchObject({
    compound: "SOFT",
    stint_number: 2,
    pit_out: true,
    inaccurate: true,
  });
});

test("ends engineer control on an early chequered crossing", async () => {
  const compare = vi.spyOn(api, "compare").mockResolvedValue({
    outcomes: [
      {
        name: "Stay out",
        projected_laps: [
          {
            lap_number: 2,
            compound: "MEDIUM",
            tyre_age: 2,
            stint_number: 1,
            tyre_health_percent: 96,
            lap_time_ms: 91_500,
            cumulative_time_ms: 181_500,
            historical_time_ms: 180_000,
            predicted_position: 4,
            pit_stop: false,
            dnf: false,
            status: "CHEQUERED",
          },
        ],
      },
    ],
  } as unknown as StrategyComparison);
  const onLapChange = renderEngineer();

  fireEvent.click(
    screen.getByRole("button", { name: /Stay out · advance to lap 2/i }),
  );

  expect(await screen.findByText("Race complete")).toBeInTheDocument();
  expect(onLapChange).toHaveBeenCalledWith(5);
  expect(
    screen.queryByRole("button", { name: /advance to lap/i }),
  ).not.toBeInTheDocument();
  compare.mockRestore();
});
