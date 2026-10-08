"""Synthetic contract fixtures: no provider requests or participant data."""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta, timezone
import json

import pytest

from tennis_api.models.canonical import (
    Coverage,
    Draw,
    DrawSlot,
    EntryKind,
    Event,
    EventId,
    Match,
    MatchId,
    MatchProbability,
    MatchProbabilityProvider,
    MatchScore,
    MatchStatus,
    Player,
    PlayerId,
    PlayerMatchStats,
    PredictionContext,
    Provenance,
    RankingSnapshot,
    Surface,
    Tour,
)


P1 = PlayerId("canonical:p1")
P2 = PlayerId("canonical:p2")
NOW = datetime(2026, 1, 3, 12, tzinfo=timezone.utc)


@pytest.fixture
def provenance():
    return Provenance(
        source="synthetic",
        source_version="fixture-1",
        source_record_id=None,
        observed_at=date(2026, 1, 1),
        available_at=NOW - timedelta(days=1),
        ingested_at=NOW,
    )


@pytest.fixture
def event(provenance):
    return Event(
        event_id=EventId("canonical:2026-fixture"),
        name="Synthetic event",
        tour=Tour.ATP,
        start_date=date(2026, 1, 3),
        end_date=date(2026, 1, 10),
        surface=Surface.HARD,
        best_of=3,
        round_count=2,
        level="fixture",
        provenance=provenance,
    )


@pytest.fixture
def match(event, provenance):
    return Match(
        match_id=MatchId("canonical:prior"),
        event_id=event.event_id,
        tour=Tour.ATP,
        player1_id=P1,
        player2_id=P2,
        surface=Surface.CLAY,
        best_of=3,
        round_number=1,
        occurred_at=date(2026, 1, 1),
        status=MatchStatus.COMPLETED,
        winner_id=P1,
        score=MatchScore(sets=((7, 6), (6, 4)), tiebreak_points=((7, 3), None)),
        provenance=provenance,
    )


@pytest.fixture
def context(event, match, provenance):
    ranking = RankingSnapshot(
        player_id=P1,
        tour=Tour.ATP,
        ranking_date=date(2026, 1, 1),
        rank=None,
        points=None,
        provenance=provenance,
    )
    stats = PlayerMatchStats(
        match_id=match.match_id,
        player_id=P1,
        provenance=provenance,
        service_points=50,
        first_serves_in=30,
        first_serve_points_won=20,
    )
    return PredictionContext(
        event=event,
        player1_id=P1,
        player2_id=P2,
        round_number=1,
        cutoff=NOW,
        target_match_id=MatchId("canonical:target"),
        rankings=(ranking,),
        history=(match,),
        statistics=(stats,),
    )


def probability(context):
    return MatchProbability(
        player1_id=context.player1_id,
        player2_id=context.player2_id,
        player1_win_probability=0.7,
        model_version="synthetic-v1",
        calibration_version=None,
        cutoff=context.cutoff,
        context_digest=context.digest,
        coverage=Coverage(observed=("ranking",), missing=("return_points",)),
        warnings=("synthetic, uncalibrated",),
        includes_availability_risk=False,
    )


def test_all_contracts_json_round_trip_without_mutation(context, provenance):
    draw = Draw(
        event=context.event,
        provenance=provenance,
        slots=(
            DrawSlot(position=1, kind=EntryKind.PLAYER, player_id=P1, seed=1),
            DrawSlot(position=2, kind=EntryKind.BYE, player_id=None),
            DrawSlot(position=3, kind=EntryKind.QUALIFIER, player_id=None),
            DrawSlot(
                position=4,
                kind=EntryKind.REPLACEMENT,
                player_id=P2,
                replaced_player_id=PlayerId("canonical:withdrawn"),
            ),
        ),
    )
    records = [
        provenance,
        replace(provenance, observed_at=None),
        replace(provenance, observed_at=NOW - timedelta(days=2)),
        Player(
            player_id=P1, display_name="Same Name", tour=Tour.ATP, provenance=provenance
        ),
        context.event,
        context.history[0],
        context.history[0].score,
        context.rankings[0],
        context.statistics[0],
        draw,
        *draw.slots,
        context,
        probability(context),
        probability(context).coverage,
    ]
    for record in records:
        payload = json.loads(json.dumps(record.to_dict(), allow_nan=False))
        before = json.dumps(payload, sort_keys=True)
        assert type(record).from_dict(payload) == record
        assert json.dumps(payload, sort_keys=True) == before
        assert record.schema_version == 1
        with pytest.raises(FrozenInstanceError):
            record.schema_version = 2


