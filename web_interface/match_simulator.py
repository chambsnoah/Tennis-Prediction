"""Unvalidated synthetic win heuristic for the legacy web interface.

Detailed forecasts are unavailable until a model-to-serve mapping is validated.
The web app calls ``simulate_matches`` directly as a bounded job; this module
reads no files and takes no paths.
"""

from __future__ import annotations

import random
from typing import Any

from tennis_preds.tennis import Player, TennisMatch

SURFACE_ADJUSTMENTS = {
    "grass": {"first_serve": 0.02, "first_win": 0.05, "second_win": 0.02},
    "clay": {"first_serve": -0.01, "first_win": -0.02, "second_win": 0.01},
    "hard": {"first_serve": 0.0, "first_win": 0.0, "second_win": 0.0},
}


def create_player(name: str, p_factor: float, n_factor: float, surface: str = "grass") -> Any:
    """Create synthetic heuristic inputs, not measured or model-derived stats."""
    adj = SURFACE_ADJUSTMENTS[surface]
    first_serve = 0.65 + adj["first_serve"] + p_factor * 2 - n_factor * 2
    first_win = 0.70 + adj["first_win"] + p_factor * 5 - n_factor * 3
    second_win = 0.55 + adj["second_win"] + p_factor * 3 - n_factor * 2
    return Player(name, max(0.4, min(0.8, first_serve)), 0.90,
                  max(0.5, min(0.85, first_win)), max(0.35, min(0.70, second_win)))


def simulate_matches(
    player1: tuple[str, float, float], player2: tuple[str, float, float], *,
    sets_to_win: int, simulations: int, surface: str, seed: int,
) -> dict[str, object]:
    """Return heuristic win counts only, never detailed match forecasts.

    Players are ``(name, p_factor, n_factor)``. The seed fully determines the
    result: one stream draws who serves first and every point.
    """
    if type(simulations) is not int or simulations < 1:
        raise ValueError("simulations must be a positive integer")
    if surface not in SURFACE_ADJUSTMENTS:
        raise ValueError("Unknown surface")
    rng = random.Random(seed)
    first = create_player(*player1, surface=surface)
    second = create_player(*player2, surface=surface)
    wins = 0
    for _ in range(simulations):
        match = TennisMatch(first, second, sets_to_win, rng.random() < 0.5, rng=rng)
        match.simulate_match(verbose=False)
        wins += match.get_match_winner() is first
    # These frequencies are conditional on synthetic inputs, not calibrated odds.
    return {
        "player1_wins": wins,
        "player2_wins": simulations - wins,
        "player1_win_percentage": round(wins / simulations * 100, 1),
        "player2_win_percentage": round((simulations - wins) / simulations * 100, 1),
        "seed": seed,
        "win_estimate": {
            "method": "synthetic_serve_heuristic",
            "validated": False,
            "description": "Unvalidated heuristic using synthetic serve inputs; "
                           "not calibrated model probabilities.",
        },
        "detailed_forecast": {
            "status": "unavailable",
            "reason": "No validated model-to-serve mapping for score, statistics "
                      "or duration forecasts.",
        },
    }
