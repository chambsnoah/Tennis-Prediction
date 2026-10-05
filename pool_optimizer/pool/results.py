"""Reconstruct actual tournament outcomes from a Draw sheet and score every
player with the scoring engine. Used for validation and for Elo updates."""

from __future__ import annotations

from dataclasses import dataclass

from .parsers import Draw, DrawEntry, norm
from .scoring import PlayerResult, score_player


@dataclass
class PlayerOutcome:
    entry: DrawEntry
    wins: list[tuple[int | None, int]]   # (loser_seed, loser_rank) per real win
    beaten_by: str | None                # normalized name, None if champion
    lost_in_round: int | None            # None if champion
    result: PlayerResult


def match_log(draw: Draw) -> list[tuple[int, str, str]]:
    """All real matches as (round, winner_norm, loser_norm), deduplicated."""
    by_name = {norm(e.name): e for e in draw.entries if not e.is_bye}
    seen, log = set(), []
    for (rnd, pair), winner in draw.results.items():
        names = set(pair)
        if "bye" in names or winner not in by_name:
            continue
        loser = next(iter(names - {winner}), None)
        if loser is None or loser not in by_name:
            continue
        key = (rnd, winner, loser)
        if key not in seen:
            seen.add(key)
            log.append(key)
    return sorted(log)


def score_tournament(draw: Draw, kind: str) -> dict[str, PlayerOutcome]:
    """Score every (non-bye) entrant from actual results."""
    by_name = {norm(e.name): e for e in draw.entries if not e.is_bye}
    n_rounds = draw.n_rounds
    wins: dict[str, list] = {n: [] for n in by_name}
    lost_in: dict[str, tuple[int, str]] = {}

    for rnd, winner, loser in match_log(draw):
        le = by_name[loser]
        wins[winner].append((le.seed, le.atp_rank))
        prev = lost_in.get(loser)
        if prev is None or rnd > prev[0]:
            lost_in[loser] = (rnd, winner)

    out: dict[str, PlayerOutcome] = {}
    for name, e in by_name.items():
        lr = lost_in.get(name)
        lost_round = lr[0] if lr else None
        # players eliminated without a recorded loss (e.g. walkover rows):
        # they exited the round after their last completed match
        if lost_round is None and len(wins[name]) + _byes(draw, e) < n_rounds:
            lost_round = len(wins[name]) + _byes(draw, e) + 1
        res = score_player(wins[name], lost_round, kind, e.seed, e.atp_rank)
        out[name] = PlayerOutcome(e, wins[name], lr[1] if lr else None, lost_round, res)
    return out


def _byes(draw: Draw, e: DrawEntry) -> int:
    """Number of byes on this entrant's actual path (0 or 1 in these draws)."""
    n = 0
    for (rnd, pair), winner in draw.results.items():
        if norm(e.name) in pair and "bye" in pair and winner == norm(e.name):
            n += 1
    return n
