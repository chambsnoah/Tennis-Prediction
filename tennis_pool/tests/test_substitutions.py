"""Synthetic issue #22 paired-substitute cases derived from the decision register."""

from datetime import date, datetime, timedelta, timezone
import itertools
import json

import pytest

from tennis_api.models.canonical import (
    Draw, DrawSlot, EntryKind, Event, EventId, PlayerId, Provenance, Surface, Tour,
)
from tennis_pool.ledger import (
    Accepted, ApprovedActivation, Band, EntryState, EventTerms, LedgerRecord, Pair,
    SeasonLedger, Selection, Submitted,
)
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError, load_register
from tennis_pool.substitutions import (
    Participation, SlotOutcome, Withdrawal, activation_payload, adjudicate, seed_band,
    validate_roster,
)


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def at(hours):
    return START + timedelta(hours=hours)


def evidence(hours=0, key="synthetic"):
    return Provenance(source="synthetic", source_version="fixture-v1", source_record_id=key,
                      observed_at=at(hours), available_at=at(hours), ingested_at=at(hours))


def pid(number):
    return PlayerId(f"atp:p{number}")


def gs_draw():
    """128 entrants; player N is seeded N through 32, otherwise unseeded."""
    event = Event(
        event_id=EventId("test:slam"), name="Synthetic slam", tour=Tour.ATP,
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 14), surface=Surface.HARD,
        best_of=5, round_count=7, level="grand_slam", provenance=evidence(),
    )
    slots = tuple(DrawSlot(position=i, kind=EntryKind.PLAYER, player_id=pid(i),
                           seed=i if i <= 32 else None) for i in range(1, 129))
    return Draw(event=event, slots=slots, provenance=evidence())


def pick(number):
    return Selection(player_id=pid(number), band=seed_band(number if number <= 32 else None))


PRIMARIES = (1, 5, 9, 17, 40)
SUBSTITUTES = (2, 6, 10, 18, 41)


def pairs(substitutes=SUBSTITUTES):
    return tuple(Pair(primary=pick(p), substitute=pick(s) if s is not None else None)
                 for p, s in zip(PRIMARIES, substitutes))


def check(roster, entry=None, event="australian_open"):
    with pytest.warns(ProvisionalRulesWarning):
        return validate_roster(roster, gs_draw(), event, entry, allow_provisional=True)


def withdrew(number, hours, available=None):
    return Withdrawal(player_id=pid(number), withdrawn_at=at(hours),
                      provenance=evidence(hours if available is None else available))


def played(number, first, available=None):
    return Participation(player_id=pid(number), first_at=at(first), checked_through=at(first),
                         provenance=evidence(first if available is None else available))


def idle(number, through, available=None):
    """Attests no started match or walkover advancement through the given time."""
    return Participation(player_id=pid(number), first_at=None, checked_through=at(through),
                         provenance=evidence(through if available is None else available))


def decide(withdrawals=(), participation=(), roster=None, as_of=100):
    with pytest.warns(ProvisionalRulesWarning):
        return adjudicate(roster or pairs(), withdrawals, participation, as_of=at(as_of),
                          allow_provisional=True)


def outcomes(result):
    return {slot.primary_id: slot.outcome for slot in result.slots}


@pytest.mark.parametrize("seed, band", [
    (1, Band.TOP4), (4, Band.TOP4), (5, Band.TOP8), (8, Band.TOP8), (9, Band.TOP16),
    (16, Band.TOP16), (17, Band.TOP32), (32, Band.TOP32), (None, Band.UNSEEDED),
])
def test_selection_bands_use_five_bank_categories_not_scoring_groups(seed, band):
    assert seed_band(seed) is band


@pytest.mark.parametrize("seed", [0, 33])
def test_impossible_selection_seed_is_rejected(seed):
    with pytest.raises(ValueError):
        seed_band(seed)


