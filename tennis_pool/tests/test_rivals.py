"""Synthetic rival-selection and ownership-evaluation cases; invented entries and players only."""

from datetime import date, datetime, timedelta, timezone
import warnings

import numpy as np
import pytest

from tennis_api.models.canonical import (
    Draw, DrawSlot, EntryKind, Event, EventId, PlayerId, Provenance, Surface, Tour,
)
from tennis_pool.ledger import (
    Accepted, Band, EventTerms, LedgerRecord, Pair, SeasonLedger, Selection, Submitted,
)
from tennis_pool.optimizer import ScenarioAssumptions, ScenarioSet, evaluate
from tennis_pool.rivals import (
    AppealSnapshot, KnownPick, OwnershipCase, RivalModelParameters, RivalReport, RivalStatus,
    evaluate_ownership, model_rival_field, project_ownership,
)
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError
from tennis_pool.substitutions import seed_band


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
DEADLINES = {"indian_wells": 3, "miami": 4, "monte_carlo": 5, "madrid": 6, "rome": 7,
             "australian_open": 10, "roland_garros": 40, "wimbledon": 70, "us_open": 100}
RIVALS = ("entry:a", "entry:b", "entry:c")
FAST = RivalModelParameters(worlds=64)


@pytest.fixture(autouse=True)
def quiet_provisional_rules():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalRulesWarning)
        yield


def at(day):
    return START + timedelta(days=day)


def evidence(day=0, key="synthetic"):
    return Provenance(source="synthetic", source_version="fixture-v1", source_record_id=key,
                      observed_at=at(day), available_at=at(day), ingested_at=at(day))


def pid(number):
    return PlayerId(f"atp:p{number}")


def seed_of(number):
    return number if number <= 16 else None


def selection(number):
    return Selection(player_id=pid(number), band=seed_band(seed_of(number)))


def sheet(*numbers, subs=None):
    subs = subs or {}
    return tuple(Pair(primary=selection(n), substitute=selection(subs[n]) if n in subs else None)
                 for n in numbers)


def draw(event="roland_garros"):
    day = DEADLINES[event]
    meta = Event(event_id=EventId(f"test:{event}"), name="Synthetic", tour=Tour.ATP,
                 start_date=at(day).date(), end_date=at(day + 14).date(), surface=Surface.CLAY,
                 best_of=5, round_count=5, level="fixture", provenance=evidence())
    slots = tuple(DrawSlot(position=i, kind=EntryKind.PLAYER, player_id=pid(i), seed=seed_of(i))
                  for i in range(1, 33))
    return Draw(event=meta, slots=slots, provenance=evidence())


TERMS = {event: EventTerms(event_id=event, deadline=at(day), provenance=evidence())
         for event, day in DEADLINES.items()}


def accepted(entry, event, picks, day=None, lag=0.5):
    day = DEADLINES[event] - 1 if day is None else day
    key = f"{entry}:{event}"
    return (
        LedgerRecord(record_id=key + ":s", entry_id=entry, event_id=event, effective_at=at(day),
                     evidence=evidence(day, key + ":s"),
                     payload=Submitted(picks=picks, submitted_at=at(day), excel=True)),
        LedgerRecord(record_id=key + ":a", entry_id=entry, event_id=event,
                     effective_at=at(day + lag), evidence=evidence(day + lag, key + ":a"),
                     payload=Accepted(submission_id=key + ":s", approved_by="synthetic authority")),
    )


def season(*records):
    ledger = SeasonLedger.create(tuple(TERMS.values()), allow_provisional=True)
    return ledger.append(*(r for group in records for r in group))


def history():
    """Entries a and b have Slam history; c has none."""
    return [accepted("entry:a", "australian_open", sheet(1, 5, 9, 17, 18, subs={17: 19})),
            accepted("entry:b", "australian_open", sheet(2, 6, 10, 20, 21))]


def appeal(event="roland_garros", day=0):
    return AppealSnapshot(event_id=event, values=tuple((pid(n), 100.0 / n) for n in range(1, 33)),
                          basis="synthetic strength", provenance=evidence(day, "appeal"))


def window(event="roland_garros"):
    deadline = DEADLINES[event]
    return {"starts_at": at(deadline + 0.5), "cutoff": at(deadline - 0.25)}


