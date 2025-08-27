#!/usr/bin/env python3
"""
Cache Manager Edge Case Validation

Tests the key edge cases and boundary conditions to lock down behavior.
"""

import os
import tempfile
import time
import pickle
from datetime import datetime, timedelta
from pathlib import Path

from tennis_api.cache.cache_manager import CacheManager, MemoryCache


def test_ttl_expiry_boundary():
    """Test TTL expiry at exact boundaries"""
    print("Testing TTL expiry boundary conditions...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_manager = CacheManager(temp_dir)
        
        # Set a very short TTL for testing
        test_ttl = timedelta(seconds=1)
        cache_manager.cache_config['test_type'] = test_ttl
        
        # Cache some data
        cache_manager.set('test_key', 'test_data', 'test_type')
        
        # Verify it's cached
        result = cache_manager.get('test_key', 'test_type')
        assert result == 'test_data', f"Expected 'test_data', got {result}"
        
        # Wait exactly the TTL duration
        time.sleep(1.1)  # Slightly over TTL to ensure expiry
        
        # Should be expired now
        result = cache_manager.get('test_key', 'test_type')
        assert result is None, f"Expected None (expired), got {result}"
        assert cache_manager.stats['expired'] == 1, f"Expected 1 expiry, got {cache_manager.stats['expired']}"
    
    print("✓ TTL expiry boundary test passed")


def test_type_parsing_with_underscores():
    """Test cache size type parsing when data_type contains underscores"""
    print("Testing type parsing with underscores...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_manager = CacheManager(temp_dir)
        
        # Cache data with underscores in type names
        cache_manager.set('key1', 'data1', 'player_stats')
        cache_manager.set('key2', 'data2', 'player_stats')
        cache_manager.set('key3', 'data3', 'tournament_draw_men_singles')
        
        size_info = cache_manager.get_cache_size()
        
        # Should correctly parse type despite underscores
        assert 'player_stats' in size_info['type_counts'], "player_stats not found in type_counts"
        assert size_info['type_counts']['player_stats'] == 2, f"Expected 2 player_stats entries, got {size_info['type_counts']['player_stats']}"
        assert 'tournament_draw_men_singles' in size_info['type_counts'], "tournament_draw_men_singles not found"
        assert size_info['type_counts']['tournament_draw_men_singles'] == 1, f"Expected 1 tournament entry"
    
    print("✓ Type parsing with underscores test passed")


def test_memory_cache_collisions():
    """Test memory cache behavior with type/key collisions"""
    print("Testing memory cache collisions...")
    
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
    
    print("✓ Memory cache collision test passed")


def test_memory_cache_lru_behavior():
    """Test LRU ordering works correctly"""
    print("Testing memory cache LRU behavior...")
    
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
    
    print("✓ Memory cache LRU test passed")


def test_cache_integrity_validation():
    """Test cache integrity validation behavior"""
    print("Testing cache integrity validation...")
    
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
        
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'wb') as f:
            pickle.dump(corrupted_entry, f)
        
        # Should detect corruption and return None
        result = cache_manager.get('requested_key', 'test_type')
        assert result is None, f"Expected None for corrupted cache, got {result}"
        assert cache_manager.stats['misses'] == 1
        
        # Corrupted file should be removed
        assert not cache_path.exists(), "Corrupted file should have been removed"
    
    print("✓ Cache integrity validation test passed")


def test_warmup_force_behavior():
    """Test warmup force=True removes only expired entries"""
    print("Testing warmup force behavior...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_manager = CacheManager(temp_dir)
        
        # Set short TTL for testing
        cache_manager.cache_config['test_type'] = timedelta(seconds=1)
        
        # Create valid entry
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
        assert result['checked'] == 2, f"Expected 2 checked, got {result['checked']}"
        assert result['expired'] == 1, f"Expected 1 expired, got {result['expired']}"
        assert result['removed'] == 1, f"Expected 1 removed, got {result['removed']}"
        assert result['valid'] == 1, f"Expected 1 valid, got {result['valid']}"
        
        # Valid entry should still exist
        assert cache_manager.get('valid_key', 'test_type') == 'valid_data'
        
        # Expired entry should be gone
        assert cache_manager.get('expired_key', 'test_type') is None
    
    print("✓ Warmup force behavior test passed")


def test_cache_size_info_structure():
    """Test CacheSizeInfo TypedDict return type"""
    print("Testing cache size info structure...")
    
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
    
    print("✓ Cache size info structure test passed")


def main():
    """Run all validation tests"""
    print("=== Cache Manager Edge Case Validation ===\n")
    
    tests = [
        test_ttl_expiry_boundary,
        test_type_parsing_with_underscores,
        test_memory_cache_collisions,
        test_memory_cache_lru_behavior,
        test_cache_integrity_validation,
        test_warmup_force_behavior,
        test_cache_size_info_structure
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n=== Results ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All edge case tests passed! Cache behavior is locked down.")
    else:
        print(f"\n❌ {failed} test(s) failed. Please review the issues above.")
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())