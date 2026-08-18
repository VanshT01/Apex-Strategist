# Simulation Methodology

## Scope

Phase 5 layers seeded, CPU-friendly uncertainty on the Phase 4 deterministic
strategy engine. It compares two to five validated pit-now, delayed-pit, or
stay-out candidates. The deterministic result remains visible beside every
Monte Carlo aggregate and is the central expected-value anchor; no machine-
learning lap-time model or full vehicle-physics model is used by the Phase 5
strategy-lab baseline. Engineer Mode can opt into the separately versioned
`hgb-pace-v2` expected-pace layer described below.

The selected control point is the end of a completed lap. A pit on the control
lap means the tyre change occurs before the following racing lap.

## Deterministic anchor

- Running order uses FastF1's end-of-lap `Position`.
- Time gaps use end-of-lap session timestamps only when both cars completed the
  same lap. Lapped and retired cars receive a nullable gap.
- Recent pace is the mean of up to three recent non-pit, non-deleted laps.
- Weather is the latest sample at or before the selected driver's timestamp.
- The rejoin window adds estimated pit loss to the driver's historical time and
  compares it with same-lap field timestamps.
- Candidate deltas are applied to the driver's recorded finish time so recorded
  rain and neutralizations are not replaced by an invented constant dry race.

## Learned Engineer Mode pace

Engineer Mode no longer projects a stint as a fixed recent-lap baseline plus a
clamped linear tyre slope. `hgb-pace-v2` uses scikit-learn's CPU histogram
gradient-boosting regressor to learn a clean driver's delta to the same-lap
field median. Features are compound, driver, circuit, nonlinear tyre age, race
progress, position, and stint number. Fuel and track evolution therefore come
from the recorded field anchor while the counterfactual compound and tyre age
alter the selected driver's relative pace.

For a selected historical race, training rows come only from sessions whose
session date is strictly earlier. The selected driver's future laps are never
training inputs or part of the field anchor. Up to five eligible completed laps
adapt a bounded local driver offset; future recorded competitors remain the
documented central field anchor. Models require at least 2,000 prior clean laps
and otherwise fall back to the deterministic estimator. Artifacts use seed 42,
live under `data/models`, and are registered in `model_artifacts` with their
feature schema, cutoff, sample counts, and held-out MAE.

The learned prediction is an expected clean-lap pace, not a complete race
simulator. Existing deterministic rules still apply pit loss, compound/weather
mismatch, warm-up, unsupported-age tyre cliff, puncture/DNF handling, and field
classification. Monte Carlo continues to sample bounded seeded residuals
around the expected pace.

Validation holds out the newest prior sessions chronologically rather than
randomly splitting laps, preventing later-race information from appearing in
an earlier validation fold.

## Uncertainty calibration

Clean laps exclude pit-in/out, deleted, inaccurate, and unsuitable track-status
observations. Lap time is detrended within driver/compound/stint by tyre age.
Residual scale uses median absolute deviation and a trimmed standard deviation.
The hierarchy is:

1. selected driver in the current session;
2. selected driver's team in the current session;
3. all drivers in the current session;
4. historical laps at the same circuit location;
5. a conservative global 900 ms default.

The chosen residual scale is bounded to 250–2,500 ms. A persistent per-lap
driver pace scale is derived from it and bounded to 100–500 ms. Each source is
returned with its scale, sample count, fallback flag, and plain-language
assumption.

Tyre life is fitted separately for every event and compound from all
drivers' eligible stints. Each stint's lap time is expressed relative to the
same-lap field median before its age slope is fitted; the robust median of those
stint slopes avoids confusing fuel burn and track evolution with tyre wear. A
pooled event fit is used when fewer than three usable stint slopes exist, then a
labelled compound prior. Slopes remain bounded to 20–220 ms/lap as diagnostic
compound/circuit evidence; they no longer add a second age penalty on top of
the health curve.

Usable life is a separate field-stint survival model. For each compound it
groups every driver's laps by set/stint and measures the ending tyre age. The
75th percentile of pit-ended stints estimates the competitive service window,
blended conservatively with the compound prior. Stints ending at the chequered
flag are right-censored: they prove the tyre survived that age but do not claim
it was exhausted. Terminal reserve is at least three laps beyond the longest
observed surviving set, but the former blanket extra 40% is not added to an
outlier. With sparse evidence, the response explicitly labels an event-censored
or compound-life fallback.

