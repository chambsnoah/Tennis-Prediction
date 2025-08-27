"""
API Configuration Management

Configuration system for tennis API integration including credentials,
endpoints, and API-specific settings.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional
import json
from pathlib import Path


@dataclass
class RateLimit:
    """Rate limiting configuration"""
    per_minute: int = 10
    per_hour: int = 100
    per_day: int = 500
    per_month: int = 1000


@dataclass
class APIEndpointConfig:
    """Configuration for a specific API endpoint"""
    name: str
    base_url: str
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Rate limiting
    rate_limit: RateLimit = field(default_factory=RateLimit)
    
    # Endpoints mapping
    endpoints: Dict[str, str] = field(default_factory=dict)
    
    # Legacy properties for backward compatibility
    @property
    def requests_per_minute(self) -> int:
        return self.rate_limit.per_minute
    
    @property
    def requests_per_hour(self) -> int:
        return self.rate_limit.per_hour
    
    @property
    def requests_per_day(self) -> int:
        return self.rate_limit.per_day
    
    @property
    def requests_per_month(self) -> int:
        return self.rate_limit.per_month
    
    def get_endpoint_url(self, endpoint_name: str) -> str:
        """Get full URL for an endpoint"""
        endpoint_path = self.endpoints.get(endpoint_name, "")
        return f"{self.base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"
    
    # Backward compatibility constructor
    def __init__(self, name: str, base_url: str, headers: Optional[Dict[str, str]] = None, 
                 timeout: int = 30, max_retries: int = 3, retry_delay: float = 1.0,
                 endpoints: Optional[Dict[str, str]] = None, rate_limit: Optional[RateLimit] = None,
                 # Legacy parameters for backward compatibility
                 requests_per_minute: Optional[int] = None, requests_per_hour: Optional[int] = None,
                 requests_per_day: Optional[int] = None, requests_per_month: Optional[int] = None):
        self.name = name
        self.base_url = base_url
        self.headers = headers or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.endpoints = endpoints or {}
        
        # Handle rate limit setup with backward compatibility
        if rate_limit is not None:
            self.rate_limit = rate_limit
        elif any(x is not None for x in [requests_per_minute, requests_per_hour, requests_per_day, requests_per_month]):
            # Legacy constructor with individual rate limit parameters
            self.rate_limit = RateLimit(
                per_minute=requests_per_minute or 10,
                per_hour=requests_per_hour or 100,
                per_day=requests_per_day or 500,
                per_month=requests_per_month or 1000
            )
        else:
            self.rate_limit = RateLimit()

@dataclass
class APIConfig:
    """Main API configuration container"""
    rapid_api_key: str
    
    # API endpoint configurations
    tennis_live_api: Optional[APIEndpointConfig] = None
    tennis_rankings_api: Optional[APIEndpointConfig] = None
    tennis_stats_api: Optional[APIEndpointConfig] = None
    
    # Global settings
    default_timeout: int = 10  # Reduced from 30 to prevent hanging
    max_concurrent_requests: int = 5
    cache_enabled: bool = True
    fallback_enabled: bool = True
    
    # API priorities (higher number = higher priority)
    api_priorities: Dict[str, int] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize default API configurations"""
        if not self.tennis_live_api:
            self.tennis_live_api = self._get_default_tennis_live_config()
        
        if not self.tennis_rankings_api:
            self.tennis_rankings_api = self._get_default_rankings_config()
        
        if not self.tennis_stats_api:
            self.tennis_stats_api = self._get_default_stats_config()
        
        if not self.api_priorities:
            self.api_priorities = {
                'tennis_live_api': 3,
                'tennis_rankings_api': 2,
                'tennis_stats_api': 1
            }
    
    def _get_default_tennis_live_config(self) -> APIEndpointConfig:
        """Get default configuration for tennis live data API"""
        return APIEndpointConfig(
            name="Tennis Live API",
            base_url="https://tennis-live-data.p.rapidapi.com",
            headers={
                "X-RapidAPI-Key": self.rapid_api_key,
                "X-RapidAPI-Host": "tennis-live-data.p.rapidapi.com",
                "Content-Type": "application/json"
            },
            timeout=30,
            max_retries=3,
            rate_limit=RateLimit(
                per_minute=10,
                per_hour=100,
                per_day=500,
                per_month=1000
            ),
            endpoints={
                "live_matches": "matches/live",
                "tournament_draw": "tournament/{tournament_id}/draw",
                "player_matches": "player/{player_id}/matches",
                "match_details": "match/{match_id}",
                "tournaments": "tournaments",
                "player_search": "players/search",
                "rankings": "rankings/{type}"  # type: atp, wta
            }
        )
    
    def _get_default_rankings_config(self) -> APIEndpointConfig:
        """Get default configuration for tennis rankings API"""
        return APIEndpointConfig(
            name="Tennis Rankings API",
            base_url="https://tennis-rankings.p.rapidapi.com",
            headers={
                "X-RapidAPI-Key": self.rapid_api_key,
                "X-RapidAPI-Host": "tennis-rankings.p.rapidapi.com",
                "Content-Type": "application/json"
            },
            timeout=25,
            max_retries=2,
            rate_limit=RateLimit(
                per_minute=5,
                per_hour=50,
                per_day=200,
                per_month=500
            ),
            endpoints={
                "current_rankings": "rankings/{tour}",  # tour: atp, wta
                "historical_rankings": "rankings/{tour}/history",
                "player_ranking": "player/{player_id}/ranking",
                "player_info": "player/{player_id}",
                "ranking_changes": "rankings/{tour}/changes"
            }
        )
    
    def _get_default_stats_config(self) -> APIEndpointConfig:
        """Get default configuration for tennis statistics API"""
        return APIEndpointConfig(
            name="Tennis Stats API",
            base_url="https://tennis-stats.p.rapidapi.com",
            headers={
                "X-RapidAPI-Key": self.rapid_api_key,
                "X-RapidAPI-Host": "tennis-stats.p.rapidapi.com",
                "Content-Type": "application/json"
            },
            timeout=35,
            max_retries=3,
            rate_limit=RateLimit(
                per_minute=8,
                per_hour=80,
                per_day=300,
                per_month=800
            ),
            endpoints={
                "player_stats": "player/{player_id}/stats",
                "player_surface_stats": "player/{player_id}/stats/{surface}",
                "head_to_head": "h2h/{player1_id}/{player2_id}",
                "recent_matches": "player/{player_id}/matches/recent",
                "tournament_stats": "tournament/{tournament_id}/stats",
                "match_statistics": "match/{match_id}/stats"
            }
        )
    
    def get_api_config(self, api_name: str) -> Optional[APIEndpointConfig]:
        """Get configuration for a specific API"""
        if api_name == "tennis_live_api":
            return self.tennis_live_api
        elif api_name == "tennis_rankings_api":
            return self.tennis_rankings_api
        elif api_name == "tennis_stats_api":
            return self.tennis_stats_api
        else:
            return None
    
    def get_all_configs(self) -> Dict[str, APIEndpointConfig]:
        """Get all API configurations"""
        configs = {}
        if self.tennis_live_api is not None:
            configs["tennis_live_api"] = self.tennis_live_api
        if self.tennis_rankings_api is not None:
            configs["tennis_rankings_api"] = self.tennis_rankings_api
        if self.tennis_stats_api is not None:
            configs["tennis_stats_api"] = self.tennis_stats_api
        return configs
    
    def update_api_key(self, new_key: str):
        """Update RapidAPI key for all configurations"""
        self.rapid_api_key = new_key
        
        # Update headers for all APIs
        for api_config in [self.tennis_live_api, self.tennis_rankings_api, self.tennis_stats_api]:
            if api_config and "X-RapidAPI-Key" in api_config.headers:
                api_config.headers["X-RapidAPI-Key"] = new_key
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        result = {
            "rapid_api_key": self.rapid_api_key,
            "default_timeout": self.default_timeout,
            "max_concurrent_requests": self.max_concurrent_requests,
            "cache_enabled": self.cache_enabled,
            "fallback_enabled": self.fallback_enabled,
            "api_priorities": self.api_priorities
        }
        
        # Add API configurations if they exist
        def _serialize_api_config(api_config: APIEndpointConfig) -> Dict:
            return {
                "name": api_config.name,
                "base_url": api_config.base_url,
                "timeout": api_config.timeout,
                "max_retries": api_config.max_retries,
                "requests_per_minute": api_config.rate_limit.per_minute,
                "requests_per_hour": api_config.rate_limit.per_hour,
                "requests_per_day": api_config.rate_limit.per_day,
                "requests_per_month": api_config.rate_limit.per_month,
                "endpoints": api_config.endpoints
            }
        
        api_configs = {
            "tennis_live_api": self.tennis_live_api,
            "tennis_rankings_api": self.tennis_rankings_api,
            "tennis_stats_api": self.tennis_stats_api
        }
        
        for api_name, api_config in api_configs.items():
            if api_config is not None:
                result[api_name] = _serialize_api_config(api_config)
        
        return result


