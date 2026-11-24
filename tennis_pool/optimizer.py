"""Joint five-primary, five-substitute search on shared simulated scenarios.

Every candidate policy (five primaries, each with an optional same-band
substitute) is scored per scenario: a primary who withdrew before playing hands
the slot to its substitute's result in the same simulated tournament, so draw
correlations and walkover effects are kept instead of summing marginal player
values. The search enumerates every bank-legal primary roster from a pruned
per-band pool, screens them on a scenario prefix with greedy substitutes, then
improves the substitutes of the best rosters on all scenarios, one slot at a
time and then by re-choosing same-band slot pairs together. Small instances are also solved exhaustively over every eligible
player, and the measured in-sample gap is reported. Every returned policy is
re-checked with ``substitutions.validate_roster``.

Results are in-sample estimates conditional on the probability provider, the
explicit withdrawal assumptions and, for rank-based objectives, the ownership
model. They are not promises about realized outcomes. The single-event
objectives ignore the season value of saving band quota or player uses.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
from itertools import combinations, product
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from tennis_api.models.canonical import (
    Contract, Draw, EntryKind, Match, MatchProbabilityProvider, PlayerId, PlayerMatchStats,
    RankingSnapshot,
)
from tennis_api.simulation.tournament import OutcomeKind, simulate_tournament
from tennis_pool.ledger import _MASTERS, _SEEDED, _SLAMS, Band, EntryState, Pair, Selection
from tennis_pool.payouts import PayoutConfig, payout_config
from tennis_pool.rules import DEPENDENCIES, require_resolved
from tennis_pool.scoring import TABLES, bonus_points
from tennis_pool.substitutions import _FULL_BANKS, seed_band, validate_roster


_REGISTER_VERSION = "2026-provisional-2"
# Digest of the recommendation decision texts this search implements.
_DECISION_DIGEST = "d6783d0a6f2d744276dfab15a67647ddceed95de7df2b40594478228e4ad34af"
_SLOTS = 5
_USE_CAP = 5
_TOP3_MATERIALITY = 0.015
_TIE_Z = 2.0
_BANDS = (Band.TOP4, Band.TOP8, Band.TOP16, Band.TOP32, Band.UNSEEDED)
_SIM_WITHDRAWALS = (
    "Independent pre-match withdrawal draws per listed player and scenario; each "
    "distinct withdrawal pattern is re-simulated with the player removed, so the "
    "opponent advances by walkover (no lucky loser) and a withdrawn primary hands "
    "its slot to its substitute. Unlisted players are assumed to start; "
    "retirements after play are left to the provider."
)
_SEASON_EFFECTS = (
    "Single-event objective: the later value of unspent band quota or player uses, "
    "and quota consumed by activated substitutes, are not optimized here."
)
_ROSTER_GATE = "Provisional substitution rules require an explicit boolean opt-in"


class Objective(str, Enum):
    EXPECTED_POINTS = "expected_points"
    P_TOP3 = "p_top3"
    EXPECTED_PAYOUT = "expected_payout"
    ROBUST = "robust"


_RIVAL_OBJECTIVES = (Objective.P_TOP3, Objective.EXPECTED_PAYOUT)


def _gate(
    allow_provisional: bool, register_path: str | Path | None,
) -> tuple[str, tuple[tuple[str, str, str], ...]]:
    if type(allow_provisional) is not bool:
        raise ValueError("Provisional recommendation rules require an explicit boolean opt-in")
    register = require_resolved(
        "recommendation", register_path, allow_provisional=allow_provisional,
    )
    keys = DEPENDENCIES["recommendation"]
    digest = hashlib.sha256(json.dumps(
        {key: register["decisions"][key]["decision"] for key in keys}, sort_keys=True,
    ).encode()).hexdigest()
    if register["register_version"] != _REGISTER_VERSION or digest != _DECISION_DIGEST:
        raise ValueError("Unsupported recommendation rule version; implementation review required")
    return register["register_version"], tuple(
        (key, register["decisions"][key]["status"], register["decisions"][key]["decision"])
        for key in keys
    )


@dataclass(frozen=True, kw_only=True)
class ScenarioAssumptions(Contract):
    """Reproducibility record for a scenario set."""

    source: str
    simulations: int
    seed: int | None
    kind: str | None
    draw_digest: str | None
    withdrawal_model: str
    withdrawal_probabilities: tuple[tuple[PlayerId, float], ...]
    withdrawal_patterns: int


def _owned_int64(array: NDArray[np.integer[Any]]) -> NDArray[np.int64]:
    """A private int64 copy, refusing values that would wrap on conversion."""
    limit = np.iinfo(np.int64)
    if array.size and (int(array.max()) > limit.max or int(array.min()) < limit.min):
        raise ValueError("Integer values must fit in signed 64 bits")
    return np.array(array, dtype=np.int64, copy=True)


@dataclass(frozen=True, eq=False)
class ScenarioSet:
    """Pool points per player (rows) and shared scenario (columns).

    ``points`` is what the player scores in that scenario and is zero when
    ``withdrawn`` marks a pre-match withdrawal. Columns are exchangeable draws,
    so any prefix is an unbiased subsample. The arrays are private read-only
    copies; ``digest`` identifies the exact ordered data for rival fields.
    """

    player_ids: tuple[PlayerId, ...]
    seeds: tuple[int | None, ...]
    points: NDArray[np.int64]
    withdrawn: NDArray[np.bool_]
    assumptions: ScenarioAssumptions
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        count = len(self.player_ids)
        if len(set(self.player_ids)) != count or len(self.seeds) != count:
            raise ValueError("Scenario players must be distinct and carry one seed each")
        for name, array, dtype in (("points", self.points, np.integer),
                                   ("withdrawn", self.withdrawn, np.bool_)):
            if (not isinstance(array, np.ndarray) or array.ndim != 2
                    or array.shape[0] != count or not np.issubdtype(array.dtype, dtype)):
                raise ValueError("Scenario {} must be a players x scenarios array".format(name))
        object.__setattr__(self, "points", _owned_int64(self.points))
        object.__setattr__(self, "withdrawn", np.array(self.withdrawn, dtype=np.bool_, copy=True))
        if self.points.shape != self.withdrawn.shape or self.points.shape[1] < 1:
            raise ValueError("Scenario arrays need matching shapes and at least one scenario")
        if self.points.shape[1] != self.assumptions.simulations:
            raise ValueError("Scenario count does not match its assumptions")
        if np.any(self.points < 0) or np.any(self.points[self.withdrawn] != 0):
            raise ValueError("Points must be non-negative and zero after pre-match withdrawal")
        for array in (self.points, self.withdrawn):
            array.flags.writeable = False
        content = hashlib.sha256(json.dumps(
            [list(self.player_ids), list(self.seeds), list(self.points.shape)]).encode())
        content.update(np.ascontiguousarray(self.points).tobytes())
        content.update(np.ascontiguousarray(self.withdrawn).tobytes())
        object.__setattr__(self, "digest", content.hexdigest())

    @property
    def simulations(self) -> int:
        return int(self.points.shape[1])


def _share(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and 0 <= value <= 1)


# Rounds, best-of, entrants and seed limit, as score_tournament requires.
_FORMATS = {"gs": (7, 5, 128, 32), "m7": (7, 3, 96, 32), "m6": (6, 3, 56, 16)}


def _draw_digest(draw: Draw) -> str:
    return hashlib.sha256(json.dumps(draw.to_dict(), sort_keys=True).encode()).hexdigest()


def _check_format(draw: Draw, kind: str) -> None:
    if kind not in _FORMATS:
        raise ValueError("Unsupported pool scoring kind")
    rounds, best_of, field_size, seed_limit = _FORMATS[kind]
    entrants = [s for s in draw.slots if s.kind is not EntryKind.BYE]
    if (draw.event.round_count != rounds or draw.event.best_of != best_of
            or len(entrants) != field_size
            or any(s.seed is not None and s.seed > seed_limit for s in entrants)):
        raise ValueError("Draw format does not match the {} scoring format".format(kind))


def _first_day_ranks(draw: Draw, rankings: tuple[RankingSnapshot, ...]) -> dict[PlayerId, int]:
    entrants = {slot.player_id for slot in draw.slots if slot.player_id is not None}
    ranks: dict[PlayerId, int] = {}
    for snapshot in rankings:
        if (snapshot.player_id not in entrants or snapshot.player_id in ranks
                or snapshot.tour is not draw.event.tour
                or snapshot.ranking_date > draw.event.start_date
                or snapshot.provenance.available_at.date() > draw.event.start_date):
            raise ValueError("Invalid or post-start first-day ranking evidence")
        if snapshot.rank is not None:
            ranks[snapshot.player_id] = snapshot.rank
    return ranks


def _pool_points(
    simulation: Any, draw: Draw, kind: str, ranks: Mapping[PlayerId, int],
) -> NDArray[np.int64]:
    """Terminal round points plus played-win bonuses for every simulated run."""
    table, champion = TABLES[kind]
    rounds = draw.event.round_count
    lookup = np.zeros(rounds + 2, dtype=np.int64)
    for number in range(1, rounds + 1):
        lookup[number] = table[number]
    lookup[rounds + 1] = champion
    points = lookup[np.asarray(simulation.round_reach)]
    player_ids: tuple[PlayerId, ...] = simulation.player_ids
    seeds = {slot.player_id: slot.seed for slot in draw.slots if slot.player_id is not None}
    cache: dict[tuple[int, int], int] = {}
    for outcome in simulation.rounds:
        kinds = np.asarray(outcome.kinds)
        played = (kinds == OutcomeKind.DECIDED) | (kinds == OutcomeKind.RETIRED)
        if not np.any(played):
            continue
        winners = np.asarray(outcome.winners)
        losers = np.where(winners == outcome.player1, outcome.player2, outcome.player1)
        _, runs = np.nonzero(played)
        won, lost = winners[played], losers[played]
        bonus = np.empty(len(won), dtype=np.int64)
        for position, key in enumerate(zip(won.tolist(), lost.tolist())):
            if key not in cache:
                winner, loser = player_ids[key[0]], player_ids[key[1]]
                cache[key] = bonus_points(seeds[winner], ranks.get(winner),
                                          seeds[loser], ranks.get(loser), kind == "gs")
            bonus[position] = cache[key]
        np.add.at(points, (won, runs), bonus)
    return points


def build_scenarios(
    draw: Draw,
    provider: MatchProbabilityProvider,
    *,
    kind: str,
    cutoff: datetime,
    simulations: int,
    seed: int,
    withdrawal_probabilities: Mapping[PlayerId, float] | None = None,
    rankings: tuple[RankingSnapshot, ...] = (),
    history: tuple[Match, ...] = (),
    statistics: tuple[PlayerMatchStats, ...] = (),
    max_withdrawal_patterns: int = 512,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> ScenarioSet:
    """Simulate shared pool-point scenarios, re-simulating each withdrawal pattern.

    The seed fully determines the scenarios for fixed inputs. A provider that
    already prices availability risk cannot be combined with positive explicit
    withdrawal probabilities, in any withdrawal pattern.
    """
    _gate(allow_provisional, register_path)
    _check_format(draw, kind)
    if type(seed) is not int or seed < 0:
        raise ValueError("Scenario seed must be a non-negative integer")
    if type(simulations) is not int or simulations < 1:
        raise ValueError("simulations must be a positive integer")
    ranks = _first_day_ranks(draw, rankings)
    player_ids = tuple(s.player_id for s in draw.slots if s.player_id is not None)
    index = {player: i for i, player in enumerate(player_ids)}
    risks = dict(withdrawal_probabilities or {})
    for player, probability in risks.items():
        if player not in index or not _share(probability):
            raise ValueError("Withdrawal probabilities need draw players and values in [0, 1]")
    listed = sorted(risks)
    explicit = any(risks[p] > 0 for p in listed)
    root = np.random.SeedSequence(seed)
    withdrawal_rng, = (np.random.default_rng(child) for child in root.spawn(1))
    draws = withdrawal_rng.random((len(listed), simulations)) < np.array(
        [float(risks[p]) for p in listed], dtype=np.float64,
    )[:, None]
    if listed:
        patterns, found = np.unique(draws.T, axis=0, return_inverse=True)
        inverse = np.asarray(found).reshape(-1)
    else:
        patterns = np.zeros((1, 0), dtype=np.bool_)
        inverse = np.zeros(simulations, dtype=np.int64)
    if len(patterns) > max_withdrawal_patterns:
        raise ValueError("{} withdrawal patterns exceed the limit of {}; list fewer at-risk "
                         "players".format(len(patterns), max_withdrawal_patterns))
    points = np.zeros((len(player_ids), simulations), dtype=np.int64)
    withdrawn = np.zeros((len(player_ids), simulations), dtype=np.bool_)
    for number, child in enumerate(root.spawn(len(patterns))):
        runs = np.nonzero(inverse == number)[0]
        out = frozenset(listed[i] for i in np.nonzero(patterns[number])[0])
        result = simulate_tournament(
            draw, provider, cutoff=cutoff, simulations=len(runs),
            rng=np.random.default_rng(child), withdrawn=out, rankings=rankings,
            history=history, statistics=statistics,
        )
        if tuple(result.player_ids) != player_ids:
            raise ValueError("Simulation player order changed")
        if explicit and any(p.includes_availability_risk for p in result.predictions):
            raise ValueError("Explicit withdrawal probabilities would double count provider "
                             "availability risk")
        points[:, runs] = _pool_points(result, draw, kind, ranks)
        for player in out:
            withdrawn[index[player], runs] = True
    digest = _draw_digest(draw)
    seeds = {s.player_id: s.seed for s in draw.slots if s.player_id is not None}
    return ScenarioSet(
        player_ids=player_ids, seeds=tuple(seeds[p] for p in player_ids),
        points=points, withdrawn=withdrawn,
        assumptions=ScenarioAssumptions(
            source="tennis_api.simulation.tournament:neutral-bracket-1", simulations=simulations,
            seed=seed, kind=kind, draw_digest=digest, withdrawal_model=_SIM_WITHDRAWALS,
            withdrawal_probabilities=tuple((p, float(risks[p])) for p in listed),
            withdrawal_patterns=int(len(patterns)),
        ),
    )


@dataclass(frozen=True, kw_only=True)
class RivalAssumptions(Contract):
    source: str
    rivals: int
    seed: int | None
    model: str
    ownership: tuple[tuple[PlayerId, float], ...]
    scenario_digest: str


@dataclass(frozen=True, eq=False)
class RivalField:
    """Rival entry totals (rows) on the scenario columns named by ``scenario_digest``.

    Callers supplying their own scores bind them with ``ScenarioSet.digest``.
    """

    scores: NDArray[np.int64]
    assumptions: RivalAssumptions

    def __post_init__(self) -> None:
        if (not isinstance(self.scores, np.ndarray) or self.scores.ndim != 2
                or not np.issubdtype(self.scores.dtype, np.integer)
                or self.scores.shape[0] != self.assumptions.rivals
                or self.assumptions.rivals < 1 or np.any(self.scores < 0)):
            raise ValueError("Rival scores must be a non-negative integer rivals x scenarios array")
        object.__setattr__(self, "scores", _owned_int64(self.scores))
        self.scores.flags.writeable = False


_OWNERSHIP_MODEL = (
    "Each rival, independently per scenario, takes five distinct primaries by "
    "weighted sampling without replacement (Gumbel top-k) in proportion to "
    "projected ownership, so inclusion rates approximate rather than equal "
    "ownership. Rival quotas, pick correlations and substitutes are not modelled: "
    "a withdrawn rival primary scores zero."
)


def sample_rival_field(
    scenarios: ScenarioSet, ownership: Mapping[PlayerId, float], *, rivals: int, seed: int,
) -> RivalField:
    """Score a simulated rival field from projected ownership on shared scenarios."""
    if type(rivals) is not int or rivals < 1:
        raise ValueError("Rival count must be a positive integer")
    if type(seed) is not int or seed < 0:
        raise ValueError("Rival seed must be a non-negative integer")
    index = {player: i for i, player in enumerate(scenarios.player_ids)}
    weights = np.zeros(len(index), dtype=np.float64)
    for player, share in ownership.items():
        if player not in index or not _share(share):
            raise ValueError("Ownership needs scenario players and shares in [0, 1]")
        weights[index[player]] = share
    if np.count_nonzero(weights) < _SLOTS:
        raise ValueError("Ownership must cover at least five players")
    with np.errstate(divide="ignore"):
        log_weights = np.log(weights)
    rng = np.random.default_rng(seed)
    plays = scenarios.points.T
    runs = np.arange(scenarios.simulations)[:, None]
    scores = np.empty((rivals, scenarios.simulations), dtype=np.int64)
    for rival in range(rivals):
        keys = rng.gumbel(size=plays.shape) + log_weights
        picks = np.argpartition(-keys, _SLOTS - 1, axis=1)[:, :_SLOTS]
        scores[rival] = plays[runs, picks].sum(axis=1)
    return RivalField(scores=scores, assumptions=RivalAssumptions(
        source="tennis_pool.optimizer.sample_rival_field", rivals=rivals, seed=seed,
        model=_OWNERSHIP_MODEL,
        ownership=tuple(sorted((p, float(s)) for p, s in ownership.items())),
        scenario_digest=scenarios.digest,
    ))


@dataclass(frozen=True, kw_only=True)
class SearchLimits(Contract):
    """Pruning and search limits; all are disclosed with the recommendation."""

    seeded_pool: int = 6
    unseeded_pool: int = 10
    substitute_pool: int = 6
    max_rosters: int = 400_000
    screen_scenarios: int = 2_000
    beam: int = 200
    substitute_passes: int = 3
    exchange_rosters: int = 20
    exhaustive_limit: int = 100_000
    alternatives: int = 5
    robust_alpha: float = 0.2

    def __post_init__(self) -> None:
        super().__post_init__()
        if (min(self.seeded_pool, self.unseeded_pool, self.max_rosters, self.screen_scenarios,
                self.beam, self.substitute_passes, self.alternatives) < 1
                or self.exchange_rosters < 0
                or self.substitute_pool < 0 or self.exhaustive_limit < 0
                or not 0 < self.robust_alpha <= 1):
            raise ValueError("Search limits must be positive and robust_alpha in (0, 1]")


@dataclass(frozen=True, kw_only=True)
class Metrics(Contract):
    """Every objective's estimate for one policy; rival-based ones need a field."""

    expected_points: float
    points_se: float
    robust_points: float
    p_top3: float | None
    p_top3_se: float | None
    expected_payout_cents: float | None
    payout_se_cents: float | None


