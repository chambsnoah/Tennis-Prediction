# Canonical Contracts and Models

Reference for the versioned records and model boundaries in `tennis_api`.

## Canonical Contracts

New pipeline code imports versioned records from
`tennis_api.models.canonical`, not the legacy provider models. The module defines
opaque namespaced player/event/match IDs, provenance, events, matches and scores,
ranking snapshots, measured player-match counts, fixed-order draws, and the
`MatchProbabilityProvider.predict(PredictionContext)` interface. Canonical IDs
must be resolved by adapters; names are display labels, not identity keys.

Records are immutable and support JSON-compatible `to_dict()` / `from_dict()`.
Every nested record requires schema version 1; unknown versions/fields fail
closed. Missing rankings/statistics are `None`, never plausible numeric defaults.
Times must be timezone-aware; date-only match times remain dates and are excluded
from history until the entire UTC day has passed. Availability must strictly
precede the prediction cutoff. When `PredictionContext.target_match_id` is set,
the target result is rejected from history; it defaults to `None`, so callers
that omit it must exclude the target result from `history` themselves.

Winners are player IDs. Scores and probabilities use player1/player2 order;
`swapped()` reverses scores or complements win probability without changing the
winner's or withdrawn player's identity. Unknown withdrawal identity stays
`None`; a known withdrawal identifies an entrant, never the walkover winner.
Probability responses declare model/calibration versions,
cutoff, coverage, warnings and whether availability risk is already included.
Call `require_context(context)` before consuming a response.
The response's `context_digest` must equal `context.digest`, binding all request
inputs (including event, format and historical snapshots) while preserving swaps.
Missing calibration version explicitly means uncalibrated; this interface does
not validate a model or imply detailed score/serve forecasts.

## Neutral Tournament Simulation

`tennis_api.simulation.tournament.simulate_tournament` runs neutral draws.
Install `--extra simulation` for NumPy without the ML stack (`ml` also supplies
NumPy). It accepts a canonical `Draw` and `MatchProbabilityProvider`:

```python
import numpy as np
from tennis_api.simulation.tournament import simulate_tournament

result = simulate_tournament(
    draw, provider, cutoff=cutoff, simulations=20_000,
    rng=np.random.default_rng(7),
)
```

`draw`, `provider` and the timezone-aware `cutoff` are caller-supplied; no live
source, model, or fallback is selected automatically. Optional `rankings`,
`history` and `statistics` are canonical as-of snapshots. Rankings are filtered
to each matchup; shared history/statistics must strictly predate the cutoff.
The provider is queried once per unique modeled pair in each round, not once per
simulation, so repeated samples of the same pair share one entry in
`result.predictions`. Each response's binding is validated, and its
model/calibration versions, coverage and warnings are retained there. Surface and best-of format come from the event unchanged.

Arrays in `result.rounds` contain bracket-ordered player1/player2/winner indices
into `result.player_ids`, plus `OutcomeKind` codes. `-1` means a vacant side or
no champion. `result.round_reach[player, simulation]` is the last round entered,
with `round_count + 1` for a champion and zero for a pre-event withdrawal. A bye
advances a player but is not a played win; use outcome kinds to distinguish
contested decisions, uncontested advancement, forced retirements and vacancies.
Arrays are read-only by default. Pool points, upset bonuses and roster choices
are deliberately absent. Unresolved qualifiers/lucky losers fail closed; resolve
them or supply an explicitly revised draw. Replacements keep their fixed slots.

There are **no implicit injury/withdrawal hazards**. Optional `withdrawn` is a
frozenset of pre-first-match withdrawn player IDs. Optional `retirements` is a
tuple of `ForcedRetirement(player_id, round_number)` scenarios, applied only if
that player reaches a contested match in that round. Simultaneous opponent
retirements require adjudication and raise an error; all-withdrawn brackets have
no champion. Any explicit availability scenario rejects provider responses that
already include availability risk. Provider-only probabilities may marginalize
retirement risk, but `DECIDED` never asserts a completed match or invents a
retirement identity, scoreline or duration. Scenario runs are conditional on
caller assumptions, not estimates of the scenarios' likelihood.

For replay, retain the original draw and as-of inputs, provider artifacts,
locked NumPy version, simulation count, and the returned draw digest, cutoff,
simulator version, scenario configuration and initial RNG state JSON. Restore
the named NumPy bit generator's state before replay; seeds reproduce runs within
the same implementation/dependency versions. This simulator is not wired to the
legacy web optimizer and does not establish prediction quality.