def project(ledger, event="roland_garros", **kwargs):
    options = dict(window(event), rival_ids=RIVALS, appeal=appeal(event), seed=3,
                   parameters=FAST, allow_provisional=True)
    options.update(kwargs)
    return project_ownership(ledger, draw(event), TERMS[event], **options)


def scenarios(seed=0, runs=300, withdrawn=None):
    rng = np.random.default_rng(seed)
    points = rng.integers(0, 400, size=(32, runs)).astype(np.int64)
    flags = np.zeros((32, runs), dtype=bool) if withdrawn is None else withdrawn
    points[flags] = 0
    return ScenarioSet(
        player_ids=tuple(pid(i) for i in range(1, 33)),
        seeds=tuple(seed_of(i) for i in range(1, 33)), points=points, withdrawn=flags,
        assumptions=ScenarioAssumptions(
            source="synthetic arrays", simulations=runs, seed=None, kind=None, draw_digest=None,
            withdrawal_model="fixture flags", withdrawal_probabilities=(), withdrawal_patterns=1))


def field(scenario_set, ledger=None, **kwargs):
    options = dict(window(), rival_ids=RIVALS, seed=11, parameters=FAST, allow_provisional=True)
    options.update(kwargs)
    return model_rival_field(scenario_set, ledger or season(*history()), draw(),
                             TERMS["roland_garros"], **options)


def known(entry, pair, day, key="leak"):
    return KnownPick(entry_id=entry, event_id="roland_garros", pair=pair,
                     provenance=evidence(day, key))


def test_known_picks_need_strictly_earlier_availability_than_cutoff_and_start():
    cutoff = window()["cutoff"]
    picks = (
        KnownPick(entry_id="entry:a", event_id="roland_garros", pair=sheet(1)[0],
                  provenance=Provenance(source="synthetic", source_version="v1",
                                        source_record_id="early", observed_at=None,
                                        available_at=cutoff - timedelta(microseconds=1),
                                        ingested_at=cutoff)),
        known("entry:a", sheet(5)[0], 39.75, "at-cutoff"),          # exactly the cutoff
        known("entry:b", sheet(2)[0], 40.5, "at-start"),            # exactly the start
        known("entry:b", sheet(3)[0], 45, "late"),
        KnownPick(entry_id="entry:b", event_id="wimbledon", pair=sheet(4)[0],
                  provenance=evidence(1, "other-event")),
    )
    report = project(season(*history()), known_picks=picks)
    rivals = {r.entry_id: r for r in report.rivals}
    assert (report.known_picks_used, report.excluded_after_cutoff,
            report.excluded_at_or_after_start) == (1, 1, 2)
    assert rivals["entry:a"].status is RivalStatus.PARTIAL and rivals["entry:a"].known_pairs == 1
    assert rivals["entry:b"].known_pairs == 0
    ownership = {p.player_id: p for p in report.ownership}
    assert ownership[pid(1)].known == 1 and ownership[pid(5)].known == 0
    assert ownership[pid(1)].expected >= 1 / 3

    # When play starts before the cutoff, a pick revealed in between stays hidden.
    late_start = project(season(*history()), starts_at=at(39.5),
                         known_picks=(known("entry:a", sheet(1)[0], 39.6, "after-start"),))
    assert (late_start.known_picks_used, late_start.excluded_at_or_after_start) == (0, 1)
    assert late_start.visible_before == at(39.5)


def test_analysis_and_its_inputs_must_precede_the_deadline_and_start():
    ledger = season(*history())
    with pytest.raises(ValueError, match="before-deadline"):
        project(ledger, cutoff=at(40.1))
    with pytest.raises(ValueError, match="Appeal evidence"):
        project(ledger, appeal=appeal(day=39.9))
    with pytest.raises(ValueError, match="Draw and event terms"):
        project(ledger, starts_at=at(-1))
    with pytest.raises(ValueError, match="timezone"):
        project(ledger, cutoff=datetime(2026, 2, 9))
    with pytest.raises(ValueError, match="season ledger"):
        project_ownership(ledger, draw(), EventTerms(event_id="roland_garros", deadline=at(41),
                                                     provenance=evidence()),
                          **window(), rival_ids=RIVALS, appeal=appeal(), seed=0,
                          allow_provisional=True)
    with pytest.raises(ValueError, match="distinct entry IDs"):
        project(ledger, rival_ids=("entry:a", "entry:a"))
    with pytest.raises(UnresolvedRulesError):
        project(ledger, allow_provisional=False)


