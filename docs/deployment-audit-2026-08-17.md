# Apex Strategist deployment audit — 2026-08-17

## Release verdict

The application code, database schema, normalized race data, simulation engines,
tests, dependency audits, and production builds pass the release checks described
below. The code is suitable for a controlled deployment after the production
environment and hosting target are configured.

Do not expose the current local `.env` as production configuration. It still uses
`APP_ENV=development`, localhost API/CORS addresses, and the local PostgreSQL port.
The project also has no target-specific web hosting manifest or web container, so
the final hosting commands depend on the selected platform.

## Product overview

Apex Strategist is a historical Formula 1 race replay and counterfactual race
engineering application. It normalizes public FastF1 race timing into PostgreSQL,
reconstructs race state at any completed lap, and lets the user either replay the
recorded race or run an independent one-lap-at-a-time engineer scenario.

### Historical replay

- Dedicated `/analyze` route with an archive-focused race-analysis interface.
- Season, Grand Prix, race session, and driver selection.
- Lap-one-to-chequered replay rather than a fixed mid-race starting point.
- Recorded running order, comparable gaps, tyres, stint state, pit activity,
  weather, race-control messages, Safety Car/VSC state, pace trace, and lap table.
- Recorded strategy reconstruction, including the actual compound fitted after
  each stop.
- Lapped, retired, and unclassified drivers are handled without inventing a
  precise same-lap gap.

### Play race engineer

- Dedicated `/engineer` route with a pit-wall-focused control interface.
- Starts at lap 1 and remains independent from the selected driver's historical
  pit decisions.
- No selection means stay out; selecting a compound boxes the car on the current
  decision lap.
- Supports Soft, Medium, Hard, Intermediate, and Wet tyres.
- Applies one simulated lap and returns control to the user, allowing a new call
  every lap instead of simulating the entire remainder irreversibly.
- Carries elapsed time, position, compound, physical and effective tyre age,
  health, stint number, completed laps, and counterfactual time delta forward.
- Shows the full field gap ladder and live order with team, compound, pit status,
  Safety Car/VSC context, weather, tyre health/penalty, pace trace, timing record,
  and a stacked engineer notebook.
- Classifies overtakes by completed laps and elapsed timing; a zero gap cannot
  leave two simultaneous leaders.
- Stops at the driver's first finish-line crossing after the recorded leader takes
  the chequered flag. A driver may therefore finish one lap down.

### Pace and tyre model

- `hgb-pace-v2` is a CPU-only scikit-learn histogram-gradient-boosting model.
- Training uses clean laps from earlier races and only completed current-race laps
  for bounded driver adaptation. The selected driver's unseen future laps are
  excluded.
- Event/compound tyre life is calibrated from all drivers' observed stints;
  pit-ended stints estimate competitive life and race-ending stints are censored
  durability evidence.
- Deterministic fallbacks remain available for sparse early-race data.
- Tyre health is clamped to 0–100%, with wear defined as `100 - health`.
- The shared pace curve is measured in seconds per lap:

  `0.015w + 0.00225w² + 0.006·max(0, w-50)²`, where `w` is wear percent.

- At 60% health the representative tyre penalty is 4.2 seconds per lap.
- Exactly 5.0% health remains running; strictly below 5.0% causes a mid-lap
  `TYRE_FAILURE` DNF and normal future laps stop.
- Dry tyres on a wet track and wet tyres on a dry track receive explicit pace,
  wear, and safety penalties.

### Deterministic and Monte Carlo engines

- The deterministic engine remains the central race projection.
- `monte-carlo-v2` adds bounded lap residual, persistent pace, tyre-curve, pit
  loss, warm-up, traffic, and nearby-competitor uncertainty.
- NumPy `Generator`, `default_rng`, `SeedSequence`, common random numbers, and
  stable strategy-specific seeds provide reproducibility and candidate-order
  independence.
- Requests accept 100–10,000 runs; the UI uses practical 500–5,000 presets and
  defaults to 1,000 in the comparison schema.
- Results include deterministic projections, finish distributions, time-delta
  histograms, mean/median/mode, 5/25/75/95 percentiles, win/podium/points chances,
  actual/stay-out improvement chances, rejoin position, traffic/degradation risk,
  assumptions, calibration sources, seed, count, and engine version.
- Structured rules rank results and write explanations; no LLM is used.
- Compact aggregates are persisted. Individual Monte Carlo trajectories are not.

### Data and persistence

- PostgreSQL is the production data store; SQLite is used for lightweight tests.
- Alembic owns schema migrations and reports no drift.
- FastF1 ingestion is idempotent and cached. Session-owned data is normalized in a
  transaction with uniqueness constraints.
- Historical team identity is stored on each race entry, preventing a driver's
  current team from leaking into an older race.
- The production HTTP API disables `/api/v1/admin/ingest`; deployment ingestion
  must use the existing CLI.

## Data audit

The local PostgreSQL database contains:

| Data set                                      |                    Count |
| --------------------------------------------- | -----------------------: |
| Seasons                                       |            5 (2021–2025) |
| Race sessions                                 | 114 complete / 114 total |
| Sessions containing laps                      |                114 / 114 |
| Normalized laps                               |                  125,046 |
| Race entries                                  |                    2,278 |
| Weather samples                               |                   18,432 |
| Pit stops                                     |                    4,315 |
| Race-control messages                         |                   10,191 |
| Global driver records                         |                       38 |
| Persisted strategy comparisons at audit start |                      250 |
| Pace-model artifacts                          |                       11 |

