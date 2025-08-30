"""
Phase 2: Enhanced Models Demonstration

This script demonstrates the advanced AI-powered tennis prediction capabilities
implemented in Phase 2, including enhanced player models, feature engineering,
ML predictions, and AI-enhanced match simulation.
"""

import sys
from pathlib import Path
import json
from datetime import datetime

# Add tennis_api to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tennis_api.models.enhanced_player import PlayerEnhanced, ContextualFactors
from tennis_api.models.ai_player import PlayerAI, PerformanceContext
from tennis_api.models.player_stats import PlayerStats, ServeStatistics, ReturnStatistics, SurfaceStats
from tennis_api.ml.feature_engineering import FeatureExtractor, FeatureConfig
from tennis_api.ml.prediction_models import OutcomePredictor, ScorePredictor, UpsetDetector
from tennis_api.ml.ensemble import PredictionEnsemble, EnsembleConfig
from tennis_api.simulation.enhanced_match_engine import EnhancedMatchEngine


def create_sample_players():
    """Create sample enhanced players with realistic data"""
    
    # Create Rafael Nadal-like player
    nadal_serve_stats = ServeStatistics(
        first_serve_percentage=0.68,
        first_serve_win_percentage=0.75,
        second_serve_win_percentage=0.60,
        aces_per_match=3.2,
        double_faults_per_match=1.8
    )
    
    nadal_return_stats = ReturnStatistics(
        first_serve_return_points_won=0.33,
        second_serve_return_points_won=0.58,
        break_points_converted=0.45
    )
    
    nadal_clay_stats = SurfaceStats(
        surface="clay",
        wins=150,
        losses=8,
        serve_percentage=0.78,
        return_percentage=0.42
    )
    
    nadal_hard_stats = SurfaceStats(
        surface="hard",
        wins=85,
        losses=25,
        serve_percentage=0.72,
        return_percentage=0.36
    )
    
    nadal_stats = PlayerStats(
        name="Rafael Nadal",
        current_ranking=2,
        nationality="Spain",
        age=37,
        height_cm=185,
        weight_kg=85,
        serve_stats=nadal_serve_stats,
        return_stats=nadal_return_stats,
        surface_stats={"clay": nadal_clay_stats, "hard": nadal_hard_stats},
        recent_matches=["W", "W", "W", "L", "W", "W", "W", "W", "W", "W"]
    )
    
    nadal = PlayerEnhanced.from_player_stats(
        nadal_stats,
        surface_preference="clay",
        playing_style="baseline",
        dominant_hand="left"
    )
    
    # Create Novak Djokovic-like player
    djokovic_serve_stats = ServeStatistics(
        first_serve_percentage=0.72,
        first_serve_win_percentage=0.74,
        second_serve_win_percentage=0.59,
        aces_per_match=4.1,
        double_faults_per_match=1.9
    )
    
    djokovic_return_stats = ReturnStatistics(
        first_serve_return_points_won=0.32,
        second_serve_return_points_won=0.56,
        break_points_converted=0.43
    )
    
    djokovic_hard_stats = SurfaceStats(
        surface="hard",
        wins=120,
        losses=15,
        serve_percentage=0.76,
        return_percentage=0.38
    )
    
    djokovic_clay_stats = SurfaceStats(
        surface="clay",
        wins=95,
        losses=20,
        serve_percentage=0.72,
        return_percentage=0.36
    )
    
    djokovic_stats = PlayerStats(
        name="Novak Djokovic",
        current_ranking=1,
        nationality="Serbia",
        age=36,
        height_cm=188,
        weight_kg=80,
        serve_stats=djokovic_serve_stats,
        return_stats=djokovic_return_stats,
        surface_stats={"hard": djokovic_hard_stats, "clay": djokovic_clay_stats},
        recent_matches=["W", "W", "L", "W", "W", "W", "W", "L", "W", "W"]
    )
    
    djokovic = PlayerEnhanced.from_player_stats(
        djokovic_stats,
        surface_preference="hard",
        playing_style="all_court",
        dominant_hand="right"
    )
    
    return nadal, djokovic


