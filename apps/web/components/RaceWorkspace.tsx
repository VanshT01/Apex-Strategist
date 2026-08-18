"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { EngineerMode } from "@/components/EngineerMode";
import { LapTable } from "@/components/LapTable";
import { PaceChart } from "@/components/PaceChart";
import { RaceReplay } from "@/components/RaceReplay";
import {
  DriverSelector,
  EventSelector,
  SeasonSelector,
  SessionSelector,
} from "@/components/Selectors";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/State";
import { api } from "@/lib/api";

type WorkspaceMode = "replay" | "engineer";

const workspaceCopy = {
  replay: {
    code: "ARCHIVE / 01",
    eyebrow: "Historical race analysis",
    title: "Replay every lap. Read every call.",
    description:
      "Scrub the recorded Grand Prix with synchronized timing, weather, tyres, race control and field position.",
    accent: "SESSION DATA",
    switchHref: "/engineer",
    switchLabel: "Open Race Engineer",
    switchHint: "Take control from lap 1",
  },
  engineer: {
    code: "PIT WALL / 02",
    eyebrow: "Interactive race engineer",
    title: "You own the strategy.",
    description:
      "Run an independent race one lap at a time. Box, stay out and manage weather, traffic and tyre life to the flag.",
    accent: "DECISION MODE",
    switchHref: "/analyze",
    switchLabel: "Open Race Analysis",
    switchHint: "Study the recorded race",
  },
} as const;

