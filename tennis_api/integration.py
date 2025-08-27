"""
Tennis API Integration with Existing Prediction System

This module provides integration between the new API-based tennis data system
and the existing tennis prediction codebase. It extends existing classes and
provides API-enhanced functionality while maintaining backward compatibility.
"""

import sys
from pathlib import Path
from typing import Dict, Optional, Any
import json
import asyncio

# Add tennis_preds to path for importing existing classes
sys.path.append(str(Path(__file__).parent.parent))

# Import handling with fallback - suppress type errors for conditional imports
try:
    from tennis_preds.tennis import Player as TennisPlayer, PlayerSimple as TennisPlayerSimple, TennisMatch as TennisMatchBase  # type: ignore
    TENNIS_PREDS_AVAILABLE = True
except ImportError:
    print("Warning: Could not import tennis_preds module. Make sure the path is correct.")
    TENNIS_PREDS_AVAILABLE = False
    
    # Define placeholder classes for development
    class TennisPlayer:  # type: ignore
        def __init__(self, name: str, first_serve_percentage: float = 0.6, second_serve_percentage: float = 0.9, 
                     first_serve_win_percentage: float = 0.7, second_serve_win_percentage: float = 0.5):
            self.name = name
            self.first_serve_percentage = first_serve_percentage
            self.second_serve_percentage = second_serve_percentage
            self.first_serve_win_percentage = first_serve_win_percentage
            self.second_serve_win_percentage = second_serve_win_percentage
    
    class TennisPlayerSimple:  # type: ignore
        def __init__(self, name: str, points_won_on_serve_percentage: float = 0.6):
            self.name = name
            self.points_won_on_serve_percentage = points_won_on_serve_percentage
    
    class TennisMatchBase:  # type: ignore
        def __init__(self, player1: Any, player2: Any, sets_to_win: int = 3, player1_to_serve: bool = True, seed: Optional[int] = None):
            self.player1 = player1
            self.player2 = player2

from .clients.tennis_api_client import TennisAPIClient
from .models.player_stats import PlayerStats
from .extractors.api_extractor import APIPlayerExtractor
from .config.api_config import get_api_config