def test_complete_pairs_are_legal_under_every_activation_combination():
    result = check(pairs())
    assert result.legal and result.problems == ()
    assert len(result.scenarios) == 32
    assert {s.activated for s in result.scenarios} == {
        tuple(sorted(combo)) for n in range(6)
        for combo in itertools.combinations([pid(p) for p in PRIMARIES], n)
    }
    everyone = next(s for s in result.scenarios if len(s.activated) == 5)
    assert {s.player_id for s in everyone.selections} == {pid(s) for s in SUBSTITUTES}
    assert result.protected == tuple(pid(p) for p in PRIMARIES)


def test_alternatives_are_optional_but_primaries_are_not_completed():
    unprotected = check(pairs((None,) * 5))
    assert unprotected.legal and unprotected.protected == ()
    assert [s.activated for s in unprotected.scenarios] == [()]
    partial = check(pairs((2, None, None, None, None)))
    assert partial.legal and len(partial.scenarios) == 2
    short = check(pairs()[:4])
    assert not short.legal and short.scenarios == ()
    assert any("five" in problem for problem in short.problems)


@pytest.mark.parametrize("roster, message", [
    (lambda r: (r[0], r[0], *r[2:]), "distinct primaries"),
    (lambda r: (Pair(primary=pick(1), substitute=pick(5)), *r[1:]), "same selection band"),
    (lambda r: (*r[:3], Pair(primary=pick(17), substitute=pick(41)), r[4]), "same selection band"),
    (lambda r: (Pair(primary=pick(1), substitute=pick(2)), Pair(primary=pick(3), substitute=pick(2)),
                *r[2:]), "distinct alternatives"),
    (lambda r: (Pair(primary=pick(1), substitute=pick(2)), Pair(primary=pick(2)), *r[2:]),
     "also a primary"),
    (lambda r: (*r[:4], Pair(primary=pick(40),
                             substitute=Selection(player_id=PlayerId("atp:absent"),
                                                  band=Band.UNSEEDED))), "not in the released draw"),
    (lambda r: (Pair(primary=Selection(player_id=pid(1), band=Band.TOP8)), *r[1:]),
     "does not match its draw seed"),
])
def test_overlapping_duplicate_or_misbanded_rosters_block_submission(roster, message):
    result = check(roster(pairs()))
    assert not result.legal and result.scenarios == ()
    assert any(message in problem for problem in result.problems)


def entry(usage=(), slam=(4, 4, 4, 4), masters=(9, 9, 9, 7)):
    return EntryState(entry_id="entry:one", slam=slam, masters=masters,
                      usage=tuple((pid(p), n) for p, n in usage))


def test_substitute_at_five_uses_makes_only_its_activations_illegal():
    result = check(pairs(), entry(usage=((2, 5),)))
    assert not result.legal and result.problems == ()
    bad = [s for s in result.scenarios if s.problems]
    assert len(bad) == 16 and all(pid(1) in s.activated for s in bad)
    assert all("five-use" in s.problems[0] for s in bad)


def test_primary_usage_and_exhausted_banks_are_rejected_for_the_event_bank():
    assert any("five-use" in p for p in check(pairs(), entry(usage=((9, 5),))).problems)
    exhausted = check(pairs(), entry(slam=(0, 4, 4, 4)))
    assert any("1-4" in problem for problem in exhausted.problems)
    # The Masters bank is separate: an empty Slam bank does not block a Masters event.
    assert check(pairs(), entry(slam=(0, 4, 4, 4)), event="miami").legal
    assert any("1-4" in p for p in check(pairs(), entry(masters=(0, 9, 9, 7)), "miami").problems)


def test_unknown_pool_event_is_not_guessed():
    with pytest.raises(ValueError, match="pool event"):
        check(pairs(), event="toronto")


def test_no_withdrawals_leave_every_primary_in_place():
    result = decide()
    assert set(outcomes(result).values()) == {SlotOutcome.PRIMARY}
    assert result.activated == () and not result.blocked


def test_single_pre_participation_withdrawal_activates_its_paired_substitute():
    result = decide((withdrew(1, 10),), (idle(1, 20),))
    assert outcomes(result)[pid(1)] is SlotOutcome.ACTIVATED
    assert result.activated == (pid(1),)
    # A predeclared alternative may already have played and keeps its event result.
    assert decide((withdrew(1, 10),), (idle(1, 20), played(2, 5))).activated == (pid(1),)


