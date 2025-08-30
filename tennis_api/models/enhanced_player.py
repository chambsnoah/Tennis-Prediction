"""
Enhanced Player Models for Phase 2: Advanced Tennis Prediction

This module implements the enhanced player architecture that incorporates
real-time data, contextual factors, and machine learning capabilities
to improve prediction accuracy significantly.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import json
import math
import random
from enum import Enum

from .player_stats import PlayerStats, ServeStatistics, ReturnStatistics, SurfaceStats


class MotivationLevel(Enum):
    """Tournament motivation levels"""
    LOW = 0.8          # Early rounds of small tournaments
    MEDIUM = 1.0       # Regular tournaments
    HIGH = 1.15        # Masters/Premier events
    VERY_HIGH = 1.3    # Grand Slams


class SurfaceType(Enum):
    """Tennis court surface types"""
    HARD = "hard"
    CLAY = "clay"
    GRASS = "grass"
    CARPET = "carpet"


@dataclass
class PhysicalCondition:
    """Player's physical condition and fatigue factors"""
    stamina_level: float = 1.0      # 0.5-1.0 (tired to fresh)
    injury_risk: float = 0.0        # 0.0-1.0 (healthy to injured)
    fitness_level: float = 1.0      # 0.7-1.3 (poor to excellent fitness)
    fatigue_factor: float = 1.0     # 0.7-1.0 (very tired to fresh)
    recovery_rate: float = 0.1      # How quickly player recovers between matches
    
    def apply_match_fatigue(self, match_duration: int, sets_played: int) -> None:
        """Apply fatigue after a match"""
        # Base fatigue from match duration (minutes)
        duration_fatigue = min(0.3, match_duration / 300.0)
        
        # Additional fatigue from number of sets
        sets_fatigue = (sets_played - 3) * 0.05 if sets_played > 3 else 0
        
        total_fatigue = duration_fatigue + sets_fatigue
        self.stamina_level = max(0.5, self.stamina_level - total_fatigue)
        self.fatigue_factor = max(0.7, self.fatigue_factor - total_fatigue * 0.5)
    
    def rest_recovery(self, hours: int) -> None:
        """Apply recovery during rest periods"""
        recovery = min(0.5, hours * self.recovery_rate / 24.0)
        self.stamina_level = min(1.0, self.stamina_level + recovery)
        self.fatigue_factor = min(1.0, self.fatigue_factor + recovery * 0.8)


@dataclass
class MentalState:
    """Player's mental and psychological state"""
    confidence_level: float = 1.0    # 0.5-1.5 (low to high confidence)
    pressure_tolerance: float = 1.0  # 0.7-1.3 (cracks under pressure to thrives)
    momentum: float = 1.0           # 0.5-1.5 (negative to positive momentum)
    motivation_factor: float = 1.0   # Based on tournament importance
    mental_toughness: float = 1.0    # 0.7-1.3 (weak to strong mentally)
    
    def update_momentum(self, points_won: int, points_lost: int) -> None:
        """Update momentum based on recent point outcomes"""
        if points_won + points_lost == 0:
            return
            
        point_ratio = points_won / (points_won + points_lost)
        momentum_change = (point_ratio - 0.5) * 0.2
        self.momentum = max(0.5, min(1.5, self.momentum + momentum_change))
    
    def apply_pressure(self, pressure_level: float) -> float:
        """Apply pressure effects to performance"""
        pressure_effect = 1.0 - (pressure_level * (2.0 - self.pressure_tolerance))
        return max(0.5, min(1.2, pressure_effect))


@dataclass
class ContextualFactors:
    """Match and tournament contextual factors"""
    tournament_tier: str = "ATP250"     # ATP250, ATP500, Masters1000, GrandSlam
    tournament_importance: float = 1.0   # Derived from tier
    weather_conditions: Dict[str, Any] = field(default_factory=dict)
    crowd_support: float = 1.0          # 0.8-1.2 (hostile to supportive)
    time_of_day: str = "afternoon"      # morning, afternoon, evening, night
    match_round: str = "R32"            # R128, R64, R32, R16, QF, SF, F
    
    def __post_init__(self):
        """Set tournament importance based on tier"""
        tier_mapping = {
            "GrandSlam": 1.3,
            "Masters1000": 1.15,
            "ATP500": 1.05,
            "ATP250": 1.0,
            "Challenger": 0.9,
            "Futures": 0.8
        }
        self.tournament_importance = tier_mapping.get(self.tournament_tier, 1.0)