The strict simulation type gate is
`uv run --locked --extra simulation mypy --python-version 3.13 tennis_api/simulation/tournament.py`.
The parser target accommodates NumPy's newer stubs; runtime tests cover 3.11-3.13.

The boundary is source adapters -> canonical records -> as-of tennis features ->
probability provider -> neutral simulation -> pool objectives -> presentation.
Prediction contexts accept no arbitrary feature dictionary or pool ownership,
quotas or scores. Legacy imports stay unchanged. Fabricated statistics defaults
were removed, but older numeric exports cannot be repaired without the
original observations and must not be migrated as measured data. Legacy ensemble
artifacts require retraining. Provider adapters are future work; canonical
contracts do not fetch or approve source data.

## Reviewed Player Identities

`tennis_api.models.identity.IdentityRegistry` is the player-identity adapter boundary.
It stores canonical `Player` records, reviewed `ProviderMapping` records and
`ReviewedAlias` records for workbook names. Each mapping carries source evidence,
reviewer and timezone-aware review time. Provider IDs are opaque strings scoped
by source and tour, preserving leading zeros; duplicate/colliding keys and dangling
or cross-tour player references fail at registry construction.

Call `resolve(source=..., tour=Tour.ATP, external_id=...)` for historical/current
provider records or `resolve(source=..., tour=Tour.ATP, name=...)` for an exact
reviewed workbook alias. Unknown provider IDs never fall back to names. Accent,
case and surname normalization is used only by `candidates()` for review, never
to accept an identity. A supplied provider ID and conflicting reviewed name also
fail closed. Catch `IdentityResolutionError` to quarantine the input with its
`reason` and candidate IDs; do not emit canonical training records for that row.

Registries are immutable revision snapshots with strict version-1 JSON
`to_dict()` / `from_dict()` round trips and an order-independent SHA-256 `digest`.
Record revision and digest with downstream datasets. To approve a candidate or
rename, create a new revision with an evidenced mapping/alias and keep the old
snapshot for replay. Changing a display name never creates a new canonical ID.
The synthetic test mappings are not real source approvals; no live data is
fetched and legacy name-based APIs are unchanged until their adapters migrate.

## Cited Information Observations

`tennis_api.models.information` is a local, reporting-only replacement
contract for name-keyed form overrides. Legacy code and files are not migrated or
modified. An `Observation` has a canonical player/event/tour scope, citation,
certainty in `[0, 1]`, positive `record_version`, registry revision/digest, and
`Provenance` containing the source, pinned source revision (`source_version`),
source record ID, observed/available/ingested timestamps. `effective_at` and
`expires_at` delimit its validity. All times are timezone-aware and normalized to
UTC. Missing observed times, record IDs, unsupported schemas/fields and invalid
payloads fail closed.

The payload is exactly one of `MarketAdjustment`, `AnalystOpinion`,
`VerifiedWithdrawal` or `InjuryRisk`; `observation.kind` is derived from that typed
payload. A market adjustment is a signed match-win probability change with explicit
`probability_points` (range `[-1, 1]`) or `percentage_points` (`[-100, 100]`) units
and independent, cited adjustment provenance. `0.02` probability points equals
`2` percentage points. Analyst opinions are text, verified withdrawals require a
strict boolean, and injury estimates require a probability in `[0, 1]`. Certainty
does not turn an opinion into a measurement or replace injury probability.
Nothing in this module adjusts model probabilities, sums deltas or activates a
withdrawal automatically.

```python
from tennis_api.models.information import InformationCollection, InformationKind, Observation

# local_json is a version-1 observation JSON object without player_id,
# registry_revision or registry_digest; registry is a reviewed IdentityRegistry.
item = Observation.import_local(local_json, registry=registry, external_id="001")
# Alternatively name=... requires an exact, source/tour-scoped reviewed alias.
collection = InformationCollection(revision="local-r1", observations=(item,))
snapshot = collection.as_of(
    cutoff=prediction_cutoff, event_id=item.event_id, tour=item.tour,
    player_ids=(item.player_id,),
)
report = snapshot.state(item.player_id, InformationKind.INJURY_RISK)
print(report.status, report.missing)  # Never substitute missing risk with zero.
saved_json = snapshot.to_dict()      # InformationSnapshot.from_dict(...) replays it.
```