def get_api_config() -> APIConfig:
    """
    Get API configuration from environment variables and config files
    
    Returns:
        Configured APIConfig instance
    """
    # Try to get API key from environment
    rapid_api_key = os.getenv('RAPID_API_APPLICATION_KEY')
    
    # Try to load from .env file if not in environment
    if not rapid_api_key:
        env_file = Path('.env')
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('RAPID_API_APPLICATION_KEY='):
                            rapid_api_key = line.split('=', 1)[1].strip('"\'')
                            break
            except (OSError, IOError):
                pass
    
    if not rapid_api_key:
        raise ValueError(
            "RapidAPI key not found. Please set RAPID_API_APPLICATION_KEY environment variable "
            "or add it to .env file"
        )
    
    # Try to load additional config from config file
    config_file = Path('tennis_api_config.json')
    additional_config = {}
    
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                additional_config = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    
    # Create configuration
    config = APIConfig(
        rapid_api_key=rapid_api_key,
        **additional_config
    )
    
    return config


def save_api_config(config: APIConfig, config_file: str = 'tennis_api_config.json'):
    """
    Save API configuration to file (excluding sensitive data)
    
    Args:
        config: API configuration to save
        config_file: File path to save config
    """
    # Don't save the API key to file for security
    config_dict = config.to_dict()
    config_dict.pop('rapid_api_key', None)
    
    # Remove API keys from headers
    for api_name in ['tennis_live_api', 'tennis_rankings_api', 'tennis_stats_api']:
        # Headers are already excluded from to_dict() output
        pass
    
    try:
        with open(config_file, 'w') as f:
            json.dump(config_dict, f, indent=2)
    except (OSError, TypeError) as e:
        print(f"Failed to save API config: {e}")


