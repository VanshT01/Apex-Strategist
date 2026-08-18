import type { Timeline } from "@/types/api";

const colour: Record<string, string> = {
  SOFT: "bg-red-400",
  MEDIUM: "bg-amber-300",
  HARD: "bg-stone-200",
  INTERMEDIATE: "bg-emerald-400",
  WET: "bg-sky-400",
};

export function StintTimeline({ timeline }: { timeline: Timeline }) {
  return (
    <section className="panel p-5">
      <p className="eyebrow">Tyre programme</p>
      <h2 className="mt-1 text-xl font-semibold">Stint timeline</h2>
      <div className="mt-6 flex h-12 overflow-hidden rounded-lg border border-line bg-asphalt">
        {timeline.stints.map((stint) => (
          <div
            key={stint.stint_number}
            className={`relative flex min-w-12 items-center justify-center border-r border-asphalt text-xs font-semibold text-black last:border-0 ${colour[stint.compound ?? ""] ?? "bg-mist"}`}
            style={{
              width: `${(stint.lap_count / timeline.total_laps) * 100}%`,
            }}
            title={`${stint.compound ?? "Unknown"}: laps ${stint.start_lap} to ${stint.end_lap}`}
          >
            <span className="truncate px-2">
              {stint.compound?.slice(0, 1) ?? "?"} · {stint.lap_count}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-mist">
        {timeline.stints.map((stint) => (
          <span key={stint.stint_number}>
            S{stint.stint_number} {stint.compound}: L{stint.start_lap} to L
            {stint.end_lap}
          </span>
        ))}
      </div>
    </section>
  );
}
