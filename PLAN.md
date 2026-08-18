# Apex Strategist Implementation Plan

## Scope

Phases 1–4 are complete. The active milestone is Phase 5: seeded, vectorized
Monte Carlo uncertainty layered on the existing deterministic strategy engine.
Machine learning remains deferred until this stochastic baseline is validated.

## Phase 5 Verification Baseline

- Inspected the repository, schemas, repositories, race-state service,
  deterministic engine, tyre and pit-loss estimators, persistence, routes,
  frontend strategy lab, and existing tests before modification.
- PostgreSQL upgrades to Alembic head and `alembic check` reports no model
  drift. Running Alembic directly from `apps/api` without the root environment
  selects the stale SQLite fallback file; production drift checks must use the
  root `.env` or an explicit PostgreSQL URL.
- Baseline Ruff format, Ruff lint, ESLint, 11 backend tests, 5 frontend tests,
  TypeScript compilation, and the Next.js production build pass.
- A repository-wide Prettier check has two pre-existing failures:
  `docs/data-sources.md` and root `package.json`. Phase 5 will format them.
- The previous summary's backend-test count is stale (11 rather than 10), and
  settings currently default to 500 simulations with a 5,000 maximum rather
  than Phase 5's required 1,000 and 10,000.

## Phase 5 Implementation Record

1. [x] Extend the comparison request with validated `simulation_count=1000` and
       `random_seed=42`, enforce the configured compute ceiling, and keep old saved
       deterministic responses readable through backward-compatible defaults.
2. [x] Calibrate clean-lap residual scale, persistent driver pace variation, tyre
       slope uncertainty, accepted pit-loss samples, compound warm-up variation,
       and heuristic rejoin traffic using explicit bounded fallback metadata.
3. [x] Generate common vectorized lap/competitor draws plus stable
       strategy-specific draws with NumPy `Generator` and `SeedSequence`, so seed
       reproducibility and candidate-order independence are both testable.
4. [x] Anchor every sample to its deterministic projection, retain historical
       competitor trajectories with modest pace uncertainty, and aggregate finish,
       time, probability, percentile, and compact histogram outputs without storing
       individual trajectories.
5. [x] Rank candidates by median finish, chance of beating stay out, expected time,
       and downside range; generate structured probabilistic explanations without
       an LLM. Safety-car/VSC scenario sampling remains disabled behind a documented
       interface until it can be calibrated responsibly.
6. [x] Persist `monte-carlo-v1` request, aggregates, uncertainty metadata, seed, and
       count in the existing `strategy_simulations` JSON columns; no migration is
       expected unless implementation proves otherwise.
7. [x] Add simulation controls, headline probabilities, deterministic-versus-Monte
       Carlo comparison, accessible Recharts distributions, assumptions, loading,
       retry, and error UX to the existing strategy lab.
8. [x] Add diagnostic and benchmark CLI commands, comprehensive backend/frontend
       tests, documentation, a real 2024 British GP run, honest timing results, and
       final format/lint/test/build/migration verification.

## Phase 3–4 Assumptions

- A selected control lap represents race state at the end of that lap; “pit now”
  changes tyres before the following racing lap.
- End-of-lap FastF1 `Time` is the shared session-time reference used for
  approximate gaps. Lapped/retired cars are labelled rather than assigned a
  false precise gap.
- Deterministic comparisons hold competitors to their historical trajectories.
  They do not yet model competitor reactions or return probabilities.
- Event pit loss is derived from valid paired pit-in/pit-out intervals with a
  global fallback only when the event has insufficient observations.
- Tyre degradation uses robust event/compound summaries with transparent
  fallbacks. It is a baseline estimate, not an ML model.

## Phase 3–4 Implementation Order

1. Reconstruct running order, selected-driver state, gaps, weather, race-control
   status, pit history, and nearby rejoin traffic at any completed lap.
2. Add typed race-state, timeline, and actual-strategy endpoints.
3. Add event pit-loss and tyre-degradation estimators.
4. Compare 2–5 validated pit-now, delayed-pit, or stay-out strategies using
   recent pace, compound/age effects, pace mode, and historical field traces.
5. Persist deterministic comparison output with `deterministic-v1` provenance
   and generate a rule-based recommendation/explanation.
6. Build dashboard control-lap selection and strategy lab/results UI.
7. Test algorithms, validation, APIs, UI submission/rendering, and error states.

## Phase 3–4 Risks

- **Gaps for lapped/retired cars:** return completed-lap deltas and nullable time
  gaps instead of fabricating comparable timestamps.
