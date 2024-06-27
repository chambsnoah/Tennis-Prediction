import json
import random

from tennis import PlayerSimple, TennisMatch

config = "f"

### -------- Values that can be changed ---------- ###
savefile = True
watchplayer = ""
outline_player_matches = ""
num_runs = 1
verbose = True

seed = 20240114
top_player_boost = 0.02
match_replays = True # replays the match 5,3 times depending bracket size to get less variance but still give a chance for upsets

# from online sources
average_percentage_won_on_serve = 0.64

### ---------------------------------------------- ###

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

# values of bracket_size are 64,32,16,8,4,2
def get_num_match_replay_per_bracket_size(bracket_size):
    # 5 top margin
    if not match_replays:
        return 1
    if bracket_size > 4:
        return 5
    return bracket_size + 1

if seed != None:
    random.seed(seed)

if num_runs > 1:
    verbose = False

brackets = []

for i in range(num_runs):

    players = load_players
    bracket = load_bracket
    if num_runs == 1:
        brackets.append(bracket)

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
                        averaged_player_1_seeding = stats1["seed"] #"(stats1[seed"] + stats1["power"]) / 2
                        averaged_player_2_seeding = stats2["seed"] #(stats2["seed"] + stats2["power"]) / 2
                        if player1 == outline_player_matches or player2 == outline_player_matches:
                            print(f"{player1} : {averaged_player_1_seeding} vs {player2} : {averaged_player_2_seeding}")
                        better_seed = player1 if averaged_player_1_seeding < averaged_player_2_seeding else player2
                        worse_seed = player2 if averaged_player_1_seeding < averaged_player_2_seeding else player1
                        diff = abs(averaged_player_1_seeding  - averaged_player_2_seeding)
                        if diff >= 100:
                            diff = 100
                        
                        # These are arbitrary numbers, but they're based on the fact that the higher seed should have a higher chance of winning
                        # also adding some variance
                        percentage_diff = diff / 100 * 0.08

                        num_match_replays = get_num_match_replay_per_bracket_size(len(bracket))
                        player1_total_matches_won = 0
                        player2_total_matches_won = 0

                        for _ in range(num_match_replays):
                            worse_seed_points_won_on_serve = average_percentage_won_on_serve - percentage_diff / 2 + random.uniform(-0.03, 0.03)
                            better_seed_points_won_on_serve = average_percentage_won_on_serve + percentage_diff / 2 + random.uniform(-0.03, 0.03)
                            player1_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player1 else better_seed_points_won_on_serve
                            player2_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player2 else better_seed_points_won_on_serve
                            if (player1 == "C. Alcaraz" and player2 != "N. Djokovic") \
                                or (player1 == "N. Djokovic" and player2 != "C. Alcaraz"):
                                player1_points_won_on_serve += top_player_boost
                                player2_points_won_on_serve -= top_player_boost
                            elif (player2 == "C. Alcaraz" and player1 != "N. Djokovic") \
                                or (player2 == "N. Djokovic" and player1 != "C. Alcaraz"):
                                player2_points_won_on_serve += top_player_boost
                                player1_points_won_on_serve -= top_player_boost
                            elif (player1 == "C. Alcaraz" and player2 == "N. Djokovic") \
                                or (player1 == "N. Djokovic" and player2 == "C. Alcaraz"):
                                player1_points_won_on_serve = average_percentage_won_on_serve
                                player2_points_won_on_serve = average_percentage_won_on_serve

                            player1_points_won_on_serve = round(player1_points_won_on_serve, 4)
                            player2_points_won_on_serve = round(player2_points_won_on_serve, 4)
                            player_simple_1 = PlayerSimple(player1, player1_points_won_on_serve)
                            player_simple_2 = PlayerSimple(player2, player2_points_won_on_serve)
                            if player1 == outline_player_matches or player2 == outline_player_matches:
                                print(f"{player1} : {player1_points_won_on_serve*100}% vs {player2} : {player2_points_won_on_serve*100}%")
                        
                            player1_to_start = random.choice([True, False])
                            match = TennisMatch(player_simple_1, player_simple_2, sets_to_win, player1_to_start, None)
                            if (player1 == outline_player_matches or player2 == outline_player_matches) \
                                and num_match_replays == 1:
                                match.simulate_match(verbose=True)
                            else:
                                match.simulate_match(verbose=False)

                            winner1 = match.get_match_winner().name
                            loser1 = player2 if winner1 == player1 else player1

                            player1_points_won = match.get_player1_points_won()
                            player2_points_won = match.get_player2_points_won()
                            winner1_points = player1_points_won if winner1 == player1 else player2_points_won
                            loser1_points = player2_points_won if winner1 == player1 else player1_points_won

                            player1_total_matches_won += 1 if winner1 == player1 else 0
                            player2_total_matches_won += 1 if winner1 == player2 else 0
                        
                        winner1 = player1 if player1_total_matches_won > player2_total_matches_won else player2
                        loser1 = player2 if player1_total_matches_won > player2_total_matches_won else player1
                        if (player1 == outline_player_matches or player2 == outline_player_matches) and verbose:
                            print(f"Player 1: {player1} | Player 2: {player2} | {player1_total_matches_won} - {player2_total_matches_won}")
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
                        averaged_player_1_seeding = stats1["seed"] #(stats1["seed"] + stats1["power"]) / 2
                        averaged_player_2_seeding = stats2["seed"] #(stats2["seed"] + stats2["power"]) / 2
                        if player1 == outline_player_matches or player2 == outline_player_matches:
                            print(f"{player1} : {averaged_player_1_seeding} vs {player2} : {averaged_player_2_seeding}")
                        better_seed = player1 if averaged_player_1_seeding < averaged_player_2_seeding else player2
                        worse_seed = player2 if averaged_player_1_seeding < averaged_player_2_seeding else player1
                        diff = abs(averaged_player_1_seeding  - averaged_player_2_seeding)
                        if diff >= 100:
                            diff = 100
                        
                        # These are arbitrary numbers, but they're based on the fact that the higher seed should have a higher chance of winning
                        # also adding some variance
                        percentage_diff = diff / 100 * 0.08

                        num_match_replays = get_num_match_replay_per_bracket_size(len(bracket))
                        player1_total_matches_won = 0
                        player2_total_matches_won = 0

                        for _ in range(num_match_replays):
                            worse_seed_points_won_on_serve = average_percentage_won_on_serve - percentage_diff / 2 + random.uniform(-0.03, 0.03)
                            better_seed_points_won_on_serve = average_percentage_won_on_serve + percentage_diff / 2 + random.uniform(-0.03, 0.03)
                            player1_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player1 else better_seed_points_won_on_serve
                            player2_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player2 else better_seed_points_won_on_serve
                            if (player1 == "C. Alcaraz" and player2 != "N. Djokovic") \
                                or (player1 == "N. Djokovic" and player2 != "C. Alcaraz"):
                                player1_points_won_on_serve += top_player_boost
                                player2_points_won_on_serve -= top_player_boost
                            elif (player2 == "C. Alcaraz" and player1 != "N. Djokovic") \
                                or (player2 == "N. Djokovic" and player1 != "C. Alcaraz"):
                                player2_points_won_on_serve += top_player_boost
                                player1_points_won_on_serve -= top_player_boost
                            elif (player1 == "C. Alcaraz" and player2 == "N. Djokovic") \
                                or (player1 == "N. Djokovic" and player2 == "C. Alcaraz"):
                                player1_points_won_on_serve = average_percentage_won_on_serve
                                player2_points_won_on_serve = average_percentage_won_on_serve

                            player1_points_won_on_serve = round(player1_points_won_on_serve, 4)
                            player2_points_won_on_serve = round(player2_points_won_on_serve, 4)
                            player_simple_1 = PlayerSimple(player1, player1_points_won_on_serve)
                            player_simple_2 = PlayerSimple(player2, player2_points_won_on_serve)
                            if player1 == outline_player_matches or player2 == outline_player_matches:
                                print(f"{player1} : {player1_points_won_on_serve*100}% vs {player2} : {player2_points_won_on_serve*100}%")

                            player1_to_start = random.choice([True, False])

                            match = TennisMatch(player_simple_1, player_simple_2, sets_to_win, player1_to_start, None)
                            if (player1 == outline_player_matches or player2 == outline_player_matches) \
                                and num_match_replays == 1:
                                match.simulate_match(verbose=True)
                            else:
                                match.simulate_match(verbose=False)

                            winner2 = match.get_match_winner().name
                            loser2 = player2 if winner2 == player1 else player1

                            player1_points_won = match.get_player1_points_won()
                            player2_points_won = match.get_player2_points_won()
                            winner2_points = player1_points_won if winner2 == player1 else player2_points_won
                            loser2_points = player2_points_won if winner2 == player1 else player1_points_won

                            player1_total_matches_won += 1 if winner2 == player1 else 0
                            player2_total_matches_won += 1 if winner2 == player2 else 0

                        winner2 = player1 if player1_total_matches_won > player2_total_matches_won else player2
                        loser2 = player2 if player1_total_matches_won > player2_total_matches_won else player1
                        if (player1 == outline_player_matches or player2 == outline_player_matches) and verbose:
                            print(f"Player 1: {player1} | Player 2: {player2} | {player1_total_matches_won} - {player2_total_matches_won}\n")
                elif stats1:
                    winner2 = player1
                    loser2 = player2
                elif stats2:
                    winner2 = player2
                    loser2 = player1
                next_bracket.append([winner1, winner2])

                if winner1 in player_points:
                    player_points[winner1] += winner1_points
                if winner2 in player_points:
                    player_points[winner2] += winner2_points
                if loser1 in player_points:
                    player_points[loser1] += loser1_points
                if loser2 in player_points:
                    player_points[loser2] += loser2_points
        bracket = next_bracket
        if num_runs == 1:
            brackets.append(bracket)
        if len(bracket) == 1:
            if verbose:
                print(bracket)
            player1 = bracket[0][0]
            player2 = bracket[0][1]
            stats1, stats2 = None, None
            winner, loser = None, None
            winner_points, loser_points = 55, 45
            if player1 in players:
                stats1 = players[player1]
            if player2 in players:
                stats2 = players[player2]
            if player1 == watchplayer:
                winner = player1
                loser = player2
            elif player2 == watchplayer:
                winner = player2
                loser = player1
            else:
                # This is the logic where the match is simulated
                # given that an 8% diff makes an almost 85-90% chance of winning, that will be our top margin
                # we'll only do that when the seeds are 100 apart or more
                # then we'll gradually descend to 0% diff as the seeds get closer
                averaged_player_1_seeding = stats1["seed"] #(stats1["seed"] + stats1["power"]) / 2
                averaged_player_2_seeding = stats2["seed"] #(stats2["seed"] + stats2["power"]) / 2
                if player1 == outline_player_matches or player2 == outline_player_matches:
                    print(f"{player1} : {averaged_player_1_seeding} vs {player2} : {averaged_player_2_seeding}")
                better_seed = player1 if averaged_player_1_seeding < averaged_player_2_seeding else player2
                worse_seed = player2 if averaged_player_1_seeding < averaged_player_2_seeding else player1
                diff = abs(averaged_player_1_seeding  - averaged_player_2_seeding)
                if diff >= 100:
                    diff = 100
                
                # These are arbitrary numbers, but they're based on the fact that the higher seed should have a higher chance of winning
                # also adding some variance
                percentage_diff = diff / 100 * 0.08
                worse_seed_points_won_on_serve = average_percentage_won_on_serve - percentage_diff / 2 + random.uniform(-0.03, 0.03)
                better_seed_points_won_on_serve = average_percentage_won_on_serve + percentage_diff / 2 + random.uniform(-0.03, 0.03)
                player1_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player1 else better_seed_points_won_on_serve
                player2_points_won_on_serve = worse_seed_points_won_on_serve if worse_seed == player2 else better_seed_points_won_on_serve
                
                if (player1 == "C. Alcaraz" and player2 != "N. Djokovic") \
                    or (player1 == "N. Djokovic" and player2 != "C. Alcaraz"):
                    player1_points_won_on_serve += top_player_boost
                    player2_points_won_on_serve -= top_player_boost
                elif (player2 == "C. Alcaraz" and player1 != "N. Djokovic") \
                    or (player2 == "N. Djokovic" and player1 != "C. Alcaraz"):
                    player2_points_won_on_serve += top_player_boost
                    player1_points_won_on_serve -= top_player_boost
                elif (player1 == "C. Alcaraz" and player2 == "N. Djokovic") \
                    or (player1 == "N. Djokovic" and player2 == "C. Alcaraz"):
                    player1_points_won_on_serve = average_percentage_won_on_serve
                    player2_points_won_on_serve = average_percentage_won_on_serve

                player1_points_won_on_serve = round(player1_points_won_on_serve, 4)
                player2_points_won_on_serve = round(player2_points_won_on_serve, 4)
                player_simple_1 = PlayerSimple(player1, player1_points_won_on_serve)
                player_simple_2 = PlayerSimple(player2, player2_points_won_on_serve)
                if player1 == outline_player_matches or player2 == outline_player_matches:
                    print(f"{player1} : {player1_points_won_on_serve*100}% vs {player2} : {player2_points_won_on_serve*100}%")

                player1_to_start = random.choice([True, False])

                match = TennisMatch(player_simple_1, player_simple_2, sets_to_win, player1_to_start, None)
                if verbose:
                    match.simulate_match(verbose=True)
                    match.print_match_statistics()
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
            if num_runs == 1:
                brackets.append(bracket)
            break
            
    if verbose:
        print(bracket)
        print(player_points)
    
    for player in player_points:
        player_points_total[player] += player_points[player]

for player in player_points_total:
    player_points_total[player] = round(player_points_total[player] / num_runs, 2)

if num_runs >= 1:
    print(player_points_total)

if savefile:
    if config == "m" or config == "M":
        with open("player_points_male.json", "w") as f:
            json.dump(player_points_total, f, indent=4)
        if num_runs == 1:
            with open("bracket_filled_male.json", "w") as f:
                json.dump(brackets, f, indent=4)
    elif config == "f" or config == "F":
        with open("player_points_female.json", "w") as f:
            json.dump(player_points_total, f, indent=4)
        if num_runs == 1:
            with open("bracket_filled_female.json", "w") as f:
                json.dump(brackets, f, indent=4)