Season coverage is 22 races in 2021, 22 in 2022, 22 in 2023, 24 in 2024,
and 24 in 2025. There are no duplicate `(session, driver, lap)` rows, missing
race-entry identities, or missing historical team names. Null lap times are
retained for non-timed/inaccurate records rather than fabricated.

## Verification performed

| Check                         | Result                                                 |
| ----------------------------- | ------------------------------------------------------ |
| Ruff format                   | 57 backend files formatted                             |
| Ruff lint                     | Passed with zero errors                                |
| Backend tests                 | 43 passed                                              |
| Prettier                      | Passed                                                 |
| ESLint                        | Passed with zero warnings                              |
| TypeScript                    | Passed (`tsc --noEmit`)                                |
| Frontend tests                | 19 passed across 4 files                               |
| Next production build         | Passed; `/`, `/_not-found`, and `/analyze` prerendered |
| Alembic upgrade               | Passed                                                 |
| Alembic drift check           | No new upgrade operations                              |
| npm production audit          | Zero known vulnerabilities                             |
| Python environment audit      | Zero known vulnerabilities in auditable packages       |
| API Docker image              | Built and import-smoke-tested                          |
| Live health/catalog/web smoke | HTTP 200                                               |
| Persistence round-trip        | POST and GET payloads identical                        |
| Validation failures           | 422 for invalid count/lap; 404 for missing comparison  |
| CORS                          | localhost origin allowed; unrelated origin not allowed |

The broader engineer validation exercised 20 drivers across 7 races, 80 strategy
outcomes, and 5 repeated-seed checks with zero failures. It covered dry and wet
races, long stints, retired/lapped drivers, pit/stay-out decisions, and repeatability.

A live 2021 Abu Dhabi check reconstructed Verstappen's actual lap-13 stop onto
Hard tyres. A new 1,000-run comparison completed end-to-end in 2.114 seconds.
The vectorized simulation calculation benchmark for 1,000 runs was 2.294 ms;
an earlier full three-strategy service benchmark completed in 1.966 seconds.
These are local measurements, not CI guarantees.

## Bugs fixed during this audit

1. The npm lockfile contained a high-severity `nanoid` advisory through PostCSS.
   The lockfile was updated and the production audit now reports zero findings.
2. Python's transitive `msgpack` version had a known advisory. The project now
   requires `msgpack>=1.2.1`; pytest's secure floor was also raised and the local
   pip tooling was updated before re-auditing.
3. Monte Carlo time deltas were incorrectly measured against the stay-out
   candidate. If stay-out retired, another strategy could claim a meaningless
   multi-thousand-second advantage. Each stochastic distribution now measures
   itself against its own deterministic projection; paired stay-out probability
   remains separate.
4. Recommendation text now describes avoiding a projected tyre-failure DNF rather
   than converting the artificial retirement classification offset into a fake
   time gain.
5. The unauthenticated, expensive HTTP ingestion route is automatically disabled
   when `APP_ENV` is `production` or `prod`.
6. Documentation now states the effective Node engine floor: Node 20.19+ or
   22.13+.

## Remaining limitations and deployment risks

### Must be resolved for public deployment

1. Set a production `DATABASE_URL`, `APP_ENV=production`, exact production
   `CORS_ORIGINS`, and the browser-visible `NEXT_PUBLIC_API_URL` before building
   the web application.
2. Choose and configure the web hosting target. Only an API Dockerfile and local
   PostgreSQL Compose service exist; there is no web Dockerfile or provider
   manifest in this repository.
3. Run Alembic as an explicit release step before starting the API. The API image
   does not run migrations automatically.
4. Use Node 20.19+, 22.13+, or 24+ in CI/hosting. The audit machine uses Node
   22.11 and emits an engine warning even though all checks pass.
5. Deploy the tested immutable container image/digest. Python dependencies use
   bounded version ranges rather than a fully pinned cross-platform lock file, so
   rebuilding later may resolve newer compatible packages.

### Model/product limitations

- Competitors remain anchored to their recorded trajectories and do not make a
  strategic reaction to the user's counterfactual.
- Safety Car/VSC sampling beyond recorded interventions remains disabled until a
  defensible calibration exists.
- New mechanical failures are not sampled; deterministic tyre failure is the
  explicit gameplay retirement rule.
- The model uses public timing, weather, and race-control data, not proprietary
  team telemetry or full vehicle physics.
- A historical counterfactual is an explainable model estimate, not proof that a
  different real-world call would have produced that result.
- Browser-level semantic automation could not be run in this audit environment
  because its required in-app browser runtime was unavailable. UI logic is covered
  by 19 jsdom interaction tests, TypeScript, lint, the production build, and live
  HTTP/SSR checks; a final manual Chrome/Safari pass remains advisable.
- The backend test run is green but reports upstream/deprecation warnings from
  FastAPI's TestClient and NumPy timedelta construction in fixtures.

## Production runbook

```bash
# Runtime versions
python3.12 --version
node --version  # 20.19+, 22.13+, or 24+

# Install and validate
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
npm ci
docker compose up -d postgres
make migrate
make migration-check
make lint
make test
npx tsc --noEmit -p apps/web/tsconfig.json
npm run build --workspace apps/web

# Local services
make api
make web  # http://localhost:3001
```

For production, inject environment values through the hosting platform rather
than committing `.env`. Build the frontend only after setting
`NEXT_PUBLIC_API_URL`, because it is a public build-time value.