- **Noisy pit intervals:** reject non-positive/outlier intervals and expose the
  sample count/fallback level used.
- **Sparse compound data:** fall back from event+compound to event-wide robust
  degradation and return data-quality metadata.
- **Counterfactual overclaiming:** label results deterministic, omit probability
  claims, and compare against fixed historical competitor trajectories.
- **Strategy validation:** enforce control/pit lap bounds, dry-compound
  availability, and candidate-count limits in Pydantic and the service.

## Phase 3–4 Files

- Backend: `schemas/race_state.py`, `schemas/strategy.py`,
  `repositories/race.py`, `services/race_state.py`, `simulation/deterministic.py`,
  `simulation/tyres.py`, `simulation/pit_loss.py`, `services/strategy.py`, and
  versioned routes/tests.
- Frontend: expanded API types/client plus `LapSlider`, `RaceStateCard`,
  `RunningOrder`, `StintTimeline`, `StrategyBuilder`, comparison/recommendation,
  risk, and actual-vs-simulated components.

## Assumptions

- Python 3.11 or 3.12, Node.js 20+, Docker Desktop, and Docker Compose are
  available on the development Mac.
- PostgreSQL is the default database. SQLite remains supported for lightweight
  backend tests and local troubleshooting.
- FastF1 is the system of record for this milestone. FastF1 fields are accessed
  defensively because older races and partially loaded sessions can omit data.
- A race is uniquely identified by season, event round, and session type.
- Driver number is stored as text because motorsport timing feeds treat it as an
  identifier rather than a quantity.
- The default demo ingestion is configurable and uses a recent completed race;
  no race data is bundled or permanently mocked.
- The frontend calls only the local FastAPI service. It never calls FastF1,
  OpenF1, or Jolpica directly.

## First Implementation Phase

1. Create the monorepo, environment configuration, Docker Compose, Makefile,
   CI workflow, and documentation skeleton.
2. Build the FastAPI application, SQLAlchemy domain models, Alembic migration,
   health endpoint, and consistent API errors.
3. Build FastF1 cache/configuration, normalization helpers, idempotent ingestion
   service, and ingestion CLI/API endpoint.
4. Add typed list/detail endpoints for seasons, events, sessions, drivers, and
   paginated driver laps.
5. Build the Next.js race-selection and driver-lap explorer with loading, empty,
   and error states.
6. Add backend/frontend tests, format, lint, test, and correct all failures.

## Risks and Mitigations

- **Provider/network availability:** ingestion is an explicit command, uses the
  FastF1 disk cache, records failed status, and does not affect read endpoints.
- **FastF1 schema variation:** every optional column is checked before access;
  pandas/NumPy/timestamp values are normalized through shared helpers.
- **Large lap inserts:** normalized rows are prepared in batches and committed
  once; uniqueness constraints prevent accidental duplicates.
- **Partial session data:** required event/session records persist an ingestion
  error while optional weather and race-control datasets may be absent.
- **PostgreSQL/SQLite differences:** models use portable SQLAlchemy types and the
  test suite exercises SQLite while production configuration targets Postgres.
- **Frontend/backend schema drift:** Pydantic response schemas have matching,
  centralized TypeScript interfaces and contract-shaped fixtures in tests.
- **Historical corrections:** `--force` deletes session-owned normalized data and
  re-ingests the selected session within a transaction.

## Files Created or Modified in This Milestone

- Root: `README.md`, `PLAN.md`, `.env.example`, `.gitignore`, `Makefile`,
  `docker-compose.yml`, `pyproject.toml`, `package.json`
- CI/infra: `.github/workflows/ci.yml`, `infra/api.Dockerfile`
- Backend: `apps/api/alembic.ini`, `apps/api/alembic/**`, `apps/api/app/**`,
  `apps/api/tests/**`
- Frontend: `apps/web/app/**`, `apps/web/components/**`, `apps/web/lib/**`,
  `apps/web/types/**`, `apps/web/tests/**`, plus Next.js/Tailwind/test config
- Docs: `docs/architecture.md`, `docs/data-sources.md`
- Runtime directories: `data/fastf1/.gitkeep`, `data/models/.gitkeep`

## Milestone Acceptance Checklist

- [x] PostgreSQL starts healthy through Docker Compose on host port 5433.
- [x] Alembic upgrades a clean database to head and matches model metadata
      (`alembic check`, SQLite fallback).
- [x] A configurable historical race ingests through FastF1 with caching (2024
      British Grand Prix: 20 drivers, 960 laps).
