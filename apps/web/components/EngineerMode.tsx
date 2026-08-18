"use client";

import { motion } from "framer-motion";
import { LapTable } from "@/components/LapTable";
import { PaceChart } from "@/components/PaceChart";
import { useState } from "react";
import { api } from "@/lib/api";
import type {
  Lap,
  RaceState,
  SimulationContext,
  StrategyComparison,
} from "@/types/api";

const compounds = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"] as const;
const compoundColor: Record<string, string> = {
  SOFT: "#ff4b3e",
  MEDIUM: "#ffd447",
  HARD: "#f5f7fa",
  INTERMEDIATE: "#3fd06f",
  WET: "#47a8ff",
};

function tyrePaceLossSeconds(health: number) {
  const wear = 100 - Math.max(0, Math.min(100, health));
  const cliffWear = Math.max(0, wear - 50);
  return 0.015 * wear + 0.00225 * wear ** 2 + 0.006 * cliffWear ** 2;
}

function tyreStateForHealth(health: number) {
  if (health < 5) return "FAILED";
  if (health < 10) return "FAILURE IMMINENT";
  if (health < 30) return "CRITICAL";
  if (health < 60) return "SEVERE";
  if (health < 70) return "HIGH DEGRADATION";
  if (health < 80) return "DEGRADING";
  return "HEALTHY";
}

type Compound = (typeof compounds)[number];
type Projection = NonNullable<
  StrategyComparison["outcomes"][number]["projected_laps"]
>;
type Decision = {
  lap: number;
  call: string;
  result: string;
};

