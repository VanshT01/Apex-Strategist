"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { StrategyComparison } from "@/types/api";

export function InteractiveStrategyDeck({
  result,
  selectedStrategyName,
}: {
  result: StrategyComparison;
  selectedStrategyName?: string;
}) {
  const [expanded, setExpanded] = useState(
    selectedStrategyName ?? result.recommendation.strategy_name,
  );
  const [exploring, setExploring] = useState<number | null>(null);
  const recommended = result.outcomes.find(
    (item) => item.name === result.recommendation.strategy_name,
  );
  const aggregate = recommended?.monte_carlo;
  const radar = result.outcomes.map((outcome) => ({
    strategy: outcome.name.replace(/ · .*/, ""),
    values: [
      { axis: "Win", value: (outcome.monte_carlo?.win_probability ?? 0) * 100 },
      {
        axis: "Finish",
        value: Math.max(
          0,
          105 - (outcome.monte_carlo?.median_predicted_finish ?? 20) * 5,
        ),
      },
      {
        axis: "Low risk",
        value: (1 - (outcome.monte_carlo?.degradation_risk ?? 1)) * 100,
      },
      {
        axis: "Traffic",
        value: (1 - (outcome.monte_carlo?.traffic_risk ?? 1)) * 100,
      },
      {
        axis: "Tyre life",
        value: Math.max(0, 100 - outcome.final_tyre_age * 1.8),
      },
      {
        axis: "Baseline",
        value: (outcome.monte_carlo?.improve_stay_out_probability ?? 0) * 100,
      },
    ],
  }));
  const radarData = [
    "Win",
    "Finish",
    "Low risk",
    "Traffic",
    "Tyre life",
    "Baseline",
  ].map((axis, axisIndex) => ({
    axis,
    ...Object.fromEntries(
      radar.map((series) => [series.strategy, series.values[axisIndex].value]),
    ),
  }));

  return (
    <div className="grid gap-6">
      {aggregate && (
        <MonteCarloFormation
          distribution={aggregate.finish_position_distribution}
          count={aggregate.simulation_count}
        />
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        {result.outcomes.map((outcome) => {
          const mc = outcome.monte_carlo;
          const open = expanded === outcome.name;
          const recommendedCard =
            outcome.name === result.recommendation.strategy_name;
          const userCall = outcome.name === selectedStrategyName;
          return (
            <motion.article
              layout
              key={outcome.name}
              className={`overflow-hidden rounded-2xl border ${recommendedCard ? "border-signal/60 bg-signal/[.07]" : "border-line bg-panel"}`}
            >
              <button
                type="button"
                className="w-full p-5 text-left"
                onClick={() => setExpanded(open ? "" : outcome.name)}
                aria-expanded={open}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <span className="text-[10px] uppercase tracking-[.18em] text-signal">
                      {userCall
                        ? "Your call"
                        : recommendedCard
                          ? "Engineer call"
                          : "Alternative"}
                    </span>
                    <h3 className="mt-1 text-lg font-semibold uppercase">
                      {outcome.name}
                    </h3>
                  </div>
                  <motion.span
                    animate={{ rotate: open ? 180 : 0 }}
                    className="text-mist"
                  >
                    ⌄
                  </motion.span>
                </div>
                <div className="mt-5 grid grid-cols-3 gap-2">
                  <CardMetric
                    label="Expected"
                    value={`P${mc?.median_predicted_finish.toFixed(0) ?? outcome.predicted_finish}`}
                  />
                  <CardMetric label="Win" value={pct(mc?.win_probability)} />
                  <CardMetric
                    label="Risk"
                    value={risk(
                      Math.max(
                        mc?.traffic_risk ?? 0,
                        mc?.degradation_risk ?? 0,
                      ),
                    )}
                  />
                </div>
              </button>
              <AnimatePresence initial={false}>
                {open && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="border-t border-line px-5 py-4 text-sm">
                      <div className="grid grid-cols-2 gap-3">
                        <Detail
                          label="Rejoin"
                          value={
                            outcome.likely_rejoin_position
                              ? `P${outcome.likely_rejoin_position}`
                              : "No stop"
                          }
                        />
                        <Detail
                          label="90% range"
                          value={
                            mc
                              ? `P${mc.finish_position_p05} to P${mc.finish_position_p95}`
                              : "N/A"
                          }
                        />
                        <Detail
                          label="Tyre at finish"
                          value={`${outcome.next_compound ?? "Current"} · ${outcome.final_tyre_age.toFixed(0)} laps`}
                        />
                        <Detail
                          label="Beats stay out"
                          value={pct(mc?.improve_stay_out_probability)}
                        />
                      </div>
                      <div className="mt-4">
                        <span className="text-xs text-mist">
                          Degradation exposure
                        </span>
                        <div className="mt-2 h-1.5 rounded-full bg-line">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{
                              width: `${(mc?.degradation_risk ?? outcome.degradation_risk) * 100}%`,
                            }}
                            className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-yellow-300 to-signal"
                          />
                        </div>
                      </div>
                      <p className="mt-4 leading-6 text-mist">
                        {recommendedCard
                          ? result.recommendation.explanation
                          : outcome.assumptions[0]}
                      </p>
                      <CounterfactualReplay
                        strategyName={outcome.name}
                        laps={outcome.projected_laps ?? []}
                      />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.article>
          );
        })}
      </div>

      <div className="grid gap-6 xl:grid-cols-[.9fr_1.1fr]">
        <article className="panel p-5">
          <p className="eyebrow">Decision matrix</p>
          <h3 className="mt-1 text-xl font-semibold">Strategy resilience</h3>
          <p className="mt-2 text-xs text-mist">
            Normalized comparison; higher is stronger. Select a strategy card
            for exact values.
          </p>
          <div className="mt-3 h-[330px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="#34383e" />
                <PolarAngleAxis
                  dataKey="axis"
                  tick={{ fill: "#a8a29e", fontSize: 11 }}
                />
                {radar.map((series, index) => (
                  <Radar
                    key={series.strategy}
                    name={series.strategy}
                    dataKey={series.strategy}
                    stroke={["#ff4b3e", "#f6c945", "#54a6ff"][index]}
                    fill={["#ff4b3e", "#f6c945", "#54a6ff"][index]}
                    fillOpacity={0.08}
                  />
                ))}
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </article>
        <article className="panel p-5">
          <p className="eyebrow">Probability explorer</p>
          <h3 className="mt-1 text-xl font-semibold">
            Select a finishing position
          </h3>
          {aggregate ? (
            <div className="mt-5 space-y-2">
              {aggregate.finish_position_distribution.map((bucket) => (
                <button
                  type="button"
                  key={bucket.position}
                  onClick={() => setExploring(bucket.position)}
                  className={`grid w-full grid-cols-[2.5rem_1fr_4rem] items-center gap-3 rounded-lg p-2 text-left transition ${exploring === bucket.position ? "bg-white/10" : "hover:bg-white/5"}`}
                >
                  <strong>P{bucket.position}</strong>
                  <span className="h-2 overflow-hidden rounded-full bg-line">
                    <motion.span
                      initial={{ width: 0 }}
                      animate={{ width: `${bucket.probability * 100}%` }}
                      className="block h-full rounded-full bg-signal"
                    />
                  </span>
                  <span className="text-right font-mono text-sm">
                    {pct(bucket.probability)}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-5 text-mist">No distribution available.</p>
          )}
          {exploring && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-4 rounded-lg border border-line bg-asphalt p-4 text-sm text-mist"
            >
              P{exploring} occurs when the combined pit loss, degradation,
              traffic, and competitor draws place this strategy in that
              classification band. Individual trajectories are not stored.
            </motion.div>
          )}
        </article>
      </div>

      <article className="panel p-5">
        <p className="eyebrow">Engineer notebook</p>
        <h3 className="mt-1 text-xl font-semibold">Automatic decision notes</h3>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {[
            result.recommendation.primary_advantage,
            result.recommendation.key_risk,
            result.recommendation.uncertainty_note,
            aggregate
              ? `${pct(aggregate.improve_stay_out_probability)} chance of beating the no stop baseline.`
              : null,
          ]
            .filter(Boolean)
            .map((note, index) => (
              <motion.p
                key={note}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.08 }}
                className="rounded-lg border border-line bg-asphalt p-4 text-sm leading-6 text-mist"
              >
                <span className="mr-2 text-signal">0{index + 1}</span>
                {note}
              </motion.p>
            ))}
        </div>
      </article>
    </div>
  );
}

function CounterfactualReplay({
  strategyName,
  laps,
}: {
  strategyName: string;
  laps: Array<{
    lap_number: number;
    compound: string;
    tyre_age: number;
    lap_time_ms: number;
    predicted_position: number;
    pit_stop: boolean;
  }>;
}) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing || !laps.length) return;
    const timer = window.setInterval(() => {
      setIndex((current) => {
        if (current >= laps.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 260);
    return () => window.clearInterval(timer);
  }, [laps.length, playing]);
  if (!laps.length) return null;
  const lap = laps[index];
  return (
    <div className="mt-4 rounded-xl border border-line bg-[#090b0e] p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <span className="text-[10px] uppercase tracking-wider text-signal">
            Counterfactual continuation
          </span>
          <strong className="mt-1 block">
            Lap {lap.lap_number} · P{lap.predicted_position}
          </strong>
        </div>
        <button
          type="button"
          onClick={() => {
            if (index === laps.length - 1) setIndex(0);
            setPlaying((value) => !value);
          }}
          className="control-button"
        >
          {playing ? "Pause" : index ? "Continue replay" : "Replay consequence"}
        </button>
      </div>
      <div className="relative mt-4 h-12 overflow-hidden rounded-lg bg-white/[.04]">
        <div className="absolute inset-x-3 top-1/2 h-px bg-line" />
        <motion.div
          className="absolute top-2 grid h-8 w-8 place-items-center rounded-full bg-signal text-[10px] font-bold"
          animate={{
            left: `${Math.max(2, 96 - lap.predicted_position * 4.5)}%`,
          }}
          transition={{ type: "spring", stiffness: 110, damping: 18 }}
        >
          P{lap.predicted_position}
        </motion.div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <Detail label="Tyre" value={lap.compound} />
        <Detail label="Age" value={`${lap.tyre_age.toFixed(0)} laps`} />
        <Detail
          label={lap.pit_stop ? "Pit event" : "Lap time"}
          value={
            lap.pit_stop ? "BOX" : `${(lap.lap_time_ms / 1000).toFixed(1)}s`
          }
        />
      </div>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-line">
        <motion.div
          className="h-full bg-signal"
          animate={{ width: `${((index + 1) / laps.length) * 100}%` }}
        />
      </div>
      <p className="mt-2 text-[10px] text-mist">
        {strategyName} against recorded competitor trajectories and historical
        race conditions.
      </p>
    </div>
  );
}

function MonteCarloFormation({
  distribution,
  count,
}: {
  distribution: Array<{ position: number; probability: number }>;
  count: number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (navigator.userAgent.includes("jsdom")) return;
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    let frame = 0;
    let animation = 0;
    const dots = Array.from({ length: Math.min(count, 1000) }, (_, index) => ({
      x: (index % 50) / 49,
      y: Math.floor(index / 50) / 20,
      target:
        distribution[index % Math.max(distribution.length, 1)]?.position ?? 1,
    }));
    const draw = () => {
      frame += 1;
      context.clearRect(0, 0, 1000, 220);
      dots.forEach((dot, index) => {
        const settle = Math.min(frame / 55, 1);
        const targetY =
          ((dot.target - 1) / Math.max(distribution.length, 1)) * 180 + 18;
        const y = (dot.y * 180 + 18) * (1 - settle) + targetY * settle;
        context.fillStyle =
          index % 7 === 0 ? "#ff4b3e" : "rgba(255,255,255,.55)";
        context.fillRect(dot.x * 970 + 12, y, 3, 3);
      });
      if (frame < 60) animation = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(animation);
  }, [count, distribution]);
  return (
    <article className="panel overflow-hidden p-5">
      <div className="flex items-end justify-between">
        <div>
          <p className="eyebrow">Monte Carlo formation</p>
          <h3 className="mt-1 text-xl font-semibold">
            {count.toLocaleString()} race outcomes settling
          </h3>
        </div>
        <span className="text-xs text-mist">Seeded · reproducible</span>
      </div>
      <canvas
        ref={canvas}
        width={1000}
        height={220}
        className="mt-4 h-40 w-full rounded-lg bg-asphalt"
        aria-label={`${count} simulated race outcomes animate into finishing position groups`}
      />
    </article>
  );
}

function CardMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="block text-[10px] uppercase tracking-wider text-mist">
        {label}
      </span>
      <strong className="mt-1 block text-lg">{value}</strong>
    </div>
  );
}
function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-asphalt p-3">
      <span className="text-[10px] uppercase text-mist">{label}</span>
      <strong className="mt-1 block">{value}</strong>
    </div>
  );
}
function pct(value: number | null | undefined) {
  return value == null ? "N/A" : `${(value * 100).toFixed(1)}%`;
}
function risk(value: number) {
  return value < 0.34 ? "Low" : value < 0.67 ? "Medium" : "High";
}
