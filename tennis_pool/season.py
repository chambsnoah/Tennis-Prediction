"""Rolling season planning: what saving band quota and player uses is worth.

Each event is planned from the information available before its own cutoff.
Future events stay uncertain: per sampled world, a player enters with his
pre-cutoff entry probability, entrants are seeded by a noisy rank, and outcomes
are noisy around his expected points. A future event's participation and seeds
are revealed only at that event's own decision, never its results.

Three policies are compared on the same worlds:

- ``GREEDY`` optimizes the event on the whole remaining bank.
- ``RATIONED`` caps each seeded band at its fair share of the events left that
  seed it, spending everything at the last one (the repaired reference rule).
- ``HORIZON`` chooses this event's band structure to maximize expected points
  now plus the expected value of the bank left, from a backward dynamic
  programme over future events, and preserves a player's use when its expected
  future value clearly exceeds his edge now.

``plan_event`` recommends a sheet and explains the opportunity cost of every
token and use it spends or keeps. ``replay_season`` replays a season
sequentially: each policy decides from pre-cutoff inputs only and consumes its
own ledger state after every event. Estimates are conditional on the supplied
prospects and on unfitted model priors; they are not predictions of the
winning sheet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from itertools import product
import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from tennis_api.models.canonical import Contract, Draw, PlayerId, Provenance
from tennis_pool.ledger import (
    _MASTERS, _SEEDED, _SLAMS, Accepted, ApprovedActivation, Band, EntryState, EventPoints,
    EventTerms, LedgerRecord, Pair, SeasonLedger, Submitted,
)
from tennis_pool.optimizer import (
    Objective, Recommendation, RivalField, ScenarioSet, SearchLimits, _gate, optimize,
)
from tennis_pool.payouts import PayoutConfig, payout_config, split_prizes
from tennis_pool.substitutions import _FULL_BANKS, seed_band, validate_roster


_TAG = 0x5345534E
_SLOTS = 5
_USE_CAP = 5
_BONUS = 250
_BONUS_EVENTS = 7
_TIE_Z = 2.0
_TOP3_MATERIALITY = 0.015
_EPSILON = 1e-6
_BANDS = (Band.TOP4, Band.TOP8, Band.TOP16, Band.TOP32, Band.UNSEEDED)
_UNSEEDED = 4
_KINDS: dict[str, str] = {**{e: "gs" for e in _SLAMS}, **{e: "m7" for e in _MASTERS},
                          "monte_carlo": "m6", "paris": "m6"}
_SEEDS = {"gs": 32, "m7": 32, "m6": 16}
_CAPACITY = {"gs": (4, 4, 8, 16), "m7": (4, 4, 8, 16), "m6": (4, 4, 8, 0)}
# Every seeded band structure (picks per seeded band) of a five-pick sheet.
_STRUCTURES = np.array([c for c in product(range(_SLOTS + 1), repeat=4) if sum(c) <= _SLOTS],
                       dtype=np.int64)
_TOKENS = _STRUCTURES.sum(axis=1)

_FUTURE_MODEL = (
    "Each future event is sampled per world from its latest pre-cutoff prospects: "
    "independent entry draws, seeds by noisy rank among entrants (32 seeds, 16 at "
    "Monte Carlo and Paris), and gamma outcome noise around each entrant's expected "
    "points. Participation and seeds are known only at that event's own decision, "
    "outcomes never. Players outside the prospects are worth zero."
)
_HORIZON_MODEL = (
    "Band tokens: a backward dynamic programme over each bank (Slam, Masters) on "
    "planning worlds picks every event's band structure to maximize expected points "
    "now plus the expected value of the bank left; tokens expire unused after the "
    "last event of their bank. Within a structure the best expected scorers are "
    "picked; the programme ignores later use caps, which the forward simulation "
    "enforces. Opportunity costs come from a forward simulation of that policy on "
    "separate evaluation worlds with common random numbers. A use is preserved only "
    "when its later value beats its edge now by more than two standard errors."
)
_RIVAL_MODEL = (
    "Rivals keep the fair-share ration of their own bank and use caps and pick the "
    "best expected scorers under lognormal choice noise (an unfitted prior); their "
    "picks share each world's outcomes with yours. Withdrawn rival picks score zero. "
    "Every entry is assumed to submit the Excel sheet for every remaining event, so "
    "the 250-point bonus is added when seven qualifying events remain reachable."
)
_SEASON_LIMITS = (
    "Substitutes are optimized for this event only; future events are planned without "
    "substitutes. Outcome noise is independent across players within an event."
)
_REPLAY_NOTE = (
    "One sequential realization per policy on the supplied season: each decision saw "
    "only pre-cutoff inputs and the policy's own ledger state. A single season is one "
    "draw, not an expected difference; use plan_event projections for uncertainty "
    "and never sum independent weekly backtests into a season claim."
)


class Policy(str, Enum):
    GREEDY = "greedy"
    RATIONED = "rationed"
    HORIZON = "horizon"


class SeasonObjective(str, Enum):
    EXPECTED_POINTS = "expected_season_points"
    SEASON_PAYOUT = "expected_season_payout"
    P_TOP3 = "p_season_top3"


_PREFERENCE = (Policy.HORIZON, Policy.RATIONED, Policy.GREEDY)


@dataclass(frozen=True, kw_only=True)
class Prospect(Contract):
    """What is known before the cutoff about one player at one future event.

    ``mean_points`` is the expected pool points if he enters; ``rank`` orders
    entrants for seeding (lower is better).
    """

    player_id: PlayerId
    entry_probability: float
    rank: float
    mean_points: float

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0 <= self.entry_probability <= 1 or self.rank <= 0 or self.mean_points < 0:
            raise ValueError("Prospects need an entry probability in [0, 1], a positive rank "
                             "and non-negative expected points")


@dataclass(frozen=True, kw_only=True)
class FutureEvent(Contract):
    """Pre-cutoff prospects for a future event; its draw and results are unknown."""

    event_id: str
    available_at: datetime
    prospects: tuple[Prospect, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.event_id not in _KINDS:
            raise ValueError("Unknown pool event: " + self.event_id)
        if (not self.prospects
                or len({p.player_id for p in self.prospects}) != len(self.prospects)):
            raise ValueError("Future events need distinct player prospects")


@dataclass(frozen=True, kw_only=True)
class PlanningParameters(Contract):
    """Simulation sizes and unfitted priors; every plan discloses them."""

    planning_worlds: int = 100
    evaluation_worlds: int = 200
    rank_noise: float = 0.15
    points_shape: float = 0.7
    rival_choice_noise: float = 0.35

    def __post_init__(self) -> None:
        super().__post_init__()
        if (min(self.planning_worlds, self.evaluation_worlds) < 2 or self.rank_noise < 0
                or self.points_shape <= 0 or self.rival_choice_noise < 0):
            raise ValueError("Planning needs at least two worlds and non-negative noise")


@dataclass(frozen=True, kw_only=True)
class TokenCost(Contract):
    """Now-versus-later value of the marginal token of one seeded band."""

    bank: str
    band: Band
    remaining: int
    planned_spend: int
    gain_now: float | None
    value_later: float | None
    value_later_se: float | None
    advice: str
    explanation: str


@dataclass(frozen=True, kw_only=True)
class UseCost(Contract):
    """Now-versus-later value of one use of a player the plan considered."""

    player_id: PlayerId
    uses_left: int
    in_plan: bool
    edge_now: float
    value_later: float
    value_later_se: float
    later_events: tuple[tuple[str, float], ...]
    advice: str
    explanation: str


@dataclass(frozen=True, kw_only=True)
class RivalGap(Contract):
    entry_id: str
    current_gap: int
    expected_final_gap: float
    final_gap_se: float
    p_finish_ahead: float


@dataclass(frozen=True, kw_only=True)
class PolicyProjection(Contract):
    policy: Policy
    recommendation: Recommendation
    spend: tuple[int, ...]
    preserved: tuple[PlayerId, ...]
    event_expected_points: float
    future_expected_points: float
    season_expected_points: float
    season_points_se: float
    expected_unused_tokens: float
    p_season_top3: float | None
    p_season_first: float | None
    expected_season_payout_cents: float | None
    season_payout_se_cents: float | None
    rival_gaps: tuple[RivalGap, ...]
    gap_to_best: float
    gap_se: float
    tie_with_best: bool


@dataclass(frozen=True, kw_only=True)
class PlanAssumptions(Contract):
    seed: int
    parameters: PlanningParameters
    future_events: tuple[str, ...]
    future_information_at: tuple[tuple[str, datetime], ...]
    future_model: str
    horizon_model: str
    rival_model: str | None
    limits: str
    tie_rule: str
    rule_register_version: str
    recommendation_decisions: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, kw_only=True)
class SeasonPlan(Contract):
    event_id: str
    cutoff: datetime
    objective: SeasonObjective
    chosen: Policy
    projections: tuple[PolicyProjection, ...]
    token_costs: tuple[TokenCost, ...]
    use_costs: tuple[UseCost, ...]
    assumptions: PlanAssumptions

    @property
    def recommendation(self) -> Recommendation:
        return next(p.recommendation for p in self.projections if p.policy is self.chosen)


def ration(bank: Sequence[int], events_left: Sequence[int]) -> tuple[int, ...]:
    """Fair-share cap per seeded band: ceil(remaining / events left seeding it).

    ``events_left`` counts this event and later events of the same bank that seed
    the band, from one deduplicated calendar. The last such event may spend all.
    """
    if len(bank) != 4 or len(events_left) != 4 or min(*bank, *events_left) < 0:
        raise ValueError("Rationing needs four non-negative bank and event counts")
    return tuple(rem if left <= 1 else -(-rem // left) for rem, left in zip(bank, events_left))


def _bank_name(event_id: str) -> str:
    return "slam" if event_id in _SLAMS else "masters"


def _events_left(calendar: Sequence[EventTerms], event: EventTerms) -> tuple[int, ...]:
    same = [t for t in calendar if _bank_name(t.event_id) == _bank_name(event.event_id)
            and t.deadline >= event.deadline]
    return tuple(sum(_CAPACITY[_KINDS[t.event_id]][band] > 0 for t in same) for band in range(4))


@dataclass
class _Event:
    """One event over W worlds for the players it lists (rows)."""

    event_id: str
    kind: str
    players: NDArray[np.int64]
    means: NDArray[np.float64]
    entered: NDArray[np.bool_]
    bands: NDArray[np.int64]
    realized: NDArray[np.float64]
    fillers: bool = True


@dataclass
class _Horizon:
    strides: NDArray[np.int64]
    values: list[NDArray[np.float64]]


def _sample(event: FutureEvent, universe: dict[PlayerId, int], worlds: int,
            params: PlanningParameters, rng: np.random.Generator) -> _Event:
    kind = _KINDS[event.event_id]
    count = len(event.prospects)
    probability = np.array([p.entry_probability for p in event.prospects])
    rank = np.array([p.rank for p in event.prospects])
    means = np.array([p.mean_points for p in event.prospects])
    entered = rng.random((count, worlds)) < probability[:, None]
    key = np.log(rank)[:, None] + params.rank_noise * rng.standard_normal((count, worlds))
    order = np.argsort(np.where(entered, key, np.inf), axis=0, kind="stable")
    seed = np.empty_like(order)
    np.put_along_axis(seed, order, np.arange(1, count + 1)[:, None].repeat(worlds, 1), axis=0)
    bands = np.select([seed <= 4, seed <= 8, seed <= 16, seed <= 32], [0, 1, 2, 3], _UNSEEDED)
    bands = np.where(entered & (seed <= _SEEDS[kind]), bands, _UNSEEDED)
    noise = rng.gamma(params.points_shape, 1 / params.points_shape, (count, worlds))
    return _Event(event_id=event.event_id, kind=kind,
                  players=np.array([universe[p.player_id] for p in event.prospects]),
                  means=means, entered=entered, bands=bands,
                  realized=np.where(entered, means[:, None] * noise, 0.0))


def _current(scenarios: ScenarioSet, event_id: str, universe: dict[PlayerId, int],
             worlds: int) -> _Event:
    columns = np.arange(worlds) % scenarios.simulations
    count = len(scenarios.player_ids)
    bands = np.array([_BANDS.index(seed_band(s)) for s in scenarios.seeds])
    return _Event(event_id=event_id, kind=_KINDS[event_id],
                  players=np.array([universe[p] for p in scenarios.player_ids]),
                  means=scenarios.points.mean(axis=1).astype(np.float64),
                  entered=np.ones((count, worlds), dtype=np.bool_),
                  bands=np.repeat(bands[:, None], worlds, axis=1),
                  realized=scenarios.points[:, columns].astype(np.float64), fillers=False)


def _tops(choice: NDArray[np.float64], bands: NDArray[np.int64], kind: str, fillers: bool,
          ) -> tuple[NDArray[np.float64], list[NDArray[np.int64]], list[NDArray[np.bool_]]]:
    """Structure values (N, W, structures) and the best five per band, best first.

    ``choice`` is N x W x P with -inf for unavailable players; ``bands`` is W x P.
    With ``fillers`` (future events), missing band members are unlisted players
    worth zero, never real picks; otherwise a structure needs real members.
    """
    n, w, count = choice.shape
    k = min(_SLOTS, count)
    prefixes, indexes, reals = [], [], []
    for band in range(len(_BANDS)):
        masked = np.where(bands[None] == band, choice, -np.inf)
        part = (np.argpartition(-masked, k - 1, axis=2)[..., :k] if count > k
                else np.broadcast_to(np.arange(count), (n, w, count)).copy())
        top = np.take_along_axis(masked, part, axis=2)
        order = np.argsort(-top, axis=2, kind="stable")
        index = np.take_along_axis(part, order, axis=2)
        top = np.take_along_axis(top, order, axis=2)
        if k < _SLOTS:
            index = np.concatenate((index, np.zeros((n, w, _SLOTS - k), np.int64)), axis=2)
            top = np.concatenate((top, np.full((n, w, _SLOTS - k), -np.inf)), axis=2)
        real = np.isfinite(top)
        missing = 0.0 if fillers else -np.inf
        prefixes.append(np.concatenate(
            (np.zeros((n, w, 1)), np.cumsum(np.where(real, top, missing), axis=2)), axis=2))
        indexes.append(index)
        reals.append(real)
    values = prefixes[_UNSEEDED][..., _SLOTS - _TOKENS]
    for band in range(4):
        values = values + prefixes[band][..., _STRUCTURES[:, band]]
    infeasible = (_STRUCTURES > np.array(_CAPACITY[kind])).any(axis=1)
    values[..., infeasible] = -np.inf
    return values - _EPSILON * _TOKENS, indexes, reals


def _next_index(bank: NDArray[np.int64], strides: NDArray[np.int64],
                states: int) -> NDArray[np.int64]:
    after = bank[..., None, :] - _STRUCTURES
    return np.where((after >= 0).all(axis=-1), (after * strides).sum(axis=-1), states)


def _play(event: _Event, bank: NDArray[np.int64], usage: NDArray[np.int64], *, rule: Policy,
          events_left: tuple[int, ...], horizon: _Horizon | None = None, position: int = 0,
          noise: NDArray[np.float64] | None = None,
          ) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_]]:
    """Play one event for N x W states in place; returns expected, realized, picks."""
    ok = event.entered.T[None] & (usage[:, :, event.players] < _USE_CAP)
    choice = np.broadcast_to(event.means, ok.shape)
    if noise is not None:
        choice = choice * noise
    values, indexes, reals = _tops(np.where(ok, choice, -np.inf), event.bands.T, event.kind,
                                   event.fillers)
    allowed = bank
    if rule is Policy.RATIONED:
        left = np.array(events_left)
        allowed = np.where(left <= 1, bank, -(-bank // np.maximum(left, 1)))
    values = np.where((_STRUCTURES > allowed[:, :, None, :]).any(axis=-1), -np.inf, values)
    if rule is Policy.HORIZON and horizon is not None:
        later = np.append(horizon.values[position], -np.inf)
        values = values + later[_next_index(bank, horizon.strides, len(later) - 1)]
    counts = _STRUCTURES[np.argmax(values, axis=2)]
    take = np.concatenate((counts, _SLOTS - counts.sum(axis=-1, keepdims=True)), axis=-1)
    picked = np.zeros(ok.shape, dtype=np.bool_)
    for band in range(len(_BANDS)):
        chosen = (np.arange(_SLOTS) < take[..., band:band + 1]) & reals[band]
        n, w, slot = np.nonzero(chosen)
        picked[n, w, indexes[band][n, w, slot]] = True
    expected = (picked * event.means).sum(axis=-1)
    realized = (picked * event.realized.T[None]).sum(axis=-1)
    bank -= counts
    usage[:, :, event.players] += picked
    return expected, realized, picked


def _programme(events: list[_Event], bank: tuple[int, ...],
               exhausted: NDArray[np.bool_]) -> _Horizon:
    """Backward induction over every bank state at or below ``bank``."""
    dims = tuple(b + 1 for b in bank)
    strides = np.array([math.prod(dims[j + 1:]) for j in range(4)], dtype=np.int64)
    states = np.indices(dims).reshape(4, -1).T
    following = _next_index(states, strides, len(states))
    values = [np.zeros(len(states))]
    for event in reversed(events):
        ok = event.entered & ~exhausted[event.players][:, None]
        choice = np.where(ok, event.means[:, None], -np.inf).T[None]
        now = _tops(choice, event.bands.T, event.kind, event.fillers)[0][0]
        later = np.append(values[0], -np.inf)[following]
        total = np.zeros(len(states))
        chunk = max(1, 4_000_000 // later.size)
        for start in range(0, len(now), chunk):
            total += (now[start:start + chunk, None, :] + later[None]).max(axis=2).sum(axis=0)
        values.insert(0, total / len(now))
    return _Horizon(strides=strides, values=values)


@dataclass
class _Context:
    event_id: str
    bank_name: str
    entry: EntryState
    universe: dict[PlayerId, int]
    now: _Event
    planning: list[_Event]
    evaluation: list[_Event]
    future_left: list[tuple[int, ...]]
    events_left: tuple[int, ...]
    horizons: dict[str, _Horizon]
    params: PlanningParameters
    rng: np.random.Generator
    ids: list[PlayerId]

    def usage_vector(self, extra: Sequence[PlayerId] = ()) -> NDArray[np.int64]:
        usage = np.zeros(len(self.universe), dtype=np.int64)
        for player, count in self.entry.usage:
            if player in self.universe:
                usage[self.universe[player]] = count
        for player in extra:
            usage[self.universe[player]] += 1
        return usage

    def bank(self) -> tuple[int, ...]:
        return self.entry.slam if self.bank_name == "slam" else self.entry.masters


def _check_time(value: datetime, cutoff: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None or value >= cutoff:
        raise ValueError(name + " must be timezone-aware and available before the cutoff")


def _context(scenarios: ScenarioSet, draw: Draw, terms: EventTerms, cutoff: datetime,
             entry: EntryState, calendar: Sequence[EventTerms], future: Sequence[FutureEvent],
             params: PlanningParameters, entropy: Sequence[int]) -> _Context:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("Cutoff requires timezone")
    if cutoff >= terms.deadline:
        raise ValueError("Planning cutoff must precede the submission deadline")
    _check_time(terms.provenance.available_at, cutoff, "Event terms")
    _check_time(draw.provenance.available_at, cutoff, "The draw")
    ids = [t.event_id for t in calendar]
    if len(set(ids)) != len(ids) or terms not in calendar:
        raise ValueError("The calendar must list each event once, including this one")
    remaining = sorted((t for t in calendar if t.deadline > terms.deadline),
                       key=lambda t: (t.deadline, t.event_id))
    future_ids = [f.event_id for f in future]
    if sorted(future_ids) != sorted(t.event_id for t in remaining):
        raise ValueError("Future prospects must cover every later calendar event exactly once")
    by_id = {f.event_id: f for f in future}
    for item in future:
        _check_time(item.available_at, cutoff, "Future prospects")
    universe: dict[PlayerId, int] = {}
    for player in list(scenarios.player_ids) + [p.player_id for f in future for p in f.prospects]:
        universe.setdefault(player, len(universe))
    root = np.random.SeedSequence(list(entropy))
    planning_seed, evaluation_seed, rival_seed = root.spawn(3)
    plan_rng = np.random.default_rng(planning_seed)
    eval_rng = np.random.default_rng(evaluation_seed)
    planning = [_sample(by_id[t.event_id], universe, params.planning_worlds, params, plan_rng)
                for t in remaining]
    evaluation = [_sample(by_id[t.event_id], universe, params.evaluation_worlds, params,
                          eval_rng) for t in remaining]
    context = _Context(
        event_id=terms.event_id, bank_name=_bank_name(terms.event_id), entry=entry,
        universe=universe,
        now=_current(scenarios, terms.event_id, universe, params.evaluation_worlds),
        planning=planning, evaluation=evaluation,
        future_left=[_events_left(calendar, t) for t in remaining],
        events_left=_events_left(calendar, terms), horizons={}, params=params,
        rng=np.random.default_rng(rival_seed), ids=list(universe),
    )
    exhausted = context.usage_vector() >= _USE_CAP
    for name in ("slam", "masters"):
        own = [e for e in planning if _bank_name(e.event_id) == name]
        bank = entry.slam if name == "slam" else entry.masters
        context.horizons[name] = _programme(own, bank, exhausted)
    return context


def _forward(context: _Context, rule: Policy, banks: dict[str, NDArray[np.int64]],
             usage: NDArray[np.int64], noise: float = 0.0,
             ) -> tuple[NDArray[np.float64], NDArray[np.float64], list[NDArray[np.bool_]]]:
    """Play every future evaluation event in deadline order, in place."""
    n, w = usage.shape[:2]
    expected, realized = np.zeros((n, w)), np.zeros((n, w))
    picks = []
    position = {"slam": 0, "masters": 0}
    for event, left in zip(context.evaluation, context.future_left):
        name = _bank_name(event.event_id)
        position[name] += 1
        shocks = (np.exp(noise * context.rng.standard_normal((n, w, len(event.players))))
                  if noise else None)
        e, r, p = _play(event, banks[name], usage, rule=rule, events_left=left,
                        horizon=context.horizons[name], position=position[name], noise=shocks)
        expected += e
        realized += r
        picks.append(p)
    return expected, realized, picks


def _rows(context: _Context, rows: Sequence[tuple[tuple[int, ...], tuple[int, ...],
                                                  NDArray[np.int64]]],
          ) -> tuple[NDArray[np.float64], list[NDArray[np.bool_]]]:
    """Future expected points of several own states on common evaluation worlds."""
    w = context.params.evaluation_worlds
    banks = {name: np.array([[row[i]] * w for row in rows], dtype=np.int64)
             for i, name in enumerate(("slam", "masters"))}
    usage = np.array([np.tile(row[2], (w, 1)) for row in rows], dtype=np.int64)
    expected, _, picks = _forward(context, Policy.HORIZON, banks, usage)
    return expected, picks


def _structure_now(context: _Context, excluded: set[PlayerId]) -> tuple[
        NDArray[np.float64], list[NDArray[np.int64]], list[NDArray[np.bool_]]]:
    now = context.now
    usage = context.usage_vector()[now.players]
    ok = (usage < _USE_CAP) & np.array([context.ids[i] not in excluded for i in now.players])
    choice = np.where(ok, now.means, -np.inf)[None, None]
    values, indexes, reals = _tops(choice, now.bands[:, :1].T, now.kind, False)
    return values[0, 0], [i[0, 0] for i in indexes], [r[0, 0] for r in reals]


def _roster(context: _Context, structure: NDArray[np.int64], indexes: list[NDArray[np.int64]],
            reals: list[NDArray[np.bool_]]) -> list[int]:
    take = list(structure) + [_SLOTS - int(structure.sum())]
    return [int(indexes[b][k]) for b in range(len(_BANDS)) for k in range(take[b])
            if reals[b][k]]


def _horizon_choice(context: _Context, excluded: set[PlayerId]) -> tuple[int, float]:
    """Best band structure now plus the bank's later value, and that total."""
    values, _, _ = _structure_now(context, excluded)
    bank = np.array(context.bank(), dtype=np.int64)
    horizon = context.horizons[context.bank_name]
    later = np.append(horizon.values[0], -np.inf)
    total = values + later[_next_index(bank, horizon.strides, len(later) - 1)]
    best = int(np.argmax(total))
    return best, float(total[best])