@dataclass(frozen=True, kw_only=True)
class Candidate(Contract):
    pairs: tuple[Pair, ...]
    objective_value: float
    metrics: Metrics
    gap_to_best: float
    gap_se: float
    tie_with_best: bool


@dataclass(frozen=True, kw_only=True)
class SearchReport(Contract):
    method: str
    eligible_players: int
    primary_pool: int
    substitute_pool: int
    pruned_players: int
    primary_rosters: int
    screen_scenarios: int
    refined_rosters: int
    exchanged_rosters: int
    limits: SearchLimits
    exhaustive: bool
    exhaustive_policies: int | None
    optimality_gap: float | None
    gap_basis: str
    upper_bound: float | None


@dataclass(frozen=True, kw_only=True)
class RecommendationAssumptions(Contract):
    objective: Objective
    objective_definition: str
    scenarios: ScenarioAssumptions
    rivals: RivalAssumptions | None
    payout_config_version: str | None
    tie_rule: str
    season_effects: str
    rule_register_version: str
    recommendation_decisions: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, kw_only=True)
class Recommendation(Contract):
    event_id: str
    objective: Objective
    best: Candidate
    alternatives: tuple[Candidate, ...]
    search: SearchReport
    assumptions: RecommendationAssumptions

    @property
    def near_ties(self) -> tuple[Candidate, ...]:
        return tuple(c for c in self.alternatives if c.tie_with_best)


