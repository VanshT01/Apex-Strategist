"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { z } from "zod";
import type { RaceState, SimulationSubmission } from "@/types/api";

const strategyCompound = z.enum([
  "SOFT",
  "MEDIUM",
  "HARD",
  "INTERMEDIATE",
  "WET",
]);
const paceMode = z.enum(["CONSERVATIVE", "BALANCED", "AGGRESSIVE"]);
const inputSchema = z.object({
  pitNowCompound: strategyCompound,
  delayedCompound: strategyCompound,
  pace: paceMode,
  simulationCount: z.number().int().min(100).max(10_000),
  randomSeed: z.number().int().min(0).max(2_147_483_647),
  pitLossDeltaSeconds: z.number().min(-10).max(10),
  degradationPercent: z.number().min(-50).max(50),
});

export function StrategyBuilder({
  controlLap,
  totalLaps,
  loading,
  onSubmit,
  onCancel,
  state,
}: {
  controlLap: number;
  totalLaps: number;
  loading: boolean;
  onSubmit: (submission: SimulationSubmission) => void;
  onCancel?: () => void;
  state?: RaceState;
}) {
  const [pitNowCompound, setPitNowCompound] = useState<
    "SOFT" | "MEDIUM" | "HARD" | "INTERMEDIATE" | "WET"
  >("HARD");
  const [delayedCompound, setDelayedCompound] = useState<
    "SOFT" | "MEDIUM" | "HARD" | "INTERMEDIATE" | "WET"
  >("MEDIUM");
  const [pace, setPace] = useState<"CONSERVATIVE" | "BALANCED" | "AGGRESSIVE">(
    "BALANCED",
  );
  const [error, setError] = useState("");
  const [simulationCount, setSimulationCount] = useState(1000);
  const [randomSeed, setRandomSeed] = useState(42);
  const [decision, setDecision] = useState<string | null>(null);
  const [pitLossDeltaSeconds, setPitLossDeltaSeconds] = useState(0);
  const [degradationPercent, setDegradationPercent] = useState(0);
  const delayedLap = Math.min(controlLap + 3, totalLaps - 1);

  function buildSubmission(selectedStrategyName?: string) {
    const parsed = inputSchema.safeParse({
      pitNowCompound,
      delayedCompound,
      pace,
      simulationCount,
      randomSeed,
      pitLossDeltaSeconds,
      degradationPercent,
    });
    if (!parsed.success || controlLap >= totalLaps) {
      setError(`Choose a control lap before lap ${totalLaps}.`);
      return null;
    }
    setError("");
    return {
      simulation_count: simulationCount,
      random_seed: randomSeed,
      scenario: {
        pit_loss_delta_ms: pitLossDeltaSeconds * 1000,
        tyre_degradation_multiplier: 1 + degradationPercent / 100,
      },
      selected_strategy_name: selectedStrategyName,
      strategies: [
        {
          name: `Pit now · ${pitNowCompound}`,
          pit_lap: controlLap,
          next_compound: pitNowCompound,
          pace_mode: pace,
        },
        {
          name: `Wait 3 laps · ${delayedCompound}`,
          pit_lap: delayedLap,
          next_compound: delayedCompound,
          pace_mode: pace,
        },
        {
          name: "Stay out",
          pit_lap: null,
          next_compound: null,
          pace_mode: pace,
        },
      ],
    } satisfies SimulationSubmission;
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const submission = buildSubmission();
    if (submission) onSubmit(submission);
  }

  function makeDecision(label: string) {
    setDecision(label);
    const selectedStrategyName =
      label === "Box this lap"
        ? `Pit now · ${pitNowCompound}`
        : label === "Stay out"
          ? "Stay out"
          : label === "Wait 3 laps"
            ? `Wait 3 laps · ${delayedCompound}`
            : undefined;
    const submission = buildSubmission(selectedStrategyName);
    if (submission) onSubmit(submission);
  }

  return (
    <section id="strategy-lab" className="panel scroll-mt-24 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Monte Carlo strategy lab</p>
          <h2 className="mt-1 text-2xl font-semibold">Call the next stop</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-mist">
            Compare pit now, a three lap delay, and staying out across seeded,
            explainable outcome simulations anchored to the deterministic model.
          </p>
        </div>
        <span className="rounded-full border border-line px-3 py-2 text-xs text-mist">
          CONTROL LAP {controlLap}
        </span>
      </div>
      <form onSubmit={submit} className="mt-6">
        <motion.div
          layout
          className="mb-5 rounded-xl border border-signal/30 bg-signal/[.06] p-5"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <span className="eyebrow">Decision mode · Lap {controlLap}</span>
              <h3 className="mt-2 text-xl font-semibold">
                What do you want to do?
              </h3>
              <p className="mt-2 text-sm leading-6 text-mist">
                {state?.weather?.rainfall
                  ? "Rain is active. "
                  : "Track signal is dry. "}
                {state?.nearby_driver_ids.length
                  ? `${state.nearby_driver_ids.length} cars threaten the rejoin window. `
                  : "Pit lane rejoin traffic is limited. "}
                {state?.selected_driver.compound ?? "Current"} tyre age:{" "}
                {state?.selected_driver.tyre_life ?? "N/A"} laps.
              </p>
            </div>
            {decision && (
              <span className="status-chip">Last call · {decision}</span>
            )}
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {[
              "Box this lap",
              "Stay out",
              "Wait 3 laps",
              "Override recommendation",
            ].map((label) => (
              <button
                key={label}
                type="button"
                disabled={loading}
                onClick={() => makeDecision(label)}
                className="rounded-lg border border-line bg-asphalt px-4 py-3 text-left text-sm font-semibold transition hover:border-signal hover:bg-signal/10 disabled:opacity-50"
              >
                <span className="mr-2 text-signal">○</span>
                {label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-mist">
            Selecting a call immediately runs the full comparison so the
            engineer can challenge your decision.
          </p>
        </motion.div>
        <div className="grid gap-4 md:grid-cols-3">
          <StrategyControl
            title="Pit now"
            detail={`Stop after lap ${controlLap}`}
            compound={pitNowCompound}
            setCompound={setPitNowCompound}
          />
          <StrategyControl
            title="Delay 3 laps"
            detail={`Stop after lap ${delayedLap}`}
            compound={delayedCompound}
            setCompound={setDelayedCompound}
          />
          <div className="rounded-xl border border-line bg-asphalt p-4">
            <p className="font-semibold">Stay out</p>
            <p className="mt-1 text-xs text-mist">No further stop</p>
            <p className="mt-8 text-sm text-mist">
              Continue the current compound and tyre age.
            </p>
          </div>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <div>
            <label className="label" htmlFor="pace-mode">
              Pace mode
            </label>
            <select
              id="pace-mode"
              className="select min-w-52"
              value={pace}
              onChange={(event) => setPace(event.target.value as typeof pace)}
            >
              <option value="CONSERVATIVE">Conservative</option>
              <option value="BALANCED">Balanced</option>
              <option value="AGGRESSIVE">Aggressive</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="simulation-count">
              Simulations
            </label>
            <select
              id="simulation-count"
              className="select"
              value={simulationCount}
              onChange={(event) =>
                setSimulationCount(Number(event.target.value))
              }
              disabled={loading}
            >
              {[500, 1000, 2500, 5000].map((count) => (
                <option key={count} value={count}>
                  {count.toLocaleString()}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="random-seed">
              Random seed
            </label>
            <input
              id="random-seed"
              className="select"
              type="number"
              min={0}
              max={2_147_483_647}
              step={1}
              value={randomSeed}
              onChange={(event) => setRandomSeed(Number(event.target.value))}
              disabled={loading}
            />
          </div>
        </div>
        <details className="mt-5 rounded-xl border border-line bg-asphalt p-4">
          <summary className="cursor-pointer font-semibold">
            Scenario sandbox
          </summary>
          <p className="mt-2 text-xs leading-5 text-mist">
            These explicit counterfactual adjustments are passed into the
            deterministic and Monte Carlo engines. They are user defined
            scenarios, not predictions.
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <label className="label" htmlFor="pit-loss-adjustment">
                Pit lane loss adjustment · {pitLossDeltaSeconds > 0 ? "+" : ""}
                {pitLossDeltaSeconds}s
              </label>
              <input
                id="pit-loss-adjustment"
                type="range"
                min={-10}
                max={10}
                value={pitLossDeltaSeconds}
                onChange={(event) =>
                  setPitLossDeltaSeconds(Number(event.target.value))
                }
                className="replay-range w-full"
              />
            </div>
            <div>
              <label className="label" htmlFor="degradation-adjustment">
                Tyre degradation · {degradationPercent > 0 ? "+" : ""}
                {degradationPercent}%
              </label>
              <input
                id="degradation-adjustment"
                type="range"
                min={-50}
                max={50}
                step={5}
                value={degradationPercent}
                onChange={(event) =>
                  setDegradationPercent(Number(event.target.value))
                }
                className="replay-range w-full"
              />
            </div>
          </div>
        </details>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-4">
          <p className="max-w-2xl text-xs leading-5 text-mist">
            More simulations improve distribution stability but require more CPU
            time. The same seed and inputs reproduce the same outcomes.
          </p>
          <div className="flex gap-3">
            {loading && onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="rounded-lg border border-line px-5 py-3 text-sm font-semibold"
              >
                Cancel
              </button>
            )}
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-signal px-6 py-3 font-semibold transition hover:bg-[#ff654b] disabled:cursor-wait disabled:opacity-60"
            >
              {loading
                ? `Simulating ${simulationCount.toLocaleString()} outcomes…`
                : "Compare strategies"}
            </button>
          </div>
        </div>
        {error && (
          <p role="alert" className="mt-4 text-sm text-red-300">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

function StrategyControl({
  title,
  detail,
  compound,
  setCompound,
}: {
  title: string;
  detail: string;
  compound: string;
  setCompound: (
    value: "SOFT" | "MEDIUM" | "HARD" | "INTERMEDIATE" | "WET",
  ) => void;
}) {
  return (
    <div className="rounded-xl border border-line bg-asphalt p-4">
      <p className="font-semibold">{title}</p>
      <p className="mt-1 text-xs text-mist">{detail}</p>
      <label className="label mt-5" htmlFor={`compound-${title}`}>
        Next compound
      </label>
      <select
        id={`compound-${title}`}
        className="select"
        value={compound}
        onChange={(event) =>
          setCompound(
            event.target.value as
              "SOFT" | "MEDIUM" | "HARD" | "INTERMEDIATE" | "WET",
          )
        }
      >
        <option>SOFT</option>
        <option>MEDIUM</option>
        <option>HARD</option>
        <option>INTERMEDIATE</option>
        <option>WET</option>
      </select>
    </div>
  );
}
