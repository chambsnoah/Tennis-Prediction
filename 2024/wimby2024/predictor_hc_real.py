import json
import random

random.seed(20240701)

config = "f"

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

current_best_players = random.sample(players_list, 8)
current_best_points = 0
total_salary = 0
for player in current_best_players:
    current_best_points += players_points[player]
    total_salary += players[player]["cost"]
while total_salary <= 100000:
    neighbor_found = False
    for i in range(8):
        for j in range(len(players)):
            if players_list[j] in current_best_players:
                continue
            new_players = current_best_players.copy()
            new_players[i] = players_list[j]
            new_points = 0
            new_salary = 0
            for player in new_players:
                new_points += players_points[player]
                new_salary += players[player]["cost"]
            if new_salary <= 100000 and new_points > current_best_points:
                current_best_players = new_players
                current_best_points = new_points
                total_salary = new_salary
                neighbor_found = True
                break
        if neighbor_found:
            break
    if not neighbor_found:
        break

print(current_best_players)
print(current_best_points)