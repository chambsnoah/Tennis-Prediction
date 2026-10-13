# Tennis-Prediction

A Python project for simulating and predicting tennis match outcomes using player statistics. The project supports both detailed and simplified player models, includes real-time API integration, and can simulate matches for various tournaments and years.

## 2026 ATP Pool Rules

The [auditable 2026 rules specification](docs/pool/2026-rules.md) records the
published rules, source fingerprints, and explicit best-guess assumptions for
issue #4. Development can use these provisional decisions with
`require_resolved(operation, allow_provisional=True)`; strict mode still requires
commissioner confirmation. The existing web team optimizer remains a legacy
budget workflow, not a validated 2026 pool optimizer.

---

## Features

- **Player Modeling:**  
  - Detailed player model with serve/return stats.
  - Simple player model with overall serve win percentage.

- **Match Simulation:**  
  - Simulates full tennis matches, including sets, games, tiebreaks, and service alternation.
  - Tracks detailed statistics: double faults, break points, tiebreaks, service/return points, and more.

- **API Integration:**
  - Real-time tennis data integration with caching and rate limiting.
  - Multiple data sources: TennisAPI1, ATP-WTA-ITF API, Jeff Sackmann's tennis_atp repository, Tennis Abstract.
  - Comprehensive historical data from 1968-present.
  - Automatic data extraction and processing from APIs, Git repositories, and web sources.

- **Web Interface:**  
  - Interactive web application for match simulation and team optimization.
  - Tournament bracket visualization and player statistics.

- **Tournament Data:**  
  - Includes data and scripts for major tournaments (Australian Open, French Open, Wimbledon, US Open) across multiple years.

- **Testing & Scripts:**  
  - Comprehensive test suite with automated verification scripts.
  - Performance comparison and edge case validation tools.

---

## Project Structure

```
.
├── 2023/ & 2024/          # Tournament data by year
├── tennis_preds/           # Core simulation engine
├── tennis_api/             # API integration module
├── web_interface/          # Web application
├── scripts/                # Test runners and verification tools
├── reports/                # Generated test reports
└── pytest.ini             # Test configuration
```

