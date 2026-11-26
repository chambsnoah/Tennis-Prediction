"""Legacy budget-format team annealing for the web interface (not 2026 decision support).

Adapted from the 2023/2024 ``predictor_annealing.py`` scripts. The web app calls
``optimize_team`` directly as a bounded job with already-validated records; this
module reads no files. A seeded ``random.Random`` makes results reproducible.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence

from web_interface.errors import ServiceError
from web_interface.legacy_data import PlayerRecord


def evaluate_combination(combination: Sequence[str], points: Mapping[str, float],
                         costs: Mapping[str, float]) -> tuple[float, float]:
    return (sum(points[p] for p in combination), sum(costs[p] for p in combination))


def perturb_solution(rng: random.Random, current: list[str], players: list[str],
                     team_size: int) -> list[str]:
    """Swap a random number (at least one) of members for outsiders; the size never changes."""
    outsiders = [p for p in players if p not in current]
    most = min(team_size, len(outsiders))
    if most <= 0:
        return current
    # Single swaps must be possible: they are the only moves for one-player teams
    # and often the only affordable ones under a tight budget.
    count = rng.randint(1, most)
    return rng.sample(current, team_size - count) + rng.sample(outsiders, count)


def simulated_annealing(
    rng: random.Random, players: list[str], points: Mapping[str, float],
    costs: Mapping[str, float], budget: float, team_size: int, cutoff: float = 1300,
) -> tuple[list[str], float]:
    # Start from the cheapest full team, which fits whenever any team does.
    current = sorted(players, key=lambda p: (costs[p], p))[:team_size]
    if len(current) < team_size or evaluate_combination(current, points, costs)[1] > budget:
        raise ServiceError("budget_too_small", 422)
    best = current[:]
    current_score, _ = evaluate_combination(current, points, costs)
    best_score = current_score
    temperature = 100.0
    for _ in range(1000):
        if temperature <= 0.1 and best_score >= cutoff:
            break
        candidate = perturb_solution(rng, current, players, team_size)
        score, cost = evaluate_combination(candidate, points, costs)
        if cost <= budget:
            if score > current_score:
                current, current_score = candidate[:], score
                if score > best_score:
                    best, best_score = candidate[:], score
            # Metropolis acceptance: worse teams are accepted with probability
            # exp(delta / T). The legacy scripts subtracted 1, which never accepted any.
            elif rng.random() < math.exp((score - current_score) / temperature):
                current, current_score = candidate[:], score
        temperature *= 0.95
    return best, best_score


def optimize_team(
    players: Sequence[PlayerRecord], points: Mapping[str, float] | None, *,
    budget: int, team_size: int, seed: int,
) -> dict[str, object]:
    """Choose ``team_size`` players under ``budget``; seed-derived points without a points file."""
    records = {p.name: p for p in players}
    if points:
        scores = {name: points[name] for name in records if name in points}
    else:
        # Higher seeds (lower numbers) get higher scores; unseeded counts as 128.
        scores = {name: float(max(1, 129 - (p.seed or 128)) * 10) for name, p in records.items()}
    if len(scores) < team_size:
        # A stale points file can leave too few players to fill the team.
        raise ServiceError("insufficient_scored_players", 422)
    costs = {name: records[name].cost for name in scores}
    best, best_score = simulated_annealing(
        random.Random(seed), sorted(scores), scores, costs, budget, team_size)
    best.sort(key=lambda name: scores[name], reverse=True)
    total_cost = sum(costs[name] for name in best)
    return {
        "team_roster": [{
            "name": name, "seed": records[name].seed, "cost": records[name].cost,
            "points": scores[name], "p_factor": records[name].p_factor,
            "n_factor": records[name].n_factor,
        } for name in best],
        "total_score": best_score,
        "total_cost": total_cost,
        "budget_used": round(total_cost / budget * 100, 1),
        "seed": seed,
    }
