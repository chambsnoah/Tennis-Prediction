"""
Feature Engineering Pipeline for Tennis Prediction ML Models

This module implements comprehensive feature extraction and transformation
for tennis match prediction, including ranking features, form features,
surface-specific features, physical condition features, and contextual features.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Union
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from enum import Enum
import json
import math

# Optional ML imports with fallbacks
try:
    from sklearn.preprocessing import StandardScaler, MinMaxScaler, LabelEncoder
    from sklearn.feature_selection import SelectKBest, f_regression, mutual_info_regression
    ML_AVAILABLE = True
except ImportError:
    print("Warning: scikit-learn not available. Feature engineering will be limited.")
    ML_AVAILABLE = False
    
    # Placeholder classes
    class StandardScaler:
        def fit(self, X): return self
        def transform(self, X): return X
        def fit_transform(self, X): return X
    
    class MinMaxScaler:
        def fit(self, X): return self
        def transform(self, X): return X
        def fit_transform(self, X): return X


class FeatureType(Enum):
    """Types of features for tennis prediction"""
    RANKING = "ranking"
    FORM = "form"
    SURFACE = "surface"
    PHYSICAL = "physical"
    CONTEXTUAL = "contextual"
    STATISTICAL = "statistical"
    HEAD_TO_HEAD = "head_to_head"


@dataclass
class FeatureConfig:
    """Configuration for feature engineering pipeline"""
    include_ranking_features: bool = True
    include_form_features: bool = True
    include_surface_features: bool = True
    include_physical_features: bool = True
    include_contextual_features: bool = True
    include_statistical_features: bool = True
    include_h2h_features: bool = True
    
    # Feature selection
    use_feature_selection: bool = True
    max_features: Optional[int] = 50
    feature_selection_method: str = "mutual_info"  # mutual_info, f_test, variance
    
    # Scaling
    scaling_method: str = "standard"  # standard, minmax, none
    handle_missing_values: str = "median"  # median, mean, zero, drop
    
    # Temporal windows
    recent_matches_window: int = 10
    form_calculation_window: int = 20
    h2h_window_months: int = 24


class FeatureExtractor:
    """
    Comprehensive feature extraction for tennis match prediction
    
    Extracts features from player statistics, match context, and historical data
    to create ML-ready feature vectors for prediction models.
    """
    
    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
        self.scalers: Dict[str, Any] = {}
        self.feature_selector: Optional[Any] = None
        self.feature_names: List[str] = []
        self.is_fitted: bool = False
        
        # Initialize scalers based on config
        if ML_AVAILABLE:
            if self.config.scaling_method == "standard":
                self.scalers['main'] = StandardScaler()
            elif self.config.scaling_method == "minmax":
                self.scalers['main'] = MinMaxScaler()
    
    def extract_ranking_features(self, player1_data: Dict, player2_data: Dict) -> Dict[str, float]:
        """Extract ranking-based features"""
        features = {}
        
        # Basic ranking features
        player1_ranking = player1_data.get('current_ranking', 100)
        player2_ranking = player2_data.get('current_ranking', 100)
        
        features['player1_ranking'] = player1_ranking
        features['player2_ranking'] = player2_ranking
        features['ranking_difference'] = player1_ranking - player2_ranking
        features['ranking_ratio'] = player1_ranking / max(1, player2_ranking)
        
        # Ranking momentum (trend)
        player1_prev = player1_data.get('previous_ranking', player1_ranking)
        player2_prev = player2_data.get('previous_ranking', player2_ranking)
        
        features['player1_ranking_trend'] = player1_prev - player1_ranking  # Positive = improving
        features['player2_ranking_trend'] = player2_prev - player2_ranking
        features['ranking_momentum_diff'] = features['player1_ranking_trend'] - features['player2_ranking_trend']
        
        # Ranking categories
        features['player1_top10'] = float(player1_ranking <= 10)
        features['player1_top20'] = float(player1_ranking <= 20)
        features['player1_top50'] = float(player1_ranking <= 50)
        features['player2_top10'] = float(player2_ranking <= 10)
        features['player2_top20'] = float(player2_ranking <= 20)
        features['player2_top50'] = float(player2_ranking <= 50)
        
        return features
    
    def extract_form_features(self, player1_data: Dict, player2_data: Dict) -> Dict[str, float]:
        """Extract recent form and performance features"""
        features = {}
        
        # Recent form factors
        features['player1_form_factor'] = player1_data.get('recent_form_factor', 1.0)
        features['player2_form_factor'] = player2_data.get('recent_form_factor', 1.0)
        features['form_advantage'] = features['player1_form_factor'] - features['player2_form_factor']
        
        # Recent match results (if available)
        player1_recent = player1_data.get('recent_matches', [])
        player2_recent = player2_data.get('recent_matches', [])
        
        if player1_recent:
            player1_wins = sum(1 for match in player1_recent[-self.config.recent_matches_window:] if match == 'W')
            features['player1_recent_win_rate'] = player1_wins / len(player1_recent[-self.config.recent_matches_window:])
            features['player1_win_streak'] = self._calculate_win_streak(player1_recent)
        else:
            features['player1_recent_win_rate'] = 0.5
            features['player1_win_streak'] = 0
        
        if player2_recent:
            player2_wins = sum(1 for match in player2_recent[-self.config.recent_matches_window:] if match == 'W')
            features['player2_recent_win_rate'] = player2_wins / len(player2_recent[-self.config.recent_matches_window:])
            features['player2_win_streak'] = self._calculate_win_streak(player2_recent)
        else:
            features['player2_recent_win_rate'] = 0.5
            features['player2_win_streak'] = 0
        
        # Form comparison
        features['win_rate_difference'] = features['player1_recent_win_rate'] - features['player2_recent_win_rate']
        features['streak_difference'] = features['player1_win_streak'] - features['player2_win_streak']
        
        return features
    
    def extract_surface_features(self, player1_data: Dict, player2_data: Dict, 
                               surface: str) -> Dict[str, float]:
        """Extract surface-specific performance features"""
        features = {}
        
        # Surface encoding
        surface_map = {'hard': 0, 'clay': 1, 'grass': 2, 'carpet': 3}
        features['surface_type'] = surface_map.get(surface.lower(), 0)
        
        # Surface preferences
        player1_pref = player1_data.get('surface_preference', 'hard')
        player2_pref = player2_data.get('surface_preference', 'hard')
        
        features['player1_surface_match'] = float(player1_pref.lower() == surface.lower())
        features['player2_surface_match'] = float(player2_pref.lower() == surface.lower())
        features['surface_preference_advantage'] = features['player1_surface_match'] - features['player2_surface_match']
        
        # Surface-specific statistics
        player1_surface_stats = player1_data.get('surface_stats', {}).get(surface.lower(), {})
        player2_surface_stats = player2_data.get('surface_stats', {}).get(surface.lower(), {})
        
        features['player1_surface_win_rate'] = player1_surface_stats.get('win_percentage', 0.5)
        features['player2_surface_win_rate'] = player2_surface_stats.get('win_percentage', 0.5)
        features['surface_win_rate_diff'] = features['player1_surface_win_rate'] - features['player2_surface_win_rate']
        
        return features
    
    def extract_statistical_features(self, player1_data: Dict, player2_data: Dict) -> Dict[str, float]:
        """Extract tennis-specific statistical features"""
        features = {}
        
        # Serve statistics
        player1_serve = player1_data.get('serve_stats', {})
        player2_serve = player2_data.get('serve_stats', {})
        
        features['player1_first_serve_win'] = player1_serve.get('first_serve_win_percentage', 0.7)
        features['player1_second_serve_win'] = player1_serve.get('second_serve_win_percentage', 0.5)
        features['player1_aces_per_match'] = player1_serve.get('aces_per_match', 5.0)
        
        features['player2_first_serve_win'] = player2_serve.get('first_serve_win_percentage', 0.7)
        features['player2_second_serve_win'] = player2_serve.get('second_serve_win_percentage', 0.5)
        features['player2_aces_per_match'] = player2_serve.get('aces_per_match', 5.0)
        
        # Serve advantages
        features['first_serve_advantage'] = features['player1_first_serve_win'] - features['player2_first_serve_win']
        features['second_serve_advantage'] = features['player1_second_serve_win'] - features['player2_second_serve_win']
        
        # Return statistics
        player1_return = player1_data.get('return_stats', {})
        player2_return = player2_data.get('return_stats', {})
        
        features['player1_return_first_serve'] = player1_return.get('first_serve_return_points_won', 0.3)
        features['player1_break_points'] = player1_return.get('break_points_converted', 0.4)
        
        features['player2_return_first_serve'] = player2_return.get('first_serve_return_points_won', 0.3)
        features['player2_break_points'] = player2_return.get('break_points_converted', 0.4)
        
        # Return advantages
        features['return_advantage'] = features['player1_return_first_serve'] - features['player2_return_first_serve']
        features['break_point_advantage'] = features['player1_break_points'] - features['player2_break_points']
        
        return features
    
    def extract_all_features(self, player1_data: Dict, player2_data: Dict, 
                           match_context: Dict) -> Dict[str, float]:
        """Extract all feature types for a match"""
        all_features = {}
        surface = match_context.get('surface', 'hard')
        
        if self.config.include_ranking_features:
            ranking_features = self.extract_ranking_features(player1_data, player2_data)
            all_features.update(ranking_features)
        
        if self.config.include_form_features:
            form_features = self.extract_form_features(player1_data, player2_data)
            all_features.update(form_features)
        
        if self.config.include_surface_features:
            surface_features = self.extract_surface_features(player1_data, player2_data, surface)
            all_features.update(surface_features)
        
        if self.config.include_statistical_features:
            statistical_features = self.extract_statistical_features(player1_data, player2_data)
            all_features.update(statistical_features)
        
        return all_features
    
    def _calculate_win_streak(self, recent_matches: List[str]) -> int:
        """Calculate current win/loss streak"""
        if not recent_matches:
            return 0
        
        current_result = recent_matches[-1]
        streak = 0
        
        for result in reversed(recent_matches):
            if result == current_result:
                streak += 1 if result == 'W' else -1
            else:
                break
        
        return streak
    
    def fit_transformers(self, feature_data: List[Dict[str, float]], 
                        target_values: Optional[List[float]] = None) -> None:
        """Fit scaling and feature selection transformers"""
        if not feature_data:
            return
        
        # Convert to DataFrame for easier handling
        df = pd.DataFrame(feature_data)
        self.feature_names = list(df.columns)
        
        # Handle missing values
        if self.config.handle_missing_values == "median":
            df = df.fillna(df.median())
        elif self.config.handle_missing_values == "mean":
            df = df.fillna(df.mean())
        elif self.config.handle_missing_values == "zero":
            df = df.fillna(0)
        
        # Fit scaler
        if ML_AVAILABLE and 'main' in self.scalers:
            self.scalers['main'].fit(df.values)
        
        # Fit feature selector
        if (self.config.use_feature_selection and target_values and 
            ML_AVAILABLE and len(df.columns) > (self.config.max_features or 20)):
            
            self.feature_selector = SelectKBest(
                score_func=mutual_info_regression if self.config.feature_selection_method == "mutual_info" else f_regression,
                k=min(self.config.max_features or 20, len(df.columns))
            )
            
            self.feature_selector.fit(df.values, target_values)
            
            # Update feature names to selected features
            selected_indices = self.feature_selector.get_support(indices=True)
            self.feature_names = [self.feature_names[i] for i in selected_indices]
        
        self.is_fitted = True
    
    def transform_features(self, feature_dict: Dict[str, float]) -> List[float]:
        """Transform features using fitted transformers"""
        if not self.is_fitted:
            return list(feature_dict.values())
        
        # Convert to DataFrame and align with training features
        df = pd.DataFrame([feature_dict])
        
        # Ensure all expected features are present
        for feature_name in self.feature_names:
            if feature_name not in df.columns:
                df[feature_name] = 0.0
        
        # Reorder columns to match training
        df = df[self.feature_names]
        
        # Handle missing values
        if self.config.handle_missing_values == "median":
            df = df.fillna(df.median())
        elif self.config.handle_missing_values == "zero":
            df = df.fillna(0)
        
        # Apply feature selection
        if self.feature_selector and ML_AVAILABLE:
            transformed_values = self.feature_selector.transform(df.values)
        else:
            transformed_values = df.values
        
        # Apply scaling
        if ML_AVAILABLE and 'main' in self.scalers:
            transformed_values = self.scalers['main'].transform(transformed_values)
        
        return transformed_values[0].tolist()
    
    def get_feature_importance(self, model: Any = None) -> Dict[str, float]:
        """Get feature importance scores"""
        importance_dict = {}
        
        if self.feature_selector and ML_AVAILABLE:
            scores = self.feature_selector.scores_
            for i, feature_name in enumerate(self.feature_names):
                importance_dict[feature_name] = float(scores[i]) if i < len(scores) else 0.0
        
        if model and hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
            for i, feature_name in enumerate(self.feature_names):
                if i < len(importances):
                    importance_dict[feature_name] = float(importances[i])
        
        return importance_dict