def demonstrate_enhanced_players():
    """Demonstrate enhanced player capabilities"""
    print("=" * 60)
    print("PHASE 2: ENHANCED PLAYER MODELS DEMONSTRATION")
    print("=" * 60)
    
    nadal, djokovic = create_sample_players()
    
    print(f"\n1. ENHANCED PLAYER ANALYSIS")
    print(f"   Player 1: {nadal.name} (Ranking: {nadal.current_ranking})")
    print(f"   Player 2: {djokovic.name} (Ranking: {djokovic.current_ranking})")
    
    # Demonstrate surface adjustments
    print(f"\n2. SURFACE-SPECIFIC PERFORMANCE")
    surfaces = ["clay", "hard", "grass"]
    
    for surface in surfaces:
        nadal_mult = nadal.get_surface_multiplier(surface)
        djokovic_mult = djokovic.get_surface_multiplier(surface)
        
        print(f"   {surface.upper():6}: Nadal={nadal_mult:.3f}, Djokovic={djokovic_mult:.3f}")
    
    # Demonstrate dynamic serve adjustment
    print(f"\n3. DYNAMIC SERVE PERFORMANCE (on clay)")
    nadal_serve_clay = nadal.get_adjusted_serve_percentage("clay", djokovic.current_ranking)
    djokovic_serve_clay = djokovic.get_adjusted_serve_percentage("clay", nadal.current_ranking)
    
    print(f"   Nadal serve %: {nadal_serve_clay:.3f}")
    print(f"   Djokovic serve %: {djokovic_serve_clay:.3f}")
    
    # Demonstrate form factors
    print(f"\n4. RECENT FORM ANALYSIS")
    nadal_form = nadal.calculate_form_factor()
    djokovic_form = djokovic.calculate_form_factor()
    
    print(f"   Nadal form factor: {nadal_form:.3f}")
    print(f"   Djokovic form factor: {djokovic_form:.3f}")
    
    return nadal, djokovic


def demonstrate_feature_engineering():
    """Demonstrate feature engineering pipeline"""
    print(f"\n5. FEATURE ENGINEERING PIPELINE")
    print("-" * 40)
    
    nadal, djokovic = create_sample_players()
    
    # Create feature extractor
    config = FeatureConfig(
        include_ranking_features=True,
        include_form_features=True,
        include_surface_features=True,
        include_statistical_features=True,
        max_features=25
    )
    
    extractor = FeatureExtractor(config)
    
    # Prepare player data
    player1_data = {
        'name': nadal.name,
        'current_ranking': nadal.current_ranking,
        'recent_form_factor': nadal.recent_form_factor,
        'surface_preference': nadal.surface_preference,
        'serve_stats': {
            'first_serve_win_percentage': nadal.api_stats.serve_stats.first_serve_win_percentage,
            'second_serve_win_percentage': nadal.api_stats.serve_stats.second_serve_win_percentage,
            'aces_per_match': nadal.api_stats.serve_stats.aces_per_match
        },
        'return_stats': {
            'first_serve_return_points_won': nadal.api_stats.return_stats.first_serve_return_points_won,
            'break_points_converted': nadal.api_stats.return_stats.break_points_converted
        },
        'recent_matches': nadal.api_stats.recent_matches,
        'surface_stats': {surface: stats.to_dict() for surface, stats in nadal.api_stats.surface_stats.items()}
    }
    
    player2_data = {
        'name': djokovic.name,
        'current_ranking': djokovic.current_ranking,
        'recent_form_factor': djokovic.recent_form_factor,
        'surface_preference': djokovic.surface_preference,
        'serve_stats': {
            'first_serve_win_percentage': djokovic.api_stats.serve_stats.first_serve_win_percentage,
            'second_serve_win_percentage': djokovic.api_stats.serve_stats.second_serve_win_percentage,
            'aces_per_match': djokovic.api_stats.serve_stats.aces_per_match
        },
        'return_stats': {
            'first_serve_return_points_won': djokovic.api_stats.return_stats.first_serve_return_points_won,
            'break_points_converted': djokovic.api_stats.return_stats.break_points_converted
        },
        'recent_matches': djokovic.api_stats.recent_matches,
        'surface_stats': {surface: stats.to_dict() for surface, stats in djokovic.api_stats.surface_stats.items()}
    }
    
    match_context = {
        'surface': 'clay',
        'tournament_tier': 'GrandSlam',
        'match_round': 'SF',
        'weather_temp': 25.0,
        'pressure_level': 0.8
    }
    
    # Extract features
    features = extractor.extract_all_features(player1_data, player2_data, match_context)
    
    print(f"   Extracted {len(features)} features:")
    
    # Show key features
    key_features = [
        'ranking_difference', 'form_advantage', 'surface_preference_advantage',
        'first_serve_advantage', 'return_advantage', 'surface_win_rate_diff'
    ]
    
    for feature in key_features:
        if feature in features:
            print(f"   {feature:25}: {features[feature]:7.3f}")
    
    return features


