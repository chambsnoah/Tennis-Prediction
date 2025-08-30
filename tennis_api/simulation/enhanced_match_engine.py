"""
Enhanced Match Simulation Engine for Phase 2

This module implements an advanced tennis match simulation engine that integrates
AI predictions, dynamic state management, and real-time factor adjustments.
"""

import random
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum

from ..models.enhanced_player import PlayerEnhanced
from ..models.ai_player import PlayerAI, PerformanceContext
from ..ml.ensemble import PredictionEnsemble, ComprehensivePrediction


class MatchState(Enum):
    """Current state of the match"""
    PRE_MATCH = "pre_match"
    IN_PROGRESS = "in_progress"
    MATCH_COMPLETE = "match_complete"


class PointOutcome(Enum):
    """Possible point outcomes"""
    ACE = "ace"
    DOUBLE_FAULT = "double_fault"
    WINNER = "winner"
    UNFORCED_ERROR = "unforced_error"
    REGULAR_PLAY = "regular_play"


@dataclass
class MatchStatistics:
    """Comprehensive match statistics"""
    duration_minutes: int = 0
    total_points: int = 0
    total_games: int = 0
    sets_played: int = 0
    
    # Player statistics
    p1_points_won: int = 0
    p1_games_won: int = 0
    p1_sets_won: int = 0
    p1_aces: int = 0
    p1_double_faults: int = 0
    p1_break_points_won: int = 0
    
    p2_points_won: int = 0
    p2_games_won: int = 0
    p2_sets_won: int = 0
    p2_aces: int = 0
    p2_double_faults: int = 0
    p2_break_points_won: int = 0
    
    # Dynamic factors
    momentum_swings: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to dictionary"""
        return {
            'duration_minutes': self.duration_minutes,
            'total_points': self.total_points,
            'total_games': self.total_games,
            'sets_played': self.sets_played,
            'player1': {
                'points_won': self.p1_points_won,
                'games_won': self.p1_games_won,
                'sets_won': self.p1_sets_won,
                'aces': self.p1_aces,
                'double_faults': self.p1_double_faults,
                'break_points_won': self.p1_break_points_won
            },
            'player2': {
                'points_won': self.p2_points_won,
                'games_won': self.p2_games_won,
                'sets_won': self.p2_sets_won,
                'aces': self.p2_aces,
                'double_faults': self.p2_double_faults,
                'break_points_won': self.p2_break_points_won
            },
            'momentum_swings': self.momentum_swings
        }


class EnhancedMatchEngine:
    """
    Enhanced Tennis Match Simulation Engine
    
    Integrates AI predictions, dynamic player state management, and real-time
    factor adjustments to provide highly realistic match simulations.
    """
    
    def __init__(self, prediction_ensemble: Optional[PredictionEnsemble] = None,
                 surface: str = "hard", tournament_tier: str = "ATP250",
                 verbose: bool = False, seed: Optional[int] = None):
        
        self.prediction_ensemble = prediction_ensemble
        self.surface = surface
        self.tournament_tier = tournament_tier
        self.verbose = verbose
        
        # Set random seed for reproducibility
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        
        # Match state
        self.match_state = MatchState.PRE_MATCH
        self.statistics = MatchStatistics()
        
        # Players (will be set during simulation)
        self.player1: Optional[PlayerEnhanced] = None
        self.player2: Optional[PlayerEnhanced] = None
        
        # Dynamic match factors
        self.current_momentum: float = 0.0  # -1.0 to 1.0
        self.pressure_level: float = 0.5    # 0.0 to 1.0
        self.crowd_factor: float = 1.0      # 0.8 to 1.2
        
        # Match tracking
        self.sets_to_win: int = 3
        self.current_set_scores: List[Tuple[int, int]] = []
        self.current_game_score: Tuple[int, int] = (0, 0)
        self.serving_player: int = 1
        
        # AI prediction cache
        self.ai_predictions: Optional[ComprehensivePrediction] = None
    
    def setup_match(self, player1: PlayerEnhanced, player2: PlayerEnhanced,
                   sets_to_win: int = 3, player1_serves_first: bool = True) -> None:
        """Setup the match with enhanced players"""
        self.player1 = player1
        self.player2 = player2
        self.sets_to_win = sets_to_win
        self.serving_player = 1 if player1_serves_first else 2
        
        # Initialize match state
        self.match_state = MatchState.IN_PROGRESS
        
        # Generate AI predictions if ensemble is available
        if self.prediction_ensemble:
            self._generate_ai_predictions()
        
        # Initialize contextual factors
        self._initialize_match_context()
    
    def _generate_ai_predictions(self) -> None:
        """Generate comprehensive AI predictions for the match"""
        if not self.player1 or not self.player2 or not self.prediction_ensemble:
            return
        
        # Prepare player data for AI prediction
        player1_data = self._prepare_player_data(self.player1)
        player2_data = self._prepare_player_data(self.player2)
        
        match_context = {
            'surface': self.surface,
            'tournament_tier': self.tournament_tier,
            'pressure_level': self.pressure_level
        }
        
        # Generate predictions
        self.ai_predictions = self.prediction_ensemble.predict_match(
            player1_data, player2_data, match_context
        )
        
        if self.verbose:
            winner_name = self.player1.name if self.ai_predictions.winner_prediction == 1 else self.player2.name
            print(f"AI Prediction: {winner_name} wins ({self.ai_predictions.win_probability:.1%})")
    
    def _prepare_player_data(self, player: PlayerEnhanced) -> Dict[str, Any]:
        """Prepare player data for AI prediction"""
        data = {
            'name': player.name,
            'current_ranking': player.current_ranking,
            'recent_form_factor': player.recent_form_factor,
            'surface_preference': player.surface_preference
        }
        
        # Add API stats if available
        if player.api_stats:
            data['serve_stats'] = {
                'first_serve_win_percentage': player.api_stats.serve_stats.first_serve_win_percentage,
                'second_serve_win_percentage': player.api_stats.serve_stats.second_serve_win_percentage
            }
            data['recent_matches'] = player.api_stats.recent_matches
        
        return data
    
    def _initialize_match_context(self) -> None:
        """Initialize contextual factors for the match"""
        if not self.player1 or not self.player2:
            return
        
        # Set initial pressure based on ranking difference
        ranking_diff = abs(self.player1.current_ranking - self.player2.current_ranking)
        if ranking_diff > 50:
            self.pressure_level = 0.7
        else:
            self.pressure_level = 0.5
        
        # Adjust for tournament tier
        tier_pressure = {
            'GrandSlam': 0.9,
            'Masters1000': 0.8,
            'ATP500': 0.6,
            'ATP250': 0.5
        }
        self.pressure_level = min(1.0, self.pressure_level + tier_pressure.get(self.tournament_tier, 0.5))
    
    def simulate_point(self) -> Tuple[int, PointOutcome]:
        """Simulate a single point with enhanced factors"""
        if not self.player1 or not self.player2:
            raise ValueError("Players not set up for simulation")
        
        server = self.player1 if self.serving_player == 1 else self.player2
        returner = self.player2 if self.serving_player == 1 else self.player1
        
        # Get adjusted serve performance
        serve_performance = server.get_adjusted_serve_percentage(
            self.surface, returner.current_ranking
        )
        
        # Apply dynamic factors
        serve_performance = self._apply_dynamic_factors(serve_performance, self.serving_player)
        
        # Execute point simulation
        point_winner, outcome = self._execute_point_simulation(serve_performance)
        
        # Update statistics and dynamics
        self._update_point_statistics(point_winner, outcome)
        self._update_dynamic_factors(point_winner, outcome)
        
        return point_winner, outcome
    
    def _apply_dynamic_factors(self, base_performance: float, serving_player: int) -> float:
        """Apply dynamic factors to adjust performance"""
        adjusted_performance = base_performance
        
        # Apply momentum
        momentum_effect = self.current_momentum if serving_player == 1 else -self.current_momentum
        adjusted_performance += momentum_effect * 0.05
        
        # Apply pressure (negative effect)
        adjusted_performance -= self.pressure_level * 0.03
        
        # Apply fatigue
        server = self.player1 if serving_player == 1 else self.player2
        fatigue_effect = (1.0 - server.physical_condition.fatigue_factor) * 0.04
        adjusted_performance -= fatigue_effect
        
        # Ensure reasonable bounds
        return max(0.2, min(0.95, adjusted_performance))
    
    def _execute_point_simulation(self, serve_performance: float) -> Tuple[int, PointOutcome]:
        """Execute the actual point simulation"""
        # First serve attempt
        if random.random() <= 0.65:  # First serve in
            if random.random() <= serve_performance:
                # Check for ace
                if random.random() <= 0.06:
                    return self.serving_player, PointOutcome.ACE
                else:
                    return self.serving_player, PointOutcome.REGULAR_PLAY
            else:
                return 3 - self.serving_player, PointOutcome.WINNER
        else:
            # Second serve
            if random.random() <= 0.92:  # Second serve in
                if random.random() <= serve_performance * 0.8:
                    return self.serving_player, PointOutcome.REGULAR_PLAY
                else:
                    return 3 - self.serving_player, PointOutcome.WINNER
            else:
                return 3 - self.serving_player, PointOutcome.DOUBLE_FAULT
    
    def _update_point_statistics(self, winner: int, outcome: PointOutcome) -> None:
        """Update match statistics after a point"""
        self.statistics.total_points += 1
        
        if winner == 1:
            self.statistics.p1_points_won += 1
        else:
            self.statistics.p2_points_won += 1
        
        # Update specific outcome statistics
        if outcome == PointOutcome.ACE:
            if self.serving_player == 1:
                self.statistics.p1_aces += 1
            else:
                self.statistics.p2_aces += 1
        elif outcome == PointOutcome.DOUBLE_FAULT:
            if self.serving_player == 1:
                self.statistics.p1_double_faults += 1
            else:
                self.statistics.p2_double_faults += 1
    
    def _update_dynamic_factors(self, winner: int, outcome: PointOutcome) -> None:
        """Update dynamic match factors"""
        # Update momentum
        momentum_change = 0.0
        
        if outcome == PointOutcome.ACE:
            momentum_change = 0.15 if winner == self.serving_player else -0.15
        elif outcome == PointOutcome.DOUBLE_FAULT:
            momentum_change = -0.2 if winner != self.serving_player else 0.2
        else:
            momentum_change = 0.05 if winner == 1 else -0.05
        
        # Apply momentum change with decay
        self.current_momentum = max(-1.0, min(1.0, self.current_momentum * 0.95 + momentum_change))
        
        # Track momentum swings
        if abs(momentum_change) > 0.1:
            self.statistics.momentum_swings += 1
    
    def simulate_game(self) -> int:
        """Simulate a complete game"""
        points = [0, 0]  # [player1_points, player2_points]
        
        while True:
            winner, outcome = self.simulate_point()
            points[winner - 1] += 1
            
            # Check for game win
            if max(points) >= 4 and abs(points[0] - points[1]) >= 2:
                game_winner = 1 if points[0] > points[1] else 2
                break
        
        # Update game statistics
        if game_winner == 1:
            self.statistics.p1_games_won += 1
        else:
            self.statistics.p2_games_won += 1
        
        self.statistics.total_games += 1
        
        # Check for break points
        if self.serving_player != game_winner:
            if game_winner == 1:
                self.statistics.p1_break_points_won += 1
            else:
                self.statistics.p2_break_points_won += 1
        
        return game_winner
    
    def simulate_set(self) -> int:
        """Simulate a complete set"""
        games = [0, 0]  # [player1_games, player2_games]
        
        while True:
            game_winner = self.simulate_game()
            games[game_winner - 1] += 1
            
            # Switch serve
            self.serving_player = 3 - self.serving_player
            
            # Check for set win
            if max(games) >= 6:
                if abs(games[0] - games[1]) >= 2:
                    break
                elif max(games) == 7:  # 7-5 or 7-6 tiebreak
                    break
        
        set_winner = 1 if games[0] > games[1] else 2
        self.current_set_scores.append((games[0], games[1]))
        
        # Update set statistics
        if set_winner == 1:
            self.statistics.p1_sets_won += 1
        else:
            self.statistics.p2_sets_won += 1
        
        self.statistics.sets_played += 1
        
        if self.verbose:
            winner_name = self.player1.name if set_winner == 1 else self.player2.name
            print(f"Set {self.statistics.sets_played} won by {winner_name}: {games[0]}-{games[1]}")
        
        return set_winner
    
    def simulate_match(self) -> Dict[str, Any]:
        """Simulate the complete match"""
        if not self.player1 or not self.player2:
            raise ValueError("Players not set up for simulation")
        
        match_start = datetime.now()
        
        while (self.statistics.p1_sets_won < self.sets_to_win and 
               self.statistics.p2_sets_won < self.sets_to_win):
            
            set_winner = self.simulate_set()
            
            # Apply fatigue between sets
            self._apply_between_set_effects()
        
        # Match complete
        self.match_state = MatchState.MATCH_COMPLETE
        match_duration = (datetime.now() - match_start).seconds // 60
        self.statistics.duration_minutes = match_duration
        
        # Determine match winner
        match_winner = 1 if self.statistics.p1_sets_won > self.statistics.p2_sets_won else 2
        
        # Create result
        result = {
            'winner': match_winner,
            'winner_name': self.player1.name if match_winner == 1 else self.player2.name,
            'final_score': self.current_set_scores,
            'statistics': self.statistics.to_dict(),
            'ai_prediction_accuracy': self._calculate_prediction_accuracy() if self.ai_predictions else None,
            'match_duration_minutes': match_duration
        }
        
        # Update player states after match
        self._update_players_after_match(match_winner, match_duration)
        
        if self.verbose:
            winner_name = self.player1.name if match_winner == 1 else self.player2.name
            print(f"Match won by {winner_name}")
            print(f"Final score: {self.current_set_scores}")
            print(f"Duration: {match_duration} minutes")
        
        return result
    
    def _apply_between_set_effects(self) -> None:
        """Apply fatigue and recovery effects between sets"""
        if self.player1 and self.player2:
            # Apply fatigue
            self.player1.physical_condition.apply_match_fatigue(30, 1)  # Approximate set duration
            self.player2.physical_condition.apply_match_fatigue(30, 1)
            
            # Small recovery during break
            self.player1.physical_condition.rest_recovery(1)  # 1 hour approximation
            self.player2.physical_condition.rest_recovery(1)
    
    def _calculate_prediction_accuracy(self) -> Dict[str, Any]:
        """Calculate how accurate the AI predictions were"""
        if not self.ai_predictions:
            return {}
        
        actual_winner = 1 if self.statistics.p1_sets_won > self.statistics.p2_sets_won else 2
        predicted_winner = self.ai_predictions.winner_prediction
        
        return {
            'winner_correct': actual_winner == predicted_winner,
            'predicted_confidence': self.ai_predictions.win_probability,
            'actual_sets': (self.statistics.p1_sets_won, self.statistics.p2_sets_won),
            'predicted_sets': self.ai_predictions.predicted_sets
        }
    
    def _update_players_after_match(self, winner: int, duration: int) -> None:
        """Update player states after the match"""
        if self.player1 and self.player2:
            match_result1 = "W" if winner == 1 else "L"
            match_result2 = "W" if winner == 2 else "L"
            
            sets_played = self.statistics.sets_played
            opponent_name = self.player2.name if self.player1 else ""
            
            if hasattr(self.player1, 'update_after_match'):
                self.player1.update_after_match(match_result1, duration, sets_played, opponent_name)
            
            if hasattr(self.player2, 'update_after_match'):
                self.player2.update_after_match(match_result2, duration, sets_played, self.player1.name)