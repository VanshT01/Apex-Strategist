import type { Lap } from "@/types/api";
import { TyreBadge } from "./TyreBadge";

function time(ms: number | null) {
  if (ms === null) return "N/A";
  const minutes = Math.floor(ms / 60000);
  return `${minutes}:${((ms % 60000) / 1000).toFixed(3).padStart(6, "0")}`;
}

export function LapTable({
  laps,
  compact = false,
}: {
  laps: Lap[];
  compact?: boolean;
}) {
  const visibleLaps = compact ? [...laps].reverse() : laps;
  return (
    <section
      className={`panel overflow-hidden ${compact ? "flex h-full max-h-48 min-h-0 flex-col" : ""}`}
    >
      <div
        className={`flex items-end justify-between border-b border-line ${compact ? "px-3 py-2" : "p-5"}`}
      >
        <div>
          <p className="eyebrow">Timing record</p>
          <h2
            className={`mt-1 font-semibold ${compact ? "text-sm" : "text-xl"}`}
          >
            {compact ? "Recent laps" : "Driver laps"}
          </h2>
        </div>
        <span className="text-sm text-mist">{laps.length} laps</span>
      </div>
      <div
        className={compact ? "min-h-0 flex-1 overflow-auto" : "overflow-x-auto"}
      >
        <table
          className={`w-full text-left ${compact ? "min-w-[390px] text-xs" : "min-w-[760px] text-sm"}`}
        >
          <caption className="sr-only">
            Lap number, position, lap time, tyre compound, tyre age, stint and
            pit status
          </caption>
          <thead className="bg-asphalt/60 text-xs uppercase tracking-wider text-mist">
            <tr>
              {(compact
                ? ["Lap", "Pos", "Lap time", "Compound", "Age", "Status"]
                : [
                    "Lap",
                    "Pos",
                    "Lap time",
                    "Compound",
                    "Tyre age",
                    "Stint",
                    "Status",
                  ]
              ).map((h) => (
                <th
                  className={
                    compact
                      ? "px-2 py-1.5 font-medium"
                      : "px-5 py-3 font-medium"
                  }
                  key={h}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleLaps.map((lap) => (
              <tr
                key={lap.id}
                className="border-t border-line/70 hover:bg-white/[.025]"
              >
                <td
                  className={
                    compact ? "px-2 py-1.5 font-mono" : "px-5 py-4 font-mono"
                  }
                >
                  {lap.lap_number}
                </td>
                <td className={compact ? "px-2 py-1.5" : "px-5 py-4"}>
                  {lap.position ?? "N/A"}
                </td>
                <td
                  className={
                    compact ? "px-2 py-1.5 font-mono" : "px-5 py-4 font-mono"
                  }
                >
                  {time(lap.lap_time_ms)}
                </td>
                <td className={compact ? "px-2 py-1.5" : "px-5 py-4"}>
                  <TyreBadge compound={lap.compound} />
                </td>
                <td className={compact ? "px-2 py-1.5" : "px-5 py-4"}>
                  {lap.tyre_life ?? "N/A"}
                </td>
                {!compact && (
                  <td className="px-5 py-4">{lap.stint_number ?? "N/A"}</td>
                )}
                <td
                  className={
                    compact ? "px-2 py-1.5 text-mist" : "px-5 py-4 text-mist"
                  }
                >
                  {lap.pit_in
                    ? "Pit in"
                    : lap.pit_out
                      ? "Pit out"
                      : lap.inaccurate
                        ? "Inaccurate"
                        : "Racing"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