def test_banks_use_caps_and_same_band_substitutes_hold_in_every_sampled_sheet():
    masters = ("indian_wells", "miami", "monte_carlo", "madrid", "rome")
    records = [accepted("entry:a", event, sheet(5, 9, 17, 18, 19, subs={17: 20, 9: 10}))
               for event in masters]
    records.append(accepted("entry:a", "australian_open", sheet(1, 2, 3, 4, 20)))
    model = field(scenarios(), season(*records),
                  parameters=RivalModelParameters(worlds=200))
    summary = model.report.rivals[0]
    assert summary.bank == (0, 4, 4, 4)
    index = {p: i for i, p in enumerate(model.player_ids)}
    top4 = {index[pid(n)] for n in range(1, 5)}
    none = len(model.player_ids)
    bands = [seed_band(seed_of(n)) for n in range(1, 33)]
    for r in range(len(RIVALS)):
        for world in range(200):
            chosen = model.primaries[r, world].tolist()
            covers = [s for s in model.substitutes[r, world].tolist() if s != none]
            assert len(set(chosen + covers)) == len(chosen) + len(covers) == 5 + len(covers)
            for p, s in zip(chosen, model.substitutes[r, world].tolist()):
                assert s == none or bands[s] is bands[p]
            if r == 0:
                assert not top4 & set(chosen + covers)
                assert index[pid(5)] not in chosen + covers
    assert (model.substitutes[0] != none).any()


def test_known_sheet_scores_exactly_with_substitute_activation():
    withdrawn = np.zeros((32, 300), dtype=bool)
    withdrawn[0, ::3] = True
    scenario_set = scenarios(withdrawn=withdrawn)
    pairs = sheet(1, 5, 9, 17, 18, subs={1: 2})
    picks = tuple(known("entry:c", pair, 20, f"k{i}") for i, pair in enumerate(pairs))
    model = field(scenario_set, known_picks=picks)
    rivals = {r.entry_id: r for r in model.report.rivals}
    assert rivals["entry:c"].status is RivalStatus.KNOWN
    assert rivals["entry:a"].status is RivalStatus.ESTIMATED
    points = scenario_set.points
    expected = np.where(withdrawn[0], points[1], points[0]) + points[[4, 8, 16, 17]].sum(axis=0)
    assert np.array_equal(model.field.scores[2], expected)
    assert model.field.assumptions.scenario_digest == scenario_set.digest
    metrics = evaluate(scenario_set, sheet(3, 6, 10, 19, 20), rivals=model.field,
                       allow_provisional=True)
    assert metrics.p_top3 is not None
    with pytest.raises(ValueError, match="exact scenarios"):
        evaluate(scenarios(seed=1), sheet(3, 6, 10, 19, 20), rivals=model.field,
                 allow_provisional=True)


def test_selection_draws_are_independent_of_tournament_outcomes_for_a_fixed_appeal():
    first = field(scenarios(seed=0), appeal=appeal())
    second = field(scenarios(seed=99), appeal=appeal())
    for name in ("primaries", "substitutes", "world_of_scenario"):
        assert np.array_equal(getattr(first, name), getattr(second, name))
    assert not np.array_equal(first.field.scores, second.field.scores)
    reseeded = field(scenarios(seed=0), appeal=appeal(), seed=12)
    assert not np.array_equal(first.primaries, reseeded.primaries)
    # Sharing an integer with the scenario seed does not share a stream.
    world = np.random.default_rng(np.random.SeedSequence(11).spawn(2)[1]).integers(
        64, size=300)
    assert not np.array_equal(first.world_of_scenario, world)
    assert not first.primaries.flags.writeable
    with pytest.raises(ValueError, match="seed"):
        field(scenarios(), seed=-1)


