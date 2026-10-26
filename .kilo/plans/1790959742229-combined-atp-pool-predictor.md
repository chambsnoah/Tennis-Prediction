# Combined ATP Pool Predictor Plan

## Goal

Build an ATP-first, local single-user product in `Tennis-Prediction` that provides calibrated pre-match probabilities, tournament forecasts, and the exact 2026 pool scoring/quota/roster workflow currently implemented in `/Users/noahc/Documents/projects/tennis`.

The first release is complete only when match probabilities pass chronological validation and those probabilities drive bracket simulation and pool optimization end to end.

## Decisions

- `Tennis-Prediction` is the destination repository; `/tennis` remains a read-only reference during migration.
- ATP only for the first release. WTA becomes a later, separately evaluated cohort.
- A legally approved multi-year historical ATP dataset is required; existing workbooks alone are insufficient for model training.
- Initial deployment is local single-user. Public authentication, multi-tenancy, and horizontal scaling are out of scope.
- Implement the exact 2026 pool rules first rather than a generic rules engine.
- Match quality is evaluated independently from bracket and pool outcomes.
- Primary model metric is chronological holdout log loss; Brier score and calibration are release gates. Accuracy is secondary.
- Existing untrained/synthetic Phase 2 accuracy claims are not baselines and must not be carried forward.

## Target Boundaries

Create clear layers with no reverse dependencies:

```text
approved raw sources
  -> canonical data + identity resolution
  -> as-of feature snapshots
  -> probability models + calibration
  -> tournament simulation
  -> 2026 scoring and pool optimization
  -> local service/UI
```

Suggested package boundaries:

```text
tennis_data/       canonical schemas, ingestion, identity, validation
tennis_ml/         features, Elo, training, calibration, evaluation, artifacts
tennis_preds/      retained point/game/set simulator and probability interfaces
tennis_tournament/ draw conversion and vectorized tournament simulation
tennis_pool/       2026 rules, ownership model, quotas, roster optimization
web_interface/     local presentation and orchestration only
```

Do not let `tennis_pool` features feed the match model. Ownership, quotas, fantasy scores, and realized pool outcomes are downstream objectives, not match labels.

## Work Plan

### 1. Establish Reproducible Project Gates

- Add one supported Python version range and package metadata in `pyproject.toml`.
- Separate runtime, ML, development, and optional web dependencies; lock them reproducibly.
- Add CI jobs for formatting/linting, type checks, unit tests, chronological smoke backtest, dependency audit, and secret scanning.
- Make tests use temporary cache/state directories and remove import-time side effects.
- Record deterministic seeds, dataset digest, code revision, feature schema version, and model version for every training/evaluation run.

Acceptance gate:

- A clean environment can install the project and run the test suite through one documented command.
- CI fails on any test failure; the current 80% "production ready" threshold is removed.

### 2. Define Canonical Tennis Contracts

- Define stable IDs and typed records for `Player`, `Tournament`, `RankingSnapshot`, `Match`, `MatchScore`, `PlayerMatchStats`, `Draw`, and `PredictionContext`.
- Include event timestamps, source provenance, ingestion timestamps, surface, indoor/outdoor status, round, best-of format, retirement/walkover state, and optional odds snapshot IDs.
- Define one winner encoding throughout the system.
- Define a `MatchProbabilityProvider` protocol returning player-one probability, model version, calibration version, feature cutoff, and warnings.
- Define typed, expiring current-information records for withdrawal, injury assessment, analyst adjustment, H2H note, and market snapshot.
- Retain accent/case normalization from `/tennis/pool/parsers.py` only as a fallback; canonical joins use stable IDs.

Acceptance gate:

- Round-trip serialization tests exist for every contract.
- Duplicate names, renamed players, missing ranks, byes, retirements, qualifiers, and walkovers have explicit behavior.

### 3. Build Approved Historical Ingestion

- Select and document an approved ATP source covering multiple seasons with match dates, results, rankings, scores, surfaces, and serve/return statistics where available.
- Store source terms, permitted use, retrieval date, checksum, and schema version before ingestion.
- Implement source adapters into the canonical contracts without embedding provider-specific fields downstream.
- Import existing `2023/` and `2024/` JSON files as regression fixtures, not authoritative training labels.
- Convert the eleven `/tennis/data/*.xlsm` workbooks into validated draw/result/pool fixtures, subject to privacy and licensing review.
- Add data-quality checks for uniqueness, referential integrity, impossible dates/scores, winner consistency, duplicates, and schema drift.

Acceptance gate:

- Re-running ingestion is idempotent and produces identical dataset digests.
- Every feature-relevant record has a usable event timestamp and source.
- Quarantined records are reported rather than silently defaulted.

### 4. Port and Correct the Elo Baselines