`Observation.from_dict()` replays already-canonical records; `import_local()`
resolves local source IDs or reviewed aliases and records the registry lineage.
Unknown provider IDs never fall back to names. `InformationCollection` and
`InformationSnapshot` are immutable version-1 contracts with strict JSON round
trips and deterministic SHA-256 digests. Collections deduplicate identical source
record/version imports, including imports resolved through different aliases;
different contents for that same key are rejected. `extend(revision=...,
observations=(... ,))` requires a new collection revision and retains prior record
versions. Record revisions cannot change player/event/tour/kind or move source
availability backwards. Local ingestion may arrive out of order when backfilling
older revisions; each record still has to meet its own ingestion cutoff. The
highest visible record version supersedes earlier
versions when known, even if its effective time is still pending; earlier cutoffs
retain their earlier versions. Preserve old collections/snapshots for audit.

Availability must be **strictly before** the cutoff. The default `locally_known`
mode also requires ingestion strictly before it. Active validity is
`effective_at <= cutoff < expires_at`; expiry at the cutoff is stale. Reports
retain separate `active`, `stale` and `pending` evidence tuples, with a status of
`active`, `conflicting`, `stale`, `pending` or `missing`. Every requested player
has a report for every kind; no active evidence means `missing=True`, including
stale/pending-only cases. Different active values are conflicts, regardless of
certainty or source preference. Equal values from independent records remain
separate citations, not accumulated adjustments; equivalent market units agree.
No conflicting winner is chosen. Only the requested event, tour and player roster
can enter a snapshot; information is never implicitly shared across events.

For a later local import to support a backtest, explicitly request
`mode=SnapshotMode.HISTORICAL_RECONSTRUCTION` and supply each observation's
`historical_snapshot: Provenance`. This must cite an archived snapshot record and
revision, captured no earlier than the observation's claimed source availability;
the archive itself must have been available strictly before the cutoff. It must
have been ingested no later than the observation that cites it. Reconstruction
mode requires this evidence for every selected record. A current snapshot,
backdated availability alone, or a later archive never establishes historical
knowledge. Mode and archive lineage persist in snapshot JSON/digests. These are
validated caller-supplied evidence declarations, not independent authentication of
the archive or permission to retrieve it; retain and review the cited artifacts.

**No live provider is approved for this workflow.** The
[historical source policy](data/historical_source_policy.json) remains
blocked. Snapshots explicitly report
`refresh_status="blocked_no_approved_provider"`; this module performs no network
refresh and adds no provider adapter. Existing legacy API examples in
the [README](../README.md) do not approve a source for information observations or backtests.
Tests use synthetic records only and never read the separate `/tennis` project.

## Local App and Services

`web_interface` is the single-user local app. One command starts it:

```bash
uv run --locked --extra web --extra excel --extra simulation python -m web_interface
```

It binds `127.0.0.1` only (there is no host option), never enables the
Werkzeug debugger or reloader, and accepts only `127.0.0.1`/`localhost` Host
headers, so a DNS-rebinding page cannot reach it. POST requests with a foreign
`Origin` are refused, JSON routes require `application/json` and the upload
route `application/octet-stream`, so a cross-site page cannot send a simple
form post. Public or multi-user hosting is out of scope.

**Typed services.** Routes call `web_interface.services.LocalServices`
directly; nothing shells out or parses a script's output. Each method validates
untrusted JSON into a typed job record (`MatchSimulationJob`,
`TeamOptimizationJob`, `WorkbookPreviewJob`, `PredictionJob`, `ScenarioJob`,
`RecommendationJob`) and runs it through the job runner. Python callers can
build these records and call the job functions or `preview_upload` themselves.

