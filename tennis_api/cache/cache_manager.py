"""
Cache Manager for Tennis API Data

Intelligent caching system with TTL (Time To Live) based on data type.
Different types of tennis data have different update frequencies and cache durations.
"""

import logging
import os
import pickle
import tempfile
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict
import hashlib

logger = logging.getLogger(__name__)


class CacheSizeInfo(TypedDict):
    """Type definition for cache size information"""
    total_files: int
    total_size_bytes: int
    total_size_mb: float
    type_counts: Dict[str, int]
    hits: int
    misses: int
    expired: int
    writes: int


class CacheManager:
    """Intelligent caching with TTL based on data type"""
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize cache manager
        
        Args:
            cache_dir: Directory to store cache files. Defaults to './cache'
        """
        if cache_dir is None:
            cache_dir = os.path.join(os.getcwd(), 'cache')
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        
        # Enforce permissions on existing directory (POSIX only)
        try:
            os.chmod(self.cache_dir, 0o700)
        except (OSError, AttributeError):
            # Skip chmod on non-POSIX platforms or if it fails
            logger.debug("Could not set directory permissions (non-POSIX platform or permission error)")
        
        # TTL configuration for different data types
        self.cache_config = {
            'rankings': timedelta(hours=24),        # Rankings change daily
            'player_stats': timedelta(hours=6),     # Stats updated frequently  
            'tournament_draws': timedelta(hours=1), # Draws change rapidly during tournaments
            'head_to_head': timedelta(days=7),      # H2H rarely changes
            'match_results': timedelta(days=30),    # Historical results don't change
            'live_scores': timedelta(minutes=5),    # Live scores need frequent updates
            'tournament_info': timedelta(days=1),   # Tournament info is relatively stable
            'player_bio': timedelta(days=7),        # Bio info changes infrequently
            'default': timedelta(hours=2)           # Default TTL for unspecified types
        }
        
        # Cache statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'expired': 0,
            'writes': 0
        }
        
        self._cleanup_old_cache()
    
    def _get_cache_path(self, key: str, data_type: str) -> Path:
        """Generate cache file path for a key"""
        # Create hash of key to handle long keys and special characters
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        # Sanitize type for filenames
        safe_type = "".join(
            c if (c.isalnum() or c in ("-", "_")) else "_" 
            for c in data_type
        )
        filename = f"{safe_type}_{key_hash}.cache"
        return self.cache_dir / filename
        
    def _cleanup_old_cache(self):
        """Remove expired cache files on startup based on TTL configuration"""
        current_time = datetime.now()
        grace_period = timedelta(hours=1)  # Grace period for cleanup
        
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                # Try to infer data type from filename
                parts = cache_file.stem.rsplit('_', 1)
                if len(parts) >= 1:
                    data_type = parts[0]
                else:
                    data_type = 'default'
                
                # Get TTL for this data type
                ttl = self.cache_config.get(data_type, self.cache_config['default'])
                
                # Calculate expiry time based on file modification time + TTL + grace
                file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                expiry_time = file_mtime + ttl + grace_period
                
                if current_time > expiry_time:
                    cache_file.unlink()
                    logger.debug("Removed expired cache file: %s", cache_file.name)
                    
            except (OSError, FileNotFoundError):
                # File disappeared or other OS error, skip
                pass
            except (pickle.PickleError, EOFError, AttributeError, TypeError, KeyError) as e:
                # Corrupt cache file, delete it
                try:
                    cache_file.unlink()
                    logger.warning("Removed corrupt cache file %s: %s", cache_file.name, e)
                except (OSError, FileNotFoundError):
                    pass
    
    def get(self, key: str, data_type: str) -> Optional[Any]:
        """
        Retrieve cached data if still valid
        
        Args:
            key: Cache key
            data_type: Type of data for TTL lookup
            
        Returns:
            Cached data if valid, None if expired or not found
        """
        cache_path = self._get_cache_path(key, data_type)
        
        if not cache_path.exists():
            self.stats['misses'] += 1
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                cache_entry = pickle.load(f)
            
            # Defensive validation: verify cache entry integrity
            if (cache_entry.get('key') != key or 
                cache_entry.get('data_type') != data_type):
                # Cache file is corrupted or has wrong content
                self.stats['misses'] += 1
                try:
                    cache_path.unlink()
                    logger.warning("Removed corrupted cache file with mismatched metadata: %s", cache_path.name)
                except (OSError, FileNotFoundError):
                    pass
                return None
            
            # Check if cache entry is still valid
            ttl = self.cache_config.get(data_type, self.cache_config['default'])
            if datetime.now() - cache_entry['timestamp'] > ttl:
                # Cache expired
                self.stats['expired'] += 1
                cache_path.unlink()  # Remove expired cache
                return None
            
            self.stats['hits'] += 1
            return cache_entry['data']
            
        except (FileNotFoundError, pickle.PickleError, EOFError, AttributeError, TypeError, KeyError, OSError):
            self.stats['misses'] += 1
            # Try to clean up corrupted file
            try:
                if cache_path.exists():
                    cache_path.unlink()
                    logger.debug("Removed corrupted cache file: %s", cache_path.name)
            except (OSError, FileNotFoundError):
                pass
            return None
    
    def set(self, key: str, data: Any, data_type: str) -> None:
        """
        Cache data with appropriate TTL using atomic file writing
        
        Args:
            key: Cache key
            data: Data to cache
            data_type: Type of data for TTL lookup
        """
        cache_path = self._get_cache_path(key, data_type)
        
        cache_entry = {
            'data': data,
            'timestamp': datetime.now(),
            'data_type': data_type,
            'key': key
        }
        
        tmp_name = None
        try:
            # Atomic write via temp file
            with tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False) as tmp:
                pickle.dump(cache_entry, tmp, protocol=pickle.HIGHEST_PROTOCOL)
                tmp.flush()
                # Handle potential file descriptor issues (e.g., in testing)
                try:
                    fileno = tmp.fileno()
                    if isinstance(fileno, int):
                        os.fsync(fileno)
                except (TypeError, OSError, AttributeError):
                    # If fsync fails, continue without it (not critical for cache)
                    pass
                tmp_name = tmp.name
            os.replace(tmp_name, cache_path)
            self.stats['writes'] += 1
            
        except (OSError, pickle.PickleError, AttributeError) as e:
            logger.warning("Failed to cache data for key %s: %s", key, e)
            # Best-effort cleanup of temp file
            try:
                if tmp_name and os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except (OSError, NameError):
                pass
    
    def invalidate(self, key: str, data_type: str) -> bool:
        """
        Manually invalidate cache entry
        
        Args:
            key: Cache key
            data_type: Type of data
            
        Returns:
            True if cache was invalidated, False if not found
        """
        cache_path = self._get_cache_path(key, data_type)
        
        try:
            cache_path.unlink()
            return True
        except FileNotFoundError:
            return False
    
    def invalidate_by_type(self, data_type: str) -> int:
        """
        Invalidate all cache entries of a specific type
        
        Args:
            data_type: Type of data to invalidate
            
        Returns:
            Number of entries invalidated
        """
        count = 0

        # Sanitize data_type to prevent glob metacharacter injection
        safe_type = "".join(
            c if (c.isalnum() or c in ("-", "_")) else "_" 
            for c in data_type
        )
        prefix = f"{safe_type}_"

        # Match only .cache files, then filter by the sanitized prefix
        for cache_file in self.cache_dir.glob("*.cache"):
            if not cache_file.name.startswith(prefix):
                continue
            try:
                cache_file.unlink()
                count += 1
            except FileNotFoundError:
                pass
        
        return count
    
    def clear_all(self) -> int:
        """
        Clear all cache entries
        
        Returns:
            Number of entries cleared
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                cache_file.unlink()
                count += 1
            except FileNotFoundError:
                pass
        
        return count
    
    def get_cache_size(self) -> CacheSizeInfo:
        """
        Get cache size information
        
        Returns:
            Dictionary with cache statistics
        """
        total_files = 0
        total_size = 0
        type_counts = {}
        
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                total_files += 1
                total_size += cache_file.stat().st_size
                
                # Extract data type from filename
                parts = cache_file.stem.rsplit('_', 1)
                if len(parts) >= 1:
                    data_type = parts[0]
                    type_counts[data_type] = type_counts.get(data_type, 0) + 1
                    
            except (OSError, FileNotFoundError):
                pass
        
        result: CacheSizeInfo = {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'type_counts': type_counts,
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'expired': self.stats['expired'],
            'writes': self.stats['writes']
        }
        return result
    
    def get_cache_info(self, key: str, data_type: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific cache entry
        
        Args:
            key: Cache key
            data_type: Type of data
            
        Returns:
            Cache entry info or None if not found
        """
        cache_path = self._get_cache_path(key, data_type)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                cache_entry = pickle.load(f)
            
            # Validate cache entry integrity
            if (cache_entry.get('key') != key or 
                cache_entry.get('data_type') != data_type):
                return None
            
            ttl = self.cache_config.get(data_type, self.cache_config['default'])
            expires_at = cache_entry['timestamp'] + ttl
            is_expired = datetime.now() > expires_at
            
            return {
                'key': cache_entry['key'],
                'data_type': cache_entry['data_type'],
                'cached_at': cache_entry['timestamp'].isoformat(),
                'expires_at': expires_at.isoformat(),
                'is_expired': is_expired,
                'ttl_seconds': ttl.total_seconds(),
                'file_size_bytes': cache_path.stat().st_size
            }
            
        except (FileNotFoundError, pickle.PickleError, EOFError, AttributeError, TypeError, KeyError, OSError):
            return None
    
    def update_ttl_config(self, data_type: str, ttl: timedelta):
        """
        Update TTL configuration for a data type
        
        Args:
            data_type: Type of data
            ttl: New TTL duration
        """
        if not isinstance(ttl, timedelta) or ttl <= timedelta(0):
            raise ValueError("ttl must be a positive timedelta")
        self.cache_config[data_type] = ttl
        
    def warmup_cache(self, data_type: str, force: bool = False) -> Dict[str, Any]:
        """
        Warm up cache by checking all entries of a type
        
        Args:
            data_type: Type of data to check
            force: If True, removes expired entries
            
        Returns:
            Summary of warmup operation
        """
        pattern = f"{data_type}_*.cache"
        checked = 0
        expired = 0
        valid = 0
        
        for cache_file in self.cache_dir.glob(pattern):
            try:
                with open(cache_file, 'rb') as f:
                    cache_entry = pickle.load(f)
                
                checked += 1
                ttl = self.cache_config.get(data_type, self.cache_config['default'])
                
                if datetime.now() - cache_entry['timestamp'] > ttl:
                    expired += 1
                    if force:
                        cache_file.unlink()
                else:
                    valid += 1
                    
            except (FileNotFoundError, pickle.PickleError, KeyError, OSError):
                pass
        
        return {
            'data_type': data_type,
            'checked': checked,
            'valid': valid,
            'expired': expired,
            'removed': expired if force else 0
        }


class MemoryCache:
    """Simple in-memory cache for frequently accessed data with true LRU eviction"""
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize memory cache
        
        Args:
            max_size: Maximum number of entries to keep in memory
        """
        self.cache = OrderedDict()  # LRU ordering: least recent first
        self.max_size = max_size
        
        # TTL for memory cache (shorter than disk cache)
        self.memory_ttl = {
            'player_stats': timedelta(minutes=30),
            'rankings': timedelta(hours=2),
            'tournament_draws': timedelta(minutes=15),
            'default': timedelta(minutes=30)
        }
    
    def get(self, key: str, data_type: str) -> Optional[Any]:
        """Get data from memory cache"""
        ckey = (data_type, key)
        if ckey not in self.cache:
            return None
        
        entry = self.cache[ckey]
        ttl = self.memory_ttl.get(data_type, self.memory_ttl['default'])
        
        if datetime.now() - entry['timestamp'] > ttl:
            # Expired - remove from cache
            del self.cache[ckey]
            return None
        
        # Move to end (most recently used) and return data
        self.cache.move_to_end(ckey)
        return entry['data']
        
    def set(self, key: str, data: Any, data_type: str):
        """Set data in memory cache"""
        ckey = (data_type, key)
        
        # If key already exists, update it
        if ckey in self.cache:
            self.cache[ckey] = {
                'data': data,
                'timestamp': datetime.now(),
                'data_type': data_type
            }
            self.cache.move_to_end(ckey)  # Move to end (most recently used)
            return
        
        # Remove oldest entries if at capacity
        if len(self.cache) >= self.max_size:
            self._evict_oldest()

        # Add new entry at end (most recently used)
        self.cache[ckey] = {
            'data': data,
            'timestamp': datetime.now(),
            'data_type': data_type
        }
    
    def _evict_oldest(self):
        """Remove oldest entries to make room using true LRU"""
        if not self.cache:
            return
        
        # Remove the 10% oldest entries (or at least 1)
        num_to_remove = max(1, len(self.cache) // 10)
        
        for _ in range(num_to_remove):
            if self.cache:
                self.cache.popitem(last=False)  # Remove least recently used
    
    def clear(self):
        """Clear memory cache"""
        self.cache.clear()
    
    def size(self) -> int:
        """Get current cache size"""
        return len(self.cache)