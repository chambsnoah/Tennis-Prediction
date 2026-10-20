"""Rules tests at the canonical TennisMatch simulation boundary."""

from concurrent.futures import ThreadPoolExecutor
import random

import pytest

from tennis_preds.tennis import Player, PlayerSimple, TennisMatch


def simulate(seed):
    match = TennisMatch(PlayerSimple("A", 0.62), PlayerSimple("B", 0.58),
                        sets_to_win=2, rng=random.Random(seed))
    match.simulate_match(verbose=False)
    return vars(match) | {"player1": None, "player2": None, "rng": None}


def test_match_rng_is_injected_reproducible_and_independent():
    state = random.getstate()
    expected = simulate(7)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(simulate, [7, 11, 7]))
    assert results[0] == results[2] == expected
    assert results[1] != expected
    assert random.getstate() == state


def test_seed_does_not_reseed_global_randomness():
    state = random.getstate()
    match = TennisMatch(PlayerSimple(), PlayerSimple(), sets_to_win=2, seed=7)
    match.simulate_match(verbose=False)
    assert random.getstate() == state


class PointScript:
    """A random source that also observes the public current-server state."""

    def __init__(self, points):
        self.points = iter(points)
        self.servers = []

    def random(self):
        server, winner = next(self.points)
        self.servers.append(1 if self.match.player1_to_serve else 2)
        return 0.0 if server == winner else 0.99


def play_script(points, **kwargs):
    rng = PointScript(points)
    match = TennisMatch(PlayerSimple("A"), PlayerSimple("B"), rng=rng, **kwargs)
    rng.match = match
    match.simulate_match(verbose=False)
    assert rng.servers == [server for server, _ in points]
    assert next(rng.points, None) is None
    return match


def test_deuce_advantage_saved_break_point_and_service_alternation():
    # A serves: 40-0, deuce, B advantage, deuce, A advantage, game A.
    points = [(1, winner) for winner in [1, 1, 1, 2, 2, 2, 2, 1, 1, 1]]
    points += [(server, 1) for server in [2, 1, 2, 1, 2] for _ in range(4)]
    points += [(server, 1) for server in [1, 2, 1, 2, 1, 2] for _ in range(4)]
    match = play_script(points, sets_to_win=2)
    assert match.player1_games_won_per_set == [6, 6]
    assert match.player2_games_won_per_set == [0, 0]
    assert match.player2_break_point_chances == 1
    assert match.player2_break_points_converted == 0
    # Three return games per set, each converted at love on its sole chance.
    assert match.player1_break_point_chances == 6
    assert match.player1_break_points_converted == 6
    assert match.player1_total_points_won == 50
    assert match.player2_total_points_won == 4


@pytest.mark.parametrize("deciding_target", [7, 10])
@pytest.mark.parametrize("sets_to_win", [2, 3])
def test_normal_and_deciding_tiebreaks_win_by_two_and_next_set_server(deciding_target, sets_to_win):
    points = [(server, server) for server in [1, 2] * 6 for _ in range(4)]
    # First tiebreak extends to 8-6. Serve order: one, then pairs.
    servers = [1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 2]
    points += list(zip(servers, [1, 2] * 6 + [1, 1]))
    # B (the tiebreak's first receiver) serves first in the next set, wins 6-0.
    points += [(server, 2) for server in [2, 1] * 3 for _ in range(4)]
    if sets_to_win == 3:
        points += [(server, winner) for winner in [1, 2] for server in [2, 1] * 3 for _ in range(4)]
    points += [(server, server) for server in [2, 1] * 6 for _ in range(4)]
    servers = [2, 1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1]
    winners = [1, 2] * (deciding_target - 1) + [1, 1]
    points += list(zip(servers, winners))
    match = play_script(points, sets_to_win=sets_to_win, deciding_tiebreak_points=deciding_target)
    assert match.player1_games_won_per_set == ([7, 0, 7] if sets_to_win == 2 else [7, 0, 6, 0, 7])
    assert match.player2_games_won_per_set == ([6, 6, 6] if sets_to_win == 2 else [6, 6, 0, 6, 6])
    assert match.player1_points_won_in_tiebreak_per_set == [8] + [0] * (2 * sets_to_win - 3) + [deciding_target + 1]
    assert match.player2_points_won_in_tiebreak_per_set == [6] + [0] * (2 * sets_to_win - 3) + [deciding_target - 1]
    assert match.total_tiebreaks_played == match.player1_tiebreaks_won == 2
    assert match.player1_service_games_played == match.player2_service_games_played == (15 if sets_to_win == 2 else 21)
    assert match.player1_sets_won == sets_to_win
    assert match.player2_sets_won == sets_to_win - 1


