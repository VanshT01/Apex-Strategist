export function LapSlider({
  value,
  max,
  onChange,
}: {
  value: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="panel p-5">
      <div className="flex items-end justify-between">
        <div>
          <label htmlFor="control-lap" className="eyebrow">
            Control point
          </label>
          <p className="mt-1 text-lg font-semibold">End of lap {value}</p>
        </div>
        <span className="font-mono text-sm text-mist">
          LAP {value.toString().padStart(2, "0")} / {max}
        </span>
      </div>
      <input
        id="control-lap"
        className="mt-5 h-2 w-full cursor-pointer accent-signal"
        type="range"
        min={1}
        max={Math.max(max, 1)}
        value={Math.min(value, max)}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <div className="mt-2 flex justify-between text-xs text-mist">
        <span>Race start</span>
        <span>Strategy cutoff</span>
      </div>
    </div>
  );
}
