"""
Test Suite for Phase 2: Enhanced Models Implementation

This module tests the new enhanced player models, AI prediction engine,
feature engineering pipeline, and enhanced match simulation.
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, List, Any
import json

# Add tennis_api to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.enhanced_player import PlayerEnhanced, PhysicalCondition, MentalState, ContextualFactors
from models.ai_player import PlayerAI, PerformanceContext, MLModel
from models.player_stats import PlayerStats, ServeStatistics, ReturnStatistics
from ml.feature_engineering import FeatureExtractor, FeatureConfig
from ml.prediction_models import OutcomePredictor, ScorePredictor, UpsetDetector
from ml.ensemble import PredictionEnsemble
from simulation.enhanced_match_engine import EnhancedMatchEngine


class TestEnhancedPlayerModels:
    """Test enhanced player models and AI integration"""
    
    def test_enhanced_player_creation(self):
        """Test creating enhanced players with advanced attributes"""
        # Create basic player stats
        serve_stats = ServeStatistics(
            first_serve_percentage=0.65,
            first_serve_win_percentage=0.75,
            second_serve_win_percentage=0.55
        )
        
        return_stats = ReturnStatistics(
            first_serve_return_points_won=0.35,
            second_serve_return_points_won=0.55
        )
        
        player_stats = PlayerStats(
            name="Test Player",
            current_ranking=20,
            serve_stats=serve_stats,
            return_stats=return_stats
        )
        
        # Create enhanced player
        enhanced_player = PlayerEnhanced.from_player_stats(
            player_stats,
            surface_preference="clay",
            playing_style="baseline"
        )
        
        assert enhanced_player.name == "Test Player"
        assert enhanced_player.current_ranking == 20
        assert enhanced_player.surface_preference == "clay"
        assert enhanced_player.api_stats == player_stats
        
        # Test surface multiplier calculation
        clay_multiplier = enhanced_player.get_surface_multiplier("clay")
        hard_multiplier = enhanced_player.get_surface_multiplier("hard")
        
        assert clay_multiplier >= hard_multiplier  # Should prefer clay
        
    def test_ai_player_prediction(self):
        """Test AI player prediction capabilities"""
        # Create AI player
        ai_player = PlayerAI(
            name="AI Test Player",
            current_ranking=10
        )
        
        # Create performance context
        context = PerformanceContext(
            surface="hard",
            opponent_ranking=15,
            tournament_tier="Masters1000",
            pressure_level=0.7
        )
        
        # Test serve prediction (should work even without training)
        serve_pred, serve_conf = ai_player.predict_serve_performance(context)
        
        assert 0.3 <= serve_pred <= 0.95
        assert 0.0 <= serve_conf <= 1.0
        
        # Test mental state prediction
        mental_pred, mental_conf = ai_player.predict_mental_state(0.8, context)
        
        assert isinstance(mental_pred, dict)
        assert 0.0 <= mental_conf <= 1.0
        
    def test_player_state_updates(self):
        """Test dynamic player state updates"""
        player = PlayerEnhanced(
            name="Dynamic Player",
            current_ranking=25
        )
        
        initial_confidence = player.mental_state.confidence_level
        initial_stamina = player.physical_condition.stamina_level
        
        # Simulate match outcome
        player.update_after_match("W", 120, 3, "Opponent")
        
        # Confidence should increase after win
        assert player.mental_state.confidence_level >= initial_confidence
        
        # Stamina should decrease after match
        assert player.physical_condition.stamina_level <= initial_stamina


class TestFeatureEngineering:
    """Test feature engineering pipeline"""
    
    def test_feature_extractor_creation(self):
        """Test creating feature extractor with config"""
        config = FeatureConfig(
            include_ranking_features=True,
            include_form_features=True,
            max_features=30
        )
        
        extractor = FeatureExtractor(config)
        assert extractor.config.max_features == 30
        assert extractor.config.include_ranking_features
        
    def test_ranking_feature_extraction(self):
        """Test ranking feature extraction"""
        extractor = FeatureExtractor()
        
        player1_data = {
            'current_ranking': 5,
            'previous_ranking': 8,
            'seed': 2
        }
        
        player2_data = {
            'current_ranking': 15,
            'previous_ranking': 12,
            'seed': 8
        }
        
        features = extractor.extract_ranking_features(player1_data, player2_data)
        
        assert 'ranking_difference' in features
        assert 'player1_ranking_trend' in features
        assert 'player1_top10' in features
        
        assert features['ranking_difference'] == -10  # 5 - 15
        assert features['player1_ranking_trend'] == 3   # 8 - 5 (improving)
        assert features['player1_top10'] == 1.0
        assert features['player2_top10'] == 0.0
        
    def test_form_feature_extraction(self):
        """Test form feature extraction"""
        extractor = FeatureExtractor()
        
        player1_data = {
            'recent_form_factor': 1.2,
            'recent_matches': ['W', 'W', 'L', 'W', 'W']
        }
        
        player2_data = {
            'recent_form_factor': 0.8,
            'recent_matches': ['L', 'W', 'L', 'L', 'W']
        }
        
        features = extractor.extract_form_features(player1_data, player2_data)
        
        assert 'form_advantage' in features
        assert 'player1_recent_win_rate' in features
        assert 'win_rate_difference' in features
        
        assert features['form_advantage'] == 0.4  # 1.2 - 0.8
        assert features['player1_recent_win_rate'] == 0.8  # 4/5 wins
        assert features['player2_recent_win_rate'] == 0.4  # 2/5 wins
        
    def test_surface_feature_extraction(self):
        """Test surface-specific feature extraction"""
        extractor = FeatureExtractor()
        
        player1_data = {
            'surface_preference': 'clay',
            'surface_stats': {
                'clay': {'win_percentage': 0.8, 'matches_played': 20}
            }
        }
        
        player2_data = {
            'surface_preference': 'hard',
            'surface_stats': {
                'clay': {'win_percentage': 0.6, 'matches_played': 15}
            }
        }
        
        features = extractor.extract_surface_features(player1_data, player2_data, 'clay')
        
        assert 'surface_type' in features
        assert 'player1_surface_match' in features
        assert 'surface_win_rate_diff' in features
        
        assert features['surface_type'] == 1  # clay encoding
        assert features['player1_surface_match'] == 1.0  # prefers clay
        assert features['player2_surface_match'] == 0.0  # prefers hard
        assert features['surface_win_rate_diff'] == 0.2  # 0.8 - 0.6


class TestMLModels:
    """Test machine learning prediction models"""
    
    def test_outcome_predictor_creation(self):
        """Test creating outcome predictor"""
        predictor = OutcomePredictor()
        assert not predictor.is_trained
        assert predictor.config.model_type == "random_forest"
        
    def test_outcome_prediction_fallback(self):
        """Test outcome prediction without training (fallback)"""
        predictor = OutcomePredictor()
        
        # Create dummy features
        features = [0.5] * 20
        
        result = predictor.predict(features)
        
        assert result.prediction in [0, 1]
        assert 0.0 <= result.confidence <= 1.0
        assert result.model_type.value == "outcome"
        
    def test_score_predictor_fallback(self):
        """Test score prediction without training"""
        predictor = ScorePredictor()
        
        features = [0.5] * 20
        result = predictor.predict(features)
        
        assert isinstance(result.prediction, dict)
        assert 'winner_sets' in result.prediction
        assert 'duration_minutes' in result.prediction
        
    def test_upset_detector_fallback(self):
        """Test upset detection without training"""
        detector = UpsetDetector()
        
        features = [0.5] * 20
        ranking_diff = 30  # Lower ranked player facing higher ranked
        
        result = detector.predict(features, ranking_diff)
        
        assert 0.0 <= result.prediction <= 1.0
        assert result.model_type.value == "upset"


class TestPredictionEnsemble:
    """Test AI prediction ensemble"""
    
    def test_ensemble_creation(self):
        """Test creating prediction ensemble"""
        ensemble = PredictionEnsemble()
        assert not ensemble.is_trained
        assert ensemble.outcome_predictor is not None
        assert ensemble.score_predictor is not None
        assert ensemble.upset_detector is not None
        
    def test_ensemble_prediction_fallback(self):
        """Test ensemble prediction without training"""
        ensemble = PredictionEnsemble()
        
        # Create test player data
        player1_data = {
            'name': 'Player 1',
            'current_ranking': 10,
            'recent_form_factor': 1.1
        }
        
        player2_data = {
            'name': 'Player 2', 
            'current_ranking': 25,
            'recent_form_factor': 0.9
        }
        
        match_context = {
            'surface': 'hard',
            'tournament_tier': 'ATP250'
        }
        
        prediction = ensemble.predict_match(player1_data, player2_data, match_context)
        
        assert prediction.winner_prediction in [0, 1]
        assert 0.0 <= prediction.win_probability <= 1.0
        assert isinstance(prediction.predicted_sets, dict)
        assert 0.0 <= prediction.upset_probability <= 1.0
        assert prediction.prediction_risk in ['low', 'medium', 'high']


class TestEnhancedMatchEngine:
    """Test enhanced match simulation engine"""
    
    def test_match_engine_creation(self):
        """Test creating enhanced match engine"""
        engine = EnhancedMatchEngine(
            surface="clay",
            tournament_tier="GrandSlam",
            verbose=False,
            seed=42
        )
        
        assert engine.surface == "clay"
        assert engine.tournament_tier == "GrandSlam"
        assert engine.match_state.value == "pre_match"
        
    def test_match_setup(self):
        """Test setting up a match with enhanced players"""
        engine = EnhancedMatchEngine(seed=42)
        
        # Create test players
        player1 = PlayerEnhanced(
            name="Rafael Nadal",
            current_ranking=2,
            surface_preference="clay"
        )
        
        player2 = PlayerEnhanced(
            name="Novak Djokovic", 
            current_ranking=1,
            surface_preference="hard"
        )
        
        engine.setup_match(player1, player2, sets_to_win=3)
        
        assert engine.player1 == player1
        assert engine.player2 == player2
        assert engine.sets_to_win == 3
        assert engine.match_state.value == "in_progress"
        
    def test_point_simulation(self):
        """Test simulating individual points"""
        engine = EnhancedMatchEngine(seed=42)
        
        player1 = PlayerEnhanced(name="Player 1", current_ranking=10)
        player2 = PlayerEnhanced(name="Player 2", current_ranking=20)
        
        engine.setup_match(player1, player2)
        
        # Simulate a few points
        for _ in range(10):
            winner, outcome = engine.simulate_point()
            assert winner in [1, 2]
            assert outcome in [
                engine.PointOutcome.ACE,
                engine.PointOutcome.DOUBLE_FAULT,
                engine.PointOutcome.WINNER,
                engine.PointOutcome.UNFORCED_ERROR,
                engine.PointOutcome.REGULAR_PLAY
            ]
            
    def test_match_simulation(self):
        """Test complete match simulation"""
        engine = EnhancedMatchEngine(seed=42, verbose=False)
        
        player1 = PlayerEnhanced(
            name="Simulated Player 1",
            current_ranking=15
        )
        
        player2 = PlayerEnhanced(
            name="Simulated Player 2",
            current_ranking=25
        )
        
        engine.setup_match(player1, player2, sets_to_win=2)  # Best of 3
        
        # Simulate complete match
        result = engine.simulate_match()
        
        assert 'winner' in result
        assert result['winner'] in [1, 2]
        assert 'winner_name' in result
        assert 'final_score' in result
        assert 'statistics' in result
        assert 'match_duration_minutes' in result
        
        # Check statistics
        stats = result['statistics']
        assert stats['total_points'] > 0
        assert stats['total_games'] > 0
        assert stats['sets_played'] >= 2
        
        # Verify winner has more sets
        if result['winner'] == 1:
            assert stats['player1']['sets_won'] >= 2
        else:
            assert stats['player2']['sets_won'] >= 2


class TestIntegration:
    """Integration tests for Phase 2 components"""
    
    def test_full_ai_enhanced_simulation(self):
        """Test complete AI-enhanced match simulation"""
        # Create prediction ensemble
        ensemble = PredictionEnsemble()
        
        # Create enhanced match engine with AI
        engine = EnhancedMatchEngine(
            prediction_ensemble=ensemble,
            surface="hard",
            tournament_tier="Masters1000",
            seed=42
        )
        
        # Create enhanced players with API stats
        serve_stats1 = ServeStatistics(
            first_serve_win_percentage=0.78,
            second_serve_win_percentage=0.58
        )
        
        player_stats1 = PlayerStats(
            name="Enhanced Player 1",
            current_ranking=8,
            serve_stats=serve_stats1
        )
        
        player1 = PlayerEnhanced.from_player_stats(player_stats1)
        
        serve_stats2 = ServeStatistics(
            first_serve_win_percentage=0.72,
            second_serve_win_percentage=0.55
        )
        
        player_stats2 = PlayerStats(
            name="Enhanced Player 2", 
            current_ranking=18,
            serve_stats=serve_stats2
        )
        
        player2 = PlayerEnhanced.from_player_stats(player_stats2)
        
        # Setup and simulate match
        engine.setup_match(player1, player2, sets_to_win=2)
        result = engine.simulate_match()
        
        # Verify AI predictions were generated
        assert engine.ai_predictions is not None
        assert hasattr(engine.ai_predictions, 'winner_prediction')
        assert hasattr(engine.ai_predictions, 'win_probability')
        
        # Verify match result
        assert result['winner'] in [1, 2]
        assert result['statistics']['total_points'] > 0
        
        # Check if prediction accuracy was calculated
        if 'ai_prediction_accuracy' in result:
            accuracy = result['ai_prediction_accuracy']
            assert 'winner_correct' in accuracy
            assert isinstance(accuracy['winner_correct'], bool)


def run_phase2_tests():
    """Run all Phase 2 tests"""
    print("Running Phase 2 Enhanced Models Tests...")
    
    # Run tests
    test_classes = [
        TestEnhancedPlayerModels,
        TestFeatureEngineering,
        TestMLModels,
        TestPredictionEnsemble,
        TestEnhancedMatchEngine,
        TestIntegration
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for test_class in test_classes:
        print(f"\n--- Testing {test_class.__name__} ---")
        test_instance = test_class()
        
        # Get all test methods
        test_methods = [method for method in dir(test_instance) if method.startswith('test_')]
        
        for test_method in test_methods:
            total_tests += 1
            try:
                method = getattr(test_instance, test_method)
                method()
                print(f"✓ {test_method}")
                passed_tests += 1
            except Exception as e:
                print(f"✗ {test_method}: {str(e)}")
    
    print(f"\n--- Test Summary ---")
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success rate: {passed_tests/total_tests*100:.1f}%")
    
    return passed_tests == total_tests


if __name__ == "__main__":
    success = run_phase2_tests()
    exit(0 if success else 1)