@pytest.mark.parametrize("kwargs", [
    {"sets_to_win": 0}, {"sets_to_win": True}, {"sets_to_win": 2.5},
    {"deciding_tiebreak_points": 0}, {"deciding_tiebreak_points": True},
    {"deciding_tiebreak_points": 8}, {"seed": 7, "rng": random.Random(7)},
])
def test_invalid_rules_or_ambiguous_random_source_fail_before_play(kwargs):
    with pytest.raises(ValueError):
        TennisMatch(PlayerSimple(), PlayerSimple(), **kwargs)


@pytest.mark.parametrize("sets_to_win", [1, 2, 3])
@pytest.mark.parametrize("first_server", [True, False])
def test_double_faults_probability_boundaries_and_best_of_formats(sets_to_win, first_server, capsys):
    class ZeroRandom:
        def random(self):
            return 0.0

    # A always double faults. B always lands and wins its first serve.
    a = Player("A", 0, 0, 0, 0)
    b = Player("B", 1, 1, 1, 1)
    match = TennisMatch(a, b, sets_to_win=sets_to_win,
                        player1_to_serve=first_server, rng=ZeroRandom())
    match.simulate_match(verbose=False)
    assert match.get_match_winner() is b
    assert match.player1_games_won_per_set == [0] * sets_to_win
    assert match.player2_games_won_per_set == [6] * sets_to_win
    assert match.player1_first_serves_played == match.player1_double_faults == 12 * sets_to_win
    assert match.player1_first_serves_in == match.player1_second_serves_in == 0
    assert match.player1_second_serves_played == 12 * sets_to_win
    assert match.player2_first_serves_played == match.player2_first_serves_won == 12 * sets_to_win
    assert match.player2_second_serves_played == match.player2_double_faults == 0
    assert match.player2_total_points_won == 24 * sets_to_win
    assert match.player2_return_points_won == match.player2_service_points_won == 12 * sets_to_win
    assert match.player2_break_points_converted == match.player2_break_point_chances == 3 * sets_to_win
    match.print_match_statistics()
    assert "N/A" in capsys.readouterr().out


@pytest.mark.parametrize("seed", [3, 42, 90])
def test_detailed_statistics_conserve_points_and_games(seed):
    match = TennisMatch(Player("A", 0.64, 0.93, 0.73, 0.52),
                        Player("B", 0.58, 0.89, 0.71, 0.51), sets_to_win=3, seed=seed)
    match.simulate_match(verbose=False)
    total_points = match.player1_total_points_won + match.player2_total_points_won
    assert match.player1_first_serves_played + match.player2_first_serves_played == total_points
    regular_games = sum(match.player1_games_won_per_set + match.player2_games_won_per_set) - match.total_tiebreaks_played
    assert match.player1_service_games_played + match.player2_service_games_played == regular_games
    assert match.total_tiebreaks_played == match.player1_tiebreaks_won + match.player2_tiebreaks_won
    for number in (1, 2):
        stat = lambda name: getattr(match, f"player{number}_{name}")
        assert stat("total_points_won") == stat("service_points_won") + stat("return_points_won")
        assert stat("second_serves_played") == stat("first_serves_played") - stat("first_serves_in")
        assert stat("double_faults") == stat("second_serves_played") - stat("second_serves_in")
        assert stat("service_points_won") == stat("first_serves_won") + stat("second_serves_won")
        assert stat("break_points_converted") <= stat("break_point_chances")