def demonstrate_ml_predictions():
    """Demonstrate ML prediction models"""
    print(f"\n6. MACHINE LEARNING PREDICTIONS")
    print("-" * 40)
    
    # Create dummy feature vector (in real scenario, this would come from feature engineering)
    features = [0.1, 0.2, 0.15, 0.8, 0.6, 0.75, 0.55, 1.2, 0.9, 0.3] * 2  # 20 features
    
    # Test individual models (without training - showing fallback behavior)
    outcome_predictor = OutcomePredictor()
    score_predictor = ScorePredictor()
    upset_detector = UpsetDetector()
    
    # Outcome prediction
    outcome_result = outcome_predictor.predict(features)
    winner_name = "Nadal" if outcome_result.prediction == 1 else "Djokovic"
    print(f"   Match Winner: {winner_name} (Confidence: {outcome_result.confidence:.3f})")
    
    # Score prediction
    score_result = score_predictor.predict(features)
    score_pred = score_result.prediction
    print(f"   Predicted Sets: {score_pred['winner_sets']}-{score_pred['loser_sets']}")
    print(f"   Est. Duration: {score_pred['duration_minutes']} minutes")
    
    # Upset detection
    ranking_diff = -1  # Nadal ranked lower (upset potential)
    upset_result = upset_detector.predict(features, ranking_diff)
    print(f"   Upset Probability: {upset_result.prediction:.3f}")
    
    return outcome_result, score_result, upset_result


def demonstrate_ai_ensemble():
    """Demonstrate AI prediction ensemble"""
    print(f"\n7. AI PREDICTION ENSEMBLE")
    print("-" * 40)
    
    nadal, djokovic = create_sample_players()
    
    # Create prediction ensemble
    ensemble_config = EnsembleConfig(
        min_confidence_threshold=0.6,
        outcome_weight=0.4,
        score_weight=0.3,
        upset_weight=0.3
    )
    
    ensemble = PredictionEnsemble(ensemble_config)
    
    # Prepare player data for ensemble
    player1_data = {
        'name': nadal.name,
        'current_ranking': nadal.current_ranking,
        'recent_form_factor': nadal.recent_form_factor,
        'serve_stats': {
            'first_serve_win_percentage': 0.75,
            'aces_per_match': 3.2
        },
        'return_stats': {
            'first_serve_return_points_won': 0.33
        }
    }
    
    player2_data = {
        'name': djokovic.name,
        'current_ranking': djokovic.current_ranking,
        'recent_form_factor': djokovic.recent_form_factor,
        'serve_stats': {
            'first_serve_win_percentage': 0.74,
            'aces_per_match': 4.1
        },
        'return_stats': {
            'first_serve_return_points_won': 0.32
        }
    }
    
    match_context = {
        'surface': 'clay',
        'tournament_tier': 'GrandSlam',
        'match_round': 'SF',
        'pressure_level': 0.8
    }
    
    # Generate ensemble prediction
    prediction = ensemble.predict_match(player1_data, player2_data, match_context)
    
    print(f"   COMPREHENSIVE PREDICTION:")
    winner_name = nadal.name if prediction.winner_prediction == 1 else djokovic.name
    print(f"   Winner: {winner_name}")
    print(f"   Win Probability: {prediction.win_probability:.3f}")
    print(f"   Predicted Score: {prediction.predicted_sets}")
    print(f"   Upset Risk: {prediction.upset_probability:.3f}")
    print(f"   Overall Confidence: {prediction.overall_confidence:.3f}")
    print(f"   Prediction Risk: {prediction.prediction_risk}")
    
    return prediction