@dataclass 
class PlayerEnhanced:
    """
    Enhanced Player class with advanced attributes and contextual factors
    
    This class extends the basic player model with real-time data integration,
    physical condition tracking, mental state modeling, and contextual awareness.
    """
    # Basic player information
    name: str
    api_stats: Optional[PlayerStats] = None
    
    # Rankings and basic stats
    current_ranking: int = 100
    previous_ranking: int = 100
    ranking_trend: float = 0.0  # Positive = improving, negative = declining
    
    # Surface and style preferences
    surface_preference: str = "hard"
    playing_style: str = "baseline"  # baseline, serve_and_volley, all_court
    dominant_hand: str = "right"
    backhand_style: str = "two_handed"
    
    # Performance factors
    recent_form_factor: float = 1.0     # 0.5-1.5 based on recent results
    physical_condition: PhysicalCondition = field(default_factory=PhysicalCondition)
    mental_state: MentalState = field(default_factory=MentalState)
    contextual_factors: ContextualFactors = field(default_factory=ContextualFactors)
    
    # Advanced statistics
    surface_stats: Dict[str, SurfaceStats] = field(default_factory=dict)
    head_to_head_records: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    tournament_history: Dict[str, List[str]] = field(default_factory=dict)  # tournament -> [results]
    
    # Time-sensitive data
    last_updated: datetime = field(default_factory=datetime.now)
    last_match_date: Optional[datetime] = None
    next_match_date: Optional[datetime] = None
    
    def calculate_form_factor(self, recent_matches: Optional[List[str]] = None) -> float:
        """
        Calculate recent form factor based on last 10 matches
        
        Args:
            recent_matches: List of match results ["W", "L", "W", ...]
            
        Returns:
            Form factor between 0.5 and 1.5
        """
        if recent_matches is None and self.api_stats:
            recent_matches = self.api_stats.recent_matches
        
        if not recent_matches:
            return 1.0
        
        # Weight recent matches more heavily
        weighted_score = 0
        total_weight = 0
        
        for i, result in enumerate(reversed(recent_matches[-10:])):
            weight = (i + 1) / 10.0  # More recent matches have higher weight
            score = 1.0 if result == "W" else 0.0
            weighted_score += score * weight
            total_weight += weight
        
        if total_weight == 0:
            return 1.0
        
        weighted_win_rate = weighted_score / total_weight
        # Convert to form factor: 0.0 -> 0.5, 0.5 -> 1.0, 1.0 -> 1.5
        form_factor = 0.5 + weighted_win_rate
        return max(0.5, min(1.5, form_factor))
    
    def get_surface_multiplier(self, surface: str) -> float:
        """
        Get performance multiplier for specific surface
        
        Args:
            surface: Surface type (hard, clay, grass, carpet)
            
        Returns:
            Performance multiplier between 0.6 and 1.4
        """
        surface_lower = surface.lower()
        
        # Use API stats if available
        if self.api_stats and surface_lower in self.api_stats.surface_stats:
            return self.api_stats.get_surface_multiplier(surface)
        
        # Use enhanced surface stats
        if surface_lower in self.surface_stats:
            surface_stat = self.surface_stats[surface_lower]
            baseline_win_rate = 0.5
            actual_win_rate = surface_stat.calculated_win_percentage
            multiplier = actual_win_rate / baseline_win_rate
            return max(0.6, min(1.4, multiplier))
        
        # Default surface preference adjustment
        preference_bonus = 0.1 if surface_lower == self.surface_preference.lower() else 0.0
        return 1.0 + preference_bonus
    
    def assess_injury_risk(self, news_data: Optional[Dict] = None) -> float:
        """
        Assess injury risk based on news sentiment and physical condition
        
        Args:
            news_data: Optional news sentiment data
            
        Returns:
            Injury risk between 0.0 and 1.0
        """
        base_risk = self.physical_condition.injury_risk
        
        # Factor in fatigue
        fatigue_risk = (1.0 - self.physical_condition.stamina_level) * 0.3
        
        # Factor in recent match frequency
        risk = base_risk + fatigue_risk
        
        # News sentiment analysis (if available)
        if news_data and 'injury_mentions' in news_data:
            sentiment_risk = news_data['injury_mentions'] * 0.2
            risk += sentiment_risk
        
        return max(0.0, min(1.0, risk))
    
    def evaluate_motivation(self, tournament_importance: Optional[float] = None) -> float:
        """
        Evaluate motivation factor based on tournament importance
        
        Args:
            tournament_importance: Tournament tier importance (0.8-1.3)
            
        Returns:
            Motivation factor between 0.8 and 1.3
        """
        if tournament_importance is None:
            tournament_importance = self.contextual_factors.tournament_importance
        
        # Base motivation from tournament tier
        base_motivation = tournament_importance
        
        # Adjust based on ranking (lower ranked players more motivated for bigger events)
        if self.current_ranking > 50:
            ranking_bonus = min(0.2, (self.current_ranking - 50) * 0.002)
            base_motivation += ranking_bonus
        
        # Apply mental state
        motivation = base_motivation * self.mental_state.motivation_factor
        
        return max(0.8, min(1.3, motivation))
    
    def get_adjusted_serve_percentage(self, surface: str, opponent_ranking: int) -> float:
        """
        Calculate dynamically adjusted serve percentage
        
        Args:
            surface: Court surface
            opponent_ranking: Opponent's current ranking
            
        Returns:
            Adjusted serve percentage between 0.3 and 0.95
        """
        # Base serve percentage from API stats or defaults
        if self.api_stats:
            base_percentage = self.api_stats.serve_stats.first_serve_win_percentage
        else:
            base_percentage = 0.65  # Default
        
        # Apply surface adjustment
        surface_factor = self.get_surface_multiplier(surface)
        
        # Apply form factor
        form_factor = self.recent_form_factor
        
        # Apply physical condition
        physical_factor = (self.physical_condition.stamina_level + 
                         self.physical_condition.fatigue_factor) / 2.0
        
        # Apply mental state
        mental_factor = (self.mental_state.confidence_level + 
                        self.mental_state.momentum) / 2.0
        
        # Apply opponent strength (ranking difference)
        ranking_diff = self.current_ranking - opponent_ranking
        opponent_factor = max(0.9, min(1.1, 1.0 + (ranking_diff * 0.0005)))
        
        # Apply motivation
        motivation_factor = self.evaluate_motivation()
        
        # Combine all factors
        adjusted_percentage = (base_percentage * surface_factor * form_factor * 
                             physical_factor * mental_factor * opponent_factor * 
                             motivation_factor)
        
        return max(0.3, min(0.95, adjusted_percentage))
    
    def update_after_match(self, match_result: str, match_duration: int, 
                          sets_played: int, opponent_name: str) -> None:
        """
        Update player state after a match
        
        Args:
            match_result: "W" or "L"
            match_duration: Match duration in minutes
            sets_played: Number of sets played
            opponent_name: Name of opponent
        """
        # Update physical condition
        self.physical_condition.apply_match_fatigue(match_duration, sets_played)
        
        # Update mental state based on result
        if match_result == "W":
            self.mental_state.confidence_level = min(1.5, self.mental_state.confidence_level + 0.1)
            self.mental_state.momentum = min(1.5, self.mental_state.momentum + 0.2)
        else:
            self.mental_state.confidence_level = max(0.5, self.mental_state.confidence_level - 0.05)
            self.mental_state.momentum = max(0.5, self.mental_state.momentum - 0.1)
        
        # Update head-to-head record
        if opponent_name not in self.head_to_head_records:
            self.head_to_head_records[opponent_name] = (0, 0)
        
        wins, losses = self.head_to_head_records[opponent_name]
        if match_result == "W":
            self.head_to_head_records[opponent_name] = (wins + 1, losses)
        else:
            self.head_to_head_records[opponent_name] = (wins, losses + 1)
        
        # Update timestamps
        self.last_match_date = datetime.now()
        self.last_updated = datetime.now()
        
        # Recalculate form factor
        if self.api_stats:
            # Add result to recent matches
            self.api_stats.recent_matches.append(match_result)
            if len(self.api_stats.recent_matches) > 10:
                self.api_stats.recent_matches = self.api_stats.recent_matches[-10:]
            self.recent_form_factor = self.calculate_form_factor()
    
    def get_head_to_head_factor(self, opponent_name: str) -> float:
        """
        Get head-to-head performance factor against specific opponent
        
        Args:
            opponent_name: Name of the opponent
            
        Returns:
            H2H factor between 0.5 and 1.5
        """
        if opponent_name not in self.head_to_head_records:
            return 1.0
        
        wins, losses = self.head_to_head_records[opponent_name]
        total_matches = wins + losses
        
        if total_matches == 0:
            return 1.0
        
        win_rate = wins / total_matches
        # Convert to factor: 0.0 -> 0.5, 0.5 -> 1.0, 1.0 -> 1.5
        factor = 0.5 + win_rate
        return max(0.5, min(1.5, factor))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'name': self.name,
            'current_ranking': self.current_ranking,
            'surface_preference': self.surface_preference,
            'recent_form_factor': self.recent_form_factor,
            'physical_condition': {
                'stamina_level': self.physical_condition.stamina_level,
                'injury_risk': self.physical_condition.injury_risk,
                'fatigue_factor': self.physical_condition.fatigue_factor
            },
            'mental_state': {
                'confidence_level': self.mental_state.confidence_level,
                'momentum': self.mental_state.momentum,
                'motivation_factor': self.mental_state.motivation_factor
            },
            'last_updated': self.last_updated.isoformat()
        }
    
    @classmethod
    def from_player_stats(cls, player_stats: PlayerStats, **kwargs) -> 'PlayerEnhanced':
        """Create PlayerEnhanced from PlayerStats"""
        return cls(
            name=player_stats.name,
            api_stats=player_stats,
            current_ranking=player_stats.current_ranking,
            recent_form_factor=player_stats.calculate_form_factor(),
            **kwargs
        )