def _use_costs(context: _Context, slam: tuple[int, ...], masters: tuple[int, ...],
               roster: Sequence[int], excluded: set[PlayerId]) -> list[UseCost]:
    """Edge now (plan value with versus without the player, bands re-chosen) against
    the later value of keeping one use (forward simulation, common worlds)."""
    now = context.now
    chosen = [context.ids[now.players[i]] for i in roster]
    base = context.usage_vector(chosen)
    rows = [(slam, masters, base)]
    for i in roster:
        less = base.copy()
        less[now.players[i]] -= 1
        rows.append((slam, masters, less))
    expected, picks = _rows(context, rows)
    costs = []
    for k, i in enumerate(roster, start=1):
        player = context.ids[now.players[i]]
        gain = expected[k] - expected[0]
        value, se = float(gain.mean()), float(gain.std(ddof=1) / math.sqrt(len(gain)))
        edge = _horizon_choice(context, excluded)[1] - _horizon_choice(
            context, excluded | {player})[1]
        local = int(now.players[i])
        shares = []
        for event, chosen_picks in zip(context.evaluation, picks):
            where = np.nonzero(event.players == local)[0]
            if len(where):
                extra = chosen_picks[k, :, where[0]] & ~chosen_picks[0, :, where[0]]
                if extra.mean() >= 0.005:
                    shares.append((event.event_id, float(extra.mean())))
        shares.sort(key=lambda item: -item[1])
        left = _USE_CAP - int(base[local]) + 1
        if abs(edge - value) <= _TIE_Z * se:
            advice = "tie"
        else:
            advice = "preserve" if value > edge else "spend"
        where_text = ", ".join("{} ({:.0%})".format(e, s) for e, s in shares[:3]) or "nowhere"
        costs.append(UseCost(
            player_id=player, uses_left=left, in_plan=True, edge_now=edge, value_later=value,
            value_later_se=se, later_events=tuple(shares[:3]), advice=advice,
            explanation=(
                "{} has {} use(s) left. Having him now adds {:.1f} expected season points "
                "(bands re-planned without him); keeping the use is worth {:.1f} ± {:.1f} "
                "later, mostly at {}. "
                "{}.".format(player, left, edge, value, se, where_text, {
                    "tie": "Within noise: spend it now (never hoard a fragile asset)",
                    "preserve": "Preserve the use", "spend": "Spend the use now"}[advice])),
        ))
    return costs