@dataclass(frozen=True, kw_only=True)
class RecommendationSet(Contract):
    recommendations: tuple[Recommendation, ...]
    skipped: tuple[tuple[Objective, str], ...]


_DEFINITIONS = {
    Objective.EXPECTED_POINTS: "Mean own pool points over the shared scenarios.",
    Objective.P_TOP3: ("Share of scenarios with fewer than three rivals strictly ahead "
                       "(ties for third count as top three)."),
    Objective.EXPECTED_PAYOUT: ("Mean event prize in cents; ties share the pooled prizes "
                                "of the positions they occupy."),
    Objective.ROBUST: ("Lower-tail mean of own points (Rockafellar-Uryasev CVaR) over the "
                       "worst robust_alpha share of scenarios."),
}


class _Scorer:
    """Vectorized per-scenario contributions whose mean is the objective."""

    def __init__(self, rivals: RivalField | None, prizes: tuple[int, ...] | None,
                 alpha: float, own_max: int) -> None:
        self.alpha = alpha
        self.rivals = rivals
        self.flat: NDArray[np.int64] | None = None
        if rivals is not None:
            count, runs = rivals.scores.shape
            self.count = count
            self.width = int(max(own_max, int(rivals.scores.max()))) + 1
            if runs * self.width >= 2**62:
                raise ValueError("Scores too large to rank exactly in 64-bit keys")
            ordered = np.sort(rivals.scores, axis=0).T
            self.flat = (ordered + (np.arange(runs, dtype=np.int64) * self.width)[:, None]).ravel()
            padded = np.zeros(count + 1, dtype=np.float64)
            if prizes is not None:
                padded[:min(len(prizes), count + 1)] = prizes[:count + 1]
            self.cumulative = np.concatenate(([0.0], np.cumsum(padded)))
            self.has_prizes = prizes is not None

    def _rank(self, totals: NDArray[np.int64]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
        assert self.flat is not None
        runs = totals.shape[-1]
        offsets = np.arange(runs, dtype=np.int64)
        query = totals + offsets * self.width
        base = offsets * self.count
        right = np.searchsorted(self.flat, query, side="right") - base
        left = np.searchsorted(self.flat, query, side="left") - base
        ahead = self.count - right
        return ahead, right - left

    def contributions(self, objective: Objective,
                      totals: NDArray[np.int64]) -> NDArray[np.float64]:
        if objective is Objective.EXPECTED_POINTS:
            return totals.astype(np.float64)
        if objective is Objective.ROBUST:
            runs = totals.shape[-1]
            k = max(1, math.ceil(self.alpha * runs)) - 1
            var = np.partition(totals, k, axis=-1)[..., k:k + 1].astype(np.float64)
            return var + np.minimum(totals - var, 0.0) / self.alpha
        if self.rivals is None:
            raise ValueError("Rank-based objectives require a rival field from ownership input")
        ahead, tied = self._rank(totals)
        if objective is Objective.P_TOP3:
            return (ahead < 3).astype(np.float64)
        if not self.has_prizes:
            raise ValueError("Expected payout requires a payout configuration")
        share = self.cumulative[ahead + tied + 1] - self.cumulative[ahead]
        result: NDArray[np.float64] = share / (tied + 1)
        return result


@dataclass
class _Problem:
    scenarios: ScenarioSet
    plays: NDArray[np.int64]           # padded with a zero row for "no substitute"
    out: NDArray[np.int64]             # 1 where the player withdrew pre-match
    eligible: list[int]
    bands: dict[int, Band]
    banks: dict[Band, int]
    screen_value: NDArray[np.float64]
    prune_value: NDArray[np.float64]
    withdrawal_rate: NDArray[np.float64]
    none: int = field(init=False)

    def __post_init__(self) -> None:
        self.none = len(self.scenarios.player_ids)

    def totals(self, primaries: NDArray[np.int64], substitutes: NDArray[np.int64],
               runs: int | None = None) -> NDArray[np.int64]:
        plays = self.plays if runs is None else self.plays[:, :runs]
        out = self.out if runs is None else self.out[:, :runs]
        slot = plays[primaries] + out[primaries] * plays[substitutes]
        result: NDArray[np.int64] = slot.sum(axis=-2)
        return result

    def legal_counts(self, roster: Sequence[int]) -> bool:
        counts: dict[Band, int] = {}
        for player in roster:
            counts[self.bands[player]] = counts.get(self.bands[player], 0) + 1
        return all(counts.get(band, 0) <= self.banks[band] for band in _SEEDED)


def _problem(scenarios: ScenarioSet, draw: Draw, event_id: str,
             entry: EntryState | None) -> _Problem:
    if event_id not in _SLAMS | _MASTERS:
        raise ValueError("Unknown pool event; use a canonical 2026 pool event ID")
    seeds = {s.player_id: s.seed for s in draw.slots if s.player_id is not None}
    if seeds.keys() != set(scenarios.player_ids) or any(
            seeds[p] != seed for p, seed in zip(scenarios.player_ids, scenarios.seeds)):
        raise ValueError("Scenario players and seeds must match the released draw")
    if (scenarios.assumptions.draw_digest is not None
            and scenarios.assumptions.draw_digest != _draw_digest(draw)):
        raise ValueError("Scenarios were simulated on a different draw")
    bank_name = "slam" if event_id in _SLAMS else "masters"
    if entry is None:
        bank, usage = _FULL_BANKS[bank_name], {}
    else:
        bank = entry.slam if bank_name == "slam" else entry.masters
        usage = dict(entry.usage)
    banks = dict(zip(_SEEDED, bank))
    bands = {i: seed_band(seed) for i, seed in enumerate(scenarios.seeds)}
    eligible = [i for i, p in enumerate(scenarios.player_ids) if usage.get(p, 0) < _USE_CAP]
    mean = scenarios.points.mean(axis=1).astype(np.float64)
    upside = np.quantile(scenarios.points, 0.9, axis=1).astype(np.float64)
    plays = np.vstack((scenarios.points.astype(np.int64),
                       np.zeros((1, scenarios.simulations), dtype=np.int64)))
    out = np.vstack((scenarios.withdrawn.astype(np.int64),
                     np.zeros((1, scenarios.simulations), dtype=np.int64)))
    return _Problem(scenarios=scenarios, plays=plays, out=out, eligible=eligible,
                    bands=bands, banks=banks, screen_value=mean, prune_value=mean + upside,
                    withdrawal_rate=scenarios.withdrawn.mean(axis=1).astype(np.float64))


def _band_lists(problem: _Problem, players: Sequence[int]) -> dict[Band, list[int]]:
    """Players per band, best first by mean plus 90th-percentile points."""
    lists: dict[Band, list[int]] = {band: [] for band in _BANDS}
    for player in players:
        lists[problem.bands[player]].append(player)
    for band in lists:
        lists[band].sort(key=lambda i: (-problem.prune_value[i], i))
    return lists


def _rosters(problem: _Problem, pool: dict[Band, list[int]], limit: int) -> list[tuple[int, ...]]:
    """Every bank-legal five-primary roster from the pool, counted before enumeration."""
    caps = [min(len(pool[b]), _SLOTS if b is Band.UNSEEDED else problem.banks[b]) for b in _BANDS]
    structures = [counts for counts in product(*(range(cap + 1) for cap in caps))
                  if sum(counts) == _SLOTS]
    total = sum(math.prod(math.comb(len(pool[band]), n) for band, n in zip(_BANDS, counts))
                for counts in structures)
    if total > limit:
        raise ValueError("{} legal primary rosters exceed the limit of {}; lower the pool "
                         "sizes or raise max_rosters".format(total, limit))
    rosters: list[tuple[int, ...]] = []
    for counts in structures:
        groups = [combinations(pool[band], n) for band, n in zip(_BANDS, counts)]
        for combo in product(*groups):
            rosters.append(tuple(sorted(i for group in combo for i in group)))
    return rosters


def _greedy_substitutes(problem: _Problem, roster: tuple[int, ...],
                        options: dict[Band, list[int]], cover: dict[tuple[int, int], float],
                        ) -> list[int]:
    """Best same-band cover per slot (withdrawal-weighted value, then mean points)."""
    taken = set(roster)
    chosen = [problem.none] * _SLOTS
    order = sorted(range(_SLOTS), key=lambda j: -problem.withdrawal_rate[roster[j]])
    for j in order:
        primary = roster[j]
        best: tuple[float, float, int] | None = None
        for sub in options[problem.bands[primary]]:
            if sub in taken:
                continue
            key = (cover.get((primary, sub), 0.0), float(problem.screen_value[sub]), -sub)
            if best is None or key > best:
                best = key
        if best is not None:
            chosen[j] = -best[2]
            taken.add(chosen[j])
    return chosen


def _cover(problem: _Problem, primaries: Sequence[int], subs: Sequence[int],
           ) -> dict[tuple[int, int], float]:
    """Mean substitute points in scenarios where the primary withdrew."""
    if not primaries or not subs:
        return {}
    risky = [p for p in primaries if problem.out[p].any()]
    if not risky:
        return {}
    matrix = (problem.out[risky].astype(np.float64) @ problem.plays[list(subs)].T.astype(np.float64)
              ) / problem.scenarios.simulations
    return {(p, s): float(matrix[a, b]) for a, p in enumerate(risky) for b, s in enumerate(subs)
            if problem.bands[p] is problem.bands[s]}


def _values(scorer: _Scorer, objective: Objective, problem: _Problem,
            primaries: NDArray[np.int64], substitutes: NDArray[np.int64],
            runs: int | None = None, chunk: int = 256) -> NDArray[np.float64]:
    values = np.empty(len(primaries), dtype=np.float64)
    for start in range(0, len(primaries), chunk):
        stop = start + chunk
        totals = problem.totals(primaries[start:stop], substitutes[start:stop], runs)
        values[start:stop] = scorer.contributions(objective, totals).mean(axis=-1)
    return values


def _improve_substitutes(scorer: _Scorer, objective: Objective, problem: _Problem,
                         roster: tuple[int, ...], substitutes: list[int],
                         options: dict[Band, list[int]], passes: int) -> list[int]:
    """Coordinate ascent over each slot's substitute on every scenario."""
    subs = list(substitutes)
    primaries = np.array(roster, dtype=np.int64)
    for _ in range(passes):
        changed = False
        for j in range(_SLOTS):
            used = set(roster) | {s for k, s in enumerate(subs) if k != j}
            choices = [problem.none] + [
                s for s in options[problem.bands[roster[j]]] if s not in used
            ]
            trial = np.tile(np.array(subs, dtype=np.int64), (len(choices), 1))
            trial[:, j] = choices
            values = _values(scorer, objective, problem,
                             np.tile(primaries, (len(choices), 1)), trial)
            def key(c: int) -> tuple[float, bool, float, int]:
                sub = choices[c]
                insured = sub != problem.none
                return (float(values[c]), insured,
                        float(problem.screen_value[sub]) if insured else -math.inf, -sub)

            best = max(range(len(choices)), key=key)
            if key(best) > key(choices.index(subs[j])):
                subs[j] = choices[best]
                changed = True
        if not changed:
            break
    return subs


def _exchange_substitutes(scorer: _Scorer, objective: Objective, problem: _Problem,
                          roster: tuple[int, ...], substitutes: list[int],
                          options: dict[Band, list[int]], passes: int) -> list[int]:
    """Re-choose the substitutes of every same-band slot pair together.

    Coordinate ascent stalls when two slots must trade covers at once; this
    pairwise move (a 2-exchange) removes that local optimum.
    """
    subs = list(substitutes)
    primaries = np.array(roster, dtype=np.int64)

    def key(assignment: Sequence[int], value: float) -> tuple[float, int, float]:
        insured = [s for s in assignment if s != problem.none]
        return value, len(insured), float(sum(problem.screen_value[s] for s in insured))

    for _ in range(passes):
        changed = False
        for j, k in combinations(range(_SLOTS), 2):
            band = problem.bands[roster[j]]
            if problem.bands[roster[k]] is not band:
                continue
            used = set(roster) | {s for i, s in enumerate(subs) if i not in (j, k)}
            free = [problem.none] + [s for s in options[band] if s not in used]
            trials = [(a, b) for a in free for b in free if a != b or a == problem.none]
            batch = np.tile(np.array(subs, dtype=np.int64), (len(trials), 1))
            batch[:, j] = [a for a, _ in trials]
            batch[:, k] = [b for _, b in trials]
            values = _values(scorer, objective, problem,
                             np.tile(primaries, (len(trials), 1)), batch)
            current = key(subs, float(values[trials.index((subs[j], subs[k]))]))
            best = max(range(len(trials)),
                       key=lambda t: (key(batch[t].tolist(), float(values[t])),
                                      [-x for x in batch[t].tolist()]))
            if key(batch[best].tolist(), float(values[best])) > current:
                subs = batch[best].tolist()
                changed = True
        if not changed:
            break
    return subs


def _substitute_assignments(problem: _Problem, roster: tuple[int, ...],
                            options: dict[Band, list[int]]) -> Iterator[tuple[int, ...]]:
    def extend(slot: int, used: frozenset[int]) -> Iterator[tuple[int, ...]]:
        if slot == _SLOTS:
            yield ()
            return
        for sub in [problem.none] + options[problem.bands[roster[slot]]]:
            if sub != problem.none and sub in used:
                continue
            for rest in extend(slot + 1, used | {sub} if sub != problem.none else used):
                yield (sub,) + rest
    yield from extend(0, frozenset(roster))


def _exhaustive(problem: _Problem, limit: int) -> tuple[NDArray[np.int64], NDArray[np.int64]] | None:
    """Every legal policy over all eligible players, or None above the limit."""
    if limit < 1:
        return None
    pool = _band_lists(problem, problem.eligible)
    try:
        rosters = _rosters(problem, pool, limit)
    except ValueError:
        return None
    primaries: list[tuple[int, ...]] = []
    substitutes: list[tuple[int, ...]] = []
    for roster in rosters:
        for assignment in _substitute_assignments(problem, roster, pool):
            primaries.append(roster)
            substitutes.append(assignment)
            if len(primaries) > limit:
                return None
    if not primaries:
        return None
    return np.array(primaries, dtype=np.int64), np.array(substitutes, dtype=np.int64)


def _expected_points_bound(problem: _Problem) -> float:
    """Relaxation: best cover per primary ignoring substitute distinctness."""
    pool = _band_lists(problem, problem.eligible)
    mean_play = problem.plays.mean(axis=1)
    slot_best: dict[Band, list[float]] = {band: [] for band in _BANDS}
    for band, players in pool.items():
        for p in players:
            cover = 0.0
            others = [s for s in players if s != p]
            if others and problem.out[p].any():
                cover = float(np.max(problem.out[p] @ problem.plays[others].T)
                              ) / problem.scenarios.simulations
            slot_best[band].append(float(mean_play[p]) + cover)
        slot_best[band].sort(reverse=True)
    caps = [min(len(slot_best[b]), _SLOTS if b is Band.UNSEEDED else problem.banks[b])
            for b in _BANDS]
    best = -math.inf
    for counts in product(*(range(cap + 1) for cap in caps)):
        if sum(counts) == _SLOTS:
            best = max(best, sum(sum(slot_best[b][:n]) for b, n in zip(_BANDS, counts)))
    return best


def _metrics(scorer: _Scorer, totals: NDArray[np.int64]) -> Metrics:
    runs = totals.shape[-1]

    def se(values: NDArray[np.float64]) -> float:
        return float(values.std(ddof=1) / math.sqrt(runs)) if runs > 1 else 0.0

    points = totals.astype(np.float64)
    robust = scorer.contributions(Objective.ROBUST, totals)
    top3 = payout = None
    if scorer.rivals is not None:
        top3 = scorer.contributions(Objective.P_TOP3, totals)
        if scorer.has_prizes:
            payout = scorer.contributions(Objective.EXPECTED_PAYOUT, totals)
    return Metrics(
        expected_points=float(points.mean()), points_se=se(points),
        robust_points=float(robust.mean()),
        p_top3=None if top3 is None else float(top3.mean()),
        p_top3_se=None if top3 is None else se(top3),
        expected_payout_cents=None if payout is None else float(payout.mean()),
        payout_se_cents=None if payout is None else se(payout),
    )


def _pairs(problem: _Problem, roster: Sequence[int], subs: Sequence[int]) -> tuple[Pair, ...]:
    ids = problem.scenarios.player_ids

    def selection(i: int) -> Selection:
        return Selection(player_id=ids[i], band=problem.bands[i])

    return tuple(Pair(primary=selection(p), substitute=None if s == problem.none else selection(s))
                 for p, s in sorted(zip(roster, subs), key=lambda pair: ids[pair[0]]))


def _check_inputs(objective: Objective, scenarios: ScenarioSet, rivals: RivalField | None,
                  payout: PayoutConfig | None, allow_provisional: bool,
                  register_path: str | Path | None) -> tuple[int, ...] | None:
    if not isinstance(objective, Objective):
        raise ValueError("Unknown optimization objective")
    if rivals is not None and (rivals.scores.shape[1] != scenarios.simulations
                               or rivals.assumptions.scenario_digest != scenarios.digest):
        raise ValueError("Rival scores must be bound to these exact scenarios")
    if objective in _RIVAL_OBJECTIVES and rivals is None:
        raise ValueError("Rank-based objectives require ownership input (a rival field)")
    if payout is None:
        if objective is Objective.EXPECTED_PAYOUT:
            raise ValueError("Expected payout requires a payout configuration")
        return None
    derived = payout_config(payout.participants, override=payout.override,
                            allow_provisional=allow_provisional, register_path=register_path)
    if derived != payout:
        raise ValueError("Payout configuration does not match its versioned derivation")
    if rivals is None or rivals.assumptions.rivals + 1 != payout.participants:
        raise ValueError("Payouts need a rival field of participants - 1 entries")
    return payout.event_prizes_cents


def optimize(
    scenarios: ScenarioSet,
    draw: Draw,
    event_id: str,
    *,
    objective: Objective,
    entry: EntryState | None = None,
    rivals: RivalField | None = None,
    payout: PayoutConfig | None = None,
    limits: SearchLimits | None = None,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> Recommendation:
    """Return the best legal joint policy plus ranked, tie-labelled alternatives."""
    version, decisions = _gate(allow_provisional, register_path)
    limits = limits or SearchLimits()
    prizes = _check_inputs(objective, scenarios, rivals, payout,
                           allow_provisional, register_path)
    problem = _problem(scenarios, draw, event_id, entry)
    own_max = int(np.sort(scenarios.points, axis=0)[-2 * _SLOTS:].sum(axis=0).max())
    scorer = _Scorer(rivals, prizes, limits.robust_alpha, own_max)

    by_band = _band_lists(problem, problem.eligible)
    pool = {band: players[:limits.unseeded_pool if band is Band.UNSEEDED else limits.seeded_pool]
            for band, players in by_band.items()}
    options = {band: list(dict.fromkeys(pool[band] + players[:limits.substitute_pool]))
               for band, players in by_band.items()}
    pool_players = [p for players in pool.values() for p in players]
    option_players = sorted({p for players in options.values() for p in players})
    screen_runs = min(limits.screen_scenarios, scenarios.simulations)
    rosters = _rosters(problem, pool, limits.max_rosters)
    policies: list[tuple[tuple[int, ...], list[int]]] = []
    found: float | None = None
    candidates_p = np.zeros((0, _SLOTS), dtype=np.int64)
    candidates_s = np.zeros((0, _SLOTS), dtype=np.int64)
    values = np.zeros(0, dtype=np.float64)
    if rosters:
        cover = _cover(problem, pool_players, option_players)
        greedy = [_greedy_substitutes(problem, roster, options, cover) for roster in rosters]
        screened = _values(scorer, objective, problem, np.array(rosters, dtype=np.int64),
                           np.array(greedy, dtype=np.int64), screen_runs)
        keep = sorted(range(len(rosters)),
                      key=lambda i: (-screened[i], rosters[i]))[:limits.beam]
        policies = [(rosters[i], _improve_substitutes(
            scorer, objective, problem, rosters[i], greedy[i], options,
            limits.substitute_passes)) for i in keep]
        candidates_p = np.array([p for p, _ in policies], dtype=np.int64)
        candidates_s = np.array([s for _, s in policies], dtype=np.int64)
        values = _values(scorer, objective, problem, candidates_p, candidates_s)
        exchange = sorted(range(len(policies)), key=lambda i: (-values[i], policies[i][0]))
        for i in exchange[:limits.exchange_rosters]:
            candidates_s[i] = _exchange_substitutes(
                scorer, objective, problem, policies[i][0], candidates_s[i].tolist(),
                options, limits.substitute_passes)
        values = _values(scorer, objective, problem, candidates_p, candidates_s)
        found = float(values.max())

    method = ("pruned enumeration + prefix screen + substitute coordinate ascent "
              "+ pairwise substitute exchange")
    exhaustive = _exhaustive(problem, limits.exhaustive_limit)
    gap: float | None = None
    bound: float | None = None
    exhaustive_count: int | None = None
    if exhaustive is not None:
        all_values = _values(scorer, objective, problem, *exhaustive)
        exhaustive_count = len(all_values)
        candidates_p, candidates_s, values = exhaustive[0], exhaustive[1], all_values
        method = "exhaustive enumeration"
        basis = "Exhaustive over all {} legal policies of every eligible player; ".format(
            exhaustive_count)
        if found is None:
            basis += ("the pruned pool formed no legal roster, so the heuristic gap is not "
                      "measured; the recommendation is the exhaustive optimum.")
        else:
            gap = max(0.0, float(all_values.max()) - found)
            basis += ("the heuristic search's in-sample gap is reported; the recommendation "
                      "is the exhaustive optimum.")
    elif found is None:
        raise ValueError("No legal five-primary roster under the remaining bank and use cap "
                         "in the searched pool")
    elif objective is Objective.EXPECTED_POINTS:
        bound = _expected_points_bound(problem)
        gap = max(0.0, bound - found)
        basis = ("Upper bound from a relaxation that ignores substitute distinctness; the gap "
                 "is an in-sample bound, not a measured gap.")
    else:
        basis = ("Not measured: the policy space exceeds the exhaustive limit of {} policies "
                 "and this objective has no bound.".format(limits.exhaustive_limit))

    order = sorted(range(len(values)), key=lambda i: (
        -values[i], tuple(candidates_p[i]), tuple(candidates_s[i])))
    # Alternatives are distinct primary rosters with the best substitutes found.
    unique: list[int] = []
    seen: set[frozenset[int]] = set()
    for i in order:
        roster = frozenset(candidates_p[i].tolist())
        if roster not in seen:
            seen.add(roster)
            unique.append(i)
        if len(unique) > limits.alternatives:
            break
    best_totals = problem.totals(candidates_p[unique[0]], candidates_s[unique[0]])
    best_contrib = scorer.contributions(objective, best_totals)
    materiality = _TOP3_MATERIALITY if objective is Objective.P_TOP3 else 0.0
    chosen: list[Candidate] = []
    for i in unique:
        totals = problem.totals(candidates_p[i], candidates_s[i])
        diff = best_contrib - scorer.contributions(objective, totals)
        runs = len(diff)
        gap_se = float(diff.std(ddof=1) / math.sqrt(runs)) if runs > 1 else 0.0
        gap_mean = float(diff.mean())
        pairs = _pairs(problem, candidates_p[i].tolist(), candidates_s[i].tolist())
        check = validate_roster(
            pairs, draw, event_id, entry, allow_provisional=allow_provisional,
            register_path=register_path,
        )
        if not check.legal:
            raise AssertionError("Search produced an illegal policy: " + "; ".join(
                check.problems + tuple(p for s in check.scenarios for p in s.problems)))
        chosen.append(Candidate(
            pairs=pairs, objective_value=float(values[i]), metrics=_metrics(scorer, totals),
            gap_to_best=gap_mean, gap_se=gap_se,
            tie_with_best=i != unique[0] and gap_mean <= max(_TIE_Z * gap_se, materiality),
        ))
    report = SearchReport(
        method=method, eligible_players=len(problem.eligible), primary_pool=len(pool_players),
        substitute_pool=len(option_players),
        pruned_players=len(problem.eligible) - len(set(pool_players) | set(option_players)),
        primary_rosters=len(rosters), screen_scenarios=screen_runs,
        refined_rosters=len(policies),
        exchanged_rosters=min(limits.exchange_rosters, len(policies)), limits=limits,
        exhaustive=exhaustive is not None, exhaustive_policies=exhaustive_count,
        optimality_gap=gap, gap_basis=basis, upper_bound=bound,
    )
    tie_rule = ("An alternative ties the best when its paired in-sample shortfall is at most "
                "{:g} paired standard errors{}.".format(
                    _TIE_Z, " or {:.1%} absolute P(top-3)".format(materiality)
                    if materiality else ""))
    return Recommendation(
        event_id=event_id, objective=objective, best=chosen[0], alternatives=tuple(chosen[1:]),
        search=report, assumptions=RecommendationAssumptions(
            objective=objective,
            objective_definition=_DEFINITIONS[objective].replace(
                "robust_alpha", "{:g}".format(limits.robust_alpha)),
            scenarios=scenarios.assumptions,
            rivals=None if rivals is None else rivals.assumptions,
            payout_config_version=None if payout is None else payout.config_version,
            tie_rule=tie_rule, season_effects=_SEASON_EFFECTS,
            rule_register_version=version, recommendation_decisions=decisions,
        ),
    )


def recommend(
    scenarios: ScenarioSet,
    draw: Draw,
    event_id: str,
    *,
    entry: EntryState | None = None,
    rivals: RivalField | None = None,
    payout: PayoutConfig | None = None,
    limits: SearchLimits | None = None,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> RecommendationSet:
    """Expected-points, robust and, given ownership input, rank/payout alternatives."""
    results = []
    skipped: list[tuple[Objective, str]] = []
    for objective in Objective:
        if objective in _RIVAL_OBJECTIVES and rivals is None:
            skipped.append((objective, "Requires ownership input (a rival field)"))
            continue
        if objective is Objective.EXPECTED_PAYOUT and payout is None:
            skipped.append((objective, "Requires a payout configuration"))
            continue
        results.append(optimize(
            scenarios, draw, event_id, objective=objective, entry=entry, rivals=rivals,
            payout=payout if rivals is not None else None, limits=limits, allow_provisional=allow_provisional,
            register_path=register_path,
        ))
    return RecommendationSet(recommendations=tuple(results), skipped=tuple(skipped))


def evaluate(
    scenarios: ScenarioSet,
    pairs: tuple[Pair, ...],
    *,
    rivals: RivalField | None = None,
    payout: PayoutConfig | None = None,
    robust_alpha: float = 0.2,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> Metrics:
    """Score a caller's own policy on the same scenarios.

    Legality is not checked here; use ``substitutions.validate_roster``.
    """
    _gate(allow_provisional, register_path)
    prizes = _check_inputs(Objective.EXPECTED_POINTS, scenarios, rivals, payout,
                           allow_provisional, register_path)
    index = {player: i for i, player in enumerate(scenarios.player_ids)}
    none = len(index)
    try:
        primaries = np.array([index[p.primary.player_id] for p in pairs], dtype=np.int64)
        substitutes = np.array([none if p.substitute is None else index[p.substitute.player_id]
                                for p in pairs], dtype=np.int64)
    except KeyError as error:
        raise ValueError("Policy player is not in the scenarios") from error
    if not 0 < robust_alpha <= 1:
        raise ValueError("robust_alpha must be in (0, 1]")
    plays = np.vstack((scenarios.points.astype(np.int64),
                       np.zeros((1, scenarios.simulations), dtype=np.int64)))
    out = np.vstack((scenarios.withdrawn.astype(np.int64),
                     np.zeros((1, scenarios.simulations), dtype=np.int64)))
    totals = (plays[primaries] + out[primaries] * plays[substitutes]).sum(axis=0)
    own_max = int(totals.max())
    return _metrics(_Scorer(rivals, prizes, robust_alpha, own_max), totals)