def test_multiple_withdrawals_are_one_order_independent_snapshot():
    withdrawals = (withdrew(1, 10), withdrew(9, 11), withdrew(40, 12))
    participation = (idle(1, 30), idle(9, 30), played(40, 15))
    first = decide(withdrawals, participation)
    assert set(first.activated) == {pid(1), pid(9), pid(40)}
    reordered = decide(withdrawals[::-1], participation[::-1], roster=pairs()[::-1])
    assert reordered.activated == first.activated
    assert reordered.evidence_digest == first.evidence_digest


@pytest.mark.parametrize("first_match", [5, 10])
def test_no_replacement_after_participation_or_a_loss(first_match):
    # Withdrawing at or after the first started match keeps the earned result.
    result = decide((withdrew(1, 10),), (played(1, first_match, available=20),))
    slot = next(s for s in result.slots if s.primary_id == pid(1))
    assert slot.outcome is SlotOutcome.PRIMARY and "participat" in slot.reason
    assert result.activated == ()


def test_unpaired_pre_participation_withdrawal_scores_zero():
    result = decide((withdrew(1, 10),), (idle(1, 20),), roster=pairs((None, 6, 10, 18, 41)))
    assert outcomes(result)[pid(1)] is SlotOutcome.ZERO_UNPAIRED
    assert result.activated == ()


def test_substitute_withdrawal_before_participation_means_no_chain_and_zero():
    result = decide((withdrew(1, 10), withdrew(2, 12)), (idle(1, 20), idle(2, 20)))
    assert outcomes(result)[pid(1)] is SlotOutcome.ZERO_SUBSTITUTE_WITHDREW
    assert result.activated == ()
    # A substitute who already played keeps its earned points and is activated.
    late = decide((withdrew(1, 10), withdrew(2, 12)), (idle(1, 20), played(2, 11)))
    assert late.activated == (pid(1),)


@pytest.mark.parametrize("withdrawals, participation, clarification", [
    ((withdrew(1, 10),), (), "replacement_eligibility"),
    ((withdrew(1, 10),), (idle(1, 9),), "replacement_eligibility"),
    ((withdrew(1, 10), withdrew(1, 11)), (idle(1, 20),), "replacement_eligibility"),
    ((withdrew(1, 10),), (idle(1, 20), played(1, 15)), "replacement_eligibility"),
    ((withdrew(1, 10), withdrew(2, 12)), (idle(1, 20),), "substitute_withdrawal"),
    ((withdrew(1, 10), withdrew(2, 12)), (idle(1, 20), idle(2, 11)), "substitute_withdrawal"),
])
def test_missing_or_conflicting_evidence_blocks_and_names_the_decision(
    withdrawals, participation, clarification,
):
    result = decide(withdrawals, participation)
    slot = next(s for s in result.slots if s.primary_id == pid(1))
    assert slot.outcome is SlotOutcome.BLOCKED and slot.clarification == clarification
    assert result.blocked
    with pytest.raises(ValueError, match=clarification):
        activation_payload(result, acceptance_id="a", submission_id="s", approved_by="x")


def test_future_evidence_is_invisible_but_late_receipt_keeps_the_official_cutoff():
    hidden = decide((withdrew(1, 10, available=50),), (idle(1, 60),), as_of=40)
    assert set(outcomes(hidden).values()) == {SlotOutcome.PRIMARY}
    # A later correction to participation evidence cannot change an earlier snapshot.
    corrected_later = (idle(1, 20), played(1, 5, available=50))
    assert decide((withdrew(1, 10),), corrected_later, as_of=40).activated == (pid(1),)
    assert decide((withdrew(1, 10),), corrected_later, as_of=60).blocked
    # Evidence received after the first match still uses the official withdrawal time.
    received_late = decide((withdrew(1, 10, available=50),), (played(1, 30, available=60),))
    assert received_late.activated == (pid(1),)


