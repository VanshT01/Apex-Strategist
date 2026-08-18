import type {
  Driver,
  Event,
  LapPage,
  RaceSession,
  RaceState,
  Season,
  StrategyCandidate,
  StrategyComparison,
  SimulationSubmission,
  Timeline,
} from "@/types/api";
import {
  driverSchema,
  eventSchema,
  lapPageSchema,
  raceStateSchema,
  seasonSchema,
  sessionSchema,
  strategyComparisonSchema,
  timelineSchema,
} from "./schemas";
import { z } from "zod";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function get<T>(
  path: string,
  schema: z.ZodType<T>,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { signal });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      payload?.detail ?? `API request failed (${response.status})`,
    );
  }
  return schema.parse(await response.json());
}

async function post<T>(
  path: string,
  body: unknown,
  schema: z.ZodType<T>,
  signal?: AbortSignal,
): Promise<T> {
  const timeout = new AbortController();
  const timeoutId = window.setTimeout(() => timeout.abort(), 30_000);
  const combinedSignal = signal
    ? AbortSignal.any([signal, timeout.signal])
    : timeout.signal;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: combinedSignal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(
        signal?.aborted
          ? "Simulation request cancelled."
          : "Simulation request timed out after 30 seconds.",
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      payload?.detail ?? `API request failed (${response.status})`,
    );
  }
  return schema.parse(await response.json());
}

export const api = {
  seasons: (signal?: AbortSignal) =>
    get<Season[]>("/seasons", z.array(seasonSchema), signal),
  events: (season: number, signal?: AbortSignal) =>
    get<Event[]>(`/events?season=${season}`, z.array(eventSchema), signal),
  sessions: (eventId: number, signal?: AbortSignal) =>
    get<RaceSession[]>(
      `/events/${eventId}/sessions`,
      z.array(sessionSchema),
      signal,
    ),
  drivers: (sessionId: number, signal?: AbortSignal) =>
    get<Driver[]>(
      `/sessions/${sessionId}/drivers`,
      z.array(driverSchema),
      signal,
    ),
  laps: (sessionId: number, driverId: number, signal?: AbortSignal) =>
    get<LapPage>(
      `/sessions/${sessionId}/laps?driver_id=${driverId}&page_size=200`,
      lapPageSchema,
      signal,
    ),
  raceState: (
    sessionId: number,
    driverId: number,
    lap: number,
    signal?: AbortSignal,
  ) =>
    get<RaceState>(
      `/sessions/${sessionId}/race-state?lap=${lap}&driver_id=${driverId}`,
      raceStateSchema,
      signal,
    ),
  timeline: (sessionId: number, driverId: number, signal?: AbortSignal) =>
    get<Timeline>(
      `/sessions/${sessionId}/timeline?driver_id=${driverId}`,
      timelineSchema,
      signal,
    ),
  compare: (
    sessionId: number,
    driverId: number,
    controlLap: number,
    strategies: StrategyCandidate[],
    simulationCount: number,
    randomSeed: number,
    scenario?: SimulationSubmission["scenario"],
    simulationContext?: SimulationSubmission["simulation_context"],
    signal?: AbortSignal,
  ) =>
    post<StrategyComparison>(
      "/simulations/compare",
      {
        session_id: sessionId,
        driver_id: driverId,
        control_lap: controlLap,
        strategies,
        simulation_count: simulationCount,
        random_seed: randomSeed,
        scenario,
        simulation_context: simulationContext,
      },
      strategyComparisonSchema,
      signal,
    ),
};
