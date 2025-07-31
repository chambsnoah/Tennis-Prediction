# Tennis-Prediction

A Python project for simulating and predicting tennis match outcomes using player statistics. The project supports both detailed and simplified player models, and can simulate matches for various tournaments and years.

---

## Features

- **Player Modeling:**  
  - Detailed player model with serve/return stats.
  - Simple player model with overall serve win percentage.

- **Match Simulation:**  
  - Simulates full tennis matches, including sets, games, tiebreaks, and service alternation.
  - Tracks detailed statistics: double faults, break points, tiebreaks, service/return points, and more.

- **Tournament Data:**  
  - Includes data and scripts for major tournaments (Australian Open, French Open, Wimbledon, US Open) across multiple years.

- **Extensible:**  
  - Easily add new players, tournaments, or prediction logic.

---

## Project Structure

```
.
├── 2023/
│   ├── au2023/
│   ├── rg2023/
│   ├── us2023/
│   └── wimby2023/
├── 2024/
│   ├── au2024/
│   ├── rg2024/
│   ├── us2024/
│   └── wimby2024/
├── tennis_preds/
│   └── tennis.py
├── .gitignore
└── README.md
```

- **2023/** and **2024/**: Tournament data, scripts, and results for each year.
- **tennis_preds/tennis.py**: Main simulation engine and player models.

---

## Requirements

- Python 3.7+
- No external dependencies (uses only the Python standard library).

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