- [x] API health, season, event, session, driver, and lap routes work against the
      real normalized session.
- [x] Web UI selects an ingested race and driver and renders lap, tyre, stint,
      position, and lap-time data.
- [x] Backend and frontend formatting, linting, and tests pass.
- [x] Next.js production build and TypeScript compilation pass.
- [x] README contains exact macOS commands and verified limitations.

## Status

Phases 1–5 implementation complete. The Phase 4 deterministic projection is
preserved and Phase 5 adds seeded `monte-carlo-v1` distributions, empirical
calibration with labelled fallbacks, persisted aggregates, probabilistic
recommendations, diagnostics, and an accessible strategy-lab UI. Final command
verification is recorded below.

Phase 6 interactive replay and the continuous race-engineer decision loop are
implemented. The 2026-08-17 deployment audit is recorded in
`docs/deployment-audit-2026-08-17.md`; all application checks pass, with final
production environment and hosting configuration still required before a public
release.

The user interface now exposes Phase 6 as two dedicated routes: `/analyze` for
historical race replay and `/engineer` for the independent pit-wall game. Both
share `RaceWorkspace` for catalog and race-state loading, while the global shell
uses a motorsport timing and race-control visual language.

## Phase 5 Acceptance Checklist

- [x] Request defaults to 1,000 simulations and seed 42; accepts 100–10,000 and
      respects the configured compute ceiling.
- [x] Same request/seed is reproducible; different seeds vary; candidate order
      does not perturb strategy-specific samples.
- [x] Lap residual, driver pace, tyre slope, pit loss, warm-up, traffic, and
      competitor uncertainty are bounded and vectorized with NumPy Generator.
- [x] Deterministic results remain visible beside aggregate finish/time
      distributions, percentiles, probabilities, risks, and metadata.
- [x] Probabilistic recommendation is structured and does not use an LLM.
- [x] Aggregates persist in existing JSON columns and retrieve without storing
      every trajectory; no migration was required.
- [x] UI supports 500/1,000/2,500/5,000 presets, optional seed, cancellation,
      retry, headline statistics, accessible charts, and assumptions.
- [x] Diagnostic and benchmark CLI commands expose calibration and timing.
- [x] Real 2024 British GP final benchmark completed: 1,000 × 3, seed 42,
      4.337 ms NumPy calculation and 125.648 ms end-to-end service time.
- [x] Backend tests: 20 passed. Frontend tests: 7 passed. Ruff, ESLint,
      TypeScript, and Next.js production build passed.
- [x] Final repository-wide formatting and PostgreSQL Alembic drift checks
      pass after documentation formatting.

## Phase 3–4 Acceptance Checklist

- [x] Reconstruct running order, selected-driver pace/tyres/stint, comparable
      gaps, weather, race-control status, pit history, and rejoin window.
- [x] Return typed race-state, timeline, and actual-strategy APIs.
- [x] Estimate current-event pit loss with historical/global fallback metadata.
- [x] Estimate bounded event/compound tyre offset and degradation with fallback.
- [x] Validate and compare pit-now, three-lap delay, and stay-out strategies.
- [x] Persist and retrieve reproducible `deterministic-v1` comparisons.
- [x] Generate rule-based recommendation and actual-result comparison without
      probability claims.
- [x] Render control-lap dashboard, running order, stints, strategy builder,
      comparison table, risks, provenance, and disclaimer.
- [x] Verify 11 backend tests, 5 frontend tests, lint/format, production build,
      and live HTTP 200 responses on ports 3001 and 8000.

## Deferred Work

Calibrated Safety Car/VSC scenario sampling,
new-mechanical-DNF modeling, wet-compound strategy validation, multi-stop
candidates, reactive competitors, multi-race evaluation, and deployment polish
remain deferred.

## Learned Engineer Pace Correction

- [x] Reproduce the exact fixed `+0.020s/lap` staircase and trace it to the
      event-wide linear tyre slope's 20ms lower clamp.
- [x] Add a CPU histogram-gradient-boosting expected-pace model trained on clean
      laps strictly before the selected race.
- [x] Predict driver pace relative to the same-lap field median using compound,
      driver, circuit, nonlinear tyre age, race progress, position, and stint.
- [x] Adapt from completed selected-driver laps only and exclude that driver's
      future laps from training and the field anchor.
- [x] Keep pit loss, wet/dry rules, warm-up, tyre cliff, puncture/DNF, ordering,
      and seeded Monte Carlo uncertainty outside the learned model.
- [x] Persist local artifacts and validation metadata in `model_artifacts`; use
      the deterministic fallback when fewer than 2,000 eligible rows exist.
