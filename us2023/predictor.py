import json
import random
import itertools
from tqdm import tqdm

players_points = json.load(open("player_points_male.json", "r"))

players = json.load(open("players_male.json", "r"))

# with a hill-climbing approach, find the best combination of 8 players with the highest total points under the salary cap (100,000)
# first, lets remove the players that have less than 50 points
players = {player: players[player] for player in players if players_points[player] >= 50}
print(players)

best_players = []
best_points = 0
# go through all possible combinations of 8 players
for players_list in tqdm(itertools.combinations(players, 8)):
    # calculate the total points
    total_points = 0
    for player in players_list:
        total_points += players_points[player]
    # calculate the total salary
    total_salary = 0
    for player in players_list:
        total_salary += players[player]["cost"]
    # if the total salary is under the salary cap, then we're done
    if total_salary <= 100000:
        best_players = players_list if total_points > best_points else best_players
        best_points = total_points if total_points > best_points else best_points

print(best_players)
print(best_points)

# print results to a file
with open("results_male.txt", "w") as f:
    f.write("Best players: " + str(best_players) + "\n")
    f.write("Total points: " + str(best_points) + "\n")
    f.write("Total salary: " + str(total_salary) + "\n")
    for player in best_players:
        f.write(player + ": " + str(players_points[player]) + " points, " + str(players[player]["cost"]) + " salary\n")