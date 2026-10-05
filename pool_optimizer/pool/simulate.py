"""Monte Carlo tournament simulator.

Simulates the bracket match by match, scoring each player with the exact
pool rules (ATP points + cumulative path-dependent upset bonuses).
Returns a points matrix players x sims for the optimizer.
"""

from __future__ import annotations

import numpy as np

from .parsers import Draw, DrawEntry
from .scoring import TABLES, band, bonus_points, effective_rank
from .strength import StrengthModel, win_prob


def simulate(
    draw_entries: list[DrawEntry],
    model: StrengthModel,
    kind: str,               # 'gs' | 'm7' | 'm6'
    n_sims: int = 20000,
    seed: int = 7,
    upset_factor: float = 1.0,   # <1 compresses Elo gaps (variance events)
    injury_risk: dict[str, float] | None = None,  # extra per-match breakdown p
    base_hazard: float = 0.01,   # everyone can retire/collapse mid-event
    h2h: list[tuple[str, str, float]] | None = None,  # (a, b, elo tilt for a)
    return_champs: bool = False,
) -> tuple[list[str], np.ndarray]:
    """Returns (player_names, points[player_idx, sim]).

    draw_entries must be a literal single-elimination slot list (BYEs
    included) whose length is a power of two. BYEs never win.
    """
    # 6-round events (Monte Carlo, Paris) pad the sheet's bottom half with
    # BYEs — trim so round numbering matches the real bracket
    while len(draw_entries) > 2 and all(
            e.is_bye for e in draw_entries[len(draw_entries) // 2:]):
        draw_entries = draw_entries[: len(draw_entries) // 2]

    n_slots = len(draw_entries)
    assert n_slots & (n_slots - 1) == 0, "slot count must be a power of two"
    n_rounds = n_slots.bit_length() - 1
    is_gs = kind == "gs"
    round_table, champion_pts = TABLES[kind]

    players = [e for e in draw_entries if not e.is_bye]
    names = [e.name for e in players]
    idx_of = {id(e): i for i, e in enumerate(players)}

    # per-slot arrays (BYE = -1)
    slot_player = np.full(n_slots, -1, dtype=np.int32)
    for s, e in enumerate(draw_entries):
        if not e.is_bye:
            slot_player[s] = idx_of[id(e)]

    n = len(players)
    elo = np.array([model.elo(e.name) for e in players])
    seeds = [e.seed for e in players]
    ranks = [e.atp_rank for e in players]

    # precompute per-player band and the bonus a win over each opponent yields
    bonus_vs = np.zeros((n, n), dtype=np.int16)
    for w in range(n):
        for l in range(n):
            if w != l:
                bonus_vs[w, l] = bonus_points(
                    seeds[w], ranks[w], seeds[l], ranks[l], is_gs
                )

    bo5 = (1.15 if is_gs else 1.0) * upset_factor
    rng = np.random.default_rng(seed)

    # per-match breakdown probability: injuries strike mid-tournament, and a
    # deep run means more exposure. A breakdown loses that match outright.
    from .parsers import norm as _norm
    risk = np.full(n, base_hazard)
    if injury_risk:
        for player, p in injury_risk.items():
            for i, e in enumerate(players):
                if _norm(e.name) == _norm(player):
                    risk[i] = base_hazard + float(p)

    # head-to-head: a directional rating tilt applied only when these two
    # meet (matchup problems the ratings don't capture). Stored one-way so
    # the elo difference is adjusted exactly once.
    h2h_tilt = np.zeros((n, n), dtype=np.float32)
    if h2h:
        by_key = {_norm(e.name): i for i, e in enumerate(players)}
        for a, b, tilt in h2h:
            ia, ib = by_key.get(_norm(a)), by_key.get(_norm(b))
            if ia is not None and ib is not None:
                h2h_tilt[ia, ib] = float(tilt)

    points = np.zeros((n, n_sims), dtype=np.int16)
    # ATP points for losing in round r (1-based); champions handled separately
    lose_pts = np.array([0] + [round_table[r] for r in range(1, n_rounds + 1)],
                        dtype=np.int16)

    # simulate all sims round by round, vectorized over sims
    # state: current[slot_half, sim] = player idx or -1 (BYE)
    current = np.tile(slot_player[:, None], (1, n_sims))  # (n_slots, n_sims)
    bonus_acc = np.zeros((n, n_sims), dtype=np.int16)

    for rnd in range(1, n_rounds + 1):
        a = current[0::2, :]  # (n_matches, n_sims)
        b = current[1::2, :]
        n_matches = a.shape[0]

        # win probability of a over b from Elo (vectorized via lookup)
        elo_a = np.where(a >= 0, elo[np.clip(a, 0, None)], -1e9)
        elo_b = np.where(b >= 0, elo[np.clip(b, 0, None)], -1e9)
        both = (a >= 0) & (b >= 0)
        ca, cb = np.clip(a, 0, None), np.clip(b, 0, None)
        tilt = np.where(both, h2h_tilt[ca, cb] - h2h_tilt[cb, ca], 0.0)
        diff = (elo_a - elo_b + tilt) * bo5
        p_a = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
        # byes: the real player always advances; double-bye advances -1
        p_a = np.where((a >= 0) & (b < 0), 1.0, p_a)
        p_a = np.where((a < 0) & (b >= 0), 0.0, p_a)

        # breakdowns: an injured body loses the match regardless of Elo
        risk_a = np.where(a >= 0, risk[np.clip(a, 0, None)], 0.0)
        risk_b = np.where(b >= 0, risk[np.clip(b, 0, None)], 0.0)
        broke_a = rng.random((n_matches, n_sims)) < risk_a
        broke_b = rng.random((n_matches, n_sims)) < risk_b
        p_a = np.where(broke_a & ~broke_b, 0.0, p_a)
        p_a = np.where(broke_b & ~broke_a, 1.0, p_a)
        # byes still auto-advance the real player
        p_a = np.where((a >= 0) & (b < 0), 1.0, p_a)
        p_a = np.where((a < 0) & (b >= 0), 0.0, p_a)

        r = rng.random((n_matches, n_sims))
        a_wins = r < p_a
        winners = np.where(a_wins, a, b)
        losers = np.where(a_wins, b, a)

        # losers get ATP points for the round they lost in
        real_loss = (losers >= 0) & (winners >= 0)  # bye "losses" don't count
        li, si = np.nonzero(real_loss)
        points[losers[li, si], si] = lose_pts[rnd]
        # winners accumulate upset bonuses for real wins
        bonus_acc[winners[li, si], si] += bonus_vs[winners[li, si], losers[li, si]]

        current = winners

    champs = current[0, :]
    points[champs, np.arange(n_sims)] = champion_pts
    points = points + bonus_acc
    if return_champs:
        # bonus-heavy runners-up can out-POINT the champion, so callers that
        # need title probabilities must use this, never point totals
        return names, points, champs
    return names, points