def _token_costs(context: _Context, spend: tuple[int, ...], usage_ids: Sequence[PlayerId],
                 values: NDArray[np.float64]) -> list[TokenCost]:
    bank = context.bank()
    base = tuple(b - s for b, s in zip(bank, spend))
    other = context.entry.masters if context.bank_name == "slam" else context.entry.slam
    usage = context.usage_vector(usage_ids)

    def row(own: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...], NDArray[np.int64]]:
        return (own, other, usage) if context.bank_name == "slam" else (other, own, usage)

    rows = [row(base)]
    variants: list[tuple[int, int]] = []
    for band in range(4):
        if spend[band] > 0:
            delta = 1
        elif base[band] > 0:
            delta = -1
        else:
            continue
        rows.append(row(tuple(b + delta * (j == band) for j, b in enumerate(base))))
        variants.append((band, delta))
    expected, _ = _rows(context, rows)
    index = {tuple(s): i for i, s in enumerate(_STRUCTURES.tolist())}
    structure = list(spend)
    costs = []
    for band in range(4):
        variant = next((k for k, (b, _) in enumerate(variants) if b == band), None)
        label = _BANDS[band]
        if variant is None:
            costs.append(TokenCost(
                bank=context.bank_name, band=label, remaining=bank[band], planned_spend=0,
                gain_now=None, value_later=None, value_later_se=None, advice="none",
                explanation="No {} {} token left.".format(context.bank_name, label.value)))
            continue
        delta = variants[variant][1]
        diff = (expected[variant + 1] - expected[0]) * delta
        later, se = float(diff.mean()), float(diff.std(ddof=1) / math.sqrt(diff.shape[0]))
        neighbour = list(structure)
        neighbour[band] -= delta
        current = values[index[tuple(structure)]]
        alternative = values[index[tuple(neighbour)]] if tuple(neighbour) in index else -np.inf
        gain = float(current - alternative) if delta > 0 else float(alternative - current)
        gain_now = gain if math.isfinite(gain) else None
        if gain_now is None:
            advice = "preserve"
        elif abs(gain_now - later) <= _TIE_Z * se:
            advice = "tie"
        else:
            advice = "spend" if gain_now > later else "preserve"
        what = ("the last of {} planned".format(spend[band]) if delta > 0
                else "one more than planned")
        now_text = ("{:.1f} expected points now".format(gain_now) if gain_now is not None
                    else "nothing now (this event cannot use it)")
        costs.append(TokenCost(
            bank=context.bank_name, band=label, remaining=bank[band],
            planned_spend=spend[band], gain_now=gain_now, value_later=later,
            value_later_se=se, advice=advice,
            explanation=(
                "{} {} band: {} left. Spending {} yields {}; holding it is worth "
                "{:.1f} ± {:.1f} expected points later. {}.".format(
                    context.bank_name.capitalize(), label.value, bank[band], what, now_text,
                    later, se, {"tie": "Within noise", "preserve": "Preserve the token",
                                "spend": "Spend it now"}[advice])),
        ))
    return costs