- Port `rank_elo`, `win_prob`, `StrengthModel`, and cutoff-first update concepts from `/tennis/pool/strength.py` into `tennis_ml`.
- Replace surname keys with canonical player IDs.
- Update matches in true chronological order; freeze ratings for simultaneous matches where ordering is unknown.
- Add overall Elo plus surface-specific ratings with shrinkage toward overall strength.
- Wire actual tournament surface metadata; remove the current hard-coded `target_surface="hard"` behavior.
- Tune Elo scale, K factor, recency decay, surface shrinkage, and best-of adjustment only on training folds.
- Keep manual injury, H2H, and market deltas out of the baseline.

Acceptance gate:

- Chronological tests prove no match updates a rating used to predict itself or an earlier match.
- Rank-only, overall Elo, and surface Elo baselines have stored holdout log loss, Brier score, accuracy, and reliability plots.

### 5. Build the As-Of Feature Pipeline

- Rewrite `tennis_api/ml/feature_engineering.py` as a deterministic, timestamp-aware pipeline over canonical records.
- Initial features: overall Elo, surface Elo, ranking level/difference, serve and return strength, recent opponent-adjusted form, surface form with sample-size shrinkage, age/career phase, rest days, recent minutes, tournament level, round, best-of format, indoor/outdoor, and known pre-match availability.
- Add missingness indicators instead of silently replacing all unknowns with tour averages.
- Encode categorical surfaces explicitly rather than ordinally.
- Generate both player orientations and enforce complementary predictions so swapping players yields `1 - p`.
- Fit all scalers, imputers, selectors, and encoders inside each chronological training fold.

Acceptance gate:

- Automated leakage tests assert every source timestamp is strictly earlier than match start.
- Orientation, range, missing-data, duplicate-record, and sparse-player property tests pass.
- Feature snapshots are reproducible from dataset digest plus cutoff timestamp.

### 6. Train and Calibrate Match Models

- Train a regularized logistic model as the interpretable feature baseline.
- Train one boosted-tree candidate, initially LightGBM or XGBoost, using the same feature contracts and folds.
- Use expanding-window validation with tournament/date boundaries and a final untouched chronological season holdout.
- Produce out-of-fold predictions for calibration; compare Platt, isotonic, and beta calibration without fitting on the final holdout.
- Blend models only if the blend improves chronological log loss and calibration consistently, not merely accuracy.
- Persist the complete inference pipeline, feature schema, calibration object, metadata, and hashes as one versioned artifact.
- Fail closed when no trained artifact is available; never display heuristic fallback output as an ML prediction.

Acceptance gate:

- The selected model beats rank-only Elo on final holdout log loss and does not regress materially against surface Elo on Brier score.
- Reliability plots and metrics are reported overall and by surface, tournament level, round, ranking tier, and best-of format.
- Loading a saved artifact reproduces prediction vectors exactly within numeric tolerance.

### 7. Separate Fast Tournament Simulation From Detailed Match Simulation

- Port the vectorized bracket mechanics from `/tennis/pool/simulate.py` into `tennis_tournament`.
- Replace its hard-wired Elo array with `MatchProbabilityProvider` calls or a precomputed probability matrix.
- Preserve fixed draw positions, byes, late withdrawals, seeded replacements, round reach, finalist, and champion distributions.
- Inject a local RNG; never mutate global random state.
- Keep fantasy scoring outside the simulator and return neutral tournament outcomes.
- Retain `tennis_preds/tennis.py` for optional scoreline/stat projections; refactor it to injected RNG and add rules tests before using it in product output.
- Do not port `tennis_api/simulation/enhanced_match_engine.py`; validated dynamic factors should enter probabilities or the canonical simulator later.

Acceptance gate:

- Small deterministic brackets match hand-calculated probabilities.
- Vectorized results converge to analytic expectations within documented Monte Carlo tolerance.
- Byes, withdrawals, deciding-set tiebreaks, serving order, and swapped-player symmetry have tests.

### 8. Port Exact 2026 Pool Rules

- Move scoring logic from `/tennis/pool/scoring.py` into `tennis_pool` without generalizing it prematurely.
- Convert `/tennis/tests/test_scoring.py` and workbook comparisons into parameterized tests.
- Reproduce all documented 564 player-tournament scoring records before changing behavior.
- Port quota banks, player-use caps, bands, five-player roster constraints, and historical state reconstruction.
- Make tournament cutoff explicit so historical pool state cannot see later selections or standings.

Acceptance gate:

- Workbook-grounded ATP points, bonuses, totals, quotas, and usage match exactly.
- Invalid rosters return typed constraint failures rather than being silently repaired.

### 9. Port Pool Optimization and Isolate Ownership Risk