- [x] Add nonlinear-shape and selected-future-exclusion regression tests.
- [x] Validate the 2023 Canadian GP Stroll Hard scenario: the exact 20ms
      staircase is replaced by a varying learned field/tyre curve.

## Phase 6 Interactive Experience

- [x] Split the workstation into Historical Replay and Play Race Engineer modes.
- [x] Start engineer mode at lap 1 and replace the three-strategy UI with one
      optional Box + compound decision; no selection means stay out.
- [x] Keep counterfactual control in the main lap panel and advance only one lap
      after each call so the user can make repeated decisions.
- [x] Carry counterfactual compound, tyre age, position, and time delta into
      later seeded simulations instead of resetting to recorded history.
- [x] Surface recorded live weather lap by lap in both modes.
- [x] Add all-driver orbit and live order with leader gaps, compounds, pit
      status, and SC/VSC intervention boxing context to Engineer Mode.
- [x] Add an event-calibrated tyre degradation gauge to Engineer Mode and reset
      the modeled reserve to 100% whenever a new set is fitted.
- [x] Fully separate the player trajectory from recorded driver strategy from
      lap 1; recorded stops can no longer pit the player car.
- [x] Trigger a terminal tyre-failure DNF strictly below 5% health with zero win, podium,
      and points probability and disable further engineer decisions.
- [x] Verify the continuous loop with 24 backend and 13 frontend tests, Ruff,
      ESLint, TypeScript, production build, Alembic upgrade/drift checks, and a
      real 500-run 2021 Abu Dhabi continuation (comparison 88).

- [x] Replay every completed lap with play, pause, restart, and direct scrubbing.
- [x] Synchronize compound, tyre age/health, running order, gaps, weather,
      race-control state, pit markers, rejoin context, and engineer radio.
- [x] Animate leaderboard changes, gap bars, driver markers, cards, and result
      disclosures with Framer Motion and reduced-motion support.
- [x] Allow driver selection from the leaderboard/map and pin up to three
      synchronized driver comparisons.
- [x] Add timeline/story modes with pit-event-driven race chapters.
- [x] Launch the seeded comparison immediately from Box, Stay out, Wait, or
      Override decision prompts.
- [x] Add validated and persisted pit-loss and degradation scenario controls
      that genuinely affect both deterministic and Monte Carlo calculations.
- [x] Add animated Monte Carlo formation, expandable live strategy cards,
      radar comparison, finish probability explorer, and engineer notebook.
- [x] Preserve full deterministic tables, distributions, model provenance,
      assumptions, raw pace, and timing views.
- [x] Label the track view as schematic because normalized GPS/circuit/DRS data
      is not available; do not fabricate telemetry.
- [x] Verify 21 backend tests, 10 frontend tests, formatting, Ruff, ESLint,
      TypeScript, production build, PostgreSQL migration, and schema drift.
- [x] Run and persist a real 1,000-run Abu Dhabi 2021 scenario comparison with
      +3 seconds pit loss and +20% tyre degradation (comparison 66).
- [x] Start new race selections on lap 1, bound replay by official event laps,
      accept the final lap in race-state reconstruction, and render a podium or
      race-complete chequered-flag state.
- [x] Generate and persist lap-by-lap deterministic consequence trajectories
      for every strategy, anchored to historical conditions and recorded field
      timing, with an expandable continuation replay.
- [x] Support Intermediate and Wet selections through empirical event fits or
      clearly labelled conservative fallbacks.
- [x] Space schematic cars by recorded gap as a fraction of leader lap time and
      move the selected driver through the pit lane on recorded stops.
- [x] Verify final classification and 51-lap Intermediate consequence trajectory
      on the real 71-lap São Paulo 2021 session (comparison 76).
- [x] Verify 23 backend tests, 11 frontend tests, Ruff, ESLint, Prettier,
      TypeScript, and the Next.js production build after the correction.

## Post-Phase-5 Correction

- [x] Reproduced the 2021 Abu Dhabi lap 12–14 Verstappen recommendation against
      PostgreSQL and confirmed the recorded lap-13 Hard stop was correct.
- [x] Fixed unsupported tyre-age extrapolation that allowed the stay-out
      candidate to project a 61-lap Soft set at the fitted degradation floor.
- [x] Added event/compound clean maximum tyre age, labelled compound fallback,
      conservative post-support degradation, matching Monte Carlo exposure, and
      a regression test.
