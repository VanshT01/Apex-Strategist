import type { RaceState } from "@/types/api";
import { TyreBadge } from "./TyreBadge";

function time(ms: number | null) {
  return ms === null ? "N/A" : `${(ms / 1000).toFixed(3)}s`;
}

export function RaceStateCard({ state }: { state: RaceState }) {
  const driver = state.selected_driver;
  const metrics = [
    ["Position", driver.position ? `P${driver.position}` : "N/A"],
    ["Last lap", time(driver.last_lap_time_ms)],
    ["Recent pace", time(driver.recent_pace_ms)],
    [
      "Tyre age",
      driver.tyre_life === null ? "N/A" : `${driver.tyre_life} laps`,
    ],
    [
      "Likely rejoin",
      state.likely_rejoin_position ? `P${state.likely_rejoin_position}` : "N/A",
    ],
    ["Pit loss", `~${(state.pit_loss.estimated_ms / 1000).toFixed(1)}s`],
  ];
  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Race state / lap {state.control_lap}</p>
          <h2 className="mt-2 text-2xl font-semibold">
            {driver.abbreviation} · {driver.full_name}
          </h2>
          <div className="mt-3 flex items-center gap-3">
            <TyreBadge compound={driver.compound} />
            <span className="text-sm text-mist">
              Stint {driver.stint_number ?? "N/A"}
            </span>
            <span className="rounded-full border border-line px-2 py-1 text-[11px] text-mist">
              {state.data_quality} DATA
            </span>
          </div>
        </div>
        <div
          className={`rounded-lg border px-3 py-2 text-xs font-semibold ${state.race_control.status_label === "GREEN" ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300" : "border-amber-300/30 bg-amber-300/10 text-amber-200"}`}
        >
          {state.race_control.status_label}
        </div>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-3">
        {metrics.map(([label, value]) => (
          <div className="bg-panel p-4" key={label}>
            <p className="text-xs uppercase tracking-wider text-mist">
              {label}
            </p>
            <p className="mt-2 font-mono text-lg font-semibold">{value}</p>
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
        <div>
          <p className="label">Weather</p>
          <p>
            {state.weather
              ? `${state.weather.track_temperature?.toFixed(1) ?? "N/A"}°C track · ${state.weather.rainfall ? "Rain" : "Dry"}`
              : "Unavailable"}
          </p>
        </div>
        <div>
          <p className="label">Pit-loss source</p>
          <p>
            {state.pit_loss.source.replaceAll("_", " ")} ·{" "}
            {state.pit_loss.sample_count} samples
          </p>
        </div>
      </div>
    </section>
  );
}
