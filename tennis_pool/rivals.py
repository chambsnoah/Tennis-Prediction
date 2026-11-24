"""Deadline-aware rival selections: legitimately known picks plus modelled sheets.

A rival's sheet is one fixed choice for the event; what we do not know is which.
Every known pick carries the time it became legitimately available. An analysis
at ``cutoff`` sees a pick only when it was available strictly before both the
cutoff and the tournament start (exclusive, as in ``ledger.replay``), and the
cutoff must not follow the submission deadline. Rival banks, use counts, pick
history and any acceptance already recorded for this event come from one
``SeasonLedger.replay`` at that same visibility cut.

Unknown slots are sampled per rival: a band structure from the rival's own
history for this bank (smoothed toward the field and toward every legal
structure), then players within each band by a pre-cutoff appeal signal
(current strength, which the field follows more than pick history), repeat-use
affinity and noise, under the remaining Slam or Masters bank and the five-use
cap. Substitutes come from the same band. Shared "world" noise on appeal makes
the field herd together and widens ownership intervals; rivals with no usable
history get broader personal noise and are labelled as such.

All selection randomness comes from children of a tagged ``SeedSequence``,
whose entropy differs from the scenario seed's, and each scenario column picks
its world from its own stream. For a fixed appeal signal, selection draws
therefore never depend on simulated tournament outcomes. The fallback appeal
(scenario mean points) is derived from the scenarios, so it carries no such
guarantee; pass an ``AppealSnapshot`` for it. Fields are bound to
``ScenarioSet.digest``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from itertools import product
import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from tennis_api.models.canonical import Contract, Draw, PlayerId, Provenance
from tennis_pool.ledger import (
    _MASTERS, _SEEDED, _SLAMS, Band, EventTerms, Pair, SeasonLedger,
)
from tennis_pool.optimizer import RivalAssumptions, RivalField, ScenarioSet, _draw_digest, _gate
from tennis_pool.substitutions import _FULL_BANKS, seed_band


_SLOTS = 5
_USE_CAP = 5
_BANDS = (Band.TOP4, Band.TOP8, Band.TOP16, Band.TOP32, Band.UNSEEDED)
# Mixed into every rival seed so its streams never coincide with scenario streams.
_STREAM_TAG = 0x52495641
# Last event of each bank: unspent seeded tokens expire afterwards.
_EXPIRING = {"slam": "us_open", "masters": "paris"}
_MIN_SHARE = 0.0005
_RELEVANT_SHARE = 0.01
_MODEL = (
    "Known pairs (available before the cutoff and the start) are fixed. Each unknown "
    "sheet draws a band structure from the rival's own history for this bank, smoothed "
    "toward the field and every legal structure, then fills bands by Plackett-Luce "
    "sampling on appeal^concentration x (1 + affinity x prior uses) with shared world "
    "noise and per-rival noise (broader without history). Same-band substitutes follow "
    "the rival's smoothed substitute rate. Banks, five-use caps and known picks are "
    "respected; a withdrawn rival primary hands its slot to its substitute. Scenario "
    "columns draw worlds independently of outcomes."
)


class RivalStatus(str, Enum):
    KNOWN = "known"            # all five primaries legitimately known before the cutoff
    PARTIAL = "partial"        # one to four primaries known; the rest modelled
    ESTIMATED = "estimated"    # nothing known; modelled from the rival's accepted history
    NO_HISTORY = "no_history"  # nothing known and no accepted history: broad field prior


@dataclass(frozen=True, kw_only=True)
class KnownPick(Contract):
    """One rival pair, legitimately known from ``provenance.available_at`` onward."""

    entry_id: str
    event_id: str
    pair: Pair
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.event_id not in _SLAMS | _MASTERS or not self.provenance.source_record_id:
            raise ValueError("Known picks need a canonical event and a source record")


@dataclass(frozen=True, kw_only=True)
class AppealSnapshot(Contract):
    """A pre-cutoff strength signal rivals chase, such as market favourites.

    Draw players missing from ``values`` get half the smallest listed value.
    """

    event_id: str
    values: tuple[tuple[PlayerId, float], ...]
    basis: str
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        players = [player for player, _ in self.values]
        if (not self.values or len(set(players)) != len(players)
                or any(not value > 0 for _, value in self.values)):
            raise ValueError("Appeal needs distinct players with positive values")


@dataclass(frozen=True, kw_only=True)
class RivalModelParameters(Contract):
    """Unfitted priors, disclosed with every output; check them with the evaluation."""

    concentration: float = 1.0
    repeat_affinity: float = 0.3
    structure_prior: float = 2.0
    uniform_prior: float = 1.0
    substitute_prior: float = 2.0
    field_noise: float = 0.5
    personal_noise: float = 0.35
    no_history_noise: float = 1.0
    worlds: int = 256
    interval: float = 0.8
    spend_expiring_bank: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if (self.concentration <= 0 or self.repeat_affinity < 0 or self.structure_prior < 0
                or self.uniform_prior <= 0 or self.substitute_prior <= 0
                or min(self.field_noise, self.personal_noise, self.no_history_noise) < 0
                or not 1 <= self.worlds <= 100_000 or not 0 < self.interval < 1):
            raise ValueError("Invalid rival model parameters")


@dataclass(frozen=True, kw_only=True)
class RivalSummary(Contract):
    entry_id: str
    status: RivalStatus
    known_pairs: int
    history_events: int        # accepted sheets of any kind before this event
    structure_events: int      # of which for this event's bank kind
    ledger_state: bool         # False: absent from the ledger; full bank, no uses assumed
    bank: tuple[int, ...]      # remaining seeded bank for this event's kind, before it
    structure_basis: str
    substitute_rate: float
    personal_noise: float
    # Sum of squared primary inclusion probabilities / 5: 1 when every pick is
    # certain, near 0 when picks are spread thinly across the draw.
    pick_certainty: float


@dataclass(frozen=True, kw_only=True)
class PlayerOwnership(Contract):
    """Share of all rivals holding the player as a primary.

    ``known`` counts rivals known to hold the player before the cutoff;
    ``expected`` includes them. ``low``/``high`` bound the share across worlds.
    """

    player_id: PlayerId
    band: Band
    known: int
    expected: float
    low: float
    high: float


@dataclass(frozen=True, kw_only=True)
class RivalReport(Contract):
    event_id: str
    cutoff: datetime
    starts_at: datetime
    visible_before: datetime
    rivals: tuple[RivalSummary, ...]
    ownership: tuple[PlayerOwnership, ...]
    known_picks_used: int
    excluded_after_cutoff: int
    excluded_at_or_after_start: int
    appeal_basis: str
    appeal_missing: int
    parameters: RivalModelParameters
    seed: int
    ledger_history_digest: str
    scenario_digest: str | None
    model: str
    rule_register_version: str

    def describe(self) -> tuple[str, ...]:
        """Plain lines that keep known, modelled and no-history rivals apart."""
        lines = []
        for rival in self.rivals:
            if rival.status is RivalStatus.KNOWN:
                detail = "all five primaries known before the cutoff"
            elif rival.status is RivalStatus.NO_HISTORY:
                detail = "{} known; rest from {}, broad noise {:g}".format(
                    rival.known_pairs, rival.structure_basis, rival.personal_noise)
            else:
                detail = "{} known; rest from {}".format(rival.known_pairs, rival.structure_basis)
            if rival.status is not RivalStatus.KNOWN:
                detail += "; pick certainty {:.2f}".format(rival.pick_certainty)
            if not rival.ledger_state:
                detail += "; not in ledger, full bank assumed"
            lines.append("{} [{}] {}".format(rival.entry_id, rival.status.value.upper(), detail))
        width = "{:.0%}".format(self.parameters.interval)
        for player in self.ownership:
            lines.append("{} [{}] known {} | projected {:.0%} ({} interval {:.0%}-{:.0%})".format(
                player.player_id, player.band.value, player.known, player.expected, width,
                player.low, player.high))
        return tuple(lines)


@dataclass(frozen=True, eq=False)
class RivalModel:
    """A rival field for the optimizer plus the report and the sampled sheets.

    ``primaries``/``substitutes`` are rivals x worlds x slots player indexes in
    scenario order (``len(player_ids)`` means no substitute); scenario column
    ``j`` uses world ``world_of_scenario[j]``.
    """

    field: RivalField
    report: RivalReport
    player_ids: tuple[PlayerId, ...]
    primaries: NDArray[np.int64]
    substitutes: NDArray[np.int64]
    world_of_scenario: NDArray[np.int64]


@dataclass
class _Rival:
    entry_id: str
    bank: list[int]
    usage: dict[PlayerId, int]
    ledger_state: bool
    known: list[Pair]
    history: list[tuple[int, ...]]
    events: int = 0
    pairs_seen: int = 0
    subs_seen: int = 0


@dataclass
class _Setup:
    version: str
    event_id: str
    kind: str
    cutoff: datetime
    starts_at: datetime
    visible: datetime
    players: tuple[PlayerId, ...]
    bands: list[Band]
    appeal: NDArray[np.float64]
    appeal_basis: str
    appeal_missing: int
    rivals: list[_Rival]
    used_known: int
    after_cutoff: int
    after_start: int
    history_digest: str


@dataclass
class _Draws:
    primaries: NDArray[np.int64]
    substitutes: NDArray[np.int64]
    known: list[set[int]]
    summaries: list[RivalSummary]


def _aware(value: object, name: str) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() is None):
        raise ValueError("{} requires a timezone-aware datetime".format(name))
    return value


def _seed(seed: object) -> int:
    if type(seed) is not int or seed < 0:
        raise ValueError("Rival seed must be a non-negative integer")
    return seed


def _structure(bands: Iterable[Band]) -> tuple[int, ...]:
    counts = Counter(bands)
    return tuple(counts.get(band, 0) for band in _BANDS)


def _prepare(
    ledger: SeasonLedger, draw: Draw, terms: EventTerms, *, starts_at: datetime,
    cutoff: datetime, rival_ids: tuple[str, ...], known_picks: Sequence[KnownPick],
    appeal: AppealSnapshot | None, order: tuple[PlayerId, ...] | None,
    default_appeal: NDArray[np.float64] | None, allow_provisional: bool,
    register_path: str | Path | None,
) -> _Setup:
    version, _ = _gate(allow_provisional, register_path)
    _aware(cutoff, "cutoff")
    _aware(starts_at, "starts_at")
    if not isinstance(ledger, SeasonLedger) or terms not in ledger.events:
        raise ValueError("Event terms must come from the season ledger")
    if cutoff > terms.deadline:
        raise ValueError("Rival selection is a before-deadline analysis; the cutoff "
                         "must not follow the submission deadline")
    visible = min(cutoff, starts_at)
    if terms.provenance.available_at >= visible or draw.provenance.available_at >= visible:
        raise ValueError("Draw and event terms must be available before the cutoff and start")
    if (type(rival_ids) is not tuple or not rival_ids or len(set(rival_ids)) != len(rival_ids)
            or any(not isinstance(r, str) or not r.strip() for r in rival_ids)):
        raise ValueError("Rival IDs must be a non-empty tuple of distinct entry IDs")
    event_id = terms.event_id
    kind = "slam" if event_id in _SLAMS else "masters"
    seeds = {slot.player_id: slot.seed for slot in draw.slots if slot.player_id is not None}
    players = tuple(seeds) if order is None else order
    if len(players) != len(seeds) or set(players) != set(seeds):
        raise ValueError("Players must match the released draw")
    bands = [seed_band(seeds[p]) for p in players]
    band_of = dict(zip(players, bands))

    snapshot = ledger.replay(visible)
    entries = {entry.entry_id: entry for entry in snapshot.entries}
    same_kind = _SLAMS if kind == "slam" else _MASTERS
    rivals: list[_Rival] = []
    for entry_id in rival_ids:
        entry = entries.get(entry_id)
        if entry is None:
            bank, usage = list(_FULL_BANKS[kind]), {}
        else:
            bank = list(entry.slam if kind == "slam" else entry.masters)
            usage = dict(entry.usage)
        rival = _Rival(entry_id=entry_id, bank=bank, usage=usage,
                       ledger_state=entry is not None, known=[], history=[])
        for state in snapshot.events:
            if state.entry_id != entry_id:
                continue
            if state.event_id == event_id:
                # Accepted before the visible cut: legitimately known. Undo its
                # debits so the bank describes the state before this event.
                for selection in state.selections:
                    usage[selection.player_id] -= 1
                    if selection.band is not Band.UNSEEDED:
                        bank[_SEEDED.index(selection.band)] += 1
                rival.known.extend(state.accepted_picks)
            elif len(state.accepted_picks) == _SLOTS:
                # Band structures depend on the bank kind; substitute habit does not.
                if state.event_id in same_kind:
                    rival.history.append(
                        _structure(p.primary.band for p in state.accepted_picks))
                rival.events += 1
                rival.pairs_seen += _SLOTS
                rival.subs_seen += sum(p.substitute is not None for p in state.accepted_picks)
        rivals.append(rival)

    by_id = {rival.entry_id: rival for rival in rivals}
    used = after_cutoff = after_start = 0
    for pick in known_picks:
        if not isinstance(pick, KnownPick):
            raise ValueError("Known picks must be KnownPick records")
        if pick.event_id != event_id:
            continue
        if pick.entry_id not in by_id:
            raise ValueError("Known pick for an entry outside the rival list")
        available = pick.provenance.available_at
        if available >= starts_at:
            after_start += 1
            continue
        if available >= cutoff:
            after_cutoff += 1
            continue
        rival = by_id[pick.entry_id]
        if pick.pair not in rival.known:
            rival.known.append(pick.pair)
        used += 1

    for rival in rivals:
        primaries = [pair.primary for pair in rival.known]
        selections = primaries + [p.substitute for p in rival.known if p.substitute is not None]
        ids = [s.player_id for s in selections]
        if len(primaries) > _SLOTS or len(set(ids)) != len(ids):
            raise ValueError("Known picks for a rival must be at most five distinct, "
                             "non-overlapping pairs")
        for selection in selections:
            if band_of.get(selection.player_id) is not selection.band:
                raise ValueError("Known picks must name draw players in their seed band")
            if rival.usage.get(selection.player_id, 0) >= _USE_CAP:
                raise ValueError("Known pick exceeds the rival's five-use cap")
        if any(p.substitute is not None and p.substitute.band is not p.primary.band
               for p in rival.known):
            raise ValueError("Known substitutes must share their primary's band")
        counts = Counter(s.band for s in primaries)
        if any(counts[band] > rival.bank[i] for i, band in enumerate(_SEEDED)):
            raise ValueError("Known picks exceed the rival's remaining bank")

    if appeal is None:
        if default_appeal is None:
            raise ValueError("An appeal snapshot is required")
        values, basis, missing = default_appeal, (
            "scenario mean pool points + 1 (ex-ante means, not per-scenario outcomes)"), 0
    else:
        if not isinstance(appeal, AppealSnapshot) or appeal.event_id != event_id:
            raise ValueError("Appeal must be an AppealSnapshot for this event")
        if appeal.provenance.available_at >= visible:
            raise ValueError("Appeal evidence must be available before the cutoff and start")
        lookup = dict(appeal.values)
        if set(lookup) - set(players):
            raise ValueError("Appeal names players outside the draw")
        floor = min(lookup.values()) / 2
        values = np.array([lookup.get(p, floor) for p in players], dtype=np.float64)
        basis, missing = appeal.basis, sum(p not in lookup for p in players)
    return _Setup(
        version=version, event_id=event_id, kind=kind, cutoff=cutoff, starts_at=starts_at,
        visible=visible, players=players, bands=bands, appeal=values, appeal_basis=basis,
        appeal_missing=missing, rivals=rivals, used_known=used, after_cutoff=after_cutoff,
        after_start=after_start, history_digest=snapshot.history_digest,
    )


def _legal_structures(bank: Sequence[int], known: Counter[Band],
                      available: dict[Band, int], expiring: bool) -> list[tuple[int, ...]]:
    ranges = []
    for i, band in enumerate(_BANDS):
        upper = min(_SLOTS, known[band] + available[band])
        if band is not Band.UNSEEDED:
            upper = min(upper, bank[i])
        ranges.append(range(known[band], upper + 1))
    structures = [s for s in product(*ranges) if sum(s) == _SLOTS]
    if expiring and structures:
        spend = max(sum(s[:-1]) for s in structures)
        structures = [s for s in structures if sum(s[:-1]) == spend]
    return structures


def _sample(setup: _Setup, params: RivalModelParameters,
            sequence: np.random.SeedSequence) -> _Draws:
    count, worlds = len(setup.players), params.worlds
    world_seq, rival_seq = sequence.spawn(2)
    shared = np.random.default_rng(world_seq).normal(0.0, params.field_noise, (worlds, count))
    index = {player: i for i, player in enumerate(setup.players)}
    members = {band: np.array([i for i in range(count) if setup.bands[i] is band], dtype=np.int64)
               for band in _BANDS}
    field = Counter(s for rival in setup.rivals for s in rival.history)
    field_total = sum(field.values())
    pairs = sum(rival.pairs_seen for rival in setup.rivals)
    field_rate = sum(rival.subs_seen for rival in setup.rivals) / pairs if pairs else 0.5
    log_appeal = params.concentration * np.log(setup.appeal)
    expiring = params.spend_expiring_bank and setup.event_id == _EXPIRING[setup.kind]
    rival_count = len(setup.rivals)
    primaries = np.empty((rival_count, worlds, _SLOTS), dtype=np.int64)
    substitutes = np.full((rival_count, worlds, _SLOTS), count, dtype=np.int64)
    known_sets: list[set[int]] = []
    summaries: list[RivalSummary] = []
    for r, (rival, child) in enumerate(zip(setup.rivals, rival_seq.spawn(rival_count))):
        known = len(rival.known)
        for slot, pair in enumerate(rival.known):
            primaries[r, :, slot] = index[pair.primary.player_id]
            if pair.substitute is not None:
                substitutes[r, :, slot] = index[pair.substitute.player_id]
        known_sets.append({index[p.primary.player_id] for p in rival.known})
        if known == _SLOTS:
            summaries.append(RivalSummary(
                entry_id=rival.entry_id, status=RivalStatus.KNOWN, known_pairs=known,
                history_events=rival.events, structure_events=len(rival.history),
                ledger_state=rival.ledger_state, bank=tuple(rival.bank),
                structure_basis="known before the cutoff",
                substitute_rate=sum(p.substitute is not None for p in rival.known) / _SLOTS,
                personal_noise=0.0, pick_certainty=1.0))
            continue
        rng = np.random.default_rng(child)
        usage = np.array([rival.usage.get(p, 0) for p in setup.players], dtype=np.float64)
        eligible = usage < _USE_CAP
        for pair in rival.known:
            eligible[index[pair.primary.player_id]] = False
            if pair.substitute is not None:
                eligible[index[pair.substitute.player_id]] = False
        pools = {band: ids[eligible[ids]] for band, ids in members.items()}
        known_counts = Counter(p.primary.band for p in rival.known)
        structures = _legal_structures(
            rival.bank, known_counts, {band: len(ids) for band, ids in pools.items()}, expiring)
        if not structures:
            raise ValueError("No legal sheet for rival {}: bank, use caps and known picks "
                             "leave too few players".format(rival.entry_id))
        own = Counter(rival.history)
        weights = np.array([
            own[s] + params.structure_prior * (field[s] / field_total if field_total else 0.0)
            + params.uniform_prior / len(structures) for s in structures], dtype=np.float64)
        if rival.history:
            basis = "own {} history ({} events) smoothed toward the field".format(
                setup.kind, len(rival.history))
        elif field_total:
            basis = "field history ({} sheets) and legal structures".format(field_total)
        else:
            basis = "uniform over legal structures"
        rate = ((rival.subs_seen + params.substitute_prior * field_rate)
                / (rival.pairs_seen + params.substitute_prior))
        sigma = params.personal_noise if rival.events else params.no_history_noise
        choice = rng.choice(len(structures), size=worlds, p=weights / weights.sum())
        keys = (log_appeal + np.log1p(params.repeat_affinity * usage) + shared
                + rng.normal(0.0, sigma, (worlds, count)) + rng.gumbel(size=(worlds, count)))
        insure = rng.random((worlds, _SLOTS)) < rate
        for world in range(worlds):
            slot = known
            for b, band in enumerate(_BANDS):
                need = structures[choice[world]][b] - known_counts[band]
                if need == 0:
                    continue
                pool = pools[band]
                ranked = pool[np.argsort(-keys[world, pool], kind="stable")]
                spare = list(ranked[need:])
                for player in ranked[:need]:
                    primaries[r, world, slot] = player
                    if insure[world, slot] and spare:
                        substitutes[r, world, slot] = spare.pop(0)
                    slot += 1
        inclusion = np.bincount(primaries[r].ravel(), minlength=count) / worlds
        summaries.append(RivalSummary(
            entry_id=rival.entry_id,
            status=(RivalStatus.PARTIAL if known else RivalStatus.ESTIMATED if rival.events
                    else RivalStatus.NO_HISTORY),
            known_pairs=known, history_events=rival.events, structure_events=len(rival.history),
            ledger_state=rival.ledger_state, bank=tuple(rival.bank), structure_basis=basis,
            substitute_rate=float(rate), personal_noise=float(sigma),
            pick_certainty=float(np.square(inclusion).sum() / _SLOTS)))
    return _Draws(primaries=primaries, substitutes=substitutes, known=known_sets,
                  summaries=summaries)


def _world_counts(primaries: NDArray[np.int64], count: int) -> NDArray[np.float64]:
    """Rivals holding each player per world: worlds x players."""
    rivals, worlds, slots = primaries.shape
    rows = np.broadcast_to(np.arange(worlds)[None, :, None], primaries.shape)
    counts = np.zeros((worlds, count), dtype=np.float64)
    np.add.at(counts, (rows.ravel(), primaries.ravel()), 1.0)
    return counts


def _report(setup: _Setup, draws: _Draws, params: RivalModelParameters, seed: int,
            scenario_digest: str | None) -> RivalReport:
    count = len(setup.players)
    shares = _world_counts(draws.primaries, count) / len(setup.rivals)
    tail = (1 - params.interval) / 2
    expected = shares.mean(axis=0)
    low, high = np.quantile(shares, [tail, 1 - tail], axis=0)
    known = np.zeros(count, dtype=np.int64)
    for players in draws.known:
        for player in players:
            known[player] += 1
    order = sorted(range(count), key=lambda i: (_BANDS.index(setup.bands[i]), -expected[i],
                                                setup.players[i]))
    ownership = tuple(PlayerOwnership(
        player_id=setup.players[i], band=setup.bands[i], known=int(known[i]),
        expected=float(expected[i]), low=float(low[i]), high=float(high[i]),
    ) for i in order if expected[i] >= _MIN_SHARE or known[i])
    return RivalReport(
        event_id=setup.event_id, cutoff=setup.cutoff, starts_at=setup.starts_at,
        visible_before=setup.visible, rivals=tuple(draws.summaries), ownership=ownership,
        known_picks_used=setup.used_known, excluded_after_cutoff=setup.after_cutoff,
        excluded_at_or_after_start=setup.after_start, appeal_basis=setup.appeal_basis,
        appeal_missing=setup.appeal_missing, parameters=params, seed=seed,
        ledger_history_digest=setup.history_digest, scenario_digest=scenario_digest,
        model=_MODEL, rule_register_version=setup.version,
    )


def project_ownership(
    ledger: SeasonLedger,
    draw: Draw,
    terms: EventTerms,
    *,
    starts_at: datetime,
    cutoff: datetime,
    rival_ids: tuple[str, ...],
    appeal: AppealSnapshot,
    seed: int,
    known_picks: Sequence[KnownPick] = (),
    parameters: RivalModelParameters | None = None,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> RivalReport:
    """Projected rival ownership as of ``cutoff``, without tournament scenarios."""
    params = parameters or RivalModelParameters()
    setup = _prepare(ledger, draw, terms, starts_at=starts_at, cutoff=cutoff,
                     rival_ids=rival_ids, known_picks=known_picks, appeal=appeal, order=None,
                     default_appeal=None, allow_provisional=allow_provisional,
                     register_path=register_path)
    first, _ = np.random.SeedSequence([_STREAM_TAG, _seed(seed)]).spawn(2)
    return _report(setup, _sample(setup, params, first), params, seed, None)


def model_rival_field(
    scenarios: ScenarioSet,
    ledger: SeasonLedger,
    draw: Draw,
    terms: EventTerms,
    *,
    starts_at: datetime,
    cutoff: datetime,
    rival_ids: tuple[str, ...],
    seed: int,
    known_picks: Sequence[KnownPick] = (),
    appeal: AppealSnapshot | None = None,
    parameters: RivalModelParameters | None = None,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> RivalModel:
    """Score modelled rival sheets on the exact scenario columns for the optimizer.

    Without ``appeal``, rivals chase the scenarios' mean points: an ex-ante summary
    shared by every column, never the outcome of the column being scored. That
    summary changes with the scenarios, so sheets stay fixed across scenario sets
    only when an explicit ``AppealSnapshot`` is given.
    """
    params = parameters or RivalModelParameters()
    seeds = {slot.player_id: slot.seed for slot in draw.slots if slot.player_id is not None}
    if (seeds.keys() != set(scenarios.player_ids)
            or any(seeds[p] != s for p, s in zip(scenarios.player_ids, scenarios.seeds))):
        raise ValueError("Scenario players and seeds must match the released draw")
    if (scenarios.assumptions.draw_digest is not None
            and scenarios.assumptions.draw_digest != _draw_digest(draw)):
        raise ValueError("Scenarios were simulated on a different draw")
    default = scenarios.points.mean(axis=1).astype(np.float64) + 1.0
    setup = _prepare(ledger, draw, terms, starts_at=starts_at, cutoff=cutoff,
                     rival_ids=rival_ids, known_picks=known_picks, appeal=appeal,
                     order=scenarios.player_ids, default_appeal=default,
                     allow_provisional=allow_provisional, register_path=register_path)
    sheets, assignment = np.random.SeedSequence([_STREAM_TAG, _seed(seed)]).spawn(2)
    draws = _sample(setup, params, sheets)
    runs = scenarios.simulations
    world = np.random.default_rng(assignment).integers(params.worlds, size=runs)
    plays = np.vstack((scenarios.points, np.zeros((1, runs), dtype=np.int64)))
    out = np.vstack((scenarios.withdrawn.astype(np.int64), np.zeros((1, runs), dtype=np.int64)))
    columns = np.arange(runs)[:, None]
    scores = np.empty((len(setup.rivals), runs), dtype=np.int64)
    for r in range(len(setup.rivals)):
        chosen, cover = draws.primaries[r][world], draws.substitutes[r][world]
        scores[r] = (plays[chosen, columns]
                     + out[chosen, columns] * plays[cover, columns]).sum(axis=1)
    report = _report(setup, draws, params, seed, scenarios.digest)
    field = RivalField(scores=scores, assumptions=RivalAssumptions(
        source="tennis_pool.rivals.model_rival_field", rivals=len(setup.rivals), seed=seed,
        model=_MODEL, ownership=tuple(sorted(
            (p.player_id, p.expected) for p in report.ownership if p.expected > 0)),
        scenario_digest=scenarios.digest,
    ))
    for array in (draws.primaries, draws.substitutes, world):
        array.flags.writeable = False
    return RivalModel(field=field, report=report, player_ids=setup.players,
                      primaries=draws.primaries, substitutes=draws.substitutes,
                      world_of_scenario=world)


@dataclass(frozen=True, kw_only=True)
class OwnershipCase(Contract):
    """One past event: projected at ``cutoff``, scored on picks seen by ``outcome_cutoff``."""

    draw: Draw
    terms: EventTerms
    starts_at: datetime
    cutoff: datetime
    outcome_cutoff: datetime
    appeal: AppealSnapshot

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.outcome_cutoff <= max(self.terms.deadline, self.cutoff):
            raise ValueError("Outcomes must be read after the deadline and the cutoff")


@dataclass(frozen=True, kw_only=True)
class ReliabilityBin(Contract):
    lower: float
    upper: float
    forecasts: int
    mean_forecast: float | None
    observed_rate: float | None


@dataclass(frozen=True, kw_only=True)
class EventOwnershipScore(Contract):
    event_id: str
    cutoff: datetime
    rivals: int
    known_rivals: int
    scored_rivals: int
    unscored_rivals: int
    known_pick_mismatches: int
    forecasts: int
    brier: float | None
    ownership_mae: float | None
    ownership_sse: float | None
    interval_coverage: float | None
    band_leaders: int
    band_leader_hits: int


@dataclass(frozen=True, kw_only=True)
class OwnershipEvaluation(Contract):
    scope: str
    interval: float
    events: tuple[EventOwnershipScore, ...]
    forecasts: int
    brier: float | None
    reliability: tuple[ReliabilityBin, ...]
    ownership_mae: float | None
    ownership_rmse: float | None
    interval_coverage: float | None
    band_leaders: int
    band_leader_hits: int
    parameters: RivalModelParameters
    seed: int


_SCOPE = (
    "Ownership only: rival-level primary inclusion probabilities and field ownership "
    "shares projected at each cutoff, scored against primaries accepted for the event. "
    "Rivals fully known before the cutoff and known pairs are excluded from scoring. "
    "No match results, scenarios or player-performance quality enter these metrics; "
    "match-prediction quality must be evaluated and reported separately."
)


def _mean(values: Sequence[float]) -> float | None:
    return float(np.mean(values)) if values else None


def evaluate_ownership(
    ledger: SeasonLedger,
    cases: Sequence[OwnershipCase],
    *,
    rival_ids: tuple[str, ...],
    seed: int,
    known_picks: Sequence[KnownPick] = (),
    parameters: RivalModelParameters | None = None,
    bins: int = 10,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> OwnershipEvaluation:
    """Walk-forward ownership calibration and error with exclusive time cutoffs.

    Each projection replays the ledger and filters known picks at its own cutoff,
    so it cannot see the accepted sheets it is scored on. Outcomes are the
    accepted primaries replayed at ``outcome_cutoff``; rivals without an accepted
    sheet are counted as unscored.
    """
    params = parameters or RivalModelParameters()
    _seed(seed)
    if type(bins) is not int or bins < 1:
        raise ValueError("Reliability bins must be a positive integer")
    if not cases or any(not isinstance(case, OwnershipCase) for case in cases):
        raise ValueError("Evaluation needs OwnershipCase records")
    tail = (1 - params.interval) / 2
    edges = np.linspace(0.0, 1.0, bins + 1)
    probabilities: list[float] = []
    outcomes: list[float] = []
    errors: list[float] = []
    covered: list[bool] = []
    events: list[EventOwnershipScore] = []
    leaders = leader_hits = 0
    for number, case in enumerate(sorted(cases, key=lambda c: (c.cutoff, c.terms.event_id))):
        setup = _prepare(ledger, case.draw, case.terms, starts_at=case.starts_at,
                         cutoff=case.cutoff, rival_ids=rival_ids, known_picks=known_picks,
                         appeal=case.appeal, order=None, default_appeal=None,
                         allow_provisional=allow_provisional, register_path=register_path)
        draws = _sample(setup, params, np.random.SeedSequence([_STREAM_TAG, seed, number]))
        index = {player: i for i, player in enumerate(setup.players)}
        after = ledger.replay(case.outcome_cutoff)
        actual: dict[str, set[int]] = {}
        for state in after.events:
            if (state.entry_id not in rival_ids or state.event_id != setup.event_id
                    or len(state.accepted_picks) != _SLOTS):
                continue
            if any(p.primary.player_id not in index for p in state.accepted_picks):
                raise ValueError("Accepted rival picks name players outside the case draw")
            actual[state.entry_id] = {index[p.primary.player_id] for p in state.accepted_picks}
        count = len(setup.players)
        worlds = params.worlds
        forecast_share = np.zeros(count)
        actual_share = np.zeros(count)
        world_share = np.zeros((worlds, count))
        known_rivals = unscored = mismatches = scored = 0
        event_probabilities: list[float] = []
        event_outcomes: list[float] = []
        for r, summary in enumerate(draws.summaries):
            if summary.status is RivalStatus.KNOWN:
                known_rivals += 1
                mismatches += len(draws.known[r] - actual.get(summary.entry_id, draws.known[r]))
                continue
            sheet = actual.get(summary.entry_id)
            if sheet is None:
                unscored += 1
                continue
            scored += 1
            known = draws.known[r]
            mismatches += len(known - sheet)
            mask = np.ones(count, dtype=bool)
            mask[list(known)] = False
            held = np.zeros((worlds, count))
            np.put_along_axis(held, draws.primaries[r], 1.0, axis=1)
            held[:, ~mask] = 0.0
            inclusion = held.mean(axis=0)
            truth = np.zeros(count)
            truth[list(sheet - known)] = 1.0
            event_probabilities.extend(inclusion[mask].tolist())
            event_outcomes.extend(truth[mask].tolist())
            forecast_share += inclusion
            actual_share += truth
            world_share += held
        event_errors: list[float] = []
        event_covered: list[bool] = []
        hits = bands_scored = 0
        if scored:
            forecast_share /= scored
            actual_share /= scored
            world_share /= scored
            low, high = np.quantile(world_share, [tail, 1 - tail], axis=0)
            relevant = (forecast_share >= _RELEVANT_SHARE) | (actual_share > 0)
            event_errors = np.abs(forecast_share - actual_share)[relevant].tolist()
            event_covered = ((low <= actual_share + 1e-12)
                             & (actual_share <= high + 1e-12))[relevant].tolist()
            for band in _BANDS:
                ids = np.array([i for i in range(count) if setup.bands[i] is band], dtype=np.int64)
                if not len(ids) or actual_share[ids].max() <= 0:
                    continue
                bands_scored += 1
                top = ids[actual_share[ids] == actual_share[ids].max()]
                hits += int(ids[int(np.argmax(forecast_share[ids]))] in top)
        brier = [(p - o) ** 2 for p, o in zip(event_probabilities, event_outcomes)]
        events.append(EventOwnershipScore(
            event_id=setup.event_id, cutoff=case.cutoff, rivals=len(draws.summaries),
            known_rivals=known_rivals, scored_rivals=scored, unscored_rivals=unscored,
            known_pick_mismatches=mismatches, forecasts=len(event_probabilities),
            brier=_mean(brier), ownership_mae=_mean(event_errors),
            ownership_sse=float(((forecast_share - actual_share) ** 2).sum()) if scored else None,
            interval_coverage=_mean([float(c) for c in event_covered]),
            band_leaders=bands_scored, band_leader_hits=hits,
        ))
        probabilities.extend(event_probabilities)
        outcomes.extend(event_outcomes)
        errors.extend(event_errors)
        covered.extend(event_covered)
        leaders += bands_scored
        leader_hits += hits
    forecast = np.array(probabilities)
    observed = np.array(outcomes)
    which = np.clip(np.searchsorted(edges, forecast, side="right") - 1, 0, bins - 1)
    reliability = tuple(ReliabilityBin(
        lower=float(edges[b]), upper=float(edges[b + 1]), forecasts=int((which == b).sum()),
        mean_forecast=_mean(forecast[which == b].tolist()),
        observed_rate=_mean(observed[which == b].tolist()),
    ) for b in range(bins))
    return OwnershipEvaluation(
        scope=_SCOPE, interval=params.interval, events=tuple(events), forecasts=len(forecast),
        brier=_mean(((forecast - observed) ** 2).tolist()), reliability=reliability,
        ownership_mae=_mean(errors),
        ownership_rmse=None if not errors else math.sqrt(float(np.mean(np.square(errors)))),
        interval_coverage=_mean([float(c) for c in covered]),
        band_leaders=leaders, band_leader_hits=leader_hits, parameters=params, seed=seed,
    )
