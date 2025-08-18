#!/usr/bin/env python3
"""
Simple Flask server for Tennis Prediction System
Calls existing Python scripts via clean wrapper modules
"""

import os
import sys
import json
import subprocess
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# Get the project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@app.route('/')
def serve_index():
    """Serve the main HTML file"""
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files (CSS, JS, etc.)"""
    return send_from_directory('.', filename)

@app.route('/api/tournaments')
def get_tournaments():
    """Get list of available tournaments by scanning directories"""
    tournaments = []
    
    # Scan for tournament directories
    for year in ['2023', '2024']:
        year_path = os.path.join(PROJECT_ROOT, year)
        if os.path.exists(year_path):
            for tournament_dir in os.listdir(year_path):
                tournament_path = os.path.join(year_path, tournament_dir)
                if os.path.isdir(tournament_path):
                    # Check if it has player data
                    has_male = os.path.exists(os.path.join(tournament_path, 'players_male.json'))
                    has_female = os.path.exists(os.path.join(tournament_path, 'players_female.json'))
                    
                    if has_male or has_female:
                        # Format tournament name nicely
                        tournament_name = tournament_dir.replace('2024', ' 2024').replace('2023', ' 2023')
                        tournament_name = tournament_name.replace('wimby', 'Wimbledon')
                        tournament_name = tournament_name.replace('us', 'US Open')
                        tournament_name = tournament_name.replace('rg', 'Roland Garros')
                        tournament_name = tournament_name.replace('au', 'Australian Open')
                        
                        tournaments.append({
                            'id': f"{year}/{tournament_dir}",
                            'name': tournament_name.title(),
                            'has_male': has_male,
                            'has_female': has_female
                        })
    
    return jsonify(tournaments)

@app.route('/api/players/<path:tournament_path>/<gender>')
def get_players(tournament_path, gender):
    """Get players for a specific tournament and gender"""
    players_file = os.path.join(PROJECT_ROOT, tournament_path, f'players_{gender}.json')
    
    if not os.path.exists(players_file):
        return jsonify({'error': 'Players file not found'}), 404
    
    try:
        with open(players_file, 'r') as f:
            players_data = json.load(f)
        
        # Format for frontend
        players = []
        for name, data in players_data.items():
            players.append({
                'name': name,
                'seed': data.get('seed', 0),
                'cost': data.get('cost', 0),
                'p_factor': data.get('p_factor', 0),
                'n_factor': data.get('n_factor', 0)
            })
        
        # Sort by seed
        players.sort(key=lambda x: x['seed'])
        return jsonify(players)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate-match', methods=['POST'])
def simulate_match():
    """Run match simulation using match_simulator.py"""
    data = request.json
    
    try:
        tournament_path = data['tournament_path']
        gender = data['gender']
        player1_name = data['player1_name']
        player2_name = data['player2_name']
        sets_to_win = int(data.get('sets_to_win', 3))
        num_simulations = int(data.get('num_simulations', 500))
        surface = data.get('surface', 'grass')
        
        # Debug logging
        print(f"DEBUG: Simulating match between '{player1_name}' vs '{player2_name}'")
        print(f"DEBUG: Tournament: {tournament_path}, Gender: {gender}")
        
        # Call the match_simulator.py script
        cmd = [
            sys.executable, 'match_simulator.py',
            tournament_path, gender, player1_name, player2_name,
            '--sets', str(sets_to_win),
            '--simulations', str(num_simulations),
            '--surface', surface
        ]
        
        print(f"DEBUG: Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        print(f"DEBUG: Return code: {result.returncode}")
        print(f"DEBUG: STDOUT: {result.stdout}")
        print(f"DEBUG: STDERR: {result.stderr}")
        
        if result.returncode == 0:
            try:
                simulation_results = json.loads(result.stdout)
                return jsonify(simulation_results)
            except json.JSONDecodeError as e:
                print(f"DEBUG: JSON decode error: {e}")
                return jsonify({'error': f'Invalid JSON response: {result.stdout}'}), 500
        else:
            error_msg = result.stderr if result.stderr else "Simulation failed"
            return jsonify({'error': error_msg}), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Simulation timed out'}), 500
    except Exception as e:
        print(f"DEBUG: Exception in simulate_match: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/optimize-team', methods=['POST'])
def optimize_team():
    """Run team optimization using team_optimizer.py"""
    data = request.json
    
    try:
        tournament_path = data['tournament_path']
        gender = data['gender']
        budget = int(data.get('budget', 100000))
        team_size = int(data.get('team_size', 8))
        
        # Call the team_optimizer.py script
        cmd = [
            sys.executable, 'team_optimizer.py',
            tournament_path, gender,
            '--budget', str(budget),
            '--team-size', str(team_size)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            optimization_results = json.loads(result.stdout)
            return jsonify(optimization_results)
        else:
            error_msg = result.stderr if result.stderr else "Optimization failed"
            return jsonify({'error': error_msg}), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Optimization timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bracket/<path:tournament_path>/<gender>')
def get_bracket(tournament_path, gender):
    """Get tournament bracket data"""
    bracket_file = os.path.join(PROJECT_ROOT, tournament_path, f'bracket_{gender}.txt')
    
    if not os.path.exists(bracket_file):
        return jsonify({'error': 'Bracket file not found'}), 404
    
    try:
        with open(bracket_file, 'r') as f:
            bracket_content = f.read()
        
        # Parse bracket into structured data (simplified)
        matches = []
        lines = bracket_content.strip().split('\n')
        
        for line in lines:
            if 'Singles' in line and ('R1' in line or 'Upcoming' in line):
                # Simple parsing - in a real app you'd want more robust parsing
                parts = line.split()
                if len(parts) >= 6:
                    match_info = {
                        'round': 'R1',
                        'status': 'Upcoming',
                        'player1': ' '.join(parts[4:6]) if len(parts) > 5 else parts[4] if len(parts) > 4 else '',
                        'player2': ' '.join(parts[-2:]) if len(parts) > 7 else parts[-1] if len(parts) > 6 else ''
                    }
                    matches.append(match_info)
        
        return jsonify({
            'bracket_text': bracket_content,
            'matches': matches[:32]  # Limit to first 32 matches for display
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Tennis Prediction Web Interface...")
    print(f"Project root: {PROJECT_ROOT}")
    print("Available at: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
