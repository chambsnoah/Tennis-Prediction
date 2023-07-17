import datetime
import random

class Player:
    def __init__(self, name="John Doe", first_serve_percentage=0.5, second_serve_percentage=0.9, first_serve_win_percentage=0.5, second_serve_win_percentage=0.5):
        self.name = name
        self.first_serve_percentage = first_serve_percentage
        self.second_serve_percentage = second_serve_percentage
        self.first_serve_win_percentage = first_serve_win_percentage
        self.second_serve_win_percentage = second_serve_win_percentage

class TennisMatch:
    def __init__(self, player1, player2, sets_to_win=3, player1_to_serve=True, seed=None):
        self.player1 = player1
        self.player2 = player2

        # Number of sets won by each player
        self.player1_sets_won = 0
        self.player2_sets_won = 0

        # List where each index represents a set, and the value represents the number of games won by the player during that set
        self.player1_games_won_per_set = []
        self.player2_games_won_per_set = []

        # List only used if there is a tiebreak during a set, same structure as above
        self.player1_points_won_in_tiebreak_per_set = []
        self.player2_points_won_in_tiebreak_per_set = []

        # Total points won by each player
        self.player1_totaL_points_won = 0
        self.player2_total_points_won = 0

        # Total number of service games won by each player
        self.player1_service_games_won = 0
        self.player2_service_games_won = 0

        # Total number of service games played by each player
        self.player1_service_games_played = 0
        self.player2_service_games_played = 0

        # Total number of tiebreaks played
        self.total_tiebreaks_played = 0

        # Total number of tiebreaks won by each player
        self.player1_tiebreaks_won = 0
        self.player2_tiebreaks_won = 0

        # Serving stats
        self.player1_first_serves_played = 0
        self.player1_first_serves_in = 0
        self.player1_first_serves_won = 0
        self.player1_second_serves_played = 0
        self.player1_second_serves_in = 0
        self.player1_second_serves_won = 0
        self.player1_double_faults = 0

        self.player2_first_serves_played = 0
        self.player2_first_serves_in = 0
        self.player2_first_serves_won = 0
        self.player2_second_serves_played = 0
        self.player2_second_serves_in = 0
        self.player2_second_serves_won = 0
        self.player2_double_faults = 0

        # Game variables
        self.player1_to_serve = player1_to_serve
        self.sets_to_win = sets_to_win

        # Set random seed
        if seed != None:
            random.seed(seed)

    def points_in_game_to_score(self, points_player_1, points_player_2):
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

    def print_scoreline(self, in_game, player1_number_of_points_won_in_current_game, player2_number_of_points_won_in_current_game):
        num_sets = len(self.player1_games_won_per_set)
        for i in range(num_sets):
            print(f"{self.player1_games_won_per_set[i]}-{self.player2_games_won_per_set[i]}", end="")

            if self.player1_games_won_per_set[i] >= 6 and self.player2_games_won_per_set[i] >= 6:
                if in_game and i == num_sets - 1:
                    print(f" ({self.player1_points_won_in_tiebreak_per_set[i]}-{self.player2_points_won_in_tiebreak_per_set[i]})   | Player {1 if self.player1_to_serve == True else 2} to serve", end="")
                else:
                    print(f" ({self.player1_points_won_in_tiebreak_per_set[i]}-{self.player2_points_won_in_tiebreak_per_set[i]})", end="")
            else:
                if in_game and i == num_sets - 1:
                    score = self.points_in_game_to_score(player1_number_of_points_won_in_current_game, player2_number_of_points_won_in_current_game)
                    score_length = len(score)
                    spacing = 2
                    if score_length == 4:
                        spacing = 1
                    elif score_length == 5:
                        spacing = 0
                    spaces = " " * spacing
                    print(f" {score} {spaces} | {player1.name if self.player1_to_serve else player2.name} to serve", end=" ")

            if i < num_sets - 1:
                print(",", end=" ")
            else:
                print()

    def simulate_point(self, player1, player2):
        # Simulate a point
        if self.player1_to_serve:
            # 1st serve
            self.player1_first_serves_played += 1
            if random.random() <= player1.first_serve_percentage:
                # 1st serve in
                self.player1_first_serves_in += 1
                if random.random() <= player1.first_serve_win_percentage:
                    self.player1_first_serves_won += 1
                    print(f"{player1.name} makes 1st serve and wins point")
                    return 1
                else:
                    print(f"{player1.name} makes 1st serve but loses point")
                    return 2
            else:
                # 1st serve out
                self.player1_second_serves_played += 1
                print(f"{player1.name} misses 1st serve")
                if random.random() <= player1.second_serve_percentage:
                    # 2nd serve in
                    self.player1_second_serves_in += 1
                    if random.random() <= player1.second_serve_win_percentage:
                        self.player1_second_serves_won += 1
                        print(f"{player1.name} makes 2nd serve and wins point")
                        return 1
                    else:
                        print(f"{player1.name} makes 2nd serve but loses point")
                        return 2
                else:
                    # 2nd serve out
                    self.player1_double_faults += 1
                    print(f"{player1.name} double faults")
                    return 2
        else:
            # 1st serve
            self.player2_first_serves_played += 1
            if random.random() <= player2.first_serve_percentage:
                # 1st serve in
                self.player2_first_serves_in += 1
                if random.random() <= player2.first_serve_win_percentage:
                    self.player2_first_serves_won += 1
                    print(f"{player2.name} makes 1st serve and wins point")
                    return 2
                else:
                    print(f"{player2.name} makes 1st serve but loses point")
                    return 1
            else:
                # 1st serve out
                self.player2_second_serves_played += 1
                print(f"{player2.name} misses 1st serve")
                if random.random() <= player2.second_serve_percentage:
                    # 2nd serve in
                    self.player2_second_serves_in += 1
                    if random.random() <= player2.second_serve_win_percentage:
                        self.player2_second_serves_won += 1
                        print(f"{player2.name} makes 2nd serve and wins point")
                        return 2
                    else:
                        print(f"{player2.name} makes 2nd serve but loses point")
                        return 1
                else:
                    # 2nd serve out
                    self.player2_double_faults += 1
                    print(f"{player2.name} double faults")
                    return 1


    def simulate_match(self):
        print("Simulating match...")
        while True: # Simulate a set
            if self.player1_sets_won == self.sets_to_win or self.player2_sets_won == self.sets_to_win:
                break

            player1_games_won = 0
            player2_games_won = 0

            # Add a new index to the list for the set
            self.player1_games_won_per_set.append(0)
            self.player2_games_won_per_set.append(0)

            # Add a new index to the list for the tiebreak
            self.player1_points_won_in_tiebreak_per_set.append(0)
            self.player2_points_won_in_tiebreak_per_set.append(0)

            while True: # Simulate a game
                if (player1_games_won >= 6 or player2_games_won >= 6) and abs(player1_games_won - player2_games_won) >= 2:
                    break

                print()
                self.print_scoreline(True, 0, 0)

                if player1_games_won == 6 and player2_games_won == 6:
                    # Simulate a tiebreak
                    player1_points_won_in_tiebreak = 0
                    player2_points_won_in_tiebreak = 0

                    # Player who receives first in the tiebreak is the player who will serve first in the next set
                    server_that_should_start_next_set = not self.player1_to_serve

                    points_needed_to_win_tiebreak = 7 if len(self.player1_games_won_per_set) < (self.sets_to_win) * 2 - 1 else 10

                    while True:
                        if self.simulate_point(self.player1, self.player2) == 1:
                            player1_points_won_in_tiebreak += 1
                            self.player1_points_won_in_tiebreak_per_set[-1] += 1
                            self.player1_totaL_points_won += 1
                        else:
                            player2_points_won_in_tiebreak += 1
                            self.player2_points_won_in_tiebreak_per_set[-1] += 1
                            self.player2_total_points_won += 1

                        if (player1_points_won_in_tiebreak >= points_needed_to_win_tiebreak or player2_points_won_in_tiebreak >= points_needed_to_win_tiebreak) and \
                            abs(player1_points_won_in_tiebreak - player2_points_won_in_tiebreak) >= 2:
                            self.player1_to_serve = server_that_should_start_next_set
                            break

                        # Switch server after every 2 points
                        if (player1_points_won_in_tiebreak + player2_points_won_in_tiebreak) % 2 == 1:
                            self.player1_to_serve = not self.player1_to_serve
                        
                        self.print_scoreline(True, player1_points_won_in_tiebreak, player2_points_won_in_tiebreak)

                    if player1_points_won_in_tiebreak > player2_points_won_in_tiebreak:
                        player1_games_won += 1
                        self.player1_games_won_per_set[-1] += 1
                        self.player1_tiebreaks_won += 1
                    else:
                        player2_games_won += 1
                        self.player2_games_won_per_set[-1] += 1
                        self.player2_tiebreaks_won += 1

                    self.total_tiebreaks_played += 1
                    break

                # --- This lower part of the code is only reached if there is no tiebreak in the set ---

                # Otherwise, simulate a regular game
                player1_points_won = 0
                player2_points_won = 0

                while True:
                    # Regular game
                    if self.simulate_point(self.player1, self.player2) == 1:
                        player1_points_won += 1
                        self.player1_totaL_points_won += 1
                    else:
                        player2_points_won += 1
                        self.player2_total_points_won += 1

                    if (player1_points_won >= 4 or player2_points_won >= 4) and abs(player1_points_won - player2_points_won) >= 2:
                        break

                    self.print_scoreline(True, player1_points_won, player2_points_won)
                    
                if player1_points_won > player2_points_won:
                    player1_games_won += 1
                    self.player1_games_won_per_set[-1] += 1
                    self.player1_service_games_won += 1 if self.player1_to_serve else 0
                else:
                    player2_games_won += 1
                    self.player2_games_won_per_set[-1] += 1
                    self.player2_service_games_won += 1 if not self.player1_to_serve else 0

                if self.player1_to_serve:
                    self.player1_service_games_played += 1
                else:
                    self.player2_service_games_played += 1

                # Switch server
                self.player1_to_serve = not self.player1_to_serve

                # End of game

            if player1_games_won > player2_games_won:
                self.player1_sets_won += 1
            else:
                self.player2_sets_won += 1

            self.print_scoreline(False, 0, 0)
            # End of set
            
        # End of match

        # Print match statistics
        print()
        self.print_match_statistics()

    def print_match_statistics(self):
        winner = player1 if self.player1_sets_won > self.player2_sets_won else player2
        print(f"Match winner: {winner.name}!")

        print(f"{player1.name} total points won: {self.player1_totaL_points_won}")
        print(f"{player2.name} total points won: {self.player2_total_points_won}")
        winning_percentage = round(self.player1_totaL_points_won / (self.player1_totaL_points_won + self.player2_total_points_won) * 100, 2)
        if winner == player2:
            winning_percentage = 100 - winning_percentage
        print(f"Point winning percentage: {winning_percentage}%")

        print()

        print(f"{player1.name} total games won: {sum(self.player1_games_won_per_set)}")
        print(f"{player1.name} service games won: {self.player1_service_games_won} / {self.player1_service_games_played}")

        print(f"{player2.name} total games won: {sum(self.player2_games_won_per_set)}")
        print(f"{player2.name} service games won: {self.player2_service_games_won} / {self.player2_service_games_played}")

        if self.total_tiebreaks_played > 0:
            print(f"{player1.name} tiebreaks won: {self.player1_tiebreaks_won}")
            print(f"{player2.name} tiebreaks won: {self.player2_tiebreaks_won}")

        print()

        print(f"{player1.name} first serve percentage: {round(self.player1_first_serves_in / self.player1_first_serves_played * 100, 2)}%")      
        print(f"{player1.name} first serve points won: {round(self.player1_first_serves_won / self.player1_first_serves_in * 100, 2)}%")
        print(f"{player1.name} second serve points won: {round(self.player1_second_serves_won / self.player1_second_serves_in * 100, 2)}%")
        print(f"{player1.name} double faults: {self.player1_double_faults}")

        print()

        print(f"{player2.name} first serve percentage: {round(self.player2_first_serves_in / self.player2_first_serves_played * 100, 2)}%")
        print(f"{player2.name} first serve points won: {round(self.player2_first_serves_won / self.player2_first_serves_in * 100, 2)}%")
        print(f"{player2.name} second serve points won: {round(self.player2_second_serves_won / self.player2_second_serves_in * 100, 2)}%")
        print(f"{player2.name} double faults: {self.player2_double_faults}")
                
# Example usage
# Wimbledon womens
# seed = datetime.datetime(2023, 7, 15)
# player1 = Player(0.63, 0.86, 0.61, 0.55) # -> 4 df
# player2 = Player(0.48, 1, 0.48, 0.45) # -> 0 df
# Wimbledon mens prediction
# seed = datetime.datetime(2023, 7, 16)
# player1 = Player(0.645, 0.87, 0.7, 0.56) # -> 7 df
# player2 = Player(0.643, 0.92, 0.72, 0.57) # -> 1 df
# Wimbledon mens actual (player2 served first)
seed = datetime.datetime(2023, 7, 16)
player1 = Player("Carlos Alcaraz", 0.62, 0.87, 0.7, 0.57) # -> 4 df
player2 = Player("Novak Djokovic", 0.64, 0.90, 0.62, 0.59) # -> 7 df

seed = int(seed.strftime("%Y%m%d"))
print("Seed:", seed)
tennis_match = TennisMatch(player1, player2, 3, False, seed)
tennis_match.simulate_match()