@dataclass
class _Decision:
    policy: Policy
    recommendation: Recommendation
    spend: tuple[int, ...]
    preserved: tuple[PlayerId, ...]
    preserved_costs: list[UseCost]


def _spend(pairs: tuple[Pair, ...]) -> tuple[int, ...]:
    return tuple(sum(p.primary.band is band for p in pairs) for band in _SEEDED)


def _decide(context: _Context, policy: Policy, scenarios: ScenarioSet, draw: Draw, *,
            objective: Objective, rivals: RivalField | None, payout: PayoutConfig | None,
            limits: SearchLimits | None, allow_provisional: bool,
            register_path: str | Path | None) -> _Decision:
    entry = context.entry
    bank = context.bank()
    preserved: tuple[PlayerId, ...] = ()
    preserved_costs: list[UseCost] = []
    caps = bank
    if policy is Policy.RATIONED:
        caps = ration(bank, context.events_left)
    elif policy is Policy.HORIZON:
        _, indexes, reals = _structure_now(context, set())
        structure = _horizon_choice(context, set())[0]
        roster = _roster(context, _STRUCTURES[structure], indexes, reals)
        spend = tuple(int(x) for x in _STRUCTURES[structure])
        base = tuple(b - s for b, s in zip(bank, spend))
        slam, masters = ((base, entry.masters) if context.bank_name == "slam"
                         else (entry.slam, base))
        costs = _use_costs(context, slam, masters, roster, set())
        preserved_costs = [c for c in costs if c.advice == "preserve"]
        preserved = tuple(sorted(c.player_id for c in preserved_costs))
        if preserved:
            structure = _horizon_choice(context, set(preserved))[0]
        caps = tuple(int(x) for x in _STRUCTURES[structure])
    usage = dict(entry.usage)
    usage.update({p: _USE_CAP for p in preserved})
    capped = replace(entry, slam=caps if context.bank_name == "slam" else entry.slam,
                     masters=caps if context.bank_name == "masters" else entry.masters,
                     usage=tuple(sorted(usage.items())))
    recommendation = optimize(
        scenarios, draw, context.event_id, objective=objective, entry=capped, rivals=rivals,
        payout=payout, limits=limits, allow_provisional=allow_provisional,
        register_path=register_path,
    )
    pairs = recommendation.best.pairs
    if not validate_roster(pairs, draw, context.event_id, entry,
                           allow_provisional=allow_provisional,
                           register_path=register_path).legal:
        raise AssertionError("Season planning produced a sheet illegal for the real state")
    return _Decision(policy=policy, recommendation=recommendation, spend=_spend(pairs),
                     preserved=preserved, preserved_costs=[
                         replace(c, in_plan=False) for c in preserved_costs])


