#!/usr/bin/env python3
"""Unvalidated synthetic win heuristic for the legacy web interface.

Detailed forecasts are unavailable until a model-to-serve mapping is validated.
"""

import sys
import os
import json
import random
import argparse

# Add project paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, 'tennis_preds'))

from tennis_preds.tennis import Player, TennisMatch

DATA_ROOT = os.path.abspath(os.environ.get('TENNIS_DATA_ROOT', project_root))

def create_player_from_data(name, player_data, surface='grass'):
    """Create synthetic heuristic inputs, not measured or model-derived stats."""
    # Base serving statistics
    first_serve_percentage = 0.65
    second_serve_percentage = 0.90
    first_serve_win_percentage = 0.70
    second_serve_win_percentage = 0.55
    
    # Get player factors
    p_factor = player_data.get('p_factor', 0)
    n_factor = player_data.get('n_factor', 0)
    
    # Surface adjustments
    surface_adjustments = {
        'grass': {'first_serve': 0.02, 'first_win': 0.05, 'second_win': 0.02},
        'clay': {'first_serve': -0.01, 'first_win': -0.02, 'second_win': 0.01},
        'hard': {'first_serve': 0, 'first_win': 0, 'second_win': 0}
    }
    
    adj = surface_adjustments.get(surface, surface_adjustments['hard'])
    
    # Apply adjustments
    first_serve_percentage += adj['first_serve'] + (p_factor * 2) - (n_factor * 2)
    first_serve_win_percentage += adj['first_win'] + (p_factor * 5) - (n_factor * 3)
    second_serve_win_percentage += adj['second_win'] + (p_factor * 3) - (n_factor * 2)
    
    # Ensure realistic bounds
    first_serve_percentage = max(0.4, min(0.8, first_serve_percentage))
    first_serve_win_percentage = max(0.5, min(0.85, first_serve_win_percentage))
    second_serve_win_percentage = max(0.35, min(0.70, second_serve_win_percentage))
    
    return Player(name, first_serve_percentage, second_serve_percentage, 
                 first_serve_win_percentage, second_serve_win_percentage)

def simulate_matches(tournament_path, gender, player1_name, player2_name, 
                    sets_to_win=3, num_simulations=500, surface='grass'):
    """Return heuristic win counts only, never detailed match forecasts."""
    if num_simulations < 1:
        raise ValueError("num_simulations must be positive")
    
    # Load player data
    players_file = os.path.join(DATA_ROOT, tournament_path, f'players_{gender}.json')
    
    with open(players_file, 'r') as f:
        players_data = json.load(f)
    
    if player1_name not in players_data or player2_name not in players_data:
        raise ValueError(f"Player not found in {players_file}")
    
    player1_data = players_data[player1_name]
    player2_data = players_data[player2_name]
    
    # Create players
    player1 = create_player_from_data(player1_name, player1_data, surface)
    player2 = create_player_from_data(player2_name, player2_data, surface)
    
    # Run simulations
    results: dict[str, float] = {
        'player1_wins': 0.0,
        'player2_wins': 0.0,
    }
    
    for i in range(num_simulations):
        player1_to_start = random.choice([True, False])
        match = TennisMatch(player1, player2, sets_to_win, player1_to_start)
        match.simulate_match(verbose=False)
        
        winner = match.get_match_winner()
        if winner == player1:
            results['player1_wins'] += 1
        else:
            results['player2_wins'] += 1
        
    # These frequencies are conditional on synthetic inputs, not calibrated odds.
    results['player1_win_percentage'] = round((results['player1_wins'] / num_simulations) * 100, 1)
    results['player2_win_percentage'] = round((results['player2_wins'] / num_simulations) * 100, 1)
    return {
        **results,
        'win_estimate': {
            'method': 'synthetic_serve_heuristic',
            'validated': False,
            'description': 'Unvalidated heuristic using synthetic serve inputs; not calibrated model probabilities.',
        },
        'detailed_forecast': {
            'status': 'unavailable',
            'reason': 'No validated model-to-serve mapping for score, statistics or duration forecasts.',
        },
    }

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Simulate tennis matches')
    parser.add_argument('tournament_path', help='Path to tournament data')
    parser.add_argument('gender', choices=['male', 'female'], help='Player gender')
    parser.add_argument('player1', help='First player name')
    parser.add_argument('player2', help='Second player name')
    parser.add_argument('--sets', type=int, default=3, help='Sets to win (default: 3)')
    parser.add_argument('--simulations', type=int, default=500, help='Number of simulations (default: 500)')
    parser.add_argument('--surface', choices=['grass', 'clay', 'hard'], default='grass', help='Court surface (default: grass)')
    
    args = parser.parse_args()
    
    try:
        results = simulate_matches(
            args.tournament_path, args.gender, args.player1, args.player2,
            args.sets, args.simulations, args.surface
        )
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(json.dumps({'error': str(e)}), file=sys.stderr)
        sys.exit(1)
