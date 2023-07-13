import json
import random

def evaluate_combination(combination, points, costs, budget):
    total_points = sum(points[player] for player in combination)
    total_cost = sum(costs[player] for player in combination)
    return total_points, total_cost

# Read player points from file
with open('player_points_male.json') as points_file:
    points_data = json.load(points_file)

# Read player costs from file
with open('players_male.json') as costs_file:
    costs_data = json.load(costs_file)

# Extract player names and points
players = list(points_data.keys())
points = points_data

# Extract player costs
costs = {}
for player, cost_data in costs_data.items():
    costs[player] = cost_data['cost']

# Set budget constraint
budget_constraint = 100000

# Set the number of iterations
num_iterations = 100000

# Initialize variables to track the best combination and its score
best_combination = None
best_score = 0

# Perform random search for the specified number of iterations
while best_score < 1600:
    random_combination = random.sample(players, 8)
    score, cost = evaluate_combination(random_combination, points, costs, budget_constraint)
    if cost <= budget_constraint and score > best_score:
        best_combination = random_combination
        best_score = score

# Print the best combination
print("Best combination of 8 players:")
print(best_combination)
print(best_score)