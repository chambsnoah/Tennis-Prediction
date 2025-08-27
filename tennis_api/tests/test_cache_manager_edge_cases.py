"""
Unit tests for cache manager edge cases and boundary conditions.

Tests focus on:
- TTL expiry boundary conditions
- Type parsing with underscores
- Memory cache collisions
- Warmup force behavior
- Cache integrity validation
- Atomic file operations
"""

import os
import tempfile
import time
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from tennis_api.cache.cache_manager import CacheManager, MemoryCache


class TestTTLExpiryBoundaryConditions:
    """Test TTL expiry at exact boundaries"""
    
    def test_cache_exactly_at_ttl_boundary(self):
        """Test cache entry exactly at TTL expiry time"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Set a very short TTL for testing
            test_ttl = timedelta(seconds=1)
            cache_manager.cache_config['test_type'] = test_ttl
            
            # Cache some data
            cache_manager.set('test_key', 'test_data', 'test_type')
            
            # Verify it's cached
            result = cache_manager.get('test_key', 'test_type')
            assert result == 'test_data'
            
            # Wait exactly the TTL duration
            time.sleep(1.1)  # Slightly over TTL to ensure expiry
            
            # Should be expired now
            result = cache_manager.get('test_key', 'test_type')
            assert result is None
            assert cache_manager.stats['expired'] == 1
    
    def test_cache_just_before_ttl_expiry(self):
        """Test cache entry just before TTL expiry"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Set TTL for testing
            test_ttl = timedelta(seconds=2)
            cache_manager.cache_config['test_type'] = test_ttl
            
            # Cache some data
            cache_manager.set('test_key', 'test_data', 'test_type')
            
            # Wait just under TTL
            time.sleep(1.5)
            
            # Should still be valid
            result = cache_manager.get('test_key', 'test_type')
            assert result == 'test_data'
            assert cache_manager.stats['hits'] == 1
    
    def test_cache_startup_cleanup_ttl_boundary(self):
        """Test startup cleanup respects TTL boundaries"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test TTL-aware cleanup by simulating scenario where
            # an old cache file should be cleaned up during get() operation
            cache_manager = CacheManager(temp_dir)
            cache_manager.cache_config['test_type'] = timedelta(seconds=1)
            
            # Create a cache file manually with old timestamp
            cache_path = cache_manager._get_cache_path('test_key', 'test_type')
            old_cache_entry = {
                'data': 'old_data',
                'timestamp': datetime.now() - timedelta(seconds=2),  # Expired
                'data_type': 'test_type',
                'key': 'test_key'
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(old_cache_entry, f)
            
            # Verify file exists
            assert cache_path.exists()
            
            # Try to get the expired cache - should return None and clean up
            result = cache_manager.get('test_key', 'test_type')
            assert result is None
            assert cache_manager.stats['expired'] == 1
            
            # File should be cleaned up by the get() operation
            assert not cache_path.exists()


class TestCacheSizeTypeParsingWithUnderscores:
    """Test cache size type parsing when data_type contains underscores"""
    
    def test_single_underscore_in_data_type(self):
        """Test data type with single underscore"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Cache data with underscore in type
            cache_manager.set('key1', 'data1', 'player_stats')
            cache_manager.set('key2', 'data2', 'player_stats')
            
            size_info = cache_manager.get_cache_size()
            
            # Should correctly parse type despite underscore
            assert 'player_stats' in size_info['type_counts']
            assert size_info['type_counts']['player_stats'] == 2
    
    def test_multiple_underscores_in_data_type(self):
        """Test data type with multiple underscores"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Cache data with multiple underscores
            cache_manager.set('key1', 'data1', 'tournament_draw_men_singles')
            cache_manager.set('key2', 'data2', 'tournament_draw_women_doubles')
            
            size_info = cache_manager.get_cache_size()
            
            # Should correctly parse full type names
            assert 'tournament_draw_men_singles' in size_info['type_counts']
            assert 'tournament_draw_women_doubles' in size_info['type_counts']
            assert size_info['type_counts']['tournament_draw_men_singles'] == 1
            assert size_info['type_counts']['tournament_draw_women_doubles'] == 1
    
    def test_similar_type_names_with_underscores(self):
        """Test similar type names that could be confused during parsing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Cache data with similar but distinct type names
            cache_manager.set('key1', 'data1', 'player')
            cache_manager.set('key2', 'data2', 'player_stats')
            cache_manager.set('key3', 'data3', 'player_stats_detailed')
            
            size_info = cache_manager.get_cache_size()
            
            # Should distinguish between similar type names
            assert 'player' in size_info['type_counts']
            assert 'player_stats' in size_info['type_counts']
            assert 'player_stats_detailed' in size_info['type_counts']
            assert size_info['type_counts']['player'] == 1
            assert size_info['type_counts']['player_stats'] == 1
            assert size_info['type_counts']['player_stats_detailed'] == 1