export function RaceWorkspace({ mode }: { mode: WorkspaceMode }) {
  const copy = workspaceCopy[mode];
  const [season, setSeason] = useState("");
  const [event, setEvent] = useState("");
  const [session, setSession] = useState("");
  const [driver, setDriver] = useState("");
  const [controlLap, setControlLap] = useState(0);
  const seasons = useQuery({
    queryKey: ["seasons"],
    queryFn: ({ signal }) => api.seasons(signal),
  });
  const events = useQuery({
    queryKey: ["events", season],
    queryFn: ({ signal }) => api.events(Number(season), signal),
    enabled: !!season,
  });
  const sessions = useQuery({
    queryKey: ["sessions", event],
    queryFn: ({ signal }) => api.sessions(Number(event), signal),
    enabled: !!event,
  });
  const drivers = useQuery({
    queryKey: ["drivers", session],
    queryFn: ({ signal }) => api.drivers(Number(session), signal),
    enabled: !!session,
  });
  const laps = useQuery({
    queryKey: ["laps", session, driver],
    queryFn: ({ signal }) => api.laps(Number(session), Number(driver), signal),
    enabled: !!session && !!driver,
  });
  const replayMaxLap = useMemo(() => {
    const officialTotal = events.data?.find(
      (item) => item.id === Number(event),
    )?.total_laps;
    const recordedMaximum = Math.max(
      ...(laps.data?.items.map((lap) => lap.lap_number) ?? [1]),
    );
    return Math.max(1, officialTotal ?? recordedMaximum);
  }, [event, events.data, laps.data]);
  const activeControlLap = controlLap || 1;
  const completedLaps = useMemo(
    () =>
      (laps.data?.items ?? []).filter(
        (lap) => lap.lap_number <= activeControlLap,
      ),
    [activeControlLap, laps.data],
  );
  const raceState = useQuery({
    queryKey: ["race-state", session, driver, activeControlLap],
    queryFn: ({ signal }) =>
      api.raceState(Number(session), Number(driver), activeControlLap, signal),
    enabled: !!session && !!driver && !!laps.data?.items.length,
    placeholderData: keepPreviousData,
  });
  const timeline = useQuery({
    queryKey: ["timeline", session, driver],
    queryFn: ({ signal }) =>
      api.timeline(Number(session), Number(driver), signal),
    enabled: !!session && !!driver,
  });
  const queryError =
    seasons.error ??
    events.error ??
    sessions.error ??
    drivers.error ??
    laps.error ??
    raceState.error ??
    timeline.error;

  function resetBelow(level: "season" | "event" | "session" | "driver") {
    if (level === "season") {
      setEvent("");
      setSession("");
      setDriver("");
    }
    if (level === "event") {
      setSession("");
      setDriver("");
    }
    if (level === "session") setDriver("");
    setControlLap(0);
  }

  return (
    <main className={`race-workspace race-workspace--${mode}`}>
      <section className="race-masthead">
        <div className="race-masthead__copy">
          <div className="flex flex-wrap items-center gap-3">
            <span className="race-code">{copy.code}</span>
            <span className="live-pill">
              <span aria-hidden className="live-pill__dot" />
              {copy.accent}
            </span>
          </div>
          <p className="eyebrow mt-5">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="race-masthead__description">{copy.description}</p>
        </div>
        <Link href={copy.switchHref} className="mode-transfer">
          <span className="mode-transfer__arrow" aria-hidden>
            ↗
          </span>
          <span>
            <strong>{copy.switchLabel}</strong>
            <small>{copy.switchHint}</small>
          </span>
        </Link>
      </section>

      <section className="race-selector" aria-label="Race selection">
        <div className="race-selector__rail" aria-hidden>
          <span>01</span>
          <span>02</span>
          <span>03</span>
          <span>04</span>
        </div>
        <div className="race-selector__fields">
          <SeasonSelector
            items={seasons.data ?? []}
            value={season}
            onChange={(value) => {
              setSeason(value);
              resetBelow("season");
            }}
          />
          <EventSelector
            items={events.data ?? []}
            value={event}
            onChange={(value) => {
              setEvent(value);
              resetBelow("event");
            }}
            disabled={!season}
          />
          <SessionSelector
            items={sessions.data ?? []}
            value={session}
            onChange={(value) => {
              setSession(value);
              resetBelow("session");
            }}
            disabled={!event}
          />
          <DriverSelector
            items={drivers.data ?? []}
            value={driver}
            onChange={(value) => {
              setDriver(value);
              resetBelow("driver");
            }}
            disabled={!session}
          />
        </div>
      </section>

      {queryError && (
        <ErrorState
          message={
            queryError instanceof Error ? queryError.message : "Unknown error"
          }
        />
      )}
      {seasons.isLoading && <LoadingSkeleton />}
      {!seasons.isLoading && seasons.data?.length === 0 && (
        <EmptyState>
          No races have been ingested yet. Run{" "}
          <code className="text-white">make ingest-demo</code> to load the demo
          seasons, then refresh this page.
        </EmptyState>
      )}
      {laps.isLoading && <LoadingSkeleton label="Loading driver laps" />}
      {laps.data && laps.data.items.length > 0 && (
        <div className="grid gap-3">
          {raceState.isLoading && (
            <LoadingSkeleton label="Reconstructing race state" />
          )}
          {raceState.data && timeline.data && (
            <>
              <div
                className={
                  mode === "replay"
                    ? "min-h-[680px] xl:h-[calc(100vh-15rem)] xl:min-h-[560px]"
                    : ""
                }
              >
                {mode === "replay" ? (
                  <RaceReplay
                    lap={activeControlLap}
                    maxLap={replayMaxLap}
                    state={raceState.data}
                    timeline={timeline.data}
                    selectedDriverId={Number(driver)}
                    drivers={drivers.data ?? []}
                    selectedLaps={laps.data.items}
                    onLapChange={setControlLap}
                    onDriverChange={(driverId) => {
                      setDriver(String(driverId));
                      setControlLap(activeControlLap);
                    }}
                  />
                ) : (
                  <EngineerMode
                    key={`${session}-${driver}`}
                    sessionId={Number(session)}
                    driverId={Number(driver)}
                    lap={activeControlLap}
                    maxLap={replayMaxLap}
                    state={raceState.data}
                    selectedLaps={laps.data.items}
                    onLapChange={setControlLap}
                  />
                )}
              </div>
              {mode === "replay" && (
                <section
                  className="grid gap-3"
                  aria-label={`Completed telemetry through lap ${activeControlLap}`}
                >
                  <PaceChart laps={completedLaps} />
                  <LapTable laps={completedLaps} />
                </section>
              )}
            </>
          )}
        </div>
      )}
      {laps.data?.items.length === 0 && (
        <EmptyState>
          No normalized laps are available for this driver.
        </EmptyState>
      )}
    </main>
  );
}