export function EngineerMode({
  sessionId,
  driverId,
  lap,
  maxLap,
  state,
  selectedLaps,
  onLapChange,
}: {
  sessionId: number;
  driverId: number;
  lap: number;
  maxLap: number;
  state: RaceState;
  selectedLaps: Lap[];
  onLapChange: (lap: number) => void;
}) {
  const [selectedCompound, setSelectedCompound] = useState<Compound | null>(
    null,
  );
  const [context, setContext] = useState<SimulationContext | null>(null);
  const [projection, setProjection] = useState<Projection>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastResult, setLastResult] = useState<StrategyComparison | null>(null);
  const [simulatedLapHistory, setSimulatedLapHistory] = useState<
    Record<number, Projection[number]>
  >({});
  const [retirement, setRetirement] = useState<string | null>(null);
  const [finishedAtLap, setFinishedAtLap] = useState<number | null>(null);

  const current: SimulationContext = context ?? {
    current_compound: normaliseCompound(state.selected_driver.compound),
    current_tyre_age: state.selected_driver.tyre_life,
    current_effective_tyre_age: state.selected_driver.tyre_life,
    current_tyre_health_pct: state.selected_driver.tyre_health_percent,
    current_position: state.selected_driver.position,
    current_stint_number: state.selected_driver.stint_number,
    current_completed_laps: state.selected_driver.completed_laps,
    current_timestamp_ms: state.selected_driver.timestamp_ms,
    cumulative_time_delta_ms: 0,
  };
  const projectedCurrentLap = projection.find(
    (item) => item.lap_number === lap,
  );
  const tyreHealth =
    projectedCurrentLap?.tyre_health_percent ??
    current.current_tyre_health_pct ??
    state.selected_driver.tyre_health_percent ??
    100;
  const tyrePaceLoss =
    projectedCurrentLap?.tyre_pace_loss_seconds ??
    (!context ? state.selected_driver.tyre_pace_loss_seconds : undefined) ??
    tyrePaceLossSeconds(tyreHealth);
  const tyreState =
    projectedCurrentLap?.tyre_state ??
    (!context ? state.selected_driver.tyre_state : undefined) ??
    tyreStateForHealth(tyreHealth);
  const finished =
    retirement !== null || finishedAtLap !== null || lap >= maxLap;

  async function advance() {
    if (finished || loading) return;
    setError("");

    if (selectedCompound) {
      await simulateDecision(selectedCompound);
      return;
    }

    const next = projection.find((item) => item.lap_number === lap + 1);
    if (next) {
      recordAndAdvance("Stay out", "Independent race advanced", next);
      return;
    }
    await simulateDecision(null);
  }

  async function simulateDecision(boxCompound: Compound | null) {
    setLoading(true);
    try {
      const primaryName = boxCompound ? `Box · ${boxCompound}` : "Stay out";
      const strategies = boxCompound
        ? [
            {
              name: primaryName,
              pit_lap: lap,
              next_compound: boxCompound,
              pace_mode: "BALANCED" as const,
            },
            {
              name: "Stay out reference",
              pit_lap: null,
              next_compound: null,
              pace_mode: "BALANCED" as const,
            },
          ]
        : [
            {
              name: primaryName,
              pit_lap: null,
              next_compound: null,
              pace_mode: "BALANCED" as const,
            },
            {
              name: "Stay out uncertainty reference",
              pit_lap: null,
              next_compound: null,
              pace_mode: "BALANCED" as const,
            },
          ];
      const result = await api.compare(
        sessionId,
        driverId,
        lap,
        strategies,
        500,
        42 + lap,
        undefined,
        current,
      );
      const outcome = result.outcomes.find((item) => item.name === primaryName);
      const next = outcome?.projected_laps?.find(
        (item) => item.lap_number === lap + 1,
      );
      if (!outcome || !next)
        throw new Error("The race projection did not return the next lap.");
      setProjection(outcome.projected_laps ?? []);
      setLastResult(result);
      recordAndAdvance(
        primaryName,
        boxCompound
          ? `Rejoins around P${outcome.likely_rejoin_position ?? "N/A"}`
          : "Stayed out in the independent race",
        next,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to simulate this decision.",
      );
    } finally {
      setLoading(false);
    }
  }

  function recordAndAdvance(
    call: string,
    result: string,
    next: Projection[number] | null,
  ) {
    setDecisions((items) => [...items, { lap, call, result }]);
    if (next) {
      setSimulatedLapHistory((history) => ({
        ...history,
        [next.lap_number]: next,
      }));
      setContext({
        current_compound: normaliseCompound(next.compound),
        current_tyre_age: next.tyre_age,
        current_effective_tyre_age: next.effective_tyre_age,
        current_tyre_health_pct: next.tyre_health_percent,
        current_position: next.predicted_position,
        current_stint_number: next.stint_number,
        current_completed_laps: next.lap_number,
        current_timestamp_ms: next.cumulative_time_ms,
        cumulative_time_delta_ms:
          next.cumulative_time_ms -
          (next.historical_time_ms ?? next.cumulative_time_ms),
      });
      if (next.dnf) setRetirement(next.status ?? "DNF");
      if (next.status === "CHEQUERED") setFinishedAtLap(next.lap_number);
    }
    setSelectedCompound(null);
    onLapChange(
      next?.status === "CHEQUERED" ? maxLap : Math.min(lap + 1, maxLap),
    );
  }

  const deltaSeconds = current.cumulative_time_delta_ms / 1000;
  const monteCarlo = lastResult?.outcomes[0]?.monte_carlo;
  const effectiveLaps = mergeEngineerLaps(
    selectedLaps,
    simulatedLapHistory,
    finishedAtLap ?? lap,
  );

  return (
    <section className="panel overflow-visible" aria-label="Race engineer mode">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-gradient-to-r from-signal/10 to-transparent px-4 py-2.5">
        <div className="flex items-baseline gap-3">
          <p className="eyebrow">Engineer mode</p>
          <h2 className="text-xl font-semibold">
            Lap {finishedAtLap ?? lap} / {maxLap}
          </h2>
          <span className="hidden text-xs text-mist lg:inline">
            Independent race · you own every pit call
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="status-chip">
            {retirement ? "DNF" : `P${current.current_position ?? "N/A"}`}
          </span>
          <span
            className="status-chip"
            style={{ color: compoundColor[current.current_compound ?? ""] }}
          >
            {current.current_compound ?? "NO TYRE"} ·{" "}
            {current.current_tyre_age ?? "N/A"}L
          </span>
          <span className="status-chip">
            TYRE{" "}
            {tyreHealth < 10 ? tyreHealth.toFixed(1) : Math.round(tyreHealth)}%
          </span>
          <span
            className={`status-chip ${deltaSeconds <= 0 ? "text-emerald-300" : "text-red-300"}`}
          >
            Δ {deltaSeconds > 0 ? "+" : ""}
            {deltaSeconds.toFixed(1)}s
          </span>
          <span className="status-chip">
            RANGE{" "}
            {monteCarlo
              ? `P${monteCarlo.finish_position_p05} to P${monteCarlo.finish_position_p95}`
              : "N/A"}
          </span>
        </div>
      </div>

      <div className="grid items-start gap-3 p-3 xl:grid-cols-[minmax(0,1.5fr)_minmax(310px,.5fr)]">
        <div className="grid gap-3">
          <RaceField
            state={state}
            selectedDriverId={driverId}
            selectedContext={current}
            selectedInPit={
              projection.find(
                (item) => item.lap_number === (finishedAtLap ?? lap),
              )?.pit_stop ?? false
            }
            selectedRetired={retirement !== null}
          />
          <section className="grid gap-3" aria-label="Engineer telemetry">
            <PaceChart laps={effectiveLaps} />
            <LapTable laps={effectiveLaps} />
          </section>
        </div>

        <aside className="space-y-3" aria-label="Engineer decision rail">
          <LiveWeather
            state={state}
            compound={selectedCompound ?? current.current_compound}
          />
          <InterventionPanel state={state} />
          <TyreDegradationGauge
            compound={current.current_compound}
            age={current.current_tyre_age}
            health={tyreHealth}
            paceLossSeconds={tyrePaceLoss}
            tyreState={tyreState}
            source={
              lastResult?.outcomes[0]?.tyre_estimate?.life_source ??
              state.selected_driver.tyre_life_source ??
              undefined
            }
            performanceLife={
              lastResult?.outcomes[0]?.tyre_estimate?.performance_life_laps ??
              state.selected_driver.tyre_performance_life_laps ??
              undefined
            }
            durability={
              lastResult?.outcomes[0]?.tyre_estimate?.durability_laps ??
              state.selected_driver.tyre_durability_laps ??
              undefined
            }
            stintSamples={
              lastResult?.outcomes[0]?.tyre_estimate?.stint_sample_count ??
              state.selected_driver.tyre_stint_sample_count
            }
          />
          {retirement && <PunctureDnf status={retirement} lap={lap} />}

          <div className="rounded-xl border border-line bg-asphalt p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="eyebrow">Your call</p>
                <h3 className="mt-0.5 text-lg font-semibold">
                  {retirement
                    ? "Driver retired"
                    : finished
                      ? "Race complete"
                      : "Box this lap?"}
                </h3>
              </div>
              <span className="text-[10px] text-mist">
                No selection = stay out
              </span>
            </div>

            {!finished && (
              <>
                <div className="mt-2 grid grid-cols-5 gap-1.5">
                  {compounds.map((compound) => (
                    <button
                      key={compound}
                      type="button"
                      title={compound}
                      aria-label={compound}
                      onClick={() =>
                        setSelectedCompound((value) =>
                          value === compound ? null : compound,
                        )
                      }
                      className={`rounded-lg border px-1 py-2 text-center transition ${selectedCompound === compound ? "border-white bg-white/10" : "border-line hover:border-white/30"}`}
                    >
                      <span
                        className="mx-auto mb-1 block h-2 w-2 rounded-full"
                        style={{ backgroundColor: compoundColor[compound] }}
                      />
                      <strong className="text-[9px]">
                        {compound === "INTERMEDIATE"
                          ? "INTER"
                          : compound.slice(0, 4)}
                      </strong>
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  disabled={loading}
                  onClick={advance}
                  className="mt-2 w-full rounded-lg bg-signal px-4 py-2.5 text-sm font-semibold transition hover:bg-[#ff654b] disabled:cursor-wait disabled:opacity-60"
                >
                  {loading
                    ? "Running seeded race model…"
                    : selectedCompound
                      ? `Box for ${selectedCompound} · next lap`
                      : `Stay out · advance to lap ${lap + 1}`}
                </button>
              </>
            )}
            {error && (
              <p className="mt-2 rounded-lg border border-red-400/30 bg-red-400/10 p-2 text-xs text-red-200">
                {error}
              </p>
            )}
          </div>

          <div className="rounded-xl border border-line bg-asphalt p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <strong>Engineer notes</strong>
              <span className="text-mist">{decisions.length} calls</span>
            </div>
            {decisions.length > 0 ? (
              <div className="mt-2 space-y-2">
                {[...decisions].reverse().map((decision) => (
                  <motion.p
                    key={decision.lap}
                    layout
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="border-t border-line/70 pt-2 leading-5 text-mist first:border-0 first:pt-0"
                  >
                    <span className="mr-2 text-signal">LAP {decision.lap}</span>
                    <strong className="text-white">
                      {decision.call}.
                    </strong>{" "}
                    {decision.result}
                  </motion.p>
                ))}
              </div>
            ) : (
              <p className="mt-2 leading-5 text-mist">
                Advance lap by lap. Weather and competitors stay historically
                anchored; your driver follows only your decisions.
              </p>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}

export function mergeEngineerLaps(
  laps: Lap[],
  simulatedHistory: Record<number, Projection[number]>,
  completedLap: number,
): Lap[] {
  return laps
    .filter((item) => item.lap_number <= completedLap)
    .map((item) => {
      const simulated = simulatedHistory[item.lap_number];
      if (!simulated) return item;
      return {
        ...item,
        lap_time_ms: simulated.lap_time_ms,
        timestamp_ms: simulated.cumulative_time_ms,
        compound: simulated.compound,
        tyre_life: simulated.tyre_age,
        stint_number: simulated.stint_number ?? item.stint_number,
        position: simulated.predicted_position,
        pit_in: false,
        pit_out: simulated.pit_stop,
        inaccurate: item.inaccurate,
      };
    });
}

function PunctureDnf({ status, lap }: { status: string; lap: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      className="rounded-xl border border-red-400/60 bg-red-500/10 p-3"
      role="alert"
    >
      <p className="eyebrow">Terminal race event · lap {lap}</p>
      <h3 className="mt-1 text-xl font-semibold text-red-200">DNF: {status}</h3>
      <p className="mt-1 text-xs text-mist">
        Tyre health crossed strictly below 5% during this lap. The simulated
        driver has stopped and no further strategy decisions are available.
      </p>
    </motion.div>
  );
}

function TyreDegradationGauge({
  compound,
  age,
  health,
  paceLossSeconds,
  tyreState,
  source,
  performanceLife,
  durability,
  stintSamples,
}: {
  compound: SimulationContext["current_compound"];
  age: number | null;
  health: number;
  paceLossSeconds: number;
  tyreState: string;
  source?: string;
  performanceLife?: number;
  durability?: number;
  stintSamples?: number;
}) {
  const boundedHealth = Math.max(0, Math.min(100, health));
  const displayedHealth =
    boundedHealth < 10 ? boundedHealth.toFixed(1) : Math.round(boundedHealth);
  const condition = tyreState.replaceAll("_", " ");
  return (
    <div className="rounded-xl border border-line bg-asphalt p-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Tyre degradation</p>
          <h3 className="mt-0.5 text-lg font-semibold">
            {compound ?? "Unknown compound"} · {condition}
          </h3>
          <p className="mt-1 text-xs text-mist">
            Health {displayedHealth}% · age {age ?? "N/A"} laps · tyre penalty +
            {paceLossSeconds.toFixed(1)}s/lap
          </p>
        </div>
        <motion.strong
          key={boundedHealth}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-2xl"
        >
          {displayedHealth}%
        </motion.strong>
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-line"
        role="progressbar"
        aria-label="Modeled tyre performance remaining"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={boundedHealth}
      >
        <motion.div
          className="h-full rounded-full"
          style={{
            backgroundColor:
              boundedHealth >= 70
                ? "#3fd06f"
                : boundedHealth >= 35
                  ? "#ffd447"
                  : "#ff4b3e",
          }}
          initial={false}
          animate={{ width: `${boundedHealth}%` }}
          transition={{ type: "spring", stiffness: 90, damping: 18 }}
        />
      </div>
      <div className="mt-2 flex justify-between text-[10px] uppercase tracking-wider text-mist">
        <span>Tyre cliff</span>
        <span>{source ? source.replaceAll("_", " ") : "event tyre model"}</span>
        <span>New set · 100%</span>
      </div>
      {performanceLife !== undefined && durability !== undefined && (
        <p
          className="mt-2 text-[10px] leading-4 text-mist"
          aria-label={`Tyre life model: ${performanceLife.toFixed(0)} lap performance window, ${durability.toFixed(0)} lap terminal reserve, ${stintSamples ?? 0} event stints`}
        >
          Field model: performance window ≈ {performanceLife.toFixed(0)} laps ·
          terminal reserve ≈ {durability.toFixed(0)} laps · {stintSamples ?? 0}
          event stints
        </p>
      )}
    </div>
  );
}

function RaceField({
  state,
  selectedDriverId,
  selectedContext,
  selectedInPit,
  selectedRetired,
}: {
  state: RaceState;
  selectedDriverId: number;
  selectedContext: SimulationContext;
  selectedInPit: boolean;
  selectedRetired: boolean;
}) {
  const order = simulatedOrder(
    state,
    selectedDriverId,
    selectedContext,
    selectedRetired,
  );

  return (
    <div className="grid items-start gap-3 xl:grid-cols-[.9fr_1.1fr]">
      <RaceGapLadder
        order={order}
        selectedDriverId={selectedDriverId}
        selectedInPit={selectedInPit}
        selectedRetired={selectedRetired}
        lap={state.control_lap}
      />

      <div className="rounded-xl border border-line bg-asphalt">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div>
            <p className="eyebrow">Live order · all drivers</p>
            <strong className="mt-1 block">Gap, tyre and pit status</strong>
          </div>
          <span className="text-xs text-mist">Distance to leader</span>
        </div>
        <div className="p-1.5">
          {order.map((driver) => {
            const inPit =
              driver.driver_id === selectedDriverId
                ? selectedInPit
                : driver.in_pit;
            return (
              <motion.div
                layout
                key={driver.driver_id}
                className={`mb-0.5 grid grid-cols-[1.7rem_3rem_1fr_auto_auto] items-center gap-2 rounded-lg px-2 py-1.5 ${driver.driver_id === selectedDriverId ? "bg-white/10 ring-1 ring-signal" : "bg-white/[.025]"}`}
              >
                <strong>{driver.position ?? "N/A"}</strong>
                <strong>{driver.abbreviation}</strong>
                <span className="min-w-0 truncate text-xs text-mist">
                  {driver.team_name ?? driver.status ?? "N/A"}
                </span>
                <span className="flex items-center gap-1.5 text-xs">
                  <i
                    className="h-2.5 w-2.5 rounded-full"
                    style={{
                      backgroundColor:
                        compoundColor[driver.compound ?? ""] ?? "#777",
                    }}
                  />
                  {driver.compound ?? "N/A"}
                </span>
                <span className="min-w-20 text-right font-mono text-xs">
                  {selectedRetired && driver.driver_id === selectedDriverId ? (
                    <strong className="text-red-300">TYRE FAILURE · DNF</strong>
                  ) : inPit ? (
                    <strong className="text-yellow-300">IN PIT</strong>
                  ) : (
                    formatLeaderGap(
                      driver.gap_to_leader_ms,
                      driver.position,
                      driver.status,
                    )
                  )}
                </span>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function RaceGapLadder({
  order,
  selectedDriverId,
  selectedInPit,
  selectedRetired,
  lap,
}: {
  order: ReturnType<typeof simulatedOrder>;
  selectedDriverId: number;
  selectedInPit: boolean;
  selectedRetired: boolean;
  lap: number;
}) {
  const maximumGap = Math.max(
    1,
    ...order.map((driver) => driver.gap_to_leader_ms ?? 0),
  );
  return (
    <div className="rounded-xl border border-line bg-asphalt p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Field gap ladder · all drivers</p>
          <h3 className="mt-0.5 text-base font-semibold">
            Distance from race leader
          </h3>
        </div>
        <span className="status-chip">LAP {lap}</span>
      </div>
      <div
        className="mt-2 pr-1"
        role="img"
        aria-label={`Gap ladder showing ${order.length} drivers in effective race order`}
      >
        {order.map((driver) => {
          const selected = driver.driver_id === selectedDriverId;
          const inPit = selected ? selectedInPit : driver.in_pit;
          const gap = driver.gap_to_leader_ms;
          const width =
            driver.position === 1 || gap == null
              ? 0
              : Math.max(2, Math.sqrt(gap / maximumGap) * 100);
          return (
            <div
              key={driver.driver_id}
              className="grid grid-cols-[1.5rem_2.7rem_1fr_auto] items-center gap-2 border-b border-line/50 py-1.5 text-xs"
            >
              <strong>{driver.position}</strong>
              <strong className={selected ? "text-signal" : "text-white"}>
                {driver.abbreviation}
              </strong>
              <span className="relative h-1.5 overflow-hidden rounded-full bg-line">
                <motion.span
                  className={`absolute inset-y-0 left-0 rounded-full ${selected ? "bg-signal" : inPit ? "bg-yellow-300" : "bg-white/60"}`}
                  animate={{ width: `${width}%` }}
                  transition={{ type: "spring", stiffness: 100, damping: 22 }}
                />
              </span>
              <span className="min-w-16 text-right font-mono text-[10px] text-mist">
                {selectedRetired && selected
                  ? "DNF"
                  : inPit
                    ? "PIT"
                    : formatLeaderGap(gap, driver.position, driver.status)}
              </span>
            </div>
          );
        })}
      </div>
      <p className="mt-1 text-[10px] text-mist">
        Bar length uses a square root time scale so the leading pack remains
        readable.
      </p>
    </div>
  );
}

function InterventionPanel({ state }: { state: RaceState }) {
  const intervention = ["SAFETY CAR", "VSC", "VSC ENDING"].includes(
    state.race_control.status_label,
  );
  if (!intervention) return null;
  const boxed = (state.race_control.boxed_driver_ids ?? [])
    .map(
      (id) =>
        state.running_order.find((driver) => driver.driver_id === id)
          ?.abbreviation,
    )
    .filter(Boolean);
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-yellow-300/50 bg-yellow-300/10 p-3"
      role="status"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Race control intervention</p>
          <h3 className="mt-0.5 text-lg font-semibold text-yellow-200">
            {state.race_control.status_label}
          </h3>
        </div>
        <span className="status-chip">
          SINCE LAP{" "}
          {state.race_control.intervention_start_lap ?? state.control_lap}
        </span>
      </div>
      <p className="mt-1 text-xs text-mist">
        Boxed during this intervention:{" "}
        {boxed.length ? boxed.join(", ") : "none yet"}.
      </p>
    </motion.div>
  );
}

export function simulatedOrder(
  state: RaceState,
  selectedDriverId: number,
  context: SimulationContext,
  selectedRetired = false,
) {
  const original = state.running_order.find(
    (driver) => driver.driver_id === selectedDriverId,
  );
  const historicalSelectedTimestamp =
    state.selected_driver.timestamp_ms ?? original?.timestamp_ms ?? null;
  const projectedSelectedTimestamp =
    context.current_timestamp_ms ??
    (historicalSelectedTimestamp === null
      ? null
      : historicalSelectedTimestamp + context.cumulative_time_delta_ms);
  const timed = state.running_order.map((driver) => {
    const selected = driver.driver_id === selectedDriverId;
    const reconstructedTimestamp =
      driver.timestamp_ms ??
      (historicalSelectedTimestamp !== null &&
      driver.gap_to_selected_ms !== null
        ? historicalSelectedTimestamp + driver.gap_to_selected_ms
        : null);
    return {
      ...driver,
      compound: selected ? context.current_compound : driver.compound,
      tyre_life: selected ? context.current_tyre_age : driver.tyre_life,
      stint_number: selected
        ? (context.current_stint_number ?? driver.stint_number)
        : driver.stint_number,
      completed_laps: selected
        ? (context.current_completed_laps ?? driver.completed_laps)
        : driver.completed_laps,
      timestamp_ms:
        selected && projectedSelectedTimestamp !== null
          ? projectedSelectedTimestamp
          : reconstructedTimestamp,
      selectedRetired: selected && selectedRetired,
    };
  });
  timed.sort((left, right) => {
    if (left.selectedRetired !== right.selectedRetired)
      return left.selectedRetired ? 1 : -1;
    if (left.completed_laps !== right.completed_laps)
      return right.completed_laps - left.completed_laps;
    if (left.timestamp_ms !== null && right.timestamp_ms !== null)
      return left.timestamp_ms - right.timestamp_ms;
    if (left.timestamp_ms !== null) return -1;
    if (right.timestamp_ms !== null) return 1;
    return (left.position ?? 999) - (right.position ?? 999);
  });
  const positioned = timed.map((driver, index) => ({
    ...driver,
    position: index + 1,
  }));
  const leader = positioned[0];
  const leaderTimestamp = leader?.timestamp_ms ?? null;

  return positioned
    .map((driver) => {
      const comparableToLeader =
        leaderTimestamp !== null &&
        driver.timestamp_ms != null &&
        driver.completed_laps === leader?.completed_laps;
      const comparableToSelected =
        projectedSelectedTimestamp !== null &&
        driver.timestamp_ms != null &&
        driver.completed_laps ===
          (context.current_completed_laps ??
            state.selected_driver.completed_laps);
      return {
        ...driver,
        gap_to_leader_ms:
          driver.position === 1
            ? 0
            : comparableToLeader
              ? Math.max(0, driver.timestamp_ms! - leaderTimestamp)
              : driver.gap_to_leader_ms,
        gap_to_selected_ms: comparableToSelected
          ? driver.timestamp_ms! - projectedSelectedTimestamp
          : driver.gap_to_selected_ms,
      };
    })
    .sort(
      (left, right) =>
        (left.position ?? 999) - (right.position ?? 999) ||
        right.completed_laps - left.completed_laps,
    );
}

function formatLeaderGap(
  gapMs: number | null,
  position: number | null,
  status: string | null,
) {
  if (position === 1) return "LEADER";
  if (status?.startsWith("+")) return status.toUpperCase();
  if (gapMs === null) return "N/A";
  return `+${(Math.max(0, gapMs) / 1000).toFixed(3)}s`;
}

function LiveWeather({
  state,
  compound,
}: {
  state: RaceState;
  compound: SimulationContext["current_compound"];
}) {
  const weather = state.weather;
  const wetTyre = compound === "INTERMEDIATE" || compound === "WET";
  const incompatible = weather?.rainfall ? !wetTyre : wetTyre;
  return (
    <div
      className={`rounded-xl border p-3 ${weather?.rainfall ? "border-blue-400/50 bg-blue-400/10" : "border-line bg-asphalt"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Live weather · lap {state.control_lap}</p>
          <h3 className="mt-0.5 text-lg font-semibold">
            {weather?.rainfall ? "Rain on circuit" : "Dry track"}
          </h3>
        </div>
        <span className="status-chip">RECORDED LAP OBSERVATION</span>
      </div>
      <div className="mt-2 grid grid-cols-4 gap-1.5">
        <Metric
          label="Track"
          value={
            weather?.track_temperature == null
              ? "N/A"
              : `${weather.track_temperature.toFixed(1)}°C`
          }
        />
        <Metric
          label="Air"
          value={
            weather?.air_temperature == null
              ? "N/A"
              : `${weather.air_temperature.toFixed(1)}°C`
          }
        />
        <Metric
          label="Humidity"
          value={
            weather?.humidity == null
              ? "N/A"
              : `${weather.humidity.toFixed(0)}%`
          }
        />
        <Metric
          label="Wind"
          value={
            weather?.wind_speed == null
              ? "N/A"
              : `${weather.wind_speed.toFixed(1)} m/s`
          }
        />
      </div>
      {incompatible && (
        <p className="mt-2 rounded-lg border border-yellow-300/40 bg-yellow-300/10 p-2 text-xs text-yellow-100">
          {weather?.rainfall
            ? `${compound} is unsafe for the recorded wet conditions: major pace and wear penalties apply.`
            : `${compound} is the wrong tyre for a dry track: overheating, wear and a major pace penalty apply.`}
        </p>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel/60 p-2">
      <span className="text-[10px] uppercase tracking-wider text-mist">
        {label}
      </span>
      <motion.strong
        key={value}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="mt-0.5 block text-sm"
      >
        {value}
      </motion.strong>
    </div>
  );
}

function normaliseCompound(value: string | null | undefined): Compound | null {
  return compounds.find((compound) => compound === value) ?? null;
}