def test_duplicate_display_names_are_not_identity(provenance):
    first = Player(
        player_id=P1, display_name="Same Name", tour=Tour.ATP, provenance=provenance
    )
    second = replace(first, player_id=P2)
    assert first.display_name == second.display_name
    assert first.player_id != second.player_id


@pytest.mark.parametrize(
    "identifier", ["", "Surname", "a b:c", "ATP:12", "atp:", " atp:12"]
)
def test_unresolved_name_keys_are_rejected(identifier, provenance):
    with pytest.raises(ValueError):
        Player(
            player_id=identifier,
            display_name="Name",
            tour=Tour.ATP,
            provenance=provenance,
        )


@pytest.mark.parametrize("version", [None, 0, 2, "1", True])
def test_unknown_or_missing_schema_versions_fail(version, context):
    payload = context.to_dict()
    if version is None:
        del payload["schema_version"]
    else:
        payload["schema_version"] = version
    with pytest.raises(ValueError):
        PredictionContext.from_dict(payload)
    payload = context.to_dict()
    payload["event"]["provenance"]["schema_version"] = version
    with pytest.raises(ValueError):
        PredictionContext.from_dict(payload)


@pytest.mark.parametrize("field", ["ownership", "quotas", "pool_scores", "features"])
def test_pool_state_cannot_enter_prediction_context(field, context):
    payload = context.to_dict()
    payload[field] = {"value": 99}
    with pytest.raises(ValueError, match="Unknown"):
        PredictionContext.from_dict(payload)
    with pytest.raises(TypeError):
        PredictionContext(
            **{**{f.name: getattr(context, f.name) for f in fields(context)}, field: 99}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"cutoff": NOW.replace(tzinfo=None)},
        {"player2_id": P1},
        {"round_number": 0},
        {"round_number": 3},
        {"round_number": True},
        {"rankings": []},
    ],
)
def test_context_rejects_invalid_types_and_shape(changes, context):
    with pytest.raises(ValueError):
        replace(context, **changes)


def test_missing_statistics_never_become_invented_measurements(context):
    stats = context.statistics[0]
    assert stats.return_points is None
    assert stats.aces is None
    assert context.rankings[0].rank is None
    missing = PlayerMatchStats.from_dict(
        {
            key: value
            for key, value in stats.to_dict().items()
            if key not in ("aces", "return_points")
        }
    )
    assert missing.aces is None and missing.return_points is None
    measured_zero = replace(stats, aces=0, return_points=0, return_points_won=0)
    assert measured_zero != stats


@pytest.mark.parametrize(
    "changes",
    [
        {"aces": -1},
        {"aces": True},
        {"return_points": 10, "return_points_won": 11},
        {"first_serves_in": 51},
        {"first_serve_points_won": 31},
        {"second_serve_points_won": 21},
        {"break_points_faced": 0, "break_points_saved": 1},
    ],
)
def test_statistics_validate_counts_and_denominators(changes, context):
    with pytest.raises(ValueError):
        replace(context.statistics[0], **changes)


@pytest.mark.parametrize(
    "status",
    [
        MatchStatus.RETIRED,
        MatchStatus.WALKOVER,
        MatchStatus.WITHDRAWN,
        MatchStatus.CANCELLED,
    ],
)
def test_unplayed_and_incomplete_match_status_round_trips(status, match):
    decided = status in (MatchStatus.RETIRED, MatchStatus.WALKOVER)
    result = replace(
        match,
        status=status,
        winner_id=P1 if decided else None,
        score=MatchScore(sets=((2, 1),)) if status is MatchStatus.RETIRED else None,
    )
    assert Match.from_dict(result.to_dict()) == result


@pytest.mark.parametrize(
    "changes",
    [
        {"winner_id": PlayerId("canonical:outsider")},
        {"winner_id": None},
        {"score": MatchScore(sets=((6, 4),))},
        {"score": MatchScore(sets=((4, 6), (4, 6)))},
        {"score": MatchScore(sets=((6, 4), (6, 4), (6, 4)))},
        {"score": MatchScore(sets=((6, 5), (6, 4)))},
        {"status": MatchStatus.WALKOVER},
        {"status": MatchStatus.SCHEDULED},
    ],
)
def test_inconsistent_match_results_are_rejected(changes, match):
    with pytest.raises(ValueError):
        replace(match, **changes)