- Port constrained roster enumeration/evaluation from `/tennis/pool/optimize.py`; replace the current annealing implementation.
- Validate global optimality against brute force on small fixtures.
- Compute expected points, variance, quantiles, win probability, and top-three probability from shared tournament simulations.
- Port `FieldModel` only as an optional opponent module with a versioned output and explicit uncertainty.
- Refit ownership behavior using historical cutoff data and report calibration separately from match-model calibration.
- Provide optimization modes for maximum expected score, top-three probability, and constrained contrarian exposure.

Acceptance gate:

- Every recommended roster satisfies exact quotas, caps, bands, and budget rules.
- Match uncertainty and opponent-pick uncertainty can be seeded and evaluated separately.
- Pool output clearly labels when ownership estimates are weak or unavailable.

### 10. Integrate a Safe Local Product Flow

- Replace Flask subprocess orchestration with direct typed service calls.
- Replace caller-controlled filesystem paths with server-side tournament IDs and an allowlisted registry.
- Default to loopback binding with debug disabled; validate request sizes and numeric ranges even for local use.
- Expose local workflows for match prediction, bracket simulation, player round/title probabilities, roster optimization, and model/report provenance.
- Show calibration/model version, data cutoff, missing-data warnings, and simulation count in the UI.
- Preserve the existing visual workflows where practical, but do not expose untrained or stale predictions.

Acceptance gate:

- One command starts the local application against a selected versioned model artifact.
- An end-to-end fixture flows from draw ingestion through probabilities, simulations, pool scores, and a legal optimized roster.
- Path traversal, unbounded simulations, raw internal errors, and debug exposure are covered by tests.

### 11. Shadow Comparison and Cutover

- Run the new model alongside the current seed heuristic and `/tennis` Elo for historical tournaments.
- Compare match metrics first, then bracket distributions, then pool outcomes; do not select a model based only on pool cashes.
- Preserve old JSON outputs and reports as read-only fixtures during comparison.
- Switch the local UI only after the selected artifact passes all match, simulation, scoring, and roster gates.
- Keep a configuration switch to select the previous local heuristic during one stabilization period; remove it after reproducibility and scoring parity are confirmed.

Acceptance gate:

- A versioned evaluation report documents baselines, chronological folds, final holdout, calibration, error cohorts, simulation convergence, pool scoring parity, and known limitations.
- The release can be reproduced from clean checkout, approved raw-data digests, and recorded configuration.

### 12. Post-Release Extensions

Execute only after the ATP release gates pass:

- Add WTA as a separately trained and calibrated cohort.
- Generalize 2026 scoring into a configurable pool-rules schema.
- Add versioned historical odds and evaluate them as baseline or ensemble input.
- Add scoreline/duration models and richer point-level simulation.
- Replace local-only deployment with a private hosted service, including authentication, job limits, observability, and secure artifact/data storage.

## Parallel Workstreams

After canonical contracts are frozen, these can proceed concurrently:

- Historical source ingestion and data validation.
- Elo baseline implementation and evaluation harness.
- Core simulator rules tests and RNG refactor.
- Workbook scoring-fixture conversion.
- Packaging, CI, and isolated test infrastructure.

These remain dependency ordered:

- Feature engineering follows canonical ingestion.
- Model training follows the chronological evaluation harness.
- Tournament forecasts follow a stable probability-provider contract.
- Pool optimization follows neutral tournament simulation and exact scoring parity.
- UI cutover follows every earlier acceptance gate.

## Principal Risks

- **Data licensing:** block ingestion until permitted use and redistribution are documented.
- **Temporal leakage:** enforce timestamps in schemas and automated feature-lineage tests, not reviewer convention.
- **Identity collisions:** do not train until ambiguous names are resolved or quarantined.
- **Sparse surface data:** use hierarchical shrinkage and report cohort uncertainty.
- **Manual news contamination:** require effective timestamps, sources, expiry, and separate provenance; exclude from historical evaluation unless archived as-of snapshots exist.
- **Market leakage:** never use closing or post-start prices for pre-match predictions.
- **Pool overfitting:** judge probability models on match holdouts before inspecting pool performance.
- **Simulation false precision:** publish Monte Carlo error/convergence and keep model uncertainty distinct from simulation noise.

## Release Definition

The combined ATP pool predictor is releasable when:

- Approved multi-year data ingest reproducibly with stable identities and timestamps.
- A calibrated model beats documented rank and surface-Elo baselines on untouched chronological holdout log loss.
- Calibration and Brier metrics meet documented thresholds across major cohorts.
- Tournament simulation passes analytic and rules-based validation.
- All 2026 scoring fixtures match and every optimized roster is legal.
- The local UI runs without subprocesses, arbitrary filesystem access, debug exposure, or silent heuristic fallbacks.
- Model, dataset, feature, calibration, and simulation versions are visible and reproducible.
