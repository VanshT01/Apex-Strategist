"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import type { Driver, Lap, RaceState, Timeline } from "@/types/api";

const compoundColor: Record<string, string> = {
  SOFT: "#ff4b3e",
  MEDIUM: "#ffd447",
  HARD: "#f5f7fa",
  INTERMEDIATE: "#3fd06f",
  WET: "#47a8ff",
};

export function RaceReplay({
  lap,
  maxLap,
  state,
  timeline,
  selectedDriverId,
  drivers,
  selectedLaps,
  onLapChange,
  onDriverChange,
}: {
  lap: number;
  maxLap: number;
  state: RaceState;
  timeline: Timeline;
  selectedDriverId: number;
  drivers: Driver[];
  selectedLaps: Lap[];
  onLapChange: (lap: number) => void;
  onDriverChange: (driverId: number) => void;
}) {
  const [playing, setPlaying] = useState(false);
  const [mode, setMode] = useState<"timeline" | "story">("timeline");
  const [pinned, setPinned] = useState<number[]>([selectedDriverId]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      if (lap >= maxLap) {
        setPlaying(false);
        return;
      }
      onLapChange(lap + 1);
    }, 850);
    return () => window.clearInterval(timer);
  }, [lap, maxLap, onLapChange, playing]);

  const selectedLap = selectedLaps.find((item) => item.lap_number === lap);
  const chapters = useMemo(
    () => buildChapters(selectedLaps, timeline, maxLap),
    [maxLap, selectedLaps, timeline],
  );

  function togglePin(driverId: number) {
    setPinned((current) => {
      if (current.includes(driverId))
        return current.filter((id) => id !== driverId);
      return [...current, driverId].slice(-3);
    });
  }

  function selectDriver(driverId: number) {
    setPinned((current) =>
      current.includes(driverId) ? current : [driverId, ...current].slice(0, 3),
    );
    onDriverChange(driverId);
  }

  return (
    <section
      className="panel flex h-full min-h-0 flex-col overflow-hidden"
      aria-label="Interactive race replay"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <p className="eyebrow">Race replay</p>
          <h2 className="mt-1 text-2xl font-semibold">
            Lap {lap} / {maxLap}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="control-button"
            type="button"
            onClick={() => onLapChange(1)}
          >
            Restart
          </button>
          <button
            className="rounded-lg bg-signal px-4 py-2 text-sm font-semibold transition hover:bg-[#ff654b]"
            type="button"
            onClick={() => setPlaying((value) => !value)}
          >
            {playing ? "Pause" : "Play replay"}
          </button>
          <div className="rounded-lg border border-line p-1">
            {(["timeline", "story"] as const).map((item) => (
              <button
                className={`rounded-md px-3 py-1.5 text-xs capitalize transition ${mode === item ? "bg-white text-asphalt" : "text-mist"}`}
                key={item}
                type="button"
                onClick={() => setMode(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="px-4 pt-3">
        <div className="relative">
          <input
            aria-label="Race replay lap"
            className="replay-range w-full"
            type="range"
            min={1}
            max={maxLap}
            value={lap}
            onChange={(event) => onLapChange(Number(event.target.value))}
          />
          <div className="pointer-events-none absolute inset-x-1 top-1/2 -translate-y-1/2">
            {timeline.pit_laps.map((pitLap) => (
              <span
                key={pitLap}
                className="absolute h-3 w-0.5 bg-signal"
                style={{
                  left: `${((pitLap - 1) / Math.max(maxLap - 1, 1)) * 100}%`,
                }}
                title={`Pit stop lap ${pitLap}`}
              />
            ))}
          </div>
        </div>
        <div className="mt-2 flex justify-between text-[10px] uppercase tracking-wider text-mist">
          <span>Lights out</span>
          <span>Control point · L{lap}</span>
          <span>Chequered flag</span>
        </div>
      </div>

      {lap === maxLap && <ChequeredFlagMoment state={state} />}

      <AnimatePresence mode="wait">
        {mode === "timeline" ? (
          <motion.div
            key="timeline"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="grid min-h-0 flex-1 gap-3 p-3 xl:grid-cols-[.82fr_1.08fr_.9fr]"
          >
            <div className="min-h-0">
              <AnimatedLeaderboard
                state={state}
                selectedDriverId={selectedDriverId}
                pinned={pinned}
                onSelect={selectDriver}
                onPin={togglePin}
              />
            </div>
            <div className="min-h-0">
              <TrackMap
                state={state}
                selectedDriverId={selectedDriverId}
                onSelect={selectDriver}
              />
            </div>
            <div className="grid min-h-0 content-start gap-3 overflow-y-auto pr-1">
              <ReplayTelemetry state={state} selectedLap={selectedLap} />
              <EngineerRadio state={state} timeline={timeline} />
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="story"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="grid min-h-0 flex-1 gap-3 overflow-y-auto p-3 md:grid-cols-2 xl:grid-cols-3"
          >
            {chapters.map((chapter, index) => (
              <button
                key={chapter.title}
                type="button"
                onClick={() => onLapChange(chapter.lap)}
                className={`rounded-xl border p-4 text-left transition ${lap >= chapter.start && lap <= chapter.end ? "border-signal bg-signal/10" : "border-line bg-asphalt hover:border-white/30"}`}
              >
                <span className="text-xs text-signal">
                  CHAPTER {index + 1} · L{chapter.start} to L{chapter.end}
                </span>
                <strong className="mt-2 block">{chapter.title}</strong>
                <span className="mt-2 block text-sm leading-6 text-mist">
                  {chapter.summary}
                </span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {pinned.length > 1 && (
        <div className="border-t border-line px-5 py-4">
          <p className="mb-3 text-xs uppercase tracking-wider text-mist">
            Synchronized driver comparison
          </p>
          <div className="grid gap-2 md:grid-cols-3">
            {pinned.map((id) => {
              const row = state.running_order.find(
                (item) => item.driver_id === id,
              );
              const driver = drivers.find((item) => item.id === id);
              return row ? (
                <motion.button
                  layout
                  key={id}
                  type="button"
                  onClick={() => onDriverChange(id)}
                  className="rounded-lg border border-line bg-asphalt p-3 text-left"
                >
                  <span className="font-semibold">
                    {driver?.abbreviation ?? row.abbreviation}
                  </span>
                  <span className="float-right text-signal">
                    P{row.position ?? "N/A"}
                  </span>
                  <span className="mt-1 block text-xs text-mist">
                    {row.compound ?? "N/A"} · {formatGap(row.gap_to_leader_ms)}
                  </span>
                </motion.button>
              ) : null;
            })}
          </div>
        </div>
      )}
    </section>
  );
}

function ChequeredFlagMoment({ state }: { state: RaceState }) {
  const position = state.selected_driver.position;
  const podium = position !== null && position <= 3;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      className="relative mx-5 mt-5 overflow-hidden rounded-2xl border border-white/20 bg-gradient-to-br from-white/10 via-panel to-signal/10 p-6"
    >
      {podium && (
        <div
          className="pointer-events-none absolute inset-0"
          aria-hidden="true"
        >
          {Array.from({ length: 28 }, (_, index) => (
            <motion.span
              key={index}
              className="absolute h-2 w-1 rounded-sm"
              style={{
                left: `${(index * 37) % 100}%`,
                backgroundColor: ["#ff4b3e", "#ffd447", "#ffffff"][index % 3],
              }}
              initial={{ top: "-10%", rotate: 0 }}
              animate={{ top: "115%", rotate: 420 }}
              transition={{
                duration: 2.2 + (index % 5) * 0.2,
                delay: (index % 7) * 0.08,
                repeat: Infinity,
              }}
            />
          ))}
        </div>
      )}
      <div className="relative flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Chequered flag</p>
          <h3 className="mt-2 text-3xl font-semibold">
            {podium ? "Podium secured" : "Race complete"}
          </h3>
          <p className="mt-2 text-sm text-mist">
            {state.selected_driver.full_name} completes the recorded race
            classification.
          </p>
        </div>
        <motion.div
          initial={{ y: 12 }}
          animate={{ y: 0 }}
          className="text-right"
        >
          <span className="block text-xs uppercase tracking-[.2em] text-mist">
            Final position
          </span>
          <strong
            className={`text-6xl ${podium ? "text-yellow-300" : "text-white"}`}
          >
            P{position ?? "N/A"}
          </strong>
        </motion.div>
      </div>
    </motion.div>
  );
}

function ReplayTelemetry({
  state,
  selectedLap,
}: {
  state: RaceState;
  selectedLap?: Lap;
}) {
  const tyreHealth = Math.max(
    5,
    Math.round(100 - (state.selected_driver.tyre_life ?? 0) * 2.1),
  );
  return (
    <div className="grid grid-cols-2 gap-1.5 md:grid-cols-4">
      <div
        className={`col-span-2 rounded-xl border p-3 md:col-span-4 ${state.weather?.rainfall ? "border-blue-400/50 bg-blue-400/10" : "border-line bg-asphalt"}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <span className="text-[10px] uppercase tracking-wider text-mist">
              Live weather · lap {state.control_lap}
            </span>
            <strong className="mt-0.5 block text-base">
              {state.weather?.rainfall ? "Rain on circuit" : "Dry track"}
            </strong>
          </div>
          <span className="text-xs text-mist">
            Track {state.weather?.track_temperature?.toFixed(1) ?? "N/A"}°C ·
            Air {state.weather?.air_temperature?.toFixed(1) ?? "N/A"}°C ·
            Humidity {state.weather?.humidity?.toFixed(0) ?? "N/A"}% · Wind{" "}
            {state.weather?.wind_speed?.toFixed(1) ?? "N/A"} m/s
          </span>
        </div>
      </div>
      <ReplayMetric
        label="Position"
        value={`P${state.selected_driver.position ?? "N/A"}`}
      />
      <ReplayMetric
        label="Compound"
        value={state.selected_driver.compound ?? "N/A"}
        accent={compoundColor[state.selected_driver.compound ?? ""]}
      />
      <ReplayMetric
        label="Tyre health"
        value={`${tyreHealth}%`}
        detail={`Age ${state.selected_driver.tyre_life ?? "N/A"} laps`}
      />
      <ReplayMetric
        label="Track"
        value={state.race_control.status_label}
        detail={state.weather?.rainfall ? "Rain detected" : "Dry signal"}
      />
      <div className="col-span-2 rounded-xl border border-line bg-asphalt p-2.5 md:col-span-4">
        <div className="flex justify-between text-xs text-mist">
          <span>Estimated tyre health</span>
          <span>
            {selectedLap?.lap_time_ms
              ? `${(selectedLap.lap_time_ms / 1000).toFixed(3)}s last lap`
              : "No lap time"}
          </span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-line">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-signal via-yellow-300 to-emerald-400"
            animate={{ width: `${tyreHealth}%` }}
            transition={{ type: "spring", stiffness: 90 }}
          />
        </div>
      </div>
    </div>
  );
}

function ReplayMetric({
  label,
  value,
  detail,
  accent,
}: {
  label: string;
  value: string;
  detail?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-line bg-asphalt p-2">
      <span className="text-[10px] uppercase tracking-wider text-mist">
        {label}
      </span>
      <motion.strong
        key={value}
        initial={{ opacity: 0, y: 5 }}
        animate={{ opacity: 1, y: 0 }}
        className="mt-0.5 block text-base"
        style={{ color: accent }}
      >
        {value}
      </motion.strong>
      {detail && <span className="text-xs text-mist">{detail}</span>}
    </div>
  );
}

function AnimatedLeaderboard({
  state,
  selectedDriverId,
  pinned,
  onSelect,
  onPin,
}: {
  state: RaceState;
  selectedDriverId: number;
  pinned: number[];
  onSelect: (id: number) => void;
  onPin: (id: number) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-asphalt">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <strong>Live order</strong>
        <span className="text-xs text-mist">
          Click driver · double click to compare
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
        {state.running_order.map((item, index) => (
          <motion.button
            layout
            key={item.driver_id}
            transition={{ type: "spring", stiffness: 280, damping: 28 }}
            type="button"
            onClick={() => onSelect(item.driver_id)}
            onDoubleClick={() => onPin(item.driver_id)}
            className={`mb-0.5 grid w-full grid-cols-[1.5rem_3rem_1fr_auto] items-center gap-2 rounded-lg px-2 py-1.5 text-left ${item.driver_id === selectedDriverId ? "bg-white/10 ring-1 ring-signal" : "hover:bg-white/5"}`}
          >
            <span className="text-lg font-semibold">
              {item.position ?? index + 1}
            </span>
            <span className="font-semibold">{item.abbreviation}</span>
            <span className="min-w-0">
              <span className="block truncate text-xs text-mist">
                {item.team_name}
              </span>
              <span className="mt-1 block h-1 max-w-44 rounded-full bg-line">
                <motion.span
                  className="block h-full rounded-full bg-signal/70"
                  animate={{
                    width: `${Math.max(8, 100 - Math.min(Math.abs(item.gap_to_leader_ms ?? 0) / 500, 92))}%`,
                  }}
                />
              </span>
            </span>
            <span className="text-right text-xs">
              <i
                className="mr-2 inline-block h-2 w-2 rounded-full"
                style={{
                  backgroundColor: compoundColor[item.compound ?? ""] ?? "#777",
                }}
              />
              {formatGap(item.gap_to_selected_ms)}
              {pinned.includes(item.driver_id) && (
                <span className="ml-2 text-signal">●</span>
              )}
            </span>
          </motion.button>
        ))}
      </div>
    </div>
  );
}

function TrackMap({
  state,
  selectedDriverId,
  onSelect,
}: {
  state: RaceState;
  selectedDriverId: number;
  onSelect: (id: number) => void;
}) {
  const leaderLapMs =
    state.running_order.find((driver) => driver.position === 1)
      ?.last_lap_time_ms ??
    state.selected_driver.recent_pace_ms ??
    90_000;
  const selectedInPit = state.selected_driver.pit_history.some(
    (stop) => stop.lap_number === state.control_lap,
  );
  return (
    <div className="rounded-xl border border-line bg-asphalt p-4">
      <div className="flex justify-between">
        <div>
          <strong>Schematic race orbit</strong>
          <p className="text-xs text-mist">
            Lap progress view · not GPS telemetry
          </p>
        </div>
        <span className="status-chip">
          {state.weather?.rainfall ? "RAIN" : state.race_control.status_label}
        </span>
      </div>
      <div className="relative mx-auto mt-5 aspect-[16/9] max-w-xl">
        <div className="absolute inset-[12%_8%] rounded-[45%] border-[12px] border-line shadow-[inset_0_0_0_1px_rgba(255,255,255,.08)]" />
        <div
          className="absolute bottom-[7%] left-[21%] h-1 w-[28%] bg-signal/50"
          title="Pit lane"
        />
        {state.running_order.slice(0, 20).map((driver, index) => {
          const gapFraction =
            driver.gap_to_leader_ms === null
              ? Math.min(0.92, 0.08 + index * 0.045)
              : Math.min(
                  0.96,
                  Math.max(0, driver.gap_to_leader_ms / leaderLapMs),
                );
          const angle = -Math.PI / 2 - gapFraction * Math.PI * 2;
          const x = 50 + 42 * Math.cos(angle);
          const y = 50 + 35 * Math.sin(angle);
          const inPit = driver.driver_id === selectedDriverId && selectedInPit;
          return (
            <motion.button
              key={driver.driver_id}
              type="button"
              aria-label={`Select ${driver.full_name}`}
              onClick={() => onSelect(driver.driver_id)}
              className={`absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded px-1.5 py-0.5 text-[9px] font-bold shadow-lg ${driver.driver_id === selectedDriverId ? "bg-signal text-white ring-2 ring-white" : "bg-white text-asphalt"}`}
              animate={{
                left: `${inPit ? 33 : x}%`,
                top: `${inPit ? 91 : y}%`,
              }}
              transition={{ type: "spring", stiffness: 80, damping: 18 }}
            >
              {inPit ? "PIT" : driver.abbreviation}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

function EngineerRadio({
  state,
  timeline,
}: {
  state: RaceState;
  timeline: Timeline;
}) {
  const messages = [
    `Lap ${state.control_lap}. ${state.weather?.rainfall ? "Rain reported around the circuit." : "Track currently reported dry."}`,
    state.race_control.status_label !== "GREEN"
      ? `Race control: ${state.race_control.status_label}.`
      : "Race control: track clear.",
    timeline.pit_laps.includes(state.control_lap)
      ? `${state.selected_driver.abbreviation} enters the pit window.`
      : `Tyre age ${state.selected_driver.tyre_life ?? "unknown"}; current compound ${state.selected_driver.compound ?? "unknown"}.`,
    state.nearby_driver_ids.length
      ? `Rejoin traffic: ${state.nearby_driver_ids.length} car${state.nearby_driver_ids.length === 1 ? "" : "s"} inside the critical window.`
      : `Pit lane projection is clear around the rejoin window.`,
    ...state.race_control.latest_messages.slice(0, 2),
  ];
  return (
    <div className="rounded-xl border border-line bg-[#090b0e] p-3">
      <div className="flex items-center justify-between">
        <strong>Engineer radio</strong>
        <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
      </div>
      <div className="mt-2 space-y-1.5" aria-live="polite">
        {messages.map((message, index) => (
          <motion.div
            key={`${state.control_lap}-${index}-${message}`}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.06 }}
            className="border-l-2 border-signal/60 pl-2 text-xs leading-5 text-mist"
          >
            <span className="mr-2 text-[10px] text-signal">
              {String(index + 1).padStart(2, "0")}
            </span>
            {message}
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function buildChapters(laps: Lap[], timeline: Timeline, maxLap: number) {
  const points = [1, ...timeline.pit_laps, maxLap]
    .filter(
      (value, index, array) =>
        value >= 1 && value <= maxLap && array.indexOf(value) === index,
    )
    .sort((a, b) => a - b);
  return points.slice(0, -1).map((start, index) => {
    const end = points[index + 1];
    const lap = laps.find((item) => item.lap_number === start);
    return {
      start,
      end,
      lap: Math.min(start + Math.floor((end - start) / 2), maxLap),
      title:
        index === 0
          ? "Opening stint"
          : end === maxLap
            ? "Final sprint"
            : `Strategy window ${index}`,
      summary: `${lap?.compound ?? "Unknown"} tyres lead into a ${end - start + 1}-lap chapter. Explore the order, gaps, and alternative call at this point.`,
    };
  });
}

function formatGap(value: number | null) {
  if (value === null) return "N/A";
  if (value === 0) return "SELECTED";
  return `${value > 0 ? "+" : ""}${(value / 1000).toFixed(1)}s`;
}
