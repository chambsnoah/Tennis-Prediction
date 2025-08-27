"""
API-Based Tennis Data Extractor

This module replaces static file-based data extraction with real-time API-based
data extraction for tournaments and player information. It provides the same
interface as existing extractors but uses live data from tennis APIs.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

from ..clients.tennis_api_client import TennisAPIClient
from ..clients.base_client import APIException
from ..config.api_config import get_api_config
from ..models.player_stats import PlayerStats
from ..models.tournament_data import TournamentDraw


class APIPlayerExtractor:
    """
    Extract player data from tennis APIs, replacing static file extraction
    """
    
    def __init__(self, api_client: Optional[TennisAPIClient] = None, cache_results: bool = True):
        """
        Initialize API-based player extractor
        
        Args:
            api_client: Tennis API client instance
            cache_results: Whether to cache extracted data to files
        """
        if api_client is None:
            config = get_api_config()
            api_client = TennisAPIClient(config)
        
        self.api_client = api_client
        self.cache_results = cache_results
        
        # Statistics tracking
        self.extraction_stats = {
            'players_extracted': 0,
            'api_calls_made': 0,
            'cache_hits': 0,
            'extraction_errors': 0,
            'last_extraction': None
        }
    
    async def extract_tournament_players(self, 
                                       tournament_id: str,
                                       output_dir: Optional[str] = None,
                                       include_detailed_stats: bool = True) -> Dict[str, Dict]:
        """
        Extract all players for a tournament with enhanced API data
        
        Args:
            tournament_id: Tournament identifier
            output_dir: Directory to save extracted data (optional)
            include_detailed_stats: Whether to fetch detailed player statistics
            
        Returns:
            Dictionary of player data compatible with existing system
        """
        print(f"Extracting tournament players for {tournament_id} using API...")
        
        try:
            # Get tournament draw from API
            print("Fetching tournament draw...")
            tournament_draw = await self.api_client.get_tournament_draw(tournament_id)
            self.extraction_stats['api_calls_made'] += 1
            
            # Get all players from the draw
            all_players = tournament_draw.get_all_players()
            print(f"Found {len(all_players)} players in tournament")
            
            # Get current rankings for cost calculation
            print("Fetching current rankings...")
            try:
                atp_rankings = await self.api_client.get_rankings('atp')
                wta_rankings = await self.api_client.get_rankings('wta')
                self.extraction_stats['api_calls_made'] += 2
                
                rankings_dict = self._build_rankings_dict(atp_rankings, wta_rankings)
            except APIException as e:
                print(f"Warning: Could not fetch rankings: {e}")
                rankings_dict = {}
            
            # Extract enhanced player data
            enhanced_players = {}
            for i, player_name in enumerate(all_players):
                print(f"Processing player {i+1}/{len(all_players)}: {player_name}")
                
                try:
                    # Get comprehensive player stats if requested
                    if include_detailed_stats:
                        player_stats = await self.api_client.get_player_stats(
                            player_name, 
                            prefer_detailed=True
                        )
                        self.extraction_stats['api_calls_made'] += 1
                    else:
                        # Create basic PlayerStats
                        player_stats = PlayerStats(
                            name=player_name,
                            current_ranking=rankings_dict.get(player_name, 100)
                        )
                    
                    # Calculate enhanced cost based on multiple factors
                    cost = self._calculate_dynamic_cost(
                        player_stats, 
                        tournament_draw.surface,
                        tournament_draw.get_seed(player_name)
                    )
                    
                    # Build player data in existing system format
                    enhanced_players[player_name] = {
                        'seed': tournament_draw.get_seed(player_name),
                        'cost': cost,
                        'ranking': player_stats.current_ranking,
                        'nationality': player_stats.nationality,
                        'recent_form': player_stats.recent_form_factor,
                        'surface_preference': player_stats.get_surface_multiplier(tournament_draw.surface),
                        'serve_percentage': player_stats.serve_stats.first_serve_win_percentage if player_stats.serve_stats else 0.65,
                        'return_percentage': player_stats.return_stats.first_serve_return_points_won if player_stats.return_stats else 0.35,
                        'age': player_stats.age,
                        'api_extracted': True,
                        'last_updated': player_stats.last_updated.isoformat()
                    }
                    
                    self.extraction_stats['players_extracted'] += 1
                    
                except APIException as e:
                    print(f"Warning: Could not get detailed stats for {player_name}: {e}")
                    self.extraction_stats['extraction_errors'] += 1
                    
                    # Fallback to basic data
                    enhanced_players[player_name] = self._get_fallback_player_data(
                        player_name,
                        tournament_draw.get_seed(player_name),
                        rankings_dict.get(player_name, 100)
                    )
            
            # Cache results if requested
            if self.cache_results and output_dir:
                await self._cache_extracted_data(
                    enhanced_players, 
                    tournament_draw,
                    tournament_id, 
                    output_dir
                )
            
            self.extraction_stats['last_extraction'] = datetime.now()
            
            print(f"✓ Extraction completed: {len(enhanced_players)} players extracted")
            print(f"  API calls made: {self.extraction_stats['api_calls_made']}")
            print(f"  Errors: {self.extraction_stats['extraction_errors']}")
            
            return enhanced_players
            
        except Exception as e:
            print(f"Error during tournament extraction: {e}")
            raise APIException(f"Tournament extraction failed: {e}")
    
    def extract_tournament_players_sync(self, 
                                      tournament_id: str,
                                      output_dir: Optional[str] = None,
                                      include_detailed_stats: bool = True) -> Dict[str, Dict]:
        """Synchronous wrapper for extract_tournament_players"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.extract_tournament_players(tournament_id, output_dir, include_detailed_stats)
            )
        finally:
            loop.close()
    
    def _build_rankings_dict(self, atp_rankings: Dict, wta_rankings: Dict) -> Dict[str, int]:
        """Build a dictionary mapping player names to rankings"""
        rankings_dict = {}
        
        # Process ATP rankings
        if 'rankings' in atp_rankings:
            for player_data in atp_rankings['rankings']:
                name = player_data.get('name')
                ranking = player_data.get('ranking')
                if name and ranking:
                    rankings_dict[name] = ranking
        
        # Process WTA rankings
        if 'rankings' in wta_rankings:
            for player_data in wta_rankings['rankings']:
                name = player_data.get('name')
                ranking = player_data.get('ranking')
                if name and ranking:
                    rankings_dict[name] = ranking
        
        return rankings_dict
    
    def _calculate_dynamic_cost(self, 
                              player_stats: PlayerStats, 
                              surface: str,
                              seed: Optional[int] = None) -> float:
        """
        Calculate dynamic player cost based on multiple factors
        
        Args:
            player_stats: Player statistics
            surface: Tournament surface
            seed: Player seed (if any)
            
        Returns:
            Calculated cost value
        """
        # Base cost from ranking (lower ranking = higher cost)
        ranking = player_stats.current_ranking
        if ranking <= 10:
            base_cost = 100 - (ranking - 1) * 5  # Top 10: 95-100
        elif ranking <= 50:
            base_cost = 75 - (ranking - 10) * 1.25  # 11-50: 25-75
        else:
            base_cost = max(5, 25 - (ranking - 50) * 0.2)  # 51+: 5-25
        
        # Surface adjustment
        surface_multiplier = player_stats.get_surface_multiplier(surface)
        surface_adjusted_cost = base_cost * surface_multiplier
        
        # Form adjustment
        form_factor = player_stats.recent_form_factor
        form_adjusted_cost = surface_adjusted_cost * form_factor
        
        # Seed bonus (seeded players get slight cost increase)
        if seed and seed <= 32:
            seed_bonus = (33 - seed) * 0.5  # Small bonus for seeded players
            final_cost = form_adjusted_cost + seed_bonus
        else:
            final_cost = form_adjusted_cost
        
        # Ensure cost is within reasonable bounds
        return max(1.0, min(100.0, final_cost))
    
    def _get_fallback_player_data(self, 
                                player_name: str, 
                                seed: Optional[int],
                                ranking: int) -> Dict:
        """Generate fallback player data when API calls fail"""
        # Calculate basic cost from ranking and seed
        if seed and seed <= 8:
            cost = 95 - (seed - 1) * 5
        elif ranking <= 20:
            cost = 80 - (ranking - 1) * 2
        elif ranking <= 50:
            cost = 50 - (ranking - 20) * 1
        else:
            cost = max(10, 30 - (ranking - 50) * 0.3)
        
        return {
            'seed': seed,
            'cost': cost,
            'ranking': ranking,
            'nationality': 'Unknown',
            'recent_form': 1.0,
            'surface_preference': 1.0,
            'serve_percentage': 0.65,
            'return_percentage': 0.35,
            'age': 25,
            'api_extracted': False,
            'fallback_data': True,
            'last_updated': datetime.now().isoformat()
        }
    
    async def _cache_extracted_data(self, 
                                  players_data: Dict, 
                                  tournament_draw: TournamentDraw,
                                  tournament_id: str, 
                                  output_dir: str):
        """Cache extracted data to files for compatibility"""
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Save players data in existing format
            players_file = output_path / 'players.json'
            with open(players_file, 'w') as f:
                json.dump(players_data, f, indent=2)
            
            # Save tournament draw data
            tournament_file = output_path / 'tournament_draw.json'
            with open(tournament_file, 'w') as f:
                json.dump(tournament_draw.to_dict(), f, indent=2)
            
            # Save extraction metadata
            metadata = {
                'tournament_id': tournament_id,
                'extraction_time': datetime.now().isoformat(),
                'player_count': len(players_data),
                'api_calls_made': self.extraction_stats['api_calls_made'],
                'extraction_errors': self.extraction_stats['extraction_errors'],
                'surface': tournament_draw.surface,
                'tournament_name': tournament_draw.tournament_name
            }
            
            metadata_file = output_path / 'extraction_metadata.json'
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✓ Data cached to {output_dir}")
        except (OSError, IOError) as e:
            print(f"Warning: Failed to cache data: {e}")
            # Don't raise—caching is not critical to the operation
    
    def get_extraction_stats(self) -> Dict:
        """Get extraction statistics"""
        return {
            **self.extraction_stats,
            'api_client_stats': self.api_client.get_client_stats()
        }
    
    def reset_stats(self):
        """Reset extraction statistics"""
        self.extraction_stats = {
            'players_extracted': 0,
            'api_calls_made': 0,
            'cache_hits': 0,
            'extraction_errors': 0,
            'last_extraction': None
        }


