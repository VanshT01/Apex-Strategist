const colours: Record<string, string> = {
  SOFT: "border-red-400/40 bg-red-400/10 text-red-300",
  MEDIUM: "border-amber-300/40 bg-amber-300/10 text-amber-200",
  HARD: "border-white/30 bg-white/10 text-white",
  INTERMEDIATE: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
  WET: "border-sky-400/40 bg-sky-400/10 text-sky-300",
};

export function TyreBadge({ compound }: { compound: string | null }) {
  const name = compound ?? "UNKNOWN";
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-semibold ${colours[name] ?? "border-line bg-asphalt text-mist"}`}
    >
      {name}
    </span>
  );
}