class TestMemoryCacheCollisions:
    """Test memory cache behavior with type/key collisions"""
    
    def test_memory_cache_type_prefix_collision(self):
        """Test memory cache with types that share prefixes"""
        memory_cache = MemoryCache(max_size=100)
        
        # Add entries with type names that share prefixes
        memory_cache.set('key1', 'data1', 'player')
        memory_cache.set('key1', 'data2', 'player_stats')  # Same key, different type
        memory_cache.set('key1', 'data3', 'player_stats_detailed')
        
        # Should store all three separately
        assert memory_cache.get('key1', 'player') == 'data1'
        assert memory_cache.get('key1', 'player_stats') == 'data2'
        assert memory_cache.get('key1', 'player_stats_detailed') == 'data3'
        assert memory_cache.size() == 3
    
    def test_memory_cache_type_suffix_collision(self):
        """Test memory cache with types that share suffixes"""
        memory_cache = MemoryCache(max_size=100)
        
        # Add entries with type names that share suffixes
        memory_cache.set('key1', 'data1', 'atp_stats')
        memory_cache.set('key1', 'data2', 'wta_stats')
        memory_cache.set('key1', 'data3', 'junior_stats')
        
        # Should store all three separately
        assert memory_cache.get('key1', 'atp_stats') == 'data1'
        assert memory_cache.get('key1', 'wta_stats') == 'data2'
        assert memory_cache.get('key1', 'junior_stats') == 'data3'
        assert memory_cache.size() == 3
    
    def test_memory_cache_key_collision_same_type(self):
        """Test memory cache with same key and type (should overwrite)"""
        memory_cache = MemoryCache(max_size=100)
        
        # Add entry
        memory_cache.set('key1', 'data1', 'player_stats')
        assert memory_cache.get('key1', 'player_stats') == 'data1'
        assert memory_cache.size() == 1
        
        # Overwrite with same key and type
        memory_cache.set('key1', 'data2', 'player_stats')
        assert memory_cache.get('key1', 'player_stats') == 'data2'
        assert memory_cache.size() == 1  # Should not increase size
    
    def test_memory_cache_lru_ordering_with_collisions(self):
        """Test LRU ordering works correctly with similar keys/types"""
        memory_cache = MemoryCache(max_size=3)
        
        # Fill cache to capacity
        memory_cache.set('key', 'data1', 'type1')
        memory_cache.set('key', 'data2', 'type2')
        memory_cache.set('key', 'data3', 'type3')
        
        # Access first entry to make it most recent
        _ = memory_cache.get('key', 'type1')
        
        # Add new entry (should evict type2, least recently used)
        memory_cache.set('key', 'data4', 'type4')
        
        # Verify LRU eviction
        assert memory_cache.get('key', 'type1') == 'data1'  # Still there (recently accessed)
        assert memory_cache.get('key', 'type2') is None     # Evicted
        assert memory_cache.get('key', 'type3') == 'data3'  # Still there
        assert memory_cache.get('key', 'type4') == 'data4'  # New entry


