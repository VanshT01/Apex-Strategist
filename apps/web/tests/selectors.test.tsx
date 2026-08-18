import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { SeasonSelector } from "@/components/Selectors";
import { LapTable } from "@/components/LapTable";

test("season selector reports the chosen season", async () => {
  const user = userEvent.setup();
  let selected = "";
  const { rerender } = render(
    <SeasonSelector
      items={[{ id: 1, year: 2024 }]}
      value={selected}
      onChange={(value) => {
        selected = value;
      }}
    />,
  );
  await user.selectOptions(screen.getByLabelText("Season"), "2024");
  rerender(
    <SeasonSelector
      items={[{ id: 1, year: 2024 }]}
      value={selected}
      onChange={() => undefined}
    />,
  );
  expect(screen.getByLabelText("Season")).toHaveValue("2024");
});

test("lap table renders tyre, stint and position data", () => {
  render(
    <LapTable
      laps={[
        {
          id: 1,
          session_id: 1,
          driver_id: 4,
          lap_number: 8,
          position: 2,
          lap_time_ms: 90500,
          sector_1_ms: null,
          sector_2_ms: null,
          sector_3_ms: null,
          compound: "MEDIUM",
          tyre_life: 8,
          stint_number: 1,
          fresh_tyre: true,
          pit_in: false,
          pit_out: false,
          track_status: "1",
          deleted: false,
          inaccurate: false,
          timestamp_ms: 1000,
          speed_i1: null,
          speed_i2: null,
          speed_fl: null,
          speed_st: null,
          personal_best: false,
        },
      ]}
    />,
  );
  expect(screen.getByText("MEDIUM")).toBeInTheDocument();
  expect(screen.getByText("1:30.500")).toBeInTheDocument();
  expect(screen.getByRole("table")).toHaveTextContent("Racing");
});