def test_winner_id_and_score_orientation_survive_swap(match):
    swapped = match.swapped()
    assert swapped.winner_id == match.winner_id
    assert swapped.score.sets == ((6, 7), (4, 6))
    assert swapped.score.tiebreak_points == ((3, 7), None)
    assert swapped.swapped() == match


@pytest.mark.parametrize("size,byes", [(128, 0), (128, 32), (64, 8)])
def test_full_slam_and_masters_draw_shapes(size, byes, event, provenance):
    slots = tuple(
        DrawSlot(
            position=i,
            kind=EntryKind.BYE if i <= byes * 2 and i % 2 == 0 else EntryKind.PLAYER,
            player_id=None
            if i <= byes * 2 and i % 2 == 0
            else PlayerId(f"fixture:p{i}"),
        )
        for i in range(1, size + 1)
    )
    draw = Draw(
        event=replace(event, round_count=size.bit_length() - 1),
        slots=slots,
        provenance=provenance,
    )
    assert sum(slot.player_id is not None for slot in draw.slots) == size - byes
    assert Draw.from_dict(draw.to_dict()) == draw


@pytest.mark.parametrize("kind", [EntryKind.QUALIFIER, EntryKind.LUCKY_LOSER])
def test_unresolved_qualifiers_stay_distinct_from_byes(kind):
    slot = DrawSlot(position=1, kind=kind, player_id=None)
    assert slot.kind is not EntryKind.BYE
    assert replace(slot, player_id=P1).player_id == P1


def test_draw_rejects_duplicate_players_bad_slots_and_double_byes(event, provenance):
    slots = tuple(
        DrawSlot(position=i, kind=EntryKind.PLAYER, player_id=PlayerId(f"fixture:p{i}"))
        for i in range(1, 5)
    )
    for invalid in (
        slots[:2],
        slots[::-1],
        (slots[0], replace(slots[1], player_id=slots[0].player_id), *slots[2:]),
        (
            replace(slots[0], kind=EntryKind.BYE, player_id=None),
            replace(slots[1], kind=EntryKind.BYE, player_id=None),
            *slots[2:],
        ),
    ):
        with pytest.raises(ValueError):
            Draw(event=event, slots=invalid, provenance=provenance)


@pytest.mark.parametrize("target", ["event", "ranking", "match", "stats"])
def test_available_at_cutoff_or_later_is_excluded(target, context):
    late = replace(context.event.provenance, available_at=NOW)
    changes = {
        "event": {"event": replace(context.event, provenance=late)},
        "ranking": {"rankings": (replace(context.rankings[0], provenance=late),)},
        "match": {"history": (replace(context.history[0], provenance=late),)},
        "stats": {"statistics": (replace(context.statistics[0], provenance=late),)},
    }
    with pytest.raises(ValueError, match="available"):
        replace(context, **changes[target])


def test_date_only_history_cannot_leak_into_same_day(context):
    assert replace(
        context,
        history=(replace(context.history[0], occurred_at=NOW - timedelta(seconds=1)),),
    )
    for occurred_at in (NOW, NOW + timedelta(seconds=1), NOW.date(), None):
        with pytest.raises(ValueError, match="history"):
            replace(
                context, history=(replace(context.history[0], occurred_at=occurred_at),)
            )


def test_context_rejects_target_cross_tour_and_unrelated_stats(context):
    for changes in (
        {"target_match_id": context.history[0].match_id},
        {"history": (replace(context.history[0], tour=Tour.WTA),)},
        {"history": context.history * 2},
        {"rankings": (replace(context.rankings[0], tour=Tour.WTA),)},
        {"rankings": context.rankings * 2},
        {
            "statistics": (
                replace(context.statistics[0], player_id=PlayerId("canonical:p3")),
            )
        },
        {"statistics": context.statistics * 2},
    ):
        with pytest.raises(ValueError):
            replace(context, **changes)


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf"), True, "0.5"])
def test_invalid_probabilities_fail(value, context):
    with pytest.raises(ValueError):
        replace(probability(context), player1_win_probability=value)


