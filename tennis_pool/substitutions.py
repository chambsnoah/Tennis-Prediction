"""Paired-substitute legality and withdrawal activation from explicit evidence.

Submission checks enumerate every activation combination of the supplied pairs.
Adjudication decides activations from one as-of snapshot of official withdrawal
and first-participation evidence; it never adds players beyond the accepted pairs,
allows chains, or replaces a primary who already played. Missing or conflicting
evidence blocks the slot and names the decision that needs clarification.
Approval of the resulting activation remains a caller attestation for the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
from itertools import combinations
import json
from pathlib import Path

from tennis_api.models.canonical import Contract, Draw, PlayerId, Provenance
from tennis_pool.ledger import (
    _MASTERS, _SEEDED, _SLAMS, ApprovedActivation, Band, EntryState, Pair, Selection,
)
from tennis_pool.rules import DEPENDENCIES, require_resolved


_REGISTER_VERSION = "2026-provisional-2"
# Digest of the implemented substitution decision texts; changes need review.
_DECISION_DIGEST = "9bb92c95df366cb6a6c53b7e1331c55179dc452d371bbb8da2da3344a8244cae"
_FULL_BANKS: dict[str, tuple[int, ...]] = {"slam": (4, 4, 4, 4), "masters": (9, 9, 9, 7)}


def seed_band(seed: int | None) -> Band:
    """Map an event seed to its five-category selection bank, not scoring groups."""
    if seed is None:
        return Band.UNSEEDED
    for limit, band in ((4, Band.TOP4), (8, Band.TOP8), (16, Band.TOP16), (32, Band.TOP32)):
        if 1 <= seed <= limit:
            return band
    raise ValueError("Seed outside the 2026 selection banks")


@dataclass(frozen=True, kw_only=True)
class Withdrawal(Contract):
    """Official withdrawal time; later receipt does not move the cutoff."""

    player_id: PlayerId
    withdrawn_at: datetime
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.withdrawn_at > self.provenance.available_at:
            raise ValueError("Withdrawal evidence cannot precede the withdrawal")


@dataclass(frozen=True, kw_only=True)
class Participation(Contract):
    """First started match or walkover advancement; a bye is not participation.

    ``first_at=None`` attests no participation through ``checked_through``.
    """

    player_id: PlayerId
    first_at: datetime | None
    checked_through: datetime
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.checked_through > self.provenance.available_at:
            raise ValueError("Participation evidence cannot attest the future")
        if self.first_at is not None and self.first_at > self.checked_through:
            raise ValueError("First participation must fall within the checked period")


class SlotOutcome(str, Enum):
    PRIMARY = "primary"
    ACTIVATED = "activated"
    ZERO_UNPAIRED = "zero_unpaired"
    ZERO_SUBSTITUTE_WITHDREW = "zero_substitute_withdrew"
    BLOCKED = "blocked"


@dataclass(frozen=True, kw_only=True)
class SlotDecision(Contract):
    primary_id: PlayerId
    substitute_id: PlayerId | None
    outcome: SlotOutcome
    reason: str
    clarification: str | None = None


@dataclass(frozen=True, kw_only=True)
class Adjudication(Contract):
    as_of: datetime
    slots: tuple[SlotDecision, ...]
    evidence_digest: str
    rule_register_version: str
    substitution_decisions: tuple[tuple[str, str, str], ...]

    @property
    def activated(self) -> tuple[PlayerId, ...]:
        return tuple(sorted(slot.primary_id for slot in self.slots
                            if slot.outcome is SlotOutcome.ACTIVATED))

    @property
    def blocked(self) -> bool:
        return any(slot.outcome is SlotOutcome.BLOCKED for slot in self.slots)


@dataclass(frozen=True, kw_only=True)
class Scenario(Contract):
    """Selections charged when exactly these primaries are replaced.

    Unpaired or doubly withdrawn slots keep the primary's debit, so their
    accounting equals the scenario without that activation.
    """

    activated: tuple[PlayerId, ...]
    selections: tuple[Selection, ...]
    problems: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class RosterCheck(Contract):
    event_id: str
    problems: tuple[str, ...]
    scenarios: tuple[Scenario, ...]
    protected: tuple[PlayerId, ...]
    rule_register_version: str
    substitution_decisions: tuple[tuple[str, str, str], ...]

    @property
    def legal(self) -> bool:
        return not self.problems and all(not s.problems for s in self.scenarios)


def _gate(
    allow_provisional: bool, register_path: str | Path | None,
) -> tuple[str, tuple[tuple[str, str, str], ...]]:
    if type(allow_provisional) is not bool:
        raise ValueError("Provisional substitution rules require an explicit boolean opt-in")
    register = require_resolved("substitution", register_path, allow_provisional=allow_provisional)
    keys = DEPENDENCIES["substitution"]
    digest = hashlib.sha256(json.dumps(
        {key: register["decisions"][key]["decision"] for key in keys}, sort_keys=True,
    ).encode()).hexdigest()
    if register["register_version"] != _REGISTER_VERSION or digest != _DECISION_DIGEST:
        raise ValueError("Unsupported substitution rule version; implementation review required")
    return register["register_version"], tuple(
        (key, register["decisions"][key]["status"], register["decisions"][key]["decision"])
        for key in keys
    )


def _pair_problems(pairs: tuple[Pair, ...]) -> list[str]:
    problems = []
    primaries = [pair.primary.player_id for pair in pairs]
    alternatives = [pair.substitute.player_id for pair in pairs if pair.substitute is not None]
    if len(pairs) != 5:
        problems.append("A submission requires exactly five primaries")
    if len(set(primaries)) != len(primaries):
        problems.append("A submission requires distinct primaries")
    if len(set(alternatives)) != len(alternatives):
        problems.append("Supplied substitutes must be distinct alternatives")
    for player in sorted(set(alternatives) & set(primaries)):
        problems.append(f"Substitute {player} is also a primary")
    for pair in pairs:
        if pair.substitute is not None and pair.substitute.band is not pair.primary.band:
            problems.append(
                f"Substitute {pair.substitute.player_id} must share the same selection band "
                f"as {pair.primary.player_id}"
            )
    return problems


def _charge_problems(
    selections: tuple[Selection, ...], banks: tuple[int, ...], usage: dict[PlayerId, int],
    bank_name: str,
) -> tuple[str, ...]:
    problems = [f"{s.player_id} has no remaining five-use allowance"
                for s in selections if usage.get(s.player_id, 0) >= 5]
    for index, band in enumerate(_SEEDED):
        needed = sum(s.band is band for s in selections)
        if needed > banks[index]:
            problems.append(f"{bank_name} bank {band.value} has {banks[index]} left; needs {needed}")
    return tuple(problems)


def validate_roster(
    pairs: tuple[Pair, ...], draw: Draw, event_id: str, entry: EntryState | None = None, *,
    allow_provisional: bool = False, register_path: str | Path | None = None,
) -> RosterCheck:
    """Check a pre-deadline submission against the released draw and season state.

    Every combination of activations is checked against the event's remaining
    bank and the five-use cap; unused substitutes are never charged. A roster is
    submittable only when ``legal``. Primaries are never silently completed.
    """
    version, decisions = _gate(allow_provisional, register_path)
    if event_id not in _SLAMS | _MASTERS:
        raise ValueError("Unknown pool event; use a canonical 2026 pool event ID")
    bank_name = "slam" if event_id in _SLAMS else "masters"
    problems = _pair_problems(pairs)
    seeds = {slot.player_id: slot.seed for slot in draw.slots if slot.player_id is not None}
    for selection in [p.primary for p in pairs] + [p.substitute for p in pairs if p.substitute]:
        if selection.player_id not in seeds:
            problems.append(f"{selection.player_id} is not in the released draw")
        elif seed_band(seeds[selection.player_id]) is not selection.band:
            problems.append(f"{selection.player_id} band does not match its draw seed")
    protected = tuple(p.primary.player_id for p in pairs if p.substitute is not None)
    if problems:
        return RosterCheck(event_id=event_id, problems=tuple(problems), scenarios=(),
                           protected=protected, rule_register_version=version,
                           substitution_decisions=decisions)
    if entry is None:
        banks, usage = _FULL_BANKS[bank_name], {}
    else:
        banks = entry.slam if bank_name == "slam" else entry.masters
        usage = dict(entry.usage)
    base = tuple(pair.primary for pair in pairs)
    problems.extend(_charge_problems(base, banks, usage, bank_name))
    scenarios = []
    for size in range(len(protected) + 1):
        for replaced in combinations(protected, size):
            selections = tuple(
                pair.substitute if pair.primary.player_id in replaced and pair.substitute
                else pair.primary for pair in pairs
            )
            scenarios.append(Scenario(
                activated=tuple(sorted(replaced)), selections=selections,
                problems=_charge_problems(selections, banks, usage, bank_name),
            ))
    return RosterCheck(event_id=event_id, problems=tuple(problems), scenarios=tuple(scenarios),
                       protected=protected, rule_register_version=version,
                       substitution_decisions=decisions)


_CONFLICT = "conflict"


def _withdrawal_time(records: list[Withdrawal]) -> datetime | str | None:
    times = {record.withdrawn_at for record in records}
    if len(times) > 1:
        return _CONFLICT
    return next(iter(times), None)


def _first_participation(
    records: list[Participation], withdrawn_at: datetime,
) -> tuple[bool, str] | None:
    """Return (participated before withdrawal, reason), or None when unknown."""
    firsts: set[datetime] = set()
    idle_through: list[datetime] = []
    for record in records:
        if record.first_at is None:
            idle_through.append(record.checked_through)
        else:
            firsts.add(record.first_at)
    if len(firsts) > 1 or (firsts and any(t >= min(firsts) for t in idle_through)):
        return None
    if firsts:
        first = next(iter(firsts))
        return first <= withdrawn_at, "first participation " + first.isoformat()
    if idle_through and max(idle_through) >= withdrawn_at:
        return False, "no participation through " + max(idle_through).isoformat()
    return None


def adjudicate(
    pairs: tuple[Pair, ...], withdrawals: tuple[Withdrawal, ...],
    participation: tuple[Participation, ...], *, as_of: datetime,
    allow_provisional: bool = False, register_path: str | Path | None = None,
) -> Adjudication:
    """Decide every slot from evidence available strictly before ``as_of``.

    A primary is replaced only when its official withdrawal precedes its first
    started match or walkover advancement and its predeclared substitute has not
    withdrawn before participating. Transfers are evaluated together from one
    snapshot, so evidence order and slot order do not matter.
    """
    version, decisions = _gate(allow_provisional, register_path)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Adjudication cutoff requires timezone")
    problems = _pair_problems(pairs)
    if problems:
        raise ValueError("; ".join(problems))
    visible_w = [w for w in withdrawals if w.provenance.available_at < as_of]
    visible_p = [p for p in participation if p.provenance.available_at < as_of]

    def withdrawn(player: PlayerId) -> datetime | str | None:
        return _withdrawal_time([w for w in visible_w if w.player_id == player])

    def participated(player: PlayerId, cutoff: datetime) -> tuple[bool, str] | None:
        return _first_participation([p for p in visible_p if p.player_id == player], cutoff)

    slots = []
    for pair in pairs:
        primary = pair.primary.player_id
        substitute = pair.substitute.player_id if pair.substitute else None

        def slot(outcome: SlotOutcome, reason: str, clarification: str | None = None,
                 ) -> SlotDecision:
            return SlotDecision(primary_id=primary, substitute_id=substitute, outcome=outcome,
                                reason=reason, clarification=clarification)

        primary_at = withdrawn(primary)
        if primary_at is None:
            slots.append(slot(SlotOutcome.PRIMARY, "No official withdrawal before cutoff"))
            continue
        if isinstance(primary_at, str):
            slots.append(slot(SlotOutcome.BLOCKED, "Conflicting official withdrawal times",
                              "replacement_eligibility"))
            continue
        primary_played = participated(primary, primary_at)
        if primary_played is None:
            slots.append(slot(SlotOutcome.BLOCKED,
                              "Missing or conflicting first-participation evidence",
                              "replacement_eligibility"))
            continue
        if primary_played[0]:
            slots.append(slot(SlotOutcome.PRIMARY, "Withdrew after participating; "
                              + primary_played[1] + "; earned result stands"))
            continue
        if substitute is None:
            slots.append(slot(SlotOutcome.ZERO_UNPAIRED,
                              "Withdrew before participating with no paired substitute"))
            continue
        substitute_at = withdrawn(substitute)
        if substitute_at is None:
            slots.append(slot(SlotOutcome.ACTIVATED, "Withdrew before participating; "
                              + primary_played[1]))
            continue
        if isinstance(substitute_at, str):
            slots.append(slot(SlotOutcome.BLOCKED, "Conflicting substitute withdrawal times",
                              "substitute_withdrawal"))
            continue
        substitute_played = participated(substitute, substitute_at)
        if substitute_played is None:
            slots.append(slot(SlotOutcome.BLOCKED,
                              "Missing or conflicting substitute participation evidence",
                              "substitute_withdrawal"))
        elif substitute_played[0]:
            slots.append(slot(SlotOutcome.ACTIVATED,
                              "Substitute participated before withdrawing; keeps earned result"))
        else:
            slots.append(slot(SlotOutcome.ZERO_SUBSTITUTE_WITHDREW,
                              "Substitute also withdrew before participating; no chain"))
    evidence = {
        "pairs": sorted(json.dumps(p.to_dict(), sort_keys=True) for p in pairs),
        "withdrawals": sorted(json.dumps(w.to_dict(), sort_keys=True) for w in visible_w),
        "participation": sorted(json.dumps(p.to_dict(), sort_keys=True) for p in visible_p),
    }
    return Adjudication(
        as_of=as_of, slots=tuple(sorted(slots, key=lambda s: s.primary_id)),
        evidence_digest=hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
        rule_register_version=version, substitution_decisions=decisions,
    )


def activation_payload(
    adjudication: Adjudication, *, acceptance_id: str, submission_id: str, approved_by: str,
) -> ApprovedActivation:
    """Build the ledger attestation; blocked slots must be clarified first."""
    blocked = sorted({slot.clarification or "unknown" for slot in adjudication.slots
                      if slot.outcome is SlotOutcome.BLOCKED})
    if blocked:
        raise ValueError("Activation blocked pending clarification: " + ", ".join(blocked))
    return ApprovedActivation(acceptance_id=acceptance_id, submission_id=submission_id,
                              primary_ids=adjudication.activated, approved_by=approved_by)
