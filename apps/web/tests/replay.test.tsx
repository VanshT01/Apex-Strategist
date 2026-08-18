import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { RaceReplay } from "@/components/RaceReplay";
import type { Driver, Lap, RaceState, Timeline } from "@/types/api";

const drivers: Driver[] = [
  {
    id: 1,
    driver_number: "1",
    abbreviation: "VER",
    full_name: "Max Verstappen",
    team_name: "Red Bull",
    country_code: "NED",
    grid_position: 1,
    finishing_position: 1,
    status: "Finished",
    points: 25,
  },
  {
    id: 2,
    driver_number: "44",
    abbreviation: "HAM",
    full_name: "Lewis Hamilton",
    team_name: "Mercedes",
    country_code: "GBR",
    grid_position: 2,
    finishing_position: 2,
    status: "Finished",
    points: 18,
  },
];
const state: RaceState = {
  session_id: 1,
  control_lap: 12,
  total_laps: 58,
  selected_driver: {
    driver_id: 1,
    abbreviation: "VER",
    full_name: "Max Verstappen",
    position: 1,
    completed_laps: 12,
    compound: "SOFT",
    tyre_life: 12,
    stint_number: 1,
    last_lap_time_ms: 89_000,
    recent_pace_ms: 89_100,
    recent_pace_sample_count: 3,
    pit_history: [],
  },
  running_order: drivers.map((driver, index) => ({
    driver_id: driver.id,
    driver_number: driver.driver_number,
    abbreviation: driver.abbreviation,
    full_name: driver.full_name,
    team_name: driver.team_name,
    position: index + 1,
    completed_laps: 12,
    compound: index ? "HARD" : "SOFT",
    tyre_life: 12,
    stint_number: 1,
    last_lap_time_ms: 89_000 + index * 400,
    gap_to_leader_ms: index * 2_000,
    gap_to_selected_ms: index * 2_000,
    status: "Finished",
  })),
  weather: {
    timestamp_ms: 1_000_000,
    air_temperature: 26,
    track_temperature: 34,
    humidity: 40,
    rainfall: false,
    wind_speed: 2,
  },
  race_control: {
    track_status: "1",
    status_label: "GREEN",
    latest_messages: ["TRACK CLEAR"],
  },
  pit_loss: {
    estimated_ms: 21_000,
    sample_count: 20,
    source: "current_session",
    uncertainty_ms: 500,
  },
  likely_rejoin_position: 3,
  nearby_driver_ids: [],
  data_quality: "HIGH",
};
const timeline: Timeline = {
  session_id: 1,
  driver_id: 1,
  total_laps: 58,
  stints: [
    {
      stint_number: 1,
      compound: "SOFT",
      start_lap: 1,
      end_lap: 13,
      lap_count: 13,
    },
  ],
  pit_laps: [13],
};
const laps = [
  {
    id: 1,
    session_id: 1,
    driver_id: 1,
    lap_number: 12,
    position: 1,
    lap_time_ms: 89_000,
    sector_1_ms: null,
    sector_2_ms: null,
    sector_3_ms: null,
    compound: "SOFT",
    tyre_life: 12,
    stint_number: 1,
    fresh_tyre: false,
    pit_in: false,
    pit_out: false,
    track_status: "1",
    deleted: false,
    inaccurate: false,
    timestamp_ms: 1_000_000,
    speed_i1: null,
    speed_i2: null,
    speed_fl: null,
    speed_st: null,
    personal_best: false,
  },
] satisfies Lap[];

test("race replay scrubbing moves the shared control point", () => {
  const onLapChange = vi.fn();
  render(
    <RaceReplay
      lap={12}
      maxLap={58}
      state={state}
      timeline={timeline}
      selectedDriverId={1}
      drivers={drivers}
      selectedLaps={laps}
      onLapChange={onLapChange}
      onDriverChange={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText("Race replay lap"), {
    target: { value: "13" },
  });
  expect(onLapChange).toHaveBeenCalledWith(13);
  expect(screen.getByText("Engineer radio")).toBeInTheDocument();
  expect(screen.getByText("Schematic race orbit")).toBeInTheDocument();
});

test("leaderboard driver selection updates the dashboard driver", async () => {
  const user = userEvent.setup();
  const onDriverChange = vi.fn();
  render(
    <RaceReplay
      lap={12}
      maxLap={58}
      state={state}
      timeline={timeline}
      selectedDriverId={1}
      drivers={drivers}
      selectedLaps={laps}
      onLapChange={vi.fn()}
      onDriverChange={onDriverChange}
    />,
  );
  await user.click(screen.getByRole("button", { name: /HAM/ }));
  expect(onDriverChange).toHaveBeenCalledWith(2);
});

test("final lap renders the chequered-flag podium state and repeated radio messages", () => {
  const finalState = {
    ...state,
    control_lap: 58,
    race_control: {
      ...state.race_control,
      latest_messages: [
        "GREEN LIGHT - PIT EXIT OPEN",
        "GREEN LIGHT - PIT EXIT OPEN",
      ],
    },
  };
  render(
    <RaceReplay
      lap={58}
      maxLap={58}
      state={finalState}
      timeline={timeline}
      selectedDriverId={1}
      drivers={drivers}
      selectedLaps={laps}
      onLapChange={vi.fn()}
      onDriverChange={vi.fn()}
    />,
  );

  expect(screen.getAllByText("Chequered flag").length).toBeGreaterThan(0);
  expect(screen.getByText("Podium secured")).toBeInTheDocument();
  expect(screen.getAllByText("GREEN LIGHT - PIT EXIT OPEN")).toHaveLength(2);
});