def test_withdrawals_outside_the_accepted_pairs_cannot_add_players():
    result = decide((withdrew(77, 10),), (idle(77, 20),))
    assert result.activated == () and pid(77) not in {s.primary_id for s in result.slots}


@pytest.mark.parametrize("make", [
    lambda: Withdrawal(player_id=pid(1), withdrawn_at=at(10), provenance=evidence(5)),
    lambda: Participation(player_id=pid(1), first_at=None, checked_through=at(10),
                          provenance=evidence(5)),
    lambda: Participation(player_id=pid(1), first_at=at(11), checked_through=at(10),
                          provenance=evidence(20)),
])
def test_evidence_cannot_attest_the_future(make):
    with pytest.raises(ValueError):
        make()


def test_adjudication_rejects_structurally_invalid_pairs():
    with pytest.warns(ProvisionalRulesWarning), pytest.raises(ValueError, match="distinct"):
        adjudicate((pairs()[0],) * 5, (), (), as_of=at(1), allow_provisional=True)


def test_strict_mode_blocks_with_the_questions_needing_clarification():
    with pytest.raises(UnresolvedRulesError) as blocked:
        validate_roster(pairs(), gs_draw(), "australian_open")
    assert "replacement_eligibility" in blocked.value.blockers
    with pytest.raises(UnresolvedRulesError):
        adjudicate(pairs(), (), (), as_of=at(1))
    with pytest.raises(ValueError, match="boolean"):
        adjudicate(pairs(), (), (), as_of=at(1), allow_provisional=1)  # type: ignore[arg-type]


@pytest.mark.parametrize("change", ["version", "decision"])
def test_changed_substitution_rules_require_implementation_review(tmp_path, change):
    register = load_register()
    if change == "version":
        register["register_version"] = "2026-provisional-3"
    else:
        register["decisions"]["substitute_withdrawal"]["decision"] = "Allow substitute chains."
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(register))
    with pytest.warns(ProvisionalRulesWarning), pytest.raises(ValueError, match="implementation review"):
        adjudicate(pairs(), (), (), as_of=at(1), allow_provisional=True, register_path=path)


def ledger_record(key, payload, hours):
    return LedgerRecord(record_id=key, entry_id="entry:one", event_id="australian_open",
                        effective_at=at(hours), evidence=evidence(hours, key), payload=payload)


def test_activation_updates_ledger_quota_and_uses_exactly_once():
    with pytest.warns(ProvisionalRulesWarning):
        season = SeasonLedger.create((EventTerms(
            event_id="australian_open", deadline=at(8), provenance=evidence(),
        ),), allow_provisional=True)
    season = season.append(
        ledger_record("s", Submitted(picks=pairs(), submitted_at=at(1), excel=True), 1),
        ledger_record("a", Accepted(submission_id="s", approved_by="synthetic authority"), 2),
    )
    before = dict(season.replay(at(3)).entries[0].usage)
    # Unused alternatives consume nothing.
    assert set(before) == {pid(p) for p in PRIMARIES}
    result = decide((withdrew(1, 10), withdrew(9, 10)), (idle(1, 20), idle(9, 20)), as_of=30)
    payload = activation_payload(result, acceptance_id="a", submission_id="s",
                                 approved_by="synthetic authority")
    assert isinstance(payload, ApprovedActivation)
    assert payload.primary_ids == (pid(1), pid(9))
    activated = season.append(ledger_record("act", payload, 30))
    # Retrying the same record, or attesting the same activation twice, charges once.
    activated = activated.append(ledger_record("act", payload, 30), ledger_record("act2", payload, 31))
    state = activated.replay(at(40))
    usage = dict(state.entries[0].usage)
    assert pid(1) not in usage and pid(9) not in usage
    assert usage[pid(2)] == usage[pid(10)] == 1
    assert sum(usage.values()) == 5
    assert state.entries[0].slam == season.replay(at(3)).entries[0].slam
    assert [s.player_id for s in state.events[0].selections] == [
        pid(2), pid(5), pid(10), pid(17), pid(40)]