Health falls gently early in the service window, accelerates to 60% at its end,
then follows a cubic smoothstep to exactly 5% at terminal reserve. Health is
cumulative: every lap consumes the field-life curve difference after supported
compound and recorded-condition wear multipliers. Conditions cannot restore
health; a real stop resets tyre age/effective age to 1 and health to 100%.

Pace loss is modeled in seconds per lap. With `wear = 100 - health`:

```text
base = 0.015 × wear + 0.00225 × wear²
cliff_wear = max(0, wear - 50)
loss_seconds = base + 0.006 × cliff_wear²
```

The learned/deterministic estimator supplies fresh baseline pace and this curve
is added exactly once. It yields 4.2 s/lap at 60% health and accelerates below
the 50%-health cliff. Exactly 5.0% remains running. Strictly below 5.0% produces
`TYRE_FAILURE`; a threshold-crossing lap is truncated at its crossing fraction,
is not marked complete, and ends all future normal lap generation. This is a
game rule rather than a physical failure-frequency estimate.

Tyre choice also follows explicit track-condition rules. Each future lap uses
the recorded rainfall observation plus the field's wet-compound usage to label
the track Dry, Damp, or Wet. On a dry track, Intermediates add 4.5 seconds per
lap and Full Wets add 8 seconds, with accelerated overheating wear. In damp
conditions, dry tyres add 3.5 seconds and Full Wets add 2.5 seconds. On a wet
track, dry compounds add 12 seconds per lap, accelerate reserve consumption,
and are marked unsafe; Intermediates add 1.5 seconds while Full Wets carry no
mismatch penalty. These deliberately simple public-data rules are applied to
both the candidate and recorded reference tyre. They are not a physical water-
depth or aquaplaning model.

Pit-loss samples retain valid 10–60-second paired pit intervals after robust
outlier rejection. Simulations bootstrap the accepted event sample. When it is
sparse, they use the estimator's bounded normal fallback; no negative or
impossible pit loss is allowed.

Compound-dependent first-two-lap warm-up variation is modest and mean-centred.
It is labelled as a conservative assumption because public timing alone cannot
cleanly separate warm-up from traffic, fuel, and driver effects.

Traffic probability is derived from the deterministic nearby-car/rejoin risk:
`clip(0.05 + 0.65 × risk, 0.05, 0.80)`. Conditional loss uses a bounded gamma
distribution from 0.3 to 7 seconds and is mean-centred so it does not silently
move the deterministic anchor. This remains an explicitly labelled heuristic,
not a calibrated overtaking model.

## Random generation and vectorization

Every generator is created with NumPy `default_rng` from a `SeedSequence`; the
module never uses mutable global random state. Request-level common random
numbers drive selected-driver pace, autocorrelated lap residuals, and competitor
uncertainty. A stable BLAKE2 hash of a candidate's semantic fields derives its
child sequence. Candidate names and list positions are excluded, so reordering
or adding a candidate does not change existing candidate samples.

Lap residuals use an AR(1) process with coefficient 0.35. This avoids treating
every lap as an unrelated extreme event. The simulator generates arrays shaped
`simulation_count × remaining_laps`, then vectorizes residual, degradation,
pit-loss, warm-up, traffic, time aggregation, and field comparison. Tyre-curve
severity is bounded to 0.9–1.1× and cliff onset to 45–55% wear; health remains
within 0–100% and the deterministic failure result is never randomized. Small loops
over laps, strategies, compounds, and competitors are retained for clarity; no
ORM query or DataFrame work occurs inside the simulation loop.

## Competitors and classification

Recorded competitor finish times and completed-lap counts remain the central
field anchor. Each receives a small bounded persistent pace offset and limited
aggregate residual uncertainty. Classification follows the essential F1 order:
more completed laps ranks ahead, then elapsed finish time orders cars on the
same lap. The player stops at their first finish-line crossing after the
recorded leader receives the chequered flag, which permits a counterfactual car
to finish one or more laps down instead of incorrectly forcing it through the
official race distance. Retired cars are not assigned false comparable finish
times. Random mechanical DNFs are not sampled. The interactive tyre model does
trigger a deterministic tyre-failure DNF below 5% modeled health, so the
finish distribution contains classified positions only.

