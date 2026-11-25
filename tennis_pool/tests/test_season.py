"""Synthetic season-planning cases; invented players and entries only."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import warnings

import numpy as np
import pytest

from tennis_api.models.canonical import (
    Draw, DrawSlot, EntryKind, Event, EventId, PlayerId, Provenance, Surface, Tour,
)
from tennis_pool.ledger import Band, EntryState, EventTerms, SeasonLedger
from tennis_pool.optimizer import ScenarioAssumptions, ScenarioSet
from tennis_pool.payouts import payout_config, split_prizes
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError
from tennis_pool.season import (
    EventOutcome, FutureEvent, PlanningParameters, Policy, Prospect, ReplayEvent,
    SeasonObjective, SeasonPlan, plan_event, ration, replay_season,
)


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
SLAMS = ("australian_open", "roland_garros", "wimbledon", "us_open")
PARAMS = PlanningParameters(planning_worlds=40, evaluation_worlds=120)
BASE = [34, 32, 31, 30, 26, 25, 24, 23, 20, 19, 18, 17, 16, 15, 14, 13]


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


CALENDAR = tuple(EventTerms(event_id=e, deadline=at(20 + 40 * i), provenance=evidence(0, e))
                 for i, e in enumerate(SLAMS))


def terms(event):
    return next(t for t in CALENDAR if t.event_id == event)


def draw(day=0):
    event = Event(event_id=EventId("test:slam"), name="Synthetic", tour=Tour.ATP,
                  start_date=date(2026, 1, 2), end_date=date(2026, 1, 9), surface=Surface.HARD,
                  best_of=5, round_count=4, level="fixture", provenance=evidence(day))
    slots = tuple(DrawSlot(position=i, kind=EntryKind.PLAYER, player_id=pid(i),
                           seed=i if i <= 8 else None) for i in range(1, 17))
    return Draw(event=event, slots=slots, provenance=evidence(day))


def scenarios(means, runs=300, seed=0, withdraw=0.0):
    rng = np.random.default_rng(seed)
    means = np.asarray(means, dtype=float)
    points = rng.gamma(2.0, means[:, None] / 2.0, size=(16, runs)).astype(np.int64)
    withdrawn = rng.random((16, runs)) < withdraw
    points = np.where(withdrawn, 0, points)
    return ScenarioSet(
        player_ids=tuple(pid(i) for i in range(1, 17)),
        seeds=tuple(i if i <= 8 else None for i in range(1, 17)),
        points=points, withdrawn=withdrawn,
        assumptions=ScenarioAssumptions(
            source="synthetic", simulations=runs, seed=seed, kind=None, draw_digest=None,
            withdrawal_model="fixture flags", withdrawal_probabilities=(),
            withdrawal_patterns=1),
    )


def future(event, means=BASE, day=0, entry=0.9, ranks=None):
    ranks = ranks or list(range(1, 17))
    return FutureEvent(event_id=event, available_at=at(day), prospects=tuple(
        Prospect(player_id=pid(i + 1), entry_probability=entry, rank=ranks[i],
                 mean_points=m) for i, m in enumerate(means)))


def futures(after, special=None, day=0):
    special = special or {}
    later = SLAMS[SLAMS.index(after) + 1:]
    return tuple(special.get(e) or future(e, day=day) for e in later)


def entry(slam=(4, 4, 4, 4), usage=(), points=0):
    return EntryState(entry_id="entry:own", slam=slam, masters=(9, 9, 9, 7), usage=usage,
                      season_points=points)


def plan(event="australian_open", means=BASE, own=None, special=None, **kwargs):
    kwargs.setdefault("parameters", PARAMS)
    kwargs.setdefault("allow_provisional", True)
    return plan_event(
        scenarios(means), draw(), terms(event), cutoff=terms(event).deadline - timedelta(days=1),
        entry=own or entry(), calendar=CALENDAR, future=futures(event, special), seed=11,
        **kwargs)


def projection(result, policy):
    return next(p for p in result.projections if p.policy is policy)


def star_at_wimbledon():
    return {"wimbledon": future("wimbledon", means=[220] + BASE[1:], entry=0.95)}


def test_ration_is_a_fair_share_that_spends_everything_at_the_last_event():
    assert ration((4, 4, 4, 4), (4, 4, 4, 4)) == (1, 1, 1, 1)
    assert ration((3, 2, 4, 0), (2, 2, 3, 2)) == (2, 1, 2, 0)
    assert ration((3, 2, 4, 1), (1, 1, 1, 0)) == (3, 2, 4, 1)
    # The stale reference appended a second US Open, so Wimbledon saw three Slams left.
    assert ration((3, 3, 3, 3), (2, 2, 2, 2)) == (2, 2, 2, 2)
    with pytest.raises(ValueError):
        ration((1, 2, 3), (1, 1, 1))


def test_horizon_preserves_a_top_band_token_for_a_dominant_future_favourite():
    result = plan(own=entry(slam=(1, 4, 4, 4)), special=star_at_wimbledon())
    greedy, horizon = projection(result, Policy.GREEDY), projection(result, Policy.HORIZON)
    assert greedy.spend[0] == 1 and horizon.spend[0] == 0
    assert horizon.gap_to_best == 0 and greedy.gap_to_best > 2 * greedy.gap_se > 0
    assert result.chosen is Policy.HORIZON
    assert result.recommendation == horizon.recommendation
    top4 = next(c for c in result.token_costs if c.band is Band.TOP4)
    assert top4.advice == "preserve" and top4.planned_spend == 0
    assert top4.value_later > top4.gain_now > 0
    assert "Preserve the token" in top4.explanation and "1 left" in top4.explanation


def test_horizon_preserves_a_last_use_for_a_much_better_later_chance():
    usage = ((pid(9), 4),)
    means = BASE[:8] + [40] + BASE[9:]
    special = {"wimbledon": future("wimbledon", means=BASE[:8] + [200] + BASE[9:],
                                   entry=0.95, ranks=list(range(1, 9)) + [12] + list(range(9, 16)))}
    result = plan(means=means, own=entry(usage=usage), special=special)
    greedy, horizon = projection(result, Policy.GREEDY), projection(result, Policy.HORIZON)
    assert pid(9) in {p.primary.player_id for p in greedy.recommendation.best.pairs}
    picked = {p.primary.player_id for p in horizon.recommendation.best.pairs}
    covers = {p.substitute.player_id for p in horizon.recommendation.best.pairs if p.substitute}
    assert horizon.preserved == (pid(9),) and pid(9) not in picked | covers
    cost = next(c for c in result.use_costs if c.player_id == pid(9))
    assert cost.advice == "preserve" and not cost.in_plan and cost.uses_left == 1
    assert cost.value_later > cost.edge_now + 2 * cost.value_later_se
    assert cost.later_events[0][0] == "wimbledon"
    assert "Preserve the use" in cost.explanation


def test_plentiful_uses_and_expiring_tokens_are_spent():
    result = plan(event="us_open")
    horizon = projection(result, Policy.HORIZON)
    assert horizon.spend == projection(result, Policy.GREEDY).spend
    assert horizon.future_expected_points == 0
    for cost in result.token_costs:
        if cost.planned_spend:
            assert cost.value_later == 0 and cost.advice == "spend"
    assert all(c.advice == "spend" and c.value_later == 0 for c in result.use_costs)


def test_rationed_policy_never_exceeds_its_fair_share():
    result = plan()
    rationed = projection(result, Policy.RATIONED)
    assert all(s <= c for s, c in zip(rationed.spend, ration((4, 4, 4, 4), (4, 4, 4, 4))))


def test_calendar_and_information_cutoffs_fail_closed():
    event = terms("roland_garros")
    cutoff = event.deadline - timedelta(days=1)

    def attempt(**changes):
        kwargs = dict(cutoff=cutoff, entry=entry(), calendar=CALENDAR,
                      future=futures("roland_garros"), seed=1, parameters=PARAMS,
                      allow_provisional=True)
        kwargs.update(changes)
        return plan_event(scenarios(BASE), changes.pop("the_draw", draw()), event,
                          **{k: v for k, v in kwargs.items() if k != "the_draw"})

    duplicated = futures("roland_garros") + (future("us_open"),)
    with pytest.raises(ValueError, match="exactly once"):
        attempt(future=duplicated)
    with pytest.raises(ValueError, match="exactly once"):
        attempt(future=futures("roland_garros")[:1])
    with pytest.raises(ValueError, match="calendar"):
        attempt(calendar=CALENDAR + (CALENDAR[0],))
    late = futures("roland_garros")[:1] + (future("us_open", day=59),)
    with pytest.raises(ValueError, match="before the cutoff"):
        attempt(future=late)
    with pytest.raises(ValueError, match="draw"):
        plan_event(scenarios(BASE), draw(day=59), event, cutoff=cutoff, entry=entry(),
                   calendar=CALENDAR, future=futures("roland_garros"), seed=1,
                   parameters=PARAMS, allow_provisional=True)
    with pytest.raises(ValueError, match="precede"):
        attempt(cutoff=event.deadline)
    tied = CALENDAR[:3] + (replace(CALENDAR[3], deadline=CALENDAR[2].deadline),)
    with pytest.raises(ValueError, match="distinct"):
        attempt(calendar=tied)
    unknown = CALENDAR[:3] + (replace(CALENDAR[3], provenance=evidence(59, "us_open")),)
    with pytest.raises(ValueError, match="Calendar event terms"):
        attempt(calendar=unknown)


def test_strict_mode_blocks_on_provisional_rules():
    with pytest.raises(UnresolvedRulesError):
        plan(allow_provisional=False)


def test_plans_are_seed_reproducible_and_round_trip():
    first, second = plan(), plan()
    assert first == second
    assert SeasonPlan.from_dict(first.to_dict()) == first
    assumptions = first.assumptions
    assert assumptions.future_events == SLAMS[1:]
    assert assumptions.parameters == PARAMS and "dynamic programme" in assumptions.horizon_model


def standings():
    return tuple(EntryState(entry_id=f"entry:r{i:02d}", slam=(4, 4, 4, 4), masters=(9, 9, 9, 7),
                            usage=(), season_points=300 + 20 * i) for i in range(39))


def test_standing_objectives_report_uncertainty_and_named_rival_gaps():
    config = payout_config(40, allow_provisional=True)
    rivals = standings()
    rivals = (replace(rivals[0], season_points=0),
              replace(rivals[1], season_points=50_000)) + rivals[2:]
    named = ("entry:r00", "entry:r01")
    for objective in SeasonObjective:
        result = plan(own=entry(points=700), objective=objective, rival_states=rivals,
                      named_rivals=named, season_payout=config)
        for item in result.projections:
            assert 0 <= item.p_season_top3 <= 1 and 0 <= item.p_season_first <= 1
            assert item.expected_season_payout_cents >= 0 and item.season_payout_se_cents >= 0
            behind, ahead = item.rival_gaps
            assert behind.current_gap == 700 and behind.p_finish_ahead == 1
            assert ahead.current_gap == 700 - 50_000 and ahead.p_finish_ahead == 0
            assert ahead.expected_final_gap < 0 < behind.expected_final_gap
        assert result.assumptions.rival_model is not None
    default = plan(own=entry(points=700), rival_states=standings())
    gaps = projection(default, Policy.HORIZON).rival_gaps
    assert [g.entry_id for g in gaps] == ["entry:r23", "entry:r22", "entry:r21"]
    with pytest.raises(ValueError, match="rival entries"):
        plan(objective=SeasonObjective.P_TOP3)
    with pytest.raises(ValueError, match="participant"):
        plan(rival_states=standings()[:5], season_payout=config)


def ledger():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalRulesWarning)
        return SeasonLedger.create(CALENDAR[:3], allow_provisional=True)


def season(overrides=None, withdrawn=()):
    """Three replayed Slams with a dominant favourite revealed for Wimbledon."""
    rng = np.random.default_rng(5)
    events = []
    for i, name in enumerate(SLAMS[:3]):
        event = terms(name)
        cutoff = event.deadline - timedelta(days=1)
        means = [220] + BASE[1:] if name == "wimbledon" else BASE
        later = [future(e, day=1 + 40 * i) if e != "wimbledon"
                 else future(e, means=[220] + BASE[1:], entry=0.95, day=1 + 40 * i)
                 for e in SLAMS[i + 1:3]]
        realized = rng.gamma(2.0, np.array(means) / 2.0).astype(int)
        outcome = EventOutcome(
            revealed_at=event.deadline + timedelta(days=14),
            points=tuple((pid(k + 1), int(v)) for k, v in enumerate(realized)),
            withdrawn=withdrawn if i == 0 else (),
            rival_points=tuple((f"entry:r{k}", int(80 + 10 * k + i)) for k in range(3)))
        if overrides and name in overrides:
            outcome = overrides[name]
        events.append(ReplayEvent(
            terms=event, cutoff=cutoff, draw=draw(day=1 + 40 * i),
            scenarios=scenarios(means, seed=i, withdraw=0.1),
            scenarios_available_at=cutoff - timedelta(hours=1), future=tuple(later),
            outcome=outcome))
    return events



def replay(events, **kwargs):
    return replay_season(events, ledger=ledger(), entry_id="entry:own", seed=3,
                         parameters=PARAMS, allow_provisional=True, **kwargs)


def test_replay_consumes_each_policys_own_state_through_the_ledger():
    events = season()
    comparison = replay(events)
    by_policy = {t.policy: t for t in comparison.trajectories}
    for trajectory in comparison.trajectories:
        bank = (4, 4, 4, 4)
        for step in trajectory.steps:
            bank = tuple(b - s for b, s in zip(bank, step.spend))
            assert step.slam_after == bank and min(bank) >= 0
            assert step.information_at < step.cutoff
        assert trajectory.season_points == sum(s.realized_points for s in trajectory.steps)
        assert trajectory.submission_bonus == 0
        assert trajectory.unused_tokens == sum(bank) + 34
    greedy, horizon = by_policy[Policy.GREEDY], by_policy[Policy.HORIZON]
    assert greedy.steps[0].spend[0] > horizon.steps[0].spend[0] or (
        greedy.steps[0].slam_after != horizon.steps[0].slam_after)
    assert horizon.steps[2].slam_after[0] < horizon.steps[1].slam_after[0] or (
        horizon.steps[1].slam_after[0] == 0)
    assert comparison.baseline is Policy.GREEDY
    assert dict(comparison.season_point_deltas)[Policy.HORIZON] == (
        horizon.season_points - greedy.season_points)
    assert "never sum independent weekly backtests" in comparison.note


def test_replay_decisions_never_see_their_own_or_later_outcomes():
    base = replay(season())
    later = season()[2].outcome
    changed = replay(season({"wimbledon": replace(
        later, points=tuple((p, 0) for p, _ in later.points))}))
    middle = season()[1].outcome
    shifted = replay(season({"roland_garros": replace(
        middle, points=tuple((p, v + 7) for p, v in middle.points))}))
    for a, b, c in zip(base.trajectories, changed.trajectories, shifted.trajectories):
        assert [s.pairs for s in a.steps] == [s.pairs for s in b.steps]
        assert [s.pairs for s in a.steps][:2] == [s.pairs for s in c.steps][:2]
        assert a.steps[2].realized_points != b.steps[2].realized_points or (
            a.steps[2].realized_points == 0)


def test_replay_activates_the_substitute_of_a_withdrawn_primary():
    base = replay(season(), policies=(Policy.GREEDY,))
    pairs = base.trajectories[0].steps[0].pairs
    covered = next(p for p in pairs if p.substitute is not None)
    events = season(withdrawn=(covered.primary.player_id,))
    result = replay(events, policies=(Policy.GREEDY,)).trajectories[0].steps[0]
    points = dict(events[0].outcome.points)
    expected = sum(points[p.substitute.player_id] if p == covered else points[p.primary.player_id]
                   for p in result.pairs)
    assert result.pairs == pairs and result.realized_points == expected


def test_replay_reserves_substitutes_whose_activation_is_still_pending():
    events = season()
    late = events[1].cutoff + timedelta(days=1)
    events[0] = replace(events[0], outcome=replace(events[0].outcome, revealed_at=late))
    result = replay(events, policies=(Policy.GREEDY,)).trajectories[0]
    first = result.steps[0]
    covers = tuple(sorted(p.substitute.player_id for p in first.pairs if p.substitute))
    assert covers and result.steps[1].reserved == covers and result.steps[2].reserved == ()
    # Two unresolved sheets naming the same cover reserve two uses.
    both = list(events)
    both[1] = replace(both[1], outcome=replace(both[1].outcome,
                                               revealed_at=both[2].cutoff + timedelta(days=1)))
    both[0] = replace(both[0], outcome=replace(both[0].outcome,
                                               revealed_at=both[2].cutoff + timedelta(days=1)))
    steps = replay(both, policies=(Policy.GREEDY,)).trajectories[0].steps
    pending = sorted(p.substitute.player_id for s in steps[:2] for p in s.pairs if p.substitute)
    assert list(steps[2].reserved) == pending


def test_replay_rejects_conflicting_or_self_referential_results():
    events = season()
    duplicate = list(events)
    points = events[0].outcome.points
    duplicate[0] = replace(events[0], outcome=replace(
        events[0].outcome, points=points + ((points[0][0], points[0][1] + 50),)))
    with pytest.raises(ValueError, match="exactly once"):
        replay(duplicate)
    own = [replace(e, outcome=replace(e.outcome, rival_points=e.outcome.rival_points
                                      + (("entry:own", 1),))) for e in events]
    with pytest.raises(ValueError, match="own entry"):
        replay(own)
    config = payout_config(40, allow_provisional=True)
    rivals = tuple((f"entry:r{k}", 10) for k in range(39))
    field = [replace(e, outcome=replace(e.outcome, rival_points=rivals)) for e in events]
    tampered = replace(config, event_prizes_cents=(10**9,) + config.event_prizes_cents[1:])
    with pytest.raises(ValueError, match="versioned derivation"):
        replay(field, payout=tampered)


def test_replay_pays_ties_and_ranks_against_the_supplied_field():
    config = payout_config(40, allow_provisional=True)
    events = season()
    rivals = tuple((f"entry:r{k}", 10) for k in range(39))
    events = [replace(e, outcome=replace(e.outcome, rival_points=rivals)) for e in events]
    result = replay(events, policies=(Policy.HORIZON,), payout=config)
    trajectory = result.trajectories[0]
    assert trajectory.season_rank == 1 and trajectory.event_payout_cents > 0
    assert trajectory.season_payout_cents == config.season_prizes_cents[0]
    # Tie the own entry with one rival for first at the opening event.
    own_first = trajectory.steps[0].realized_points
    tied_rivals = ((f"entry:r0", own_first),) + rivals[1:]
    tied = [replace(events[0], outcome=replace(events[0].outcome, rival_points=tied_rivals))]
    tied += events[1:]
    shared = replay(tied, policies=(Policy.HORIZON,), payout=config).trajectories[0].steps[0]
    pool = sum(config.event_prizes_cents[:2])
    assert shared.event_rank == 1
    assert shared.event_payout_cents == pool // 2 + pool % 2
    assert shared.event_payout_cents == next(
        a.payout_cents for a in split_prizes({"entry:own": own_first, **dict(tied_rivals)},
                                             config.event_prizes_cents)
        if a.entry_id == "entry:own")
    with pytest.raises(ValueError, match="same distinct rivals"):
        broken = list(events)
        broken[1] = replace(broken[1], outcome=replace(broken[1].outcome, rival_points=()))
        replay(broken)
    with pytest.raises(ValueError, match="before the cutoff"):
        bad = list(events)
        bad[0] = replace(bad[0], scenarios_available_at=bad[0].cutoff)
        replay(bad)
    with pytest.raises(ValueError, match="revealed"):
        bad = list(events)
        bad[0] = replace(bad[0], outcome=replace(bad[0].outcome,
                                                 revealed_at=bad[0].cutoff))
        replay(bad)


def narrow_entry(last_uses=0, spare=()):
    """Only p1, p2 (1-4 seeds), p9-p11 (unseeded) and ``spare`` are still pickable."""
    capped = [n for n in (3, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16) if n not in spare]
    usage = tuple(sorted([(pid(n), 5) for n in capped]
                         + ([(pid(1), last_uses), (pid(2), last_uses)] if last_uses else [])))
    return entry(usage=usage)


def test_fair_share_falls_back_to_the_bank_when_it_cannot_fill_a_sheet():
    result = plan(own=narrow_entry())
    rationed = projection(result, Policy.RATIONED)
    assert rationed.spend == (2, 0, 0, 0) and "cannot fill a legal sheet" in rationed.notes[0]
    top4 = next(c for c in result.token_costs if c.band is Band.TOP4)
    assert top4.gain_now is None and top4.advice == "spend"
    assert "none exists with one fewer" in top4.explanation
    required = [c for c in result.use_costs if c.player_id in (pid(1), pid(2))]
    assert required and all(c.edge_now is None and c.advice == "spend" for c in required)
    assert all("No legal sheet exists without him" in c.explanation for c in required)


def test_joint_preservation_keeps_a_legal_horizon_sheet():
    def absent(event):
        base = future(event)
        return replace(base, prospects=tuple(
            replace(p, entry_probability=0.0) if p.player_id in (pid(1), pid(2)) else p
            for p in base.prospects))

    stars = {"roland_garros": absent("roland_garros"), "us_open": absent("us_open"),
             "wimbledon": future("wimbledon", means=[220, 210] + BASE[2:], entry=0.95)}
    result = plan(own=narrow_entry(last_uses=4, spare=(12,)), special=stars)
    horizon = projection(result, Policy.HORIZON)
    assert len(horizon.preserved) == 1 and len(horizon.notes) == 1
    assert "would leave no legal sheet" in horizon.notes[0]
    picked = {p.primary.player_id for p in horizon.recommendation.best.pairs}
    assert picked.isdisjoint(horizon.preserved) and len(picked) == 5


def test_a_rival_without_a_legal_sheet_scores_nothing():
    stuck = replace(standings()[0], entry_id="entry:stuck", season_points=699,
                    usage=tuple((pid(n), 5) for n in range(1, 14)))
    result = plan(event="us_open", own=entry(points=700), rival_states=(stuck,))
    for item in result.projections:
        assert item.rival_gaps[0].p_finish_ahead == 1
        assert item.rival_gaps[0].expected_final_gap == pytest.approx(
            item.season_expected_points - 699)


def test_cost_baseline_holds_only_this_events_charges(monkeypatch):
    import tennis_pool.season as season_module

    seen = []
    original = season_module._use_costs

    def spy(context, slam, masters, base, charges, excluded):
        seen.append(np.array(base, copy=True))
        return original(context, slam, masters, base, charges, excluded)

    monkeypatch.setattr(season_module, "_use_costs", spy)
    result = plan(event="roland_garros", policies=(Policy.GREEDY,))
    pairs = result.recommendation.best.pairs
    final = seen[-1]
    # Five uses charged in every world: this event only, never later simulated picks.
    assert (final.sum(axis=1) == len(pairs)).all()


def test_the_bonus_needs_seven_legal_sheets():
    stuck = replace(standings()[0], entry_id="entry:stuck", season_points=699,
                    usage=tuple((pid(n), 5) for n in range(1, 14)),
                    qualifying_events=("a", "b", "c", "d", "e", "f"))
    able = replace(stuck, entry_id="entry:able", usage=())
    result = plan(event="us_open", own=entry(points=700), rival_states=(stuck, able))
    for item in result.projections:
        stuck_gap, able_gap = item.rival_gaps if item.rival_gaps[0].entry_id == "entry:stuck" \
            else item.rival_gaps[::-1]
        # The stuck rival cannot submit a legal sixth-to-seventh sheet: no bonus.
        assert stuck_gap.expected_final_gap == pytest.approx(item.season_expected_points - 699)
        assert able_gap.expected_final_gap < stuck_gap.expected_final_gap - 250


def test_activated_substitutes_are_charged_in_the_use_advice():
    event = terms("roland_garros")
    result = plan_event(
        scenarios(BASE, withdraw=0.3), draw(), event,
        cutoff=event.deadline - timedelta(days=1), entry=entry(), calendar=CALENDAR,
        future=futures("roland_garros"), seed=11, parameters=PARAMS, allow_provisional=True)
    pairs = result.recommendation.best.pairs
    covers = {p.substitute.player_id for p in pairs if p.substitute is not None}
    by_player = {c.player_id: c for c in result.use_costs}
    assert covers and covers <= by_player.keys()
    for player in covers:
        cost = by_player[player]
        assert cost.in_plan and cost.edge_now > 0
        assert "As a substitute he is charged in" in cost.explanation
    assert {p.primary.player_id for p in pairs} <= by_player.keys()


def test_repeated_scenario_columns_are_not_counted_as_independent():
    sparse = plan_event(
        scenarios(BASE, runs=4), draw(), terms("us_open"),
        cutoff=terms("us_open").deadline - timedelta(days=1), entry=entry(),
        calendar=CALENDAR, future=(), seed=11, parameters=PARAMS, allow_provisional=True)
    dense = plan_event(
        scenarios(BASE, runs=PARAMS.evaluation_worlds), draw(), terms("us_open"),
        cutoff=terms("us_open").deadline - timedelta(days=1), entry=entry(),
        calendar=CALENDAR, future=(), seed=11, parameters=PARAMS, allow_provisional=True)
    naive = [p.season_points_se for p in sparse.projections]
    assert all(se > 0 for se in naive)
    # Four independent draws spread over 120 worlds must not look like 120 draws.
    assert min(naive) > 2 * max(p.season_points_se for p in dense.projections) / 3