- **tennis_preds/**: Core simulation engine and player models.
- **tennis_api/**: Real-time API integration with caching, rate limiting, and data models.
- **web_interface/**: Interactive web application for simulations and team optimization.
- **scripts/**: Test runners, verification scripts, and development tools.
- **2023/** and **2024/**: Tournament data, scripts, and results for each year.

---

## Requirements

- Supported interpreters: Python 3.11, 3.12, and 3.13.
- Install [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.12.23.
- From the repository root, install all features and development tools:

```bash
uv sync --locked --python 3.13 --all-extras --group dev
```

`pyproject.toml` is the dependency source of truth; `uv.lock` pins the resolved
versions and artifact hashes for every supported interpreter. The old nested
requirements files and dependency helpers have been replaced by this workflow.
See [dependency management](docs/DEPENDENCIES.md) for feature-only installs,
lock updates, and clean-environment validation.

---

## Usage

### 1. Simulate a Match

You can simulate a match by creating `Player` or `PlayerSimple` objects and running a simulation:

```python
from tennis_preds.tennis import Player, TennisMatch

player1 = Player("Novak Djokovic", 0.73, 0.963, 0.80, 0.65)
player2 = Player("Carlos Alcaraz", 0.64, 0.974, 0.57, 0.68)
tennis_match = TennisMatch(player1, player2, sets_to_win=3, player1_to_serve=True)
tennis_match.simulate_match(verbose=True)
tennis_match.print_match_statistics()
```

### 2. Batch Simulations

To run multiple simulations and aggregate results, use the test code in [`tennis_preds/tennis.py`](tennis_preds/tennis.py):

```python
player1_wins = 0
player2_wins = 0
for i in range(1000):
    player1 = PlayerSimple("Player 1", 0.68)
    player2 = PlayerSimple("Player 2", 0.65)
    tennis_match = TennisMatch(player1, player2, sets_to_win=3, player1_to_serve=True)
    tennis_match.simulate_match()
    if tennis_match.player1_sets > tennis_match.player2_sets:
        player1_wins += 1
    else:
        player2_wins += 1

print(f"Player 1 wins: {player1_wins}, Player 2 wins: {player2_wins}")
```

### 3. Web Interface

Start the web application for interactive simulations:

```bash
uv run --locked --extra web python -m web_interface.server
```

Then open your browser to `http://localhost:5000` for:
- Interactive match simulations
- Team optimization tools
- Tournament bracket visualization

### 4. API Integration

Use the tennis API for real-time data:

```python
from tennis_api import TennisAPIClient, PlayerStats

# Initialize API client (requires .env configuration)
client = TennisAPIClient()

# Get player statistics
stats = client.get_player_stats("Novak Djokovic", tour="atp")
print(f"Serve win %: {stats.serve_win_pct}")
```

### 5. Running Tests

```bash
# Full project test suite (from the repository root)
uv run --locked --all-extras --group dev python -m pytest
```

Tests run with a fresh temporary working directory, isolated caches and quota
state, synthetic data, and blocked network access. Collection covers API,
models, core simulation, pool rules/scoring, workbook ingestion, and web routes.
Live provider contracts are skipped unless explicitly requested with
`--live`; these require `RAPID_API_APPLICATION_KEY` in the environment and may
consume provider quota. Ordinary tests never read your checkout's `.env`.

The CI workflow tests Python 3.11-3.13 and blocks on each failure, fatal Ruff
lint checks, strict mypy checks for pool rules/scoring and canonical contracts,
a locked dependency audit (including optional features and development tools),
and a redacted Gitleaks history scan. Legacy runner scripts delegate to pytest
and propagate its exit status; a partial pass is not a release or prediction-quality claim.
Type coverage can expand as feature and model modules land.

```bash
uv run --locked ruff check .
uv run --locked mypy
uv export --locked --all-extras --group dev --no-emit-project --no-hashes --no-annotate --no-header --output-file /tmp/tennis-audit.txt
uv run --locked pip-audit --strict --disable-pip --no-deps -r /tmp/tennis-audit.txt
```

Chronological model smoke evaluation will join these gates when the
backtesting harness in issue #12 is implemented; no accuracy threshold is
claimed by the current CI.

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
precede the prediction cutoff, and the target result is excluded from history.

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

The boundary is source adapters -> canonical records -> as-of tennis features ->
probability provider -> neutral simulation -> pool objectives -> presentation.
Prediction contexts accept no arbitrary feature dictionary or pool ownership,
quotas or scores. Legacy imports stay unchanged. Issue #2 removed fabricated
statistics defaults, but older numeric exports cannot be repaired without the
original observations and must not be migrated as measured data. Legacy ensemble
artifacts require retraining. Provider adapters follow in issue #10; canonical
contracts do not fetch or approve source data.

### Reviewed Player Identities

`tennis_api.models.identity.IdentityRegistry` is the adapter boundary for issue #8.
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

## Workbook Preview

`tennis_pool.workbooks.preview_workbook` is a read-only issue #11 adapter for
authorized `.xlsx` / `.xlsm` input. Install the existing `excel` extra. Supply a
canonical ATP `Event`, its explicit `year`, a `format` (`GS128`, `M7`, or `M6`),
a reviewed `IdentityRegistry`, and workbook `Provenance`; filenames never infer
metadata or identities. Every player label requires an exact, source-scoped
reviewed alias. Registry revision/digest and source provenance accompany results.

```python
from tennis_pool.workbooks import preview_workbook

# event, registry and evidence are caller-supplied reviewed records.
preview = preview_workbook(
    authorized_event_path, event=event, year=2026, format="M7",
    registry=registry, provenance=evidence,
    # Optional separate season file; its provenance must also be supplied.
    season_path=authorized_season_path, season_provenance=season_evidence,
)
```

The frozen preview contains a canonical draw, player-ID ranking measurements,
sheet coverage summaries, and private local observations in `preview.season`:
pick history (including substitute slot labels), standings, remaining banks,
use counts and provided substitutions. These records retain participant labels
for local reconciliation but are excluded from default preview representations;
never publish or log them. Missing values remain `None`; workbook rankings
have no inferred effective date and are not canonical as-of ranking snapshots.
No ledger, season consumption, scoring or commit API is implemented.

Supported formats cover the four Slams (`GS128`: 128 slots/entrants, 32 seeds),
Indian Wells, Miami, Madrid, Rome, Canada, Cincinnati and Shanghai (`M7`: 128
slots, 96 entrants, 32 seeds), and Monte Carlo/Paris (`M6`: 64 slots, 56 entrants,
16 seeds). Use the legacy French event labels in `TOURNAMENTS`; explicit
Australian Open/French Open and Canadian Masters/Toronto/Montreal labels are
also accepted. Canada remains one event, not separate venue events. Only trailing,
empty-result bye padding at positions 65-128 can be removed from an M6 sheet;
other padding is rejected, never rebracketed heuristically.

Layouts follow the reference's positional sheets: `Draw` header in column A,
then position/player/rank/seed; `Rankings` rank/player; `Choix` participant blocks
with 13 player/band pairs from column C; `Classement` rows from row 5, totals in
Q; `Banques (Solde restant)` quotas from row 3 (full season or Masters-only);
`ChoixSommaire` participant headers in row 3 and player/use rows from row 5.
Recognized header labels and column order are validated. `Choix` rows labeled
`Substitut`/`Remplacant` are alternatives; an optional `Substitutions` sheet uses
exact headers `Participant, Event, Withdrawn, Replacement, Band`. Substitution
legality/activation is not inferred. Conflicting copies of a support sheet in
the event and season files fail rather than silently overwrite one another.

Check `missing_sheets`, `unsupported_sheets`, summary `missing_values`, and
`warnings` before using a preview. Absent support files/sheets, Masters-only Slam
quotas and missing formula caches are explicit; nothing is filled with zero or
a guessed rank. Both cached-value and formula views are read, without formula
evaluation; missing identity caches make the affected layout unsupported.
`WorkbookImportError` exposes only safe reason codes. `WorkbookLimits` defaults
to 8 MiB/file, 32 MiB expanded ZIP, 256 members, 10,000 rows/sheet, 128 columns,
and 300,000 actual/dense cells across worksheets per file, enforced before
openpyxl parsing. DTD/entities and malformed/duplicate ZIP or cell structures are
rejected. Workbooks always close; VBA is not retained/executed and external links
are not loaded. Worksheet relationships must target local `xl/worksheets/*.xml`
members so relocated payloads cannot bypass preflight. This is bounded data
parsing, not an untrusted-file sandbox.

Tests generate wholly synthetic workbooks at runtime. No real workbook has been
audited or compatibility-certified; unfamiliar headers/layouts remain explicit
limitations. Legacy `pool_optimizer/pool/parsers.py` is unchanged. This adapter
does not authorize private-data publication or unblock historical retrieval in
issues #9/#10; the [historical source policy](docs/data/HISTORICAL_SOURCE_POLICY.md)
still applies.
