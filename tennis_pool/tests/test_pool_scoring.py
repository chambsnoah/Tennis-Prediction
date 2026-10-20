"""Synthetic pool scoring cases derived from published tables, not workbooks."""

import pytest
import json
from dataclasses import replace
from datetime import date, datetime, timezone

from tennis_api.models.canonical import (
    Draw, DrawSlot, EntryKind, Event, EventId, Match, MatchId, MatchStatus,
    PlayerId, Provenance, RankingSnapshot, Surface, Tour,
)
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError

from tennis_pool.scoring import atp_points, bonus_points, score_player
from tennis_pool.results import score_tournament, TournamentScore
from tennis_pool.rules import load_register


@pytest.mark.parametrize("kind, losses, champion", [
    ("gs", (1, 7, 15, 30, 50, 90, 140), 200),
    ("m7", (1, 4, 7, 15, 25, 45, 70), 100),
    ("m6", (1, 7, 15, 25, 45, 70), 100),
])
def test_terminal_awards_match_pdf_table(kind, losses, champion):
    assert tuple(atp_points(i, kind) for i in range(1, len(losses) + 1)) == losses
    assert atp_points(None, kind) == champion


@pytest.mark.parametrize("round_number", [True, 1.0, 0, -1, 8])
def test_invalid_round_does_not_receive_points(round_number):
    with pytest.raises(ValueError):
        atp_points(round_number, "gs")


def test_missing_rank_is_only_required_for_two_unseeded_players():
    assert bonus_points(18, None, 17, None, True) == 10
    assert bonus_points(None, None, 18, None, True) == 10
    assert bonus_points(18, None, None, 1, True) == 0
    with pytest.raises(ValueError, match="ranking"):
        bonus_points(None, None, None, 40, True)


@pytest.mark.parametrize("seed", [0, -1, 33, True, 2.5])
def test_invalid_seed_does_not_receive_bonus(seed):
    with pytest.raises(ValueError):
        bonus_points(seed, 40, 1, 1, True)


def completed_event(kind="m6", overrides=None):
    """Explicit synthetic outcomes; no prediction model or workbook data."""
    rounds, size, byes, best_of = {
        "gs": (7, 128, 0, 5), "m7": (7, 128, 32, 3), "m6": (6, 64, 8, 3),
    }[kind]
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provenance = Provenance(
        source="synthetic", source_version="fixture-v1", source_record_id=None,
        observed_at=timestamp, available_at=timestamp, ingested_at=timestamp,
    )
    event = Event(
        event_id=EventId("test:event"), name="Synthetic event", tour=Tour.ATP,
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 14),
        surface=Surface.HARD, best_of=best_of, round_count=rounds,
        level="grand_slam" if kind == "gs" else "masters", provenance=provenance,
    )
    slots = tuple(
        DrawSlot(position=i, kind=EntryKind.BYE, player_id=None)
        if i % 2 == 0 and i <= byes * 2 else
        DrawSlot(position=i, kind=EntryKind.PLAYER, player_id=PlayerId(f"test:p{i}"))
        for i in range(1, size + 1)
    )
    draw = Draw(event=event, slots=slots, provenance=provenance)
    rankings = tuple(
        RankingSnapshot(player_id=s.player_id, tour=Tour.ATP, ranking_date=event.start_date,
                        rank=s.position, points=None, provenance=provenance)
        for s in slots if s.player_id is not None
    )
    matches = []
    active = [s.player_id for s in slots]
    for rnd in range(1, rounds + 1):
        next_round = []
        for p1, p2 in zip(active[::2], active[1::2]):
            if p1 is None or p2 is None:
                next_round.append(p1 or p2)
                continue
            status, winner = (overrides or {}).get((rnd, p1), (MatchStatus.COMPLETED, p1))
            loser = p2 if winner == p1 else p1
            matches.append(Match(
                match_id=MatchId(f"test:m{len(matches)}"), event_id=event.event_id,
                tour=Tour.ATP, player1_id=p1, player2_id=p2, surface=event.surface,
                best_of=best_of, round_number=rnd, occurred_at=date(2026, 1, rnd),
                status=status, winner_id=winner, score=None, provenance=provenance,
                withdrawn_player_id=loser if status is MatchStatus.WALKOVER else None,
            ))
            next_round.append(winner)
        active = next_round
    return draw, tuple(matches), rankings


@pytest.mark.parametrize("kind, champion, final_loss", [
    ("gs", 200, 140), ("m7", 100, 70), ("m6", 100, 70),
])
def test_complete_canonical_bracket_has_one_champion(kind, champion, final_loss):
    draw, matches, rankings = completed_event(kind)
    with pytest.raises(UnresolvedRulesError):
        score_tournament(draw, matches, rankings, kind)
    with pytest.warns(ProvisionalRulesWarning):
        result = score_tournament(draw, matches, rankings, kind, allow_provisional=True)
    by_id = {p.player_id: p for p in result.players}
    assert sum(p.lost_in_round is None for p in result.players) == 1
    assert by_id[PlayerId("test:p1")].atp == champion
    assert by_id[PlayerId(f"test:p{len(draw.slots) // 2 + 1}")].atp == final_loss
    assert result.rule_register_version == "2026-provisional-2"
    assert {entry[0] for entry in result.scoring_decisions} == {
        "walkovers", "mixed_bonus_order", "semifinal_points",
    }
    assert all(entry[1] == "provisional" for entry in result.scoring_decisions)
    assert TournamentScore.from_dict(result.to_dict()) == result


