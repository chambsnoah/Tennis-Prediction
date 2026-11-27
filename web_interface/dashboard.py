"""Season state and decision/monitoring mode for the local pool dashboard.

The operator keeps the season in ``season.json`` inside the trusted pool
directory: the ledger calendar (``EventTerms``), the append-only ledger records,
the dashboard's own ``entry_id`` and optional rival, prospect and appeal inputs.
Requests never name it or any other path; it is re-read for every request, so
an updated file is picked up without a restart.

The mode comes from the server clock, never from the request: before an event's
deadline the dashboard may recommend; at or after it only monitoring is
available, so a sheet cannot be re-selected after lock. This module has no
NumPy dependency; the decision job lives in ``web_interface.dashboard_jobs``.

Season data (entry IDs, picks, banks, standings) is private. It is returned
only to the loopback browser, marked ``no-store``, and never logged.
"""

from __future__ import annotations

import json
import re
import warnings
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tennis_pool.ledger import (
    Band, EntryState, EventState, EventTerms, LedgerRecord, LedgerSnapshot, Pair, SeasonLedger,
)
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError
from web_interface.errors import ServiceError
from web_interface.files import read_bounded

SEASON_FILE = "season.json"
SEASON_INPUT_BYTES = 8 * 1024 * 1024
MAX_SEASON_RECORDS = 20_000
MAX_ENTRIES = 200
SLAM_EVENTS = frozenset({"australian_open", "roland_garros", "wimbledon", "us_open"})
_ENTRY = re.compile(r"[A-Za-z0-9:_.-]{1,64}")
_FRESH_SLAM = (4, 4, 4, 4)
_FRESH_MASTERS = (9, 9, 9, 7)
_SEEDED = (Band.TOP4, Band.TOP8, Band.TOP16, Band.TOP32)
_OPTIONAL = ("known_picks", "future", "appeal")


@dataclass(frozen=True)
class SeasonInputs:
    """Typed ledger inputs plus raw optional model inputs the NumPy worker parses."""

    entry_id: str = field(repr=False)
    events: tuple[EventTerms, ...] = field(repr=False)
    records: tuple[LedgerRecord, ...] = field(repr=False)
    entries: tuple[str, ...] = field(repr=False)
    known_picks: tuple[Mapping[str, Any], ...] = field(default=(), repr=False)
    future: tuple[Mapping[str, Any], ...] = field(default=(), repr=False)
    appeal: tuple[Mapping[str, Any], ...] = field(default=(), repr=False)

    def terms(self, event_id: str) -> EventTerms:
        found = next((t for t in self.events if t.event_id == event_id), None)
        if found is None:
            raise ServiceError("event_terms_missing", 422)
        return found

    @property
    def rival_ids(self) -> tuple[str, ...]:
        return tuple(e for e in self.entries if e != self.entry_id)


def _invalid() -> ServiceError:
    return ServiceError("invalid_season_input", 503)


def _entry_id(value: object) -> str:
    if not isinstance(value, str) or not _ENTRY.fullmatch(value):
        raise _invalid()
    return value


def _objects(data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list) or len(value) > MAX_SEASON_RECORDS or any(
            not isinstance(item, dict) for item in value):
        raise _invalid()
    return value


