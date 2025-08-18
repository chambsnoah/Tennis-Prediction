#!/usr/bin/env python3
"""
Team optimization wrapper for web interface
Extends existing predictor_annealing.py functionality
"""

import sys
import os
import json
import random
import math
import argparse

# Add project paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

def evaluate_combination(combination, points, costs):
    """Evaluate a team combination - from existing predictor_annealing.py"""
    total_points = sum(points[player] for player in combination)
    total_cost = sum(costs[player] for player in combination)
    return total_points, total_cost

def perturb_solution(current_solution, remaining_players, team_size):
    """Perturb current solution - adapted from existing predictor_annealing.py"""
    num_to_replace = min(team_size - 1, len(remaining_players))
    if num_to_replace <= 0:
        return current_solution
    
    new_solution = random.sample(remaining_players, num_to_replace) + [random.choice(current_solution)]
    
    # Ensure no duplicates
    while len(set(new_solution)) != len(new_solution):
        new_solution = random.sample(remaining_players, num_to_replace) + [random.choice(current_solution)]
    
    return new_solution

def simulated_annealing(players, points, costs, budget, team_size, cutoff=1300):
    """Simulated annealing optimization - from existing predictor_annealing.py"""
    current_solution = random.sample(players, min(team_size, len(players)))
    remaining_players = [player for player in players if player not in current_solution]
    best_solution = current_solution[:]
    current_score, current_cost = evaluate_combination(current_solution, points, costs)
    best_score = current_score

    temperature = 100.0
    cooling_rate = 0.95
    max_iterations = 1000

    for i in range(max_iterations):
        if temperature <= 0.1 and best_score >= cutoff:
            break
            
        new_solution = perturb_solution(current_solution, remaining_players, team_size)
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

def optimize_team(tournament_path, gender, budget=100000, team_size=8):
    """Optimize team selection for a tournament"""
    
    # Determine file paths
    base_path = os.path.join(project_root, tournament_path)
    player_points_file = os.path.join(base_path, f'player_points_{gender}.json')
    players_file = os.path.join(base_path, f'players_{gender}.json')
    
    # Load player points data
    points_data = {}
    if os.path.exists(player_points_file):
        with open(player_points_file, 'r') as f:
            points_data = json.load(f)
    
    # Load player cost data
    if not os.path.exists(players_file):
        raise FileNotFoundError(f"Players file not found: {players_file}")
    
    with open(players_file, 'r') as f:
        costs_data = json.load(f)
    
    # If no points data, create simple scoring based on seed
    if not points_data:
        for name, data in costs_data.items():
            seed = data.get('seed', 128)
            # Higher seeds (lower numbers) get higher scores
            points_data[name] = max(1, 129 - seed) * 10
    
    # Extract data for optimization
    players = list(points_data.keys())
    points = points_data
    costs = {player: cost_data['cost'] for player, cost_data in costs_data.items()}
    
    # Set cutoff based on gender (from original predictor_annealing.py)
    cutoff = 1300 if gender == 'female' else 1300
    
    # Run optimization
    best_players, best_score = simulated_annealing(players, points, costs, budget, team_size, cutoff)
    
    # Format results
    team_roster = []
    total_cost = 0
    
    for player_name in best_players:
        if player_name in costs_data:
            player_info = costs_data[player_name]
            player_cost = costs[player_name]
            player_points = points[player_name]
            total_cost += player_cost
            
            team_roster.append({
                'name': player_name,
                'seed': player_info.get('seed', 0),
                'cost': player_cost,
                'points': player_points,
                'p_factor': player_info.get('p_factor', 0),
                'n_factor': player_info.get('n_factor', 0)
            })
    
    # Sort by points descending
    team_roster.sort(key=lambda x: x['points'], reverse=True)
    
    results = {
        'team_roster': team_roster,
        'total_score': best_score,
        'total_cost': total_cost,
        'budget_used': round((total_cost / budget) * 100, 1) if budget > 0 else 0
    }
    
    return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optimize tennis team selection')
    parser.add_argument('tournament_path', help='Path to tournament data')
    parser.add_argument('gender', choices=['male', 'female'], help='Player gender')
    parser.add_argument('--budget', type=int, default=100000, help='Budget constraint (default: 100000)')
    parser.add_argument('--team-size', type=int, default=8, help='Team size (default: 8)')
    
    args = parser.parse_args()
    
    try:
        results = optimize_team(
            args.tournament_path, args.gender, args.budget, args.team_size
        )
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(json.dumps({'error': str(e)}), file=sys.stderr)
        sys.exit(1)
