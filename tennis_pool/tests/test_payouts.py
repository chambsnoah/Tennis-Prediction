"""Synthetic payout tests: hand-calculated cents, never private participant data."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from tennis_api.models.canonical import PlayerId, Provenance
from tennis_pool.ledger import (
    _MASTERS, _SLAMS, Accepted, Band, EntryState, EventPoints, EventState, EventTerms,
    LedgerRecord, LedgerSnapshot, Missed, Pair, SeasonLedger, Selection, Submitted,
)
from tennis_pool.payouts import (
    ScheduleOverride, event_payouts, outlook, payout_config, season_payouts, split_prizes,
)
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError, load_register


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
EVENTS = tuple(sorted(_SLAMS | _MASTERS))


def at(day):
    return START + timedelta(days=day)


def config(participants=80, override=None, **kwargs):
    with pytest.warns(ProvisionalRulesWarning):
        return payout_config(participants, override=override, allow_provisional=True, **kwargs)


def small_override(participants=6, event=(200, 100), sixth=0, version="adj-1"):
    return ScheduleOverride(
        version=version, participants=participants, event_prizes_cents=event,
        sixth_prize_cents=sixth, approved_by="synthetic commissioner",
        source="synthetic announcement", announced_at=at(0),
    )


def payouts(awards):
    return {award.entry_id: award.payout_cents for award in awards}


# --- printed schedules and versioned configuration -------------------------------------

def test_payouts_require_the_payout_rule_gate():
    with pytest.raises(UnresolvedRulesError):
        payout_config(80)
    with pytest.raises(ValueError, match="boolean"):
        payout_config(80, allow_provisional=1)


@pytest.mark.parametrize("participants, event, season", [
    (40, (3500, 1500, 500), (64513, 33462, 15350, 10175, 5000, 0)),
    (60, (4500, 2500, 1000), (101888, 51337, 21850, 13425, 5000, 2500)),
    (80, (7000, 3500, 2000), (125750, 62750, 26000, 15500, 5000, 2500)),
])
def test_printed_schedules_use_the_residual_formula_not_rounded_examples(
        participants, event, season):
    result = config(participants)
    assert result.event_prizes_cents == event
    assert result.season_prizes_cents == season
    assert result.override is None
    assert result.config_version == f"2026-printed-{participants}"
    # The pot is conserved exactly: 13 events plus the season schedule.
    assert 13 * sum(event) + sum(season) == participants * 5000


def test_printed_season_examples_are_only_approximations():
    printed = {40: (64500, 33500, 15500, 10000, 5000, 0),
               60: (102000, 51000, 22000, 13500, 5000, 2500),
               80: (126000, 63000, 26000, 15000, 5000, 2500)}
    for participants, example in printed.items():
        computed = config(participants).season_prizes_cents
        assert computed != example
        assert all(abs(a - b) <= 500 for a, b in zip(computed, example))


def test_residual_rounding_uses_largest_remainders_with_position_order():
    # 40 entrants: 57.5% and 27.5% of $1035 both leave half a cent; first wins it.
    assert config(40).residual_cents == 103500
    assert config(40).season_prizes_cents[:2] == (64513, 33462)


@pytest.mark.parametrize("participants", [0, 39, 41, 59, 61, 79, 81, 100])
def test_unprinted_participant_counts_require_explicit_configuration(participants):
    with pytest.raises(ValueError, match="explicit configured schedule"):
        config(participants)


def test_commissioner_override_is_explicit_and_versioned():
    override = small_override()
    result = config(6, override)
    assert result.config_version == "override:adj-1"
    assert result.override == override
    assert result.event_prizes_cents == (200, 100)
    # 6 x $50 - 13 x $3 - 5 x $50 = $11 residual, split 57.5/27.5/10/5.
    assert result.residual_cents == 1100
    assert result.season_prizes_cents == (5633, 5302, 5110, 5055, 5000, 0)
    assert config(80, small_override(80, (7000, 3500, 2000), 2500)).season_prizes_cents == \
        config(80).season_prizes_cents
    with pytest.raises(ValueError, match="participant count"):
        config(7, override)
    # Zero-prize positions beyond the field are harmless.
    padded = config(6, small_override(event=(200, 100) + (0,) * 5))
    assert padded.season_prizes_cents == result.season_prizes_cents


@pytest.mark.parametrize("override, message", [
    (small_override(event=(4000,)), "Underfunded"),
    (small_override(event=(100, 200)), "non-increasing"),
    (small_override(event=(-1,)), "non-negative"),
    (small_override(event=()), "at least one"),
    (small_override(participants=5, event=(0,), sixth=100), "sixth"),
    (small_override(participants=4, event=(0,)), "five season"),
    (small_override(event=(50,) * 7), "beyond the participant count"),
])
def test_invalid_overrides_fail_closed(override, message):
    with pytest.raises(ValueError, match=message):
        config(override.participants, override)


def test_override_requires_timezone_and_nonblank_attestation():
    with pytest.raises(ValueError, match="timezone"):
        replace(small_override(), announced_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="blank"):
        replace(small_override(), approved_by=" ")


def test_configuration_round_trips_and_pins_rules():
    result = config(80)
    assert type(result).from_dict(json.loads(json.dumps(result.to_dict()))) == result
    register = load_register()
    assert result.rule_register_version == register["register_version"]
    assert result.payout_decisions == (
        ("ties_payouts", "provisional", register["decisions"]["ties_payouts"]["decision"]),
    )


def test_changed_payout_decision_requires_implementation_review(tmp_path):
    register = load_register()
    register["decisions"]["ties_payouts"]["decision"] += " Changed."
    path = tmp_path / "register.json"
    path.write_text(json.dumps(register))
    with pytest.raises(ValueError, match="implementation review"):
        config(80, register_path=path)


# --- tie sharing -------------------------------------------------------------------------

def test_ties_crossing_the_paid_boundary_share_occupied_positions():
    prizes = (7000, 3500, 2000)
    # Two tied for third share $20 + $0.
    awards = split_prizes({"e1": 90, "e2": 80, "e3": 70, "e4": 70, "e5": 10}, prizes)
    assert payouts(awards) == {"e1": 7000, "e2": 3500, "e3": 1000, "e4": 1000, "e5": 0}
    assert [(a.entry_id, a.position, a.tied_with) for a in awards] == [
        ("e1", 1, 1), ("e2", 2, 1), ("e3", 3, 2), ("e4", 3, 2), ("e5", 5, 1)]
    # Three tied for second share $35 + $20 + $0; the odd cent goes by stable ID.
    awards = split_prizes({"e9": 50, "e1": 99, "e3": 50, "e2": 50}, prizes)
    assert payouts(awards) == {"e1": 7000, "e2": 1834, "e3": 1833, "e9": 1833}
    # Everyone tied pools every prize.
    assert payouts(split_prizes({"a": 1, "b": 1, "c": 1, "d": 1}, prizes)) == {
        "a": 3125, "b": 3125, "c": 3125, "d": 3125}
    # Ties outside the paid places receive nothing.
    assert payouts(split_prizes({"a": 3, "b": 2, "c": 1, "d": 0, "e": 0}, prizes))["d"] == 0


def test_season_ties_spanning_fifth_and_sixth_pool_refund_and_sixth_prize():
    season = config(80).season_prizes_cents
    points = {f"e{i}": 100 - i for i in range(1, 5)} | {"e5": 50, "e6": 50, "e7": 10}
    result = payouts(split_prizes(points, season))
    assert result["e5"] == result["e6"] == (5000 + 2500) // 2
    assert result["e7"] == 0
    # A tie spanning 4th/5th pools the refunded stakes too.
    tied = payouts(split_prizes({"a": 9, "b": 8, "c": 7, "d": 6, "e": 6, "f": 1}, season))
    assert tied["d"] + tied["e"] == season[3] + season[4]
    assert abs(tied["d"] - tied["e"]) <= 1
    assert sum(tied.values()) == sum(season)


def test_split_rejects_bad_points():
    with pytest.raises(ValueError, match="at least one"):
        split_prizes({}, (100,))
    with pytest.raises(ValueError, match="points"):
        split_prizes({"a": True}, (100,))
    with pytest.raises(ValueError, match="points"):
        split_prizes({"a": float("nan")}, (100,))


# --- ledger snapshots: random assignments and season standings ---------------------------

def evidence(day=0, key="synthetic"):
    return Provenance(source="synthetic", source_version="fixture-v1", source_record_id=key,
                      observed_at=at(day), available_at=at(day), ingested_at=at(day))


def roster(entry):
    bands = (Band.TOP4, Band.TOP8, Band.TOP16, Band.TOP32, Band.UNSEEDED)
    return tuple(Pair(primary=Selection(player_id=PlayerId(f"atp:{entry}{i}"), band=band))
                 for i, band in enumerate(bands))


def record(entry, key, payload, day):
    return LedgerRecord(record_id=f"{entry}:{key}", entry_id=entry, event_id="australian_open",
                        effective_at=at(day), evidence=evidence(day, key), payload=payload)


def test_random_assignment_scores_for_season_but_not_event_prizes():
    with pytest.warns(ProvisionalRulesWarning):
        state = SeasonLedger.create(
            (EventTerms(event_id="australian_open", deadline=at(10), provenance=evidence()),),
            allow_provisional=True)
    entries = [f"entry:{c}" for c in "abcdef"]
    for entry in entries[:5]:
        state = state.append(
            record(entry, "s", Submitted(picks=roster(entry[-1]), submitted_at=at(1), excel=True), 1),
            record(entry, "a", Accepted(submission_id=f"{entry}:s", approved_by="synthetic"), 2))
    random = tuple(pair.primary for pair in roster("z"))
    state = state.append(record("entry:f", "m", Missed(assignments=random, approved_by="synthetic"), 11))
    points = dict(zip(entries, (40, 30, 20, 10, 5, 99)))
    basis = {item.entry_id: item.accounting_digest for item in state.replay(at(20)).events}
    state = state.append(*(record(entry, "p", EventPoints(points=total, accounting_digest=basis[entry]), 15)
                           for entry, total in points.items()))
    snapshot = state.replay(at(20))
    table = event_payouts(snapshot, "australian_open", config(6, small_override()),
                          allow_provisional=True)
    # The random-assigned top score is excluded before ranking for the event prize.
    assert table.excluded == ("entry:f",)
    assert payouts(table.awards) == {"entry:a": 200, "entry:b": 100, "entry:c": 0,
                                     "entry:d": 0, "entry:e": 0}
    assert table.awards[0].position == 1
    # ...but its points still count toward the season standings.
    assert {e.entry_id: e.season_points for e in snapshot.entries}["entry:f"] == 99


def snapshot_for(rows, events=EVENTS, eligible=lambda entry, event: True, recorded=True, bonus=()):
    """Direct snapshot fixture: rows maps entry -> per-event points."""
    with pytest.warns(ProvisionalRulesWarning):
        rules = SeasonLedger.create(
            (EventTerms(event_id="paris", deadline=at(10), provenance=evidence()),),
            allow_provisional=True).rules
    states = tuple(
        EventState(entry_id=entry, event_id=event, submitted=(), accepted_submission_id=None,
                   accepted_picks=(), selections=(), accounting_digest=f"{entry}:{event}",
                   event_payout_eligible=eligible(entry, event), qualifying_excel=False,
                   season_points=points, points_recorded=recorded)
        for entry, points in rows.items() for event in events)
    entries = tuple(
        EntryState(entry_id=entry, slam=(4, 4, 4, 4), masters=(9, 9, 9, 7), usage=(),
                   submission_bonus=250 if entry in bonus else 0,
                   season_points=points * len(events) + (250 if entry in bonus else 0))
        for entry, points in rows.items())
    return LedgerSnapshot(cutoff=at(400), entries=entries, events=states, rules=rules,
                          history_digest="synthetic")


def test_season_payouts_include_bonus_and_random_assigned_entries():
    rows = {"a": 10, "b": 10, "c": 9, "d": 8, "e": 7, "f": 1}
    snapshot = snapshot_for(rows, eligible=lambda entry, event: entry != "c", bonus=("b",))
    table = season_payouts(snapshot, config(6, small_override()), allow_provisional=True)
    assert table.scope == "season"
    assert table.excluded == ()
    # b's Excel bonus breaks the tie with a; c's random-assigned events still count.
    assert [award.entry_id for award in table.awards] == ["b", "a", "c", "d", "e", "f"]
    assert payouts(table.awards) == dict(zip("bacdef", (5633, 5302, 5110, 5055, 5000, 0)))
    assert sum(payouts(table.awards).values()) == 6 * 5000 - 13 * 300


def test_payout_tables_require_complete_matching_evidence():
    rows = {c: 1 for c in "abcdef"}
    six = config(6, small_override())
    with pytest.raises(ValueError, match="participant count"):
        season_payouts(snapshot_for({c: 1 for c in "abcde"}), six, allow_provisional=True)
    with pytest.raises(ValueError, match="Incomplete"):
        season_payouts(snapshot_for(rows, events=EVENTS[:-1]), six, allow_provisional=True)
    with pytest.raises(ValueError, match="Incomplete"):
        event_payouts(snapshot_for(rows, recorded=False), "paris", six, allow_provisional=True)
    with pytest.raises(ValueError, match="Incomplete"):
        event_payouts(snapshot_for(rows, events=("rome",)), "paris", six, allow_provisional=True)
    with pytest.raises(ValueError, match="Unknown pool event"):
        event_payouts(snapshot_for(rows), "queens", six, allow_provisional=True)


def test_payout_tables_reject_forged_configuration():
    rows = {c: 1 for c in "abcdef"}
    forged = replace(config(6, small_override()), season_prizes_cents=(9000, 0, 0, 0, 0, 0))
    with pytest.raises(ValueError, match="configuration"):
        season_payouts(snapshot_for(rows), forged, allow_provisional=True)
    with pytest.raises(UnresolvedRulesError):
        season_payouts(snapshot_for(rows), config(6, small_override()))


def test_payout_table_is_auditable():
    table = season_payouts(snapshot_for({c: 1 for c in "abcdef"}),
                           config(6, small_override()), allow_provisional=True)
    assert table.config_version == "override:adj-1"
    assert table.source_history_digest == "synthetic"
    assert len(table.input_digest) == 64
    assert type(table).from_dict(json.loads(json.dumps(table.to_dict()))) == table


# --- optimizer outlook: payout separate from top-three probability and points ------------

def test_outlook_reports_expected_payout_separately():
    eighty = config(80)
    rivals = {f"r{i}": 0 for i in range(77)}
    samples = [
        {"me": 50, "x": 40, "y": 30} | rivals,   # 1st: $70
        {"me": 30, "x": 40, "y": 30} | rivals,   # tied 2nd: ($35 + $20) / 2
        {"me": 10, "x": 40, "y": 30} | rivals,   # 3rd alone: $20
        {"me": 0, "x": 40, "y": 30} | rivals,    # tied 3rd with 77 rivals: $20 / 78
    ]
    with pytest.warns(ProvisionalRulesWarning):
        result = outlook(samples, "me", eighty, allow_provisional=True)
    assert result.simulations == 4
    assert result.expected_points == pytest.approx(22.5)
    assert result.p_top3 == pytest.approx(1.0)
    assert result.expected_payout_cents == pytest.approx((7000 + 2750 + 2000 + 2000 / 78) / 4)
    assert result.scope == "event"


def test_outlook_top3_and_payout_can_disagree():
    six = config(6, small_override())
    samples = [{"me": 5, "a": 9, "b": 9, "c": 9, "d": 0, "e": 0}] * 3 + \
              [{"me": 9, "a": 9, "b": 9, "c": 9, "d": 0, "e": 0}]
    with pytest.warns(ProvisionalRulesWarning):
        result = outlook(samples, "me", six, allow_provisional=True)
    # A four-way tie for first is a top-three finish worth a quarter of the pool.
    assert result.p_top3 == pytest.approx(0.25)
    assert result.expected_payout_cents == pytest.approx(300 / 4 / 4)
    with pytest.warns(ProvisionalRulesWarning):
        season = outlook(samples, "me", six, scope="season", allow_provisional=True)
    assert season.expected_payout_cents == pytest.approx(
        (3 * 5055 + sum(six.season_prizes_cents[:4]) / 4) / 4)


def test_outlook_excludes_ineligible_rivals_from_event_ranking():
    six = config(6, small_override())
    samples = [{"me": 5, "rand": 99, "a": 1, "b": 1, "c": 1, "d": 1}]
    with pytest.warns(ProvisionalRulesWarning):
        result = outlook(samples, "me", six, ineligible=frozenset({"rand"}),
                         allow_provisional=True)
    assert result.expected_payout_cents == 200
    with pytest.warns(ProvisionalRulesWarning):
        season = outlook(samples, "me", six, scope="season", ineligible=frozenset({"rand"}),
                         allow_provisional=True)
    assert season.expected_payout_cents == six.season_prizes_cents[1]


@pytest.mark.parametrize("kwargs, message", [
    ({"samples": []}, "at least one"),
    ({"samples": [{"me": 1}]}, "participant count"),
    ({"samples": [{"x": 1, "a": 1, "b": 1, "c": 1, "d": 1, "e": 1}]}, "participant count"),
    ({"ineligible": frozenset({"me"})}, "ineligible"),
    ({"ineligible": frozenset({"zz"})}, "Unknown"),
    ({"scope": "weekly"}, "scope"),
])
def test_outlook_rejects_inconsistent_inputs(kwargs, message):
    six = config(6, small_override())
    args = {"samples": [{c: 1 for c in ("me", "a", "b", "c", "d", "e")}]} | kwargs
    with pytest.warns(ProvisionalRulesWarning), pytest.raises(ValueError, match=message):
        outlook(args.pop("samples"), "me", six, allow_provisional=True, **args)
