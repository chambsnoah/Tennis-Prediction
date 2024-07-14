import datetime
import random

class Player:
    def __init__(self, name="John Doe", first_serve_percentage=0.5, second_serve_percentage=0.9, first_serve_win_percentage=0.5, second_serve_win_percentage=0.5):
        self.name = name
        self.first_serve_percentage = first_serve_percentage
        self.second_serve_percentage = second_serve_percentage
        self.first_serve_win_percentage = first_serve_win_percentage
        self.second_serve_win_percentage = second_serve_win_percentage

    # def __init__(self, name="John Doe", first_serve_percentage=0.5, service_points_won=80,  first_serve_win_percentage=0.5, second_serve_win_percentage=0.5):
    #     self.name = name
    #     self.first_serve_percentage = first_serve_percentage
    #     self.second_serve_percentage = (service_points_won / self.avg(first_serve_win_percentage, second_serve_win_percentage)) * (1 - first_serve_percentage)
    #     self.first_serve_win_percentage = second_serve_win_percentage
    #     self.second_serve_win_percentage = second_serve_win_percentage

    def avg(self, no1, no2):
        return (no1 + no2) / 2

class PlayerSimple:
    def __init__(self, name="John Doe", points_won_on_serve_percentage=0.5):
        self.name = name
        self.points_won_on_serve_percentage = points_won_on_serve_percentage

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

        # Break points
        self.player1_break_point_chances = 0
        self.player1_break_points_converted = 0
        self.player2_break_point_chances = 0
        self.player2_break_points_converted = 0

        # Return points
        self.player1_return_points_won = 0
        self.player2_return_points_won = 0

        # Service points
        self.player1_service_points_won = 0
        self.player2_service_points_won = 0

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
                    print(f" ({self.player1_points_won_in_tiebreak_per_set[i]}-{self.player2_points_won_in_tiebreak_per_set[i]})   | {self.player1.name if self.player1_to_serve == True else self.player2.name} to serve", end="")
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
                    print(f" {score} {spaces} | {self.player1.name if self.player1_to_serve else self.player2.name} to serve", end=" ")

            if i < num_sets - 1:
                print(",", end=" ")
            else:
                print()

    def simulate_point(self, player1, player2, verbose):
        if type(player1) == PlayerSimple:
            return self.simulate_point_simple(player1, player2)
        
        # Simulate a point
        if self.player1_to_serve:
            # 1st serve
            self.player1_first_serves_played += 1
            if random.random() <= player1.first_serve_percentage:
                # 1st serve in
                self.player1_first_serves_in += 1
                if random.random() <= player1.first_serve_win_percentage:
                    self.player1_first_serves_won += 1
                    if verbose:
                        print(f"{player1.name} makes 1st serve and wins point")
                    return 1
                else:
                    if verbose:
                        print(f"{player1.name} makes 1st serve but loses point")
                    return 2
            else:
                # 1st serve out
                self.player1_second_serves_played += 1
                if verbose:
                    print(f"{player1.name} misses 1st serve")
                if random.random() <= player1.second_serve_percentage:
                    # 2nd serve in
                    self.player1_second_serves_in += 1
                    if random.random() <= player1.second_serve_win_percentage:
                        self.player1_second_serves_won += 1
                        if verbose:
                            print(f"{player1.name} makes 2nd serve and wins point")
                        return 1
                    else:
                        if verbose:
                            print(f"{player1.name} makes 2nd serve but loses point")
                        return 2
                else:
                    # 2nd serve out
                    self.player1_double_faults += 1
                    if verbose:
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
                    if verbose:
                        print(f"{player2.name} makes 1st serve and wins point")
                    return 2
                else:
                    if verbose:
                        print(f"{player2.name} makes 1st serve but loses point")
                    return 1
            else:
                # 1st serve out
                self.player2_second_serves_played += 1
                if verbose:
                    print(f"{player2.name} misses 1st serve")
                if random.random() <= player2.second_serve_percentage:
                    # 2nd serve in
                    self.player2_second_serves_in += 1
                    if random.random() <= player2.second_serve_win_percentage:
                        self.player2_second_serves_won += 1
                        if verbose:
                            print(f"{player2.name} makes 2nd serve and wins point")
                        return 2
                    else:
                        if verbose:
                            print(f"{player2.name} makes 2nd serve but loses point")
                        return 1
                else:
                    # 2nd serve out
                    self.player2_double_faults += 1
                    if verbose:
                        print(f"{player2.name} double faults")
                    return 1

    def simulate_point_simple(self, player1, player2):
        # Simulate a point
        if self.player1_to_serve:
            if random.random() <= player1.points_won_on_serve_percentage:
                return 1
            else:
                return 2
        else:
            if random.random() <= player2.points_won_on_serve_percentage:
                return 2
            else:
                return 1

    def simulate_match(self, verbose=True):
        if verbose:
            print("Simulating match...")
            print(f"{self.player1.name} vs {self.player2.name}")

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

                if verbose:
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
                        if self.simulate_point(self.player1, self.player2, verbose) == 1:
                            player1_points_won_in_tiebreak += 1
                            self.player1_points_won_in_tiebreak_per_set[-1] += 1
                            self.player1_totaL_points_won += 1
                            if not self.player1_to_serve:
                                self.player1_return_points_won += 1
                            else:
                                self.player1_service_points_won += 1
                        else:
                            player2_points_won_in_tiebreak += 1
                            self.player2_points_won_in_tiebreak_per_set[-1] += 1
                            self.player2_total_points_won += 1
                            if self.player1_to_serve:
                                self.player2_return_points_won += 1
                            else:
                                self.player2_service_points_won += 1

                        if (player1_points_won_in_tiebreak >= points_needed_to_win_tiebreak or player2_points_won_in_tiebreak >= points_needed_to_win_tiebreak) and \
                            abs(player1_points_won_in_tiebreak - player2_points_won_in_tiebreak) >= 2:
                            self.player1_to_serve = server_that_should_start_next_set
                            break

                        # Switch server after every 2 points
                        if (player1_points_won_in_tiebreak + player2_points_won_in_tiebreak) % 2 == 1:
                            self.player1_to_serve = not self.player1_to_serve
                        
                        if verbose:
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
                    if self.simulate_point(self.player1, self.player2, verbose) == 1:
                        player1_points_won += 1
                        self.player1_totaL_points_won += 1
                        if not self.player1_to_serve:
                            self.player1_return_points_won += 1
                        else:
                            self.player1_service_points_won += 1
                    else:
                        player2_points_won += 1
                        self.player2_total_points_won += 1
                        if self.player1_to_serve:
                            self.player2_return_points_won += 1
                        else:
                            self.player2_service_points_won += 1

                    if (player1_points_won >= 4 or player2_points_won >= 4) and abs(player1_points_won - player2_points_won) >= 2:
                        break

                    if self.player1_to_serve:
                        if player2_points_won >= 3 and player2_points_won - player1_points_won >= 1:
                            self.player2_break_point_chances += 1
                    else:
                        if player1_points_won >= 3 and player1_points_won - player2_points_won >= 1:
                            self.player1_break_point_chances += 1

                    if verbose:
                        self.print_scoreline(True, player1_points_won, player2_points_won)
                    
                if player1_points_won > player2_points_won:
                    if not self.player1_to_serve:
                        self.player1_break_points_converted += 1
                    player1_games_won += 1
                    self.player1_games_won_per_set[-1] += 1
                    self.player1_service_games_won += 1 if self.player1_to_serve else 0
                else:
                    if self.player1_to_serve:
                        self.player2_break_points_converted += 1
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

            if verbose:
                self.print_scoreline(False, 0, 0)
            # End of set
            
        # End of match

        if verbose:
            print()

    def get_match_winner(self):
        return self.player1 if self.player1_sets_won > self.player2_sets_won else self.player2
    
    def get_player1_points_won(self):
        player1_percentage = round(self.player1_totaL_points_won / (self.player1_totaL_points_won + self.player2_total_points_won) * 100, 2)
        return player1_percentage
    
    def get_player2_points_won(self):
        player2_percentage = round(self.player2_total_points_won / (self.player1_totaL_points_won + self.player2_total_points_won) * 100, 2)
        return player2_percentage
    
    def print_match_statistics(self):
        winner = self.get_match_winner()
        print(f"Match winner: {winner.name}!")

        print()
        
        # Statistics table
        print(f"{self.player1.name} | {self.player2.name}")

        if type(self.player1) == Player:
            print(f"Double faults: {self.player1_double_faults} | {self.player2_double_faults}")
            
            player1_first_serve_percentage = round(self.player1_first_serves_in / self.player1_first_serves_played * 100, 2)
            player2_first_serve_percentage = round(self.player2_first_serves_in / self.player2_first_serves_played * 100, 2)
            print(f"1st serve in: {player1_first_serve_percentage}% | {player2_first_serve_percentage}%")

            player1_first_serve_points_won_percentage = round(self.player1_first_serves_won / self.player1_first_serves_in * 100, 2)
            player2_first_serve_points_won_percentage = round(self.player2_first_serves_won / self.player2_first_serves_in * 100, 2)
            print(f"1st serve points won: {player1_first_serve_points_won_percentage}% | {player2_first_serve_points_won_percentage}%")

            player1_second_serve_points_won_percentage = round(self.player1_second_serves_won / self.player1_second_serves_in * 100, 2)
            player2_second_serve_points_won_percentage = round(self.player2_second_serves_won / self.player2_second_serves_in * 100, 2)
            print(f"2nd serve points won: {player1_second_serve_points_won_percentage}% | {player2_second_serve_points_won_percentage}%")

        print(f"Break points won: {self.player1_break_points_converted}/{self.player1_break_point_chances} | {self.player2_break_points_converted}/{self.player2_break_point_chances}")

        print(f"Tiebreaks won: {self.player1_tiebreaks_won} | {self.player2_tiebreaks_won}")

        print(f"Receiving points won: {self.player1_return_points_won} | {self.player2_return_points_won}")

        print(f"Total points won: {self.player1_totaL_points_won} | {self.player2_total_points_won}")
        player1_percentage = round(self.player1_totaL_points_won / (self.player1_totaL_points_won + self.player2_total_points_won) * 100, 2)
        print(f"Points won percentage: {player1_percentage}% | {100 - player1_percentage}%")

        print(f"Total games won: {sum(self.player1_games_won_per_set)} | {sum(self.player2_games_won_per_set)}")

        print(f"Service points won: {self.player1_service_points_won} | {self.player2_service_points_won}")

        print(f"Service games won: {self.player1_service_games_won}/{self.player1_service_games_played} | {self.player2_service_games_won}/{self.player2_service_games_played}")
    
    def test_simple():
        player1_wins = 0
        player2_wins = 0
        for i in range(1000):
            player1 = PlayerSimple("Player 1", 0.68)
            player2 = PlayerSimple("Player 2", 0.50)
            player1_to_start = random.choice([True, False])
            tennis_match = TennisMatch(player1, player2, 2, player1_to_start, None)
            tennis_match.simulate_match(verbose=False)
            if tennis_match.get_match_winner() == player1:
                player1_wins += 1
            else:
                player2_wins += 1

        print("Player 1 wins:", player1_wins)
        print("Player 2 wins:", player2_wins)