def _own_current(scenarios: ScenarioSet, pairs: tuple[Pair, ...], worlds: int,
                 ) -> tuple[NDArray[np.float64], list[list[PlayerId]]]:
    """Per-world event points and the players whose use each world consumes."""
    index = {p: i for i, p in enumerate(scenarios.player_ids)}
    columns = np.arange(worlds) % scenarios.simulations
    totals = np.zeros(worlds)
    used: list[list[PlayerId]] = [[] for _ in range(worlds)]
    for pair in pairs:
        primary = index[pair.primary.player_id]
        out = scenarios.withdrawn[primary, columns]
        cover = pair.substitute
        for w in range(worlds):
            if out[w] and cover is not None:
                totals[w] += scenarios.points[index[cover.player_id], columns[w]]
                used[w].append(cover.player_id)
            else:
                totals[w] += scenarios.points[primary, columns[w]]
                used[w].append(pair.primary.player_id)
    return totals, used


def _pending_bonus(entry: EntryState, events: int) -> int:
    return _BONUS if (entry.submission_bonus == 0
                      and len(entry.qualifying_events) + events >= _BONUS_EVENTS) else 0


def _se(values: NDArray[np.float64]) -> float:
    return float(values.std(ddof=1) / math.sqrt(len(values))) if len(values) > 1 else 0.0


