"""Event and season prize money from explicit, versioned payout configuration.

Printed 2026 schedules exist only for 40, 60 and 80 participants; any other
count, or any commissioner adjustment (rule 14 ***), must be supplied as an
explicit `ScheduleOverride`. Season prizes refund the top five stakes, add the
optional sixth prize, and split the residual 57.5/27.5/10/5 percent in cents by
largest remainders, so the page 7 examples are approximations, not targets.
Tied entries share the prizes of every position they occupy, including unpaid
positions; leftover cents go to the lowest stable anonymized entry IDs.
Random-assigned entries are excluded from event prizes but keep season points.
Approval of an override remains a caller attestation, not commissioner evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable, Mapping

from tennis_api.models.canonical import Contract
from tennis_pool.ledger import _MASTERS, _SLAMS, LedgerSnapshot
from tennis_pool.rules import DEPENDENCIES, require_resolved


_REGISTER_VERSION = "2026-provisional-2"
# Digest of the implemented payout decision text; changes need review.
_DECISION_DIGEST = "09d33259ffe95b31e1384736aa1b0295a57d5c8a59e38789ad42d8ee45a0b9f2"
_STAKE_CENTS = 5000
_EVENT_COUNT = 13
_REFUND_PLACES = 5
_RESIDUAL_SHARES_BP = (5750, 2750, 1000, 500)
# Printed rule 14/15 schedules (page 7): event prizes and the sixth-place prize.
_PRINTED: dict[int, tuple[tuple[int, ...], int]] = {
    40: ((3500, 1500, 500), 0),
    60: ((4500, 2500, 1000), 2500),
    80: ((7000, 3500, 2000), 2500),
}
_EVENTS = frozenset(_SLAMS | _MASTERS)


@dataclass(frozen=True, kw_only=True)
class ScheduleOverride(Contract):
    """A commissioner-announced schedule; approval is the caller's attestation."""

    version: str
    participants: int
    event_prizes_cents: tuple[int, ...]
    sixth_prize_cents: int
    approved_by: str
    source: str
    announced_at: datetime


@dataclass(frozen=True, kw_only=True)
class PayoutConfig(Contract):
    config_version: str
    participants: int
    stake_cents: int
    event_count: int
    event_prizes_cents: tuple[int, ...]
    residual_cents: int
    season_prizes_cents: tuple[int, ...]
    override: ScheduleOverride | None
    rule_register_version: str
    rules_source_sha256: str
    payout_decisions: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, kw_only=True)
class Award(Contract):
    entry_id: str
    points: int | float
    position: int
    tied_with: int
    payout_cents: int


@dataclass(frozen=True, kw_only=True)
class PayoutTable(Contract):
    scope: str
    awards: tuple[Award, ...]
    excluded: tuple[str, ...]
    config_version: str
    rule_register_version: str
    source_history_digest: str
    input_digest: str


@dataclass(frozen=True, kw_only=True)
class Outlook(Contract):
    """Simulated prospects; payout is reported apart from points and top three."""

    entry_id: str
    scope: str
    simulations: int
    expected_points: float
    p_top3: float
    expected_payout_cents: float
    config_version: str


def _check_points(points: object) -> int | float:
    if (type(points) not in (int, float)
            or (isinstance(points, float) and not math.isfinite(points))):
        raise ValueError("Entry points must be finite numbers")
    assert isinstance(points, (int, float))
    return points


