"""
Unified Tennis API Client

Main interface that coordinates multiple tennis API clients with intelligent
fallback mechanisms, load balancing, and unified data aggregation.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import logging

from .base_client import APIException, RateLimitException
from .tennis_live_client import TennisLiveAPIClient
from .tennis_stats_client import TennisStatsAPIClient
from ..config.api_config import APIConfig, get_api_config
from ..cache.cache_manager import CacheManager, MemoryCache
from ..cache.rate_limiter import RateLimiter
from ..models.player_stats import PlayerStats
from ..models.tournament_data import TournamentDraw
from ..models.match_data import HeadToHeadRecord


import logging

# Do not configure logging here; leave configuration to the application
logger = logging.getLogger(__name__)


class TennisAPIClient:
    """
    Unified client for tennis APIs with fallback mechanisms and data aggregation
    """
    
    def __init__(self, config: Optional[APIConfig] = None):
        """
        Initialize unified tennis API client
        
        Args:
            config: API configuration, if None will load from environment
        """
        if config is None:
            config = get_api_config()
        
        self.config = config
        
        # Initialize cache and rate limiting
        self.cache_manager = CacheManager()
        self.memory_cache = MemoryCache()
        self.rate_limiter = RateLimiter()
        
        # Initialize API clients
        self.clients = {}
        self._initialize_clients()
        
        # Fallback order based on priority
        self.fallback_order = self._get_fallback_order()
        
        # Client health tracking
        self.client_health = {}
        self._initialize_health_tracking()
        
        # Global statistics
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'fallback_used': 0,
            'cache_hits': 0,
            'api_errors': {}
        }
    
    def _initialize_clients(self):
        """Initialize all API clients"""
        try:
            # Tennis Live API Client
            if self.config.tennis_live_api:
                self.clients['live'] = TennisLiveAPIClient(
                    self.config.tennis_live_api,
                    self.cache_manager,
                    self.rate_limiter,
                    self.memory_cache
                )
                logger.info("Initialized Tennis Live API client")
            
            # Tennis Rankings API Client (using TennisStatsAPIClient for now)
            # TODO: Create dedicated TennisRankingsAPIClient for rankings-specific functionality
            if self.config.tennis_rankings_api:
                self.clients['rankings'] = TennisStatsAPIClient(
                    self.config.tennis_rankings_api,
                    self.cache_manager,
                    self.rate_limiter,
                    self.memory_cache
                )
                logger.info("Initialized Tennis Stats API client for rankings data")
            
            # Tennis Stats API Client
            if self.config.tennis_stats_api:
                self.clients['stats'] = TennisStatsAPIClient(
                    self.config.tennis_stats_api,
                    self.cache_manager,
                    self.rate_limiter,
                    self.memory_cache
                )
                logger.info("Initialized Tennis Stats API client")
                
        except Exception as e:
            logger.error(f"Failed to initialize API clients: {e}")
            raise APIException(f"Client initialization failed: {e}")
    
    def _get_fallback_order(self) -> List[str]:
        """Get fallback order based on API priorities"""
        priorities = self.config.api_priorities
        return sorted(self.clients.keys(), 
                     key=lambda x: priorities.get(x, 0), 
                     reverse=True)
    
    def _initialize_health_tracking(self):
        """Initialize health tracking for all clients"""
        for client_name in self.clients:
            self.client_health[client_name] = {
                'is_healthy': True,
                'last_success': datetime.now(),
                'last_failure': None,
                'consecutive_failures': 0,
                'total_requests': 0,
                'successful_requests': 0
            }
    
    def _update_client_health(self, client_name: str, success: bool):
        """Update health status for a client"""
        health = self.client_health[client_name]
        health['total_requests'] += 1
        
        if success:
            health['is_healthy'] = True
            health['last_success'] = datetime.now()
            health['consecutive_failures'] = 0
            health['successful_requests'] += 1
        else:
            health['last_failure'] = datetime.now()
            health['consecutive_failures'] += 1
            
            # Mark as unhealthy after 3 consecutive failures
            if health['consecutive_failures'] >= 3:
                health['is_healthy'] = False
                logger.warning(f"Client {client_name} marked as unhealthy")
    
    def _get_healthy_clients(self) -> List[str]:
        """Get list of healthy clients in fallback order"""
        return [client for client in self.fallback_order 
                if self.client_health[client]['is_healthy']]
    
    async def get_player_stats(self, player_name: str, 
                             prefer_detailed: bool = True,
                             fallback_enabled: bool = True) -> PlayerStats:
        """
        Get comprehensive player statistics with fallback support
        
        Args:
            player_name: Player name to lookup
            prefer_detailed: Prefer detailed stats from stats API
            fallback_enabled: Enable fallback to other APIs
            
        Returns:
            PlayerStats object with comprehensive data
        """
        self.stats['total_requests'] += 1
        
        # Determine client order based on preference
        if prefer_detailed:
            client_order = ['stats', 'rankings', 'live']
        else:
            client_order = ['live', 'stats', 'rankings']
        
        # Filter to only healthy clients
        healthy_clients = self._get_healthy_clients()
        available_clients = [c for c in client_order if c in healthy_clients]
        
        if not available_clients:
            # All clients unhealthy, try the first available anyway
            available_clients = [c for c in client_order if c in self.clients]
        
        if not available_clients:
            # All clients unhealthy
            logger.error("All API clients are unhealthy")
            raise APIException("All API clients are currently unhealthy. Please try again later.")
        
        last_exception = None
        
        for client_name in available_clients:
            if client_name not in self.clients:
                continue
                
            try:
                client = self.clients[client_name]
                logger.info(f"Attempting to get player stats for {player_name} from {client_name}")
                
                player_stats = await client.get_player_stats(player_name)
                
                # Update health and stats
                self._update_client_health(client_name, True)
                self.stats['successful_requests'] += 1
                
                # If we used a fallback, note it
                if client_name != client_order[0]:
                    self.stats['fallback_used'] += 1
                    logger.info(f"Used fallback client {client_name} for player stats")
                
                return player_stats
                
            except (APIException, RateLimitException) as e:
                last_exception = e
                self._update_client_health(client_name, False)
                self.stats['api_errors'][client_name] = self.stats['api_errors'].get(client_name, 0) + 1
                
                logger.warning(f"Client {client_name} failed for player {player_name}: {e}")
                
                if not fallback_enabled:
                    break
                    
                continue
        
        # All clients failed
        self.stats['failed_requests'] += 1
        error_msg = f"All API clients failed to get player stats for {player_name}"
        if last_exception:
            error_msg += f". Last error: {last_exception}"
        
        logger.error(error_msg)
        raise APIException(error_msg)
    
    async def get_tournament_draw(self, tournament_id: str,
                                fallback_enabled: bool = True) -> TournamentDraw:
        """
        Get tournament draw with fallback support
        
        Args:
            tournament_id: Tournament identifier
            fallback_enabled: Enable fallback to other APIs
            
        Returns:
            TournamentDraw object
        """
        self.stats['total_requests'] += 1
        
        # Live API is best for tournament draws
        client_order = ['live', 'stats', 'rankings']
        healthy_clients = self._get_healthy_clients()
        available_clients = [c for c in client_order if c in healthy_clients]
        
        if not available_clients:
            available_clients = [c for c in client_order if c in self.clients]
        
        last_exception = None
        
        for client_name in available_clients:
            if client_name not in self.clients:
                continue
                
            try:
                client = self.clients[client_name]
                logger.info(f"Attempting to get tournament draw {tournament_id} from {client_name}")
                
                tournament_draw = await client.get_tournament_draw(tournament_id)
                
                self._update_client_health(client_name, True)
                self.stats['successful_requests'] += 1
                
                if client_name != client_order[0]:
                    self.stats['fallback_used'] += 1
                
                return tournament_draw
                
            except (APIException, RateLimitException) as e:
                last_exception = e
                self._update_client_health(client_name, False)
                self.stats['api_errors'][client_name] = self.stats['api_errors'].get(client_name, 0) + 1
                
                logger.warning(f"Client {client_name} failed for tournament {tournament_id}: {e}")
                
                if not fallback_enabled:
                    break
                    
                continue
        
        self.stats['failed_requests'] += 1
        error_msg = f"All API clients failed to get tournament draw for {tournament_id}"
        if last_exception:
            error_msg += f". Last error: {last_exception}"
        
        logger.error(error_msg)
        raise APIException(error_msg)
    
    async def get_rankings(self, tour: str = 'atp', 
                         fallback_enabled: bool = True) -> Dict:
        """
        Get current rankings with fallback support
        
        Args:
            tour: Tournament tour ('atp' or 'wta')
            fallback_enabled: Enable fallback to other APIs
            
        Returns:
            Rankings data dictionary
        """
        self.stats['total_requests'] += 1
        
        # Rankings API is best for rankings
        client_order = ['rankings', 'stats', 'live']
        healthy_clients = self._get_healthy_clients()
        available_clients = [c for c in client_order if c in healthy_clients]
        
        if not available_clients:
            available_clients = [c for c in client_order if c in self.clients]
        
        last_exception = None
        
        for client_name in available_clients:
            if client_name not in self.clients:
                continue
                
            try:
                client = self.clients[client_name]
                logger.info(f"Attempting to get {tour} rankings from {client_name}")
                
                rankings = await client.get_rankings(tour)
                
                self._update_client_health(client_name, True)
                self.stats['successful_requests'] += 1
                
                if client_name != client_order[0]:
                    self.stats['fallback_used'] += 1
                
                return rankings
                
            except (APIException, RateLimitException) as e:
                last_exception = e
                self._update_client_health(client_name, False)
                self.stats['api_errors'][client_name] = self.stats['api_errors'].get(client_name, 0) + 1
                
                logger.warning(f"Client {client_name} failed for {tour} rankings: {e}")
                
                if not fallback_enabled:
                    break
                    
                continue
        
        self.stats['failed_requests'] += 1
        error_msg = f"All API clients failed to get {tour} rankings"
        if last_exception:
            error_msg += f". Last error: {last_exception}"
        
        logger.error(error_msg)
        raise APIException(error_msg)
    
    async def get_head_to_head(self, player1_name: str, player2_name: str,
                             fallback_enabled: bool = True) -> HeadToHeadRecord:
        """
        Get head-to-head record with fallback support
        
        Args:
            player1_name: First player name
            player2_name: Second player name
            fallback_enabled: Enable fallback to other APIs
            
        Returns:
            HeadToHeadRecord object
        """
        self.stats['total_requests'] += 1
        
        # Stats API is best for head-to-head
        client_order = ['stats', 'rankings', 'live']
        healthy_clients = self._get_healthy_clients()
        available_clients = [c for c in client_order if c in healthy_clients]
        
        if not available_clients:
            available_clients = [c for c in client_order if c in self.clients]
        
        last_exception = None
        
        for client_name in available_clients:
            if client_name not in self.clients:
                continue
                
            try:
                client = self.clients[client_name]
                
                # Only stats client has head-to-head method
                if hasattr(client, 'get_head_to_head'):
                    logger.info(f"Attempting to get H2H {player1_name} vs {player2_name} from {client_name}")
                    
                    h2h = await client.get_head_to_head(player1_name, player2_name)
                    
                    self._update_client_health(client_name, True)
                    self.stats['successful_requests'] += 1
                    
                    return h2h
                else:
                    continue
                
            except (APIException, RateLimitException) as e:
                last_exception = e
                self._update_client_health(client_name, False)
                self.stats['api_errors'][client_name] = self.stats['api_errors'].get(client_name, 0) + 1
                
                logger.warning(f"Client {client_name} failed for H2H: {e}")
                
                if not fallback_enabled:
                    break
                    
                continue
        
        # Return empty H2H record if all clients fail
        logger.warning(f"Could not get H2H for {player1_name} vs {player2_name}, returning empty record")
        return HeadToHeadRecord(player1=player1_name, player2=player2_name)
    
    async def get_live_matches(self) -> List[Dict]:
        """Get live matches (only from live API)"""
        if 'live' not in self.clients:
            raise APIException("Live API client not available")
        
        try:
            return await self.clients['live'].get_live_matches()
        except Exception as e:
            raise APIException(f"Failed to get live matches: {e}")
    
    def get_client_stats(self) -> Dict:
        """Get comprehensive statistics for all clients"""
        client_stats = {}
        
        for client_name, client in self.clients.items():
            client_stats[client_name] = {
                **client.get_stats(),
                'health': self.client_health[client_name]
            }
        
        return {
            'global_stats': self.stats,
            'client_stats': client_stats,
            'cache_stats': self.cache_manager.get_cache_size(),
            'rate_limiter_stats': self.rate_limiter.get_usage_stats()
        }
    
    def reset_client_health(self, client_name: Optional[str] = None):
        """Reset health status for a client or all clients"""
        if client_name:
            if client_name in self.client_health:
                self.client_health[client_name]['is_healthy'] = True
                self.client_health[client_name]['consecutive_failures'] = 0
                logger.info(f"Reset health for client {client_name}")
        else:
            for name in self.client_health:
                self.client_health[name]['is_healthy'] = True
                self.client_health[name]['consecutive_failures'] = 0
            logger.info("Reset health for all clients")
    
    async def health_check(self) -> Dict[str, bool]:
        """Perform health check on all clients"""
        health_status = {}
        
        for client_name, client in self.clients.items():
            try:
                # Try a simple operation to check health
                if hasattr(client, 'get_rankings'):
                    await client.get_rankings('atp')
                    health_status[client_name] = True
                    self._update_client_health(client_name, True)
                else:
                    health_status[client_name] = True  # Assume healthy if no test method
                    
            except Exception as e:
                health_status[client_name] = False
                self._update_client_health(client_name, False)
                logger.warning(f"Health check failed for {client_name}: {e}")
        
        return health_status
    
    def close(self):
        """Close all client connections"""
        for client in self.clients.values():
            if hasattr(client, 'close'):
                client.close()
    
    async def close_async(self):
        """Close all async client connections"""
        for client in self.clients.values():
            if hasattr(client, 'close_async'):
                await client.close_async()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_async()
    
    # Synchronous wrapper methods for compatibility
    def get_player_stats_sync(self, player_name: str, prefer_detailed: bool = True) -> PlayerStats:
        """Synchronous wrapper for get_player_stats with timeout protection"""
        try:
            # Check if we're already in an async context
            asyncio.get_running_loop()
            raise APIException("Cannot call sync wrapper from async context. Use get_player_stats() instead.")
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            pass
        
        # Use shorter timeout for tests while still providing protection
        timeout = 5 if 'test' in str(type(self).__module__) else 15
        
        try:
            return asyncio.run(asyncio.wait_for(self.get_player_stats(player_name, prefer_detailed), timeout=timeout))
        except asyncio.TimeoutError:
            raise APIException(f"Player stats request for {player_name} timed out after {timeout} seconds")
    
    def get_tournament_draw_sync(self, tournament_id: str) -> TournamentDraw:
        """Synchronous wrapper for get_tournament_draw with timeout protection"""
        try:
            # Check if we're already in an async context
            asyncio.get_running_loop()
            raise APIException("Cannot call sync wrapper from async context. Use get_tournament_draw() instead.")
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            pass
        
        try:
            return asyncio.run(asyncio.wait_for(self.get_tournament_draw(tournament_id), timeout=15))
        except asyncio.TimeoutError:
            raise APIException(f"Tournament draw request for {tournament_id} timed out after 15 seconds")
    
    def get_rankings_sync(self, tour: str = 'atp') -> Dict:
        """Synchronous wrapper for get_rankings with timeout protection"""
        try:
            # Check if we're already in an async context
            asyncio.get_running_loop()
            raise APIException("Cannot call sync wrapper from async context. Use get_rankings() instead.")
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            pass
        
        try:
            return asyncio.run(asyncio.wait_for(self.get_rankings(tour), timeout=15))
        except asyncio.TimeoutError:
            raise APIException(f"Rankings request for {tour} timed out after 15 seconds")