- [x] Verified the corrected default UI candidates recommend pit-now Hard on
      laps 12 and 13, then stay out on lap 14 because Verstappen is already on
      Hard tyres after the recorded lap-13 stop.
- [x] Fixed Engineer Mode pace trace and timing record to accumulate applied
      simulated laps after divergence instead of continuing to show history.
- [x] Re-anchored projected time against the recorded future tyre and pit
      sequence so ignoring a historical stop no longer produces zero delta.
- [x] Added a bounded nonlinear post-support tyre-cliff assumption and a long
      Soft-stint regression. Abu Dhabi 2021 lap 13–58 now ends with a 110.003s
      projected lap, +273.437s versus actual, and P11 (comparison 100).

## Post-Phase-6 Historical Identity and Classification Correction

- [x] Move historical team ownership to `race_entries.team_name`; keep the
      global driver team only as a compatibility fallback.
- [x] Add and run the Alembic migration plus a lightweight FastF1 results-only
      backfill: 2,278 entries across all 114 ingested 2021–2025 races.
- [x] Carry the player's own stint, completed-lap count, and absolute elapsed
      time between Engineer Mode decisions; recorded pit sequences cannot alter
      the player stint.
- [x] End a counterfactual race on the player's first line crossing after the
      leader finishes and classify by completed laps before elapsed time.
- [x] Apply the same completed-lap ordering to Monte Carlo competitor samples.
- [x] Add backend and frontend regressions for event teams, player stints,
      lapped finishes, chequered control flow, and simulated timing rows.
- [x] Replay the reported 2023 Canadian GP Stroll sequence: stints progress
      1→2→3→4 and the player finishes P18 on lap 68 rather than being forced to
      lap 70 and shown P14.
- [x] Verify 32 backend and 19 frontend tests, Ruff, Prettier, ESLint,
      TypeScript, Next.js production build, Alembic upgrade/drift, the 114-race
      data backfill, and the live four-stage Canadian GP API replay.

## Event-Wide Tyre-Life Calibration Correction

- [x] Replace the single maximum-age plus 40% rule with an event/compound model
      built from every driver's stint in the selected race.
- [x] Estimate pace slopes per stint after same-lap field normalization, then
      use a robust median, pooled fit, or labelled compound fallback.
- [x] Estimate the competitive service window from pit-ended stint ages while
      treating chequered-flag stints as right-censored survival evidence.
- [x] Use one nonlinear curve for health, late-stint pace loss, Monte Carlo
      degradation exposure, terminal reserve, and the 5% puncture rule.
- [x] Expose performance life, durability, sample count, and source in race
      state, strategy responses, diagnostics, and the Engineer Mode gauge.
- [x] Validate Canadian GP 2023 Hard against 28 field stints: ~38-lap
      performance window, ~61-lap terminal reserve, and puncture during a
      requested 62-lap stint rather than near-flat one-percent wear per lap.
- [x] Verify the live 100-run scenario as comparison 144 and pass 33 backend
      tests, 19 frontend tests, Ruff, Prettier, ESLint, TypeScript, Next.js
      production build, and Alembic drift checks.

## Strict Tyre-Health Pace and Failure Correction

- [x] Centralize the seconds-per-lap health curve in `TyrePerformanceConfig`;
      preserve the hard +4.2 s/lap calibration at 60% health.
- [x] Separate field-calibrated wear progression from pace loss and carry
      effective age plus health cumulatively between Engineer Mode decisions.
- [x] Normalize deterministic/learned projections to fresh pace before adding
      the health penalty once, preventing age double-counting or masking.
- [x] Reset a real pit-out lap to age/effective age 1 and 100% health; changing
      weather cannot restore health.
- [x] Implement the strict `<5.0%` `TYRE_FAILURE` rule, partial failure-lap
      timing, incomplete-lap classification, and termination of future laps.
- [x] Add bounded seeded Monte Carlo curve severity/cliff-onset uncertainty
      without randomizing health or allowing a failed tyre to survive.
- [x] Expose health, wear, seconds/lap penalty, next-lap values, tyre state,
      calibration source, and retirement reason through API and Engineer Mode.
- [x] Pass 42 backend and 19 frontend tests, Ruff/Prettier/ESLint/TypeScript,
      Next.js production build, Alembic upgrade/drift, and the calibration CLI.
- [x] Pass the real-data Engineer Mode matrix: 20 drivers, seven races, 80
      strategy outcomes, five seed-reproducibility repeats, zero failures in
      61.77 seconds; benchmark 1,000 samples at 2.294 ms simulation / 1.966 s
      end-to-end (comparison 248).
