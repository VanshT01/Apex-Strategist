"use client";

import type { Lap } from "@/types/api";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function PaceChart({
  laps,
  compact = false,
}: {
  laps: Lap[];
  compact?: boolean;
}) {
  const data = laps
    .filter((l) => l.lap_time_ms !== null)
    .map((l) => ({
      lap: l.lap_number,
      seconds: Number((l.lap_time_ms! / 1000).toFixed(3)),
    }));
  const chartWidth = compact ? Math.max(420, data.length * 18) : undefined;
  return (
    <section
      className={`panel ${compact ? "h-full min-h-0 overflow-hidden p-3" : "p-5"}`}
    >
      <div className={compact ? "mb-2" : "mb-5"}>
        <p className="eyebrow">Pace trace</p>
        <h2 className={`mt-1 font-semibold ${compact ? "text-sm" : "text-xl"}`}>
          Lap time evolution
        </h2>
        <p className={`mt-1 text-mist ${compact ? "text-[10px]" : "text-xs"}`}>
          {data.length
            ? `Completed laps 1 to ${data.at(-1)?.lap}`
            : "No completed lap time available"}
        </p>
      </div>
      <div className={compact ? "overflow-x-auto" : ""}>
        <div
          className={compact ? "h-24" : "h-72"}
          style={compact ? { width: chartWidth } : undefined}
          role="img"
          aria-label="Scrollable line chart of lap time in seconds by lap"
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ left: 4, right: 12 }}>
              <CartesianGrid stroke="#282c35" vertical={false} />
              <XAxis
                dataKey="lap"
                stroke="#777d8b"
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={["dataMin - 1", "dataMax + 1"]}
                stroke="#777d8b"
                tickLine={false}
                axisLine={false}
                width={compact ? 38 : 48}
                tick={{ fontSize: compact ? 9 : 12 }}
              />
              <Tooltip
                contentStyle={{
                  background: "#111318",
                  border: "1px solid #282c35",
                  borderRadius: 8,
                }}
                formatter={(value) => [`${value} s`, "Lap time"]}
              />
              <Line
                dataKey="seconds"
                type="monotone"
                stroke="#ff4d2e"
                strokeWidth={2}
                dot={{ r: 2, fill: "#ff4d2e", strokeWidth: 0 }}
                activeDot={{ r: 5 }}
                animationDuration={350}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