def test_missing_history_is_labelled_and_gets_broader_uncertainty():
    report = project(season(*history()), parameters=RivalModelParameters(worlds=400))
    rivals = {r.entry_id: r for r in report.rivals}
    assert rivals["entry:a"].status is RivalStatus.ESTIMATED
    assert rivals["entry:c"].status is RivalStatus.NO_HISTORY
    assert not rivals["entry:c"].ledger_state and rivals["entry:a"].ledger_state
    assert rivals["entry:c"].personal_noise > rivals["entry:a"].personal_noise
    lines = report.describe()
    assert any(line.startswith("entry:c [NO_HISTORY]") and "full bank assumed" in line
               for line in lines)
    assert any(line.startswith("entry:a [ESTIMATED]") for line in lines)

    assert rivals["entry:c"].pick_certainty < rivals["entry:a"].pick_certainty < 1
    known_sheet = tuple(known("entry:b", pair, 20, f"k{i}")
                        for i, pair in enumerate(sheet(2, 6, 10, 20, 21)))
    assert {r.entry_id: r for r in project(season(*history()), known_picks=known_sheet).rivals
            }["entry:b"].pick_certainty == 1
    assert rivals["entry:a"].structure_basis.startswith("own slam history")

    # Masters history informs substitute habit and noise but not Slam band structures.
    masters = season(accepted("entry:c", "rome", sheet(5, 9, 17, 18, 19)))
    summary = {r.entry_id: r for r in project(masters).rivals}["entry:c"]
    assert summary.status is RivalStatus.ESTIMATED
    assert (summary.history_events, summary.structure_events) == (1, 0)
    assert summary.structure_basis.startswith("uniform")


def test_acceptance_recorded_before_the_cutoff_is_known_and_refunded():
    early = accepted("entry:b", "roland_garros", sheet(2, 6, 10, 20, 21, subs={20: 22}), day=30)
    report = project(season(*history(), early))
    rivals = {r.entry_id: r for r in report.rivals}
    assert rivals["entry:b"].status is RivalStatus.KNOWN
    assert rivals["entry:b"].bank == (3, 3, 3, 4)  # only the Australian Open debit remains
    with pytest.raises(ValueError, match="distinct, non-overlapping"):
        project(season(*history(), early),
                known_picks=(known("entry:b", sheet(3)[0], 31, "extra"),))


def test_expiring_bank_is_spent_at_the_last_event_of_its_kind():
    ledger = season()
    spent = project(ledger, event="us_open", parameters=RivalModelParameters(worlds=100))
    unseeded = sum(p.expected for p in spent.ownership if p.band is Band.UNSEEDED)
    assert unseeded == 0
    habit = project(ledger, event="us_open",
                    parameters=RivalModelParameters(worlds=100, spend_expiring_bank=False))
    assert sum(p.expected for p in habit.ownership if p.band is Band.UNSEEDED) > 0


def test_known_picks_are_validated_against_draw_band_bank_and_rivals():
    ledger = season(*history())
    bad = (
        (KnownPick(entry_id="entry:z", event_id="roland_garros", pair=sheet(1)[0],
                   provenance=evidence(1, "z")), "outside the rival list"),
        (known("entry:a", Pair(primary=Selection(player_id=pid(1), band=Band.TOP8)), 1),
         "seed band"),
        (known("entry:a", Pair(primary=selection(40 - 7)), 1), "seed band"),
        (known("entry:a", Pair(primary=selection(1), substitute=selection(5)), 1), "share"),
    )
    for pick, message in bad:
        with pytest.raises(ValueError, match=message):
            project(ledger, known_picks=(pick,))
    with pytest.raises(ValueError, match="draw players"):
        project(ledger, known_picks=(known("entry:a", Pair(primary=Selection(
            player_id=pid(40), band=Band.UNSEEDED)), 1),))
    burned = season(accepted("entry:a", "australian_open", sheet(1, 2, 3, 4, 17)))
    with pytest.raises(ValueError, match="remaining bank"):
        project(burned, known_picks=(known("entry:a", sheet(1)[0], 1),))
    with pytest.raises(ValueError, match="outside the draw"):
        project(ledger, appeal=AppealSnapshot(
            event_id="roland_garros", values=((pid(40), 1.0),), basis="x",
            provenance=evidence()))


def test_appeal_floor_and_default_are_disclosed():
    partial = AppealSnapshot(event_id="roland_garros", values=((pid(1), 10.0), (pid(2), 4.0)),
                             basis="two favourites", provenance=evidence())
    report = project(season(*history()), appeal=partial)
    assert report.appeal_missing == 30 and report.appeal_basis == "two favourites"
    model = field(scenarios())
    assert "ex-ante" in model.report.appeal_basis
    with pytest.raises(ValueError, match="positive"):
        AppealSnapshot(event_id="roland_garros", values=((pid(1), 0.0),), basis="x",
                       provenance=evidence())


def test_reports_are_reproducible_and_round_trip():
    ledger = season(*history())
    first, second = project(ledger), project(ledger)
    assert first == second
    assert RivalReport.from_dict(first.to_dict()) == first
    assert project(ledger, seed=4) != first
    with pytest.raises(ValueError, match="parameters"):
        RivalModelParameters(worlds=0)