def plan_event(
    scenarios: ScenarioSet,
    draw: Draw,
    terms: EventTerms,
    *,
    cutoff: datetime,
    entry: EntryState,
    calendar: Sequence[EventTerms],
    future: Sequence[FutureEvent],
    seed: int,
    objective: SeasonObjective = SeasonObjective.EXPECTED_POINTS,
    policies: tuple[Policy, ...] = (Policy.GREEDY, Policy.RATIONED, Policy.HORIZON),
    event_objective: Objective = Objective.EXPECTED_POINTS,
    rivals: RivalField | None = None,
    event_payout: PayoutConfig | None = None,
    rival_states: tuple[EntryState, ...] = (),
    named_rivals: tuple[str, ...] = (),
    season_payout: PayoutConfig | None = None,
    limits: SearchLimits | None = None,
    parameters: PlanningParameters | None = None,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> SeasonPlan:
    """Recommend this event's sheet with its season opportunity costs.

    ``calendar`` is the single deduplicated season calendar (the ledger's
    ``events``); ``future`` must hold pre-cutoff prospects for every later event
    in it. ``rival_states`` (the other entries' ledger states at the same cutoff)
    enable standing, payout and named-rival gap projections.
    """
    version, decisions = _gate(allow_provisional, register_path)
    params = parameters or PlanningParameters()
    if type(seed) is not int or seed < 0:
        raise ValueError("Planning seed must be a non-negative integer")
    if (not policies or len(set(policies)) != len(policies)
            or any(not isinstance(p, Policy) for p in policies)):
        raise ValueError("Plan at least one distinct policy")
    if not isinstance(objective, SeasonObjective):
        raise ValueError("Unknown season objective")
    rival_ids = [r.entry_id for r in rival_states]
    if entry.entry_id in rival_ids or len(set(rival_ids)) != len(rival_ids):
        raise ValueError("Rival states must be distinct entries other than yours")
    if objective is not SeasonObjective.EXPECTED_POINTS and not rival_states:
        raise ValueError("Standing objectives need the rival entries' states")
    if objective is SeasonObjective.SEASON_PAYOUT and season_payout is None:
        raise ValueError("The season payout objective needs a payout configuration")
    if season_payout is not None:
        if season_payout != payout_config(season_payout.participants,
                                          override=season_payout.override,
                                          allow_provisional=allow_provisional,
                                          register_path=register_path):
            raise ValueError("Payout configuration does not match its versioned derivation")
        if season_payout.participants != len(rival_states) + 1:
            raise ValueError("Season payouts need every other participant's state")
    if not set(named_rivals) <= set(rival_ids):
        raise ValueError("Named rivals must be among the rival states")
    context = _context(scenarios, draw, terms, cutoff, entry, calendar, future, params,
                       (_TAG, seed))
    decisions_by_policy = {
        policy: _decide(context, policy, scenarios, draw, objective=event_objective,
                        rivals=rivals, payout=event_payout, limits=limits,
                        allow_provisional=allow_provisional, register_path=register_path)
        for policy in policies
    }

    worlds = params.evaluation_worlds
    remaining = 1 + len(context.evaluation)
    rival_totals = None
    if rival_states:
        banks = {name: np.array([[getattr(r, name)] * worlds for r in rival_states],
                                dtype=np.int64) for name in ("slam", "masters")}
        usage = np.zeros((len(rival_states), worlds, len(context.universe)), dtype=np.int64)
        for k, state in enumerate(rival_states):
            for player, count in state.usage:
                if player in context.universe:
                    usage[k, :, context.universe[player]] = count
        noise = params.rival_choice_noise
        shocks = np.exp(noise * context.rng.standard_normal(
            (len(rival_states), worlds, len(context.now.players))))
        _, now_points, _ = _play(context.now, banks[context.bank_name], usage,
                                 rule=Policy.RATIONED, events_left=context.events_left,
                                 noise=shocks)
        _, later_points, _ = _forward(context, Policy.RATIONED, banks, usage, noise)
        rival_start = np.array([r.season_points + _pending_bonus(r, remaining)
                                for r in rival_states])
        rival_totals = rival_start[:, None] + now_points + later_points

    order = sorted(rival_states, key=lambda r: (-r.season_points, r.entry_id))
    if rival_states and not named_rivals:
        ahead = [r.entry_id for r in order if r.season_points > entry.season_points]
        named_rivals = tuple(ahead[-3:]) if ahead else tuple(r.entry_id for r in order[:3])
    prizes = None
    if season_payout is not None:
        prizes = np.concatenate(([0.0], np.cumsum(np.pad(
            np.array(season_payout.season_prizes_cents, dtype=np.float64),
            (0, max(0, len(rival_states) + 1 - len(season_payout.season_prizes_cents)))))))

    samples: dict[Policy, dict[str, NDArray[np.float64]]] = {}
    for policy, decision in decisions_by_policy.items():
        pairs = decision.recommendation.best.pairs
        now_points, used = _own_current(scenarios, pairs, worlds)
        base = tuple(b - s for b, s in zip(context.bank(), decision.spend))
        own_banks = {
            "slam": np.array([[base if context.bank_name == "slam" else entry.slam] * worlds]),
            "masters": np.array([[base if context.bank_name == "masters" else entry.masters]
                                 * worlds]),
        }
        usage = np.array([[context.usage_vector(u) for u in used]], dtype=np.int64)
        expected, realized, _ = _forward(context, policy, own_banks, usage)
        unused = (own_banks["slam"].sum(axis=-1) + own_banks["masters"].sum(axis=-1))[0]
        own_start = entry.season_points + _pending_bonus(entry, remaining)
        sample = {"points": own_start + now_points + expected[0], "unused": unused.astype(float),
                  "future": expected[0]}
        if rival_totals is not None:
            final = own_start + now_points + realized[0]
            ahead = (rival_totals > final).sum(axis=0)
            tied = (rival_totals == final).sum(axis=0)
            sample["top3"] = (ahead < 3).astype(float)
            sample["first"] = (ahead == 0).astype(float)
            sample["final"] = final
            if prizes is not None:
                sample["payout"] = (prizes[ahead + tied + 1] - prizes[ahead]) / (tied + 1)
        samples[policy] = sample

    key = {SeasonObjective.EXPECTED_POINTS: "points", SeasonObjective.SEASON_PAYOUT: "payout",
           SeasonObjective.P_TOP3: "top3"}[objective]
    best = max(policies, key=lambda p: (float(samples[p][key].mean()), -_PREFERENCE.index(p)))
    materiality = _TOP3_MATERIALITY if objective is SeasonObjective.P_TOP3 else 0.0
    gaps: dict[Policy, tuple[float, float, bool]] = {}
    for policy in policies:
        diff = samples[best][key] - samples[policy][key]
        mean, se = float(diff.mean()), _se(diff)
        gaps[policy] = (mean, se, policy is not best and mean <= max(_TIE_Z * se, materiality))
    tied = [p for p in policies if p is best or gaps[p][2]]
    chosen = min(tied, key=lambda p: (sum(decisions_by_policy[p].spend), _PREFERENCE.index(p)))

    projections = []
    for policy in policies:
        decision, sample = decisions_by_policy[policy], samples[policy]
        rival_gaps = []
        if rival_totals is not None:
            for name in named_rivals:
                k = rival_ids.index(name)
                gap = sample["final"] - rival_totals[k]
                rival_gaps.append(RivalGap(
                    entry_id=name,
                    current_gap=entry.season_points - rival_states[k].season_points,
                    expected_final_gap=float(gap.mean()), final_gap_se=_se(gap),
                    p_finish_ahead=float((gap > 0).mean())))
        event_points = decision.recommendation.best.metrics.expected_points
        projections.append(PolicyProjection(
            policy=policy, recommendation=decision.recommendation, spend=decision.spend,
            preserved=decision.preserved, event_expected_points=event_points,
            future_expected_points=float(sample["future"].mean()),
            season_expected_points=float(sample["points"].mean()),
            season_points_se=_se(sample["points"]),
            expected_unused_tokens=float(sample["unused"].mean()),
            p_season_top3=float(sample["top3"].mean()) if "top3" in sample else None,
            p_season_first=float(sample["first"].mean()) if "first" in sample else None,
            expected_season_payout_cents=(float(sample["payout"].mean())
                                          if "payout" in sample else None),
            season_payout_se_cents=_se(sample["payout"]) if "payout" in sample else None,
            rival_gaps=tuple(rival_gaps), gap_to_best=gaps[policy][0],
            gap_se=gaps[policy][1], tie_with_best=gaps[policy][2],
        ))

    chosen_decision = decisions_by_policy[chosen]
    pairs = chosen_decision.recommendation.best.pairs
    values, _, _ = _structure_now(context, set(chosen_decision.preserved))
    token_costs = _token_costs(context, chosen_decision.spend,
                               [p.primary.player_id for p in pairs], values)
    index = {p: i for i, p in enumerate(scenarios.player_ids)}
    roster = [index[p.primary.player_id] for p in pairs]
    base = tuple(b - s for b, s in zip(context.bank(), chosen_decision.spend))
    slam, masters = (base, entry.masters) if context.bank_name == "slam" else (entry.slam, base)
    use_costs = _use_costs(context, slam, masters, roster, set(chosen_decision.preserved))
    use_costs += chosen_decision.preserved_costs
    tie_rule = ("Policies tie when the paired shortfall is within {:g} standard errors{}; "
                "ties go to the policy spending fewer seeded tokens now.".format(
                    _TIE_Z, " or {:.1%} absolute probability".format(materiality)
                    if materiality else ""))
    return SeasonPlan(
        event_id=terms.event_id, cutoff=cutoff, objective=objective, chosen=chosen,
        projections=tuple(projections), token_costs=tuple(token_costs),
        use_costs=tuple(use_costs), assumptions=PlanAssumptions(
            seed=seed, parameters=params, future_events=tuple(e.event_id for e in context.evaluation),
            future_information_at=tuple(sorted((f.event_id, f.available_at) for f in future)),
            future_model=_FUTURE_MODEL, horizon_model=_HORIZON_MODEL,
            rival_model=_RIVAL_MODEL if rival_states else None, limits=_SEASON_LIMITS,
            tie_rule=tie_rule, rule_register_version=version,
            recommendation_decisions=decisions,
        ),
    )


@dataclass(frozen=True, kw_only=True)
class EventOutcome(Contract):
    """Realized results, revealed only after the deadline."""

    revealed_at: datetime
    points: tuple[tuple[PlayerId, int], ...]
    withdrawn: tuple[PlayerId, ...] = ()
    rival_points: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, eq=False)
