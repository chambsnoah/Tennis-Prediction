"""
AI Prediction Engine and Model Ensemble

This module implements the comprehensive AI prediction engine that combines
multiple ML models to provide accurate tennis match predictions with
confidence scoring and detailed explanations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Union
import numpy as np
import json
from datetime import datetime
from enum import Enum
import statistics

from .prediction_models import OutcomePredictor, ScorePredictor, UpsetDetector, PredictionResult, ModelType
from .feature_engineering import FeatureExtractor, FeatureConfig
from ..models.enhanced_player import PlayerEnhanced, PerformanceContext


class EnsembleMethod(Enum):
    """Ensemble combination methods"""
    WEIGHTED_AVERAGE = "weighted_average"
    MAJORITY_VOTE = "majority_vote"
    STACKING = "stacking"
    CONFIDENCE_WEIGHTED = "confidence_weighted"


@dataclass
class EnsembleConfig:
    """Configuration for the prediction ensemble"""
    ensemble_method: EnsembleMethod = EnsembleMethod.CONFIDENCE_WEIGHTED
    min_confidence_threshold: float = 0.6
    outcome_weight: float = 0.4
    score_weight: float = 0.3
    upset_weight: float = 0.3
    
    # Model weights (if using weighted ensemble)
    model_weights: Dict[str, float] = field(default_factory=lambda: {
        'outcome': 1.0,
        'score': 0.8,
        'upset': 0.6
    })
    
    # Confidence thresholds for different prediction types
    high_confidence_threshold: float = 0.8
    medium_confidence_threshold: float = 0.65
    low_confidence_threshold: float = 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'ensemble_method': self.ensemble_method.value,
            'min_confidence_threshold': self.min_confidence_threshold,
            'outcome_weight': self.outcome_weight,
            'score_weight': self.score_weight,
            'upset_weight': self.upset_weight,
            'model_weights': self.model_weights
        }


@dataclass
class ComprehensivePrediction:
    """Complete prediction result from the AI engine"""
    # Match outcome
    winner_prediction: int  # 1 = player1, 0 = player2
    win_probability: float  # Probability that player1 wins
    outcome_confidence: float
    
    # Score prediction
    predicted_sets: Dict[str, int]  # winner_sets, loser_sets
    predicted_games: int
    predicted_duration: int  # minutes
    score_confidence: float
    
    # Upset analysis
    upset_probability: float
    upset_confidence: float
    upset_factors: Dict[str, float]
    
    # Meta information
    overall_confidence: float
    prediction_timestamp: datetime
    models_used: List[str]
    feature_importance: Dict[str, float]
    explanation: Dict[str, Any]
    
    # Risk assessment
    prediction_risk: str  # "low", "medium", "high"
    reliability_score: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'winner_prediction': self.winner_prediction,
            'win_probability': self.win_probability,
            'outcome_confidence': self.outcome_confidence,
            'predicted_sets': self.predicted_sets,
            'predicted_games': self.predicted_games,
            'predicted_duration': self.predicted_duration,
            'score_confidence': self.score_confidence,
            'upset_probability': self.upset_probability,
            'upset_confidence': self.upset_confidence,
            'upset_factors': self.upset_factors,
            'overall_confidence': self.overall_confidence,
            'prediction_timestamp': self.prediction_timestamp.isoformat(),
            'models_used': self.models_used,
            'feature_importance': self.feature_importance,
            'explanation': self.explanation,
            'prediction_risk': self.prediction_risk,
            'reliability_score': self.reliability_score
        }


class PredictionEnsemble:
    """
    AI Prediction Engine that combines multiple ML models
    
    This class orchestrates the entire prediction pipeline:
    1. Feature extraction from player and match data
    2. Individual model predictions (outcome, score, upset)
    3. Ensemble combination with confidence weighting
    4. Comprehensive result with explanations
    """
    
    def __init__(self, config: Optional[EnsembleConfig] = None, 
                 feature_config: Optional[FeatureConfig] = None):
        self.config = config or EnsembleConfig()
        self.feature_extractor = FeatureExtractor(feature_config)
        
        # Initialize individual models
        self.outcome_predictor = OutcomePredictor()
        self.score_predictor = ScorePredictor()
        self.upset_detector = UpsetDetector()
        
        # Ensemble state
        self.is_trained: bool = False
        self.model_performances: Dict[str, Dict[str, float]] = {}
        self.ensemble_history: List[ComprehensivePrediction] = []
        
        # Calibration data for confidence adjustment
        self.confidence_calibration: Dict[str, Tuple[float, float]] = {}
    
    def train_ensemble(self, training_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Train all models in the ensemble
        
        Args:
            training_data: Dictionary containing:
                - features: List of feature dictionaries
                - outcomes: List of binary outcomes (1/0)
                - scores: Dictionary with set/game/duration data
                - upsets: List of binary upset indicators
                - feature_names: List of feature names
                
        Returns:
            Training performance metrics for all models
        """
        if not training_data or not training_data.get('features'):
            return {}
        
        features = training_data['features']
        feature_names = training_data.get('feature_names', [])
        
        # Convert feature dictionaries to vectors
        feature_vectors = []
        for feature_dict in features:
            if isinstance(feature_dict, dict):
                # Extract features in consistent order
                vector = self.feature_extractor.extract_all_features(
                    feature_dict.get('player1', {}),
                    feature_dict.get('player2', {}),
                    feature_dict.get('context', {})
                )
                feature_vectors.append(list(vector.values()))
            else:
                feature_vectors.append(feature_dict)
        
        # Fit feature transformers
        outcomes = training_data.get('outcomes', [])
        if outcomes:
            self.feature_extractor.fit_transformers(features, outcomes)
        
        training_results = {}
        
        # Train outcome predictor
        if outcomes:
            outcome_metrics = self.outcome_predictor.train(
                feature_vectors, outcomes, feature_names
            )
            training_results['outcome'] = outcome_metrics
            self.model_performances['outcome'] = outcome_metrics
        
        # Train score predictor
        scores = training_data.get('scores', {})
        if scores:
            score_metrics = self.score_predictor.train(
                feature_vectors, scores, feature_names
            )
            training_results['score'] = score_metrics
            self.model_performances['score'] = score_metrics
        
        # Train upset detector
        upsets = training_data.get('upsets', [])
        if upsets:
            upset_metrics = self.upset_detector.train(
                feature_vectors, upsets, feature_names
            )
            training_results['upset'] = upset_metrics
            self.model_performances['upset'] = upset_metrics
        
        # Calculate ensemble performance weights
        self._calculate_ensemble_weights()
        
        self.is_trained = True
        return training_results
    
    def predict_match(self, player1_data: Dict[str, Any], player2_data: Dict[str, Any], 
                     match_context: Dict[str, Any]) -> ComprehensivePrediction:
        """
        Generate comprehensive match prediction
        
        Args:
            player1_data: Complete data for player 1
            player2_data: Complete data for player 2  
            match_context: Match and tournament context
            
        Returns:
            ComprehensivePrediction with all prediction components
        """
        # Extract features
        features_dict = self.feature_extractor.extract_all_features(
            player1_data, player2_data, match_context
        )
        
        # Transform features
        feature_vector = self.feature_extractor.transform_features(features_dict)
        
        # Get individual model predictions
        predictions = {}
        confidences = {}
        explanations = {}
        
        # Outcome prediction
        if self.outcome_predictor.is_trained:
            outcome_result = self.outcome_predictor.predict(feature_vector)
            predictions['outcome'] = outcome_result
            confidences['outcome'] = outcome_result.confidence
            explanations['outcome'] = outcome_result.explanation
        else:
            # Fallback outcome prediction
            ranking_diff = player1_data.get('current_ranking', 100) - player2_data.get('current_ranking', 100)
            win_prob = 0.5 + max(-0.3, min(0.3, -ranking_diff * 0.005))
            predictions['outcome'] = PredictionResult(
                prediction=1 if win_prob > 0.5 else 0,
                confidence=0.6,
                model_type=ModelType.OUTCOME,
                features_used=list(features_dict.keys()),
                explanation={'method': 'ranking_fallback'}
            )
            confidences['outcome'] = 0.6
        
        # Score prediction
        if self.score_predictor.is_trained:
            score_result = self.score_predictor.predict(feature_vector)
            predictions['score'] = score_result
            confidences['score'] = score_result.confidence
            explanations['score'] = score_result.explanation
        else:
            # Fallback score prediction
            predictions['score'] = PredictionResult(
                prediction={'winner_sets': 2, 'loser_sets': 1, 'total_games': 24, 'duration_minutes': 120},
                confidence=0.5,
                model_type=ModelType.SCORE,
                features_used=list(features_dict.keys()),
                explanation={'method': 'fallback'}
            )
            confidences['score'] = 0.5
        
        # Upset prediction
        ranking_difference = player1_data.get('current_ranking', 100) - player2_data.get('current_ranking', 100)
        if self.upset_detector.is_trained:
            upset_result = self.upset_detector.predict(feature_vector, ranking_difference)
            predictions['upset'] = upset_result
            confidences['upset'] = upset_result.confidence
            explanations['upset'] = upset_result.explanation
        else:
            # Fallback upset prediction
            upset_prob = max(0.1, min(0.9, 0.5 - ranking_difference * 0.003))
            predictions['upset'] = PredictionResult(
                prediction=upset_prob,
                confidence=0.5,
                model_type=ModelType.UPSET,
                features_used=list(features_dict.keys()),
                explanation={'method': 'ranking_fallback'}
            )
            confidences['upset'] = 0.5
        
        # Combine predictions using ensemble method
        ensemble_result = self._combine_predictions(predictions, confidences, explanations)
        
        # Calculate feature importance
        feature_importance = self._calculate_feature_importance(predictions)
        
        # Assess prediction risk
        risk_assessment = self._assess_prediction_risk(confidences, ensemble_result)
        
        # Create comprehensive prediction
        comprehensive_prediction = ComprehensivePrediction(
            winner_prediction=ensemble_result['winner'],
            win_probability=ensemble_result['win_probability'],
            outcome_confidence=confidences['outcome'],
            predicted_sets=ensemble_result['sets'],
            predicted_games=ensemble_result['games'],
            predicted_duration=ensemble_result['duration'],
            score_confidence=confidences['score'],
            upset_probability=ensemble_result['upset_probability'],
            upset_confidence=confidences['upset'],
            upset_factors=ensemble_result['upset_factors'],
            overall_confidence=ensemble_result['overall_confidence'],
            prediction_timestamp=datetime.now(),
            models_used=list(predictions.keys()),
            feature_importance=feature_importance,
            explanation=ensemble_result['explanation'],
            prediction_risk=risk_assessment['risk_level'],
            reliability_score=risk_assessment['reliability']
        )
        
        # Store in history for analysis
        self.ensemble_history.append(comprehensive_prediction)
        
        return comprehensive_prediction
    
    def _combine_predictions(self, predictions: Dict[str, PredictionResult], 
                           confidences: Dict[str, float],
                           explanations: Dict[str, Any]) -> Dict[str, Any]:
        """Combine individual model predictions using ensemble method"""
        
        # Extract predictions
        outcome_pred = predictions.get('outcome')
        score_pred = predictions.get('score')
        upset_pred = predictions.get('upset')
        
        # Winner prediction (from outcome model)
        if outcome_pred:
            winner = outcome_pred.prediction
            if hasattr(outcome_pred, 'explanation') and 'probabilities' in outcome_pred.explanation:
                # Extract probability from explanation
                probs = outcome_pred.explanation['probabilities'].get('primary', [0.5, 0.5])
                win_probability = probs[1] if len(probs) > 1 else 0.5
            else:
                win_probability = 0.6 if winner == 1 else 0.4
        else:
            winner = 1
            win_probability = 0.5
        
        # Score prediction
        if score_pred and isinstance(score_pred.prediction, dict):
            sets = {
                'winner_sets': score_pred.prediction.get('winner_sets', 2),
                'loser_sets': score_pred.prediction.get('loser_sets', 1)
            }
            games = score_pred.prediction.get('total_games', 24)
            duration = score_pred.prediction.get('duration_minutes', 120)
        else:
            sets = {'winner_sets': 2, 'loser_sets': 1}
            games = 24
            duration = 120
        
        # Upset prediction
        if upset_pred:
            upset_probability = upset_pred.prediction
            upset_factors = upset_pred.explanation if upset_pred.explanation else {}
        else:
            upset_probability = 0.3
            upset_factors = {}
        
        # Calculate overall confidence using weighted average
        weights = self.config.model_weights
        total_weight = sum(weights.get(model, 1.0) for model in confidences.keys())
        
        if total_weight > 0:
            overall_confidence = sum(
                confidences[model] * weights.get(model, 1.0) 
                for model in confidences.keys()
            ) / total_weight
        else:
            overall_confidence = statistics.mean(confidences.values()) if confidences else 0.5
        
        # Adjust confidence based on ensemble method
        if self.config.ensemble_method == EnsembleMethod.CONFIDENCE_WEIGHTED:
            # Weight by individual model confidences
            overall_confidence = min(0.95, overall_confidence * 1.1)
        
        return {
            'winner': winner,
            'win_probability': win_probability,
            'sets': sets,
            'games': games,
            'duration': duration,
            'upset_probability': upset_probability,
            'upset_factors': upset_factors,
            'overall_confidence': overall_confidence,
            'explanation': {
                'ensemble_method': self.config.ensemble_method.value,
                'individual_predictions': {k: v.to_dict() for k, v in predictions.items()},
                'model_weights': self.config.model_weights,
                'confidence_sources': confidences
            }
        }
    
    def _calculate_feature_importance(self, predictions: Dict[str, PredictionResult]) -> Dict[str, float]:
        """Calculate combined feature importance from all models"""
        all_importance = {}
        
        # Collect importance from individual models
        if hasattr(self.outcome_predictor, 'feature_importance'):
            for feature, importance in self.outcome_predictor.feature_importance.items():
                all_importance[feature] = all_importance.get(feature, 0) + importance * 0.4
        
        # Get importance from feature extractor
        extractor_importance = self.feature_extractor.get_feature_importance()
        for feature, importance in extractor_importance.items():
            all_importance[feature] = all_importance.get(feature, 0) + importance * 0.3
        
        # Normalize importance scores
        if all_importance:
            max_importance = max(all_importance.values())
            if max_importance > 0:
                all_importance = {k: v/max_importance for k, v in all_importance.items()}
        
        # Return top 10 most important features
        sorted_importance = sorted(all_importance.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_importance[:10])
    
    def _assess_prediction_risk(self, confidences: Dict[str, float], 
                              ensemble_result: Dict[str, Any]) -> Dict[str, Any]:
        """Assess the risk and reliability of the prediction"""
        
        # Calculate confidence statistics
        conf_values = list(confidences.values())
        avg_confidence = statistics.mean(conf_values) if conf_values else 0.5
        min_confidence = min(conf_values) if conf_values else 0.5
        confidence_variance = statistics.variance(conf_values) if len(conf_values) > 1 else 0
        
        # Risk factors
        risk_factors = []
        reliability_score = 1.0
        
        # Low confidence
        if avg_confidence < self.config.low_confidence_threshold:
            risk_factors.append("low_overall_confidence")
            reliability_score *= 0.8
        
        # High confidence variance (models disagree)
        if confidence_variance > 0.05:
            risk_factors.append("model_disagreement")
            reliability_score *= 0.9
        
        # Upset probability high
        if ensemble_result.get('upset_probability', 0) > 0.6:
            risk_factors.append("high_upset_risk")
            reliability_score *= 0.85
        
        # Model training status
        untrained_models = sum(1 for model in [self.outcome_predictor, self.score_predictor, self.upset_detector] 
                              if not model.is_trained)
        if untrained_models > 0:
            risk_factors.append("untrained_models")
            reliability_score *= (1.0 - untrained_models * 0.1)
        
        # Determine risk level
        if avg_confidence >= self.config.high_confidence_threshold and len(risk_factors) == 0:
            risk_level = "low"
        elif avg_confidence >= self.config.medium_confidence_threshold and len(risk_factors) <= 1:
            risk_level = "medium"
        else:
            risk_level = "high"
        
        return {
            'risk_level': risk_level,
            'reliability': max(0.1, min(1.0, reliability_score)),
            'risk_factors': risk_factors,
            'confidence_stats': {
                'average': avg_confidence,
                'minimum': min_confidence,
                'variance': confidence_variance
            }
        }
    
    def _calculate_ensemble_weights(self) -> None:
        """Calculate dynamic ensemble weights based on model performance"""
        if not self.model_performances:
            return
        
        # Update weights based on cross-validation performance
        for model_name, metrics in self.model_performances.items():
            if model_name == 'outcome':
                # Use accuracy for outcome models
                performance = metrics.get('primary_accuracy', 0.5)
            elif model_name == 'score':
                # Use R² for score models
                performance = metrics.get('sets_r2', 0.0)
            elif model_name == 'upset':
                # Use F1 for upset detection
                performance = metrics.get('upset_f1', 0.3)
            else:
                performance = 0.5
            
            # Update weight (bounded between 0.3 and 1.5)
            self.config.model_weights[model_name] = max(0.3, min(1.5, performance * 1.2))
    
    def get_ensemble_statistics(self) -> Dict[str, Any]:
        """Get statistics about ensemble performance and predictions"""
        if not self.ensemble_history:
            return {}
        
        # Calculate statistics from prediction history
        confidences = [pred.overall_confidence for pred in self.ensemble_history]
        win_probs = [pred.win_probability for pred in self.ensemble_history]
        upset_probs = [pred.upset_probability for pred in self.ensemble_history]
        
        return {
            'total_predictions': len(self.ensemble_history),
            'average_confidence': statistics.mean(confidences),
            'confidence_std': statistics.stdev(confidences) if len(confidences) > 1 else 0,
            'average_win_probability': statistics.mean(win_probs),
            'average_upset_probability': statistics.mean(upset_probs),
            'model_weights': self.config.model_weights,
            'model_performances': self.model_performances,
            'high_confidence_predictions': sum(1 for c in confidences if c >= self.config.high_confidence_threshold),
            'low_risk_predictions': sum(1 for pred in self.ensemble_history if pred.prediction_risk == 'low')
        }
    
    def save_ensemble(self, file_path: str) -> None:
        """Save the entire ensemble to file"""
        # Save individual models
        self.outcome_predictor.save_model(f"{file_path}_outcome.joblib")
        
        # Save ensemble metadata
        ensemble_data = {
            'config': self.config.to_dict(),
            'model_performances': self.model_performances,
            'is_trained': self.is_trained,
            'feature_names': self.feature_extractor.feature_names,
            'ensemble_statistics': self.get_ensemble_statistics()
        }
        
        with open(f"{file_path}_ensemble.json", 'w') as f:
            json.dump(ensemble_data, f, indent=2)
    
    def load_ensemble(self, file_path: str) -> None:
        """Load the entire ensemble from file"""
        # Load individual models
        try:
            self.outcome_predictor.load_model(f"{file_path}_outcome.joblib")
        except FileNotFoundError:
            print("Warning: Outcome model file not found")
        
        # Load ensemble metadata
        try:
            with open(f"{file_path}_ensemble.json", 'r') as f:
                ensemble_data = json.load(f)
            
            self.model_performances = ensemble_data.get('model_performances', {})
            self.is_trained = ensemble_data.get('is_trained', False)
            
        except FileNotFoundError:
            print("Warning: Ensemble metadata file not found")