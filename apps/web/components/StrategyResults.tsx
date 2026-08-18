"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { StrategyComparison } from "@/types/api";
import { InteractiveStrategyDeck } from "./InteractiveStrategyDeck";
import { TyreBadge } from "./TyreBadge";

function delta(ms: number | null) {
  if (ms === null) return "N/A";
  const sign = ms > 0 ? "+" : ms < 0 ? "−" : "";
  return `${sign}${(Math.abs(ms) / 1000).toFixed(1)}s`;
}

function percent(value: number | null) {
  return value === null ? "N/A" : `${(value * 100).toFixed(1)}%`;
}

function risk(value: number) {
  return value < 0.34 ? "Low" : value < 0.67 ? "Medium" : "High";
}

export function StrategyResults({
  result,
  selectedStrategyName,
}: {
  result: StrategyComparison;
  selectedStrategyName?: string;
}) {
  const recommended = result.outcomes.find(
    (outcome) => outcome.name === result.recommendation.strategy_name,
  );
  const recommendedAggregate = recommended?.monte_carlo;
  const probabilityData = result.outcomes
    .filter((outcome) => outcome.monte_carlo)
    .map((outcome) => ({
      strategy: outcome.name.replace(/ · .*/, ""),
      Win: (outcome.monte_carlo?.win_probability ?? 0) * 100,
      Podium: (outcome.monte_carlo?.podium_probability ?? 0) * 100,
      Points: (outcome.monte_carlo?.points_probability ?? 0) * 100,
    }));

  return (
    <section className="grid gap-6" aria-live="polite">
      <article className="overflow-hidden rounded-2xl border border-signal/40 bg-signal/[.08] p-6">
        <p className="eyebrow">Recommended call</p>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-3xl font-semibold tracking-[-.03em]">
            {result.recommendation.strategy_name}
          </h2>
          {recommendedAggregate ? (
            <span className="font-mono text-2xl">
              Median P{recommendedAggregate.median_predicted_finish.toFixed(0)}
            </span>
          ) : recommended ? (
            <span className="font-mono text-2xl">
              P{recommended.predicted_finish}
            </span>
          ) : null}
        </div>
        <p className="mt-4 max-w-4xl leading-7 text-stone-200">
          {result.recommendation.explanation}
        </p>
        {result.recommendation.uncertainty_note && (
          <p className="mt-3 text-sm text-mist">
            {result.recommendation.uncertainty_note}
          </p>
        )}
      </article>

      <InteractiveStrategyDeck
        result={result}
        selectedStrategyName={selectedStrategyName}
      />

      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[1180px] text-left text-sm">
          <caption className="sr-only">
            Seeded Monte Carlo strategy probability comparison
          </caption>
          <thead className="bg-asphalt/60 text-xs uppercase tracking-wider text-mist">
            <tr>
              {[
                "Strategy",
                "Median finish",
                "Win",
                "Podium",
                "Points",
                "Median vs baseline",
                "90% finish range",
                "Beats stay out",
                "Deterministic",
                "Risks",
              ].map((label) => (
                <th key={label} className="px-5 py-3 font-medium">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.outcomes.map((outcome) => {
              const aggregate = outcome.monte_carlo;
              return (
                <tr
                  key={outcome.name}
                  className={`border-t border-line ${outcome.name === result.recommendation.strategy_name ? "bg-signal/[.06]" : ""}`}
                >
                  <td className="px-5 py-4">
                    <strong>{outcome.name}</strong>
                    <div className="mt-2">
                      <TyreBadge compound={outcome.next_compound} />
                    </div>
                  </td>
                  <td className="px-5 py-4 text-lg font-semibold">
                    {aggregate
                      ? `P${aggregate.median_predicted_finish.toFixed(0)}`
                      : "N/A"}
                  </td>
                  <td className="px-5 py-4">
                    {percent(aggregate?.win_probability ?? null)}
                  </td>
                  <td className="px-5 py-4">
                    {percent(aggregate?.podium_probability ?? null)}
                  </td>
                  <td className="px-5 py-4">
                    {percent(aggregate?.points_probability ?? null)}
                  </td>
                  <td
                    className={`px-5 py-4 font-mono ${(aggregate?.median_time_vs_deterministic_baseline_ms ?? 0) <= 0 ? "text-emerald-300" : "text-red-300"}`}
                  >
                    {delta(
                      aggregate?.median_time_vs_deterministic_baseline_ms ??
                        null,
                    )}
                  </td>
                  <td className="px-5 py-4">
                    {aggregate
                      ? `P${aggregate.finish_position_p05} to P${aggregate.finish_position_p95}`
                      : "N/A"}
                  </td>
                  <td className="px-5 py-4">
                    {percent(aggregate?.improve_stay_out_probability ?? null)}
                  </td>
                  <td className="px-5 py-4">
                    P{outcome.predicted_finish} ·{" "}
                    {delta(outcome.time_vs_baseline_ms)}
                    {aggregate && (
                      <span className="mt-1 block text-xs text-mist">
                        MC shift{" "}
                        {delta(
                          aggregate.median_total_time_ms -
                            outcome.predicted_total_time_ms,
                        )}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-4 text-xs leading-5 text-mist">
                    Traffic{" "}
                    {risk(aggregate?.traffic_risk ?? outcome.traffic_risk)}
                    <br />
                    Degradation{" "}
                    {risk(
                      aggregate?.degradation_risk ?? outcome.degradation_risk,
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {recommendedAggregate && (
        <div className="grid gap-6 xl:grid-cols-2">
          <ChartCard
            title="Recommended finish distribution"
            summary={`${recommended?.name} most often finishes P${recommendedAggregate.most_likely_finish}; its 90% simulated range is P${recommendedAggregate.finish_position_p05} to P${recommendedAggregate.finish_position_p95}.`}
          >
            <ResponsiveContainer width="100%" height={270}>
              <BarChart
                data={recommendedAggregate.finish_position_distribution.map(
                  (bucket) => ({
                    position: `P${bucket.position}`,
                    probability: bucket.probability * 100,
                  }),
                )}
              >
                <CartesianGrid stroke="#343434" vertical={false} />
                <XAxis dataKey="position" stroke="#a8a29e" />
                <YAxis unit="%" stroke="#a8a29e" />
                <Tooltip
                  formatter={(value) => `${Number(value).toFixed(1)}%`}
                />
                <Bar dataKey="probability" fill="#ff4b2b" name="Probability" />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard
            title="Recommended time delta distribution"
            summary={`${recommended?.name} has a median delta of ${delta(recommendedAggregate.median_time_vs_deterministic_baseline_ms)} versus the deterministic stay out baseline.`}
          >
            <ResponsiveContainer width="100%" height={270}>
              <BarChart
                data={recommendedAggregate.time_delta_histogram.map(
                  (bucket) => ({
                    interval: `${(bucket.lower_ms / 1000).toFixed(1)}s`,
                    probability: bucket.probability * 100,
                  }),
                )}
              >
                <CartesianGrid stroke="#343434" vertical={false} />
                <XAxis
                  dataKey="interval"
                  stroke="#a8a29e"
                  interval="preserveStartEnd"
                />
                <YAxis unit="%" stroke="#a8a29e" />
                <Tooltip
                  formatter={(value) => `${Number(value).toFixed(1)}%`}
                />
                <Bar dataKey="probability" fill="#f59e0b" name="Probability" />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {probabilityData.length > 0 && (
        <ChartCard
          title="Headline outcome probabilities"
          summary={probabilityData
            .map(
              (item) =>
                `${item.strategy}: ${item.Win.toFixed(1)}% win, ${item.Podium.toFixed(1)}% podium, ${item.Points.toFixed(1)}% points`,
            )
            .join(". ")}
        >
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={probabilityData}>
              <CartesianGrid stroke="#343434" vertical={false} />
              <XAxis dataKey="strategy" stroke="#a8a29e" />
              <YAxis unit="%" stroke="#a8a29e" />
              <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />
              <Legend />
              <Bar dataKey="Win" fill="#ff4b2b" />
              <Bar dataKey="Podium" fill="#f59e0b" />
              <Bar dataKey="Points" fill="#38bdf8" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <article className="panel p-5">
          <p className="eyebrow">Reality comparison</p>
          <h3 className="mt-2 text-xl font-semibold">What actually happened</h3>
          <div className="mt-5 grid grid-cols-2 gap-4">
            <Metric
              label="Actual finish"
              value={
                result.actual_strategy.actual_finish
                  ? `P${result.actual_strategy.actual_finish}`
                  : "N/A"
              }
            />
            <Metric
              label="Recorded stops after control"
              value={String(result.actual_strategy.remaining_stops.length)}
            />
          </div>
          <div className="mt-4 text-sm text-mist">
            {result.actual_strategy.remaining_stops.length
              ? result.actual_strategy.remaining_stops
                  .map(
                    (stop) =>
                      `L${stop.pit_lap} → ${stop.next_compound ?? "unknown"}`,
                  )
                  .join(" · ")
              : "No further recorded stop."}
          </div>
        </article>
        <article className="panel p-5">
          <p className="eyebrow">Model provenance</p>
          <h3 className="mt-2 text-xl font-semibold">
            {result.engine_version}
          </h3>
          <p className="mt-4 text-sm leading-6 text-mist">
            {result.simulation_count.toLocaleString()} runs · seed{" "}
            {result.random_seed} ·{" "}
            {result.calculation_time_ms?.toFixed(1) ?? "N/A"}ms simulation
            calculation. Pit loss:{" "}
            {(result.pit_loss.estimated_ms / 1000).toFixed(1)}s from{" "}
            {result.pit_loss.sample_count} samples.
          </p>
        </article>
      </div>

      <details className="panel p-5">
        <summary className="cursor-pointer text-lg font-semibold">
          Simulation assumptions and uncertainty sources
        </summary>
        <ul className="mt-4 grid gap-2 text-sm leading-6 text-mist">
          {result.assumptions.map((assumption) => (
            <li key={assumption}>• {assumption}</li>
          ))}
        </ul>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-xs">
            <thead className="text-mist">
              <tr>
                <th className="pb-2">Variable</th>
                <th className="pb-2">Source</th>
                <th className="pb-2">Samples</th>
                <th className="pb-2">Scale</th>
                <th className="pb-2">Fallback</th>
              </tr>
            </thead>
            <tbody>
              {result.uncertainty_sources.map((source) => (
                <tr key={source.variable} className="border-t border-line">
                  <td className="py-2">{source.variable}</td>
                  <td className="py-2">{source.source.replaceAll("_", " ")}</td>
                  <td className="py-2">{source.sample_count}</td>
                  <td className="py-2">{source.scale_ms.toFixed(0)}ms</td>
                  <td className="py-2">{source.fallback ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className="text-xs leading-5 text-mist">{result.disclaimer}</p>
    </section>
  );
}

function ChartCard({
  title,
  summary,
  children,
}: {
  title: string;
  summary: string;
  children: React.ReactNode;
}) {
  return (
    <article className="panel p-5">
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="sr-only">{summary}</p>
      <div role="img" aria-label={summary} className="mt-5">
        {children}
      </div>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-asphalt p-4">
      <p className="text-xs uppercase tracking-wider text-mist">{label}</p>
      <p className="mt-2 text-xl font-semibold">{value}</p>
    </div>
  );
}