def test_probability_lineage_and_swapped_provider_contract(context):
    class SyntheticProvider:
        def predict(self, request: PredictionContext) -> MatchProbability:
            response = probability(context)
            return response if request.player1_id == P1 else response.swapped()

    provider: MatchProbabilityProvider = SyntheticProvider()
    result = provider.predict(context)
    swapped = provider.predict(context.swapped())
    result.require_context(context)
    swapped.require_context(context.swapped())
    assert (
        result.player1_win_probability + swapped.player1_win_probability
        == pytest.approx(1)
    )
    assert swapped.model_version == result.model_version
    assert swapped.calibration_version is None
    assert swapped.coverage == result.coverage and swapped.warnings == result.warnings
    assert swapped.includes_availability_risk is False
    with pytest.raises(ValueError, match="orientation/cutoff"):
        swapped.require_context(context)
    with pytest.raises(ValueError, match="orientation/cutoff"):
        replace(result, cutoff=NOW + timedelta(seconds=1)).require_context(context)


def test_probability_coverage_cannot_hide_conflicting_missingness():
    with pytest.raises(ValueError):
        Coverage(observed=("serve",), missing=("serve",))
    with pytest.raises(ValueError):
        Coverage(observed=("serve", "serve"), missing=())


def test_legacy_match_export_remains_unchanged():
    from tennis_api.models import Match as LegacyMatch
    from tennis_api.models.tournament_data import Match as ExistingMatch

    assert LegacyMatch is ExistingMatch
    assert LegacyMatch is not Match


@pytest.mark.parametrize(
    "changes",
    [
        {"surface": Surface.GRASS},
        {"best_of": 5},
        {"event_id": EventId("canonical:other-event")},
    ],
)
def test_probability_is_bound_to_event_and_format(changes, context):
    with pytest.raises(ValueError, match="context"):
        probability(context).require_context(
            replace(context, event=replace(context.event, **changes))
        )


def test_probability_digest_binds_target_history_and_survives_swap(context):
    assert context.digest == context.swapped().digest
    assert context.digest == PredictionContext.from_dict(context.to_dict()).digest
    assert probability(context).swapped().context_digest == context.digest
    for altered in (
        replace(context, target_match_id=MatchId("canonical:another-target")),
        replace(context, round_number=2),
        replace(context, statistics=()),
    ):
        with pytest.raises(ValueError, match="context"):
            probability(context).require_context(altered)


@pytest.mark.parametrize("points", [(3, 7), (6, 7), (7, 6), (2, 0)])
def test_tiebreak_outcome_must_agree_with_games(points):
    with pytest.raises(ValueError, match="Tiebreak"):
        MatchScore(sets=((7, 6),), tiebreak_points=(points,))
    assert MatchScore(sets=((7, 6),), tiebreak_points=(None,))


def test_seed_range_counts_unresolved_entrants_not_byes(event, provenance):
    draw = Draw(
        event=event,
        provenance=provenance,
        slots=(
            DrawSlot(position=1, kind=EntryKind.PLAYER, player_id=P1, seed=2),
            DrawSlot(position=2, kind=EntryKind.BYE, player_id=None),
            DrawSlot(position=3, kind=EntryKind.QUALIFIER, player_id=None),
            DrawSlot(position=4, kind=EntryKind.LUCKY_LOSER, player_id=None),
        ),
    )
    assert Draw.from_dict(draw.to_dict()) == draw
    with pytest.raises(ValueError, match="Seed exceeds"):
        replace(draw, slots=(replace(draw.slots[0], seed=4), *draw.slots[1:]))


@pytest.mark.parametrize("counts", [{"aces": 11}, {"double_faults": 1}])
def test_serve_counts_cannot_exceed_opportunities(counts, provenance):
    stats = PlayerMatchStats(
        match_id=MatchId("canonical:match"),
        player_id=P1,
        provenance=provenance,
        service_points=10,
        first_serves_in=10,
    )
    with pytest.raises(ValueError, match="exceeds"):
        replace(stats, **counts)
    assert replace(stats, service_points=None, first_serves_in=None, **counts)


def test_second_serve_outcomes_are_mutually_exclusive(provenance):
    stats = PlayerMatchStats(
        match_id=MatchId("canonical:match"),
        player_id=P1,
        provenance=provenance,
        service_points=20,
        first_serves_in=10,
        second_serve_points_won=6,
    )
    with pytest.raises(ValueError, match="outcomes exceed"):
        replace(stats, double_faults=6)
    assert replace(stats, double_faults=4)
    assert replace(stats, second_serve_points_won=None, double_faults=6)
    assert replace(stats, service_points=None, double_faults=6)


