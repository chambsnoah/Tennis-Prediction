import json
import random

from tennis import PlayerSimple, TennisMatch

config = "m"

players = None
bracket = None
sets_to_win = 3


if config == "m" or config == "M":
    load_players = json.load(open("players_male.json", "r"))
    load_bracket = json.load(open("bracket_male.json", "r"))
    sets_to_win = 3
elif config == "f" or config == "F":
    load_players = json.load(open("players_female.json", "r"))
    load_bracket = json.load(open("bracket_female.json", "r"))
    sets_to_win = 2

player_points_total = {}
for player in load_players:
    player_points_total[player] = 0

savefile = False
watchplayer = ""
outline_player_matches = ""
num_runs = 1
verbose = True
seed = None

if seed != None:
    random.seed(seed)

for i in range(num_runs):

    players = load_players
    bracket = load_bracket

    # TODO: make sure the player names are the same in the bracket and in the players file
    player_points = {}
    for player in players:
        player_points[player] = 0

    while True:
        if verbose:
            print(bracket)
        next_bracket = []
        for i in range(len(bracket)):
            if i % 2 == 0:
                stats1, stats2 = None, None
                winner1, winner2, loser1, loser2 = None, None, None, None
                winner1_points, winner2_points, loser1_points, loser2_points = 55, 55, 45, 45
                player1 = bracket[i][0]
                player2 = bracket[i][1]
                if player1 == watchplayer or player2 == watchplayer:
                    if verbose:
                        print()
                        print(player1 + ", " + player2)
                        print()
                if player1 in players:
                    stats1 = players[player1]
                if player2 in players:
                    stats2 = players[player2]
                if stats1 and stats2:
                    if player1 == watchplayer:
                        winner1 = player1
                        loser1 = player2
                    elif player2 == watchplayer:
                        winner1 = player2
                        loser1 = player1
                    else:
                        # This is the logic where the match is simulated
                        # given that an 8% diff makes an almost 85-90% chance of winning, that will be our top margin
                        # we'll only do that when the seeds are 100 apart or more
                        # then we'll gradually descend to 0% diff as the seeds get closer
                        better_seed = player1 if stats1["seed"] < stats2["seed"] else player2
                        worse_seed = player2 if stats1["seed"] < stats2["seed"] else player1
                        diff = abs(stats1["seed"]  - stats2["seed"])
                        if diff >= 100:
                            diff = 100
                        
                        # These are arbitrary numbers, but they're based on the fact that the higher seed should have a higher chance of winning
                        worse_seed_points_won_on_serve = 0.5
                        better_seed_points_won_on_serve = 0.5 + round(diff / 100 * 0.08, 3)
                        player1_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player1 else better_seed_points_won_on_serve
                        player2_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player2 else better_seed_points_won_on_serve

                        player_simple_1 = PlayerSimple(player1, player1_points_won_on_serve)
                        player_simple_2 = PlayerSimple(player2, player2_points_won_on_serve)
                        if player1 == outline_player_matches or player2 == outline_player_matches:
                            print(f"{player1} : {player1_points_won_on_serve*100}% vs {player2} : {player2_points_won_on_serve*100}%")

                        player1_to_start = random.choice([True, False])

                        match = TennisMatch(player_simple_1, player_simple_2, sets_to_win, player1_to_start, seed)
                        if player1 == outline_player_matches or player2 == outline_player_matches:
                            match.simulate_match(verbose=True)
                        else:
                            match.simulate_match(verbose=False)

                        winner1 = match.get_match_winner().name
                        loser1 = player2 if winner1 == player1 else player1

                        player1_points_won = match.get_player1_points_won()
                        player2_points_won = match.get_player2_points_won()
                        winner1_points = player1_points_won if winner1 == player1 else player2_points_won
                        loser1_points = player2_points_won if winner1 == player1 else player1_points_won
                elif stats1:
                    winner1 = player1
                    loser1 = player2
                elif stats2:
                    winner1 = player2
                    loser1 = player1

                player1 = bracket[i + 1][0]
                player2 = bracket[i + 1][1]
                if player1 == watchplayer or player2 == watchplayer:
                    if verbose:
                        print()
                        print(player1 + ", " + player2)
                        print()
                stats1, stats2 = None, None
                if player1 in players:
                    stats1 = players[player1]
                if player2 in players:
                    stats2 = players[player2]
                if stats1 and stats2:
                    if player1 == watchplayer:
                        winner2 = player1
                        loser2 = player2
                    elif player2 == watchplayer:
                        winner2 = player2
                        loser2 = player1
                    else:
                        # This is the logic where the match is simulated
                        # given that an 8% diff makes an almost 85-90% chance of winning, that will be our top margin
                        # we'll only do that when the seeds are 100 apart or more
                        # then we'll gradually descend to 0% diff as the seeds get closer
                        better_seed = player1 if stats1["seed"] < stats2["seed"] else player2
                        worse_seed = player2 if stats1["seed"] < stats2["seed"] else player1
                        diff = abs(stats1["seed"]  - stats2["seed"])
                        if diff >= 100:
                            diff = 100
                        
                        # These are arbitrary numbers, but they're based on the fact that the higher seed should have a higher chance of winning
                        worse_seed_points_won_on_serve = 0.5
                        better_seed_points_won_on_serve = 0.5 + round(diff / 100 * 0.08, 3)
                        player1_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player1 else better_seed_points_won_on_serve
                        player2_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player2 else better_seed_points_won_on_serve

                        player_simple_1 = PlayerSimple(player1, player1_points_won_on_serve)
                        player_simple_2 = PlayerSimple(player2, player2_points_won_on_serve)
                        if player1 == outline_player_matches or player2 == outline_player_matches:
                            print(f"{player1} : {player1_points_won_on_serve*100}% vs {player2} : {player2_points_won_on_serve*100}%")

                        player1_to_start = random.choice([True, False])

                        match = TennisMatch(player_simple_1, player_simple_2, sets_to_win, player1_to_start, seed)
                        if player1 == outline_player_matches or player2 == outline_player_matches:
                            match.simulate_match(verbose=True)
                        else:
                            match.simulate_match(verbose=False)

                        winner2 = match.get_match_winner().name
                        loser2 = player2 if winner2 == player1 else player1

                        player1_points_won = match.get_player1_points_won()
                        player2_points_won = match.get_player2_points_won()
                        winner2_points = player1_points_won if winner2 == player1 else player2_points_won
                        loser2_points = player2_points_won if winner2 == player1 else player1_points_won
                elif stats1:
                    winner2 = player1
                    loser2 = player2
                elif stats2:
                    winner2 = player2
                    loser2 = player1
                next_bracket.append([winner1, winner2])
                if player1 == outline_player_matches or player2 == outline_player_matches:
                    print(f"{winner1} : {winner1_points} vs {winner2} : {winner2_points}")
                    print(f"{loser1} : {loser1_points} vs {loser2} : {loser2_points}")

                if winner1 in player_points:
                    player_points[winner1] += winner1_points
                if winner2 in player_points:
                    player_points[winner2] += winner2_points
                if loser1 in player_points:
                    player_points[loser1] += loser1_points
                if loser2 in player_points:
                    player_points[loser2] += loser2_points
        bracket = next_bracket
        if len(bracket) == 1:
            if verbose:
                print(bracket)
            player1 = bracket[0][0]
            player2 = bracket[0][1]
            stats1, stats2 = None, None
            winner_points, loser_points = 55, 45
            if player1 in players:
                stats1 = players[player1]
            if player2 in players:
                stats2 = players[player2]
            if player1 == watchplayer:
                winner = player1
            elif player2 == watchplayer:
                winner = player2
            else:
                # This is the logic where the match is simulated
                # given that an 8% diff makes an almost 85-90% chance of winning, that will be our top margin
                # we'll only do that when the seeds are 100 apart or more
                # then we'll gradually descend to 0% diff as the seeds get closer
                better_seed = player1 if stats1["seed"] < stats2["seed"] else player2
                worse_seed = player2 if stats1["seed"] < stats2["seed"] else player1
                diff = abs(stats1["seed"]  - stats2["seed"])
                if diff >= 100:
                    diff = 100
                
                # These are arbitrary numbers, but they're based on the fact that the higher seed should have a higher chance of winning
                worse_seed_points_won_on_serve = 0.5
                better_seed_points_won_on_serve = 0.5 + round(diff / 100 * 0.08, 3)
                player1_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player1 else better_seed_points_won_on_serve
                player2_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player2 else better_seed_points_won_on_serve

                player_simple_1 = PlayerSimple(player1, player1_points_won_on_serve)
                player_simple_2 = PlayerSimple(player2, player2_points_won_on_serve)
                if player1 == outline_player_matches or player2 == outline_player_matches:
                    print(f"{player1} : {player1_points_won_on_serve*100}% vs {player2} : {player2_points_won_on_serve*100}%")

                player1_to_start = random.choice([True, False])

                match = TennisMatch(player_simple_1, player_simple_2, sets_to_win, player1_to_start, seed)
                if player1 == outline_player_matches or player2 == outline_player_matches:
                    match.simulate_match(verbose=True)
                else:
                    match.simulate_match(verbose=False)

                winner = match.get_match_winner().name
                loser = player2 if winner1 == player1 else player1

                player1_points_won = match.get_player1_points_won()
                player2_points_won = match.get_player2_points_won()
                winner_points = player1_points_won if winner == player1 else player2_points_won
                loser_points = player2_points_won if winner == player1 else player1_points_won
            player_points[winner] += winner_points
            player_points[loser] += loser_points
            bracket = [winner]
            break

    if verbose:
        print(bracket)
        print(player_points)

    if savefile:
        if config == "m" or config == "M":
            with open("player_points_male.json", "w") as f:
                json.dump(player_points, f, indent=4)
        elif config == "f" or config == "F":
            with open("player_points_female.json", "w") as f:
                json.dump(player_points, f, indent=4)
    
    for player in player_points:
        player_points_total[player] += player_points[player]

for player in player_points_total:
    player_points_total[player] = round(player_points_total[player] / num_runs, 2)

if num_runs > 1:
    print(player_points_total)