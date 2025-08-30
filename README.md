# Tennis-Prediction

A Python project for simulating and predicting tennis match outcomes using player statistics. The project supports both detailed and simplified player models, includes real-time API integration, and can simulate matches for various tournaments and years.

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

- Python 3.7+
- Core simulation: No external dependencies (uses only Python standard library)
- API features: `pip install -r tennis_api/requirements.txt`
- Web interface: `pip install -r web_interface/requirements.txt`

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
cd web_interface
python server.py
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
# Quick verification
python scripts/simple_verify.py

# Full test suite
python scripts/run_full_tests.py

# Cache system validation
python scripts/validate_cache_edge_cases.py
```
