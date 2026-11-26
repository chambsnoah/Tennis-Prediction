"""Legacy budget-format team annealing for the web interface (not 2026 decision support).

Adapted from the 2023/2024 ``predictor_annealing.py`` scripts. The web app calls
``optimize_team`` directly as a bounded job with already-validated records; this
module reads no files. A seeded ``random.Random`` makes results reproducible.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence

from web_interface.legacy_data import PlayerRecord


def evaluate_combination(combination: Sequence[str], points: Mapping[str, float],
                         costs: Mapping[str, float]) -> tuple[float, float]:
    return (sum(points[p] for p in combination), sum(costs[p] for p in combination))


def perturb_solution(rng: random.Random, current: list[str], remaining: list[str],
                     team_size: int) -> list[str]:
    count = min(team_size - 1, len(remaining))
    if count <= 0:
        return current
    for _ in range(100):
        candidate = rng.sample(remaining, count) + [rng.choice(current)]
        if len(set(candidate)) == len(candidate):
            return candidate
    return current


def simulated_annealing(
    rng: random.Random, players: list[str], points: Mapping[str, float],
    costs: Mapping[str, float], budget: float, team_size: int, cutoff: float = 1300,
) -> tuple[list[str], float]:
    current = rng.sample(players, min(team_size, len(players)))
    remaining = [p for p in players if p not in current]
    best = current[:]
    current_score, _ = evaluate_combination(current, points, costs)
    best_score = current_score
    temperature = 100.0
    for _ in range(1000):
        if temperature <= 0.1 and best_score >= cutoff:
            break
        candidate = perturb_solution(rng, current, remaining, team_size)
        score, cost = evaluate_combination(candidate, points, costs)
        if cost <= budget:
            if score > current_score:
                current, current_score = candidate[:], score
                if score > best_score:
                    best, best_score = candidate[:], score
            elif rng.random() < math.exp((score - current_score) / temperature) - 1:
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
