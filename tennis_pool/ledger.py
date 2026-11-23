"""Immutable, local season accounting from explicit evidence, not workbook guesses.

Approval fields are caller attestations, not authenticated commissioner decisions.
This module does not determine substitution eligibility or calculate tennis scores.
Cutoffs are exclusive on both effective time and information availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Mapping

from tennis_api.models.canonical import Contract, PlayerId, Provenance
from tennis_pool.rules import require_resolved
from tennis_pool.workbooks import TOURNAMENTS, WorkbookSeason


class Band(str, Enum):
    TOP4 = "1-4"
    TOP8 = "5-8"
    TOP16 = "9-16"
    TOP32 = "17-32"
    UNSEEDED = "NF"


_SEEDED = (Band.TOP4, Band.TOP8, Band.TOP16, Band.TOP32)
_SLAMS = {"australian_open", "roland_garros", "wimbledon", "us_open"}
_MASTERS = {"indian_wells", "miami", "monte_carlo", "madrid", "rome", "canada",
            "cincinnati", "shanghai", "paris"}
_IMPLEMENTED = {
    "unused_substitutes": "Unused substitutes consume neither band quota nor player uses. Validate their potential activation against the five-use cap and remaining bank when selecting them.",
    "activated_substitutes": "Debit primaries at accepted submission. On valid activation, atomically refund the withdrawn primary's event use and band debit and charge the substitute's event use and actual-band debit. Recheck limits before committing. A withdrawn primary with no valid replacement retains its selection debits but scores zero. Reprocessing an activation must not debit twice.",
    "random_accounting": "Random assignments obey the same five-use cap and debit each sampled player's actual selection-bank category, not the intended pre-fallback slot. Exclude players already at five uses. Unseeded selections still consume a player use. Apply the resulting roster debits atomically.",
    "partial_submissions": "Accept only five distinct eligible legal primaries. Allow zero to five paired alternatives because alternatives are optional, but every supplied pair must be valid. Reject an invalid submission for correction before the deadline; if no valid submission arrives by the deadline, treat it as a missed submission and use the published random-assignment policy. Never silently complete a voluntary roster.",
    "submission_bonus": "Count at most one qualifying submission per event, based on the final accepted pre-deadline submission being an attached completed spreadsheet. Pre-deadline corrections qualify; late attachments and automatically assigned rosters do not. Award 250 season points once upon reaching seven qualifying events.",
    "canada_event": "Treat Toronto and Montreal references as aliases for the single ATP Canadian Masters event with stable ID canada. Use M7 scoring and the Masters bank regardless of venue; obtain actual venue and dates from event data instead of inferring them from this PDF.",
    "substitute_bands": "Require each substitute to share its primary's selection-bank category: 1-4, 5-8, 9-16, 17-32, or unseeded. Unseeded and 17-32 are separate for this check. Do not impose one-per-band on voluntary primaries.",
    "overlapping_picks": "Require five distinct primaries and prohibit any substitute from also being a primary. One player can occupy at most one scoring slot per event.",
    "duplicate_substitutes": "Require distinct supplied substitutes; reject duplicate alternatives rather than assigning priority between their primaries.",
    "simultaneous_withdrawals": "Evaluate eligible pairs from the same pre-activation state and apply valid transfers in one atomic transaction. Invalid pairs keep the withdrawn primary and zero score. Reject an inconsistent aggregate ledger instead of resolving it by slot order. Same-band, unique substitutes should make valid transfers conflict-free.",
}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, kw_only=True)
class RuleProvenance(Contract):
    register_version: str
    source_digest: str
    register_json: str
    digest: str


@dataclass(frozen=True, kw_only=True)
class EventTerms(Contract):
    event_id: str
    deadline: datetime
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.event_id not in _SLAMS | _MASTERS or not self.provenance.source_record_id:
            raise ValueError("Explicit canonical event and deadline evidence required")


@dataclass(frozen=True, kw_only=True)
class Selection(Contract):
    player_id: PlayerId
    band: Band


@dataclass(frozen=True, kw_only=True)
class Pair(Contract):
    primary: Selection
    substitute: Selection | None = None


@dataclass(frozen=True, kw_only=True)
class Submitted(Contract):
    picks: tuple[Pair, ...]
    submitted_at: datetime
    excel: bool


@dataclass(frozen=True, kw_only=True)
class Accepted(Contract):
    submission_id: str
    approved_by: str


@dataclass(frozen=True, kw_only=True)
class ApprovedActivation(Contract):
    """Caller attests #22 eligibility was approved for these predeclared pairs.

    The source record must identify that approval, not merely a withdrawal row.
    The submission ID pins its exact revision; changed pairs need renewed evidence.
    Accounting never infers approval or first-participation times from a preview.
    An evidenced superseding correction with no primary IDs revokes that approval.
    """

    acceptance_id: str
    submission_id: str
    primary_ids: tuple[PlayerId, ...]
    approved_by: str


@dataclass(frozen=True, kw_only=True)
class Missed(Contract):
    """An externally assigned roster, not a random-roster generator."""

    assignments: tuple[Selection, ...]
    approved_by: str


@dataclass(frozen=True, kw_only=True)
class EventPoints(Contract):
    """Explicit audited season points; no scoring-service dependency."""

    points: int
    accounting_digest: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.points < 0:
            raise ValueError("Season points cannot be negative")


@dataclass(frozen=True, kw_only=True)
class Voided(Contract):
    """Evidenced cancellation of a prior record, never deletion of its history."""

    approved_by: str


@dataclass(frozen=True, kw_only=True)
class LedgerRecord(Contract):
    record_id: str
    entry_id: str
    event_id: str
    effective_at: datetime
    evidence: Provenance
    payload: Submitted | Accepted | ApprovedActivation | Missed | EventPoints | Voided
    supersedes: str | None = None
    correction_reason: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.evidence.source_record_id:
            raise ValueError("Ledger evidence requires a source record reference")
        if isinstance(self.payload, Submitted) and self.payload.submitted_at > self.effective_at:
            raise ValueError("Submission cannot follow its effective time")


@dataclass(frozen=True, kw_only=True)
class EntryState(Contract):
    entry_id: str
    slam: tuple[int, ...]
    masters: tuple[int, ...]
    usage: tuple[tuple[PlayerId, int], ...]
    qualifying_events: tuple[str, ...] = ()
    submission_bonus: int = 0
    season_points: int = 0


@dataclass(frozen=True, kw_only=True)
class EventState(Contract):
    entry_id: str
    event_id: str
    submitted: tuple[LedgerRecord, ...]
    accepted_submission_id: str | None
    accepted_picks: tuple[Pair, ...]
    selections: tuple[Selection, ...]
    accounting_digest: str
    event_payout_eligible: bool
    qualifying_excel: bool
    missed_number: int | None = None
    season_points: int = 0
    points_recorded: bool = False


@dataclass(frozen=True, kw_only=True)
class LedgerSnapshot(Contract):
    cutoff: datetime
    entries: tuple[EntryState, ...]
    events: tuple[EventState, ...]
    rules: RuleProvenance
    history_digest: str


@dataclass(frozen=True, init=False)
class SeasonLedger:
    events: tuple[EventTerms, ...]
    rules: RuleProvenance
    history: tuple[LedgerRecord, ...] = ()

    def __init__(self) -> None:
        raise TypeError("Use SeasonLedger.create; ledger history must be validated")

    @classmethod
    def _build(
        cls, events: tuple[EventTerms, ...], rules: RuleProvenance,
        history: tuple[LedgerRecord, ...] = (),
    ) -> SeasonLedger:
        result = object.__new__(cls)
        object.__setattr__(result, "events", events)
        object.__setattr__(result, "rules", rules)
        object.__setattr__(result, "history", history)
        return result

    @classmethod
    def create(
        cls, events: tuple[EventTerms, ...], *, register_path: str | Path | None = None,
        allow_provisional: bool = False,
    ) -> SeasonLedger:
        if type(allow_provisional) is not bool:
            raise ValueError("Provisional rules require an explicit boolean opt-in")
        serialized = []
        for operation in ("accounting", "submission", "event_mapping", "substitution"):
            register = require_resolved(operation, register_path, allow_provisional=allow_provisional)
            serialized.append(json.dumps(register, sort_keys=True, separators=(",", ":")))
        if len(set(serialized)) != 1:
            raise ValueError("Rule register changed while opening ledger")
        for key, decision in _IMPLEMENTED.items():
            if register["decisions"][key]["decision"] != decision:
                raise ValueError("Unimplemented rule interpretation: " + key)
        if (type(events) is not tuple or not events
                or any(not isinstance(event, EventTerms) for event in events)
                or len({event.event_id for event in events}) != len(events)):
            raise ValueError("Unique explicit event terms required")
        if any(event.deadline.year != 2026 for event in events):
            raise ValueError("Only the 2026 season is implemented")
        return cls._build(events, RuleProvenance(
            register_version=register["register_version"],
            source_digest=register["rules_source"]["sha256"],
            register_json=serialized[0], digest=_digest(serialized[0]),
        ))

    def append(self, *records: LedgerRecord) -> SeasonLedger:
        """Atomically append explicit records; an identical ID/content retry is a no-op."""
        history = list(self.history)
        by_id = {record.record_id: record for record in history}
        superseded = {record.supersedes for record in history if record.supersedes is not None}
        for record in records:
            previous = by_id.get(record.record_id)
            if previous is not None:
                if previous != record:
                    raise ValueError("Record ID reused with different content")
                continue
            if record.supersedes is not None:
                original = by_id.get(record.supersedes)
                if not record.correction_reason or not record.correction_reason.strip():
                    raise ValueError("Correction requires a reason and source evidence")
                if original is None or original.record_id in superseded:
                    raise ValueError("Correction must supersede the current history leaf")
                if (original.entry_id != record.entry_id or original.event_id != record.event_id
                        or (not isinstance(record.payload, Voided)
                            and type(original.payload) is not type(record.payload))
                        or original.effective_at != record.effective_at):
                    raise ValueError("Correction must preserve entry, event, kind and effective time")
                if record.evidence.available_at <= original.evidence.available_at:
                    raise ValueError("Correction evidence must become available later")
                superseded.add(original.record_id)
            elif record.correction_reason is not None:
                raise ValueError("Correction reason requires a superseded record")
            if isinstance(record.payload, Voided) and record.supersedes is None:
                raise ValueError("Voiding requires a superseded record")
            by_id[record.record_id] = record
            history.append(record)
        if len(history) == len(self.history):
            return self
        result = self._build(self.events, self.rules, tuple(history))
        boundaries = {max(r.effective_at, r.evidence.available_at) for r in history}
        for boundary in sorted(boundaries):
            # Validate historical prefixes too: later refunds cannot hide overspending.
            if boundary >= datetime.max.replace(tzinfo=timezone.utc):
                raise ValueError("Ledger timestamp outside replayable range")
            result.replay(boundary + timedelta(microseconds=1))
        return result

    def replay(self, cutoff: datetime) -> LedgerSnapshot:
        """Reconstruct only evidence and effective events strictly before cutoff."""
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("Cutoff requires timezone")
        visible = tuple(record for record in self.history
                        if record.effective_at < cutoff and record.evidence.available_at < cutoff)
        terms = {event.event_id: event for event in self.events
                 if event.provenance.available_at < cutoff}
        roots: dict[str, str] = {}
        active: dict[str, LedgerRecord] = {}
        for record in visible:
            root = roots[record.supersedes] if record.supersedes is not None else record.record_id
            roots[record.record_id] = root
            active[root] = record
        records = {key: active[root] for key, root in roots.items()}
        groups: dict[tuple[str, str], list[LedgerRecord]] = {}
        for record in active.values():
            if isinstance(record.payload, Voided):
                continue
            if record.event_id not in terms:
                raise ValueError("Event terms unavailable or unmapped")
            groups.setdefault((record.entry_id, record.event_id), []).append(record)
        event_states = []
        misses: dict[str, int] = {}
        for (entry_id, event_id), group in sorted(
            groups.items(), key=lambda item: (terms[item[0][1]].deadline, item[0])
        ):
            submissions = tuple(sorted((r for r in group if isinstance(r.payload, Submitted)),
                                       key=lambda r: (r.effective_at, r.record_id)))
            approvals = sorted((r for r in group if isinstance(r.payload, Accepted)),
                               key=lambda r: (r.effective_at, r.record_id))
            pairs: tuple[Pair, ...] = ()
            submission_id = None
            qualifying = False
            selections: tuple[Selection, ...] = ()
            missed_number = None
            if approvals:
                if len(approvals) > 1 and approvals[-1].effective_at == approvals[-2].effective_at:
                    raise ValueError("Ambiguous final acceptance")
                approval = approvals[-1]
                assert isinstance(approval.payload, Accepted)
                submission = records.get(approval.payload.submission_id)
                if (submission is None or not isinstance(submission.payload, Submitted)
                        or (submission.entry_id, submission.event_id) != (entry_id, event_id)
                        or submission.effective_at > approval.effective_at):
                    raise ValueError("Acceptance requires its explicit submitted record")
                if submission.payload.submitted_at >= terms[event_id].deadline:
                    raise ValueError("Accepted submission must be predeadline")
                pairs = submission.payload.picks
                if len(pairs) != 5 or len({p.primary.player_id for p in pairs}) != 5:
                    raise ValueError("Acceptance requires five distinct primaries")
                alternatives = [pair.substitute for pair in pairs if pair.substitute is not None]
                if (len({s.player_id for s in alternatives}) != len(alternatives)
                        or {s.player_id for s in alternatives} & {p.primary.player_id for p in pairs}
                        or any(p.substitute is not None and p.substitute.band is not p.primary.band
                               for p in pairs)):
                    raise ValueError("Acceptance requires distinct, nonoverlapping same-band pairs")
                submission_id = submission.record_id
                qualifying = submission.payload.excel
                selections = tuple(pair.primary for pair in pairs)
            activated: set[PlayerId] = set()
            for activation in (r for r in group if isinstance(r.payload, ApprovedActivation)):
                assert isinstance(activation.payload, ApprovedActivation)
                if not activation.payload.primary_ids and activation.supersedes is not None:
                    continue
                approved = records.get(activation.payload.acceptance_id)
                if (not approvals or approved != approvals[-1]
                        or activation.effective_at < approved.effective_at):
                    raise ValueError("Activation requires the final explicit acceptance")
                if activation.payload.submission_id != submission_id:
                    raise ValueError("Activation requires the exact approved submission revision")
                if ((not activation.payload.primary_ids and activation.supersedes is None)
                        or len(set(activation.payload.primary_ids)) != len(activation.payload.primary_ids)):
                    raise ValueError("Activation requires unambiguous primary IDs")
                paired = {p.primary.player_id: p.substitute for p in pairs}
                for player_id in activation.payload.primary_ids:
                    if paired.get(player_id) is None:
                        raise ValueError("Activation requires a predeclared paired substitute")
                activated.update(activation.payload.primary_ids)
            selections = tuple(
                pair.substitute if pair.primary.player_id in activated and pair.substitute is not None
                else pair.primary for pair in pairs
            )
            missed = [r for r in group if isinstance(r.payload, Missed)]
            if len(missed) > 1 or (missed and approvals):
                raise ValueError("Ambiguous missed/accepted event")
            if missed:
                assignment = missed[0]
                assert isinstance(assignment.payload, Missed)
                if assignment.effective_at < terms[event_id].deadline:
                    raise ValueError("Missed event cannot precede deadline")
                missed_number = misses.get(entry_id, 0) + 1
                misses[entry_id] = missed_number
                selections = assignment.payload.assignments
                if missed_number > 3 and selections:
                    raise ValueError("Fourth and later misses cannot receive assignments")
                if missed_number <= 3 and (
                    len(selections) != 5 or len({s.player_id for s in selections}) != 5
                ):
                    raise ValueError("First three misses require five explicit distinct assignments")
            accounting_digest = _digest(json.dumps({
                "entry": entry_id, "event": event_id,
                "acceptance": approvals[-1].record_id if approvals else None,
                "submission": submission_id,
                "activations": sorted(r.record_id for r in group
                                      if isinstance(r.payload, ApprovedActivation)
                                      and r.payload.primary_ids),
                "missed": missed[0].record_id if missed else None,
                "selections": [selection.to_dict() for selection in selections],
            }, sort_keys=True))
            points = [r.payload for r in group if isinstance(r.payload, EventPoints)]
            if len(points) > 1 or (points and not (approvals or missed)):
                raise ValueError("Points require one unambiguous accounted event")
            if points and points[0].accounting_digest != accounting_digest:
                raise ValueError("Points refer to a stale accounting basis")
            if points and missed_number is not None and missed_number > 3 and points[0].points != 0:
                raise ValueError("Unassigned event cannot score points")
            event_states.append(EventState(
                entry_id=entry_id, event_id=event_id, submitted=submissions,
                accepted_submission_id=submission_id, accepted_picks=pairs,
                selections=selections, missed_number=missed_number,
                accounting_digest=accounting_digest,
                event_payout_eligible=bool(approvals), qualifying_excel=qualifying,
                season_points=points[0].points if points else 0,
                points_recorded=bool(points),
            ))
        entries = []
        for entry_id in sorted({r.entry_id for r in visible}):
            slam, masters = [4, 4, 4, 4], [9, 9, 9, 7]
            usage: dict[PlayerId, int] = {}
            for state in event_states:
                if state.entry_id != entry_id:
                    continue
                for pair in state.accepted_picks:
                    if usage.get(pair.primary.player_id, 0) >= 5:
                        raise ValueError("Accepted primary exceeds five-use limit before activation")
                    if pair.substitute is not None and usage.get(pair.substitute.player_id, 0) >= 5:
                        raise ValueError("Predeclared substitute exceeds five-use potential activation")
                for selection in state.selections:
                    usage[selection.player_id] = usage.get(selection.player_id, 0) + 1
                    if selection.band is not Band.UNSEEDED:
                        bank = slam if state.event_id in _SLAMS else masters
                        bank[_SEEDED.index(selection.band)] -= 1
            if min(slam + masters) < 0 or any(count > 5 for count in usage.values()):
                raise ValueError("Season bank or five-use limit exceeded")
            own_states = [state for state in event_states if state.entry_id == entry_id]
            qualifying_events = tuple(state.event_id for state in own_states if state.qualifying_excel)
            bonus = 250 if len(qualifying_events) >= 7 else 0
            entries.append(EntryState(
                entry_id=entry_id, slam=tuple(slam), masters=tuple(masters),
                usage=tuple(sorted(usage.items())), qualifying_events=qualifying_events,
                submission_bonus=bonus,
                season_points=sum(state.season_points for state in own_states) + bonus,
            ))
        history_json = json.dumps([r.to_dict() for r in visible], sort_keys=True)
        return LedgerSnapshot(cutoff=cutoff, entries=tuple(entries), events=tuple(event_states),
                              rules=self.rules, history_digest=_digest(history_json))


@dataclass(frozen=True, kw_only=True)
class ReconciliationDifference(Contract):
    entry_id: str
    field: str
    observed: str
    calculated: str
    event_id: str | None = None
    player_id: PlayerId | None = None


@dataclass(frozen=True)
class WorkbookReconciliation:
    ledger: SeasonLedger
    snapshot: LedgerSnapshot
    differences: tuple[ReconciliationDifference, ...]
    compared: int
    unavailable: int


def reconcile_workbook(
    ledger: SeasonLedger, observations: WorkbookSeason, *, participants: Mapping[str, str],
    events: Mapping[str, str], cutoff: datetime, records: tuple[LedgerRecord, ...] = (),
    submission_links: Mapping[tuple[str, str], str] | None = None,
) -> WorkbookReconciliation:
    """Append caller-attested records and compare explicit, available observations.

    Participant/event mappings and links to submitted records are mandatory where
    used. Pick membership/bands are compared, not inferred slot pairings. Preview
    substitutions never authorize activation. Missing cells and future observations
    are counted as unavailable, not zero. Position/rank is not reconciled: a partial
    workbook cannot establish the full standings population. No parity claim is made.
    """
    updated = ledger.append(*records)
    snapshot = updated.replay(cutoff)
    entries = {entry.entry_id: entry for entry in snapshot.entries}
    states = {(state.entry_id, state.event_id): state for state in snapshot.events}
    differences: list[ReconciliationDifference] = []
    compared = unavailable = 0

    def entry(label: str) -> EntryState:
        if label not in participants or not participants[label].strip():
            raise ValueError("Explicit participant mapping required")
        key = participants[label]
        return entries.get(key, EntryState(entry_id=key, slam=(4, 4, 4, 4),
                                           masters=(9, 9, 9, 7), usage=()))

    def event(label: str) -> str:
        if label not in events or events[label] not in {term.event_id for term in updated.events}:
            raise ValueError("Explicit canonical event mapping required")
        return events[label]

    def compare(
        who: str, field: str, observed: object, calculated: object,
        event_id: str | None = None, player_id: PlayerId | None = None,
    ) -> None:
        nonlocal compared, unavailable
        if observed is None:
            unavailable += 1
            return
        compared += 1
        if observed != calculated:
            differences.append(ReconciliationDifference(
                entry_id=who, field=field, observed=str(observed), calculated=str(calculated),
                event_id=event_id, player_id=player_id,
            ))

    for bank in observations.banks:
        if bank.provenance.available_at >= cutoff:
            unavailable += 1
            continue
        state = entry(bank.participant)
        for name, observed_bank, calculated in (
            ("slam", bank.slam, state.slam), ("masters", bank.masters, state.masters),
        ):
            if observed_bank is not None and len(observed_bank) != 4:
                raise ValueError("Workbook bank requires four seeded categories")
            for index, band in enumerate(_SEEDED):
                compare(state.entry_id, name + ":" + band.value,
                        observed_bank[index] if observed_bank is not None else None,
                        calculated[index])
        maxed = tuple(sorted(player for player, count in state.usage if count == 5))
        compare(state.entry_id, "maxed_count", bank.maxed_count, len(maxed))
        if bank.maxed_count is not None or bank.maxed_players:
            compare(state.entry_id, "maxed_players", tuple(sorted(bank.maxed_players)), maxed)
        else:
            unavailable += 1
    for usage in observations.usage:
        if usage.provenance.available_at >= cutoff:
            unavailable += 1
            continue
        state = entry(usage.participant)
        compare(state.entry_id, "usage", usage.count, dict(state.usage).get(usage.player_id, 0),
                player_id=usage.player_id)
    for standing in observations.standings:
        if standing.provenance.available_at >= cutoff:
            unavailable += 1
            continue
        state = entry(standing.participant)
        if len(standing.event_points) != len(TOURNAMENTS):
            raise ValueError("Workbook standing requires explicit thirteen-event layout")
        for label, points in zip(TOURNAMENTS, standing.event_points):
            if points is None:
                unavailable += 1
                continue
            event_id = event(label)
            event_state = states.get((state.entry_id, event_id))
            compare(state.entry_id, "event_points", points,
                    event_state.season_points if event_state is not None
                    and event_state.points_recorded else None, event_id=event_id)
        compare(state.entry_id, "submission_bonus", standing.bonus, state.submission_bonus)
        compare(state.entry_id, "season_points", standing.total, state.season_points)
    pick_groups: dict[tuple[str, str], list[tuple[PlayerId, str | None, bool]]] = {}
    for pick in observations.picks:
        if pick.provenance.available_at >= cutoff:
            unavailable += 1
            continue
        entry(pick.participant)
        event(pick.event)
        pick_groups.setdefault((pick.participant, pick.event), []).append(
            (pick.player_id, pick.band, pick.is_substitute))
    for (label, event_label), picks in pick_groups.items():
        state = entry(label)
        event_id = event(event_label)
        event_state = states.get((state.entry_id, event_id))
        link = (submission_links or {}).get((label, event_label))
        if link is not None:
            for correction in updated.history:
                if (correction.supersedes == link and correction.effective_at < cutoff
                        and correction.evidence.available_at < cutoff):
                    link = correction.record_id
        submission = next((r for r in event_state.submitted if r.record_id == link), None) \
            if event_state is not None else None
        if submission is None or not isinstance(submission.payload, Submitted):
            compare(state.entry_id, "submission_attestation", "observed picks", None, event_id)
            continue
        expected = [(pair.primary.player_id, pair.primary.band.value, False)
                    for pair in submission.payload.picks]
        expected.extend((pair.substitute.player_id, pair.substitute.band.value, True)
                        for pair in submission.payload.picks if pair.substitute is not None)
        compare(state.entry_id, "submitted_players", sorted((p, s) for p, _, s in picks),
                sorted((p, s) for p, _, s in expected), event_id)
        bands = {(p, s): b for p, b, s in expected}
        for player, band_name, substitute in picks:
            compare(state.entry_id, "submitted_band", band_name, bands.get((player, substitute)),
                    event_id, player)
    for replacement in observations.substitutions:
        if replacement.provenance.available_at >= cutoff:
            unavailable += 1
            continue
        state = entry(replacement.participant)
        event_id = event(replacement.event)
        event_state = states.get((state.entry_id, event_id))
        approved_selection = next((selection for pair, selection in zip(
            event_state.accepted_picks, event_state.selections
        ) if pair.primary.player_id == replacement.withdrawn_id
            and selection.player_id == replacement.replacement_id), None) if event_state else None
        compare(state.entry_id, "activation", True, approved_selection is not None,
                event_id, replacement.replacement_id)
        if approved_selection is not None:
            compare(state.entry_id, "activated_band", replacement.band, approved_selection.band.value,
                    event_id, replacement.replacement_id)
    return WorkbookReconciliation(updated, snapshot, tuple(differences), compared, unavailable)