class PlayerEnhanced(TennisPlayer):
    """
    Enhanced Player class with real-time API data integration
    
    Extends the existing Player class to incorporate real-time statistics
    from tennis APIs while maintaining full compatibility with the existing
    tennis simulation system.
    """
    
    def __init__(self, name: str, api_stats: Optional[PlayerStats] = None, 
                 surface: str = 'hard', opponent_ranking: int = 100, **kwargs):
        """
        Initialize enhanced player with API data
        
        Args:
            name: Player name
            api_stats: PlayerStats from API (if available)
            surface: Tournament surface for adjustments
            opponent_ranking: Opponent's ranking for strength adjustments
            **kwargs: Fallback values for traditional Player initialization
        """
        # Initialize with API data if available
        if api_stats:
            # Use API statistics
            first_serve_pct = api_stats.serve_stats.first_serve_percentage
            second_serve_pct = 0.95  # Assume high second serve percentage
            first_serve_win = api_stats.serve_stats.first_serve_win_percentage
            second_serve_win = api_stats.serve_stats.second_serve_win_percentage
            
            # Apply surface and form adjustments
            surface_multiplier = api_stats.get_surface_multiplier(surface)
            form_factor = api_stats.recent_form_factor
            
            # Adjust serve percentages based on surface and form
            first_serve_win_adjusted = min(0.95, first_serve_win * surface_multiplier * form_factor)
            second_serve_win_adjusted = min(0.90, second_serve_win * surface_multiplier * form_factor)
            
        else:
            # Fallback to provided values or defaults
            first_serve_pct = kwargs.get('first_serve_percentage', 0.6)
            second_serve_pct = kwargs.get('second_serve_percentage', 0.95)
            first_serve_win_adjusted = kwargs.get('first_serve_win_percentage', 0.7)
            second_serve_win_adjusted = kwargs.get('second_serve_win_percentage', 0.5)
        
        # Initialize base Player class
        super().__init__(
            name=name,
            first_serve_percentage=first_serve_pct,
            second_serve_percentage=second_serve_pct,
            first_serve_win_percentage=first_serve_win_adjusted,
            second_serve_win_percentage=second_serve_win_adjusted
        )
        
        # Store enhanced attributes
        self.api_stats = api_stats
        self.current_ranking = api_stats.current_ranking if api_stats else 100
        self.surface_performance = self._calculate_surface_performance(surface)
        self.recent_form_factor = api_stats.recent_form_factor if api_stats else 1.0
        self.opponent_ranking = opponent_ranking
        self.enhanced_cost = self._calculate_enhanced_cost()
        self.seed = None  # Will be set later if available
        
        # API-enhanced attributes
        self.nationality = api_stats.nationality if api_stats else 'Unknown'
        self.age = api_stats.age if api_stats else 25
        self.injury_status = api_stats.injury_status if api_stats else 'Healthy'
        self.last_updated = api_stats.last_updated if api_stats else None
    
    def _calculate_surface_performance(self, surface: str) -> float:
        """Calculate surface-specific performance factor"""
        if not self.api_stats:
            return 1.0
        
        return self.api_stats.get_surface_multiplier(surface)
    
    def _calculate_enhanced_cost(self) -> float:
        """Calculate enhanced cost based on multiple factors"""
        if not self.api_stats:
            return self._calculate_basic_cost()
        
        # Base cost from ranking
        ranking = self.current_ranking
        if ranking <= 10:
            base_cost = 27000 - (ranking - 1) * 1000
        elif ranking <= 32:
            base_cost = 18000 - (ranking - 10) * 300
        elif ranking <= 64:
            base_cost = 12000 - (ranking - 32) * 200
        else:
            base_cost = max(5000, 6000 - (ranking - 64) * 50)
        
        # Apply form factor
        form_adjusted = base_cost * self.recent_form_factor
        
        # Apply surface factor
        surface_adjusted = form_adjusted * self.surface_performance
        
        return max(5000, min(30000, surface_adjusted))
    
    def _calculate_basic_cost(self) -> float:
        """Calculate basic cost when no API data available"""
        # Use existing cost calculation based on ranking
        ranking = self.current_ranking
        if ranking <= 10:
            return 25000
        elif ranking <= 32:
            return 15000
        elif ranking <= 64:
            return 8000
        else:
            return 5000
    
    def get_adjusted_serve_percentage(self, surface: Optional[str] = None, opponent_ranking: Optional[int] = None) -> float:
        """Get dynamically adjusted serve percentage"""
        base_percentage = self.first_serve_win_percentage
        
        # Apply surface adjustment
        if surface and self.api_stats:
            surface_factor = self.api_stats.get_surface_multiplier(surface)
            base_percentage *= surface_factor
        
        # Apply opponent strength adjustment
        if opponent_ranking:
            ranking_diff = self.current_ranking - opponent_ranking
            # Cap adjustment between 0.9 and 1.1 for realistic bounds
            opponent_factor = max(0.9, min(1.1, 1.0 + (ranking_diff * 0.001)))
            base_percentage *= opponent_factor
        
        return min(max(base_percentage, 0.3), 0.95)
    
    def get_head_to_head_factor(self, opponent_name: str) -> float:
        """Get head-to-head performance factor against specific opponent"""
        if not self.api_stats or opponent_name not in self.api_stats.head_to_head:
            return 1.0
        
        return self.api_stats.get_head_to_head_factor(opponent_name)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON export (compatible with existing format)"""
        return {
            'name': self.name,
            'seed': getattr(self, 'seed', None),
            'cost': self.enhanced_cost,
            'ranking': self.current_ranking,
            'nationality': self.nationality,
            'age': self.age,
            'surface_performance': self.surface_performance,
            'recent_form': self.recent_form_factor,
            'serve_percentage': self.first_serve_win_percentage,
            'return_percentage': self.api_stats.return_stats.first_serve_return_points_won if self.api_stats else 0.35,
            'injury_status': self.injury_status,
            'api_enhanced': True,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }


class PlayerSimpleEnhanced(TennisPlayerSimple):
    """Enhanced simple player with API data"""
    
    def __init__(self, name: str, api_stats: Optional[PlayerStats] = None, surface: str = 'hard', **kwargs):
        # Calculate overall serve percentage from API stats
        if api_stats:
            # Weighted average of first and second serve win percentages
            first_serve_pct = api_stats.serve_stats.first_serve_percentage
            first_serve_win = api_stats.serve_stats.first_serve_win_percentage
            second_serve_win = api_stats.serve_stats.second_serve_win_percentage
            
            # Calculate overall serve percentage
            overall_serve_pct = (first_serve_pct * first_serve_win + 
                               (1 - first_serve_pct) * second_serve_win)
            
            # Apply surface and form adjustments
            surface_factor = api_stats.get_surface_multiplier(surface)
            form_factor = api_stats.recent_form_factor
            
            adjusted_serve_pct = overall_serve_pct * surface_factor * form_factor
        else:
            adjusted_serve_pct = kwargs.get('points_won_on_serve_percentage', 0.6)
        
        super().__init__(name, min(max(adjusted_serve_pct, 0.3), 0.9))
        
        self.api_stats = api_stats
        self.surface = surface


class APITournamentExtractor:
    """
    Tournament extractor that integrates API data with existing tournament structure
    """
    
    def __init__(self, api_client: Optional[TennisAPIClient] = None):
        if api_client is None:
            config = get_api_config()
            api_client = TennisAPIClient(config)
        
        self.api_client = api_client
        self.api_extractor = APIPlayerExtractor(api_client)
    
    async def extract_tournament_with_api(self, 
                                        tournament_id: str,
                                        tournament_path: str,
                                        surface: str = 'hard') -> Dict[str, Dict]:
        """
        Extract tournament data using API with fallback to existing files
        
        Args:
            tournament_id: Tournament identifier for API
            tournament_path: Path to existing tournament directory
            surface: Tournament surface
            
        Returns:
            Player data dictionary compatible with existing system
        """
        print(f"Extracting tournament {tournament_id} with API enhancement...")
        
        try:
            # Try API extraction first
            api_players = await self.api_extractor.extract_tournament_players(
                tournament_id, 
                include_detailed_stats=True
            )
            
            print(f"✓ API extraction successful: {len(api_players)} players")
            
            # Convert to existing format with enhancements
            enhanced_players = {}
            for player_name, api_data in api_players.items():
                enhanced_players[player_name] = {
                    'seed': api_data.get('seed'),
                    'cost': api_data.get('cost', 10000),
                    'p_factor': 0.02,  # Default positive factor
                    'n_factor': 0,     # Default negative factor
                    'ranking': api_data.get('ranking', 100),
                    'api_enhanced': True,
                    'surface_factor': api_data.get('surface_preference', 1.0),
                    'form_factor': api_data.get('recent_form', 1.0)
                }
            
            return enhanced_players
            
        except Exception as e:
            print(f"API extraction failed: {e}")
            print("Falling back to existing file extraction...")
            
            # Fallback to existing file extraction
            return self._extract_from_existing_files(tournament_path, surface)
    
    def _extract_from_existing_files(self, tournament_path: str, surface: str) -> Dict[str, Dict]:
        """Extract from existing JSON files as fallback"""
        try:
            # Try to load existing players.json files
            players_male_path = Path(tournament_path) / 'players_male.json'
            players_female_path = Path(tournament_path) / 'players_female.json'
            
            combined_players = {}
            
            if players_male_path.exists():
                with open(players_male_path, 'r') as f:
                    male_players = json.load(f)
                    combined_players.update(male_players)
                    print(f"Loaded {len(male_players)} male players from existing file")
            
            if players_female_path.exists():
                with open(players_female_path, 'r') as f:
                    female_players = json.load(f)
                    combined_players.update(female_players)
                    print(f"Loaded {len(female_players)} female players from existing file")
            
            # Mark as not API enhanced
            for player_name in combined_players:
                combined_players[player_name]['api_enhanced'] = False
                combined_players[player_name]['surface_factor'] = 1.0
                combined_players[player_name]['form_factor'] = 1.0
            
            return combined_players
            
        except Exception as e:
            print(f"Fallback extraction also failed: {e}")
            raise Exception(f"Both API and file extraction failed")
    
    def extract_tournament_with_api_sync(self, tournament_id: str, tournament_path: str, surface: str = 'hard') -> Dict[str, Dict]:
        """Synchronous wrapper that handles existing event loops properly"""
        try:
            # Check if there's already a running event loop
            running_loop = asyncio.get_running_loop()
            
            # If we're in an async context, use run_coroutine_threadsafe
            if running_loop:
                # Create the coroutine
                coro = self.extract_tournament_with_api(tournament_id, tournament_path, surface)
                
                # Submit to the running loop from a thread
                future = asyncio.run_coroutine_threadsafe(coro, running_loop)
                
                # Wait for result and propagate any exceptions
                return future.result()
            
        except RuntimeError:
            # No running loop, we can create our own
            pass
        
        # Create and manage our own event loop
        loop = asyncio.new_event_loop()
        loop_created_by_us = True
        
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                self.extract_tournament_with_api(tournament_id, tournament_path, surface)
            )
        finally:
            # Only close the loop if we created it
            if loop_created_by_us:
                loop.close()
                asyncio.set_event_loop(None)


class EnhancedTennisMatch(TennisMatchBase):
    """Enhanced tennis match with API-driven player creation"""
    
    def __init__(self, player1_name: str, player2_name: str, 
                 surface: str = 'hard', tournament_id: Optional[str] = None,
                 api_client: Optional[TennisAPIClient] = None, **kwargs):
        """
        Initialize enhanced tennis match
        
        Args:
            player1_name: First player name
            player2_name: Second player name
            surface: Tournament surface
            tournament_id: Tournament identifier for context
            api_client: API client for player data
            **kwargs: Additional arguments for TennisMatch
        """
        self.surface = surface
        self.tournament_id = tournament_id
        self.api_client = api_client or TennisAPIClient()
        
        # Create enhanced players
        player1 = self._create_enhanced_player(player1_name, player2_name)
        player2 = self._create_enhanced_player(player2_name, player1_name)
        
        # Initialize base match
        super().__init__(player1, player2, **kwargs)
        
        # Store enhanced attributes
        self.player1_enhanced = player1
        self.player2_enhanced = player2
    
    def _create_enhanced_player(self, player_name: str, opponent_name: str) -> PlayerEnhanced:
        """Create enhanced player with API data"""
        try:
            # Try to get API stats
            api_stats = self.api_client.get_player_stats_sync(player_name)
            
            # Get opponent ranking for adjustments
            try:
                opponent_stats = self.api_client.get_player_stats_sync(opponent_name)
                opponent_ranking = opponent_stats.current_ranking
            except:
                opponent_ranking = 100
            
            return PlayerEnhanced(
                name=player_name,
                api_stats=api_stats,
                surface=self.surface,
                opponent_ranking=opponent_ranking
            )
            
        except Exception as e:
            print(f"Could not get API stats for {player_name}: {e}")
            # Fallback to basic player
            return PlayerEnhanced(
                name=player_name,
                surface=self.surface,
                opponent_ranking=100
            )
    
    def get_match_prediction_factors(self) -> Dict:
        """Get enhanced prediction factors for the match"""
        factors = {
            'player1_ranking': self.player1_enhanced.current_ranking,
            'player2_ranking': self.player2_enhanced.current_ranking,
            'ranking_difference': abs(self.player1_enhanced.current_ranking - self.player2_enhanced.current_ranking),
            'player1_form': self.player1_enhanced.recent_form_factor,
            'player2_form': self.player2_enhanced.recent_form_factor,
            'player1_surface_factor': self.player1_enhanced.surface_performance,
            'player2_surface_factor': self.player2_enhanced.surface_performance,
            'surface': self.surface,
            'predicted_favorite': self.player1.name if self.player1_enhanced.current_ranking < self.player2_enhanced.current_ranking else self.player2.name
        }
        
        # Add head-to-head factor if available
        if self.player1_enhanced.api_stats:
            factors['player1_h2h_factor'] = self.player1_enhanced.get_head_to_head_factor(self.player2.name)
        if self.player2_enhanced.api_stats:
            factors['player2_h2h_factor'] = self.player2_enhanced.get_head_to_head_factor(self.player1.name)
        
        return factors


def create_enhanced_players_from_tournament(tournament_path: str, 
                                          tournament_id: Optional[str] = None,
                                          surface: str = 'hard') -> Dict[str, PlayerEnhanced]:
    """
    Create enhanced players from tournament data
    
    Args:
        tournament_path: Path to tournament directory
        tournament_id: Tournament ID for API lookup
        surface: Tournament surface
        
    Returns:
        Dictionary of enhanced players
    """
    print(f"Creating enhanced players for tournament: {tournament_path}")
    
    # Initialize extractor
    extractor = APITournamentExtractor()
    
    try:
        # Extract with API if tournament_id provided
        if tournament_id:
            player_data = extractor.extract_tournament_with_api_sync(
                tournament_id, tournament_path, surface
            )
        else:
            # Use existing files only
            player_data = extractor._extract_from_existing_files(tournament_path, surface)
        
        # Create enhanced players
        enhanced_players = {}
        for player_name, data in player_data.items():
            try:
                if data.get('api_enhanced', False):
                    # Player already has API data from extraction, create without new API call
                    player = PlayerEnhanced(
                        name=player_name,
                        api_stats=data.get('api_stats'),  # Assuming stats were stored
                        surface=surface
                    )
                else:
                    # Create basic enhanced player
                    player = PlayerEnhanced(
                        name=player_name,
                        surface=surface,
                        first_serve_win_percentage=0.7,
                        second_serve_win_percentage=0.5
                    )
                
                # Set additional attributes from data
                player.seed = data.get('seed')
                player.enhanced_cost = data.get('cost', 10000)
                
                enhanced_players[player_name] = player
                
            except Exception as e:
                print(f"Error creating enhanced player {player_name}: {e}")
                # Create basic player as fallback
                enhanced_players[player_name] = PlayerEnhanced(
                    name=player_name,
                    surface=surface
                )
        
        print(f"✓ Created {len(enhanced_players)} enhanced players")
        return enhanced_players
        
    except Exception as e:
        print(f"Error in enhanced player creation: {e}")
        raise


# Example usage functions
def run_enhanced_simulation_example():
    """Example of running simulation with enhanced players"""
    print("=== Enhanced Tennis Simulation Example ===")
    
    try:
        # Create enhanced match
        match = EnhancedTennisMatch(
            player1_name="Novak Djokovic",
            player2_name="Carlos Alcaraz",
            surface="hard",
            sets_to_win=3
        )
        
        # Get prediction factors
        factors = match.get_match_prediction_factors()
        print("Match Prediction Factors:")
        for key, value in factors.items():
            print(f"  {key}: {value}")
        
        # Run simulation (if simulate_match method exists)
        if hasattr(match, 'simulate_match'):
            print("\nRunning match simulation...")
            # match.simulate_match(verbose=False)
            print("Simulation completed (method not available in this example)")
        
        print("✓ Enhanced simulation example completed")
        
    except Exception as e:
        print(f"Enhanced simulation example failed: {e}")


if __name__ == "__main__":
    # Run example
    run_enhanced_simulation_example()