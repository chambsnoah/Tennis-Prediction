"""
Test Configuration for Tennis API Integration

Configuration specifically designed for testing and development,
with mock endpoints and higher rate limits.
"""

from typing import TypedDict, Dict
from .api_config import APIConfig, APIEndpointConfig, RateLimit


# Constants
MOCK_API_KEY = "mock_test_key_12345"


# Helper functions
def build_mock_headers(api_key: str, host: str) -> Dict[str, str]:
    """Build mock RapidAPI headers for testing"""
    return {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": host,
        "Content-Type": "application/json"
    }


def _dev_headers(host: str, key: str) -> Dict[str, str]:
    """Build development RapidAPI headers"""
    return {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": host,
        "Content-Type": "application/json"
    }


# Type definitions for mock data
class ServeStats(TypedDict):
    """Type definition for serve statistics"""
    first_serve_percentage: float       # 0.0-1.0 (fraction)
    first_serve_win_percentage: float   # 0.0-1.0 (fraction)
    second_serve_win_percentage: float  # 0.0-1.0 (fraction)
    aces_per_match: float              # per match
    double_faults_per_match: float     # per match


class PlayerFixture(TypedDict):
    """Type definition for player test fixture"""
    id: str
    name: str
    ranking: int
    nationality: str
    age: int          # years
    height: int       # cm
    weight: int       # kg
    plays: str        # handedness and backhand style
    serve_stats: ServeStats


class TournamentFixture(TypedDict):
    """Type definition for tournament test fixture"""
    id: str
    name: str
    surface: str      # 'hard', 'clay', 'grass', 'carpet'
    category: str
    location: str
    draw_size: int
    status: str


class TestConfig:
    """Test configuration with mock endpoints and test settings"""
    
    @staticmethod
    def get_mock_config() -> APIConfig:
        """Get configuration with completely mock endpoints for unit testing"""
        return APIConfig(
            rapid_api_key=MOCK_API_KEY,
            tennis_live_api=APIEndpointConfig(
                name="rapidapi_tennis_live",  # Match rate limiter expected name
                base_url="https://mock-tennis-live.test",
                headers=build_mock_headers(MOCK_API_KEY, "mock-tennis-live.test"),
                timeout=5,
                max_retries=1,
                rate_limit=RateLimit(
                    per_minute=1000,  # Very high limits for testing
                    per_hour=10000,
                    per_day=100000,
                    per_month=1000000
                ),
                endpoints={
                    "live_matches": "mock/matches/live",
                    "tournament_draw": "mock/tournament/{tournament_id}/draw",
                    "player_matches": "mock/player/{player_id}/matches",
                    "match_details": "mock/match/{match_id}",
                    "tournaments": "mock/tournaments",
                    "player_search": "mock/players/search",
                    "rankings": "mock/rankings/{type}"
                }
            ),
            tennis_rankings_api=APIEndpointConfig(
                name="rapidapi_tennis_rankings",  # Match rate limiter expected name
                base_url="https://mock-tennis-rankings.test",
                headers=build_mock_headers(MOCK_API_KEY, "mock-tennis-rankings.test"),
                timeout=5,
                max_retries=1,
                rate_limit=RateLimit(
                    per_minute=500,
                    per_hour=5000,
                    per_day=50000,
                    per_month=500000
                ),
                endpoints={
                    "current_rankings": "mock/rankings/{tour}",
                    "historical_rankings": "mock/rankings/{tour}/history",
                    "player_ranking": "mock/player/{player_id}/ranking",
                    "player_info": "mock/player/{player_id}",
                    "ranking_changes": "mock/rankings/{tour}/changes"
                }
            ),
            tennis_stats_api=APIEndpointConfig(
                name="rapidapi_tennis_stats",  # Match rate limiter expected name
                base_url="https://mock-tennis-stats.test",
                headers=build_mock_headers(MOCK_API_KEY, "mock-tennis-stats.test"),
                timeout=5,
                max_retries=1,
                rate_limit=RateLimit(
                    per_minute=300,
                    per_hour=3000,
                    per_day=30000,
                    per_month=300000
                ),
                endpoints={
                    "player_stats": "mock/player/{player_id}/stats",
                    "player_surface_stats": "mock/player/{player_id}/stats/{surface}",
                    "head_to_head": "mock/h2h/{player1_id}/{player2_id}",
                    "recent_matches": "mock/player/{player_id}/matches/recent",
                    "tournament_stats": "mock/tournament/{tournament_id}/stats",
                    "match_statistics": "mock/match/{match_id}/stats"
                }
            ),
            default_timeout=5,
            max_concurrent_requests=10,
            cache_enabled=False,  # Disable cache for testing
            fallback_enabled=True,
            api_priorities={
                'tennis_live_api': 3,
                'tennis_rankings_api': 2,
                'tennis_stats_api': 1
            }
        )
    
    @staticmethod
    def get_development_config(rapid_api_key: str) -> APIConfig:
        """
        Get configuration for development with real APIs but higher limits
        
        Args:
            rapid_api_key: Real RapidAPI key for development
        """
        return APIConfig(
            rapid_api_key=rapid_api_key,
            tennis_live_api=APIEndpointConfig(
                name="rapidapi_tennis_live",  # Match rate limiter expected name
                base_url="https://tennis-live-data.p.rapidapi.com",
                headers=_dev_headers("tennis-live-data.p.rapidapi.com", rapid_api_key),
                timeout=15,  # 15s (dev); prod=30s
                max_retries=2,  # 2 retries (dev); prod=3
                rate_limit=RateLimit(
                    per_minute=20,  # 20/min (dev); prod=10/min
                    per_hour=200,   # 200/hr (dev); prod=100/hr
                    per_day=1000,   # 1000/day (dev); prod=500/day
                    per_month=2000  # 2000/month (dev); prod=1000/month
                ),
                endpoints={
                    "live_matches": "matches/live",
                    "tournament_draw": "tournament/{tournament_id}/draw",
                    "player_matches": "player/{player_id}/matches",
                    "match_details": "match/{match_id}",
                    "tournaments": "tournaments",
                    "player_search": "players/search",
                    "rankings": "rankings/{type}"
                }
            ),
            tennis_rankings_api=APIEndpointConfig(
                name="rapidapi_tennis_rankings",  # Match rate limiter expected name
                base_url="https://tennis-rankings.p.rapidapi.com",
                headers=_dev_headers("tennis-rankings.p.rapidapi.com", rapid_api_key),
                timeout=15,  # 15s (dev); prod=25s
                max_retries=2,  # 2 retries (dev); prod=2
                rate_limit=RateLimit(
                    per_minute=10,  # 10/min (dev); prod=5/min
                    per_hour=100,   # 100/hr (dev); prod=50/hr
                    per_day=400,    # 400/day (dev); prod=200/day
                    per_month=1000  # 1000/month (dev); prod=500/month
                ),
                endpoints={
                    "current_rankings": "rankings/{tour}",
                    "historical_rankings": "rankings/{tour}/history",
                    "player_ranking": "player/{player_id}/ranking",
                    "player_info": "player/{player_id}",
                    "ranking_changes": "rankings/{tour}/changes"
                }
            ),
            tennis_stats_api=APIEndpointConfig(
                name="rapidapi_tennis_stats",  # Match rate limiter expected name
                base_url="https://tennis-stats.p.rapidapi.com",
                headers=_dev_headers("tennis-stats.p.rapidapi.com", rapid_api_key),
                timeout=5,  # 5s (dev); prod=35s - reduced from 20 to prevent hanging
                max_retries=2,  # 2 retries (dev); prod=3
                rate_limit=RateLimit(
                    per_minute=15,  # 15/min (dev); prod=8/min
                    per_hour=150,   # 150/hr (dev); prod=80/hr
                    per_day=600,    # 600/day (dev); prod=300/day
                    per_month=1500  # 1500/month (dev); prod=800/month
                ),
                endpoints={
                    "player_stats": "player/{player_id}/stats",
                    "player_surface_stats": "player/{player_id}/stats/{surface}",
                    "head_to_head": "h2h/{player1_id}/{player2_id}",
                    "recent_matches": "player/{player_id}/matches/recent",
                    "tournament_stats": "tournament/{tournament_id}/stats",
                    "match_statistics": "match/{match_id}/stats"
                }
            ),
            default_timeout=5,  # 5s (dev); prod=10s - reduced from 15 to prevent hanging
            max_concurrent_requests=3,  # 3 concurrent (dev); prod=5 - conservative for development
            cache_enabled=True,
            fallback_enabled=True,
            api_priorities={
                'tennis_live_api': 3,
                'tennis_rankings_api': 2,
                'tennis_stats_api': 1
            }
        )
    
    @staticmethod
    def get_minimal_test_config() -> APIConfig:
        """Get minimal configuration for basic testing"""
        return APIConfig(
            rapid_api_key="minimal_test_key",
            default_timeout=2,
            max_concurrent_requests=1,
            cache_enabled=False,
            fallback_enabled=False
        )