> Competitors do not strategically react to the user's counterfactual choice.

This is an important limitation: the simulator is not a full 20-car behavioral
or regulation model.

## Aggregation and recommendation

Each candidate returns mean, median, and mode finish; mean and median race time;
mean/median delta from deterministic stay out; win, podium, points, better-than-
actual, and paired better-than-stay-out probabilities; 5th/25th/75th/95th race
time percentiles; 5th/95th finish percentiles; risks; finish counts; and a
compact time-delta histogram. Finish probabilities sum to approximately one.
Time values are rounded to 0.1 seconds and UI probabilities use whole or one-
decimal percentages to avoid false precision.

The recommendation sorts by median finish, paired chance of beating stay out,
median time, and downside finish/time. Structured rules report expected finish,
baseline advantage, traffic/degradation risk, and the 90% simulated finish
range. No LLM generates the recommendation.

The percentile band is a simulated interval under these assumptions. It is not
a guaranteed real-world confidence interval, and the probabilities are not
bookmaker odds or proof of a historical counterfactual.

## Safety Car and VSC

New Safety Car/VSC intervention sampling is deliberately disabled in
`monte-carlo-v2`. Older persisted `monte-carlo-v1` results remain readable. The calibration output exposes `safety_car_vsc` with source
`disabled_phase5_core`, making the boundary testable and visible. Recorded
interventions remain present through the historical finish-time anchor. The
tested `InterventionScenarioSampler` interface currently emits only
`NO_INTERVENTION` and zero pit-loss adjustment. It reserves explicit VSC and
Safety Car branches for future event-level calibration without changing the
aggregate contract.

## Persistence and API compatibility

`POST /api/v1/simulations/compare` accepts `simulation_count` (default 1,000,
minimum 100, maximum 10,000) and a bounded `random_seed` (default 42). The
configured `MAX_SIMULATION_COUNT` adds a deployment compute ceiling. The full
validated request, count, seed, engine version, deterministic inputs,
aggregates, histograms, calibration metadata, and assumptions use the existing
JSON persistence columns. Individual trajectories are not stored.

Interactive engineer requests may also include `simulation_context`. It is
optional for backward compatibility and carries the current counterfactual
compound, tyre age, position, player-owned stint, completed-lap count, absolute
elapsed time, and cumulative time delta. Returned projected laps include their
stint and recorded timestamp anchor, allowing the client to apply one lap and
pass the complete independent state into the user's next decision.

`GET /api/v1/simulations/{comparison_id}` reconstructs that response. Defaults
on newly added schema fields preserve retrieval of old `deterministic-v1`
records.

## Diagnostics and performance

```bash
PYTHONPATH=apps/api .venv/bin/python -m app.simulation.cli diagnose \
  --year 2024 --event "British Grand Prix"
PYTHONPATH=apps/api .venv/bin/python -m app.simulation.cli benchmark \
  --year 2024 --event "British Grand Prix" --simulation-count 1000 --random-seed 42
```

On the verified local 2024 British GP comparison (Lando Norris, lap 20, three
strategies, seed 42), 1,000 simulations took 4.337 ms for the NumPy simulation
calculation and 125.648 ms end to end, including database loading, calibration,
aggregation, and persistence. These are local measurements, not CI assertions;
the benchmark intentionally avoids a brittle wall-clock test.

## Remaining limitations

- Competitor strategies, team orders, overtakes, damage, and mechanical state
  do not react to the alternative decision.
- No new weather transition, Safety Car, VSC, red flag, or random mechanical DNF is sampled.
- Soft, Medium, Hard, Intermediate, and Wet are selectable. Sparse wet-compound
  evidence uses explicitly labelled conservative fallbacks; changing-weather
  counterfactuals still require extra caution.
- Warm-up and traffic are bounded assumptions where public data cannot isolate
  causal effects.
- Very long stints beyond the clean observed tyre-age range consume the final
  reserve. Exactly 5% survives and `<5%` triggers tyre-failure DNF; this is an
  explicit game rule, not a calibrated failure-frequency model.
- Public timing data cannot reveal tyre-set condition, setup, fuel correction,
  or team-private forecasts.
