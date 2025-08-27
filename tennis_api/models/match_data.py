"""
Match Result and Head-to-Head Data Models

Data classes for representing individual match results and head-to-head records
between players.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class MatchResult:
    """Individual match result with detailed statistics"""
    match_id: str
    date: datetime
    tournament: str
    surface: str
    round_name: str
    
    # Players
    player1: str
    player2: str
    winner: str
    loser: str
    
    # Score and sets
    final_score: str  # "6-4, 6-2"
    sets: List[List[int]] = field(default_factory=list)  # [[6,4], [6,2]]
    total_games_won: tuple = (0, 0)  # (player1_games, player2_games)
    
    # Match duration and context
    duration_minutes: Optional[int] = None
    retirement: bool = False
    walkover: bool = False
    
    # Detailed statistics (if available)
    aces: tuple = (0, 0)  # (player1_aces, player2_aces)
    double_faults: tuple = (0, 0)
    first_serve_percentage: tuple = (0.0, 0.0)
    first_serve_points_won: tuple = (0.0, 0.0)
    second_serve_points_won: tuple = (0.0, 0.0)
    break_points_saved: tuple = (0.0, 0.0)
    return_points_won: tuple = (0.0, 0.0)
    
    # Tournament context
    player1_seed: Optional[int] = None
    player2_seed: Optional[int] = None
    player1_ranking: Optional[int] = None
    player2_ranking: Optional[int] = None
    
    def get_winner_stats(self) -> Dict:
        """Get statistics for the match winner"""
        winner_index = 0 if self.winner == self.player1 else 1
        return {
            'aces': self.aces[winner_index],
            'double_faults': self.double_faults[winner_index],
            'first_serve_pct': self.first_serve_percentage[winner_index],
            'first_serve_won': self.first_serve_points_won[winner_index],
            'second_serve_won': self.second_serve_points_won[winner_index],
            'break_points_saved': self.break_points_saved[winner_index],
            'return_points_won': self.return_points_won[winner_index]
        }
    
    def get_loser_stats(self) -> Dict:
        """Get statistics for the match loser"""
        loser_index = 0 if self.loser == self.player1 else 1
        return {
            'aces': self.aces[loser_index],
            'double_faults': self.double_faults[loser_index],
            'first_serve_pct': self.first_serve_percentage[loser_index],
            'first_serve_won': self.first_serve_points_won[loser_index],
            'second_serve_won': self.second_serve_points_won[loser_index],
            'break_points_saved': self.break_points_saved[loser_index],
            'return_points_won': self.return_points_won[loser_index]
        }
    
    def get_player_stats(self, player_name: str) -> Dict:
        """Get statistics for a specific player"""
        if player_name == self.player1:
            index = 0
        elif player_name == self.player2:
            index = 1
        else:
            raise ValueError(f"Player {player_name} not in this match")
        
        return {
            'aces': self.aces[index],
            'double_faults': self.double_faults[index],
            'first_serve_pct': self.first_serve_percentage[index],
            'first_serve_won': self.first_serve_points_won[index],
            'second_serve_won': self.second_serve_points_won[index],
            'break_points_saved': self.break_points_saved[index],
            'return_points_won': self.return_points_won[index],
            'games_won': self.total_games_won[index]
        }
    
    @property
    def was_straight_sets(self) -> bool:
        """Check if match was won in straight sets"""
        if not self.sets:
            return False
        
        winner_index = 0 if self.winner == self.player1 else 1
        winner_sets = sum(1 for set_score in self.sets if set_score[winner_index] > set_score[1-winner_index])
        return winner_sets == len(self.sets)
    
    @property
    def total_sets_played(self) -> int:
        """Get total number of sets played"""
        return len(self.sets)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'match_id': self.match_id,
            'date': self.date.isoformat(),
            'tournament': self.tournament,
            'surface': self.surface,
            'round_name': self.round_name,
            'player1': self.player1,
            'player2': self.player2,
            'winner': self.winner,
            'loser': self.loser,
            'final_score': self.final_score,
            'sets': self.sets,
            'total_games_won': list(self.total_games_won),
            'duration_minutes': self.duration_minutes,
            'retirement': self.retirement,
            'walkover': self.walkover,
            'aces': list(self.aces),
            'double_faults': list(self.double_faults),
            'first_serve_percentage': list(self.first_serve_percentage),
            'first_serve_points_won': list(self.first_serve_points_won),
            'second_serve_points_won': list(self.second_serve_points_won),
            'break_points_saved': list(self.break_points_saved),
            'return_points_won': list(self.return_points_won),
            'player1_seed': self.player1_seed,
            'player2_seed': self.player2_seed,
            'player1_ranking': self.player1_ranking,
            'player2_ranking': self.player2_ranking
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MatchResult':
        """Create MatchResult from dictionary"""
        # Handle datetime conversion
        if 'date' in data and isinstance(data['date'], str):
            data['date'] = datetime.fromisoformat(data['date'])
        
        # Convert lists back to tuples
        tuple_fields = ['total_games_won', 'aces', 'double_faults', 'first_serve_percentage',
                       'first_serve_points_won', 'second_serve_points_won', 'break_points_saved',
                       'return_points_won']
        
        for field in tuple_fields:
            if field in data and isinstance(data[field], list):
                data[field] = tuple(data[field])
        
        return cls(**data)


@dataclass
class HeadToHeadRecord:
    """Head-to-head record between two players"""
    player1: str
    player2: str
    
    # Overall record
    player1_wins: int = 0
    player2_wins: int = 0
    
    # Surface breakdown
    hard_court_record: tuple = (0, 0)  # (player1_wins, player2_wins)
    clay_court_record: tuple = (0, 0)
    grass_court_record: tuple = (0, 0)
    
    # Recent matches (last 10)
    recent_matches: List[MatchResult] = field(default_factory=list)
    
    # Last meeting
    last_meeting: Optional[MatchResult] = None
    
    @property
    def total_matches(self) -> int:
        """Total number of matches played"""
        return self.player1_wins + self.player2_wins
    
    @property
    def player1_win_percentage(self) -> float:
        """Player 1's win percentage"""
        if self.total_matches == 0:
            return 0.5
        return self.player1_wins / self.total_matches
    
    @property
    def player2_win_percentage(self) -> float:
        """Player 2's win percentage"""
        if self.total_matches == 0:
            return 0.5
        return self.player2_wins / self.total_matches
    
    def get_surface_record(self, surface: str) -> tuple:
        """Get head-to-head record on specific surface"""
        surface_lower = surface.lower()
        if surface_lower == "hard":
            return self.hard_court_record
        elif surface_lower == "clay":
            return self.clay_court_record
        elif surface_lower == "grass":
            return self.grass_court_record
        else:
            return (0, 0)
    
    def get_surface_advantage(self, surface: str, for_player: str) -> float:
        """Get advantage factor for player on specific surface"""
        p1_wins, p2_wins = self.get_surface_record(surface)
        total = p1_wins + p2_wins
        
        if total == 0:
            return 1.0
        
        if for_player == self.player1:
            win_rate = p1_wins / total
        elif for_player == self.player2:
            win_rate = p2_wins / total
        else:
            return 1.0
        
        # Convert win rate to advantage factor
        return 0.7 + (win_rate * 0.6)  # Range: 0.7 to 1.3
    
    def add_match_result(self, match_result: MatchResult):
        """Add a new match result to the head-to-head record"""
        # Update overall record
        if match_result.winner == self.player1:
            self.player1_wins += 1
        elif match_result.winner == self.player2:
            self.player2_wins += 1
        
        # Update surface record
        self._update_surface_record(match_result.surface.lower(), match_result.winner)
        
        # Update recent matches (keep last 10)
        self.recent_matches.append(match_result)
        if len(self.recent_matches) > 10:
            self.recent_matches = self.recent_matches[-10:]
        
        # Update last meeting
        self.last_meeting = match_result

    def _update_surface_record(self, surface: str, winner):
        """Helper method to update surface-specific records"""
        surface_map = {
            "hard":  "hard_court_record",
            "clay":  "clay_court_record",
            "grass": "grass_court_record",
        }

        # Ignore any surfaces we don't track
        if surface not in surface_map:
            return

        record_attr = surface_map[surface]
        p1_wins, p2_wins = getattr(self, record_attr)

        if winner == self.player1:
            setattr(self, record_attr, (p1_wins + 1, p2_wins))
        elif winner == self.player2:
            setattr(self, record_attr, (p1_wins, p2_wins + 1))
    
    def get_recent_form_factor(self, for_player: str, matches: int = 5) -> float:
        """Get recent form factor based on last N meetings"""
        if not self.recent_matches or len(self.recent_matches) < matches:
            return 1.0
        
        recent = self.recent_matches[-matches:]
        wins = sum(1 for match in recent if match.winner == for_player)
        
        if matches == 0:
            return 1.0
        
        win_rate = wins / matches
        return 0.7 + (win_rate * 0.6)  # Range: 0.7 to 1.3
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'player1': self.player1,
            'player2': self.player2,
            'player1_wins': self.player1_wins,
            'player2_wins': self.player2_wins,
            'hard_court_record': list(self.hard_court_record),
            'clay_court_record': list(self.clay_court_record),
            'grass_court_record': list(self.grass_court_record),
            'recent_matches': [match.to_dict() for match in self.recent_matches],
            'last_meeting': self.last_meeting.to_dict() if self.last_meeting else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HeadToHeadRecord':
        """Create HeadToHeadRecord from dictionary"""
        # Convert lists back to tuples
        tuple_fields = ['hard_court_record', 'clay_court_record', 'grass_court_record']
        for field in tuple_fields:
            if field in data and isinstance(data[field], list):
                data[field] = tuple(data[field])
        
        # Convert match results
        if 'recent_matches' in data:
            recent_matches = []
            for match_data in data['recent_matches']:
                if isinstance(match_data, dict):
                    recent_matches.append(MatchResult.from_dict(match_data))
                else:
                    recent_matches.append(match_data)
            data['recent_matches'] = recent_matches
        
        if 'last_meeting' in data and data['last_meeting']:
            if isinstance(data['last_meeting'], dict):
                data['last_meeting'] = MatchResult.from_dict(data['last_meeting'])
        
        return cls(**data)