def parse_season(data: object) -> SeasonInputs:
    """Validate a ``season.json`` document into typed records (no ledger replay yet)."""
    allowed = {"schema_version", "entry_id", "entries", "events", "records", *_OPTIONAL}
    if (not isinstance(data, dict) or set(data) - allowed or data.get("schema_version") != 1
            or not {"entry_id", "events", "records"} <= set(data)):
        raise _invalid()
    entry_id = _entry_id(data["entry_id"])
    try:
        events = tuple(EventTerms.from_dict(e) for e in _objects(data, "events"))
        records = tuple(LedgerRecord.from_dict(r) for r in _objects(data, "records"))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise _invalid() from None
    if not events or len({e.event_id for e in events}) != len(events):
        raise _invalid()
    listed = data.get("entries", [])
    if not isinstance(listed, list) or len(listed) > MAX_ENTRIES:
        raise _invalid()
    named = [_entry_id(e) for e in listed]
    if len(set(named)) != len(named):
        raise _invalid()
    seen = {entry_id, *named, *(r.entry_id for r in records)}
    if len(seen) > MAX_ENTRIES:
        raise _invalid()
    return SeasonInputs(
        entry_id=entry_id, events=events, records=records, entries=tuple(sorted(seen)),
        **{key: tuple(_objects(data, key)) for key in _OPTIONAL})


def load_season(root: Path) -> SeasonInputs:
    """Read ``season.json`` from the trusted pool directory (bounded, no symlinks)."""
    raw = read_bounded(root, [SEASON_FILE], SEASON_INPUT_BYTES, trusted=True,
                       missing="season_input_missing", too_large="season_input_too_large")
    try:
        data = json.loads(raw)
    except ValueError:
        raise _invalid() from None
    return parse_season(data)


def mode(terms: EventTerms, now: datetime) -> str:
    """``decision`` strictly before the deadline, ``monitoring`` from it on."""
    return "decision" if now < terms.deadline else "monitoring"