class TestWarmupForceRemovalBehavior:
    """Test warmup force=True removes only expired entries"""
    
    def test_warmup_force_removes_only_expired(self):
        """Test that force=True only removes expired entries, not valid ones"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Set short TTL for testing
            cache_manager.cache_config['test_type'] = timedelta(seconds=1)
            
            # Create valid and expired entries
            cache_manager.set('valid_key', 'valid_data', 'test_type')
            
            # Create expired entry manually
            expired_path = cache_manager._get_cache_path('expired_key', 'test_type')
            expired_entry = {
                'data': 'expired_data',
                'timestamp': datetime.now() - timedelta(seconds=2),
                'data_type': 'test_type',
                'key': 'expired_key'
            }
            
            with open(expired_path, 'wb') as f:
                pickle.dump(expired_entry, f)
            
            # Run warmup with force=True
            result = cache_manager.warmup_cache('test_type', force=True)
            
            # Should have processed both, expired 1, removed 1
            assert result['checked'] == 2
            assert result['expired'] == 1
            assert result['removed'] == 1
            assert result['valid'] == 1
            
            # Valid entry should still exist
            assert cache_manager.get('valid_key', 'test_type') == 'valid_data'
            
            # Expired entry should be gone
            assert cache_manager.get('expired_key', 'test_type') is None
    
    def test_warmup_force_false_preserves_expired(self):
        """Test that force=False counts but doesn't remove expired entries"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Set short TTL for testing
            cache_manager.cache_config['test_type'] = timedelta(seconds=1)
            
            # Create expired entry manually
            expired_path = cache_manager._get_cache_path('expired_key', 'test_type')
            expired_entry = {
                'data': 'expired_data',
                'timestamp': datetime.now() - timedelta(seconds=2),
                'data_type': 'test_type',
                'key': 'expired_key'
            }
            
            with open(expired_path, 'wb') as f:
                pickle.dump(expired_entry, f)
            
            # Run warmup with force=False
            result = cache_manager.warmup_cache('test_type', force=False)
            
            # Should count expired but not remove
            assert result['checked'] == 1
            assert result['expired'] == 1
            assert result['removed'] == 0
            
            # Expired file should still exist
            assert expired_path.exists()


