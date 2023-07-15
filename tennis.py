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
                           player1_number_of_points_won_in_current_game, player2_number_of_points_won_in_current_game, in_game, player1_to_serve):
    num_sets = len(player1_games_won_per_set)
    for i in range(num_sets):
        print(f"{player1_games_won_per_set[i]}-{player2_games_won_per_set[i]}", end="")

        if player1_games_won_per_set[i] >= 6 and player2_games_won_per_set[i] >= 6:
            if in_game and i == num_sets - 1:
                print(f" ({player1_points_won_in_tiebreak_per_set[i]}-{player2_points_won_in_tiebreak_per_set[i]})   | Player {1 if player1_to_serve == True else 2} to serve", end="")
            else:
                print(f" ({player1_points_won_in_tiebreak_per_set[i]}-{player2_points_won_in_tiebreak_per_set[i]})", end="")
        else:
            if in_game and i == num_sets - 1:
                score = points_in_game_to_score(player1_number_of_points_won_in_current_game, player2_number_of_points_won_in_current_game)
                score_length = len(score)
                spacing = 2
                if score_length == 4:
                    spacing = 1
                elif score_length == 5:
                    spacing = 0
                spaces = " " * spacing
                print(f" {score} {spaces} | Player {1 if player1_to_serve == True else 2} to serve", end=" ")

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

    # Total number of service games won by each player
    player1_service_games_won = 0
    player2_service_games_won = 0

    # Total number of service games played by each player
    player1_service_games_played = 0
    player2_service_games_played = 0

    # Total number of tiebreaks played
    total_tiebreaks_played = 0

    # Total number of tiebreaks won by each player
    player1_tiebreaks_won = 0
    player2_tiebreaks_won = 0

    while True: # Simulate a set
        if player1_sets_won == sets_to_win or player2_sets_won == sets_to_win:
            break
        player1_games_won = 0
        player2_games_won = 0

        # Add a new index to the list for the set
        player1_games_won_per_set.append(0)
        player2_games_won_per_set.append(0)

        # Add a new index to the list for the tiebreak
        player1_points_won_in_tiebreak_per_set.append(0)
        player2_points_won_in_tiebreak_per_set.append(0)

        while True: # Simulate a game
            if (player1_games_won >= 6 or player2_games_won >= 6) and abs(player1_games_won - player2_games_won) >= 2:
                break

            print_scoreline(player1_games_won_per_set, player2_games_won_per_set, 
                player1_points_won_in_tiebreak_per_set, player2_points_won_in_tiebreak_per_set,
                0, 0, True, player1_to_serve)

            if player1_games_won == 6 and player2_games_won == 6:
                # Simulate a tiebreak
                player1_points_won_in_tiebreak = 0
                player2_points_won_in_tiebreak = 0

                # Player who receives first in the tiebreak is the player who will serve first in the next set
                server_that_should_start_next_set = not player1_to_serve

                points_needed_to_win_tiebreak = 7 if len(player1_games_won_per_set) < (sets_to_win) * 2 - 1 else 10

                while True:
                    if simulate_point(player1_to_serve, player1_points_won_on_serve, player2_points_won_on_serve) == 1:
                        player1_points_won_in_tiebreak += 1
                        player1_points_won_in_tiebreak_per_set[-1] += 1
                        player1_totaL_points_won += 1
                    else:
                        player2_points_won_in_tiebreak += 1
                        player2_points_won_in_tiebreak_per_set[-1] += 1
                        player2_total_points_won += 1

                    if (player1_points_won_in_tiebreak >= points_needed_to_win_tiebreak or player2_points_won_in_tiebreak >= points_needed_to_win_tiebreak) and \
                         abs(player1_points_won_in_tiebreak - player2_points_won_in_tiebreak) >= 2:
                        player1_to_serve = server_that_should_start_next_set
                        break

                    # Switch server after every 2 points
                    if (player1_points_won_in_tiebreak + player2_points_won_in_tiebreak) % 2 == 1:
                        player1_to_serve = not player1_to_serve
                    
                    print_scoreline(player1_games_won_per_set, player2_games_won_per_set, 
                                    player1_points_won_in_tiebreak_per_set, player2_points_won_in_tiebreak_per_set,
                                    player1_points_won_in_tiebreak, player2_points_won_in_tiebreak, True, player1_to_serve)

                if player1_points_won_in_tiebreak > player2_points_won_in_tiebreak:
                    player1_games_won += 1
                    player1_games_won_per_set[-1] += 1
                    player1_tiebreaks_won += 1
                else:
                    player2_games_won += 1
                    player2_games_won_per_set[-1] += 1
                    player2_tiebreaks_won += 1

                total_tiebreaks_played += 1
                break

            # --- This lower part of the code is only reached if there is no tiebreak in the set ---

            # Otherwise, simulate a regular game
            player1_points_won = 0
            player2_points_won = 0

            while True:
                # Regular game
                if simulate_point(player1_to_serve, player1_points_won_on_serve, player2_points_won_on_serve) == 1:
                    player1_points_won += 1
                    player1_totaL_points_won += 1
                else:
                    player2_points_won += 1
                    player2_total_points_won += 1

                if (player1_points_won >= 4 or player2_points_won >= 4) and abs(player1_points_won - player2_points_won) >= 2:
                    break

                # In a game, so the final argument is True
                print_scoreline(player1_games_won_per_set, player2_games_won_per_set, 
                                player1_points_won_in_tiebreak_per_set, player2_points_won_in_tiebreak_per_set,
                                player1_points_won, player2_points_won, True, player1_to_serve)
                
            if player1_points_won > player2_points_won:
                player1_games_won += 1
                player1_games_won_per_set[-1] += 1
                player1_service_games_won += 1 if player1_to_serve else 0
            else:
                player2_games_won += 1
                player2_games_won_per_set[-1] += 1
                player2_service_games_won += 1 if not player1_to_serve else 0

            if player1_to_serve:
                player1_service_games_played += 1
            else:
                player2_service_games_played += 1

            # Switch server
            player1_to_serve = not player1_to_serve

            # End of game

        if player1_games_won > player2_games_won:
            player1_sets_won += 1
        else:
            player2_sets_won += 1

        print_scoreline(player1_games_won_per_set, player2_games_won_per_set, 
                        player1_points_won_in_tiebreak_per_set, player2_points_won_in_tiebreak_per_set,
                        -1, -1, False, player1_to_serve)
        # End of set
        
    # End of match

    # Print match statistics
    winner = 1 if player1_sets_won > player2_sets_won else 2
    print(f"Match winner: {'Player 1!' if winner == 1 else 'Player 2!'}")

    print(f"Player 1 total points won: {player1_totaL_points_won}")
    print(f"Player 2 total points won: {player2_total_points_won}")
    winning_percentage = round(player1_totaL_points_won / (player1_totaL_points_won + player2_total_points_won) * 100, 2)
    if winner == 2:
        winning_percentage = 100 - winning_percentage
    print(f"Point winning percentage: {winning_percentage}%")

    print(f"Player 1 total games won: {sum(player1_games_won_per_set)}")
    print(f"Player 1 service games won: {player1_service_games_won} / {player1_service_games_played}")

    print(f"Player 2 total games won: {sum(player2_games_won_per_set)}")
    print(f"Player 2 service games won: {player2_service_games_won} / {player2_service_games_played}")

    if total_tiebreaks_played > 0:
        print(f"Player 1 tiebreaks won: {player1_tiebreaks_won}")
        print(f"Player 2 tiebreaks won: {player2_tiebreaks_won}")

# Example usage
simulate_tennis_game(0.9, 0.9, 3, True)