@contextmanager
def season_errors() -> Iterator[None]:
    """Ledger refusals become safe codes; strict mode stays ``rules_unresolved``."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalRulesWarning)
            yield
    except ServiceError:
        raise
    except UnresolvedRulesError:
        raise ServiceError("rules_unresolved", 409) from None
    except (ValueError, TypeError, KeyError):
        # Ledger messages can quote entries or picks; return a stable code instead.
        raise _invalid() from None


def build_ledger(season: SeasonInputs, allow_provisional: bool) -> SeasonLedger:
    with season_errors():
        ledger = SeasonLedger.create(season.events, allow_provisional=allow_provisional)
        return ledger.append(*season.records)


def fresh_state(entry_id: str) -> EntryState:
    """An entry with no visible ledger records: full banks and no uses."""
    return EntryState(entry_id=entry_id, slam=_FRESH_SLAM, masters=_FRESH_MASTERS, usage=())


def entry_states(season: SeasonInputs, snapshot: LedgerSnapshot) -> dict[str, EntryState]:
    known = {e.entry_id: e for e in snapshot.entries}
    return {e: known.get(e) or fresh_state(e) for e in season.entries}


def decision_baseline(state: EntryState, snapshot: LedgerSnapshot, event_id: str) -> EntryState:
    """The entry before this event: reverse only its own selections for ``event_id``.

    Replay already charges an accepted sheet for the event being decided. The
    optimizer and planner charge the sheet they choose, so the decision must start
    from the state without it: one use back per selection, one token back in this
    event's bank per seeded selection, and the event's sheet and points out of the
    qualifying count and season total. Earlier events keep their spending.
    """
    event = next((e for e in snapshot.events
                  if e.entry_id == state.entry_id and e.event_id == event_id), None)
    if event is None:
        return state
    usage = dict(state.usage)
    bank = list(state.slam if event_id in SLAM_EVENTS else state.masters)
    for selection in event.selections:
        usage[selection.player_id] -= 1
        if selection.band is not Band.UNSEEDED:
            bank[_SEEDED.index(selection.band)] += 1
    qualifying = tuple(e for e in state.qualifying_events if e != event_id)
    bonus = state.submission_bonus if len(qualifying) >= 7 else 0
    return EntryState(
        entry_id=state.entry_id,
        slam=tuple(bank) if event_id in SLAM_EVENTS else state.slam,
        masters=state.masters if event_id in SLAM_EVENTS else tuple(bank),
        usage=tuple(sorted((p, n) for p, n in usage.items() if n > 0)),
        qualifying_events=qualifying, submission_bonus=bonus,
        season_points=state.season_points - event.season_points
        - state.submission_bonus + bonus)


def _pairs(pairs: tuple[Pair, ...]) -> list[dict[str, Any]]:
    return [pair.to_dict() for pair in pairs]


def _event_state(state: EventState | None) -> dict[str, object]:
    if state is None:
        return {"submitted": 0, "accepted": False, "accepted_picks": [], "selections": [],
                "points_recorded": False, "season_points": 0, "missed_number": None}
    return {
        "submitted": len(state.submitted),
        "accepted": state.accepted_submission_id is not None,
        "accepted_picks": _pairs(state.accepted_picks),
        "selections": [s.to_dict() for s in state.selections],
        "points_recorded": state.points_recorded,
        "season_points": state.season_points,
        "missed_number": state.missed_number,
    }


def season_summary(season: SeasonInputs, snapshot: LedgerSnapshot, event_id: str,
                   now: datetime) -> dict[str, object]:
    """Banks, uses, standings, gaps and this event's own state at the snapshot cutoff."""
    terms = season.terms(event_id)
    states = entry_states(season, snapshot)
    own = states[season.entry_id]
    slam = event_id in SLAM_EVENTS
    bank = own.slam if slam else own.masters
    standings = sorted(states.values(), key=lambda e: (-e.season_points, e.entry_id))
    ranks: dict[int, int] = {}
    for position, entry in enumerate(standings, start=1):
        ranks.setdefault(entry.season_points, position)  # tied entries share a rank
    own_event = next((s for s in snapshot.events
                      if s.entry_id == season.entry_id and s.event_id == event_id), None)
    accepted = {(s.entry_id, s.event_id) for s in snapshot.events if s.accepted_submission_id}
    calendar = []
    for item in sorted(season.events, key=lambda t: t.deadline):
        status = ("current" if item.event_id == event_id
                  else "past" if item.deadline <= now else "upcoming")
        calendar.append({"event_id": item.event_id, "deadline": item.deadline.isoformat(),
                         "status": status,
                         "accepted": (season.entry_id, item.event_id) in accepted})
    return {
        "mode": mode(terms, now),
        "event_id": event_id,
        "deadline": terms.deadline.isoformat(),
        "now": now.isoformat(),
        "cutoff": snapshot.cutoff.isoformat(),
        "entry_id": season.entry_id,
        "own": {
            "bank_kind": "slam" if slam else "masters",
            "bank": [{"band": band.value, "remaining": left} for band, left in zip(_SEEDED, bank)],
            "slam": list(own.slam), "masters": list(own.masters),
            "usage": [{"player_id": p, "uses": n, "remaining": 5 - n} for p, n in own.usage],
            "qualifying_events": len(own.qualifying_events),
            "submission_bonus": own.submission_bonus,
            "season_points": own.season_points,
            "in_ledger": any(e.entry_id == season.entry_id for e in snapshot.entries),
        },
        "standings": [{
            "entry_id": e.entry_id, "rank": ranks[e.season_points],
            "season_points": e.season_points, "own": e.entry_id == season.entry_id,
            "gap": own.season_points - e.season_points,
            "qualifying_events": len(e.qualifying_events),
        } for e in standings],
        "event": _event_state(own_event),
        "calendar": calendar,
        "ledger": {"history_digest": snapshot.history_digest,
                   "rule_register_version": snapshot.rules.register_version,
                   "rule_digest": snapshot.rules.digest,
                   "records": len(season.records)},
    }


@dataclass(frozen=True)
class SeasonJob:
    season: SeasonInputs = field(repr=False)
    event_id: str
    now: datetime
    allow_provisional: bool


def season_job(job: SeasonJob) -> dict[str, object]:
    ledger = build_ledger(job.season, job.allow_provisional)
    with season_errors():
        snapshot = ledger.replay(job.now)
        return season_summary(job.season, snapshot, job.event_id, job.now)
