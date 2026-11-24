# Tennis-Prediction

A Python project for simulating and predicting tennis match outcomes using player statistics. The project supports both detailed and simplified player models, includes real-time API integration, and can simulate matches for various tournaments and years.

## 2026 ATP Pool Rules

The [auditable 2026 rules specification](docs/pool/2026-rules.md) records the
published rules, source fingerprints, and explicit best-guess assumptions.
Development can use these provisional decisions with
`require_resolved(operation, allow_provisional=True)`; strict mode still requires
commissioner confirmation. The existing web team optimizer remains a legacy
budget workflow, not a validated 2026 pool optimizer.

Pool scoring, the season ledger, paired substitutes, payouts, the joint roster
optimizer and workbook preview are documented in [pool modules](docs/pool/modules.md).

---

## Features

- **Player Modeling:**  
  - Detailed player model with serve/return stats.
  - Simple player model with overall serve win percentage.

- **Match Simulation:**  
  - Canonical `TennisMatch` rules sandbox for sets, games, tiebreaks, and service alternation using caller-supplied serve probabilities.
  - Tracks synthetic match statistics; these are not validated score, statistics or duration forecasts.

- **API Integration:**
  - Real-time tennis data integration with caching and rate limiting.
  - Multiple data sources: TennisAPI1, ATP-WTA-ITF API, Jeff Sackmann's tennis_atp repository, Tennis Abstract.
  - Comprehensive historical data from 1968-present.
  - Automatic data extraction and processing from APIs, Git repositories, and web sources.

- **Web Interface:**  
  - Interactive web application for explicitly unvalidated heuristic win simulations and legacy team optimization.
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

### 1. Synthetic Rules Sandbox

`tennis_preds.tennis.TennisMatch` is the sole supported detailed point/game/set
rules engine. Create `Player` or `PlayerSimple` objects with explicit synthetic
serve probabilities to exercise those mechanics. The example inputs below are
illustrative, not measured player statistics or calibrated predictions:

```python
from tennis_preds.tennis import Player, TennisMatch

player1 = Player("Novak Djokovic", 0.73, 0.963, 0.80, 0.65)
player2 = Player("Carlos Alcaraz", 0.64, 0.974, 0.57, 0.68)
tennis_match = TennisMatch(player1, player2, sets_to_win=3, player1_to_serve=True)
tennis_match.simulate_match(verbose=True)
tennis_match.print_match_statistics()
```

Detailed scorelines, serve/return statistics and match duration are optional
forecasting outputs, not consequences of having a match-win probability. No
model-to-serve mapping has been validated, so those forecasts are unavailable;
synthetic rules runs must not be presented as model-derived detailed forecasts.
The legacy `ScorePredictor` also returns an unavailable result, even if its
regressors have been fitted. Ensemble score/game/duration fields and score
confidence are `None` (JSON `null`), with `detailed_forecast` status/reason;
unvalidated score models do not contribute to ensemble confidence or explanations.

Matches use an isolated `random.Random(seed)` by default, or accept an injected
`rng` with a `random()` method. Do not supply both. Use `sets_to_win=2` for
best-of-three and `3` for best-of-five; `1` remains supported for single-set
sandbox/smoke runs. Ordinary tiebreaks are seven points, win by two; the deciding
set uses ten by default (modern Slam rules). Set
`deciding_tiebreak_points=7` explicitly for a standard ATP best-of-three event.
The first receiver of a tiebreak serves first in the next set. Service-game
counts exclude tiebreaks; serve/return point totals include them. Percentages
with no attempted/landed serves print as `N/A`, not invented zero observations.

The duplicate `tennis_api.simulation.EnhancedMatchEngine` is deprecated and
retained for historical reference and adapter compatibility. Its `simulate_match`
emits `DeprecationWarning` and raises `NotImplementedError` rather than returning
divergent scores, fabricated statistics or wall-clock time as match duration.
Its legacy helper methods are not a supported rules engine. The local
`tennis.py`/`pointsv2.py` tournament scripts under `2023/` and `2024/` are also
deprecated historical artifacts, left untouched with their data/results; new
work must import the canonical engine instead of copying or invoking those engines.

### 2. Batch Simulations

To aggregate synthetic rules runs (not validated forecasts), use
[`tennis_preds/tennis.py`](tennis_preds/tennis.py):

```python
from tennis_preds.tennis import PlayerSimple, TennisMatch

player1_wins = 0
player2_wins = 0
for i in range(1000):
    player1 = PlayerSimple("Player 1", 0.68)
    player2 = PlayerSimple("Player 2", 0.65)
    tennis_match = TennisMatch(player1, player2, sets_to_win=3, player1_to_serve=True)
    tennis_match.simulate_match()
    if tennis_match.player1_sets_won > tennis_match.player2_sets_won:
        player1_wins += 1
    else:
        player2_wins += 1

print(f"Player 1 wins: {player1_wins}, Player 2 wins: {player2_wins}")
```

### 3. Web Interface

Start the web application for legacy heuristic win simulations:

```bash
uv run --locked --extra web python -m web_interface.server
```

Then open your browser to `http://localhost:5000` for:
- Unvalidated heuristic win simulations
- Team optimization tools
- Tournament bracket visualization

The web match wrapper retains a synthetic p/n-factor-to-serve heuristic only for
win counts/frequencies, labeled `win_estimate.validated: false`; these are not
calibrated model probabilities. It exports no point/set totals or averages and
returns `detailed_forecast.status: unavailable` with the missing-mapping reason.
The UI displays detailed forecasts as unavailable rather than inventing averages.

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
chronological backtesting harness is implemented; no accuracy threshold is
claimed by the current CI.

---

## Documentation

- [2026 pool rules](docs/pool/2026-rules.md): published rules and provisional decisions.
- [Pool modules](docs/pool/modules.md): scoring, ledger, substitutes, payouts, workbook preview.
- [Canonical contracts and models](docs/architecture.md): records, simulation, identities, information observations.
- [Dependency management](docs/DEPENDENCIES.md): installs, lock updates, audits.
- [Historical source policy](docs/data/HISTORICAL_SOURCE_POLICY.md): data access and permissions.