# Test configuration for development
class TestConfig:
    """Test configuration with mock endpoints"""
    
    @staticmethod
    def get_test_config() -> APIConfig:
        """Get configuration for testing with mock endpoints"""
        return APIConfig(
            rapid_api_key="test_key_123456",
            tennis_live_api=APIEndpointConfig(
                name="Test Tennis Live API",
                base_url="https://mock-tennis-api.example.com",
                headers={"Authorization": "Bearer test_key_123456"},
                rate_limit=RateLimit(
                    per_minute=100,  # Higher limits for testing
                    per_hour=1000
                ),
                endpoints={
                    "live_matches": "test/matches/live",
                    "tournament_draw": "test/tournament/{tournament_id}/draw",
                    "player_matches": "test/player/{player_id}/matches"
                }
            ),
            tennis_rankings_api=APIEndpointConfig(
                name="Test Tennis Rankings API",
                base_url="https://mock-rankings-api.example.com",
                headers={"Authorization": "Bearer test_key_123456"},
                rate_limit=RateLimit(
                    per_minute=50,
                    per_hour=500
                ),
                endpoints={
                    "current_rankings": "test/rankings/{tour}",
                    "player_ranking": "test/player/{player_id}/ranking"
                }
            ),
            tennis_stats_api=APIEndpointConfig(
                name="Test Tennis Stats API", 
                base_url="https://mock-stats-api.example.com",
                headers={"Authorization": "Bearer test_key_123456"},
                rate_limit=RateLimit(
                    per_minute=30,
                    per_hour=300
                ),
                endpoints={
                    "player_stats": "test/player/{player_id}/stats",
                    "head_to_head": "test/h2h/{player1_id}/{player2_id}"
                }
            ),
            cache_enabled=False,  # Disable cache for testing
            fallback_enabled=True
        )