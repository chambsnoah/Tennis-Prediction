"""2026 pool point arithmetic, not rule approval or source-workbook parity.

Use tennis_pool.results.score_tournament for gated, evidence-bound scoring.
These pure helpers also serve the legacy optimizer's existing callers.
"""

from __future__ import annotations

from dataclasses import dataclass

# Terminal loss-round points (1-based); champions have a separate award.
GS_ROUND_POINTS = {1: 1, 2: 7, 3: 15, 4: 30, 5: 50, 6: 90, 7: 140}
GS_CHAMPION = 200
M7_ROUND_POINTS = {1: 1, 2: 4, 3: 7, 4: 15, 5: 25, 6: 45, 7: 70}
M7_CHAMPION = 100
M6_ROUND_POINTS = {1: 1, 2: 7, 3: 15, 4: 25, 5: 45, 6: 70}
M6_CHAMPION = 100


TABLES = {
    "gs": (GS_ROUND_POINTS, GS_CHAMPION),
    "m7": (M7_ROUND_POINTS, M7_CHAMPION),
    "m6": (M6_ROUND_POINTS, M6_CHAMPION),
}


def atp_points(lost_in_round: int | None, kind: str) -> int:
    """Points for a player who lost in `lost_in_round` (None = champion).
    kind: 'gs' (Slams), 'm7' (7-round Masters), 'm6' (Monte Carlo, Paris)."""
    if kind not in TABLES:
        raise ValueError("Unknown scoring kind")
    table, champ = TABLES[kind]
    if lost_in_round is None:
        return champ
    if type(lost_in_round) is not int or lost_in_round not in table:
        raise ValueError("Invalid loss round")
    return table[lost_in_round]


def band(seed: int | None) -> int:
    """0 = seed 1-4, 1 = seed 5-8, 2 = seed 9-16, 3 = other (17-32 or unseeded)."""
    if seed is None:
        return 3
    if type(seed) is not int or not 1 <= seed <= 32:
        raise ValueError("Invalid event seed")
    if seed <= 4:
        return 0
    if seed <= 8:
        return 1
    if seed <= 16:
        return 2
    return 3


# Grand Slam bonuses, with same-band ordering checked separately.
_GS_BONUS = (
    (20, 0, 0, 0),     # 1-4 beats ...
    (30, 10, 0, 0),    # 5-8 beats ...
    (40, 20, 10, 0),   # 9-16 beats ...
    (50, 30, 20, 10),  # other beats ...
)


def effective_rank(seed: int | None, atp_rank: int | None) -> int:
    """Ordering used for 'better player' comparisons. Seeds order by seed
    number; non-seeds by ATP world rank (rules 12 footnote)."""
    band(seed)
    if seed is not None:
        return seed
    if type(atp_rank) is not int or atp_rank < 1:
        raise ValueError("Missing or invalid first-day ATP ranking")
    return atp_rank + 32


def bonus_points(
    w_seed: int | None, w_rank: int | None,
    l_seed: int | None, l_rank: int | None,
    is_gs: bool,
) -> int:
    """Bonus for one won match. Cumulative across a player's wins."""
    wb, lb = band(w_seed), band(l_seed)
    if type(is_gs) is not bool:
        raise ValueError("Scoring category must be explicit")
    for rank in (w_rank, l_rank):
        if rank is not None and (type(rank) is not int or rank < 1):
            raise ValueError("Invalid first-day ATP ranking")
    if wb < lb:
        return 0  # beat a lower-band player: never a bonus
    if wb == lb:
        # same band: bonus only when the loser is the better player
        if w_seed is not None and l_seed is None:
            return 0
        if w_seed is None and l_seed is not None:
            return _GS_BONUS[wb][lb] if is_gs else _GS_BONUS[wb][lb] // 2
        if effective_rank(l_seed, l_rank) >= effective_rank(w_seed, w_rank):
            return 0
    base = _GS_BONUS[wb][lb]
    return base if is_gs else base // 2


@dataclass(frozen=True)
class PlayerResult:
    atp: int
    bonus: int

    @property
    def total(self) -> int:
        return self.atp + self.bonus


def score_player(
    wins: list[tuple[int | None, int | None]],  # (loser_seed, loser_rank) per played win
    lost_in_round: int | None,           # None if champion
    kind: str,                           # 'gs' | 'm7' | 'm6'
    seed: int | None,
    rank: int | None,
) -> PlayerResult:
    """Pure arithmetic for already established played wins and terminal result."""
    band(seed)
    if rank is not None and (type(rank) is not int or rank < 1):
        raise ValueError("Invalid first-day ATP ranking")
    atp = atp_points(lost_in_round, kind)
    is_gs = kind == "gs"
    bon = sum(bonus_points(seed, rank, ls, lr, is_gs) for ls, lr in wins)
    return PlayerResult(atp, bon)