class ReplayEvent:
    """Pre-cutoff decision inputs for one event plus its later outcome."""

    terms: EventTerms
    cutoff: datetime
    draw: Draw
    scenarios: ScenarioSet
    scenarios_available_at: datetime
    future: tuple[FutureEvent, ...]
    outcome: EventOutcome


@dataclass(frozen=True, kw_only=True)
class ReplayStep(Contract):
    event_id: str
    cutoff: datetime
    information_at: datetime
    pairs: tuple[Pair, ...]
    spend: tuple[int, ...]
    preserved: tuple[PlayerId, ...]
    planned_expected_points: float
    realized_points: int
    event_rank: int | None
    event_payout_cents: int | None
    slam_after: tuple[int, ...]
    masters_after: tuple[int, ...]


@dataclass(frozen=True, kw_only=True)
class PolicyTrajectory(Contract):
    policy: Policy
    steps: tuple[ReplayStep, ...]
    season_points: int
    submission_bonus: int
    season_rank: int | None
    season_payout_cents: int | None
    event_payout_cents: int | None
    unused_tokens: int
    ledger_history_digest: str


@dataclass(frozen=True, kw_only=True)
class ReplayComparison(Contract):
    baseline: Policy
    trajectories: tuple[PolicyTrajectory, ...]
    season_point_deltas: tuple[tuple[Policy, int], ...]
    payout_deltas_cents: tuple[tuple[Policy, int], ...]
    note: str


def _evidence(record_id: str, at: datetime) -> Provenance:
    return Provenance(source="tennis_pool.season.replay", source_version="1",
                      source_record_id=record_id, observed_at=at, available_at=at,
                      ingested_at=at)


def _realize(pairs: tuple[Pair, ...], outcome: EventOutcome) -> tuple[int, tuple[PlayerId, ...]]:
    points = dict(outcome.points)
    withdrawn = set(outcome.withdrawn)
    total = 0
    activated = []
    for pair in pairs:
        player = pair.primary.player_id
        if player in withdrawn and pair.substitute is not None:
            activated.append(player)
            player = pair.substitute.player_id
        total += 0 if player in withdrawn else points[player]
    return total, tuple(sorted(activated))


def _check_replay(events: Sequence[ReplayEvent], ledger: SeasonLedger) -> set[str]:
    rivals: set[str] | None = None
    previous: ReplayEvent | None = None
    for event in events:
        if event.terms not in ledger.events:
            raise ValueError("Replay events must come from the ledger's calendar")
        if previous is not None and (event.terms.deadline <= previous.terms.deadline
                                     or event.cutoff <= previous.cutoff):
            raise ValueError("Replay events must be in strictly increasing deadline order")
        _check_time(event.scenarios_available_at, event.cutoff, "Scenario inputs")
        outcome = event.outcome
        if outcome.revealed_at < event.terms.deadline:
            raise ValueError("Outcomes must be revealed at or after the deadline")
        players = {s.player_id for s in event.draw.slots if s.player_id is not None}
        if dict(outcome.points).keys() != players or not set(outcome.withdrawn) <= players:
            raise ValueError("Outcomes must score every draw player exactly once")
        if (any(v < 0 for _, v in outcome.points)
                or any(v < 0 for _, v in outcome.rival_points)):
            raise ValueError("Outcome points cannot be negative")
        names = {r for r, _ in outcome.rival_points}
        if len(names) != len(outcome.rival_points) or (rivals is not None and names != rivals):
            raise ValueError("Every event must score the same distinct rivals")
        rivals = names
        previous = event
    return rivals or set()