def test_aces_cannot_exceed_known_service_points_won(provenance):
    stats = PlayerMatchStats(
        match_id=MatchId("canonical:match"),
        player_id=P1,
        provenance=provenance,
        service_points=10,
        first_serves_in=6,
        first_serve_points_won=2,
        second_serve_points_won=1,
        aces=3,
    )
    with pytest.raises(ValueError, match="Aces"):
        replace(stats, aces=4)
    with pytest.raises(ValueError, match="Aces"):
        PlayerMatchStats.from_dict({**stats.to_dict(), "aces": 4})
    assert replace(stats, aces=4, first_serve_points_won=None)
    assert replace(stats, aces=4, second_serve_points_won=None)


@pytest.mark.parametrize("points", [(8, 2), (9, 2), (11, 2), (2, 8)])
def test_completed_tiebreak_cannot_continue_after_deciding_point(points):
    games = (7, 6) if points[0] > points[1] else (6, 7)
    with pytest.raises(ValueError, match="Tiebreak"):
        MatchScore(sets=(games,), tiebreak_points=(points,))
    with pytest.raises(ValueError, match="Tiebreak"):
        MatchScore.from_dict(
            {"schema_version": 1, "sets": [games], "tiebreak_points": [points]}
        )


@pytest.mark.parametrize("points", [(7, 2), (9, 7), (10, 2), (12, 10)])
def test_completed_seven_or_ten_point_tiebreak_remains_representable(points):
    score = MatchScore(sets=((7, 6),), tiebreak_points=(points,))
    assert MatchScore.from_dict(score.to_dict()) == score


def test_withdrawal_identity_round_trips_and_survives_swap(match):
    withdrawn = replace(
        match,
        status=MatchStatus.WITHDRAWN,
        winner_id=None,
        score=None,
        withdrawn_player_id=P1,
    )
    assert Match.from_dict(withdrawn.to_dict()) == withdrawn
    assert withdrawn.swapped().withdrawn_player_id == P1
    assert replace(withdrawn, withdrawn_player_id=P2) != withdrawn
    assert replace(withdrawn, withdrawn_player_id=None).withdrawn_player_id is None
    walkover = replace(withdrawn, status=MatchStatus.WALKOVER, winner_id=P2)
    assert Match.from_dict(walkover.to_dict()) == walkover
    with pytest.raises(ValueError, match="Withdrawal"):
        replace(walkover, winner_id=P1)
    with pytest.raises(ValueError, match="Withdrawal"):
        replace(withdrawn, withdrawn_player_id=PlayerId("canonical:outsider"))
    with pytest.raises(ValueError, match="Withdrawal"):
        replace(match, withdrawn_player_id=P1)


@pytest.mark.parametrize("best_of", [3, 5])
@pytest.mark.parametrize("swapped", [False, True])
def test_historical_twelve_all_deciding_tiebreak_round_trips(best_of, swapped, match):
    split_sets = ((6, 4), (4, 6)) * (best_of // 2)
    score = MatchScore(
        sets=(*split_sets, (13, 12)),
        tiebreak_points=(*(None for _ in split_sets), (7, 3)),
    )
    result = replace(match, best_of=best_of, score=score)
    if swapped:
        result = result.swapped()
    assert Match.from_dict(result.to_dict()) == result
    assert result.swapped().swapped() == result


@pytest.mark.parametrize(
    "sets",
    [
        ((13, 12), (6, 4), (6, 4)),
        ((6, 4), (4, 6), (6, 4), (13, 12)),
        ((4, 6), (6, 4), (4, 6), (13, 12), (6, 4)),
    ],
)
def test_twelve_all_tiebreak_requires_actual_deciding_set(sets, match):
    with pytest.raises(ValueError, match="incomplete set"):
        replace(match, best_of=5, score=MatchScore(sets=sets))


def test_historical_in_progress_twelve_all_tiebreak_round_trips(match):
    result = replace(
        match,
        status=MatchStatus.RETIRED,
        score=MatchScore(
            sets=((6, 4), (4, 6), (12, 12)),
            tiebreak_points=(None, None, (3, 2)),
        ),
    )
    assert Match.from_dict(result.to_dict()) == result
