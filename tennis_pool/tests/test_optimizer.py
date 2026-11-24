"""Synthetic issue #25 joint primary/substitute search cases; invented players only."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import itertools
import warnings

import numpy as np
import pytest

from tennis_api.models.canonical import (
    Coverage, Draw, DrawSlot, EntryKind, Event, EventId, Match, MatchId, MatchProbability,
    MatchStatus, PlayerId, Provenance, RankingSnapshot, Surface, Tour,
)
from tennis_api.simulation.tournament import OutcomeKind, simulate_tournament
from tennis_pool.ledger import Band, EntryState, Pair, Selection
from tennis_pool.optimizer import (
    Objective, Recommendation, RivalAssumptions, RivalField, ScenarioAssumptions,
    ScenarioSet, SearchLimits, _pool_points, build_scenarios, evaluate, optimize, recommend,
    sample_rival_field,
)
from tennis_pool.payouts import outlook, payout_config
from tennis_pool.results import score_tournament
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError
from tennis_pool.substitutions import seed_band, validate_roster


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
EVENT = "australian_open"


@pytest.fixture(autouse=True)
def quiet_provisional_rules():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalRulesWarning)
        yield


def evidence():
    return Provenance(source="synthetic", source_version="fixture-v1", source_record_id="s",
                      observed_at=START, available_at=START, ingested_at=START)


def pid(number):
    return PlayerId(f"atp:p{number}")


def small_draw(size=16, seeded=8):
    rounds = size.bit_length() - 1
    event = Event(event_id=EventId("test:small"), name="Synthetic", tour=Tour.ATP,
                  start_date=date(2026, 1, 2), end_date=date(2026, 1, 9), surface=Surface.HARD,
                  best_of=3, round_count=rounds, level="fixture", provenance=evidence())
    slots = tuple(DrawSlot(position=i, kind=EntryKind.PLAYER, player_id=pid(i),
                           seed=i if i <= seeded else None) for i in range(1, size + 1))
    return Draw(event=event, slots=slots, provenance=evidence())


def scenario_set(points, withdrawn=None, seeded=8, source="synthetic arrays"):
    points = np.asarray(points, dtype=np.int64)
    withdrawn = (np.zeros(points.shape, dtype=bool) if withdrawn is None
                 else np.asarray(withdrawn, dtype=bool))
    points = np.where(withdrawn, 0, points)
    count = points.shape[0]
    return ScenarioSet(
        player_ids=tuple(pid(i) for i in range(1, count + 1)),
        seeds=tuple(i if i <= seeded else None for i in range(1, count + 1)),
        points=points, withdrawn=withdrawn,
        assumptions=ScenarioAssumptions(
            source=source, simulations=points.shape[1], seed=None, kind=None, draw_digest=None,
            withdrawal_model="fixture flags", withdrawal_probabilities=(),
            withdrawal_patterns=1),
    )


def random_scenarios(seed, runs=400, withdraw=0.15):
    rng = np.random.default_rng(seed)
    scale = np.array([60, 55, 50, 45, 35, 30, 28, 25] + [12] * 8, dtype=float)
    points = rng.gamma(0.8, scale[:, None], size=(16, runs)).astype(np.int64)
    withdrawn = rng.random((16, runs)) < withdraw
    return scenario_set(points, withdrawn)


def capped_entry(capped=(3, 4, 7, 8, 15, 16), slam=(1, 4, 4, 4)):
    return EntryState(entry_id="entry:one", slam=slam, masters=(9, 9, 9, 7),
                      usage=tuple((pid(n), 5) for n in capped))


def brute_force(scenarios, entry, objective, rivals=None, prizes=None, alpha=0.2):
    """Independent pure-Python enumeration of every legal policy."""
    usage = dict(entry.usage)
    ids = scenarios.player_ids
    eligible = [i for i, p in enumerate(ids) if usage.get(p, 0) < 5]
    bands = {i: seed_band(s) for i, s in enumerate(scenarios.seeds)}
    banks = dict(zip((Band.TOP4, Band.TOP8, Band.TOP16, Band.TOP32), entry.slam))
    best = -1.0
    for roster in itertools.combinations(eligible, 5):
        if any(sum(bands[p] is b for p in roster) > n for b, n in banks.items()):
            continue
        options = [[None] + [s for s in eligible if s not in roster and bands[s] is bands[p]]
                   for p in roster]
        for subs in itertools.product(*options):
            chosen = [s for s in subs if s is not None]
            if len(set(chosen)) != len(chosen):
                continue
            totals = []
            for run in range(scenarios.simulations):
                total = 0
                for p, s in zip(roster, subs):
                    if scenarios.withdrawn[p, run]:
                        total += 0 if s is None else int(scenarios.points[s, run])
                    else:
                        total += int(scenarios.points[p, run])
                totals.append(total)
            totals = np.array(totals, dtype=float)
            if objective is Objective.EXPECTED_POINTS:
                value = totals.mean()
            elif objective is Objective.ROBUST:
                k = max(1, int(np.ceil(alpha * len(totals)))) - 1
                var = np.sort(totals)[k]
                value = var + np.minimum(totals - var, 0).mean() / alpha
            else:
                values = []
                for run, own in enumerate(totals):
                    others = rivals[:, run]
                    ahead, tied = int((others > own).sum()), int((others == own).sum())
                    if objective is Objective.P_TOP3:
                        values.append(float(ahead < 3))
                    else:
                        padded = list(prizes) + [0] * (len(others) + 1)
                        values.append(sum(padded[ahead:ahead + tied + 1]) / (tied + 1))
                value = float(np.mean(values))
            best = max(best, value)
    return best


def legal(recommendation, draw, entry):
    for candidate in (recommendation.best,) + recommendation.alternatives:
        check = validate_roster(candidate.pairs, draw, EVENT, entry, allow_provisional=True)
        assert check.legal, check.problems
    return True


def rival_field(scores, source="fixture rivals"):
    scores = np.asarray(scores, dtype=np.int64)
    return RivalField(scores=scores, assumptions=RivalAssumptions(
        source=source, rivals=scores.shape[0], seed=None, model="fixture", ownership=()))


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("objective", [Objective.EXPECTED_POINTS, Objective.ROBUST,
                                       Objective.P_TOP3])
def test_small_fixtures_match_an_independent_exhaustive_search(seed, objective):
    scenarios = random_scenarios(seed, runs=60)
    entry, draw = capped_entry(), small_draw()
    rivals = None
    if objective is Objective.P_TOP3:
        rivals = rival_field(np.random.default_rng(seed + 10).integers(60, 220, size=(5, 60)))
    expected = brute_force(scenarios, entry, objective,
                           None if rivals is None else rivals.scores)
    result = optimize(scenarios, draw, EVENT, objective=objective, entry=entry, rivals=rivals,
                      allow_provisional=True)
    assert result.search.exhaustive
    assert result.search.method == "exhaustive enumeration"
    assert result.best.objective_value == pytest.approx(expected)
    assert result.search.optimality_gap is not None and result.search.optimality_gap >= 0
    assert "Exhaustive over all" in result.search.gap_basis
    assert legal(result, draw, entry)


@pytest.mark.parametrize("seed", [9, 14, 17])
@pytest.mark.parametrize("objective", list(Objective))
def test_default_heuristic_reaches_the_exhaustive_optimum(seed, objective):
    # These seeds once stalled when two same-band slots had to trade covers.
    scenarios = random_scenarios(seed, runs=300)
    rivals = rival_field(np.random.default_rng(seed + 100).integers(60, 220, size=(39, 300)))
    result = optimize(scenarios, small_draw(), EVENT, objective=objective, entry=capped_entry(),
                      rivals=rivals, payout=payout_config(40, allow_provisional=True),
                      allow_provisional=True)
    assert result.search.exhaustive
    assert result.search.optimality_gap == pytest.approx(0.0, abs=1e-9)


def test_pruning_is_disclosed_and_its_gap_measured():
    scenarios = random_scenarios(4, runs=80)
    limits = SearchLimits(seeded_pool=1, unseeded_pool=5, substitute_pool=0)
    result = optimize(scenarios, small_draw(), EVENT, objective=Objective.EXPECTED_POINTS,
                      entry=capped_entry(), limits=limits, allow_provisional=True)
    report = result.search
    assert report.limits == limits
    assert report.primary_pool == 7 and report.pruned_players == 3
    assert report.exhaustive and report.optimality_gap is not None
    exact = brute_force(scenarios, capped_entry(), Objective.EXPECTED_POINTS)
    assert result.best.objective_value == pytest.approx(exact)


def test_large_instances_report_a_bound_or_say_the_gap_is_unmeasured():
    scenarios = random_scenarios(5, runs=200)
    limits = SearchLimits(exhaustive_limit=0)
    points = optimize(scenarios, small_draw(), EVENT, objective=Objective.EXPECTED_POINTS,
                      limits=limits, allow_provisional=True)
    assert not points.search.exhaustive and points.search.upper_bound is not None
    assert points.search.upper_bound >= points.best.objective_value
    assert points.search.optimality_gap == pytest.approx(
        points.search.upper_bound - points.best.objective_value)
    robust = optimize(scenarios, small_draw(), EVENT, objective=Objective.ROBUST,
                      limits=limits, allow_provisional=True)
    assert robust.search.optimality_gap is None and "Not measured" in robust.search.gap_basis


def test_quota_and_use_caps_hold_for_every_policy_and_activation():
    scenarios = random_scenarios(6)
    entry, draw = capped_entry(slam=(1, 0, 4, 4)), small_draw()
    result = optimize(scenarios, draw, EVENT, objective=Objective.EXPECTED_POINTS, entry=entry,
                      allow_provisional=True)
    capped = {pid(n) for n in (3, 4, 7, 8, 15, 16)}
    for candidate in (result.best,) + result.alternatives:
        players = [p.primary for p in candidate.pairs] + [
            p.substitute for p in candidate.pairs if p.substitute is not None]
        assert not capped & {s.player_id for s in players}
        assert sum(p.primary.band is Band.TOP4 for p in candidate.pairs) <= 1
        assert not any(p.primary.band is Band.TOP8 for p in candidate.pairs)
        assert all(p.substitute is None or p.substitute.band is p.primary.band
                   for p in candidate.pairs)
    assert legal(result, draw, entry)


def test_no_legal_roster_fails_instead_of_inventing_one():
    entry = capped_entry(capped=tuple(range(9, 17)), slam=(0, 0, 0, 0))
    with pytest.raises(ValueError, match="No legal"):
        optimize(random_scenarios(0), small_draw(), EVENT, objective=Objective.EXPECTED_POINTS,
                 entry=entry, allow_provisional=True)


def test_evaluate_hands_a_withdrawn_slot_to_its_substitute_in_the_same_scenario():
    runs = 100
    points = np.ones((3, runs), dtype=np.int64)
    withdrawn = np.zeros((3, runs), dtype=bool)
    withdrawn[0, :50] = True
    points[0] = 100
    points[1, :50], points[1, 50:] = 80, 0    # seed 2 scores exactly when seed 1 is out
    points[2, :50], points[2, 50:] = 0, 120   # seed 3 has the larger marginal mean
    scenarios = scenario_set(points, withdrawn)

    def policy(sub):
        return (Pair(primary=Selection(player_id=pid(1), band=Band.TOP4),
                     substitute=Selection(player_id=pid(sub), band=Band.TOP4)),)

    assert evaluate(scenarios, policy(2), allow_provisional=True).expected_points == 90.0
    assert evaluate(scenarios, policy(3), allow_provisional=True).expected_points == 50.0


def test_joint_search_picks_the_covering_substitute_for_a_risky_primary():
    runs = 100
    points = np.zeros((16, runs), dtype=np.int64)
    withdrawn = np.zeros((16, runs), dtype=bool)
    withdrawn[0, :50] = True
    points[0] = 200
    points[1, :50] = 80                    # covers exactly the withdrawal scenarios
    points[2, 50:] = 120                   # higher mean, useless as cover
    points[4:8] = 30
    points[8:16] = 5
    scenarios = scenario_set(points, withdrawn)
    entry = EntryState(entry_id="entry:one", slam=(1, 4, 4, 4), masters=(9, 9, 9, 7), usage=())
    result = optimize(scenarios, small_draw(), EVENT, objective=Objective.EXPECTED_POINTS,
                      entry=entry, limits=SearchLimits(exhaustive_limit=0),
                      allow_provisional=True)
    pairs = {p.primary.player_id: p.substitute for p in result.best.pairs}
    assert pairs[pid(1)] is not None and pairs[pid(1)].player_id == pid(2)
    assert result.best.metrics.expected_points == pytest.approx(100 + 40 + 4 * 30)


def test_draw_correlation_is_kept_instead_of_summing_marginals():
    # Seeds 5 and 6 meet early: exactly one of them goes deep in each scenario.
    runs = 200
    points = np.ones((16, runs), dtype=np.int64)
    points[4, ::2], points[5, 1::2] = 100, 100
    points[4, 1::2], points[5, ::2] = 0, 0
    points[6], points[7] = 48, 48
    scenarios = scenario_set(points)
    entry = EntryState(entry_id="entry:one", slam=(0, 2, 4, 4), masters=(9, 9, 9, 7), usage=())
    draw = small_draw()

    def top8(result):
        return {p.primary.player_id for p in result.best.pairs if p.primary.band is Band.TOP8}

    mean = optimize(scenarios, draw, EVENT, objective=Objective.EXPECTED_POINTS, entry=entry,
                    allow_provisional=True)
    assert top8(mean) == {pid(5), pid(6)}     # 100 every time beats 96
    rivals = rival_field(np.full((5, runs), 130))
    ranked = optimize(scenarios, draw, EVENT, objective=Objective.P_TOP3, entry=entry,
                      rivals=rivals, allow_provisional=True)
    chosen = top8(ranked)
    # Together seeds 5 and 6 never clear 130; one of them plus a 48 does half the time.
    assert len(chosen & {pid(5), pid(6)}) == 1 and len(chosen & {pid(7), pid(8)}) == 1
    assert ranked.best.metrics.p_top3 == pytest.approx(0.5)
    assert ranked.near_ties and all(c.metrics.p_top3 == pytest.approx(0.5)
                                    for c in ranked.near_ties)


def test_payout_metrics_match_payouts_outlook():
    scenarios = random_scenarios(7, runs=150)
    config = payout_config(40, allow_provisional=True)
    ownership = {pid(n): share for n, share in zip(range(1, 17), np.linspace(0.6, 0.05, 16))}
    rivals = sample_rival_field(scenarios, ownership, rivals=39, seed=3)
    result = optimize(scenarios, small_draw(), EVENT, objective=Objective.EXPECTED_PAYOUT,
                      rivals=rivals, payout=config, limits=SearchLimits(exhaustive_limit=0),
                      allow_provisional=True)
    pairs = result.best.pairs
    metrics = evaluate(scenarios, pairs, rivals=rivals, payout=config, allow_provisional=True)
    own = np.zeros(scenarios.simulations)
    index = {p: i for i, p in enumerate(scenarios.player_ids)}
    for pair in pairs:
        p = index[pair.primary.player_id]
        s = None if pair.substitute is None else index[pair.substitute.player_id]
        own += np.where(scenarios.withdrawn[p], 0 if s is None else scenarios.points[s],
                        scenarios.points[p])
    samples = [{"entry:me": int(own[r]), **{f"entry:r{k}": int(rivals.scores[k, r])
                                            for k in range(39)}}
               for r in range(scenarios.simulations)]
    reference = outlook(samples, "entry:me", config, allow_provisional=True)
    assert metrics.expected_payout_cents == pytest.approx(reference.expected_payout_cents)
    assert metrics.p_top3 == pytest.approx(reference.p_top3)
    assert metrics.expected_points == pytest.approx(reference.expected_points)
    assert result.best.objective_value == pytest.approx(reference.expected_payout_cents)
    assert result.assumptions.payout_config_version == config.config_version
    assert "Gumbel" in result.assumptions.rivals.model


def test_rank_objectives_need_ownership_and_recommend_says_why_they_were_skipped():
    scenarios = random_scenarios(8, runs=100)
    with pytest.raises(ValueError, match="ownership"):
        optimize(scenarios, small_draw(), EVENT, objective=Objective.P_TOP3,
                 allow_provisional=True)
    with pytest.raises(ValueError, match="payout configuration"):
        optimize(scenarios, small_draw(), EVENT, objective=Objective.EXPECTED_PAYOUT,
                 rivals=rival_field(np.ones((39, 100))), allow_provisional=True)
    result = recommend(scenarios, small_draw(), EVENT, entry=capped_entry(),
                       allow_provisional=True)
    assert [r.objective for r in result.recommendations] == [
        Objective.EXPECTED_POINTS, Objective.ROBUST]
    assert dict(result.skipped) == {
        Objective.P_TOP3: "Requires ownership input (a rival field)",
        Objective.EXPECTED_PAYOUT: "Requires ownership input (a rival field)",
    }
    config = payout_config(40, allow_provisional=True)
    with pytest.raises(ValueError, match="participants - 1"):
        optimize(scenarios, small_draw(), EVENT, objective=Objective.EXPECTED_PAYOUT,
                 rivals=rival_field(np.ones((5, 100))), payout=config, allow_provisional=True)


def test_all_objectives_are_returned_with_ownership_and_payout_input():
    scenarios = random_scenarios(9, runs=120)
    config = payout_config(40, allow_provisional=True)
    ownership = {pid(n): 0.3 for n in range(1, 17)}
    rivals = sample_rival_field(scenarios, ownership, rivals=39, seed=1)
    result = recommend(scenarios, small_draw(), EVENT, entry=capped_entry(), rivals=rivals,
                       payout=config, allow_provisional=True)
    assert [r.objective for r in result.recommendations] == list(Objective)
    assert result.skipped == ()
    for recommendation in result.recommendations:
        assert legal(recommendation, small_draw(), capped_entry())


def test_identical_options_are_reported_as_ties_not_a_false_winner():
    runs = 300
    rng = np.random.default_rng(11)
    points = rng.integers(0, 5, size=(16, runs))
    points[10:14] += 40                    # four clearly best unseeded players
    points[8] += 20
    points[9] = points[8]                  # the fifth slot has two interchangeable options
    scenarios = scenario_set(points)
    entry = EntryState(entry_id="entry:one", slam=(0, 0, 0, 0), masters=(9, 9, 9, 7), usage=())
    result = optimize(scenarios, small_draw(), EVENT, objective=Objective.EXPECTED_POINTS,
                      entry=entry, limits=SearchLimits(exhaustive_limit=0),
                      allow_provisional=True)
    assert result.near_ties, "an equal-value swap must be labelled a tie"
    tie = result.near_ties[0]
    assert tie.gap_to_best == pytest.approx(0.0, abs=1e-9)
    assert "paired standard errors" in result.assumptions.tie_rule


def test_top3_ties_use_the_one_and_a_half_point_materiality_rule():
    scenarios = random_scenarios(12, runs=400)
    rivals = rival_field(np.random.default_rng(1).integers(80, 200, size=(9, 400)))
    result = optimize(scenarios, small_draw(), EVENT, objective=Objective.P_TOP3,
                      entry=capped_entry(), rivals=rivals, allow_provisional=True)
    assert "1.5% absolute P(top-3)" in result.assumptions.tie_rule
    for candidate in result.alternatives:
        if candidate.gap_to_best <= 0.015:
            assert candidate.tie_with_best


def test_recommendation_records_reproducible_assumptions_and_round_trips():
    scenarios = random_scenarios(13, runs=100)
    result = optimize(scenarios, small_draw(), EVENT, objective=Objective.ROBUST,
                      entry=capped_entry(), allow_provisional=True)
    assumptions = result.assumptions
    assert assumptions.scenarios.simulations == 100
    assert assumptions.scenarios.withdrawal_model == "fixture flags"
    assert "0.2" in assumptions.objective_definition
    assert "Single-event" in assumptions.season_effects
    assert assumptions.rule_register_version == "2026-provisional-2"
    assert {status for _, status, _ in assumptions.recommendation_decisions} == {"provisional"}
    assert Recommendation.from_dict(result.to_dict()) == result
    again = optimize(scenarios, small_draw(), EVENT, objective=Objective.ROBUST,
                     entry=capped_entry(), allow_provisional=True)
    assert again == result


def test_strict_mode_blocks_on_provisional_recommendation_rules():
    with pytest.raises(UnresolvedRulesError):
        optimize(random_scenarios(0), small_draw(), EVENT,
                 objective=Objective.EXPECTED_POINTS)
    with pytest.raises(ValueError, match="explicit boolean"):
        optimize(random_scenarios(0), small_draw(), EVENT,
                 objective=Objective.EXPECTED_POINTS, allow_provisional=1)


def test_candidate_explosion_fails_with_an_explicit_limit():
    with pytest.raises(ValueError, match="max_rosters"):
        optimize(random_scenarios(0), small_draw(), EVENT, objective=Objective.EXPECTED_POINTS,
                 limits=SearchLimits(max_rosters=10, exhaustive_limit=0),
                 allow_provisional=True)


def test_scenarios_must_match_the_draw_and_be_well_formed():
    scenarios = random_scenarios(0)
    with pytest.raises(ValueError, match="released draw"):
        optimize(scenarios, small_draw(seeded=4), EVENT, objective=Objective.EXPECTED_POINTS,
                 allow_provisional=True)
    with pytest.raises(ValueError, match="zero after pre-match withdrawal"):
        ScenarioSet(player_ids=(pid(1),), seeds=(1,), points=np.array([[5]]),
                    withdrawn=np.array([[True]]),
                    assumptions=replace(scenarios.assumptions, simulations=1))
    with pytest.raises(ValueError, match="Unknown pool event"):
        optimize(scenarios, small_draw(), "atlantis", objective=Objective.EXPECTED_POINTS,
                 allow_provisional=True)


# --- Scenario generation through the tournament simulator -------------------


class Provider:
    def __init__(self, includes_risk=False):
        self.includes_risk = includes_risk

    def predict(self, context):
        stronger = int(context.player1_id.split("p")[-1]) < int(context.player2_id.split("p")[-1])
        return MatchProbability(
            player1_id=context.player1_id, player2_id=context.player2_id,
            player1_win_probability=0.65 if stronger else 0.35, model_version="synthetic-1",
            calibration_version=None, cutoff=context.cutoff, context_digest=context.digest,
            coverage=Coverage(observed=(), missing=("form",)),
            warnings=("synthetic uncalibrated probability",),
            includes_availability_risk=self.includes_risk,
        )


CUTOFF = START + timedelta(hours=1)


def m6_draw():
    """64 slots, 56 entrants: seeds 1-8 have byes; player N is seeded N through 16."""
    event = Event(event_id=EventId("test:m6"), name="Synthetic M6", tour=Tour.ATP,
                  start_date=date(2026, 1, 2), end_date=date(2026, 1, 9), surface=Surface.HARD,
                  best_of=3, round_count=6, level="masters", provenance=evidence())
    order = list(range(1, 57))
    slots, number = [], iter(order)
    for position in range(1, 65):
        section = (position - 1) // 8
        if position % 8 == 2 and section < 8:
            slots.append(DrawSlot(position=position, kind=EntryKind.BYE, player_id=None))
            continue
        player = next(number)
        slots.append(DrawSlot(position=position, kind=EntryKind.PLAYER, player_id=pid(player),
                              seed=player if player <= 16 else None))
    return Draw(event=event, slots=tuple(slots), provenance=evidence())


def rankings(draw):
    return tuple(RankingSnapshot(player_id=s.player_id, tour=Tour.ATP, ranking_date=date(2026, 1, 1),
                                 rank=int(s.player_id.split("p")[-1]), points=None,
                                 provenance=evidence())
                 for s in draw.slots if s.player_id is not None)


def test_simulated_pool_points_match_canonical_scoring_run_by_run():
    draw = m6_draw()
    ranks = rankings(draw)
    simulation = simulate_tournament(draw, Provider(), cutoff=CUTOFF, simulations=6,
                                     rng=np.random.default_rng(5), rankings=ranks)
    points = _pool_points(simulation, draw, "m6",
                          {r.player_id: r.rank for r in ranks})
    for run in range(6):
        matches = []
        for outcome in simulation.rounds:
            for slot in range(outcome.kinds.shape[0]):
                if outcome.kinds[slot, run] != OutcomeKind.DECIDED:
                    continue
                a, b = outcome.player1[slot, run], outcome.player2[slot, run]
                winner = outcome.winners[slot, run]
                matches.append(Match(
                    match_id=MatchId(f"test:r{outcome.round_number}s{slot}"),
                    event_id=draw.event.event_id, tour=Tour.ATP,
                    player1_id=simulation.player_ids[a], player2_id=simulation.player_ids[b],
                    surface=Surface.HARD, best_of=3, round_number=outcome.round_number,
                    occurred_at=None, status=MatchStatus.COMPLETED,
                    winner_id=simulation.player_ids[winner], score=None,
                    provenance=evidence()))
        score = score_tournament(draw, tuple(matches), ranks, "m6", allow_provisional=True)
        totals = {p.player_id: p.total for p in score.players}
        for i, player in enumerate(simulation.player_ids):
            assert points[i, run] == totals[player]


def test_scenarios_are_seed_reproducible_and_record_withdrawal_assumptions():
    draw = m6_draw()
    ranks = rankings(draw)
    risk = {pid(1): 0.5, pid(20): 1.0}
    build = lambda seed: build_scenarios(  # noqa: E731
        draw, Provider(), kind="m6", cutoff=CUTOFF, simulations=300, seed=seed,
        withdrawal_probabilities=risk, rankings=ranks, allow_provisional=True)
    first, again, other = build(7), build(7), build(8)
    assert np.array_equal(first.points, again.points)
    assert np.array_equal(first.withdrawn, again.withdrawn)
    assert not np.array_equal(first.points, other.points)
    index = {p: i for i, p in enumerate(first.player_ids)}
    assert first.withdrawn[index[pid(20)]].all() and first.points[index[pid(20)]].sum() == 0
    share = first.withdrawn[index[pid(1)]].mean()
    assert 0.4 < share < 0.6
    assert first.assumptions.withdrawal_patterns == 2
    assert first.assumptions.seed == 7 and first.assumptions.simulations == 300
    assert dict(first.assumptions.withdrawal_probabilities) == {pid(1): 0.5, pid(20): 1.0}
    assert "walkover" in first.assumptions.withdrawal_model
    # The walkover opponent of a withdrawn player advances without a played-win bonus.
    assert (first.points[index[pid(1)]][first.withdrawn[index[pid(1)]]] == 0).all()
    result = optimize(first, draw, "paris", objective=Objective.EXPECTED_POINTS,
                      allow_provisional=True)
    assert result.assumptions.scenarios == first.assumptions
    assert pid(20) not in {p.primary.player_id for p in result.best.pairs}


def test_explicit_withdrawals_cannot_double_count_provider_availability_risk():
    draw = m6_draw()
    with pytest.raises(ValueError, match="double count"):
        build_scenarios(draw, Provider(includes_risk=True), kind="m6", cutoff=CUTOFF,
                        simulations=20, seed=0, withdrawal_probabilities={pid(1): 1.0},
                        rankings=rankings(draw), allow_provisional=True)


def test_scenario_inputs_fail_closed():
    draw = m6_draw()
    with pytest.raises(ValueError, match="round count"):
        build_scenarios(draw, Provider(), kind="gs", cutoff=CUTOFF, simulations=5, seed=0,
                        rankings=rankings(draw), allow_provisional=True)
    with pytest.raises(ValueError, match="Withdrawal probabilities"):
        build_scenarios(draw, Provider(), kind="m6", cutoff=CUTOFF, simulations=5, seed=0,
                        withdrawal_probabilities={pid(99): 0.1}, rankings=rankings(draw),
                        allow_provisional=True)
    with pytest.raises(ValueError, match="withdrawal patterns"):
        build_scenarios(draw, Provider(), kind="m6", cutoff=CUTOFF, simulations=50, seed=0,
                        withdrawal_probabilities={pid(n): 0.5 for n in range(1, 9)},
                        rankings=rankings(draw), max_withdrawal_patterns=4,
                        allow_provisional=True)


def test_rival_sampling_follows_ownership_on_shared_scenarios():
    scenarios = random_scenarios(14, runs=2000, withdraw=0.0)
    ownership = {pid(1): 0.9, pid(2): 0.9, pid(3): 0.9, pid(4): 0.9, pid(5): 0.9, pid(6): 0.0001}
    field = sample_rival_field(scenarios, ownership, rivals=3, seed=2)
    chalk = scenarios.points[:5].sum(axis=0)
    assert (field.scores == chalk).mean() > 0.99
    with pytest.raises(ValueError, match="at least five"):
        sample_rival_field(scenarios, {pid(1): 0.5}, rivals=3, seed=0)
    with pytest.raises(ValueError, match="shares in"):
        sample_rival_field(scenarios, {pid(1): 1.5}, rivals=3, seed=0)
