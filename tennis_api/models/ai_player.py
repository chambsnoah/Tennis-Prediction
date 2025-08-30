"""
AI-Powered Player Models for Machine Learning Integration

This module implements the PlayerAI class that extends PlayerEnhanced with
machine learning models for serve prediction, return prediction, mental state
assessment, and opponent adaptation capabilities.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Union
import numpy as np
import json
from datetime import datetime
from enum import Enum

# ML imports - with fallback for development
try:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, mean_squared_error
    ML_AVAILABLE = True
except ImportError:
    print("Warning: scikit-learn not available. ML features will be limited.")
    ML_AVAILABLE = False
    # Create placeholder classes
    class RandomForestRegressor:
        def __init__(self, **kwargs): pass
        def fit(self, X, y): pass
        def predict(self, X): return np.zeros(len(X))
        def predict_proba(self, X): return np.zeros((len(X), 2))
    
    class RandomForestClassifier:
        def __init__(self, **kwargs): pass
        def fit(self, X, y): pass
        def predict(self, X): return np.zeros(len(X))
        def predict_proba(self, X): return np.zeros((len(X), 2))
    
    class LogisticRegression:
        def __init__(self, **kwargs): pass
        def fit(self, X, y): pass
        def predict(self, X): return np.zeros(len(X))
        def predict_proba(self, X): return np.zeros((len(X), 2))
    
    class LinearRegression:
        def __init__(self, **kwargs): pass
        def fit(self, X, y): pass
        def predict(self, X): return np.zeros(len(X))
    
    class StandardScaler:
        def __init__(self): pass
        def fit(self, X): pass
        def transform(self, X): return X
        def fit_transform(self, X): return X

from .enhanced_player import PlayerEnhanced, PhysicalCondition, MentalState, ContextualFactors


class PredictionConfidence(Enum):
    """Confidence levels for ML predictions"""
    LOW = 0.6
    MEDIUM = 0.75
    HIGH = 0.85
    VERY_HIGH = 0.95


@dataclass
class MLModelConfig:
    """Configuration for machine learning models"""
    model_type: str = "random_forest"
    n_estimators: int = 100
    max_depth: Optional[int] = 10
    random_state: int = 42
    train_test_split: float = 0.8
    feature_selection_threshold: float = 0.01
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'model_type': self.model_type,
            'n_estimators': self.n_estimators,
            'max_depth': self.max_depth,
            'random_state': self.random_state,
            'train_test_split': self.train_test_split,
            'feature_selection_threshold': self.feature_selection_threshold
        }


@dataclass
class PerformanceContext:
    """Context for performance prediction"""
    surface: str = "hard"
    opponent_ranking: int = 100
    tournament_tier: str = "ATP250"
    match_round: str = "R32"
    weather_temp: float = 22.0
    weather_humidity: float = 50.0
    weather_wind: float = 5.0
    crowd_factor: float = 1.0
    time_of_day: str = "afternoon"
    pressure_level: float = 0.5  # 0.0 (low) to 1.0 (high)
    
    def to_feature_vector(self) -> List[float]:
        """Convert context to numerical feature vector"""
        surface_encoding = {'hard': 0, 'clay': 1, 'grass': 2, 'carpet': 3}
        tier_encoding = {'GrandSlam': 4, 'Masters1000': 3, 'ATP500': 2, 'ATP250': 1, 'Challenger': 0}
        round_encoding = {'R128': 1, 'R64': 2, 'R32': 3, 'R16': 4, 'QF': 5, 'SF': 6, 'F': 7}
        time_encoding = {'morning': 0, 'afternoon': 1, 'evening': 2, 'night': 3}
        
        return [
            surface_encoding.get(self.surface, 0),
            self.opponent_ranking,
            tier_encoding.get(self.tournament_tier, 1),
            round_encoding.get(self.match_round, 3),
            self.weather_temp,
            self.weather_humidity,
            self.weather_wind,
            self.crowd_factor,
            time_encoding.get(self.time_of_day, 1),
            self.pressure_level
        ]


@dataclass
class MLModel:
    """Wrapper for machine learning models with tennis-specific functionality"""
    model_name: str
    model: Any = None
    scaler: Optional[StandardScaler] = None
    feature_names: List[str] = field(default_factory=list)
    is_trained: bool = False
    last_training_date: Optional[datetime] = None
    training_score: float = 0.0
    validation_score: float = 0.0
    config: MLModelConfig = field(default_factory=MLModelConfig)
    
    def __post_init__(self):
        """Initialize the model based on configuration"""
        if ML_AVAILABLE and self.model is None:
            if self.config.model_type == "random_forest":
                if "classifier" in self.model_name.lower():
                    self.model = RandomForestClassifier(
                        n_estimators=self.config.n_estimators,
                        max_depth=self.config.max_depth,
                        random_state=self.config.random_state
                    )
                else:
                    self.model = RandomForestRegressor(
                        n_estimators=self.config.n_estimators,
                        max_depth=self.config.max_depth,
                        random_state=self.config.random_state
                    )
            elif self.config.model_type == "logistic_regression":
                self.model = LogisticRegression(random_state=self.config.random_state)
            elif self.config.model_type == "linear_regression":
                self.model = LinearRegression()
            
            self.scaler = StandardScaler()
    
    def train(self, X: List[List[float]], y: List[float], feature_names: Optional[List[str]] = None) -> Dict[str, float]:
        """Train the model on provided data"""
        if not ML_AVAILABLE or self.model is None:
            return {'training_score': 0.0, 'validation_score': 0.0}
        
        X_array = np.array(X)
        y_array = np.array(y)
        
        if feature_names:
            self.feature_names = feature_names
        
        # Scale features
        if self.scaler:
            X_scaled = self.scaler.fit_transform(X_array)
        else:
            X_scaled = X_array
        
        # Train model
        self.model.fit(X_scaled, y_array)
        
        # Calculate scores
        if hasattr(self.model, 'score'):
            self.training_score = self.model.score(X_scaled, y_array)
        else:
            predictions = self.model.predict(X_scaled)
            if "classifier" in self.model_name.lower():
                self.training_score = accuracy_score(y_array, predictions)
            else:
                self.training_score = 1.0 - mean_squared_error(y_array, predictions)
        
        self.validation_score = self.training_score  # Simplified for now
        self.is_trained = True
        self.last_training_date = datetime.now()
        
        return {
            'training_score': self.training_score,
            'validation_score': self.validation_score
        }
    
    def predict(self, X: List[float]) -> Union[float, List[float]]:
        """Make prediction on new data"""
        if not self.is_trained or not ML_AVAILABLE:
            return 0.5  # Default fallback
        
        X_array = np.array([X])
        
        if self.scaler:
            X_scaled = self.scaler.transform(X_array)
        else:
            X_scaled = X_array
        
        prediction = self.model.predict(X_scaled)
        return float(prediction[0]) if len(prediction) == 1 else prediction.tolist()
    
    def predict_with_confidence(self, X: List[float]) -> Tuple[float, float]:
        """Make prediction with confidence score"""
        prediction = self.predict(X)
        
        if not ML_AVAILABLE or not hasattr(self.model, 'predict_proba'):
            return float(prediction), 0.5  # Default confidence
        
        X_array = np.array([X])
        if self.scaler:
            X_scaled = self.scaler.transform(X_array)
        else:
            X_scaled = X_array
        
        probabilities = self.model.predict_proba(X_scaled)[0]
        confidence = max(probabilities)
        
        return float(prediction), float(confidence)


@dataclass
class PlayerAI(PlayerEnhanced):
    """
    AI-Enhanced Player with Machine Learning Capabilities
    
    Extends PlayerEnhanced with ML models for serve performance prediction,
    return performance prediction, mental state assessment, and adaptive
    strategy against different opponents.
    """
    
    # ML Models for different aspects of tennis performance
    serve_model: MLModel = field(default_factory=lambda: MLModel("serve_predictor"))
    return_model: MLModel = field(default_factory=lambda: MLModel("return_predictor"))
    mental_model: MLModel = field(default_factory=lambda: MLModel("mental_state_classifier"))
    
    # Performance prediction models
    outcome_model: MLModel = field(default_factory=lambda: MLModel("outcome_classifier"))
    score_model: MLModel = field(default_factory=lambda: MLModel("score_predictor"))
    
    # Adaptive strategy models
    opponent_adaptation_model: MLModel = field(default_factory=lambda: MLModel("adaptation_predictor"))
    
    # Training data storage
    training_data: Dict[str, List[List[float]]] = field(default_factory=dict)
    training_labels: Dict[str, List[float]] = field(default_factory=dict)
    
    # AI-specific attributes
    learning_rate: float = 0.01
    adaptation_speed: float = 0.1
    prediction_confidence_threshold: float = 0.7
    model_update_frequency: int = 10  # Update models every N matches
    matches_since_update: int = 0
    
    def __post_init__(self):
        """Initialize AI models after object creation"""
        super().__post_init__ if hasattr(super(), '__post_init__') else lambda: None)()
        
        # Initialize training data structures
        for model_name in ['serve', 'return', 'mental', 'outcome', 'score', 'adaptation']:
            if model_name not in self.training_data:
                self.training_data[model_name] = []
                self.training_labels[model_name] = []
    
    def predict_serve_performance(self, context: PerformanceContext) -> Tuple[float, float]:
        """
        Predict serve performance given match context
        
        Args:
            context: Match context including surface, opponent, weather, etc.
            
        Returns:
            Tuple of (predicted_serve_percentage, confidence)
        """
        # Create feature vector from player state and context
        features = self._create_serve_features(context)
        
        if self.serve_model.is_trained:
            prediction, confidence = self.serve_model.predict_with_confidence(features)
        else:
            # Fallback to enhanced player calculation
            prediction = self.get_adjusted_serve_percentage(context.surface, context.opponent_ranking)
            confidence = 0.5
        
        # Ensure reasonable bounds
        prediction = max(0.3, min(0.95, prediction))
        
        return prediction, confidence
    
    def predict_return_performance(self, context: PerformanceContext) -> Tuple[float, float]:
        """
        Predict return performance given match context
        
        Args:
            context: Match context
            
        Returns:
            Tuple of (predicted_return_percentage, confidence)
        """
        features = self._create_return_features(context)
        
        if self.return_model.is_trained:
            prediction, confidence = self.return_model.predict_with_confidence(features)
        else:
            # Fallback calculation
            base_return = 0.35
            surface_adj = self.get_surface_multiplier(context.surface) - 1.0
            prediction = base_return + surface_adj * 0.1
            confidence = 0.5
        
        prediction = max(0.1, min(0.7, prediction))
        return prediction, confidence
    
    def predict_mental_state(self, pressure_level: float, context: PerformanceContext) -> Tuple[Dict[str, float], float]:
        """
        Predict mental state given pressure and context
        
        Args:
            pressure_level: Pressure level (0.0 to 1.0)
            context: Match context
            
        Returns:
            Tuple of (mental_state_dict, confidence)
        """
        features = self._create_mental_features(pressure_level, context)
        
        if self.mental_model.is_trained:
            prediction, confidence = self.mental_model.predict_with_confidence(features)
            
            # Convert single prediction to mental state components
            mental_state = {
                'confidence_adjustment': (prediction - 0.5) * 0.4,  # -0.2 to +0.2
                'pressure_tolerance': self.mental_state.pressure_tolerance * (0.8 + prediction * 0.4),
                'momentum_change': (prediction - 0.5) * 0.2
            }
        else:
            # Fallback mental state calculation
            pressure_effect = self.mental_state.apply_pressure(pressure_level)
            mental_state = {
                'confidence_adjustment': 0.0,
                'pressure_tolerance': pressure_effect,
                'momentum_change': 0.0
            }
            confidence = 0.5
        
        return mental_state, confidence
    
    def adapt_to_opponent(self, opponent_name: str, opponent_style: str, 
                         historical_data: Optional[List[Dict]] = None) -> Dict[str, float]:
        """
        Adapt strategy and predictions based on opponent characteristics
        
        Args:
            opponent_name: Name of the opponent
            opponent_style: Playing style (baseline, serve_and_volley, all_court)
            historical_data: Previous matches against this opponent
            
        Returns:
            Dictionary of adaptation factors
        """
        features = self._create_adaptation_features(opponent_name, opponent_style, historical_data)
        
        if self.opponent_adaptation_model.is_trained:
            adaptation_score = self.opponent_adaptation_model.predict(features)
        else:
            # Fallback adaptation based on head-to-head
            h2h_factor = self.get_head_to_head_factor(opponent_name)
            adaptation_score = h2h_factor
        
        # Convert adaptation score to specific adjustments
        adaptations = {
            'serve_adjustment': (adaptation_score - 1.0) * 0.1,
            'return_adjustment': (adaptation_score - 1.0) * 0.08,
            'aggression_level': 0.5 + (adaptation_score - 1.0) * 0.3,
            'strategy_confidence': min(0.9, 0.5 + abs(adaptation_score - 1.0))
        }
        
        return adaptations
    
    def update_models_after_match(self, match_result: str, match_stats: Dict[str, Any],
                                 context: PerformanceContext) -> None:
        """
        Update ML models with new match data
        
        Args:
            match_result: "W" or "L"
            match_stats: Dictionary of match statistics
            context: Match context
        """
        # Update base player state
        match_duration = match_stats.get('duration_minutes', 120)
        sets_played = match_stats.get('sets_played', 3)
        opponent_name = match_stats.get('opponent_name', 'Unknown')
        
        super().update_after_match(match_result, match_duration, sets_played, opponent_name)
        
        # Collect training data
        self._collect_training_data(match_result, match_stats, context)
        
        # Update models if enough new data
        self.matches_since_update += 1
        if self.matches_since_update >= self.model_update_frequency:
            self._retrain_models()
            self.matches_since_update = 0
    
    def _create_serve_features(self, context: PerformanceContext) -> List[float]:
        """Create feature vector for serve prediction"""
        base_features = context.to_feature_vector()
        
        player_features = [
            self.current_ranking,
            self.recent_form_factor,
            self.physical_condition.stamina_level,
            self.physical_condition.fatigue_factor,
            self.mental_state.confidence_level,
            self.mental_state.momentum,
            self.get_surface_multiplier(context.surface),
            self.api_stats.serve_stats.first_serve_percentage if self.api_stats else 0.6,
            self.api_stats.serve_stats.first_serve_win_percentage if self.api_stats else 0.65,
            self.api_stats.serve_stats.aces_per_match if self.api_stats else 5.0
        ]
        
        return base_features + player_features
    
    def _create_return_features(self, context: PerformanceContext) -> List[float]:
        """Create feature vector for return prediction"""
        base_features = context.to_feature_vector()
        
        player_features = [
            self.current_ranking,
            self.recent_form_factor,
            self.physical_condition.stamina_level,
            self.mental_state.confidence_level,
            self.get_surface_multiplier(context.surface),
            self.api_stats.return_stats.first_serve_return_points_won if self.api_stats else 0.3,
            self.api_stats.return_stats.second_serve_return_points_won if self.api_stats else 0.5,
            self.api_stats.return_stats.break_points_converted if self.api_stats else 0.4
        ]
        
        return base_features + player_features
    
    def _create_mental_features(self, pressure_level: float, context: PerformanceContext) -> List[float]:
        """Create feature vector for mental state prediction"""
        base_features = context.to_feature_vector()
        
        mental_features = [
            pressure_level,
            self.mental_state.confidence_level,
            self.mental_state.pressure_tolerance,
            self.mental_state.momentum,
            self.mental_state.mental_toughness,
            self.physical_condition.stamina_level,
            self.recent_form_factor,
            float(self.current_ranking <= 20),  # Top 20 player flag
            self.contextual_factors.tournament_importance
        ]
        
        return base_features + mental_features
    
    def _create_adaptation_features(self, opponent_name: str, opponent_style: str, 
                                  historical_data: Optional[List[Dict]]) -> List[float]:
        """Create feature vector for opponent adaptation"""
        h2h_factor = self.get_head_to_head_factor(opponent_name)
        
        style_encoding = {'baseline': 0, 'serve_and_volley': 1, 'all_court': 2}
        style_code = style_encoding.get(opponent_style, 0)
        
        features = [
            h2h_factor,
            style_code,
            len(historical_data) if historical_data else 0,
            self.recent_form_factor,
            self.mental_state.confidence_level
        ]
        
        if historical_data:
            # Add statistics from historical matches
            wins = sum(1 for match in historical_data if match.get('result') == 'W')
            avg_sets = np.mean([match.get('sets_played', 3) for match in historical_data])
            features.extend([wins / len(historical_data), avg_sets])
        else:
            features.extend([0.5, 3.0])  # Default values
        
        return features
    
    def _collect_training_data(self, match_result: str, match_stats: Dict[str, Any], 
                              context: PerformanceContext) -> None:
        """Collect training data from completed match"""
        # Serve training data
        serve_features = self._create_serve_features(context)
        actual_serve_performance = match_stats.get('serve_percentage', 0.65)
        self.training_data['serve'].append(serve_features)
        self.training_labels['serve'].append(actual_serve_performance)
        
        # Return training data
        return_features = self._create_return_features(context)
        actual_return_performance = match_stats.get('return_percentage', 0.35)
        self.training_data['return'].append(return_features)
        self.training_labels['return'].append(actual_return_performance)
        
        # Outcome training data
        outcome_features = serve_features[:10] + return_features[10:15]  # Combine key features
        outcome_label = 1.0 if match_result == 'W' else 0.0
        self.training_data['outcome'].append(outcome_features)
        self.training_labels['outcome'].append(outcome_label)
    
    def _retrain_models(self) -> Dict[str, Dict[str, float]]:
        """Retrain all models with collected data"""
        results = {}
        
        for model_name in ['serve', 'return', 'outcome']:
            if len(self.training_data[model_name]) >= 10:  # Minimum training samples
                model = getattr(self, f"{model_name}_model")
                X = self.training_data[model_name]
                y = self.training_labels[model_name]
                
                scores = model.train(X, y)
                results[model_name] = scores
                
                print(f"Retrained {model_name} model: Training={scores['training_score']:.3f}")
        
        return results
    
    def get_prediction_summary(self, context: PerformanceContext) -> Dict[str, Any]:
        """Get comprehensive prediction summary for match"""
        serve_pred, serve_conf = self.predict_serve_performance(context)
        return_pred, return_conf = self.predict_return_performance(context)
        mental_pred, mental_conf = self.predict_mental_state(context.pressure_level, context)
        
        return {
            'serve_prediction': {
                'percentage': serve_pred,
                'confidence': serve_conf,
                'model_trained': self.serve_model.is_trained
            },
            'return_prediction': {
                'percentage': return_pred,
                'confidence': return_conf,
                'model_trained': self.return_model.is_trained
            },
            'mental_state': {
                'predictions': mental_pred,
                'confidence': mental_conf,
                'model_trained': self.mental_model.is_trained
            },
            'overall_confidence': (serve_conf + return_conf + mental_conf) / 3.0,
            'prediction_timestamp': datetime.now().isoformat()
        }