@pytest.mark.parametrize("winner_seed,loser_seed,expected", [
    (4, 1, 20), (4, 5, 0), (4, 9, 0), (4, None, 0),
    (8, 1, 30), (8, 5, 10), (8, 9, 0), (8, None, 0),
    (16, 1, 40), (16, 5, 20), (16, 9, 10), (16, None, 0),
    (None, 1, 50), (None, 5, 30), (None, 9, 20), (None, None, 10),
])
@pytest.mark.parametrize("is_gs", [True, False])
def test_every_published_bonus_cell(winner_seed, loser_seed, expected, is_gs):
    assert bonus_points(winner_seed, 80, loser_seed, 40, is_gs) == (
        expected if is_gs else expected // 2
    )


@pytest.mark.parametrize("winner,loser,expected", [
    ((1, None), (4, None), 0), ((5, None), (8, None), 0),
    ((9, None), (16, None), 0), ((17, None), (32, None), 0),
    ((32, None), (17, None), 10), ((None, 40), (None, 40), 0),
    ((None, 20), (None, 40), 0), ((None, 80), (None, 40), 10),
])
def test_same_band_better_worse_equal_ordering(winner, loser, expected):
    assert bonus_points(*winner, *loser, True) == expected


def test_published_example_component_totals():
    # Synthetic opponents reproducing the published 321 + 70 = 391 totals;
    # these are not purported observations of the example's actual match paths.
    scores = [
        score_player([], None, "gs", 1, None),
        score_player([(2, None)], 6, "gs", 8, None),
        score_player([], 1, "gs", 4, None),
        score_player([], 3, "gs", 1, None),
        score_player([(1, None)], 3, "gs", 9, None),
    ]
    assert [s.total for s in scores] == [200, 120, 1, 15, 55]
    assert sum(s.atp for s in scores) == 321
    assert sum(s.bonus for s in scores) == 70
    assert sum(s.total for s in scores) == 391


def provisional_score(draw, matches, rankings, kind="m6", **kwargs):
    with pytest.warns(ProvisionalRulesWarning):
        return score_tournament(draw, matches, rankings, kind, allow_provisional=True, **kwargs)


def test_walkovers_byes_retirements_and_later_withdrawal():
    draw, matches, rankings = completed_event(overrides={
        (2, "test:p1"): (MatchStatus.WALKOVER, PlayerId("test:p1")),
        (3, "test:p1"): (MatchStatus.RETIRED, PlayerId("test:p5")),
        (4, "test:p5"): (MatchStatus.WALKOVER, PlayerId("test:p9")),
        (1, "test:p17"): (MatchStatus.WALKOVER, PlayerId("test:p18")),
    })
    result = provisional_score(draw, matches, rankings)
    by_id = {p.player_id: p for p in result.players}
    # Both p1/p3 had byes: p3 never participated, p1 advanced by walkover.
    assert (by_id[PlayerId("test:p3")].atp, by_id[PlayerId("test:p3")].total) == (0, 0)
    assert by_id[PlayerId("test:p3")].withdrew_before_participation
    assert by_id[PlayerId("test:p1")].atp == 15  # retirement after play, round 3
    assert by_id[PlayerId("test:p1")].bonus == 0  # bye/walkover are not upset wins
    assert by_id[PlayerId("test:p5")].played_wins == (PlayerId("test:p7"), PlayerId("test:p1"))
    assert (by_id[PlayerId("test:p5")].atp, by_id[PlayerId("test:p5")].bonus) == (25, 5)
    assert not by_id[PlayerId("test:p5")].withdrew_before_participation
    assert by_id[PlayerId("test:p17")].total == 0
    assert PlayerId("test:p17") not in by_id[PlayerId("test:p18")].played_wins


