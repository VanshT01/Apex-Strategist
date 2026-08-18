import type { RaceState } from "@/types/api";
import { TyreBadge } from "./TyreBadge";

function gap(ms: number | null, position: number | null) {
  if (position === 1) return "LEADER";
  if (ms === null) return "LAPPED / N.A.";
  return `+${(ms / 1000).toFixed(3)}`;
}

export function RunningOrder({ state }: { state: RaceState }) {
  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-line p-5">
        <p className="eyebrow">Track position</p>
        <h2 className="mt-1 text-xl font-semibold">Running order</h2>
      </div>
      <div className="max-h-[520px] overflow-y-auto">
        {state.running_order.map((item) => (
          <div
            key={item.driver_id}
            className={`grid grid-cols-[36px_58px_1fr_auto] items-center gap-2 border-b border-line/70 px-4 py-3 last:border-0 ${item.driver_id === state.selected_driver.driver_id ? "bg-signal/[.08]" : ""}`}
          >
            <span className="font-mono text-mist">
              {item.position ?? "N/A"}
            </span>
            <strong>{item.abbreviation}</strong>
            <div>
              <TyreBadge compound={item.compound} />
              <span className="ml-2 text-xs text-mist">
                L{item.completed_laps}
              </span>
            </div>
            <span className="font-mono text-xs text-mist">
              {gap(item.gap_to_leader_ms, item.position)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
