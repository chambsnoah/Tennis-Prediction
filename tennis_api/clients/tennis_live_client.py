"""
Tennis Live Data API Client

Primary API client for tennis live data, tournament draws, and match information.
This client handles real-time tennis data from RapidAPI tennis services.
"""

from datetime import datetime
from typing import Dict, List, Optional

try:
    from dateutil import parser as dateutil_parser
except ImportError:
    dateutil_parser = None

from .base_client import BaseAPIClient, APIException
from ..models.player_stats import PlayerStats, ServeStatistics, ReturnStatistics
from ..models.tournament_data import TournamentDraw, Match
from ..models.match_data import MatchResult


class TennisLiveAPIClient(BaseAPIClient):
    """Client for tennis live data API"""
    
    async def get_player_stats(self, player_name: str, player_id: Optional[str] = None) -> PlayerStats:  # type: ignore[override]
        """
        Get comprehensive player statistics
        
        Args:
            player_name: Player name
            player_id: Optional player ID for more accurate lookup
            
        Returns:
            PlayerStats object with comprehensive data
        """
        try:
            # Validate player_name parameter
            if player_name is None or not isinstance(player_name, str):
                raise APIException("Player name must be a non-empty string")
            
            player_name_clean = player_name.strip()
            if not player_name_clean:
                raise APIException("Player name cannot be empty or whitespace only")
            
            # Validate player_id parameter if provided
            if player_id is not None and not isinstance(player_id, str):
                raise APIException("Player ID must be a string if provided")
            
            # If we have player_id, use it directly
            if player_id:
                response = await self.get_data_async(
                    'player_matches',
                    player_id=player_id,
                    priority='high'
                )
            else:
                # Search for player first
                search_response = await self.get_data_async(
                    'player_search',
                    params={'name': player_name_clean},
                    priority='high'
                )
                
                if not search_response.get('players'):
                    raise APIException(f"Player '{player_name_clean}' not found")
                
                # Get the first matching player with bounds checking
                players_list = search_response['players']
                if len(players_list) == 0:
                    raise APIException(f"No players found for '{player_name_clean}'")
                
                player_data = players_list[0]
                player_id = player_data.get('id')
                
                if not player_id:
                    raise APIException(f"Could not find ID for player '{player_name_clean}'")
                
                # Get player matches for statistics
                response = await self.get_data_async(
                    'player_matches',
                    player_id=player_id,
                    priority='high'
                )
            
            # Parse player statistics from API response
            return self._parse_player_stats(response, player_name_clean)
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get player stats for {player_name}: {e}")
    
    async def get_rankings(self, tour: str = 'atp', limit: int = 100) -> Dict:
        """
        Get current tennis rankings
        
        Args:
            tour: Tournament tour ('atp' or 'wta')
            limit: Number of rankings to retrieve
            
        Returns:
            Rankings data dictionary
        """
        try:
            # Validate tour parameter
            if tour is None or not isinstance(tour, str):
                raise APIException("Tour parameter must be a non-empty string")
            
            tour_lower = tour.lower().strip()
            if tour_lower not in ['atp', 'wta']:
                raise APIException(f"Invalid tour '{tour}'. Must be 'atp' or 'wta'")
            
            response = await self.get_data_async(
                'rankings',
                type=tour_lower,
                params={'limit': limit},
                priority='high'
            )
            
            return response
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get {tour} rankings: {e}")
    
    async def get_tournament_draw(self, tournament_id: str) -> TournamentDraw:
        """
        Get tournament draw and bracket information
        
        Args:
            tournament_id: Tournament identifier
            
        Returns:
            TournamentDraw object with complete tournament information
        """
        try:
            response = await self.get_data_async(
                'tournament_draw',
                tournament_id=tournament_id,
                priority='critical'
            )
            
            return self._parse_tournament_draw(response, tournament_id)
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get tournament draw for {tournament_id}: {e}")
    
    async def get_live_matches(self) -> List[Dict]:
        """
        Get currently live tennis matches
        
        Returns:
            List of live match data
        """
        try:
            response = await self.get_data_async(
                'live_matches',
                use_cache=False,  # Don't cache live data
                priority='critical'
            )
            
            return response.get('matches', [])
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get live matches: {e}")
    
    async def get_match_details(self, match_id: str) -> MatchResult:
        """
        Get detailed match information and statistics
        
        Args:
            match_id: Match identifier
            
        Returns:
            MatchResult object with detailed match data
        """
        try:
            response = await self.get_data_async(
                'match_details',
                match_id=match_id,
                priority='normal'
            )
            
            return self._parse_match_result(response)
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get match details for {match_id}: {e}")
    
    async def get_tournaments(self, year: Optional[int] = None, surface: Optional[str] = None) -> List[Dict]:
        """
        Get list of tournaments
        
        Args:
            year: Tournament year filter
            surface: Surface type filter ('hard', 'clay', 'grass')
            
        Returns:
            List of tournament data
        """
        try:
            # Validate surface parameter if provided
            if surface is not None:
                if not isinstance(surface, str):
                    raise APIException("Surface parameter must be a string")
                
                surface_lower = surface.lower().strip()
                if surface_lower not in ['hard', 'clay', 'grass', 'carpet']:
                    raise APIException(f"Invalid surface '{surface}'. Must be one of: 'hard', 'clay', 'grass', 'carpet'")
                surface = surface_lower
            
            params = {}
            if year:
                params['year'] = year
            if surface:
                params['surface'] = surface
            
            response = await self.get_data_async(
                'tournaments',
                params=params if params else None,
                priority='low'
            )
            
            return response.get('tournaments', [])
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get tournaments: {e}")
    
    def _parse_player_stats(self, api_data: Dict, player_name: str) -> PlayerStats:
        """Parse API response into PlayerStats object"""
        try:
            # Extract player information
            player_info = api_data.get('player', {})
            matches = api_data.get('matches', [])
            
            # Basic player info
            name = player_info.get('name', player_name)
            ranking = player_info.get('ranking', 100)
            nationality = player_info.get('nationality', 'Unknown')
            age = player_info.get('age', 25)
            height = player_info.get('height_cm', 180)
            weight = player_info.get('weight_kg', 75)
            plays = player_info.get('plays', 'Right')
            
            # Calculate statistics from recent matches
            serve_stats, return_stats, recent_form = self._calculate_stats_from_matches(matches)
            
            # Create PlayerStats object
            player_stats = PlayerStats(
                name=name,
                current_ranking=ranking,
                nationality=nationality,
                age=age,
                height_cm=height,
                weight_kg=weight,
                plays=plays,
                serve_stats=serve_stats,
                return_stats=return_stats,
                recent_matches=recent_form,
                last_updated=datetime.now()
            )
            
            # Calculate recent form factor
            try:
                player_stats.recent_form_factor = player_stats.calculate_form_factor()
            except Exception:
                # Set a default value if calculation fails
                player_stats.recent_form_factor = 0.5
            
            return player_stats
            
        except Exception as e:
            # Return basic PlayerStats if parsing fails
            return PlayerStats(
                name=player_name,
                last_updated=datetime.now()
            )
    def _calculate_stats_from_matches(self, matches: List[Dict]) -> tuple:
        """Calculate serve/return stats and recent form from match data"""
        if not matches:
            return (ServeStatistics(), ReturnStatistics(), [])
        
        # Aggregate statistics from matches
        total_matches = len(matches)
        
        # Serve statistics
        first_serves_made = 0
        first_serves_won = 0
        second_serves_made = 0
        second_serves_won = 0
        
        # Return statistics  
        first_serve_return_points = 0
        first_serve_return_won = 0
        second_serve_return_points = 0
        second_serve_return_won = 0
        
        # Recent form
        recent_form = []
        
        for match in matches[:10]:  # Last 10 matches
            # Extract match result for form
            if 'winner' in match and 'player' in match:
                if match['winner'] == match['player']:
                    recent_form.append('W')
                else:
                    recent_form.append('L')
            
            # Extract detailed serve/return statistics if available
            stats = match.get('statistics', {})
            
            # Process serve statistics with better granularity
            if 'first_serve_made' in stats and 'first_serve_won' in stats:
                first_serves_made += max(0, stats.get('first_serve_made', 0))
                first_serves_won += max(0, stats.get('first_serve_won', 0))
            elif 'serve_points_won' in stats:  # Fallback to combined serve stats
                serves_won = max(0, stats.get('serve_points_won', 0))
                serves_total = max(1, stats.get('serve_points_total', 1))
                # Estimate first/second serve split (typical: ~60% first serve)
                estimated_first_serves = int(serves_total * 0.6)
                estimated_first_won = int(serves_won * 0.65)  # First serves typically won more
                first_serves_made += estimated_first_serves
                first_serves_won += min(estimated_first_won, estimated_first_serves)
            
            if 'second_serve_made' in stats and 'second_serve_won' in stats:
                second_serves_made += max(0, stats.get('second_serve_made', 0))
                second_serves_won += max(0, stats.get('second_serve_won', 0))
            elif 'serve_points_won' in stats:  # Fallback estimation for second serves
                serves_won = max(0, stats.get('serve_points_won', 0))
                serves_total = max(1, stats.get('serve_points_total', 1))
                estimated_second_serves = int(serves_total * 0.4)
                estimated_second_won = serves_won - min(int(serves_won * 0.65), int(serves_total * 0.6))
                second_serves_made += estimated_second_serves
                second_serves_won += max(0, min(estimated_second_won, estimated_second_serves))
            
            # Process return statistics with better accuracy
            if 'first_serve_return_points' in stats:
                first_serve_return_points += max(0, stats.get('first_serve_return_points', 0))
                first_serve_return_won += max(0, stats.get('first_serve_return_won', 0))
            
            if 'second_serve_return_points' in stats:
                second_serve_return_points += max(0, stats.get('second_serve_return_points', 0))
                second_serve_return_won += max(0, stats.get('second_serve_return_won', 0))
            
            elif 'return_points_won' in stats:  # Fallback for combined return stats
                return_won = max(0, stats.get('return_points_won', 0))
                # Estimate return opportunities based on typical match patterns
                estimated_return_points = max(1, stats.get('return_points_total', total_matches * 45))
                # Split return points (typical: ~60% against first serves)
                first_return_est = int(estimated_return_points * 0.6)
                second_return_est = estimated_return_points - first_return_est
                first_serve_return_points += first_return_est
                second_serve_return_points += second_return_est
                # Distribute won points (second serve returns typically more successful)
                first_return_won_est = int(return_won * 0.4)
                second_return_won_est = return_won - first_return_won_est
                first_serve_return_won += first_return_won_est
                second_serve_return_won += second_return_won_est
        
        # Calculate realistic percentages with proper bounds
        first_serve_win_pct = first_serves_won / max(first_serves_made, 1)
        second_serve_win_pct = second_serves_won / max(second_serves_made, 1)
        
        first_return_win_pct = first_serve_return_won / max(first_serve_return_points, 1)
        second_return_win_pct = second_serve_return_won / max(second_serve_return_points, 1)
        
        # Apply realistic tennis bounds (based on professional tennis statistics)
        serve_stats = ServeStatistics(
            first_serve_win_percentage=max(0.45, min(first_serve_win_pct, 0.85)),  # Typical range: 45-85%
            second_serve_win_percentage=max(0.35, min(second_serve_win_pct, 0.75))  # Typical range: 35-75%
        )
        
        return_stats = ReturnStatistics(
            first_serve_return_points_won=max(0.15, min(first_return_win_pct, 0.55)),  # Typical range: 15-55%
            second_serve_return_points_won=max(0.25, min(second_return_win_pct, 0.65))  # Typical range: 25-65%
        )
        
        return serve_stats, return_stats, recent_form
    
    def _parse_tournament_draw(self, api_data: Dict, tournament_id: str) -> TournamentDraw:
        """Parse API response into TournamentDraw object"""
        try:
            tournament_info = api_data.get('tournament', {})
            matches = api_data.get('matches', [])
            
            # Basic tournament info
            name = tournament_info.get('name', f'Tournament {tournament_id}')
            surface = tournament_info.get('surface', 'hard')
            year = tournament_info.get('year', datetime.now().year)
            location = tournament_info.get('location', 'Unknown')
            draw_size = tournament_info.get('draw_size', 128)
            
            # Create tournament draw
            tournament_draw = TournamentDraw(
                tournament_id=tournament_id,
                tournament_name=name,
                year=year,
                surface=surface,
                category=tournament_info.get('category', 'Unknown'),
                location=location,
                draw_size=draw_size,
                last_updated=datetime.now()
            )
            
            # Parse matches and organize by rounds
            for match_data in matches:
                match = self._parse_match_from_draw(match_data)
                tournament_draw.add_match(match)
            
            # Extract seeded players
            seeds = api_data.get('seeds', {})
            for seed_num, player_name in seeds.items():
                try:
                    # Safely convert seed_num to int, handling various input types
                    seed_int = int(seed_num) if seed_num is not None else None
                    if seed_int is not None:
                        tournament_draw.add_seeded_player(seed_int, player_name)
                except (ValueError, TypeError):
                    # Skip invalid seed numbers rather than crashing
                    continue
            
            return tournament_draw
            
        except Exception as e:
            # Return basic tournament draw if parsing fails
            return TournamentDraw(
                tournament_id=tournament_id,
                tournament_name=f'Tournament {tournament_id}',
                year=datetime.now().year,
                surface='hard',
                category='Unknown'
            )
    
    def _parse_match_from_draw(self, match_data: Dict) -> Match:
        """Parse match data from tournament draw"""
        return Match(
            match_id=match_data.get('id', 'unknown'),
            round_name=match_data.get('round', 'Unknown Round'),
            player1=match_data.get('player1', 'TBD'),
            player2=match_data.get('player2', 'TBD'),
            player1_seed=match_data.get('player1_seed'),
            player2_seed=match_data.get('player2_seed'),
            winner=match_data.get('winner'),
            score=match_data.get('score'),
            status=match_data.get('status', 'scheduled')
        )
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string with fallback mechanisms
        
        Args:
            date_str: Date string to parse (can be None or empty)
            
        Returns:
            Parsed datetime object or None if parsing fails
        """
        if not date_str or not date_str.strip():
            return None
            
        # First try standard ISO format
        try:
            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            pass
            
        # Fall back to dateutil parser if available
        if dateutil_parser:
            try:
                return dateutil_parser.parse(date_str)
            except (ValueError, TypeError):
                pass
                
        # If all parsing fails, return None
        return None
    
    def _parse_match_result(self, api_data: Dict) -> MatchResult:
        """Parse API response into MatchResult object"""
        match_info = api_data.get('match', {})
        
        # Parse date with robust error handling
        parsed_date = self._parse_date(match_info.get('date'))
        match_date = parsed_date if parsed_date is not None else datetime.now()
        
        return MatchResult(
            match_id=match_info.get('id', 'unknown'),
            date=match_date,
            tournament=match_info.get('tournament', 'Unknown'),
            surface=match_info.get('surface', 'hard'),
            round_name=match_info.get('round', 'Unknown'),
            player1=match_info.get('player1', 'Unknown'),
            player2=match_info.get('player2', 'Unknown'),
            winner=match_info.get('winner', ''),
            loser=match_info.get('loser', ''),
            final_score=match_info.get('score', ''),
            duration_minutes=match_info.get('duration', 0)
        )
    
    # Synchronous versions for compatibility
    def get_player_stats_sync(self, player_name: str, player_id: Optional[str] = None) -> PlayerStats:
        """Synchronous version of get_player_stats"""
        try:
            # Validate player_name parameter
            if player_name is None or not isinstance(player_name, str):
                raise APIException("Player name must be a non-empty string")
            
            player_name_clean = player_name.strip()
            if not player_name_clean:
                raise APIException("Player name cannot be empty or whitespace only")
            
            # Validate player_id parameter if provided
            if player_id is not None and not isinstance(player_id, str):
                raise APIException("Player ID must be a string if provided")
            
            if player_id:
                response = self.get_data_sync(
                    'player_matches',
                    player_id=player_id,
                    priority='high'
                )
            else:
                search_response = self.get_data_sync(
                    'player_search',
                    params={'name': player_name_clean},
                    priority='high'
                )
                
                if not search_response.get('players'):
                    raise APIException(f"Player '{player_name_clean}' not found")
                
                players_list = search_response['players']
                if len(players_list) == 0:
                    raise APIException(f"No players found for '{player_name_clean}'")
                
                player_data = players_list[0]
                player_id = player_data.get('id')
                
                response = self.get_data_sync(
                    'player_matches',
                    player_id=player_id,
                    priority='high'
                )
            
            return self._parse_player_stats(response, player_name_clean)
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get player stats for {player_name}: {e}")
    
    def get_rankings_sync(self, tour: str = 'atp', limit: int = 100) -> Dict:
        """Synchronous version of get_rankings"""
        try:
            # Validate tour parameter
            if tour is None or not isinstance(tour, str):
                raise APIException("Tour parameter must be a non-empty string")
            
            tour_lower = tour.lower().strip()
            if not tour_lower:
                raise APIException("Tour parameter cannot be empty or whitespace only")
            
            if tour_lower not in ('atp', 'wta'):
                raise APIException(f"Invalid tour '{tour}'. Must be 'atp' or 'wta'")
        
            response = self.get_data_sync(
                'rankings',
                type=tour_lower,
                params={'limit': limit},
                priority='high'
            )
            
            return response
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get {tour} rankings: {e}")
    
    def get_tournament_draw_sync(self, tournament_id: str) -> TournamentDraw:
        """Synchronous version of get_tournament_draw"""
        try:
            response = self.get_data_sync(
                'tournament_draw',
                tournament_id=tournament_id,
                priority='critical'
            )
            
            return self._parse_tournament_draw(response, tournament_id)
            
        except APIException:
            raise
        except Exception as e:
            raise APIException(f"Failed to get tournament draw for {tournament_id}: {e}")