def _season_prizes(participants: int, event: tuple[int, ...], sixth: int) -> tuple[int, int, tuple[int, ...]]:
    if not event:
        raise ValueError("Event schedule needs at least one prize position")
    if any(type(p) is not int or p < 0 for p in event + (sixth,)):
        raise ValueError("Prizes must be non-negative whole cents")
    if any(a < b for a, b in zip(event, event[1:])):
        raise ValueError("Event prizes must be non-increasing by position")
    if participants < _REFUND_PLACES:
        raise ValueError("Schedule needs at least five season participants to refund")
    if sixth and participants < _REFUND_PLACES + 1:
        raise ValueError("A sixth prize needs a sixth participant")
    if any(event[participants:]):
        raise ValueError("Event prizes reach positions beyond the participant count")
    residual = (participants * _STAKE_CENTS - _EVENT_COUNT * sum(event)
                - _REFUND_PLACES * _STAKE_CENTS - sixth)
    if residual < 0:
        raise ValueError("Underfunded prize schedule")
    exact = [residual * share for share in _RESIDUAL_SHARES_BP]
    base = [value // 10_000 for value in exact]
    order = sorted(range(len(exact)), key=lambda i: (-(exact[i] % 10_000), i))
    for index in order[:residual - sum(base)]:
        base[index] += 1
    season = tuple(_STAKE_CENTS + share for share in base) + (_STAKE_CENTS, sixth)
    return residual, sum(event), season


def payout_config(
    participants: int,
    *,
    override: ScheduleOverride | None = None,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> PayoutConfig:
    """Return the printed or explicitly overridden schedule for a participant count."""
    if type(allow_provisional) is not bool:
        raise ValueError("Provisional payouts require an explicit boolean opt-in")
    register = require_resolved("payout", register_path, allow_provisional=allow_provisional)
    decisions = {key: register["decisions"][key]["decision"] for key in DEPENDENCIES["payout"]}
    digest = hashlib.sha256(json.dumps(decisions, sort_keys=True).encode()).hexdigest()
    if register["register_version"] != _REGISTER_VERSION or digest != _DECISION_DIGEST:
        raise ValueError("Unsupported payout rule version; implementation review required")
    if type(participants) is not int:
        raise ValueError("Participant count must be an integer")
    if override is not None:
        if override.participants != participants:
            raise ValueError("Override participant count does not match")
        event, sixth = override.event_prizes_cents, override.sixth_prize_cents
        version = "override:" + override.version
    elif participants in _PRINTED:
        event, sixth = _PRINTED[participants]
        version = "2026-printed-{}".format(participants)
    else:
        raise ValueError("No printed schedule for {} participants; an explicit configured "
                         "schedule is required".format(participants))
    residual, _, season = _season_prizes(participants, event, sixth)
    return PayoutConfig(
        config_version=version, participants=participants, stake_cents=_STAKE_CENTS,
        event_count=_EVENT_COUNT, event_prizes_cents=event, residual_cents=residual,
        season_prizes_cents=season, override=override,
        rule_register_version=register["register_version"],
        rules_source_sha256=register["rules_source"]["sha256"],
        payout_decisions=tuple(
            (key, register["decisions"][key]["status"], register["decisions"][key]["decision"])
            for key in DEPENDENCIES["payout"]
        ),
    )


def _verified(config: PayoutConfig, allow_provisional: bool,
              register_path: str | Path | None) -> PayoutConfig:
    derived = payout_config(config.participants, override=config.override,
                            allow_provisional=allow_provisional, register_path=register_path)
    if derived != config:
        raise ValueError("Payout configuration does not match its versioned derivation")
    return derived


def split_prizes(points: Mapping[str, int | float], prizes: tuple[int, ...]) -> tuple[Award, ...]:
    """Rank entries and pool occupied-position prizes across each tie."""
    if not points:
        raise ValueError("Prize split needs at least one ranked entry")
    checked = {entry: _check_points(value) for entry, value in points.items()}
    ranked = sorted(checked, key=lambda entry: (-checked[entry], entry))
    awards: list[Award] = []
    start = 0
    while start < len(ranked):
        end = start
        while end + 1 < len(ranked) and checked[ranked[end + 1]] == checked[ranked[start]]:
            end += 1
        group = ranked[start:end + 1]
        pool = sum(prizes[start:end + 1])
        share, extra = divmod(pool, len(group))
        for index, entry in enumerate(group):
            awards.append(Award(entry_id=entry, points=checked[entry], position=start + 1,
                                tied_with=len(group), payout_cents=share + (index < extra)))
        start = end + 1
    return tuple(awards)


def _table(scope: str, points: dict[str, int], excluded: tuple[str, ...],
           prizes: tuple[int, ...], config: PayoutConfig, snapshot: LedgerSnapshot) -> PayoutTable:
    payload = {"scope": scope, "points": points, "excluded": excluded,
               "config": config.to_dict(), "history": snapshot.history_digest}
    return PayoutTable(
        scope=scope, awards=split_prizes(points, prizes), excluded=excluded,
        config_version=config.config_version,
        rule_register_version=config.rule_register_version,
        source_history_digest=snapshot.history_digest,
        input_digest=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def _check_participants(snapshot: LedgerSnapshot, config: PayoutConfig) -> None:
    if len(snapshot.entries) != config.participants:
        raise ValueError("Ledger entries do not match the configured participant count")


def event_payouts(
    snapshot: LedgerSnapshot,
    event_id: str,
    config: PayoutConfig,
    *,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> PayoutTable:
    """Pay one finished event to prize-eligible entries; random assignments rank nowhere."""
    config = _verified(config, allow_provisional, register_path)
    if event_id not in _EVENTS:
        raise ValueError("Unknown pool event: " + event_id)
    _check_participants(snapshot, config)
    states = {s.entry_id: s for s in snapshot.events if s.event_id == event_id}
    if (set(states) != {e.entry_id for e in snapshot.entries}
            or not all(s.points_recorded for s in states.values())):
        raise ValueError("Incomplete event results for every participant")
    eligible = {entry: s.season_points for entry, s in states.items() if s.event_payout_eligible}
    excluded = tuple(sorted(set(states) - set(eligible)))
    return _table(event_id, eligible, excluded, config.event_prizes_cents, config, snapshot)


def season_payouts(
    snapshot: LedgerSnapshot,
    config: PayoutConfig,
    *,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> PayoutTable:
    """Pay final season standings, including submission bonus and random-assigned points."""
    config = _verified(config, allow_provisional, register_path)
    _check_participants(snapshot, config)
    recorded = {(s.entry_id, s.event_id) for s in snapshot.events if s.points_recorded}
    if any((entry.entry_id, event) not in recorded
           for entry in snapshot.entries for event in _EVENTS):
        raise ValueError("Incomplete season results: every entry needs all 13 events recorded")
    points = {entry.entry_id: entry.season_points for entry in snapshot.entries}
    return _table("season", points, (), config.season_prizes_cents, config, snapshot)


def outlook(
    samples: Iterable[Mapping[str, int | float]],
    entry_id: str,
    config: PayoutConfig,
    *,
    scope: str = "event",
    ineligible: frozenset[str] = frozenset(),
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> Outlook:
    """Average points, top-three finishes and tie-shared prize money over simulations.

    Each sample scores every participant. Event scope ranks only prize-eligible
    entries; season scope ranks everyone. A tie counts as a top-three finish
    when fewer than three entries score strictly higher, while its expected
    payout is the equal share of the pooled positions (sub-cent remainders,
    which the realized split assigns by entry ID, are not modelled).
    """
    config = _verified(config, allow_provisional, register_path)
    if scope not in ("event", "season"):
        raise ValueError("Outlook scope must be 'event' or 'season'")
    prizes = config.event_prizes_cents if scope == "event" else config.season_prizes_cents
    excluded = ineligible if scope == "event" else frozenset()
    if entry_id in excluded:
        raise ValueError("The entry is ineligible for event prizes")
    count = top3 = 0
    points_total = payout_total = 0.0
    for sample in samples:
        if len(sample) != config.participants or entry_id not in sample:
            raise ValueError("Samples must score exactly the configured participant count, "
                             "including the entry")
        if not ineligible <= sample.keys():
            raise ValueError("Unknown ineligible entry")
        own = _check_points(sample[entry_id])
        ahead = tied = 0
        for rival, value in sample.items():
            value = _check_points(value)
            if rival == entry_id or rival in excluded:
                continue
            ahead += value > own
            tied += value == own
        count += 1
        points_total += own
        top3 += ahead < 3
        payout_total += sum(prizes[ahead:ahead + tied + 1]) / (tied + 1)
    if not count:
        raise ValueError("Outlook needs at least one simulation sample")
    return Outlook(
        entry_id=entry_id, scope=scope, simulations=count,
        expected_points=points_total / count, p_top3=top3 / count,
        expected_payout_cents=payout_total / count, config_version=config.config_version,
    )
