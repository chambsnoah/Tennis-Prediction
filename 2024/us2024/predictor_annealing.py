import json
import random
import math

random.seed(20240826)

config = "m"

# if using 100 runs of pointsv2 change values below as needed
cutoff = 1400

if config == "m":
    player_points_file = "player_points_male.json"
    players_file = "players_male.json"
    cutoff = 1300
elif config == "f":
    player_points_file = "player_points_female.json"
    players_file = "players_female.json"
    cutoff = 1300

def evaluate_combination(combination, points, costs):
    total_points = sum(points[player] for player in combination)
    total_cost = sum(costs[player] for player in combination)
    return total_points, total_cost

def perturb_solution(current_solution, remaining_players):
    new_solution = random.sample(remaining_players, 7) + [random.choice(current_solution)]
    
    while len(set(new_solution)) != len(new_solution):
        new_solution = random.sample(remaining_players, 7) + [random.choice(current_solution)]
    
    return new_solution

def simulated_annealing(players, points, costs, budget):
    current_solution = random.sample(players, 8)
    remaining_players = [player for player in players if player not in current_solution]
    best_solution = current_solution[:]
    current_score, current_cost = evaluate_combination(current_solution, points, costs)
    best_score = current_score

    temperature = 100.0
    cooling_rate = 0.95

    while temperature > 0.1 or best_score < cutoff:
        new_solution = perturb_solution(current_solution, remaining_players)
        new_score, new_cost = evaluate_combination(new_solution, points, costs)

        if new_cost <= budget:
            if new_score > current_score:
                current_solution = new_solution[:]
                current_score = new_score
                if new_score > best_score:
                    best_solution = new_solution[:]
                    best_score = new_score
            else:
                acceptance_probability = math.exp((new_score - current_score) / temperature) - 1
                if random.random() < acceptance_probability:
                    current_solution = new_solution[:]
                    current_score = new_score

        temperature *= cooling_rate

    return best_solution, best_score

# Read player points from file
with open(player_points_file) as points_file:
    points_data = json.load(points_file)

# Read player costs from file
with open(players_file) as costs_file:
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

# Apply simulated annealing to find the best combination
best_players, best_score = simulated_annealing(players, points, costs, budget_constraint)

# Print the best combination
print("Best combination of 8 players:")
print(best_players)
print(best_score)