# Example usage
if __name__ == "__main__":
    # Australian open womens (Sabalenka served first)
    # seed = datetime.datetime(2023, 1, 28)
    # player1 = Player("Elena Rybakina", 0.64, 0.977, 0.72, 0.41) # -> 1 df
    # player2 = Player("Aryna Sabalenka", 0.66, 0.816, 0.72, 0.53) # -> 7 df

    # Australian open mens (Djokovic served first)
    # seed = datetime.datetime(2023, 1, 29)
    # player1 = Player("Stefanos Tsitsipas", 0.65, 0.919, 0.72, 0.56) # -> 3 df
    # player2 = Player("Novak Djokovic", 0.66, 0.912, 0.80, 0.71) # -> 3 df

    # French open womens (Swiatek served first)
    # seed = datetime.datetime(2023, 6, 10)
    # player1 = Player("Iga Swiatek", 0.63, 0.909, 0.62, 0.57) # -> 3 df
    # player2 = Player("Karolina Muchova", 0.56, 0.923, 0.52, 0.50) # -> 3 df

    # French open mens (Ruud served first)
    # seed = datetime.datetime(2023, 6, 11)
    # player1 = Player("Novak Djokovic", 0.73, 0.963, 0.80, 0.65) # -> 1 df
    # player2 = Player("Casper Ruud", 0.64, 0.974, 0.57, 0.68) # -> 1 df

    # Wimbledon womens (Jabeur served first)
    # seed = datetime.datetime(2023, 7, 15)
    # player1 = Player("Marketa Vondrousova", 0.63, 0.83, 0.61, 0.55) # -> 4 df
    # player2 = Player("Ons Jabeur", 0.48, 1, 0.48, 0.45) # -> 0 df

    # Wimbledon mens prediction (assuming Alcaraz serves first)
    # seed = datetime.datetime(2023, 7, 16)
    # player1 = Player("Carlos Alcaraz", 0.645, 0.87, 0.7, 0.56) # -> 7 df
    # player2 = Player("Novak Djokovic", 0.643, 0.92, 0.72, 0.57) # -> 1 df

    # Wimbledon mens actual 2023 (Djokovic served first)
    # seed = datetime.datetime(2023, 7, 16)
    # player1 = Player("Carlos Alcaraz", 0.62, 0.875, 0.7, 0.57) # -> 7 df
    # player2 = Player("Novak Djokovic", 0.64, 0.955, 0.62, 0.59) # -> 3 df

    # Wimbledon mens actual 2024 (Djokovic served first)
    # to calculate second serve percentage:
    # Points on second serve = Total service points * (1 - 1st serve %)
    # = ((service points won) / avg(1st serve win %, 2nd serve win %)) * (1 -  1st serve %)
    # second serve percentage = points on second serve / (points on second serve + double faults)
    seed = datetime.datetime(2024, 7, 14)
    player1 = Player("Carlos Alcaraz", 0.635, 0.907, 0.737, 0.617) # -> 7 df
    player2 = Player("Novak Djokovic", 0.672, 0.918, 0.818, 0.656) # -> 3 df

    seed = int(seed.strftime("%Y%m%d"))
    print("Seed:", seed)
    tennis_match = TennisMatch(player1, player2, 3, True, seed)
    tennis_match.simulate_match(verbose=True)
    tennis_match.print_match_statistics()