| Route | Service | Notes |
| --- | --- | --- |
| `GET /api/status` | `status` | Effective limits and which OS limits workers get; no paths or environment values |
| `GET /api/tournaments`, `/api/players/<year>/<slug>/<gender>`, `/api/bracket/...` | legacy catalog | 2023/2024 JSON under `TENNIS_DATA_ROOT` |
| `POST /api/simulate-match` | `simulate_match` | Unvalidated synthetic heuristic, seeded, at most 20,000 matches |
| `POST /api/optimize-team` | `optimize_team` | Legacy budget annealing, seeded, from the cheapest full team; not 2026 decision support |
| `POST /api/workbooks/preview?event_id=&format=` | `preview_workbook` | Raw workbook body, at most 8 MiB; returns the canonical draw and counts only |
| `POST /api/predict` | `predict` | `{artifact, context}`: a canonical `PredictionContext`; the response must bind to it |
| `POST /api/pool/scenarios` | `simulate_tournament` | `build_scenarios` over a canonical draw; per-player mean/p90 points and the rule register used |
| `POST /api/pool/recommend` | `recommend` | Scenarios plus `optimizer.recommend` for a configured pool `event_id` (the draw's event and scoring kind must match it) and optional `EntryState` |

**No request paths.** Legacy tournaments are addressed by catalog ID
(`YYYY/slug`, fixed patterns), pool events by an ID from the configured
`events.json`, and providers by a manifest artifact name. Files are opened below
their root one component at a time with `O_NOFOLLOW`, so `..`, separators,
absolute paths and symlinks never resolve, and every read is size-bounded and
schema-checked. Static routes serve only `index.html`, `app.js` and
`styles.css`. Pool calls always use the bundled rule register (no
`register_path`), and `allow_provisional` must be a JSON boolean defaulting to
`false`, so strict mode still blocks with `rules_unresolved`. Scenario results
report the rule register version and each decision's status.

**Bounded jobs.** `web_interface.jobs.JobRunner` runs each job's registered
`module:function` in a fresh `spawn` worker with a typed payload and a pipe for
the result. At most `max_concurrent` jobs run (2 by default); another request
gets `busy` (429) rather than an unbounded queue. A job past its wall-clock
deadline (120 s), including one still sending its result, is killed
(`job_timeout`, 504), with `RLIMIT_CPU` as a backstop. Uploaded workbooks are
staged in an owner-only folder the server removes after the worker is reaped. `RLIMIT_AS` (4 GiB) caps memory where the OS enforces it: Linux does,
macOS refuses to lower it, and `/api/status` reports which limits took effect.
Payloads (16 MiB) and results (8 MiB) are bounded, numeric libraries run
single-threaded, and simulation counts, withdrawal entries (128), withdrawal
patterns (64), rankings (256), team size and budget have fixed caps. The limits
live in `LocalAppConfig` and `JobLimits`; the environment only selects
`TENNIS_DATA_ROOT`, `TENNIS_POOL_ROOT`, `TENNIS_PORT` and an optional
`TENNIS_ARTIFACT_MANIFEST_SHA256`. Requests without a `seed` use 2026, so equal
inputs give equal results.

**Safe errors.** Refusals are `{"error": "<reason_code>"}` with a fitting
status. Workbook failures keep `preview_workbook`'s safe reason codes. Any other
exception, in a route or a worker, returns `internal_error` with a random
request ID and is logged by exception type only: messages and tracebacks can
contain paths or credentials, so they are never returned or logged. No route
returns configuration paths or environment values.

**Pool inputs and trusted artifacts.** `TENNIS_POOL_ROOT` is an operator-owned
directory (owned by the running user, not group or world writable) holding a
reviewed `registry.json` (`IdentityRegistry.to_dict()`), `events.json`
(`{"schema_version": 1, "events": {"<pool event id>": <canonical Event>}}`) and
optionally `artifacts/manifest.json`:

```json
{"schema_version": 1, "artifacts": [
  {"name": "model-a", "file": "model-a.bin", "kind": "<loader kind>",
   "sha256": "<64 hex>", "bytes": 1234}]}
```

The server only resolves an artifact name; the job worker, holding a job slot,
reads it once (bounded by its declared size), hashes it and compares the pinned
digest, and the provider loader deserializes those same bytes. A changed,
resized, symlinked, foreign-owned or group/world-writable artifact, or a
symlinked `artifacts` folder, is refused. A file that exists but cannot be read
is reported as `file_unreadable`, never treated as absent. Pinning the manifest
itself with `TENNIS_ARTIFACT_MANIFEST_SHA256` also refuses an edited manifest.
Loaders map a manifest `kind` to a `module:function` in
`LocalAppConfig.provider_loaders`; they are set in code only, never by a
request or environment variable. No loader ships yet: calibrated model
artifacts are future work, so prediction and pool routes answer
`no_provider_loader` until one is configured. Legacy pickle/joblib ensembles are
not loadable through this boundary.

Tests build synthetic tournaments, workbooks, registries, draws and a fixture
provider at runtime; the fixture provider is uncalibrated and exists only to
exercise the boundary.
