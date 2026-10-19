"""Neutral simulation fixtures use only invented players and probabilities."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import random

import numpy as np
import pytest

from tennis_api.models.canonical import (
    Coverage,
    Draw,
    DrawSlot,
    EntryKind,
    Event,
    EventId,
    MatchProbability,
    Match,
    MatchId,
    MatchStatus,
    PlayerId,
    PlayerMatchStats,
    Provenance,
    RankingSnapshot,
    Surface,
    Tour,
)
from tennis_api.simulation.tournament import (
    ForcedRetirement,
    OutcomeKind,
    simulate_tournament,
)


CUTOFF = datetime(2026, 1, 2, tzinfo=timezone.utc)


def draw(rounds=2):
    provenance = Provenance(
        source="synthetic",
        source_version="1",
        source_record_id=None,
        observed_at=date(2026, 1, 1),
        available_at=CUTOFF - timedelta(days=1),
        ingested_at=CUTOFF,
    )
    return Draw(
        event=Event(
            event_id=EventId("synthetic:event"),
            name="Synthetic",
            tour=Tour.ATP,
            start_date=date(2026, 1, 3),
            end_date=date(2026, 1, 16),
            surface=Surface.CLAY,
            best_of=3,
            round_count=rounds,
            level="fixture",
            provenance=provenance,
        ),
        slots=tuple(
            DrawSlot(
                position=i + 1,
                kind=EntryKind.PLAYER,
                player_id=PlayerId(f"synthetic:p{i}"),
            )
            for i in range(2**rounds)
        ),
        provenance=provenance,
    )


class Provider:
    def __init__(self, probability=1.0, includes_risk=False):
        self.probability = probability
        self.includes_risk = includes_risk
        self.contexts = []

    def predict(self, context):
        self.contexts.append(context)
        return MatchProbability(
            player1_id=context.player1_id,
            player2_id=context.player2_id,
            player1_win_probability=self.probability,
            model_version="synthetic-1",
            calibration_version=None,
            cutoff=context.cutoff,
            context_digest=context.digest,
            coverage=Coverage(observed=(), missing=("form",)),
            warnings=("synthetic uncalibrated probability",),
            includes_availability_risk=self.includes_risk,
        )


def test_fixed_paths_neutral_outcomes_and_cached_provider_contexts():
    provider = Provider()
    result = simulate_tournament(
        draw(), provider, cutoff=CUTOFF, simulations=8, rng=np.random.default_rng(7)
    )
    assert result.player_ids == tuple(PlayerId(f"synthetic:p{i}") for i in range(4))
    assert result.rounds[0].player1[:, 0].tolist() == [0, 2]
    assert result.rounds[0].player2[:, 0].tolist() == [1, 3]
    assert result.rounds[1].player1[0].tolist() == [0] * 8
    assert result.rounds[1].player2[0].tolist() == [2] * 8
    assert result.champions.tolist() == [0] * 8
    assert result.round_reach[:, 0].tolist() == [3, 1, 2, 1]
    assert len(provider.contexts) == len(result.predictions) == 3
    assert all(
        c.event.surface is Surface.CLAY and c.cutoff == CUTOFF
        for c in provider.contexts
    )
    assert result.predictions[0].warnings == ("synthetic uncalibrated probability",)


@pytest.mark.parametrize("rounds,best_of", [(2, 3), (6, 3), (7, 3), (7, 5)])
def test_byes_resolved_qualifiers_and_replacements_keep_their_slots(rounds, best_of):
    bracket = draw(rounds)
    slots = list(bracket.slots)
    slots[0] = replace(slots[0], kind=EntryKind.QUALIFIER)
    slots[1] = DrawSlot(position=2, kind=EntryKind.BYE, player_id=None)
    slots[2] = replace(
        slots[2],
        kind=EntryKind.REPLACEMENT,
        replaced_player_id=PlayerId("synthetic:former"),
    )
    slots[3] = replace(slots[3], kind=EntryKind.LUCKY_LOSER)
    bracket = replace(
        bracket, slots=tuple(slots), event=replace(bracket.event, best_of=best_of)
    )
    provider = Provider()
    result = simulate_tournament(
        bracket, provider, cutoff=CUTOFF, simulations=4, rng=np.random.default_rng(3)
    )
    assert result.rounds[0].player2[0].tolist() == [-1] * 4
    assert result.rounds[0].winners[0].tolist() == [0] * 4
    assert result.champions.tolist() == [0] * 4
    assert result.round_reach[0].tolist() == [rounds + 1] * 4
    assert all(c.event.best_of == best_of for c in provider.contexts)
    assert all(c.player2_id != PlayerId("synthetic:former") for c in provider.contexts)


def test_small_bracket_matches_independently_worked_analytic_probabilities():
    # P(p0 title) = .8 * (.6 * .7 + .4 * .9) = .624.
    probabilities = {
        ("p0", "p1"): 0.8,
        ("p2", "p3"): 0.6,
        ("p0", "p2"): 0.7,
        ("p0", "p3"): 0.9,
        ("p1", "p2"): 0.4,
        ("p1", "p3"): 0.5,
    }

    class AnalyticProvider(Provider):
        def predict(self, context):
            self.probability = probabilities[
                (context.player1_id.split(":")[1], context.player2_id.split(":")[1])
            ]
            return super().predict(context)

    result = simulate_tournament(
        draw(),
        AnalyticProvider(),
        cutoff=CUTOFF,
        simulations=40000,
        rng=np.random.default_rng(81),
    )
    assert np.mean(result.round_reach[0] >= 2) == pytest.approx(0.8, abs=0.01)
    assert np.mean(result.champions == 0) == pytest.approx(0.624, abs=0.012)
    assert len(result.predictions) == 6
    for sim in range(100):
        assert result.champions[sim] in result.rounds[0].winners[:, sim]


def test_independent_concurrent_runs_leave_global_random_streams_unchanged():
    def run(seed):
        return simulate_tournament(
            draw(),
            Provider(0.5),
            cutoff=CUTOFF,
            simulations=100,
            rng=np.random.default_rng(seed),
        )

    python_state, numpy_state = random.getstate(), np.random.get_state()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(run, [17, 17]))
    assert np.array_equal(first.champions, second.champions)
    assert first.rng_initial_state == second.rng_initial_state
    assert first.draw_digest == second.draw_digest
    assert random.getstate() == python_state
    assert np.array_equal(np.random.get_state()[1], numpy_state[1])
    assert np.random.get_state()[2:] == numpy_state[2:]
    with pytest.raises(ValueError):
        first.champions[0] = 1


@pytest.mark.parametrize("kind", [EntryKind.QUALIFIER, EntryKind.LUCKY_LOSER])
def test_unresolved_entrants_fail_instead_of_becoming_byes(kind):
    bracket = draw()
    bracket = replace(
        bracket,
        slots=(
            replace(bracket.slots[0], kind=kind, player_id=None),
            *bracket.slots[1:],
        ),
    )
    with pytest.raises(ValueError, match="Resolve"):
        simulate_tournament(
            bracket,
            Provider(),
            cutoff=CUTOFF,
            simulations=2,
            rng=np.random.default_rng(1),
        )


@pytest.mark.parametrize("simulations", [0, -1, True, 1.5])
def test_invalid_counts_fail(simulations):
    with pytest.raises(ValueError, match="positive integer"):
        simulate_tournament(
            draw(),
            Provider(),
            cutoff=CUTOFF,
            simulations=simulations,
            rng=np.random.default_rng(1),
        )


def test_explicit_withdrawals_do_not_count_as_played_losses_or_reach():
    result = simulate_tournament(
        draw(),
        Provider(),
        cutoff=CUTOFF,
        simulations=3,
        rng=np.random.default_rng(1),
        withdrawn=frozenset({PlayerId("synthetic:p0"), PlayerId("synthetic:p1")}),
    )
    assert result.rounds[0].kinds[0].tolist() == [OutcomeKind.VACANT] * 3
    assert result.rounds[1].kinds[0].tolist() == [OutcomeKind.UNCONTESTED] * 3
    assert result.champions.tolist() == [2] * 3
    assert result.round_reach[:, 0].tolist() == [0, 0, 3, 1]
    assert len(result.predictions) == 1


def test_explicit_retirement_only_applies_if_player_reaches_that_round():
    result = simulate_tournament(
        draw(),
        Provider(),
        cutoff=CUTOFF,
        simulations=3,
        rng=np.random.default_rng(1),
        retirements=(
            ForcedRetirement(PlayerId("synthetic:p0"), 2),
            ForcedRetirement(PlayerId("synthetic:p1"), 2),
        ),
    )
    assert result.champions.tolist() == [2] * 3
    assert result.rounds[1].kinds[0].tolist() == [OutcomeKind.RETIRED] * 3
    assert result.round_reach[:, 0].tolist() == [2, 1, 3, 1]
    assert len(result.predictions) == 2


def test_ambiguous_double_retirement_blocks_instead_of_inventing_a_winner():
    with pytest.raises(ValueError, match="Both opponents"):
        simulate_tournament(
            draw(),
            Provider(),
            cutoff=CUTOFF,
            simulations=1,
            rng=np.random.default_rng(1),
            retirements=(
                ForcedRetirement(PlayerId("synthetic:p0"), 1),
                ForcedRetirement(PlayerId("synthetic:p1"), 1),
            ),
        )


def test_all_withdrawn_is_explicitly_vacant_without_a_phantom_champion():
    bracket = draw()
    result = simulate_tournament(
        bracket,
        Provider(),
        cutoff=CUTOFF,
        simulations=2,
        rng=np.random.default_rng(1),
        withdrawn=frozenset(s.player_id for s in bracket.slots),
    )
    assert result.champions.tolist() == [-1, -1]
    assert not result.round_reach.any()


@pytest.mark.parametrize(
    "scenario",
    [
        {"withdrawn": frozenset({PlayerId("synthetic:p0")})},
        {"retirements": (ForcedRetirement(PlayerId("synthetic:p0"), 2),)},
    ],
)
def test_explicit_availability_cannot_double_count_marginal_provider_risk(scenario):
    with pytest.raises(ValueError, match="availability risk"):
        simulate_tournament(
            draw(),
            Provider(includes_risk=True),
            cutoff=CUTOFF,
            simulations=2,
            rng=np.random.default_rng(1),
            **scenario,
        )


def test_provider_risk_alone_is_allowed_without_invented_retirement_attribution():
    result = simulate_tournament(
        draw(),
        Provider(includes_risk=True),
        cutoff=CUTOFF,
        simulations=2,
        rng=np.random.default_rng(1),
    )
    assert result.champions.tolist() == [0, 0]
    assert result.rounds[0].kinds[0].tolist() == [OutcomeKind.DECIDED] * 2


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.swapped(),
        lambda p: replace(p, cutoff=p.cutoff - timedelta(days=1)),
        lambda p: replace(p, context_digest="0" * 64),
    ],
)
def test_mismatched_provider_responses_fail_closed(change):
    class BrokenProvider(Provider):
        def predict(self, context):
            return change(super().predict(context))

    with pytest.raises(ValueError, match="does not match"):
        simulate_tournament(
            draw(),
            BrokenProvider(),
            cutoff=CUTOFF,
            simulations=2,
            rng=np.random.default_rng(1),
        )


def test_shared_as_of_history_and_pair_specific_rankings_reach_the_provider():
    bracket = draw()
    prior = Match(
        match_id=MatchId("synthetic:prior"),
        event_id=EventId("synthetic:previous"),
        tour=Tour.ATP,
        player1_id=PlayerId("synthetic:p0"),
        player2_id=PlayerId("synthetic:p2"),
        surface=Surface.HARD,
        best_of=3,
        round_number=1,
        occurred_at=date(2026, 1, 1),
        status=MatchStatus.COMPLETED,
        winner_id=PlayerId("synthetic:p0"),
        score=None,
        provenance=bracket.provenance,
    )
    stats = PlayerMatchStats(
        match_id=prior.match_id,
        player_id=prior.player1_id,
        service_points=10,
        provenance=bracket.provenance,
    )
    ranking = RankingSnapshot(
        player_id=prior.player1_id,
        tour=Tour.ATP,
        ranking_date=date(2026, 1, 1),
        rank=1,
        points=None,
        provenance=bracket.provenance,
    )
    provider = Provider()
    simulate_tournament(
        bracket,
        provider,
        cutoff=CUTOFF,
        simulations=2,
        rng=np.random.default_rng(1),
        history=(prior,),
        statistics=(stats,),
        rankings=(ranking,),
    )
    assert all(
        c.history == (prior,) and c.statistics == (stats,) for c in provider.contexts
    )
    assert [c.rankings for c in provider.contexts] == [(ranking,), (), (ranking,)]
    with pytest.raises(ValueError, match="future results"):
        simulate_tournament(
            bracket,
            Provider(),
            cutoff=CUTOFF,
            simulations=2,
            rng=np.random.default_rng(1),
            history=(replace(prior, occurred_at=CUTOFF.date()),),
        )


@pytest.mark.parametrize("scope", ["draw", "event"])
def test_cutoff_checks_are_enforced_even_without_a_contested_match(scope):
    bracket = draw(1)
    future = replace(bracket.provenance, available_at=CUTOFF)
    if scope == "draw":
        bracket = replace(bracket, provenance=future)
    else:
        bracket = replace(bracket, event=replace(bracket.event, provenance=future))
    with pytest.raises(ValueError, match="available before"):
        simulate_tournament(
            bracket,
            Provider(),
            cutoff=CUTOFF,
            simulations=2,
            rng=np.random.default_rng(1),
            withdrawn=frozenset({PlayerId("synthetic:p0")}),
        )


@pytest.mark.parametrize(
    "scenario",
    [
        {"withdrawn": frozenset({PlayerId("synthetic:unknown")})},
        {"retirements": (ForcedRetirement(PlayerId("synthetic:p0"), 0),)},
        {"retirements": (ForcedRetirement(PlayerId("synthetic:p0"), 3),)},
        {"retirements": (ForcedRetirement(PlayerId("synthetic:p0"), True),)},
        {"retirements": (ForcedRetirement(PlayerId("synthetic:unknown"), 1),)},
        {"retirements": (ForcedRetirement(PlayerId("synthetic:p0"), 1),) * 2},
        {
            "withdrawn": frozenset({PlayerId("synthetic:p0")}),
            "retirements": (ForcedRetirement(PlayerId("synthetic:p0"), 1),),
        },
    ],
)
def test_invalid_availability_scenarios_fail(scenario):
    with pytest.raises(ValueError):
        simulate_tournament(
            draw(),
            Provider(),
            cutoff=CUTOFF,
            simulations=2,
            rng=np.random.default_rng(1),
            **scenario,
        )


@pytest.mark.parametrize("bit_generator", [np.random.MT19937, np.random.Philox])
def test_injected_generators_with_array_state_are_replayable(bit_generator):
    import json

    rng = np.random.Generator(bit_generator(9))
    first = simulate_tournament(
        draw(), Provider(0.5), cutoff=CUTOFF, simulations=20, rng=rng
    )
    restored = np.random.Generator(bit_generator())
    restored.bit_generator.state = json.loads(first.rng_initial_state)
    second = simulate_tournament(
        draw(), Provider(0.5), cutoff=CUTOFF, simulations=20, rng=restored
    )
    assert np.array_equal(first.champions, second.champions)