class EnhancedExtractor:
    """
    Enhanced extractor that combines API data with existing static data
    for maximum reliability and data richness.
    """
    
    def __init__(self, static_extractor_class=None):
        """
        Initialize enhanced extractor
        
        Args:
            static_extractor_class: Existing static extractor class for fallback
        """
        self.api_extractor = APIPlayerExtractor()
        self.static_extractor = static_extractor_class() if static_extractor_class else None
        
    async def extract_with_fallback(self, 
                                  tournament_id: str, 
                                  static_data_path: Optional[str] = None,
                                  output_dir: Optional[str] = None) -> Dict[str, Dict]:
        """
        Extract player data with API-first approach and static fallback
        
        Args:
            tournament_id: Tournament identifier
            static_data_path: Path to static data files for fallback
            output_dir: Output directory for cached results
            
        Returns:
            Enhanced player data dictionary
        """
        print(f"Enhanced extraction for {tournament_id}")
        
        # Try API extraction first
        try:
            print("Attempting API extraction...")
            api_data = await self.api_extractor.extract_tournament_players(
                tournament_id, output_dir, include_detailed_stats=True
            )
            
            print(f"✓ API extraction successful: {len(api_data)} players")
            return api_data
            
        except APIException as e:
            print(f"API extraction failed: {e}")
            
            # Fallback to static extraction if available
            if self.static_extractor and static_data_path:
                print("Falling back to static data extraction...")
                try:
                    static_data = self.static_extractor.extract_players(static_data_path)
                    print(f"✓ Static extraction successful: {len(static_data)} players")
                    
                    # Mark data as static
                    for player_name in static_data:
                        static_data[player_name]['api_extracted'] = False
                        static_data[player_name]['static_fallback'] = True
                    
                    return static_data
                    
                except Exception as static_error:
                    print(f"Static extraction also failed: {static_error}")
                    raise APIException(f"Both API and static extraction failed: {e}, {static_error}")
            else:
                raise APIException(f"API extraction failed and no fallback available: {e}")
    
    def extract_with_fallback_sync(self, 
                                 tournament_id: str, 
                                 static_data_path: Optional[str] = None,
                                 output_dir: Optional[str] = None) -> Dict[str, Dict]:
        """Synchronous wrapper for extract_with_fallback"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.extract_with_fallback(tournament_id, static_data_path, output_dir)
            )
        finally:
            loop.close()


def create_api_extractor_for_tournament(tournament_path: str) -> APIPlayerExtractor:
    """
    Create API extractor configured for a specific tournament directory
    
    Args:
        tournament_path: Path to tournament directory (e.g., '2024/us2024')
        
    Returns:
        Configured APIPlayerExtractor instance
    """
    # Determine tournament ID from path
    # Determine tournament ID from path
    path_parts = tournament_path.split('/')
    if len(path_parts) >= 2:
        year = path_parts[0]
        tournament = path_parts[1]
        # Validate year format
        if not year.isdigit() or len(year) != 4:
            print(f"Warning: Invalid year format '{year}', using raw path")
            tournament_id = tournament_path.replace('/', '_')
        else:
            tournament_id = f"{tournament}_{year}"
    else:
        tournament_id = tournament_path
    
    print(f"Creating API extractor for tournament: {tournament_id}")
    
    extractor = APIPlayerExtractor(cache_results=True)
    return extractor


# Example usage and testing functions
async def test_extraction_example():
    """Example of how to use the API extractor"""
    print("=== API Extractor Test Example ===")
    
    try:
        extractor = APIPlayerExtractor()
        
        # Test with a real tournament (this would make API calls)
        # players = await extractor.extract_tournament_players(
        #     'us_open_2024',
        #     output_dir='./extracted_data'
        # )
        
        # For testing, just demonstrate the interface
        print("API extractor initialized successfully")
        print("To test with real data, uncomment the extraction call above")
        
        stats = extractor.get_extraction_stats()
        print(f"Extraction stats: {stats}")
        
    except Exception as e:
        print(f"Test extraction failed: {e}")


if __name__ == "__main__":
    # Run example test
    asyncio.run(test_extraction_example())