def outcome_records(rg_sheets):
    return [accepted(entry, "roland_garros", picks, day=39.9, lag=1.0)
            for entry, picks in rg_sheets.items()]


def test_ownership_evaluation_is_walk_forward_with_separate_ownership_metrics():
    case = OwnershipCase(draw=draw(), terms=TERMS["roland_garros"], starts_at=at(40.5),
                         cutoff=at(39.5), outcome_cutoff=at(45), appeal=appeal())
    chalk = {"entry:a": sheet(1, 5, 9, 17, 18), "entry:b": sheet(1, 6, 10, 17, 21)}
    fade = {"entry:a": sheet(4, 8, 16, 31, 32), "entry:b": sheet(3, 7, 15, 30, 29)}
    hint = (known("entry:a", sheet(1)[0], 39, "hint"),)
    results = {}
    for name, sheets in (("chalk", chalk), ("fade", fade)):
        ledger = season(*history(), *outcome_records(sheets))
        # The projection at the cutoff cannot see the accepted sheets it is scored on.
        assert project(ledger, cutoff=at(39.5), known_picks=hint) == project(
            season(*history()), cutoff=at(39.5), known_picks=hint)
        results[name] = evaluate_ownership(ledger, (case,), rival_ids=RIVALS, seed=5,
                                           known_picks=hint, parameters=FAST,
                                           allow_provisional=True)
    chalk_eval = results["chalk"]
    event = chalk_eval.events[0]
    assert (event.scored_rivals, event.unscored_rivals, event.known_rivals) == (2, 1, 0)
    assert event.forecasts == chalk_eval.forecasts == 2 * 32 - 1  # entry:a's known pick excluded
    assert event.known_pick_mismatches == 0
    assert results["fade"].events[0].known_pick_mismatches == 1
    assert sum(b.forecasts for b in chalk_eval.reliability) == chalk_eval.forecasts
    assert 0 <= chalk_eval.brier < results["fade"].brier <= 1
    assert chalk_eval.ownership_mae < results["fade"].ownership_mae
    assert chalk_eval.band_leader_hits > results["fade"].band_leader_hits
    assert 0 <= chalk_eval.interval_coverage <= 1
    assert "No match results" in chalk_eval.scope
    assert type(chalk_eval).from_dict(chalk_eval.to_dict()) == chalk_eval


def test_evaluation_ignores_entries_outside_the_rival_list():
    case = OwnershipCase(draw=draw(), terms=TERMS["roland_garros"], starts_at=at(40.5),
                         cutoff=at(39.5), outcome_cutoff=at(45), appeal=appeal())
    stranger = Pair(primary=Selection(player_id=pid(99), band=Band.UNSEEDED))
    ledger = season(*history(), *outcome_records({
        "entry:a": sheet(1, 5, 9, 17, 18),
        "entry:z": sheet(1, 5, 9, 17) + (stranger,)}))
    result = evaluate_ownership(ledger, (case,), rival_ids=("entry:a",), seed=0,
                                parameters=FAST, allow_provisional=True)
    assert result.events[0].scored_rivals == 1
    with pytest.raises(ValueError, match="outside the case draw"):
        evaluate_ownership(ledger, (case,), rival_ids=("entry:a", "entry:z"), seed=0,
                           parameters=FAST, allow_provisional=True)


def test_ownership_cases_must_read_outcomes_after_the_deadline():
    with pytest.raises(ValueError, match="after the deadline"):
        OwnershipCase(draw=draw(), terms=TERMS["roland_garros"], starts_at=at(40.5),
                      cutoff=at(39.5), outcome_cutoff=at(40), appeal=appeal())
    case = OwnershipCase(draw=draw(), terms=TERMS["roland_garros"], starts_at=at(40.5),
                         cutoff=at(39.5), outcome_cutoff=at(45), appeal=appeal())
    with pytest.raises(ValueError, match="bins"):
        evaluate_ownership(season(), (case,), rival_ids=RIVALS, seed=0, bins=0,
                           allow_provisional=True)
    empty = evaluate_ownership(season(), (case,), rival_ids=RIVALS, seed=0, parameters=FAST,
                               allow_provisional=True)
    assert empty.forecasts == 0 and empty.brier is None and empty.events[0].unscored_rivals == 3