# Sample mock data for testing
# Field Documentation:
# - first_serve_percentage: float 0.0-1.0 (fraction, not percentage)
# - first_serve_win_percentage: float 0.0-1.0 (fraction, not percentage)
# - second_serve_win_percentage: float 0.0-1.0 (fraction, not percentage)
# - height: int cm
# - weight: int kg
# - age: int years
# - aces_per_match: float per match average
# - double_faults_per_match: float per match average
# - ranking: int ATP/WTA ranking position
MOCK_PLAYER_DATA: Dict[str, PlayerFixture] = {
    "novak_djokovic": {
        "id": "djokovic_n",
        "name": "Novak Djokovic",
        "ranking": 1,
        "nationality": "Serbia",
        "age": 36,
        "height": 188,
        "weight": 77,
        "plays": "Right-handed (two-handed backhand)",
        "serve_stats": {
            "first_serve_percentage": 0.73,
            "first_serve_win_percentage": 0.79,
            "second_serve_win_percentage": 0.58,
            "aces_per_match": 6.2,
            "double_faults_per_match": 1.8
        }
    },
    "carlos_alcaraz": {
        "id": "alcaraz_c",
        "name": "Carlos Alcaraz",
        "ranking": 2,
        "nationality": "Spain", 
        "age": 21,
        "height": 183,
        "weight": 74,
        "plays": "Right-handed (two-handed backhand)",
        "serve_stats": {
            "first_serve_percentage": 0.64,
            "first_serve_win_percentage": 0.74,
            "second_serve_win_percentage": 0.54,
            "aces_per_match": 4.8,
            "double_faults_per_match": 2.1
        }
    }
}

MOCK_TOURNAMENT_DATA: Dict[str, TournamentFixture] = {
    "us_open_2024": {
        "id": "us_open_2024",
        "name": "US Open 2024",
        "surface": "hard",
        "category": "Grand Slam",
        "location": "New York, USA",
        "draw_size": 128,
        "status": "completed"
    },
    "australian_open_2024": {
        "id": "australian_open_2024",
        "name": "Australian Open 2024",
        "surface": "hard",
        "category": "Grand Slam",
        "location": "Melbourne, Australia",
        "draw_size": 128,
        "status": "completed"
    }
}