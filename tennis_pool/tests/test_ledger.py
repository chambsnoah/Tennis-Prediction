"""Synthetic public ledger/reconciliation tests, never private workbook parity."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from tennis_api.models.canonical import PlayerId, Provenance
from tennis_pool.ledger import (
    Accepted, ApprovedActivation, Band, EventPoints, EventTerms, LedgerRecord, Missed,
    Pair, SeasonLedger, Selection, Submitted, Voided, reconcile_workbook,
)
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError, load_register
from tennis_pool.workbooks import (
    WorkbookBank, WorkbookPick, WorkbookSeason, WorkbookStanding, WorkbookSubstitution,
    WorkbookUsage,
)


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def at(day):
    return START + timedelta(days=day)


def evidence(day=0, key="synthetic"):
    return Provenance(source="synthetic", source_version="fixture-v1", source_record_id=key,
                      observed_at=at(day), available_at=at(day), ingested_at=at(day))


def terms(event="australian_open", day=10):
    return EventTerms(event_id=event, deadline=at(day), provenance=evidence())


def ledger(*events):
    with pytest.warns(ProvisionalRulesWarning):
        return SeasonLedger.create(events or (terms(),), allow_provisional=True)


def roster(prefix="p", bands=(Band.TOP4, Band.TOP4, Band.TOP8, Band.TOP16, Band.UNSEEDED)):
    return tuple(Pair(primary=Selection(player_id=PlayerId(f"atp:{prefix}{i}"), band=band))
                 for i, band in enumerate(bands))


def record(key, payload, day=1, event="australian_open", **kwargs):
    return LedgerRecord(record_id=key, entry_id="entry:one", event_id=event,
                        effective_at=at(day), evidence=evidence(day, key), payload=payload,
                        **kwargs)


def submitted(key="s", picks=None, day=1, event="australian_open", excel=True):
    return record(key, Submitted(picks=picks or roster(), submitted_at=at(day), excel=excel),
                  day, event)


def accepted(submission="s", key="a", day=2, event="australian_open"):
    return record(key, Accepted(submission_id=submission, approved_by="synthetic authority"),
                  day, event)


def test_submitted_picks_do_not_debit_until_explicit_acceptance():
    with pytest.raises(UnresolvedRulesError):
        SeasonLedger.create((terms(),))
    original = ledger()
    pending = original.append(submitted())
    assert pending.replay(at(2)).entries[0].slam == (4, 4, 4, 4)
    charged = pending.append(accepted()).replay(at(3))
    assert charged.entries[0].slam == (2, 3, 3, 4)
    assert charged.entries[0].masters == (9, 9, 9, 7)
    assert len(charged.entries[0].usage) == 5
    assert charged.events[0].accepted_picks == roster()
    assert charged.events[0].selections == tuple(pair.primary for pair in roster())
    assert charged.events[0].event_payout_eligible
    assert original.history == ()
    assert pending.append(submitted()) == pending


def test_first_three_misses_score_for_season_only_and_fourth_gets_no_roster():
    events = ("indian_wells", "miami", "monte_carlo", "madrid")
    state = ledger(*(terms(event, 10 + i) for i, event in enumerate(events)))
    for i, event in enumerate(events):
        assignments = tuple(pair.primary for pair in roster(str(i))) if i < 3 else ()
        state = state.append(record(f"m{i}", Missed(assignments=assignments,
                                                  approved_by="synthetic authority"),
                                    10 + i, event))
        state = state.append(record(f"p{i}", EventPoints(points=30 if i < 3 else 0),
                                    15 + i, event))
    snapshot = state.replay(at(20))
    assert [event.missed_number for event in sorted(snapshot.events, key=lambda e: e.missed_number)] == [1, 2, 3, 4]
    assert not any(event.event_payout_eligible for event in snapshot.events)
    assert snapshot.entries[0].season_points == 90
    assert snapshot.entries[0].masters == (3, 6, 6, 7)
    assert sum(len(event.selections) for event in snapshot.events) == 15
    with pytest.raises(ValueError, match="Fourth"):
        ledger(*(terms(event, 10 + i) for i, event in enumerate(events))).append(
            *(record(f"bad{i}", Missed(assignments=tuple(p.primary for p in roster(str(i))),
                                       approved_by="synthetic authority"), 10 + i, event)
              for i, event in enumerate(events)))


def test_bonus_once_at_seven_final_accepted_excel_events_not_pending_revisions():
    events = ("australian_open", "indian_wells", "miami", "monte_carlo", "madrid",
              "rome", "roland_garros", "wimbledon")
    state = ledger(*(terms(event, 10 + i) for i, event in enumerate(events)))
    unseeded = (Band.UNSEEDED,) * 5
    for i, event in enumerate(events):
        state = state.append(submitted(f"s{i}", roster(str(i), unseeded), i + 1, event),
                             accepted(f"s{i}", f"a{i}", i + 1, event))
        if i == 5:
            assert state.replay(at(8)).entries[0].submission_bonus == 0
    snapshot = state.replay(at(10))
    assert len(snapshot.entries[0].qualifying_events) == 8
    assert snapshot.entries[0].submission_bonus == 250
    assert snapshot.entries[0].season_points == 250
    state = state.append(submitted("text", roster("text", unseeded), 9, "wimbledon", False),
                         accepted("text", "a-text", 9, "wimbledon"))
    assert len(state.replay(at(10)).entries[0].qualifying_events) == 7
    assert state.replay(at(10)).entries[0].submission_bonus == 250
    state = state.append(submitted("text2", roster("text2", unseeded), 9, "rome", False),
                         accepted("text2", "a-text2", 9, "rome"))
    assert state.replay(at(10)).entries[0].submission_bonus == 0
    assert snapshot.entries[0].submission_bonus == 250


def test_global_five_use_cap_includes_unseeded_across_banks():
    events = ("australian_open", "indian_wells", "miami", "monte_carlo", "madrid", "rome")
    state = ledger(*(terms(event, 10 + i) for i, event in enumerate(events)))
    for i, event in enumerate(events[:5]):
        state = state.append(submitted(f"s{i}", roster("same", (Band.UNSEEDED,) * 5), i + 1, event),
                             accepted(f"s{i}", f"a{i}", i + 1, event))
    assert dict(state.replay(at(8)).entries[0].usage)[PlayerId("atp:same0")] == 5
    with pytest.raises(ValueError, match="five-use"):
        state.append(submitted("s5", roster("same", (Band.UNSEEDED,) * 5), 6, "rome"),
                     accepted("s5", "a5", 6, "rome"))


def test_separate_banks_and_actual_random_band_are_enforced_atomically():
    state = ledger(terms(), terms("indian_wells", 20))
    fours = (Band.TOP4,) * 4 + (Band.UNSEEDED,)
    state = state.append(submitted(picks=roster("slam", fours)), accepted())
    assert state.replay(at(3)).entries[0].slam == (0, 4, 4, 4)
    assigned = tuple(pair.primary for pair in roster("random", fours))
    state = state.append(record("miss", Missed(assignments=assigned, approved_by="synthetic"),
                                20, "indian_wells"))
    assert state.replay(at(21)).entries[0].masters == (5, 9, 9, 7)
    with pytest.raises(ValueError, match="bank"):
        ledger().append(submitted(picks=roster("bad", (Band.TOP4,) * 5)), accepted())


def test_approved_activation_transfers_once_unused_alternatives_never_debit():
    picks = tuple(replace(pair, substitute=Selection(player_id=PlayerId(f"atp:sub{i}"),
                                                    band=pair.primary.band))
                  for i, pair in enumerate(roster()))
    state = ledger().append(submitted(picks=picks), accepted())
    before = state.replay(at(3))
    assert PlayerId("atp:sub0") not in dict(before.entries[0].usage)
    activation = record("activation", ApprovedActivation(
        acceptance_id="a", submission_id="s", primary_ids=(PlayerId("atp:p0"), PlayerId("atp:p1")),
        approved_by="synthetic authority attesting eligibility"), 3)
    state = state.append(activation)
    after = state.replay(at(4))
    assert after.entries[0].slam == before.entries[0].slam
    assert PlayerId("atp:p0") not in dict(after.entries[0].usage)
    assert dict(after.entries[0].usage)[PlayerId("atp:sub0")] == 1
    assert after.events[0].accepted_picks == picks
    assert after.events[0].selections[0] == picks[0].substitute
    assert state.append(activation).replay(at(4)) == after
    assert state.append(replace(activation, record_id="retry")).replay(at(4)).entries == after.entries
    with pytest.raises(ValueError, match="paired"):
        ledger().append(submitted(), accepted(), activation)
    with pytest.raises(ValueError, match="blank"):
        replace(activation.payload, approved_by="")


def test_corrections_are_immutable_evidenced_and_do_not_leak_backward():
    initial = ledger().append(submitted(), accepted(), record("score", EventPoints(points=20), 3))
    before = initial.replay(at(5))
    correction = record("corrected-score", EventPoints(points=45), 3,
                        supersedes="score", correction_reason="Synthetic corrected source total")
    correction = replace(correction, evidence=evidence(8, "corrected-source"))
    corrected = initial.append(correction)
    assert corrected.replay(at(5)) == before
    assert corrected.replay(at(8)) == initial.replay(at(8))
    assert corrected.replay(at(9)).entries[0].season_points == 45
    assert initial.replay(at(9)).entries[0].season_points == 20
    assert len(corrected.history) == 4
    with pytest.raises(FrozenInstanceError):
        before.rules.digest = "changed"
    with pytest.raises(ValueError, match="reason"):
        initial.append(replace(correction, correction_reason=None))
    with pytest.raises(ValueError, match="effective"):
        initial.append(replace(correction, effective_at=at(4)))
    with pytest.raises(ValueError, match="content"):
        initial.append(replace(initial.history[-1], payload=EventPoints(points=10)))


def test_correction_to_accepted_submission_replays_accounting_not_raw_history():
    state = ledger().append(submitted(), accepted())
    snapshot = state.replay(at(5))
    amended = replace(submitted("corrected", roster("new", (Band.UNSEEDED,) * 5)),
                      evidence=evidence(6), supersedes="s", correction_reason="Audited identities")
    corrected = state.append(amended)
    assert corrected.replay(at(5)) == snapshot
    assert corrected.replay(at(7)).entries[0].slam == (4, 4, 4, 4)
    assert corrected.replay(at(7)).events[0].selections[0].player_id == "atp:new0"


def test_availability_and_effective_cutoffs_both_exclusive():
    submission = replace(submitted(), evidence=evidence(4))
    approval = replace(accepted(), evidence=evidence(5))
    state = ledger().append(submission, approval)
    assert state.replay(at(4)).entries == ()
    assert state.replay(at(5)).entries[0].usage == ()
    assert len(state.replay(at(6)).entries[0].usage) == 5
    future = ledger().append(submitted(day=8), accepted(day=9))
    assert future.replay(at(8)).entries == ()
    assert future.replay(at(9)).entries[0].usage == ()
    with pytest.raises(ValueError, match="timezone"):
        state.replay(datetime(2026, 1, 1))


def test_changed_rule_text_fails_closed_but_pinned_provenance_survives_register_edits(tmp_path):
    register = load_register()
    path = tmp_path / "synthetic-register.json"
    path.write_text(json.dumps(register))
    with pytest.warns(ProvisionalRulesWarning):
        state = SeasonLedger.create((terms(),), register_path=path, allow_provisional=True)
    saved = state.replay(at(3)).rules
    register["decisions"]["random_accounting"]["decision"] = "Random selections are free."
    path.write_text(json.dumps(register))
    with pytest.warns(ProvisionalRulesWarning), pytest.raises(ValueError, match="interpretation"):
        SeasonLedger.create((terms(),), register_path=path, allow_provisional=True)
    assert state.replay(at(3)).rules == saved


def test_late_submissions_never_become_accepted_and_invalid_old_state_is_not_hidden():
    state = ledger().append(submitted(day=10))
    assert state.replay(at(11)).entries[0].submission_bonus == 0
    with pytest.raises(ValueError, match="predeadline"):
        state.append(accepted(day=11))
    invalid = submitted(picks=roster("bad", (Band.TOP4,) * 5))
    with pytest.raises(ValueError, match="bank"):
        ledger().append(invalid, accepted(), submitted("good", day=3),
                        accepted("good", "a-good", 4))


def test_workbook_reconciliation_imports_only_explicit_attestations_and_is_idempotent():
    observations = WorkbookSeason(
        picks=tuple(WorkbookPick("Synthetic entrant", "Australie", f"Joueur {i}",
                                 pair.primary.player_id, pair.primary.band.value, False, evidence())
                    for i, pair in enumerate(roster())),
        banks=(WorkbookBank("Synthetic entrant", (2, 3, 3, 4), (9, 9, 9, 7), (), 0, evidence()),),
        usage=(WorkbookUsage("Synthetic entrant", PlayerId("atp:p0"), 1, evidence()),),
        standings=(WorkbookStanding("Synthetic entrant", 1, (31,) + (None,) * 12,
                                    0, 31, evidence()),),
    )
    metadata = dict(participants={"Synthetic entrant": "entry:one"},
                    events={"Australie": "australian_open"}, cutoff=at(5),
                    submission_links={("Synthetic entrant", "Australie"): "s"})
    explicit = (submitted(), accepted(), record("score", EventPoints(points=31), 3))
    result = reconcile_workbook(ledger(), observations, records=explicit, **metadata)
    assert result.differences == ()
    assert result.compared >= 12
    assert result.unavailable == 12
    again = reconcile_workbook(result.ledger, observations, records=explicit, **metadata)
    assert again == result
    assert len(result.ledger.history) == 3
    assert result.snapshot.entries[0].season_points == 31
    unapproved = reconcile_workbook(ledger(), observations, **metadata)
    assert unapproved.ledger.history == ()
    assert any(d.field == "submission_attestation" for d in unapproved.differences)
    assert unapproved.snapshot.entries == ()


def test_reconciliation_reports_explicit_mismatches_and_missing_data_without_seeding_state():
    observations = WorkbookSeason(
        banks=(WorkbookBank("Synthetic entrant", None, (8, None, 9, 7), (), 0, evidence()),),
        usage=(WorkbookUsage("Synthetic entrant", PlayerId("atp:p0"), 4, evidence()),),
        standings=(WorkbookStanding("Synthetic entrant", 1, (4,) + (None,) * 12,
                                    250, 254, evidence()),),
        substitutions=(WorkbookSubstitution("Synthetic entrant", "Australie", PlayerId("atp:p0"),
                                              PlayerId("atp:unapproved"), "1-4", evidence()),),
    )
    state = ledger().append(submitted(), accepted(), record("points", EventPoints(points=3), 3))
    result = reconcile_workbook(state, observations,
                                participants={"Synthetic entrant": "entry:one"},
                                events={"Australie": "australian_open"}, cutoff=at(5))
    assert {d.field for d in result.differences} == {
        "masters:1-4", "usage", "event_points", "submission_bonus", "season_points", "activation",
    }
    assert result.ledger == state
    assert result.snapshot.entries[0].slam == (2, 3, 3, 4)
    assert result.unavailable == 17
    with pytest.raises(ValueError, match="mapping"):
        reconcile_workbook(state, observations, participants={}, events={}, cutoff=at(5))


def test_future_workbook_observations_are_not_available_at_cutoff():
    observations = WorkbookSeason(usage=(WorkbookUsage("Synthetic entrant", PlayerId("atp:p0"),
                                                       4, evidence(8)),))
    state = ledger().append(submitted(), accepted())
    result = reconcile_workbook(state, observations,
                                participants={"Synthetic entrant": "entry:one"},
                                events={}, cutoff=at(8))
    assert result.compared == 0
    assert result.unavailable == 1
    assert result.differences == ()


def test_activation_cannot_hide_an_illegal_primary_acceptance_at_same_instant():
    events = ("australian_open", "indian_wells", "miami", "monte_carlo", "madrid", "rome")
    state = ledger(*(terms(event, 10 + i) for i, event in enumerate(events)))
    for i, event in enumerate(events[:5]):
        state = state.append(submitted(f"s{i}", roster("same", (Band.UNSEEDED,) * 5), i + 1, event),
                             accepted(f"s{i}", f"a{i}", i + 1, event))
    picks = list(roster("fresh", (Band.UNSEEDED,) * 5))
    picks[0] = Pair(primary=Selection(player_id=PlayerId("atp:same0"), band=Band.UNSEEDED),
                    substitute=Selection(player_id=PlayerId("atp:replacement"), band=Band.UNSEEDED))
    with pytest.raises(ValueError, match="five-use"):
        state.append(submitted("s6", tuple(picks), 6, "rome"),
                     accepted("s6", "a6", 6, "rome"),
                     record("activate", ApprovedActivation(acceptance_id="a6", submission_id="s6",
                            primary_ids=(PlayerId("atp:same0"),), approved_by="synthetic"),
                            6, "rome"))


def test_activation_can_be_revoked_only_by_an_evidenced_correction():
    picks = roster()
    picks = (replace(picks[0], substitute=Selection(player_id=PlayerId("atp:replacement"),
                                                    band=Band.TOP4)),) + picks[1:]
    active = record("activate", ApprovedActivation(acceptance_id="a", submission_id="s",
                    primary_ids=(PlayerId("atp:p0"),), approved_by="synthetic"), 3)
    state = ledger().append(submitted(picks=picks), accepted(), active)
    revoke = replace(active, record_id="revoke", evidence=evidence(7), supersedes="activate",
                     correction_reason="Synthetic eligibility approval revoked",
                     payload=replace(active.payload, primary_ids=()))
    revoked = state.append(revoke)
    assert revoked.replay(at(6)) == state.replay(at(6))
    assert dict(revoked.replay(at(8)).entries[0].usage)[PlayerId("atp:p0")] == 1
    assert PlayerId("atp:replacement") not in dict(revoked.replay(at(8)).entries[0].usage)
    with pytest.raises(ValueError, match="unambiguous"):
        ledger().append(submitted(picks=picks), accepted(),
                        replace(active, payload=replace(active.payload, primary_ids=())))


def test_replay_survives_typed_record_round_trip_and_chained_corrections():
    state = ledger().append(submitted(), accepted(), record("score", EventPoints(points=1), 3))
    correction = replace(record("correct1", EventPoints(points=7), 3), supersedes="score",
                         correction_reason="Synthetic first amendment", evidence=evidence(6))
    correction2 = replace(correction, record_id="correct2", payload=EventPoints(points=15),
                          supersedes="correct1", evidence=evidence(8))
    state = state.append(correction, correction2)
    rebuilt = ledger().append(*(LedgerRecord.from_dict(record.to_dict()) for record in state.history))
    for day, expected in ((4, 1), (7, 7), (9, 15)):
        assert rebuilt.replay(at(day)) == state.replay(at(day))
        assert state.replay(at(day)).entries[0].season_points == expected
    with pytest.raises(ValueError, match="leaf"):
        state.append(replace(correction, record_id="branch", evidence=evidence(9)))
    with pytest.raises(ValueError, match="later"):
        state.append(replace(correction2, record_id="same-time", supersedes="correct2"))


def test_unresolved_and_changed_interpretations_block_even_with_provisional_opt_in(tmp_path):
    register = load_register()
    path = tmp_path / "synthetic-register.json"
    register["decisions"]["submission_bonus"].update(status="unresolved", decision=None)
    path.write_text(json.dumps(register))
    with pytest.warns(ProvisionalRulesWarning), pytest.raises(UnresolvedRulesError):
        SeasonLedger.create((terms(),), register_path=path, allow_provisional=True)
    for key in ("activated_substitutes", "partial_submissions", "canada_event", "substitute_bands"):
        register = load_register()
        register["decisions"][key]["decision"] = "Synthetic changed interpretation"
        path.write_text(json.dumps(register))
        with pytest.warns(ProvisionalRulesWarning), pytest.raises(ValueError, match="interpretation"):
            SeasonLedger.create((terms(),), register_path=path, allow_provisional=True)


def test_strict_confirmed_register_retains_exact_implemented_meaning_and_digest(tmp_path):
    register = load_register()
    for decision in register["decisions"].values():
        decision.update(status="confirmed", confirmation={
            "source": "synthetic fixture, not real commissioner evidence",
            "source_version": "fixture-v1", "confirmed_by": "synthetic authority",
            "confirmed_at": "2026-01-01T00:00:00Z",
        })
    register["register_version"] = "synthetic-confirmation-only"
    path = tmp_path / "synthetic-register.json"
    path.write_text(json.dumps(register))
    strict = SeasonLedger.create((terms(),), register_path=path)
    assert strict.append(submitted(), accepted()).replay(at(3)).entries[0].slam == (2, 3, 3, 4)
    pin = strict.replay(at(3)).rules
    assert json.loads(pin.register_json) == register
    import hashlib
    assert pin.digest == hashlib.sha256(pin.register_json.encode()).hexdigest()
    with pytest.raises(TypeError):
        SeasonLedger()
    with pytest.raises(TypeError):
        replace(strict, history=(submitted(), accepted()))


def test_missing_identity_deadline_or_approval_metadata_cannot_be_inferred():
    with pytest.raises(ValueError, match="timezone"):
        replace(terms(), deadline=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="evidence"):
        ledger().append(replace(submitted(), evidence=replace(evidence(), source_record_id=None)))
    with pytest.raises(ValueError, match="explicit submitted"):
        ledger().append(accepted())
    with pytest.raises(ValueError, match="unmapped"):
        ledger().append(submitted(event="canada"))
    with pytest.raises(ValueError, match="canonical event"):
        terms("Toronto")
    with pytest.raises(ValueError, match="unavailable"):
        ledger(replace(terms(), provenance=evidence(8))).append(submitted(), accepted())


@pytest.mark.parametrize("invalid", [
    roster()[:4],
    (roster()[0],) * 5,
    (replace(roster()[0], substitute=Selection(player_id=PlayerId("atp:sub"), band=Band.TOP32)),)
    + roster()[1:],
    (replace(roster()[0], substitute=roster()[1].primary),) + roster()[1:],
    (replace(roster()[0], substitute=Selection(player_id=PlayerId("atp:sub"), band=Band.TOP4)),
     replace(roster()[1], substitute=Selection(player_id=PlayerId("atp:sub"), band=Band.TOP4)))
    + roster()[2:],
])
def test_invalid_submitted_rosters_are_observations_not_accepted_accounting(invalid):
    pending = ledger().append(submitted(picks=invalid))
    assert pending.replay(at(3)).entries[0].usage == ()
    with pytest.raises(ValueError, match="Acceptance"):
        pending.append(accepted())


def test_masters_seventeen_to_thirty_two_bank_is_seven_not_nine():
    events = ("indian_wells", "miami")
    state = ledger(*(terms(event, 10 + i) for i, event in enumerate(events)))
    state = state.append(submitted("s1", roster("one", (Band.TOP32,) * 5), 1, events[0]),
                         accepted("s1", "a1", 2, events[0]))
    assert state.replay(at(3)).entries[0].masters == (9, 9, 9, 2)
    with pytest.raises(ValueError, match="bank"):
        state.append(submitted("s2", roster("two", (Band.TOP32,) * 3 + (Band.UNSEEDED,) * 2),
                                3, events[1]), accepted("s2", "a2", 4, events[1]))


def test_independent_participant_banks_and_usage_are_not_shared():
    first = (submitted(), accepted())
    second = tuple(replace(r, record_id=r.record_id + "-second", entry_id="entry:two",
                           payload=replace(r.payload, submission_id="s-second")
                           if isinstance(r.payload, Accepted) else r.payload) for r in first)
    state = ledger().append(*first, *second).replay(at(3))
    assert len(state.entries) == 2
    assert state.entries[0].slam == state.entries[1].slam == (2, 3, 3, 4)
    assert state.entries[0].usage == state.entries[1].usage


def test_submission_correction_cannot_retarget_an_existing_activation():
    picks = roster()
    picks = (replace(picks[0], substitute=Selection(player_id=PlayerId("atp:subA"),
                                                    band=Band.TOP4)),) + picks[1:]
    activation = record("activate", ApprovedActivation(
        acceptance_id="a", submission_id="s", primary_ids=(PlayerId("atp:p0"),), approved_by="synthetic"), 3)
    state = ledger().append(submitted(picks=picks), accepted(), activation)
    amended = replace(state.history[0], record_id="corrected-submission", evidence=evidence(6),
                      supersedes="s", correction_reason="Synthetic pairing correction",
                      payload=replace(state.history[0].payload, picks=(
                          replace(picks[0], substitute=Selection(player_id=PlayerId("atp:subB"),
                                                                band=Band.TOP4)),) + picks[1:]))
    with pytest.raises(ValueError, match="submission revision"):
        state.append(amended)
    reapproved = replace(activation, record_id="corrected-activation", evidence=evidence(6),
                         supersedes="activate", correction_reason="Synthetic replacement reapproved",
                         payload=replace(activation.payload, submission_id="corrected-submission"))
    corrected = state.append(amended, reapproved)
    assert corrected.replay(at(5)) == state.replay(at(5))
    assert dict(corrected.replay(at(7)).entries[0].usage)[PlayerId("atp:subB")] == 1
    assert PlayerId("atp:subA") not in dict(corrected.replay(at(7)).entries[0].usage)


def test_revoked_activation_allows_a_later_timely_acceptance():
    picks = roster()
    picks = (replace(picks[0], substitute=Selection(player_id=PlayerId("atp:subA"),
                                                    band=Band.TOP4)),) + picks[1:]
    activation = record("activate", ApprovedActivation(
        acceptance_id="a", submission_id="s", primary_ids=(PlayerId("atp:p0"),), approved_by="synthetic"), 3)
    state = ledger().append(submitted(picks=picks), accepted(), activation)
    revoke = replace(activation, record_id="revoke", evidence=evidence(4), supersedes="activate",
                     correction_reason="Synthetic revoked approval",
                     payload=replace(activation.payload, primary_ids=()))
    state = state.append(revoke)
    before = state.replay(at(5))
    corrected = state.append(submitted("new", roster("new"), day=5),
                             accepted("new", "new-acceptance", day=6))
    assert corrected.replay(at(5)) == before
    assert corrected.replay(at(7)).events[0].accepted_submission_id == "new"
    assert PlayerId("atp:subA") not in dict(corrected.replay(at(7)).entries[0].usage)


def test_timely_submission_can_be_accepted_after_deadline_without_backdating():
    pending = ledger().append(submitted())
    state = pending.append(accepted(day=11))
    assert state.replay(at(11)).entries[0].usage == ()
    after = state.replay(at(12))
    assert after.events[0].event_payout_eligible
    assert after.entries[0].qualifying_events == ("australian_open",)
    assert after.entries[0].slam == (2, 3, 3, 4)


def test_erroneous_miss_is_voided_without_rewriting_historical_accounting():
    state = ledger(terms(), terms("indian_wells", 20))
    random = record("random", Missed(assignments=tuple(p.primary for p in roster("random")),
                                     approved_by="synthetic"), day=10)
    second = record("second-miss", Missed(assignments=tuple(p.primary for p in roster("next")),
                                          approved_by="synthetic"), day=20, event="indian_wells")
    state = state.append(random, second)
    before = state.replay(at(24))
    void = replace(random, record_id="void-random", payload=Voided(approved_by="synthetic"),
                   evidence=evidence(25), supersedes="random",
                   correction_reason="Synthetic timely submission discovered")
    recovered = (replace(submitted(), evidence=evidence(25)),
                 replace(accepted(day=11), evidence=evidence(25)))
    corrected = state.append(void, *recovered)
    assert corrected.replay(at(24)) == before
    after = corrected.replay(at(26))
    assert after.events[0].event_payout_eligible
    assert after.events[0].missed_number is None
    assert after.events[1].missed_number == 1
    assert after.entries[0].qualifying_events == ("australian_open",)
    assert PlayerId("atp:random0") not in dict(after.entries[0].usage)
    assert dict(after.entries[0].usage)[PlayerId("atp:p0")] == 1
    rebuilt = ledger(*state.events).append(*(LedgerRecord.from_dict(r.to_dict())
                                             for r in corrected.history))
    assert rebuilt.replay(at(26)) == after
    with pytest.raises(ValueError, match="superseded"):
        state.append(replace(void, record_id="unbound-void", supersedes=None,
                             correction_reason=None))
