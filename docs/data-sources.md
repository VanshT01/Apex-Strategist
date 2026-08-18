# Data Sources

## FastF1 (active)

FastF1 is the sole active provider for this milestone. The implementation is
pinned to the supported 3.x line and uses its public interfaces:

- `fastf1.get_session(year, event, "R")` selects a race.
- `Session.load(telemetry=False, weather=True, messages=True)` loads timing,
  results, weather, and messages without high-frequency car telemetry.
- `Session.results` supplies driver number/name/code/team/country, grid and
  finish positions, status, and points.
- `Session.laps` supplies lap/sector times, stint, pit timestamps, speed traps,
  compound, tyre life/freshness, track status, end-lap position, deletion, and
  accuracy flags.
- `Session.weather_data` supplies time, air/track temperature, humidity,
  pressure, rainfall, wind direction, and wind speed.
- `Session.race_control_messages` is optional; message columns are inspected
  defensively because availability varies by session.

The implementation follows the official FastF1 documentation for
[sessions and lap columns](https://docs.fastf1.dev/core.html),
[event schedule fields](https://docs.fastf1.dev/events.html), and
[cache/session entry points](https://docs.fastf1.dev/fastf1.html).

`TyreLife` includes prior use of a set in other sessions; it is not necessarily
the number of race laps in the current stint. `Time`, `PitInTime`, and
`PitOutTime` are session-relative timedeltas. FastF1 documents pit timestamps as
calculated values whose millisecond precision cannot be verified; accordingly,
pit duration is approximate and stationary time remains null.

## Cache and rate-friendly behaviour

`FastF1.Cache.enable_cache()` is called before session creation/loading. Cached
provider responses live under `FASTF1_CACHE_DIR`, defaulting to
`./data/fastf1`, and are excluded from source control. Read endpoints never
download data. Re-running a completed ingestion does no provider normalization
unless `--force` is supplied (FastF1 may still use its local cache).

## OpenF1 and Jolpica (configured, inactive)

Base URLs are configurable for later phases, but this milestone makes no OpenF1
or Jolpica HTTP calls and maps no fields from them. A future source must document
and test its exact response before entering the normalized model.

## Attribution and licensing

FastF1 is an unofficial project and Formula 1 data carries provider and rights
considerations. Deployers should review FastF1's current license and upstream
terms, retain attribution, avoid official branding confusion, cache
responsibly, and confirm that their intended public/commercial use is allowed.
