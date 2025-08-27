"""
Tournament and Match Data Models

Data classes for representing tournament structures, draws, and individual matches
retrieved from tennis APIs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import json
import threading


@dataclass
class Match:
    """Individual match in a tournament"""
    match_id: str
    round_name: str  # "First Round", "Second Round", "Quarterfinals", etc.
    player1: str
    player2: str
    player1_seed: Optional[int] = None
    player2_seed: Optional[int] = None
    
    # Match result (if completed)
    winner: Optional[str] = None
    score: Optional[str] = None  # "6-4, 6-2" format
    sets: Optional[List[List[int]]] = None  # [[6,4], [6,2]] format
    match_date: Optional[datetime] = None
    match_duration_minutes: Optional[int] = None
    
    # Match status
    status: str = "scheduled"  # "scheduled", "in_progress", "completed", "cancelled"
    
    def to_dict(self) -> Dict:
        return {
            'match_id': self.match_id,
            'round_name': self.round_name,
            'player1': self.player1,
            'player2': self.player2,
            'player1_seed': self.player1_seed,
            'player2_seed': self.player2_seed,
            'winner': self.winner,
            'score': self.score,
            'sets': self.sets,
            'match_date': self.match_date.isoformat() if self.match_date else None,
            'match_duration_minutes': self.match_duration_minutes,
            'status': self.status
        }
    
    @property
    def is_completed(self) -> bool:
        return self.status == "completed" and self.winner is not None
    
    @property
    def is_walkover(self) -> bool:
        return bool(self.score and "w.o." in self.score.lower())


@dataclass
class TournamentDraw:
    """Complete tournament draw with all matches and metadata"""
    tournament_id: str
    tournament_name: str
    year: int
    surface: str  # "hard", "clay", "grass", "carpet"
    category: str  # "Grand Slam", "Masters 1000", "ATP 500", etc.
    
    # Tournament details
    location: str = "Unknown"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    draw_size: int = 128
    
    # Prize money and points
    total_prize_money: Optional[int] = None
    currency: str = "USD"
    winner_points: int = 2000
    
    # Draw structure
    rounds: Dict[str, List[Match]] = field(default_factory=dict)
    seeded_players: Dict[int, str] = field(default_factory=dict)
    all_players: List[str] = field(default_factory=list)
    
    # Tournament status
    status: str = "upcoming"  # "upcoming", "in_progress", "completed"
    current_round: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Initialize thread-safe lock for player data access"""
        self._players_lock = threading.Lock()
    
    def get_all_players(self) -> List[str]:
        """Get all players in the tournament (thread-safe)"""
        with self._players_lock:
            if self.all_players:
                return self.all_players
                
            players = set()
            for round_matches in self.rounds.values():
                for match in round_matches:
                    players.add(match.player1)
                    players.add(match.player2)
            
            self.all_players = sorted(list(players))
            return self.all_players
    
    def get_seed(self, player_name: str) -> Optional[int]:
        """Get seed number for a player"""
        for seed, seeded_player in self.seeded_players.items():
            if seeded_player == player_name:
                return seed
        return None
    
    def get_player_matches(self, player_name: str) -> List[Match]:
        """Get all matches for a specific player"""
        matches = []
        for round_matches in self.rounds.values():
            for match in round_matches:
                if match.player1 == player_name or match.player2 == player_name:
                    matches.append(match)
        return matches
    
    def get_round_matches(self, round_name: str) -> List[Match]:
        """Get all matches for a specific round"""
        return self.rounds.get(round_name, [])
    
    def add_match(self, match: Match):
        """Add a match to the appropriate round"""
        if match.round_name not in self.rounds:
            self.rounds[match.round_name] = []
        self.rounds[match.round_name].append(match)
    
    def add_seeded_player(self, seed: int, player_name: str):
        """Add a seeded player"""
        self.seeded_players[seed] = player_name
    
    def get_match_by_id(self, match_id: str) -> Optional[Match]:
        """Find a match by its ID"""
        for round_matches in self.rounds.values():
            for match in round_matches:
                if match.match_id == match_id:
                    return match
        return None
    
    def update_match_result(self, match_id: str, winner: str, score: str, 
                          sets: Optional[List[List[int]]] = None):
        """Update match result"""
        match = self.get_match_by_id(match_id)
        if match:
            match.winner = winner
            match.score = score
            match.sets = sets
            match.status = "completed"
            self.last_updated = datetime.now()
    
    def get_tournament_surface_factor(self) -> float:
        """Get surface-specific factor for predictions"""
        surface_factors = {
            "hard": 1.0,
            "clay": 0.9,
            "grass": 1.1,
            "carpet": 1.0
        }
        return surface_factors.get(self.surface.lower(), 1.0)
    
    @property
    def round_names(self) -> List[str]:
        """Get ordered list of round names"""
        # Standard tournament round order
        if self.draw_size == 128:
            return ["First Round", "Second Round", "Third Round", "Fourth Round", 
                   "Quarterfinals", "Semifinals", "Final"]
        elif self.draw_size == 64:
            return ["First Round", "Second Round", "Third Round", 
                   "Quarterfinals", "Semifinals", "Final"]
        elif self.draw_size == 32:
            return ["First Round", "Second Round", "Quarterfinals", "Semifinals", "Final"]
        else:
            return sorted(self.rounds.keys())
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'tournament_id': self.tournament_id,
            'tournament_name': self.tournament_name,
            'year': self.year,
            'surface': self.surface,
            'category': self.category,
            'location': self.location,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'draw_size': self.draw_size,
            'total_prize_money': self.total_prize_money,
            'currency': self.currency,
            'winner_points': self.winner_points,
            'rounds': {round_name: [match.to_dict() for match in matches] 
                      for round_name, matches in self.rounds.items()},
            'seeded_players': {str(seed): player for seed, player in self.seeded_players.items()},
            'all_players': self.all_players,
            'status': self.status,
            'current_round': self.current_round,
            'last_updated': self.last_updated.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TournamentDraw':
        """Create TournamentDraw from dictionary"""
        # Make a copy to avoid modifying the original data
        data = data.copy()
        
        # Handle datetime conversion
        if 'start_date' in data and data['start_date']:
            data['start_date'] = datetime.fromisoformat(data['start_date'])
        if 'end_date' in data and data['end_date']:
            data['end_date'] = datetime.fromisoformat(data['end_date'])
        if 'last_updated' in data:
            if isinstance(data['last_updated'], str):
                data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        
        # Handle nested matches
        if 'rounds' in data and isinstance(data['rounds'], dict):
            rounds = {}
            for round_name, matches_data in data['rounds'].items():
                matches = []
                for match_data in matches_data:
                    if isinstance(match_data, dict):
                        # Handle match datetime
                        if 'match_date' in match_data and match_data['match_date']:
                            match_data['match_date'] = datetime.fromisoformat(match_data['match_date'])
                        matches.append(Match(**match_data))
                    else:
                        matches.append(match_data)
                rounds[round_name] = matches
            data['rounds'] = rounds
        
        # Handle seeded players (convert string keys back to int)
        if 'seeded_players' in data and isinstance(data['seeded_players'], dict):
            seeded_players = {}
            for seed_str, player in data['seeded_players'].items():
                try:
                    seed = int(seed_str)
                    seeded_players[seed] = player
                except (ValueError, TypeError):
                    pass
            data['seeded_players'] = seeded_players
        
        # Filter data to only include valid TournamentDraw constructor parameters
        # Get all field names from the TournamentDraw dataclass
        import dataclasses
        valid_fields = {field.name for field in dataclasses.fields(cls)}
        
        # Create filtered data dict with only valid constructor parameters
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        # Ensure required fields have default values if missing
        required_defaults = {
            'category': 'Unknown',
            'tournament_id': data.get('tournament_id', 'unknown'),
            'tournament_name': data.get('tournament_name', 'Unknown Tournament'),
            'year': data.get('year', 2024),
            'surface': data.get('surface', 'hard')
        }
        
        # Add missing required fields with defaults
        for field_name, default_value in required_defaults.items():
            if field_name not in filtered_data:
                filtered_data[field_name] = default_value
        
        return cls(**filtered_data)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TournamentDraw':
        """Create TournamentDraw from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)