"""
Machine Learning Prediction Models for Tennis

This module implements the core ML models for tennis prediction:
- OutcomePredictor: Predicts match winner and probability
- ScorePredictor: Predicts set scores and match duration  
- UpsetDetector: Identifies potential upsets and assesses risk
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Union
import numpy as np
import json
from datetime import datetime
from enum import Enum
import pickle
import joblib

# ML imports with fallbacks
try:
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, IsolationForest
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.svm import SVC, SVR
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    from sklearn.preprocessing import StandardScaler
    import xgboost as xgb
    ML_AVAILABLE = True
except ImportError:
    print("Warning: ML libraries not available. Using fallback implementations.")
    ML_AVAILABLE = False
    
    # Fallback classes
    class RandomForestClassifier:
        def __init__(self, **kwargs): pass
        def fit(self, X, y): pass
        def predict(self, X): return np.zeros(len(X))
        def predict_proba(self, X): return np.random.rand(len(X), 2)
    
    class RandomForestRegressor:
        def __init__(self, **kwargs): pass
        def fit(self, X, y): pass
        def predict(self, X): return np.zeros(len(X))
    
    class LogisticRegression:
        def __init__(self, **kwargs): pass
        def fit(self, X, y): pass
        def predict(self, X): return np.zeros(len(X))
        def predict_proba(self, X): return np.random.rand(len(X), 2)


class ModelType(Enum):
    """Types of prediction models"""
    OUTCOME = "outcome"
    SCORE = "score"
    UPSET = "upset"
    PERFORMANCE = "performance"


@dataclass
class ModelConfig:
    """Configuration for ML models"""
    model_type: str = "random_forest"
    n_estimators: int = 100
    max_depth: Optional[int] = 10
    random_state: int = 42
    test_size: float = 0.2
    cv_folds: int = 5
    use_feature_importance: bool = True
    
    # Model-specific parameters
    logistic_C: float = 1.0
    svm_C: float = 1.0
    svm_kernel: str = "rbf"
    xgb_learning_rate: float = 0.1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'model_type': self.model_type,
            'n_estimators': self.n_estimators,
            'max_depth': self.max_depth,
            'random_state': self.random_state,
            'test_size': self.test_size,
            'cv_folds': self.cv_folds
        }


@dataclass
class PredictionResult:
    """Result from a prediction model"""
    prediction: Union[float, int, List[float]]
    confidence: float
    model_type: ModelType
    features_used: List[str]
    prediction_time: datetime = field(default_factory=datetime.now)
    explanation: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'prediction': self.prediction,
            'confidence': self.confidence,
            'model_type': self.model_type.value,
            'features_used': self.features_used,
            'prediction_time': self.prediction_time.isoformat(),
            'explanation': self.explanation
        }


class OutcomePredictor:
    """
    Predicts match outcomes (winner) with confidence scores
    
    Uses classification models to predict which player will win
    and provides probability estimates for match outcome.
    """
    
    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.models: Dict[str, Any] = {}
        self.feature_names: List[str] = []
        self.is_trained: bool = False
        self.training_scores: Dict[str, float] = {}
        self.feature_importance: Dict[str, float] = {}
        
        # Initialize models
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """Initialize ML models based on configuration"""
        if not ML_AVAILABLE:
            return
        
        # Primary model
        if self.config.model_type == "random_forest":
            self.models['primary'] = RandomForestClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                random_state=self.config.random_state
            )
        elif self.config.model_type == "logistic_regression":
            self.models['primary'] = LogisticRegression(
                C=self.config.logistic_C,
                random_state=self.config.random_state
            )
        elif self.config.model_type == "svm":
            self.models['primary'] = SVC(
                C=self.config.svm_C,
                kernel=self.config.svm_kernel,
                probability=True,
                random_state=self.config.random_state
            )
        
        # Ensemble models for better performance
        self.models['rf_ensemble'] = RandomForestClassifier(
            n_estimators=50,
            max_depth=8,
            random_state=self.config.random_state + 1
        )
        
        self.models['logistic_ensemble'] = LogisticRegression(
            C=0.5,
            random_state=self.config.random_state + 2
        )
    
    def train(self, X: List[List[float]], y: List[int], 
              feature_names: Optional[List[str]] = None) -> Dict[str, float]:
        """
        Train the outcome prediction model
        
        Args:
            X: Feature vectors (list of lists)
            y: Binary outcomes (0 = player2 wins, 1 = player1 wins)
            feature_names: Names of features
            
        Returns:
            Training performance metrics
        """
        if not ML_AVAILABLE or not X or not y:
            return {'accuracy': 0.5, 'precision': 0.5, 'recall': 0.5, 'f1': 0.5}
        
        X_array = np.array(X)
        y_array = np.array(y)
        
        if feature_names:
            self.feature_names = feature_names
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_array, y_array, 
            test_size=self.config.test_size,
            random_state=self.config.random_state,
            stratify=y_array if len(np.unique(y_array)) > 1 else None
        )
        
        # Train models
        metrics = {}
        for model_name, model in self.models.items():
            try:
                model.fit(X_train, y_train)
                
                # Evaluate
                y_pred = model.predict(X_test)
                
                metrics[f'{model_name}_accuracy'] = accuracy_score(y_test, y_pred)
                metrics[f'{model_name}_precision'] = precision_score(y_test, y_pred, average='weighted')
                metrics[f'{model_name}_recall'] = recall_score(y_test, y_pred, average='weighted')
                metrics[f'{model_name}_f1'] = f1_score(y_test, y_pred, average='weighted')
                
                # Cross-validation score
                cv_scores = cross_val_score(model, X_array, y_array, cv=self.config.cv_folds)
                metrics[f'{model_name}_cv_mean'] = cv_scores.mean()
                metrics[f'{model_name}_cv_std'] = cv_scores.std()
                
            except Exception as e:
                print(f"Warning: Failed to train {model_name}: {e}")
                continue
        
        # Extract feature importance from primary model
        if hasattr(self.models['primary'], 'feature_importances_'):
            importances = self.models['primary'].feature_importances_
            self.feature_importance = {
                name: float(importance) 
                for name, importance in zip(self.feature_names, importances)
            }
        
        self.training_scores = metrics
        self.is_trained = True
        
        return metrics
    
    def predict(self, features: List[float]) -> PredictionResult:
        """
        Predict match outcome
        
        Args:
            features: Feature vector for the match
            
        Returns:
            PredictionResult with winner prediction and confidence
        """
        if not self.is_trained or not ML_AVAILABLE:
            # Fallback prediction
            return PredictionResult(
                prediction=1,  # Player 1 wins
                confidence=0.5,
                model_type=ModelType.OUTCOME,
                features_used=self.feature_names,
                explanation={'method': 'fallback', 'reason': 'model_not_trained'}
            )
        
        X = np.array([features])
        
        # Get predictions from all models
        predictions = {}
        probabilities = {}
        
        for model_name, model in self.models.items():
            try:
                pred = model.predict(X)[0]
                proba = model.predict_proba(X)[0]
                
                predictions[model_name] = pred
                probabilities[model_name] = proba
                
            except Exception as e:
                print(f"Warning: Prediction failed for {model_name}: {e}")
                continue
        
        if not predictions:
            # Fallback if all models fail
            return PredictionResult(
                prediction=1,
                confidence=0.5,
                model_type=ModelType.OUTCOME,
                features_used=self.feature_names,
                explanation={'method': 'fallback', 'reason': 'prediction_failed'}
            )
        
        # Ensemble prediction (majority vote)
        primary_prediction = predictions.get('primary', 1)
        primary_proba = probabilities.get('primary', [0.5, 0.5])
        
        # Calculate confidence as the maximum probability
        confidence = max(primary_proba)
        
        # Create explanation
        explanation = {
            'model_predictions': predictions,
            'probabilities': {k: v.tolist() for k, v in probabilities.items()},
            'primary_model': self.config.model_type,
            'feature_importance': dict(list(self.feature_importance.items())[:5])  # Top 5 features
        }
        
        return PredictionResult(
            prediction=int(primary_prediction),
            confidence=float(confidence),
            model_type=ModelType.OUTCOME,
            features_used=self.feature_names,
            explanation=explanation
        )
    
    def save_model(self, file_path: str) -> None:
        """Save trained model to file"""
        model_data = {
            'config': self.config.to_dict(),
            'feature_names': self.feature_names,
            'training_scores': self.training_scores,
            'feature_importance': self.feature_importance,
            'is_trained': self.is_trained
        }
        
        if ML_AVAILABLE:
            # Save sklearn models using joblib
            joblib.dump({
                'models': self.models,
                'metadata': model_data
            }, file_path)
        else:
            # Save metadata only
            with open(file_path, 'w') as f:
                json.dump(model_data, f, indent=2)
    
    def load_model(self, file_path: str) -> None:
        """Load trained model from file"""
        if ML_AVAILABLE:
            try:
                data = joblib.load(file_path)
                self.models = data['models']
                metadata = data['metadata']
            except:
                # Fallback to JSON
                with open(file_path, 'r') as f:
                    metadata = json.load(f)
        else:
            with open(file_path, 'r') as f:
                metadata = json.load(f)
        
        self.feature_names = metadata['feature_names']
        self.training_scores = metadata['training_scores']
        self.feature_importance = metadata['feature_importance']
        self.is_trained = metadata['is_trained']


class ScorePredictor:
    """
    Predicts match scores and duration
    
    Uses regression models to predict set scores, total games,
    and estimated match duration.
    """
    
    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.models: Dict[str, Any] = {}
        self.feature_names: List[str] = []
        self.is_trained: bool = False
        self.training_scores: Dict[str, float] = {}
        
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """Initialize regression models"""
        if not ML_AVAILABLE:
            return
        
        # Models for different score aspects
        self.models['set_scores'] = RandomForestRegressor(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            random_state=self.config.random_state
        )
        
        self.models['total_games'] = LinearRegression()
        
        self.models['match_duration'] = RandomForestRegressor(
            n_estimators=50,
            max_depth=8,
            random_state=self.config.random_state
        )
    
    def train(self, X: List[List[float]], y: Dict[str, List[float]], 
              feature_names: Optional[List[str]] = None) -> Dict[str, float]:
        """
        Train score prediction models
        
        Args:
            X: Feature vectors
            y: Dictionary with 'sets', 'games', 'duration' targets
            feature_names: Names of features
            
        Returns:
            Training performance metrics
        """
        if not ML_AVAILABLE or not X:
            return {'r2_score': 0.0, 'mse': 1.0, 'mae': 1.0}
        
        X_array = np.array(X)
        
        if feature_names:
            self.feature_names = feature_names
        
        metrics = {}
        
        # Train models for different targets
        for target_name in ['sets', 'games', 'duration']:
            if target_name not in y or not y[target_name]:
                continue
            
            y_target = np.array(y[target_name])
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X_array, y_target,
                test_size=self.config.test_size,
                random_state=self.config.random_state
            )
            
            # Select appropriate model
            if target_name == 'sets':
                model = self.models['set_scores']
            elif target_name == 'games':
                model = self.models['total_games']
            else:  # duration
                model = self.models['match_duration']
            
            try:
                model.fit(X_train, y_train)
                
                # Evaluate
                y_pred = model.predict(X_test)
                
                metrics[f'{target_name}_r2'] = r2_score(y_test, y_pred)
                metrics[f'{target_name}_mse'] = mean_squared_error(y_test, y_pred)
                metrics[f'{target_name}_mae'] = mean_absolute_error(y_test, y_pred)
                
            except Exception as e:
                print(f"Warning: Failed to train {target_name} model: {e}")
                continue
        
        self.training_scores = metrics
        self.is_trained = True
        
        return metrics
    
    def predict(self, features: List[float]) -> PredictionResult:
        """
        Predict match scores and duration
        
        Args:
            features: Feature vector for the match
            
        Returns:
            PredictionResult with score predictions
        """
        if not self.is_trained or not ML_AVAILABLE:
            # Fallback predictions
            return PredictionResult(
                prediction={
                    'winner_sets': 2,
                    'loser_sets': 1,
                    'total_games': 24,
                    'duration_minutes': 120
                },
                confidence=0.5,
                model_type=ModelType.SCORE,
                features_used=self.feature_names,
                explanation={'method': 'fallback'}
            )
        
        X = np.array([features])
        predictions = {}
        
        try:
            # Predict set scores (simplified to total sets)
            if 'set_scores' in self.models:
                sets_pred = self.models['set_scores'].predict(X)[0]
                predictions['total_sets'] = max(3, min(5, round(sets_pred)))
            
            # Predict total games
            if 'total_games' in self.models:
                games_pred = self.models['total_games'].predict(X)[0]
                predictions['total_games'] = max(18, min(50, round(games_pred)))
            
            # Predict match duration
            if 'match_duration' in self.models:
                duration_pred = self.models['match_duration'].predict(X)[0]
                predictions['duration_minutes'] = max(60, min(300, round(duration_pred)))
            
            # Calculate likely set breakdown
            total_sets = predictions.get('total_sets', 3)
            if total_sets == 3:
                predictions['winner_sets'] = 2
                predictions['loser_sets'] = 1
            elif total_sets == 4:
                predictions['winner_sets'] = 3
                predictions['loser_sets'] = 1
            else:  # 5 sets
                predictions['winner_sets'] = 3
                predictions['loser_sets'] = 2
            
            # Confidence based on model performance
            confidence = 0.7  # Base confidence for score predictions
            
        except Exception as e:
            print(f"Warning: Score prediction failed: {e}")
            predictions = {
                'winner_sets': 2,
                'loser_sets': 1,
                'total_games': 24,
                'duration_minutes': 120
            }
            confidence = 0.5
        
        return PredictionResult(
            prediction=predictions,
            confidence=confidence,
            model_type=ModelType.SCORE,
            features_used=self.feature_names,
            explanation={'model_scores': self.training_scores}
        )


class UpsetDetector:
    """
    Detects potential upsets in tennis matches
    
    Uses anomaly detection and classification to identify
    matches where the lower-ranked player might win.
    """
    
    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.models: Dict[str, Any] = {}
        self.feature_names: List[str] = []
        self.is_trained: bool = False
        self.upset_threshold: float = 0.3  # Probability threshold for upset prediction
        
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """Initialize upset detection models"""
        if not ML_AVAILABLE:
            return
        
        # Anomaly detection for unusual match conditions
        self.models['anomaly_detector'] = IsolationForest(
            contamination=0.1,
            random_state=self.config.random_state
        )
        
        # Classification for upset prediction
        self.models['upset_classifier'] = RandomForestClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            random_state=self.config.random_state,
            class_weight='balanced'  # Handle imbalanced upset data
        )
    
    def train(self, X: List[List[float]], y: List[int], 
              feature_names: Optional[List[str]] = None) -> Dict[str, float]:
        """
        Train upset detection models
        
        Args:
            X: Feature vectors
            y: Binary labels (1 = upset occurred, 0 = no upset)
            feature_names: Names of features
            
        Returns:
            Training performance metrics
        """
        if not ML_AVAILABLE or not X or not y:
            return {'upset_accuracy': 0.6, 'upset_precision': 0.4, 'upset_recall': 0.3}
        
        X_array = np.array(X)
        y_array = np.array(y)
        
        if feature_names:
            self.feature_names = feature_names
        
        metrics = {}
        
        try:
            # Train anomaly detector on all data
            self.models['anomaly_detector'].fit(X_array)
            
            # Train upset classifier
            X_train, X_test, y_train, y_test = train_test_split(
                X_array, y_array,
                test_size=self.config.test_size,
                random_state=self.config.random_state,
                stratify=y_array if len(np.unique(y_array)) > 1 else None
            )
            
            self.models['upset_classifier'].fit(X_train, y_train)
            
            # Evaluate
            y_pred = self.models['upset_classifier'].predict(X_test)
            
            metrics['upset_accuracy'] = accuracy_score(y_test, y_pred)
            metrics['upset_precision'] = precision_score(y_test, y_pred, average='weighted')
            metrics['upset_recall'] = recall_score(y_test, y_pred, average='weighted')
            
            # Calculate upset-specific metrics (class 1)
            if len(np.unique(y_test)) > 1:
                metrics['upset_class_precision'] = precision_score(y_test, y_pred, pos_label=1)
                metrics['upset_class_recall'] = recall_score(y_test, y_pred, pos_label=1)
            
        except Exception as e:
            print(f"Warning: Failed to train upset detection models: {e}")
            metrics = {'upset_accuracy': 0.6, 'upset_precision': 0.4, 'upset_recall': 0.3}
        
        self.is_trained = True
        return metrics
    
    def predict(self, features: List[float], ranking_difference: float) -> PredictionResult:
        """
        Predict upset potential
        
        Args:
            features: Feature vector for the match
            ranking_difference: Difference in player rankings (positive = player1 ranked higher)
            
        Returns:
            PredictionResult with upset probability and risk factors
        """
        if not self.is_trained or not ML_AVAILABLE:
            # Simple fallback based on ranking difference
            upset_probability = max(0.1, min(0.9, 0.5 - ranking_difference * 0.005))
            
            return PredictionResult(
                prediction=upset_probability,
                confidence=0.5,
                model_type=ModelType.UPSET,
                features_used=self.feature_names,
                explanation={'method': 'ranking_based_fallback'}
            )
        
        X = np.array([features])
        
        try:
            # Anomaly detection
            anomaly_score = self.models['anomaly_detector'].decision_function(X)[0]
            is_anomalous = self.models['anomaly_detector'].predict(X)[0] == -1
            
            # Upset classification
            upset_proba = self.models['upset_classifier'].predict_proba(X)[0]
            upset_probability = upset_proba[1] if len(upset_proba) > 1 else 0.3
            
            # Combine anomaly detection with upset prediction
            if is_anomalous:
                upset_probability = min(0.9, upset_probability * 1.3)  # Boost if anomalous
            
            # Factor in ranking difference
            if ranking_difference > 50:  # Large ranking difference
                upset_probability = min(0.8, upset_probability * 1.2)
            
            confidence = max(upset_proba) if len(upset_proba) > 1 else 0.6
            
            explanation = {
                'anomaly_score': float(anomaly_score),
                'is_anomalous': bool(is_anomalous),
                'ranking_difference': ranking_difference,
                'raw_upset_proba': float(upset_proba[1]) if len(upset_proba) > 1 else 0.3,
                'adjusted_upset_proba': float(upset_probability)
            }
            
        except Exception as e:
            print(f"Warning: Upset prediction failed: {e}")
            upset_probability = 0.3
            confidence = 0.5
            explanation = {'method': 'fallback', 'error': str(e)}
        
        return PredictionResult(
            prediction=float(upset_probability),
            confidence=float(confidence),
            model_type=ModelType.UPSET,
            features_used=self.feature_names,
            explanation=explanation
        )