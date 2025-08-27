"""
Player Statistics Data Models

Data classes for representing comprehensive player statistics retrieved from tennis APIs.
Includes serve statistics, return statistics, surface-specific performance, and more.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import json


@dataclass
class ServeStatistics:
    """Comprehensive serving statistics for a player"""
    first_serve_percentage: float = 0.6
    first_serve_win_percentage: float = 0.7
    second_serve_win_percentage: float = 0.5
    aces_per_match: float = 5.0
    double_faults_per_match: float = 2.0
    service_games_won_percentage: float = 0.8
    
    def to_dict(self) -> Dict:
        return {
            'first_serve_pct': self.first_serve_percentage,
            'first_serve_win_pct': self.first_serve_win_percentage,
            'second_serve_win_pct': self.second_serve_win_percentage,
            'aces_per_match': self.aces_per_match,
            'double_faults_per_match': self.double_faults_per_match,
            'service_games_won_pct': self.service_games_won_percentage
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ServeStatistics':
        """Create ServeStatistics from dictionary with mapped field names"""
        return cls(
            first_serve_percentage=data.get('first_serve_pct', 0.6),
            first_serve_win_percentage=data.get('first_serve_win_pct', 0.7),
            second_serve_win_percentage=data.get('second_serve_win_pct', 0.5),
            aces_per_match=data.get('aces_per_match', 5.0),
            double_faults_per_match=data.get('double_faults_per_match', 2.0),
            service_games_won_percentage=data.get('service_games_won_pct', 0.8)
        )


@dataclass
class ReturnStatistics:
    """Comprehensive return statistics for a player"""
    first_serve_return_points_won: float = 0.3
    second_serve_return_points_won: float = 0.5
    break_points_converted: float = 0.4
    return_games_won_percentage: float = 0.2
    return_winners_per_match: float = 8.0
    
    def to_dict(self) -> Dict:
        return {
            'first_serve_return_won': self.first_serve_return_points_won,
            'second_serve_return_won': self.second_serve_return_points_won,
            'break_points_converted': self.break_points_converted,
            'return_games_won_pct': self.return_games_won_percentage,
            'return_winners_per_match': self.return_winners_per_match
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ReturnStatistics':
        """Create ReturnStatistics from dictionary with mapped field names"""
        return cls(
            first_serve_return_points_won=data.get('first_serve_return_won', 0.3),
            second_serve_return_points_won=data.get('second_serve_return_won', 0.5),
            break_points_converted=data.get('break_points_converted', 0.4),
            return_games_won_percentage=data.get('return_games_won_pct', 0.2),
            return_winners_per_match=data.get('return_winners_per_match', 8.0)
        )


@dataclass 
class SurfaceStats:
    """Surface-specific performance statistics"""
    surface: str
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    win_percentage: float = 0.5
    serve_percentage: float = 0.6
    return_percentage: float = 0.3
    
    @property
    def total_matches(self) -> int:
        return self.wins + self.losses
    
    @property
    def calculated_win_percentage(self) -> float:
        if self.total_matches == 0:
            return 0.5
        return self.wins / self.total_matches
    
    def to_dict(self) -> Dict:
        return {
            'surface': self.surface,
            'matches_played': self.matches_played,
            'wins': self.wins,
            'losses': self.losses,
            'win_percentage': self.calculated_win_percentage,
            'serve_percentage': self.serve_percentage,
            'return_percentage': self.return_percentage
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SurfaceStats':
        """Create SurfaceStats from dictionary"""
        # Note: win_percentage is calculated, so we don't use it in the constructor
        return cls(
            surface=data['surface'],
            matches_played=data.get('matches_played', 0),
            wins=data.get('wins', 0),
            losses=data.get('losses', 0),
            win_percentage=data.get('win_percentage', 0.5),  # fallback if needed
            serve_percentage=data.get('serve_percentage', 0.6),
            return_percentage=data.get('return_percentage', 0.3)
        )


@dataclass
class PlayerStats:
    """Comprehensive player statistics from tennis APIs"""
    name: str
    current_ranking: int = 100
    previous_ranking: int = 100
    nationality: str = "Unknown"
    age: int = 25
    height_cm: int = 180
    weight_kg: int = 75
    plays: str = "Right"  # "Right", "Left", or "Right (Two-handed backhand)"
    
    # Performance statistics
    serve_stats: ServeStatistics = field(default_factory=ServeStatistics)
    return_stats: ReturnStatistics = field(default_factory=ReturnStatistics)
    
    # Surface-specific statistics
    surface_stats: Dict[str, SurfaceStats] = field(default_factory=dict)
    
    # Recent form and performance
    recent_matches: List[str] = field(default_factory=list)  # ["W", "L", "W", ...] last 10
    recent_form_factor: float = 1.0  # Calculated from recent matches
    
    # Tournament and match context
    current_tournament: Optional[str] = None
    injury_status: str = "Healthy"
    last_updated: datetime = field(default_factory=datetime.now)
    
    # Head-to-head records (opponent_name -> (wins, losses))
    head_to_head: Dict[str, tuple] = field(default_factory=dict)
    
    def calculate_form_factor(self) -> float:
        """Calculate recent form factor based on last 10 matches"""
        if not self.recent_matches:
            return 1.0
            
        wins = sum(1 for match in self.recent_matches if match == "W")
        total = len(self.recent_matches)
        
        if total == 0:
            return 1.0
            
        win_rate = wins / total
        # Convert win rate to form factor (0.5 = neutral, higher = better form)
        form_factor = 0.7 + (win_rate * 0.6)  # Range: 0.7 to 1.3
        return max(0.5, min(1.5, form_factor))
    
    def get_surface_multiplier(self, surface: str) -> float:
        """Get performance multiplier for specific surface"""
        if surface.lower() not in self.surface_stats:
            return 1.0
            
        surface_performance = self.surface_stats[surface.lower()]
        baseline_win_rate = 0.5
        
        # Calculate multiplier based on surface win rate vs baseline
        surface_win_rate = surface_performance.calculated_win_percentage
        multiplier = surface_win_rate / baseline_win_rate
        
        # Clamp multiplier to reasonable range
        return max(0.6, min(1.4, multiplier))
    
    def get_head_to_head_factor(self, opponent_name: str) -> float:
        """Get head-to-head performance factor against specific opponent"""
        if opponent_name not in self.head_to_head:
            return 1.0
            
        wins, losses = self.head_to_head[opponent_name]
        total = wins + losses
        
        if total == 0:
            return 1.0
            
        h2h_win_rate = wins / total
        # Convert to factor (0.5 = neutral)
        factor = 0.7 + (h2h_win_rate * 0.6)
        return max(0.5, min(1.5, factor))
    
    def update_recent_form(self, match_results: List[str]):
        """Update recent match results (W/L)"""
        self.recent_matches = match_results[-10:]  # Keep last 10 matches
        self.recent_form_factor = self.calculate_form_factor()
    
    def add_surface_stats(self, surface: str, stats: SurfaceStats):
        """Add or update surface-specific statistics"""
        self.surface_stats[surface.lower()] = stats
    
    def add_head_to_head(self, opponent: str, wins: int, losses: int):
        """Add or update head-to-head record against opponent"""
        self.head_to_head[opponent] = (wins, losses)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'name': self.name,
            'current_ranking': self.current_ranking,
            'previous_ranking': self.previous_ranking,
            'nationality': self.nationality,
            'age': self.age,
            'height_cm': self.height_cm,
            'weight_kg': self.weight_kg,
            'plays': self.plays,
            'serve_stats': self.serve_stats.to_dict(),
            'return_stats': self.return_stats.to_dict(),
            'surface_stats': {k: v.to_dict() for k, v in self.surface_stats.items()},
            'recent_matches': self.recent_matches,
            'recent_form_factor': self.recent_form_factor,
            'current_tournament': self.current_tournament,
            'injury_status': self.injury_status,
            'last_updated': self.last_updated.isoformat(),
            'head_to_head': {k: list(v) for k, v in self.head_to_head.items()}
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PlayerStats':
        """Create PlayerStats from dictionary"""
        # Make a copy to avoid modifying the original data
        data = data.copy()
        
        # Handle datetime conversion
        if 'last_updated' in data:
            if isinstance(data['last_updated'], str):
                data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        
        # Handle nested objects
        if 'serve_stats' in data and isinstance(data['serve_stats'], dict):
            data['serve_stats'] = ServeStatistics.from_dict(data['serve_stats'])
        
        if 'return_stats' in data and isinstance(data['return_stats'], dict):
            data['return_stats'] = ReturnStatistics.from_dict(data['return_stats'])
        
        if 'surface_stats' in data and isinstance(data['surface_stats'], dict):
            surface_stats = {}
            for surface, stats in data['surface_stats'].items():
                if isinstance(stats, dict):
                    surface_stats[surface] = SurfaceStats.from_dict(stats)
                else:
                    surface_stats[surface] = stats
            data['surface_stats'] = surface_stats
        
        if 'head_to_head' in data and isinstance(data['head_to_head'], dict):
            h2h = {}
            for opponent, record in data['head_to_head'].items():
                if isinstance(record, list) and len(record) == 2:
                    h2h[opponent] = tuple(record)
                else:
                    h2h[opponent] = record
            data['head_to_head'] = h2h
        
        # Filter data to only include valid PlayerStats constructor parameters
        # Get all field names from the PlayerStats dataclass
        import dataclasses
        valid_fields = {field.name for field in dataclasses.fields(cls)}
        
        # Create filtered data dict with only valid constructor parameters
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        return cls(**filtered_data)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PlayerStats':
        """Create PlayerStats from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)