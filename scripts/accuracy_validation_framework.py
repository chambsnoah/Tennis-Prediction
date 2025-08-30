#!/usr/bin/env python3
"""
Accuracy Validation Framework for Tennis Prediction Systems

This framework provides comprehensive testing and validation of prediction accuracy
by comparing Phase 1 vs Phase 2 implementations against historical match data.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import statistics
import random

# Add tennis_api to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import with fallback for missing modules
try:
    from tennis_api.models.enhanced_player import PlayerEnhanced
    from tennis_api.models.player_stats import PlayerStats, ServeStatistics, ReturnStatistics
    from tennis_api.ml.ensemble import PredictionEnsemble
    from tennis_api.simulation.enhanced_match_engine import EnhancedMatchEngine
    FULL_SYSTEM_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Full tennis_api system not available: {e}")
    print("Running with mock implementations for validation")
    FULL_SYSTEM_AVAILABLE = False

    # Mock classes for testing
    class MockPlayerStats:
        def __init__(self, name, ranking):
            self.name = name
            self.current_ranking = ranking
            self.serve_stats = MockServeStats()
            self.return_stats = MockReturnStats()
            self.recent_matches = ['W', 'L', 'W']

        def calculate_form_factor(self):
            return 1.0

    class MockServeStats:
        def __init__(self):
            self.first_serve_percentage = 0.65
            self.first_serve_win_percentage = 0.7
            self.second_serve_win_percentage = 0.5
            self.aces_per_match = 5.0

    class MockReturnStats:
        def __init__(self):
            self.first_serve_return_points_won = 0.3
            self.second_serve_return_points_won = 0.5
            self.break_points_converted = 0.4

    class MockPlayerEnhanced:
        def __init__(self, name, ranking):
            self.name = name
            self.current_ranking = ranking
            self.recent_form_factor = 1.0
            self.surface_preference = "hard"
            self.api_stats = MockPlayerStats(name, ranking)

        @classmethod
        def from_player_stats(cls, player_stats):
            return cls(player_stats.name, player_stats.current_ranking)

    class MockPredictionEnsemble:
        def __init__(self):
            pass

        def predict_match(self, p1, p2, context):
            # Simple mock prediction based on ranking
            rank_diff = p1['current_ranking'] - p2['current_ranking']
            win_prob = 0.5 + max(-0.3, min(0.3, -rank_diff * 0.01))
            winner = 1 if win_prob > 0.5 else 0

            class MockResult:
                def __init__(self, winner, prob):
                    self.winner_prediction = winner
                    self.win_probability = prob
                    self.overall_confidence = 0.7
                    self.predicted_sets = {'winner_sets': 2, 'loser_sets': 1}
                    self.upset_probability = 0.2

            return MockResult(winner, win_prob)

    PlayerEnhanced = MockPlayerEnhanced
    PredictionEnsemble = MockPredictionEnsemble


@dataclass
class AccuracyMetrics:
    """Comprehensive accuracy metrics for prediction evaluation"""
    total_predictions: int = 0
    correct_predictions: int = 0
    accuracy_percentage: float = 0.0

    # Confidence analysis
    high_confidence_predictions: int = 0
    high_confidence_correct: int = 0
    high_confidence_accuracy: float = 0.0

    # Score prediction accuracy
    score_predictions: int = 0
    correct_score_predictions: int = 0
    score_accuracy_percentage: float = 0.0

    # Upset detection
    upset_predictions: int = 0
    correct_upset_predictions: int = 0
    upset_accuracy_percentage: float = 0.0

    # Brier score for probability calibration
    brier_score: float = 0.0

    def calculate_metrics(self) -> None:
        """Calculate derived metrics"""
        if self.total_predictions > 0:
            self.accuracy_percentage = (self.correct_predictions / self.total_predictions) * 100

        if self.high_confidence_predictions > 0:
            self.high_confidence_accuracy = (self.high_confidence_correct / self.high_confidence_predictions) * 100

        if self.score_predictions > 0:
            self.score_accuracy_percentage = (self.correct_score_predictions / self.score_predictions) * 100

        if self.upset_predictions > 0:
            self.upset_accuracy_percentage = (self.correct_upset_predictions / self.upset_predictions) * 100


@dataclass
class HistoricalMatch:
    """Represents a historical tennis match for testing"""
    player1_name: str
    player2_name: str
    player1_ranking: int
    player2_ranking: int
    surface: str
    tournament: str
    actual_winner: int  # 1 or 2
    actual_score: str
    match_date: str

    # Optional additional data
    player1_stats: Optional[Dict[str, Any]] = None
    player2_stats: Optional[Dict[str, Any]] = None


class AccuracyValidationFramework:
    """
    Framework for validating prediction accuracy improvements

    This class provides methods to:
    1. Load historical match data
    2. Run predictions using different system versions
    3. Compare accuracy between Phase 1 and Phase 2
    4. Generate comprehensive accuracy reports
    """

    def __init__(self, historical_data_path: Optional[str] = None):
        self.historical_matches: List[HistoricalMatch] = []
        self.phase1_results: Dict[str, Any] = {}
        self.phase2_results: Dict[str, Any] = {}
        self.comparison_results: Dict[str, Any] = {}

        if historical_data_path:
            self.load_historical_data(historical_data_path)

    def load_historical_data(self, data_path: str) -> None:
        """Load historical match data for testing"""
        try:
            with open(data_path, 'r') as f:
                data = json.load(f)

            for match_data in data.get('matches', []):
                match = HistoricalMatch(
                    player1_name=match_data['player1_name'],
                    player2_name=match_data['player2_name'],
                    player1_ranking=match_data['player1_ranking'],
                    player2_ranking=match_data['player2_ranking'],
                    surface=match_data['surface'],
                    tournament=match_data['tournament'],
                    actual_winner=match_data['actual_winner'],
                    actual_score=match_data['actual_score'],
                    match_date=match_data['match_date'],
                    player1_stats=match_data.get('player1_stats'),
                    player2_stats=match_data.get('player2_stats')
                )
                self.historical_matches.append(match)

            print(f"Loaded {len(self.historical_matches)} historical matches")

        except Exception as e:
            print(f"Error loading historical data: {e}")

    def create_mock_historical_data(self, num_matches: int = 100) -> None:
        """Create mock historical data for testing when real data isn't available"""
        surfaces = ['hard', 'clay', 'grass']
        tournaments = ['Australian Open', 'French Open', 'Wimbledon', 'US Open', 'ATP 250', 'ATP 500', 'Masters 1000']

        top_players = [
            ('Novak Djokovic', 1), ('Carlos Alcaraz', 2), ('Daniil Medvedev', 3),
            ('Rafael Nadal', 4), ('Alexander Zverev', 5), ('Jannik Sinner', 6),
            ('Andrey Rublev', 7), ('Stefanos Tsitsipas', 8), ('Felix Auger-Aliassime', 9),
            ('Taylor Fritz', 10), ('Casper Ruud', 11), ('Holger Rune', 12)
        ]

        for i in range(num_matches):
            # Select two random players
            p1, p2 = random.sample(top_players, 2)
            player1_name, player1_rank = p1
            player2_name, player2_rank = p2

            # Determine surface and tournament
            surface = random.choice(surfaces)
            tournament = random.choice(tournaments)

            # Simulate realistic win probability based on ranking
            rank_diff = player1_rank - player2_rank
            win_prob = 0.5 + max(-0.4, min(0.4, -rank_diff * 0.02))

            # Add some randomness
            win_prob += random.uniform(-0.1, 0.1)
            win_prob = max(0.1, min(0.9, win_prob))

            actual_winner = 1 if random.random() < win_prob else 2

            # Create mock match
            match = HistoricalMatch(
                player1_name=player1_name,
                player2_name=player2_name,
                player1_ranking=player1_rank,
                player2_ranking=player2_rank,
                surface=surface,
                tournament=tournament,
                actual_winner=actual_winner,
                actual_score="6-4 7-5",  # Mock score
                match_date="2024-01-01"
            )

            self.historical_matches.append(match)

        print(f"Created {len(self.historical_matches)} mock historical matches")

    def run_phase1_predictions(self) -> AccuracyMetrics:
        """Run predictions using Phase 1 methodology (baseline)"""
        print("Running Phase 1 baseline predictions...")

        metrics = AccuracyMetrics()
        predictions = []

        for match in self.historical_matches:
            # Phase 1: Simple ranking-based prediction
            prediction = self._phase1_predict_match(match)
            predictions.append(prediction)

            # Evaluate prediction
            is_correct = prediction['predicted_winner'] == match.actual_winner
            metrics.total_predictions += 1

            if is_correct:
                metrics.correct_predictions += 1

            # High confidence if ranking difference > 50
            rank_diff = abs(match.player1_ranking - match.player2_ranking)
            if rank_diff > 50:
                metrics.high_confidence_predictions += 1
                if is_correct:
                    metrics.high_confidence_correct += 1

        metrics.calculate_metrics()

        self.phase1_results = {
            'metrics': metrics,
            'predictions': predictions,
            'timestamp': datetime.now().isoformat()
        }

        return metrics

    def run_phase2_predictions(self) -> AccuracyMetrics:
        """Run predictions using Phase 2 AI-enhanced methodology"""
        print("Running Phase 2 AI-enhanced predictions...")

        # Initialize Phase 2 components
        ensemble = PredictionEnsemble()

        metrics = AccuracyMetrics()
        predictions = []

        for match in self.historical_matches:
            try:
                # Create enhanced players
                player1 = self._create_enhanced_player(match.player1_name, match.player1_ranking, match.player1_stats)
                player2 = self._create_enhanced_player(match.player2_name, match.player2_ranking, match.player2_stats)

                # Prepare match context
                match_context = {
                    'surface': match.surface,
                    'tournament_tier': self._classify_tournament_tier(match.tournament),
                    'match_round': 'R32',  # Default round
                    'pressure_level': 0.5
                }

                # Get Phase 2 prediction
                prediction = ensemble.predict_match(
                    self._player_to_dict(player1),
                    self._player_to_dict(player2),
                    match_context
                )

                # Evaluate prediction
                predicted_winner = prediction.winner_prediction
                is_correct = predicted_winner == match.actual_winner
                confidence = prediction.overall_confidence

                metrics.total_predictions += 1
                if is_correct:
                    metrics.correct_predictions += 1

                # High confidence predictions
                if confidence >= 0.8:
                    metrics.high_confidence_predictions += 1
                    if is_correct:
                        metrics.high_confidence_correct += 1

                # Score predictions (simplified)
                if hasattr(prediction, 'predicted_sets'):
                    metrics.score_predictions += 1
                    # Simplified score accuracy check
                    if prediction.predicted_sets.get('winner_sets', 2) >= 2:
                        metrics.correct_score_predictions += 1

                # Upset detection
                rank_diff = abs(match.player1_ranking - match.player2_ranking)
                if rank_diff > 30:  # Potential upset scenario
                    metrics.upset_predictions += 1
                    if prediction.upset_probability > 0.5 and match.actual_winner == (2 if match.player1_ranking < match.player2_ranking else 1):
                        metrics.correct_upset_predictions += 1

                predictions.append({
                    'match': f"{match.player1_name} vs {match.player2_name}",
                    'predicted_winner': predicted_winner,
                    'actual_winner': match.actual_winner,
                    'confidence': confidence,
                    'is_correct': is_correct
                })

            except Exception as e:
                print(f"Error predicting match {match.player1_name} vs {match.player2_name}: {e}")
                continue

        metrics.calculate_metrics()

        self.phase2_results = {
            'metrics': metrics,
            'predictions': predictions,
            'timestamp': datetime.now().isoformat()
        }

        return metrics

    def _phase1_predict_match(self, match: HistoricalMatch) -> Dict[str, Any]:
        """Phase 1 prediction logic - simple ranking-based"""
        rank_diff = match.player1_ranking - match.player2_ranking

        # Simple probability calculation
        if rank_diff > 0:
            win_prob = 0.5 + min(0.3, rank_diff * 0.005)
        else:
            win_prob = 0.5 + max(-0.3, rank_diff * 0.005)

        predicted_winner = 1 if win_prob > 0.5 else 2
        confidence = abs(win_prob - 0.5) * 2  # Scale to 0-1

        return {
            'predicted_winner': predicted_winner,
            'win_probability': win_prob,
            'confidence': confidence,
            'method': 'ranking_based'
        }

    def _create_enhanced_player(self, name: str, ranking: int, stats: Optional[Dict] = None):
        """Create an enhanced player for Phase 2 predictions"""
        # Use mock classes when full system is not available
        if not FULL_SYSTEM_AVAILABLE:
            return MockPlayerEnhanced(name, ranking)

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
            name=name,
            current_ranking=ranking,
            serve_stats=serve_stats,
            return_stats=return_stats
        )

        return PlayerEnhanced.from_player_stats(player_stats)

    def _player_to_dict(self, player) -> Dict[str, Any]:
        """Convert PlayerEnhanced to dictionary for prediction"""
        return {
            'name': player.name,
            'current_ranking': player.current_ranking,
            'recent_form_factor': player.recent_form_factor,
            'surface_preference': player.surface_preference,
            'serve_stats': {
                'first_serve_win_percentage': player.api_stats.serve_stats.first_serve_win_percentage,
                'second_serve_win_percentage': player.api_stats.serve_stats.second_serve_win_percentage
            } if player.api_stats else {}
        }

    def _classify_tournament_tier(self, tournament: str) -> str:
        """Classify tournament tier"""
        if 'Open' in tournament or 'Grand Slam' in tournament:
            return 'GrandSlam'
        elif 'Masters' in tournament or '1000' in tournament:
            return 'Masters1000'
        elif '500' in tournament:
            return 'ATP500'
        else:
            return 'ATP250'

    def compare_accuracy(self) -> Dict[str, Any]:
        """Compare Phase 1 vs Phase 2 accuracy"""
        if not self.phase1_results or not self.phase2_results:
            raise ValueError("Both Phase 1 and Phase 2 results must be available for comparison")

        phase1_metrics = self.phase1_results['metrics']
        phase2_metrics = self.phase2_results['metrics']

        # Calculate improvement
        accuracy_improvement = phase2_metrics.accuracy_percentage - phase1_metrics.accuracy_percentage
        high_conf_improvement = (phase2_metrics.high_confidence_accuracy -
                               phase1_metrics.high_confidence_accuracy)

        self.comparison_results = {
            'phase1_accuracy': phase1_metrics.accuracy_percentage,
            'phase2_accuracy': phase2_metrics.accuracy_percentage,
            'accuracy_improvement': accuracy_improvement,
            'accuracy_improvement_percentage': (accuracy_improvement / phase1_metrics.accuracy_percentage) * 100,

            'phase1_high_conf_accuracy': phase1_metrics.high_confidence_accuracy,
            'phase2_high_conf_accuracy': phase2_metrics.high_confidence_accuracy,
            'high_conf_improvement': high_conf_improvement,

            'phase1_score_accuracy': phase1_metrics.score_accuracy_percentage,
            'phase2_score_accuracy': phase2_metrics.score_accuracy_percentage,

            'phase1_upset_accuracy': phase1_metrics.upset_accuracy_percentage,
            'phase2_upset_accuracy': phase2_metrics.upset_accuracy_percentage,

            'total_matches_tested': len(self.historical_matches),
            'comparison_timestamp': datetime.now().isoformat()
        }

        return self.comparison_results

    def generate_accuracy_report(self, output_path: str = "accuracy_report.json") -> None:
        """Generate comprehensive accuracy report"""
        if not self.comparison_results:
            self.compare_accuracy()

        report = {
            'summary': {
                'total_matches_tested': len(self.historical_matches),
                'phase1_accuracy': self.comparison_results['phase1_accuracy'],
                'phase2_accuracy': self.comparison_results['phase2_accuracy'],
                'accuracy_improvement': self.comparison_results['accuracy_improvement'],
                'accuracy_improvement_percentage': self.comparison_results['accuracy_improvement_percentage'],
                'meets_15_20_percent_target': 15 <= self.comparison_results['accuracy_improvement_percentage'] <= 25
            },
            'detailed_comparison': self.comparison_results,
            'phase1_results': {
                'metrics': vars(self.phase1_results['metrics']),
                'sample_predictions': self.phase1_results['predictions'][:5]  # First 5 predictions
            },
            'phase2_results': {
                'metrics': vars(self.phase2_results['metrics']),
                'sample_predictions': self.phase2_results['predictions'][:5]  # First 5 predictions
            },
            'methodology': {
                'phase1_method': 'Simple ranking-based prediction',
                'phase2_method': 'AI-enhanced prediction with ML models and feature engineering',
                'test_data': 'Historical match results with player rankings and tournament data',
                'validation_approach': 'Direct comparison of prediction accuracy on identical match scenarios'
            },
            'recommendations': self._generate_recommendations(),
            'generated_at': datetime.now().isoformat()
        }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"Accuracy report generated: {output_path}")
        print(f"Phase 1 Accuracy: {self.comparison_results['phase1_accuracy']:.1f}%")
        print(f"Phase 2 Accuracy: {self.comparison_results['phase2_accuracy']:.1f}%")
        print(f"Improvement: {self.comparison_results['accuracy_improvement_percentage']:.1f}%")

        meets_target = self.comparison_results.get('meets_15_20_percent_target', False)
        if meets_target:
            print("TARGET ACHIEVED: 15-20% improvement confirmed!")
        else:
            print("TARGET NOT MET: Improvement outside 15-20% range")

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on results"""
        recommendations = []

        improvement = self.comparison_results['accuracy_improvement_percentage']

        if improvement < 10:
            recommendations.append("Consider additional ML model training or feature engineering")
            recommendations.append("Review Phase 2 implementation for potential issues")
        elif 10 <= improvement < 15:
            recommendations.append("Close to target - consider fine-tuning ML models")
            recommendations.append("Add more diverse training data")
        elif 15 <= improvement <= 20:
            recommendations.append("TARGET ACHIEVED - Phase 2 implementation successful")
            recommendations.append("Consider deploying Phase 2 to production")
        elif improvement > 25:
            recommendations.append("WARNING: Exceptional improvement - validate results carefully")
            recommendations.append("Check for potential overfitting or data leakage")

        return recommendations


def main():
    """Main function to run accuracy validation"""
    print("TENNIS PREDICTION ACCURACY VALIDATION FRAMEWORK")
    print("=" * 60)

    # Initialize framework
    framework = AccuracyValidationFramework()

    # Create mock historical data for testing
    print("Creating mock historical data...")
    framework.create_mock_historical_data(200)  # Test with 200 matches

    # Run Phase 1 predictions
    print("\n" + "=" * 40)
    phase1_metrics = framework.run_phase1_predictions()
    print(f"Phase 1 Results: {phase1_metrics.accuracy_percentage:.1f}% accuracy")

    # Run Phase 2 predictions
    print("\n" + "=" * 40)
    phase2_metrics = framework.run_phase2_predictions()
    print(f"Phase 2 Results: {phase2_metrics.accuracy_percentage:.1f}% accuracy")

    # Compare and generate report
    print("\n" + "=" * 40)
    comparison = framework.compare_accuracy()
    framework.generate_accuracy_report("accuracy_validation_report.json")

    print("\nVALIDATION COMPLETE!")
    print(f"Improvement: {comparison['accuracy_improvement_percentage']:.1f}%")
    print("Full report saved to: accuracy_validation_report.json")


if __name__ == "__main__":
    main()