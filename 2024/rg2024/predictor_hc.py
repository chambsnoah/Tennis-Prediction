import json
import random

random.seed(20240526)

config = "m"

if config == "m":
    player_points_file = "player_points_male.json"
    players_file = "players_male.json"
elif config == "f":
    player_points_file = "player_points_female.json"
    players_file = "players_female.json"
    
players_points = json.load(open(player_points_file, "r"))

players = json.load(open(players_file, "r"))

# with a hill-climbing approach, find the best combination of 8 players with the highest total points under the salary cap (100,000)
# first, lets remove the players that have less than 50 points
players = {player: players[player] for player in players if players_points[player] >= 50}
players_list = list(players)

current_best_players = []
current_best_points = 0
while True:
    # generate a random list of 8 players
    random_players = random.sample(players_list, 8)
    # calculate the total points and salary for the random players
    total_points = 0
    total_salary = 0
    best_players = current_best_players
    best_points = current_best_points
    for player in random_players:
        total_points += players_points[player]
        total_salary += players[player]["cost"]
    # if the total salary is under the salary cap and total points is greater than current best points
    if total_salary <= 100000 and total_points > current_best_points:
        current_best_players = random_players
        current_best_points = total_points
    # check if we have a better solution than the previous iteration
    if current_best_points > best_points:
        best_players = current_best_players
        best_points = current_best_points
    else:
        # generate a new random player list by swapping one player from current best players
        new_players = current_best_players.copy()
        random_index = random.randint(0,7)
        new_players[random_index] = random.choice(players_list)
        # calculate the total points and salary for the new player list
        new_points = 0
        new_salary = 0
        for player in new_players:
            new_points += players_points[player]
            new_salary += players[player]["cost"]
        # if the new list has higher points and is under salary cap, make that the new current best
        if new_salary <= 100000 and new_points > current_best_points:
            current_best_players = new_players
            current_best_points = new_points
        else:
            break

print(current_best_players)
print(current_best_points)
