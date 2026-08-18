import type { Driver, Event, RaceSession, Season } from "@/types/api";

type SelectProps<T> = {
  id: string;
  label: string;
  value: string;
  items: T[];
  disabled?: boolean;
  placeholder: string;
  getValue: (item: T) => string;
  getLabel: (item: T) => string;
  onChange: (value: string) => void;
};

function DataSelect<T>({
  id,
  label,
  value,
  items,
  disabled,
  placeholder,
  getValue,
  getLabel,
  onChange,
}: SelectProps<T>) {
  return (
    <div>
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <select
        className="select"
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{placeholder}</option>
        {items.map((item) => (
          <option key={getValue(item)} value={getValue(item)}>
            {getLabel(item)}
          </option>
        ))}
      </select>
    </div>
  );
}

export function SeasonSelector(props: {
  items: Season[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <DataSelect
      id="season"
      label="Season"
      placeholder="Select season"
      getValue={(x) => String(x.year)}
      getLabel={(x) => String(x.year)}
      {...props}
    />
  );
}
export function EventSelector(props: {
  items: Event[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <DataSelect
      id="event"
      label="Grand Prix"
      placeholder="Select event"
      getValue={(x) => String(x.id)}
      getLabel={(x) =>
        `${x.round_number.toString().padStart(2, "0")} · ${x.event_name}`
      }
      {...props}
    />
  );
}
export function SessionSelector(props: {
  items: RaceSession[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <DataSelect
      id="session"
      label="Session"
      placeholder="Select session"
      getValue={(x) => String(x.id)}
      getLabel={(x) => `${x.session_type} · ${x.ingestion_status}`}
      {...props}
    />
  );
}
export function DriverSelector(props: {
  items: Driver[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <DataSelect
      id="driver"
      label="Driver"
      placeholder="Select driver"
      getValue={(x) => String(x.id)}
      getLabel={(x) => `${x.abbreviation} · ${x.full_name}`}
      {...props}
    />
  );
}