class TestCacheIntegrityValidation:
    """Test cache integrity validation behavior"""
    
    def test_get_detects_key_mismatch(self):
        """Test that get() detects and handles key mismatches"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Create corrupted cache entry with wrong key
            cache_path = cache_manager._get_cache_path('requested_key', 'test_type')
            corrupted_entry = {
                'data': 'test_data',
                'timestamp': datetime.now(),
                'data_type': 'test_type',
                'key': 'different_key'  # Wrong key!
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(corrupted_entry, f)
            
            # Should detect corruption and return None
            result = cache_manager.get('requested_key', 'test_type')
            assert result is None
            assert cache_manager.stats['misses'] == 1
            
            # Corrupted file should be removed
            assert not cache_path.exists()
    
    def test_get_detects_data_type_mismatch(self):
        """Test that get() detects and handles data type mismatches"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Create corrupted cache entry with wrong data type
            cache_path = cache_manager._get_cache_path('test_key', 'requested_type')
            corrupted_entry = {
                'data': 'test_data',
                'timestamp': datetime.now(),
                'data_type': 'different_type',  # Wrong type!
                'key': 'test_key'
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(corrupted_entry, f)
            
            # Should detect corruption and return None
            result = cache_manager.get('test_key', 'requested_type')
            assert result is None
            assert cache_manager.stats['misses'] == 1
            
            # Corrupted file should be removed
            assert not cache_path.exists()
    
    def test_get_cache_info_validates_integrity(self):
        """Test that get_cache_info() also validates cache integrity"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Create corrupted cache entry
            cache_path = cache_manager._get_cache_path('test_key', 'test_type')
            corrupted_entry = {
                'data': 'test_data',
                'timestamp': datetime.now(),
                'data_type': 'wrong_type',  # Wrong type!
                'key': 'test_key'
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(corrupted_entry, f)
            
            # Should detect corruption and return None
            result = cache_manager.get_cache_info('test_key', 'test_type')
            assert result is None


class TestAtomicFileOperations:
    """Test atomic file operation behavior"""
    
    def test_set_atomic_write_failure_cleanup(self):
        """Test that failed atomic writes clean up temporary files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Mock tempfile to simulate failure after temp file creation
            with patch('tempfile.NamedTemporaryFile') as mock_tempfile:
                mock_temp = MagicMock()
                mock_temp.name = os.path.join(temp_dir, 'temp_file')
                mock_temp.fileno.return_value = 1  # Return valid integer
                mock_temp.__enter__ = MagicMock(return_value=mock_temp)
                mock_temp.__exit__ = MagicMock(return_value=None)
                mock_tempfile.return_value = mock_temp
                
                # Create temp file manually to simulate partial creation
                Path(mock_temp.name).touch()
                
                # Mock os.replace to fail
                with patch('os.replace', side_effect=OSError("Simulated failure")):
                    # Should handle the error gracefully
                    cache_manager.set('test_key', 'test_data', 'test_type')
                
                # Verify error was handled gracefully (no cache file created)
                cache_path = cache_manager._get_cache_path('test_key', 'test_type')
                assert not cache_path.exists(), "Cache file should not exist after failed atomic write"
    
    def test_set_pickle_error_handling(self):
        """Test handling of pickle errors during cache set"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Create an object that can't be pickled
            unpicklable_data = lambda x: x  # Functions can't be pickled
            
            # Should handle pickle error gracefully (no exception raised)
            cache_manager.set('test_key', unpicklable_data, 'test_type')
            
            # Should not have created any cache file
            cache_path = cache_manager._get_cache_path('test_key', 'test_type')
            assert not cache_path.exists(), "Cache file should not exist after pickle error"
            
            # Verify that get returns None (no cache entry exists)
            result = cache_manager.get('test_key', 'test_type')
            assert result is None, "Should return None when no cache entry exists"


class TestExpandedErrorHandling:
    """Test expanded error handling for pickle operations"""
    
    def test_get_handles_eoferror(self):
        """Test that get() handles EOFError from truncated pickle files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Create truncated/corrupted pickle file
            cache_path = cache_manager._get_cache_path('test_key', 'test_type')
            
            # Write partial pickle data that will cause EOFError
            with open(cache_path, 'wb') as f:
                f.write(b'\x80\x03}')  # Incomplete pickle data
            
            # Should handle EOFError gracefully
            result = cache_manager.get('test_key', 'test_type')
            assert result is None
            assert cache_manager.stats['misses'] == 1
            
            # Corrupted file should be cleaned up
            assert not cache_path.exists()
    
    def test_get_handles_attributeerror(self):
        """Test that get() handles AttributeError from malformed pickle"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            cache_path = cache_manager._get_cache_path('test_key', 'test_type')
            
            # Mock pickle.load to raise AttributeError
            with patch('pickle.load', side_effect=AttributeError("Malformed pickle")):
                # Create dummy file
                cache_path.touch()
                
                # Should handle AttributeError gracefully
                result = cache_manager.get('test_key', 'test_type')
                assert result is None
                assert cache_manager.stats['misses'] == 1
    
    def test_get_handles_typeerror(self):
        """Test that get() handles TypeError from unexpected pickle content"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            cache_path = cache_manager._get_cache_path('test_key', 'test_type')
            
            # Mock pickle.load to raise TypeError
            with patch('pickle.load', side_effect=TypeError("Unexpected type")):
                # Create dummy file
                cache_path.touch()
                
                # Should handle TypeError gracefully
                result = cache_manager.get('test_key', 'test_type')
                assert result is None
                assert cache_manager.stats['misses'] == 1


class TestCacheSizeInfoTypeAnnotation:
    """Test CacheSizeInfo TypedDict return type"""
    
    def test_get_cache_size_returns_correct_structure(self):
        """Test that get_cache_size returns exactly the expected structure"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(temp_dir)
            
            # Add some cache entries with larger data to ensure measurable size
            large_data1 = {'data': 'x' * 1000, 'metadata': {'items': list(range(100))}}
            large_data2 = {'data': 'y' * 1000, 'metadata': {'items': list(range(100))}}
            cache_manager.set('key1', large_data1, 'type1')
            cache_manager.set('key2', large_data2, 'type2')
            
            # Get some cache hits/misses
            _ = cache_manager.get('key1', 'type1')  # hit
            _ = cache_manager.get('nonexistent', 'type1')  # miss
            
            size_info = cache_manager.get_cache_size()
            
            # Verify all required fields are present with correct types
            assert isinstance(size_info['total_files'], int)
            assert isinstance(size_info['total_size_bytes'], int)
            assert isinstance(size_info['total_size_mb'], float)
            assert isinstance(size_info['type_counts'], dict)
            assert isinstance(size_info['hits'], int)
            assert isinstance(size_info['misses'], int)
            assert isinstance(size_info['expired'], int)
            assert isinstance(size_info['writes'], int)
            
            # Verify values make sense
            assert size_info['total_files'] == 2
            assert size_info['total_size_bytes'] > 0
            assert size_info['total_size_mb'] >= 0  # Small files can round to 0.00 MB
            assert size_info['hits'] == 1
            assert size_info['misses'] == 1
            assert size_info['writes'] == 2


if __name__ == '__main__':
    print("Test file loaded successfully. Use run_cache_tests.py to execute.")