def replay_season(
    events: Sequence[ReplayEvent],
    *,
    ledger: SeasonLedger,
    entry_id: str,
    seed: int,
    policies: tuple[Policy, ...] = (Policy.GREEDY, Policy.RATIONED, Policy.HORIZON),
    rival_start: Mapping[str, int] | None = None,
    payout: PayoutConfig | None = None,
    limits: SearchLimits | None = None,
    parameters: PlanningParameters | None = None,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> ReplayComparison:
    """Leakage-safe sequential replay; each policy lives off its own ledger.

    ``ledger`` holds the season calendar and any earlier own history. Every
    decision sees only that event's pre-cutoff inputs and the policy's own
    ledger replayed at the cutoff; the outcome is appended afterwards (submission,
    acceptance, activations of withdrawn primaries, audited points). Rival totals
    are ``rival_start`` plus their supplied event points, bonuses included by the
    caller.
    """
    _gate(allow_provisional, register_path)
    params = parameters or PlanningParameters()
    if type(seed) is not int or seed < 0:
        raise ValueError("Replay seed must be a non-negative integer")
    if not events or not policies or len(set(policies)) != len(policies):
        raise ValueError("Replay needs events and distinct policies")
    rivals = _check_replay(events, ledger)
    start = dict(rival_start or {})
    if not set(start) <= rivals:
        raise ValueError("Rival start points must name scored rivals")
    if payout is not None and payout.participants != len(rivals) + 1:
        raise ValueError("Payouts need every other participant's event points")
    trajectories = []
    for policy in policies:
        own = ledger
        steps = []
        for number, event in enumerate(events):
            snapshot = own.replay(event.cutoff)
            entry = next((e for e in snapshot.entries if e.entry_id == entry_id), None)
            if entry is None:
                entry = EntryState(entry_id=entry_id, slam=_FULL_BANKS["slam"],
                                   masters=_FULL_BANKS["masters"], usage=())
            context = _context(event.scenarios, event.draw, event.terms, event.cutoff, entry,
                               ledger.events, event.future, params, (_TAG, seed, number))
            decision = _decide(context, policy, event.scenarios, event.draw,
                               objective=Objective.EXPECTED_POINTS, rivals=None, payout=None,
                               limits=limits, allow_provisional=allow_provisional,
                               register_path=register_path)
            pairs = decision.recommendation.best.pairs
            key = "{}:{}:{}".format(policy.value, event.terms.event_id, entry_id)
            submit = LedgerRecord(
                record_id=key + ":submitted", entry_id=entry_id, event_id=event.terms.event_id,
                effective_at=event.cutoff, evidence=_evidence(key + ":submitted", event.cutoff),
                payload=Submitted(picks=pairs, submitted_at=event.cutoff, excel=True))
            accept = LedgerRecord(
                record_id=key + ":accepted", entry_id=entry_id, event_id=event.terms.event_id,
                effective_at=event.cutoff, evidence=_evidence(key + ":accepted", event.cutoff),
                payload=Accepted(submission_id=submit.record_id,
                                 approved_by="synthetic replay attestation"))
            own = own.append(submit, accept)
            realized, activated = _realize(pairs, event.outcome)
            revealed = event.outcome.revealed_at
            if activated:
                own = own.append(LedgerRecord(
                    record_id=key + ":activated", entry_id=entry_id,
                    event_id=event.terms.event_id, effective_at=revealed,
                    evidence=_evidence(key + ":activated", revealed),
                    payload=ApprovedActivation(
                        acceptance_id=accept.record_id, submission_id=submit.record_id,
                        primary_ids=activated, approved_by="synthetic replay attestation")))
            after = own.replay(revealed + timedelta(microseconds=1))
            state = next(s for s in after.events
                         if (s.entry_id, s.event_id) == (entry_id, event.terms.event_id))
            own = own.append(LedgerRecord(
                record_id=key + ":points", entry_id=entry_id, event_id=event.terms.event_id,
                effective_at=revealed, evidence=_evidence(key + ":points", revealed),
                payload=EventPoints(points=realized, accounting_digest=state.accounting_digest)))
            own_state = next(e for e in after.entries if e.entry_id == entry_id)
            scores = {entry_id: realized, **dict(event.outcome.rival_points)}
            rank = 1 + sum(v > realized for k, v in scores.items() if k != entry_id)
            cash = None
            if payout is not None:
                cash = next(a.payout_cents for a in split_prizes(scores, payout.event_prizes_cents)
                            if a.entry_id == entry_id)
            steps.append(ReplayStep(
                event_id=event.terms.event_id, cutoff=event.cutoff,
                information_at=max([event.scenarios_available_at,
                                    event.draw.provenance.available_at,
                                    event.terms.provenance.available_at]
                                   + [f.available_at for f in event.future]),
                pairs=pairs, spend=decision.spend, preserved=decision.preserved,
                planned_expected_points=decision.recommendation.best.metrics.expected_points,
                realized_points=realized, event_rank=rank if rivals else None,
                event_payout_cents=cash, slam_after=own_state.slam,
                masters_after=own_state.masters))
        final = own.replay(max(e.outcome.revealed_at for e in events) + timedelta(seconds=1))
        mine = next(e for e in final.entries if e.entry_id == entry_id)
        totals = {r: start.get(r, 0) + sum(dict(e.outcome.rival_points)[r] for e in events)
                  for r in rivals}
        totals[entry_id] = mine.season_points
        season_cash = None
        if payout is not None:
            season_cash = next(a.payout_cents for a in split_prizes(
                totals, payout.season_prizes_cents) if a.entry_id == entry_id)
        trajectories.append(PolicyTrajectory(
            policy=policy, steps=tuple(steps), season_points=mine.season_points,
            submission_bonus=mine.submission_bonus,
            season_rank=(1 + sum(v > mine.season_points for k, v in totals.items()
                                 if k != entry_id)) if rivals else None,
            season_payout_cents=season_cash,
            event_payout_cents=(sum(s.event_payout_cents or 0 for s in steps)
                                if payout is not None else None),
            unused_tokens=sum(mine.slam) + sum(mine.masters),
            ledger_history_digest=final.history_digest,
        ))
    baseline = trajectories[0]

    def total_cash(t: PolicyTrajectory) -> int:
        return (t.season_payout_cents or 0) + (t.event_payout_cents or 0)

    return ReplayComparison(
        baseline=baseline.policy, trajectories=tuple(trajectories),
        season_point_deltas=tuple((t.policy, t.season_points - baseline.season_points)
                                  for t in trajectories[1:]),
        payout_deltas_cents=tuple((t.policy, total_cash(t) - total_cash(baseline))
                                  for t in trajectories[1:]) if payout is not None else (),
        note=_REPLAY_NOTE,
    )
