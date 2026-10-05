"""Player strength model.

Elo anchored on the current ATP ranking, adjusted by 2026 season results
parsed from the tournament workbooks (recent + hard-court matches weighted
up), with optional manual overrides from data/form_overrides.json
(injuries, betting-odds calibration, hot streaks).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .parsers import load_draw, load_rankings, norm
from .results import match_log

# Multi-year (2015-2025) champion history sorts the 13 events into classes:
# chalk events (champion virtually always a top-4/top-8 player: the Slams,
# Rome, Madrid) vs variance events (champion outside the top 8 in ~30-40% of
# editions: Miami — Isner'18/Hurkacz'21/Menšík'25; Canada — Carreño Busta'22/
# Popyrin'24; Cincinnati — Cilic'16/Dimitrov'17/Coric'22; Shanghai —
# Hurkacz'23/Vacherot'25; Paris — Sock'17/Khachanov'18/Rune'22).
# In variance events the Elo gap between favorites and the field plays
# compressed: best-of-3, fast conditions, tune-up/fatigue scheduling.
UPSET_FACTOR = {
    "chalk": 1.0,      # Indian Wells, Monte Carlo, Madrid, Rome
    "variance": 0.80,  # Miami, Montréal, Cincinnati, Shanghai, Paris
}
EVENT_CLASS = {
    "Australie": "chalk", "Indian Wells": "chalk", "Miami": "variance",
    "Monte Carlo": "chalk", "Madrid": "chalk", "Rome": "chalk",
    "Roland-Garros": "chalk", "Wimbledon": "chalk", "Montréal": "variance",
    "Cincinnati": "variance", "US Open": "chalk", "Shanghai": "variance",
    "Paris": "variance",
}

# tournament order + surface ('hard' matters for the US Open)
SEASON = [
    ("Australie", "01 - Australie.xlsm", "hard"),
    ("Indian Wells", "02 - Indian Wells.xlsm", "hard"),
    ("Miami", "03 - Miami.xlsm", "hard"),
    ("Monte Carlo", "04 - Monte Carlo.xlsm", "clay"),
    ("Madrid", "05 - Madrid.xlsm", "clay"),
    ("Rome", "06 - Rome.xlsm", "clay"),
    ("Roland-Garros", "07 - Roland-Garros.xlsm", "clay"),
    ("Wimbledon", "08 - Wimbledon.xlsm", "grass"),
    ("Montréal", "09 - Montréal.xlsm", "hard"),
    ("Cincinnati", "10 - Cincinnati.xlsm", "hard"),
    ("US Open", "11 - US Open.xlsm", "hard"),
]

ELO_SCALE = 400.0
K = 24.0


def rank_elo(rank: int) -> float:
    """Anchor Elo from ATP rank (log-linear)."""
    return 1800.0 - 110.0 * math.log(max(rank, 1))


def win_prob(elo_a: float, elo_b: float, best_of_five: bool = False) -> float:
    diff = elo_a - elo_b
    if best_of_five:
        diff *= 1.15  # longer format favours the better player
    return 1.0 / (1.0 + 10.0 ** (-diff / ELO_SCALE))


class StrengthModel:
    def __init__(self, ratings: dict[str, float], rankings: dict[str, int]):
        self.ratings = ratings
        self.rankings = rankings

    def elo(self, name: str) -> float:
        key = norm(name)
        if key in self.ratings:
            return self.ratings[key]
        rank = self.rankings.get(key, 200)
        return rank_elo(rank)

    def p(self, a: str, b: str, best_of_five: bool = False) -> float:
        return win_prob(self.elo(a), self.elo(b), best_of_five)


def build_model(
    data_dir: str | Path,
    target_surface: str = "hard",
    overrides_file: str | None = "form_overrides.json",
    upto: str | None = None,
    anchor_ranks: dict[str, int] | None = None,
) -> StrengthModel:
    """upto: build the model as of the eve of this tournament — anchor on its
    own Rankings sheet, use only earlier events for form (backtesting)."""
    data_dir = Path(data_dir)
    season = SEASON
    anchor = None
    if upto is not None:
        idx = next(i for i, s in enumerate(season) if s[0] == upto)
        anchor = data_dir / season[idx][1]  # start-of-event official ranks
        season = season[:idx]

    if anchor is None:
        for _, fname, _ in reversed(season):
            if (data_dir / fname).exists():
                anchor = data_dir / fname
                break
    if anchor is None:
        raise FileNotFoundError("no tournament workbook found in data/")
    rankings = load_rankings(str(anchor))
    # live runs: the latest workbook's Rankings sheet is the start of the
    # PREVIOUS event (5+ weeks stale by Shanghai). The anchor is meant to be
    # start-of-THIS-event rank, so the current draw's ranks take precedence.
    if anchor_ranks and upto is None:
        for name, rank in anchor_ranks.items():
            rankings[norm(name)] = int(rank)
    ratings = {name: rank_elo(rank) for name, rank in rankings.items()}

    # season form: Elo updates from actual matches, weighted by recency and
    # surface similarity. The anchor already encodes overall skill, so form
    # updates deliberately use a modest K.
    n_events = len(season)
    for age_idx, (_, fname, surface) in enumerate(season):
        path = data_dir / fname
        if not path.exists():
            continue
        recency = 0.5 ** ((n_events - 1 - age_idx) / 4.0)
        surf_w = 1.0 if surface == target_surface else 0.5
        weight = K * recency * surf_w
        draw = load_draw(str(path))
        ranks_then = load_rankings(str(path))
        for _, winner, loser in match_log(draw):
            for name in (winner, loser):
                if name not in ratings:
                    ratings[name] = rank_elo(ranks_then.get(name, 200))
            pw = win_prob(ratings[winner], ratings[loser])
            ratings[winner] += weight * (1.0 - pw)
            ratings[loser] -= weight * (1.0 - pw)

    # manual overrides: {"player name": elo_delta} and absolute entries
    # {"player name=": absolute_elo}; withdrawals handled by the caller.
    # Overrides describe TODAY's news, so they never apply to backtests.
    if upto is not None:
        overrides_file = None
    if overrides_file:
        opath = data_dir / overrides_file
        if opath.exists():
            for player, val in json.loads(opath.read_text()).items():
                if player.startswith("_"):
                    continue  # metadata keys (e.g. _withdrawals)
                if player.endswith("="):
                    ratings[norm(player[:-1])] = float(val)
                else:
                    ratings[norm(player)] = ratings.get(
                        norm(player), rank_elo(rankings.get(norm(player), 200))
                    ) + float(val)

    return StrengthModel(ratings, rankings)


def load_withdrawals(data_dir: str | Path, overrides_file: str = "form_overrides.json") -> set[str]:
    opath = Path(data_dir) / overrides_file
    if not opath.exists():
        return set()
    data = json.loads(opath.read_text())
    return {norm(p) for p in data.get("_withdrawals", [])}


def load_h2h(data_dir: str | Path, overrides_file: str = "form_overrides.json"):
    """Directional head-to-head tilts: [[a, b, elo_tilt_for_a], ...].
    Applied only in matches between that exact pair."""
    opath = Path(data_dir) / overrides_file
    if not opath.exists():
        return []
    data = json.loads(opath.read_text())
    return [(a, b, float(t)) for a, b, t in data.get("_h2h", [])]


def load_injury_risk(data_dir: str | Path, overrides_file: str = "form_overrides.json") -> dict[str, float]:
    """Per-match breakdown-probability adders from the overrides file.
    Refresh from injury news before each tournament."""
    opath = Path(data_dir) / overrides_file
    if not opath.exists():
        return {}
    data = json.loads(opath.read_text())
    return {k: float(v) for k, v in data.get("_injury_risk", {}).items()}


def load_ownership_floor(data_dir: str | Path, overrides_file: str = "form_overrides.json") -> dict[str, float]:
    """PLAYBOOK §6 mandatory floor: {"player": min projected field share}.
    The ownership model is backward-looking (it inverted Zverev/Alcaraz at
    the 2026 US Open); hand-audited floors for in-form stars go here.
    Today's knowledge only — never applied to backtests."""
    opath = Path(data_dir) / overrides_file
    if not opath.exists():
        return {}
    data = json.loads(opath.read_text())
    return {k: float(v) for k, v in data.get("_ownership_floor", {}).items()}
