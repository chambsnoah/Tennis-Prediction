import random

def points_in_game_to_score(points_player_1, points_player_2):
    # Convert points to score, not the best way to do it but it works
    if points_player_1 == 0 and points_player_2 == 0:
        return "0-0"
    elif points_player_1 == 1 and points_player_2 == 0:
        return "15-0"
    elif points_player_1 == 2 and points_player_2 == 0:
        return "30-0"
    elif points_player_1 == 3 and points_player_2 == 0:
        return "40-0"
    elif points_player_1 == 0 and points_player_2 == 1:
        return "0-15"
    elif points_player_1 == 0 and points_player_2 == 2:
        return "0-30"
    elif points_player_1 == 0 and points_player_2 == 3:
        return "0-40"
    elif points_player_1 == 1 and points_player_2 == 1:
        return "15-15"
    elif points_player_1 == 2 and points_player_2 == 1:
        return "30-15"
    elif points_player_1 == 3 and points_player_2 == 1:
        return "40-15"
    elif points_player_1 == 1 and points_player_2 == 2:
        return "15-30"
    elif points_player_1 == 1 and points_player_2 == 3:
        return "15-40"
    elif points_player_1 == 2 and points_player_2 == 2:
        return "30-30"
    elif points_player_1 == 3 and points_player_2 == 2:
        return "40-30"
    elif points_player_1 == 2 and points_player_2 == 3:
        return "30-40"
    elif points_player_1 == points_player_2:
        return "40-40"
    elif points_player_1 > points_player_2:
        return "AD-40"
    elif points_player_1 < points_player_2:
        return "40-AD"
    else:
        return "Error"

def print_scoreline(player1_games_won_per_set, player2_games_won_per_set, player1_points_won_in_tiebreak_per_set, player2_points_won_in_tiebreak_per_set,
                           player1_number_of_points_won_in_current_game, player2_number_of_points_won_in_current_game, in_game):
    num_sets = len(player1_games_won_per_set)
    for i in range(num_sets):
        print(player1_games_won_per_set[i], "-", player2_games_won_per_set[i], end=" ")

        if player1_games_won_per_set[i] >= 6 and player2_games_won_per_set[i] >= 6:
            print("(", player1_points_won_in_tiebreak_per_set[i], "-", player2_points_won_in_tiebreak_per_set[i], ")", end=" ")
        else:
            if in_game and i == num_sets - 1:
                print(points_in_game_to_score(player1_number_of_points_won_in_current_game, player2_number_of_points_won_in_current_game), end=" ")

        if i < num_sets - 1:
            print(",", end=" ")
        else:
            print()

def simulate_point(player1_to_serve, player1_points_won_on_serve, player2_points_won_on_serve):
    # Simulate a point
    if player1_to_serve:
        if random.random() <= player1_points_won_on_serve:
            return 1
        else:
            return 2
    else:
        if random.random() <= player2_points_won_on_serve:
            return 2
        else:
            return 1


def simulate_tennis_game(player1_points_won_on_serve, player2_points_won_on_serve, sets_to_win, player1_to_serve):
    # Number of sets won by each player
    player1_sets_won = 0
    player2_sets_won = 0

    # List where each index represents a set, and the value represents the number of games won by the player during that set
    player1_games_won_per_set = []
    player2_games_won_per_set = []

    # List only used if there is a tiebreak during a set, same structure as above
    player1_points_won_in_tiebreak_per_set = []
    player2_points_won_in_tiebreak_per_set = []

    # Total points won by each player
    player1_totaL_points_won = 0
    player2_total_points_won = 0

    while True:
        if player1_sets_won == sets_to_win or player2_sets_won == sets_to_win:
            break

        # Simulate a set
        player1_games_won = 0
        player2_games_won = 0

        # Add a new index to the list for the set
        player1_games_won_per_set.append(0)
        player2_games_won_per_set.append(0)

        while True:
            # Simulate a game
            if (player1_games_won >= 6 or player2_games_won >= 6) and abs(player1_games_won - player2_games_won) >= 2:
                break

            if player1_games_won == 6 and player2_games_won == 6:
                # Simulate a tiebreak
                player1_points_won_in_tiebreak = 0
                player2_points_won_in_tiebreak = 0

                # Add a new index to the list for the tiebreak
                player1_points_won_in_tiebreak_per_set.append(0)
                player2_points_won_in_tiebreak_per_set.append(0)

                while True:
                    if (player1_points_won_in_tiebreak >= 7 or player2_points_won_in_tiebreak >= 7) and abs(player1_points_won_in_tiebreak - player2_points_won_in_tiebreak) >= 2:
                        break

                    if simulate_point(player1_to_serve, player1_points_won_on_serve, player2_points_won_on_serve) == 1:
                        player1_points_won_in_tiebreak += 1
                        player1_points_won_in_tiebreak_per_set[-1] += 1
                        player1_totaL_points_won += 1
                    else:
                        player2_points_won_in_tiebreak += 1
                        player2_points_won_in_tiebreak_per_set[-1] += 1
                        player2_total_points_won += 1
                    
                    # Not technically in a game as it is a tiebreak, so the final argument is False
                    print_scoreline(player1_games_won_per_set, player2_games_won_per_set, player1_points_won_in_tiebreak_per_set, player2_points_won_in_tiebreak_per_set,
                                    player1_points_won_in_tiebreak, player2_points_won_in_tiebreak, False)

                if player1_points_won_in_tiebreak > player2_points_won_in_tiebreak:
                    player1_games_won += 1
                    player1_games_won_per_set[-1] += 1
                else:
                    player2_games_won += 1
                    player2_games_won_per_set[-1] += 1

                # Switch server
                player1_to_serve = not player1_to_serve

                break

            # Otherwise, simulate a regular game
            player1_points_won = 0
            player2_points_won = 0

            while True:
                # Regular game
                if (player1_points_won >= 4 or player2_points_won >= 4) and abs(player1_points_won - player2_points_won) >= 2:
                    break

                if simulate_point(player1_to_serve, player1_points_won_on_serve, player2_points_won_on_serve) == 1:
                    player1_points_won += 1
                    player1_totaL_points_won += 1
                else:
                    player2_points_won += 1
                    player2_total_points_won += 1

                # In a game, so the final argument is True
                print_scoreline(player1_games_won_per_set, player2_games_won_per_set, player1_points_won_in_tiebreak_per_set, player2_points_won_in_tiebreak_per_set,
                                player1_points_won, player2_points_won, True)
                
            if player1_points_won > player2_points_won:
                player1_games_won += 1
                player1_games_won_per_set[-1] += 1
            else:
                player2_games_won += 1
                player2_games_won_per_set[-1] += 1

            # Switch server
            player1_to_serve = not player1_to_serve

        if player1_games_won > player2_games_won:
            player1_sets_won += 1
        else:
            player2_sets_won += 1

        print_scoreline(player1_games_won_per_set, player2_games_won_per_set, player1_points_won_in_tiebreak_per_set, player2_points_won_in_tiebreak_per_set,
                        -1, -1, False)

# Example usage
simulate_tennis_game(0.5, 0.5, 3, True)