@pytest.mark.parametrize("mutation", [
    "missing_final", "duplicate_match", "duplicate_id", "wrong_event", "wrong_round",
    "wrong_surface", "wrong_format", "wrong_tour", "outside_dates", "scheduled",
    "withdrawn", "unknown_withdrawal", "wrong_path", "extra_match", "unknown_player",
])
def test_malformed_or_incomplete_results_fail_closed(mutation):
    draw, records, rankings = completed_event()
    matches = list(records)
    first = matches[0]
    if mutation == "missing_final":
        matches.pop()
    elif mutation == "duplicate_match":
        matches.append(replace(first, match_id=MatchId("test:duplicate")))
    elif mutation == "duplicate_id":
        matches[1] = replace(matches[1], match_id=first.match_id)
    elif mutation == "wrong_event":
        matches[0] = replace(first, event_id=EventId("test:other"))
    elif mutation == "wrong_round":
        matches[0] = replace(first, round_number=7)
    elif mutation == "wrong_surface":
        matches[0] = replace(first, surface=Surface.CLAY)
    elif mutation == "wrong_format":
        matches[0] = replace(first, best_of=5)
    elif mutation == "wrong_tour":
        matches[0] = replace(first, tour=Tour.WTA)
    elif mutation == "outside_dates":
        matches[0] = replace(first, occurred_at=date(2026, 1, 15))
    elif mutation in ("scheduled", "withdrawn"):
        matches[0] = replace(first, status=MatchStatus(mutation), winner_id=None)
    elif mutation == "unknown_withdrawal":
        matches[0] = replace(first, status=MatchStatus.WALKOVER)
    elif mutation == "wrong_path":
        matches[0] = replace(first, winner_id=first.player2_id)
    elif mutation == "extra_match":
        matches.append(replace(first, match_id=MatchId("test:extra"), round_number=6))
    elif mutation == "unknown_player":
        matches[0] = replace(first, player2_id=PlayerId("test:unknown"))
    with pytest.raises(ValueError):
        provisional_score(draw, tuple(matches), rankings)


def test_rankings_are_not_fabricated_or_taken_from_after_start():
    draw, matches, rankings = completed_event()
    with pytest.raises(ValueError, match="ranking"):
        provisional_score(draw, matches, ())
    with pytest.raises(ValueError, match="ranking"):
        provisional_score(draw, matches, rankings + rankings[:1])
    late = replace(rankings[0], provenance=replace(
        rankings[0].provenance,
        available_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    ))
    with pytest.raises(ValueError, match="ranking"):
        provisional_score(draw, matches, (late,) + rankings[1:])


def test_input_order_is_irrelevant_but_evidence_changes_digest():
    draw, matches, rankings = completed_event()
    before = draw.to_dict(), [m.to_dict() for m in matches], [r.to_dict() for r in rankings]
    result = provisional_score(draw, matches, rankings)
    assert provisional_score(draw, matches[::-1], rankings[::-1]) == result
    changed = (replace(rankings[0], rank=1000),) + rankings[1:]
    assert provisional_score(draw, matches, changed).input_digest != result.input_digest
    assert (draw.to_dict(), [m.to_dict() for m in matches], [r.to_dict() for r in rankings]) == before


@pytest.mark.parametrize("change", ["version", "decision"])
def test_unimplemented_rule_changes_do_not_silently_change_scores(tmp_path, change):
    draw, matches, rankings = completed_event()
    register = load_register()
    if change == "version":
        register["register_version"] = "2026-provisional-3"
    else:
        register["decisions"]["walkovers"]["decision"] = "Award a bonus for every walkover."
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(register))
    with pytest.raises(ValueError, match="implementation review"):
        provisional_score(draw, matches, rankings, register_path=path)


def test_later_walkover_loss_keeps_entitlement_after_walkover_advancement():
    draw, matches, rankings = completed_event(overrides={
        (2, "test:p1"): (MatchStatus.WALKOVER, PlayerId("test:p1")),
        (3, "test:p1"): (MatchStatus.WALKOVER, PlayerId("test:p5")),
    })
    result = provisional_score(draw, matches, rankings)
    player = next(p for p in result.players if p.player_id == "test:p1")
    assert (player.atp, player.bonus, player.played_wins) == (15, 0, ())
    assert not player.withdrew_before_participation


@pytest.mark.parametrize("mutation", ["unresolved", "kind", "tour", "seed_limit", "format"])
def test_incompatible_pool_draw_is_rejected(mutation):
    draw, matches, rankings = completed_event()
    kind = "m6"
    if mutation == "unresolved":
        draw = replace(draw, slots=(replace(draw.slots[0], player_id=None, kind=EntryKind.QUALIFIER),) + draw.slots[1:])
    elif mutation == "kind":
        kind = "unknown"
    elif mutation == "tour":
        draw = replace(draw, event=replace(draw.event, tour=Tour.WTA))
    elif mutation == "seed_limit":
        draw = replace(draw, slots=(replace(draw.slots[0], seed=17),) + draw.slots[1:])
    elif mutation == "format":
        draw = replace(draw, event=replace(draw.event, best_of=5))
    with pytest.raises(ValueError):
        provisional_score(draw, matches, rankings, kind)


@pytest.mark.parametrize("checked,expected_exit", [(None, 1), (0, 1), (515, 1), (563, 1), (564, 0)])
def test_legacy_diagnostic_cannot_pass_without_required_fixture_count(
    tmp_path, monkeypatch, checked, expected_exit,
):
    from pool_optimizer.tests import test_scoring as legacy

    monkeypatch.setattr(legacy, "DATA", tmp_path)
    monkeypatch.setattr(legacy, "FILES", {"Synthetic": "synthetic.xlsm"})
    if checked is not None:
        (tmp_path / "synthetic.xlsm").touch()
        monkeypatch.setattr(legacy, "validate", lambda *args, **kwargs: (checked, 0, 0))
    assert legacy.main() == expected_exit