def demonstrate_enhanced_simulation():
    """Demonstrate enhanced match simulation"""
    print(f"\n8. AI-ENHANCED MATCH SIMULATION")
    print("-" * 40)
    
    nadal, djokovic = create_sample_players()
    
    # Create ensemble for AI predictions
    ensemble = PredictionEnsemble()
    
    # Create enhanced match engine with AI
    engine = EnhancedMatchEngine(
        prediction_ensemble=ensemble,
        surface="clay",
        tournament_tier="GrandSlam",
        verbose=False,
        seed=42
    )
    
    # Setup match
    engine.setup_match(nadal, djokovic, sets_to_win=3, player1_serves_first=True)
    
    print(f"   Match Setup: {nadal.name} vs {djokovic.name}")
    print(f"   Surface: {engine.surface}")
    print(f"   Tournament: {engine.tournament_tier}")
    
    # Show AI prediction
    if engine.ai_predictions:
        pred_winner = nadal.name if engine.ai_predictions.winner_prediction == 1 else djokovic.name
        print(f"   AI Prediction: {pred_winner} ({engine.ai_predictions.win_probability:.1%})")
    
    # Simulate match
    print(f"\n   Simulating match...")
    result = engine.simulate_match()
    
    # Display results
    print(f"\n   MATCH RESULT:")
    print(f"   Winner: {result['winner_name']}")
    print(f"   Final Score: {result['final_score']}")
    print(f"   Duration: {result['match_duration_minutes']} minutes")
    
    # Show detailed statistics
    stats = result['statistics']
    print(f"\n   MATCH STATISTICS:")
    print(f"   Total Points: {stats['total_points']}")
    print(f"   Total Games: {stats['total_games']}")
    print(f"   Sets Played: {stats['sets_played']}")
    
    player_stats = [stats['player1'], stats['player2']]
    players = [nadal, djokovic]
    
    for i, (player, pstats) in enumerate(zip(players, player_stats)):
        print(f"\n   {player.name}:")
        print(f"     Points Won: {pstats['points_won']}")
        print(f"     Games Won: {pstats['games_won']}")
        print(f"     Sets Won: {pstats['sets_won']}")
        print(f"     Aces: {pstats['aces']}")
        print(f"     Double Faults: {pstats['double_faults']}")
        print(f"     Break Points Won: {pstats['break_points_won']}")
    
    # Show AI prediction accuracy if available
    if 'ai_prediction_accuracy' in result and result['ai_prediction_accuracy']:
        accuracy = result['ai_prediction_accuracy']
        print(f"\n   AI PREDICTION ACCURACY:")
        print(f"   Winner Correct: {accuracy['winner_correct']}")
        print(f"   Predicted Confidence: {accuracy['predicted_confidence']:.3f}")
    
    return result


def main():
    """Run complete Phase 2 demonstration"""
    print("🎾 TENNIS AI PREDICTION SYSTEM - PHASE 2 DEMONSTRATION 🎾")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Demonstrate all Phase 2 capabilities
        nadal, djokovic = demonstrate_enhanced_players()
        features = demonstrate_feature_engineering()
        ml_results = demonstrate_ml_predictions()
        ensemble_prediction = demonstrate_ai_ensemble()
        match_result = demonstrate_enhanced_simulation()
        
        print(f"\n" + "=" * 60)
        print("PHASE 2 DEMONSTRATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        
        print(f"\nKey Achievements:")
        print(f"✅ Enhanced Player Models with AI integration")
        print(f"✅ Advanced Feature Engineering Pipeline")
        print(f"✅ Machine Learning Prediction Models")
        print(f"✅ AI Prediction Ensemble System")
        print(f"✅ Enhanced Match Simulation Engine")
        print(f"✅ Dynamic State Management")
        print(f"✅ Real-time Factor Adjustments")
        
        # Summary statistics
        print(f"\nDemo Statistics:")
        print(f"• Features Extracted: {len(features)}")
        print(f"• ML Models Tested: 3 (Outcome, Score, Upset)")
        print(f"• Ensemble Confidence: {ensemble_prediction.overall_confidence:.3f}")
        print(f"• Simulation Duration: {match_result['match_duration_minutes']} min")
        print(f"• Total Points Simulated: {match_result['statistics']['total_points']}")
        
    except Exception as e:
        print(f"\n❌ Error during demonstration: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    print(f"\nDemonstration {'completed successfully' if success else 'failed'}!")
    exit(0 if success else 1)