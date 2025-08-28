#!/usr/bin/env python3
"""
Comprehensive test script for the rate limiter and related components
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add tennis_api to path
sys.path.insert(0, str(Path(__file__).parent))

from tennis_api.cache.rate_limiter import RateLimiter
from tennis_api.config.api_config import APIConfig, get_api_config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_rate_limiter_basic():
    """Test basic rate limiter functionality"""
    print("=== Testing Rate Limiter Basic Functionality ===")
    
    state_file = "test_basic_rate_limiter_state.json"
    
    # Clean up any existing state file to start fresh
    try:
        Path(state_file).unlink(missing_ok=True)
    except:
        pass
    
    # Create test rate limiter with low limits
    test_limits = {
        'basic_test_api': {
            'requests_per_minute': 3,
            'requests_per_hour': 10,
            'requests_per_day': 50,
            'requests_per_month': 100
        }
    }
    
    limiter = None
    try:
        limiter = RateLimiter(limits_config=test_limits, state_file=state_file)
        
        # Test availability check
        availability = limiter.check_availability('basic_test_api', 'normal')
        print(f"Initial availability: {availability}")
        assert availability['available'] is True, "Should be available initially"
        
        # Test acquiring requests
        print("Testing request acquisition...")
        for i in range(3):
            result = limiter.acquire('basic_test_api', 'normal')
            print(f"Request {i+1}: {result}")
            assert result is True, f"Request {i+1} should succeed"
        
        # Fourth request should fail (minute limit exceeded)
        result = limiter.acquire('basic_test_api', 'normal')
        print(f"Request 4 (should fail): {result}")
        assert result is False, "Request 4 should fail due to minute limit"
        
        # Check availability after limit exceeded
        availability = limiter.check_availability('basic_test_api', 'normal')
        print(f"Availability after limit exceeded: {availability}")
        assert availability['available'] is False, "Should not be available after limit exceeded"
        
        print("✅ Basic rate limiter functionality works correctly\n")
        
    finally:
        # Clean up the test state file in multiple locations
        if limiter:
            try:
                limiter._save_state()
            except:
                pass
        
        # Clean up both potential locations of state file
        try:
            Path(state_file).unlink(missing_ok=True)
        except:
            pass
        try:
            (Path("cache") / state_file).unlink(missing_ok=True)
        except:
            pass


def test_rate_limiter_priority():
    """Test priority-based rate limiting"""
    print("=== Testing Rate Limiter Priority System ===")
    
    # Use isolated state file to avoid interference with other tests
    state_file = "test_priority_rate_limiter_state.json"
    
    # Clean up any existing state file
    try:
        Path(state_file).unlink(missing_ok=True)
    except:
        pass
    
    try:
        limiter = RateLimiter(state_file=state_file)
        
        # Test different priority levels
        priorities = ['critical', 'high', 'normal', 'low', 'background']
        
        for priority in priorities:
            availability = limiter.check_availability('rapidapi_tennis_live', priority)
            priority_factor = availability.get('priority_factor', 0)
            print(f"Priority '{priority}': factor = {priority_factor}")
            
            expected_factor = limiter.priority_weights.get(priority, 0.6)
            assert abs(priority_factor - expected_factor) < 0.001, f"Priority factor mismatch for {priority}"
        
        print("✅ Priority system works correctly\n")
        
    finally:
        # Clean up the test state file
        try:
            Path(state_file).unlink(missing_ok=True)
        except:
            pass


async def test_rate_limiter_async():
    """Test async rate limiting functionality"""
    print("=== Testing Async Rate Limiting ===")
    
    state_file = "test_async_rate_limiter_state.json"
    
    # Force clean up any existing state file to start fresh
    cache_path = Path("cache") / state_file
    try:
        cache_path.unlink(missing_ok=True)
    except:
        pass
    try:
        Path(state_file).unlink(missing_ok=True)
    except:
        pass
    
    # Create rate limiter with very low limits for testing
    test_limits = {
        'async_test_api': {
            'requests_per_minute': 2,
            'requests_per_hour': 5,
            'requests_per_day': 20,
            'requests_per_month': 50
        }
    }
    
    limiter = None
    try:
        limiter = RateLimiter(limits_config=test_limits, state_file=state_file)
        
        # Acquire two requests (should succeed)
        result1 = await limiter.acquire_async('async_test_api', 'high', max_wait=2)
        result2 = await limiter.acquire_async('async_test_api', 'high', max_wait=2)
        
        print(f"Async request 1: {result1}")
        print(f"Async request 2: {result2}")
        
        assert result1 is True, "First async request should succeed"
        assert result2 is True, "Second async request should succeed"
        
        # Third request should either fail or wait (reduced time for faster tests)
        start_time = time.time()
        result3 = await limiter.acquire_async('async_test_api', 'high', max_wait=1)  # Reduced from 2 to 1
        end_time = time.time()
        
        print(f"Async request 3: {result3} (took {end_time - start_time:.2f}s)")
        
        print("✅ Async rate limiting works correctly\n")
        
    finally:
        # Cleanup - save state and remove test file in both locations
        if limiter:
            try:
                limiter._save_state()
            except:
                pass
        
        # Clean up the test state file in both locations
        try:
            Path(state_file).unlink(missing_ok=True)
        except:
            pass
        try:
            (Path("cache") / state_file).unlink(missing_ok=True)
        except:
            pass


def test_rate_limiter_state_persistence():
    """Test state persistence functionality"""
    print("=== Testing State Persistence ===")
    
    state_file = "test_persistence_state.json"
    
    # Create first limiter and make some requests
    limiter1 = RateLimiter(state_file=state_file)
    limiter1.acquire('rapidapi_tennis_live', 'normal')
    limiter1.acquire('rapidapi_tennis_live', 'normal')
    
    stats1 = limiter1.get_usage_stats('rapidapi_tennis_live')
    print(f"Stats before persistence: {stats1}")
    
    # Save state
    limiter1._save_state()
    
    # Create new limiter with same state file
    limiter2 = RateLimiter(state_file=state_file)
    stats2 = limiter2.get_usage_stats('rapidapi_tennis_live')
    print(f"Stats after loading: {stats2}")
    
    # Check that usage was preserved
    assert stats2['current_usage']['minute'] >= 2, "Usage should be preserved after loading"
    
    # Clean up
    Path(state_file).unlink(missing_ok=True)
    
    print("✅ State persistence works correctly\n")


def test_rate_limiter_usage_stats():
    """Test usage statistics functionality"""
    print("=== Testing Usage Statistics ===")
    
    # Use isolated state file to avoid interference with other tests
    state_file = "test_usage_stats_rate_limiter_state.json"
    
    # Clean up any existing state file
    try:
        Path(state_file).unlink(missing_ok=True)
    except:
        pass
    
    try:
        limiter = RateLimiter(state_file=state_file)
        
        # Make some requests
        for i in range(3):
            limiter.acquire('rapidapi_tennis_live', 'normal')
        
        # Get stats for specific API
        stats = limiter.get_usage_stats('rapidapi_tennis_live')
        print(f"API stats: {json.dumps(stats, indent=2, default=str)}")
        
        assert 'current_usage' in stats, "Stats should include current usage"
        assert 'limits' in stats, "Stats should include limits"
        assert 'usage_percentages' in stats, "Stats should include usage percentages"
        assert stats['current_usage']['minute'] >= 3, "Should have recorded the requests"
        
        # Get stats for all APIs
        all_stats = limiter.get_usage_stats()
        print(f"All API stats keys: {list(all_stats.keys())}")
        
        assert 'rapidapi_tennis_live' in all_stats, "Should include stats for used API"
        
        print("✅ Usage statistics work correctly\n")
        
    finally:
        # Clean up the test state file
        try:
            Path(state_file).unlink(missing_ok=True)
        except:
            pass


def test_rate_limiter_edge_cases():
    """Test edge cases and error handling"""
    print("=== Testing Edge Cases ===")
    
    # Use isolated state file to avoid interference with other tests
    state_file = "test_edge_cases_rate_limiter_state.json"
    
    # Clean up any existing state file
    try:
        Path(state_file).unlink(missing_ok=True)
    except:
        pass
    
    try:
        limiter = RateLimiter(state_file=state_file)
        
        # Test unknown API
        availability = limiter.check_availability('unknown_api', 'normal')
        print(f"Unknown API availability: {availability}")
        assert availability['available'] is False, "Unknown API should not be available"
        
        result = limiter.acquire('unknown_api', 'normal')
        print(f"Unknown API acquire: {result}")
        assert result is False, "Unknown API acquire should fail"
        
        # Test invalid priority
        availability = limiter.check_availability('rapidapi_tennis_live', 'invalid_priority')
        print(f"Invalid priority availability: {availability}")
        assert 'priority_factor' in availability, "Should handle invalid priority gracefully"
        
        # Test recommended delay
        delay = limiter.get_recommended_delay('rapidapi_tennis_live', 'normal')
        print(f"Recommended delay: {delay}s")
        assert delay >= 0, "Delay should be non-negative"
        
        delay_unknown = limiter.get_recommended_delay('unknown_api', 'normal')
        print(f"Recommended delay for unknown API: {delay_unknown}s")
        assert delay_unknown == 1.0, "Should return default delay for unknown API"
        
        print("✅ Edge cases handled correctly\n")
        
    finally:
        # Clean up the test state file
        try:
            Path(state_file).unlink(missing_ok=True)
        except:
            pass


def test_rate_limiter_thread_safety():
    """Test thread safety using concurrent operations"""
    print("=== Testing Thread Safety ===")
    
    import threading
    
    # Use isolated state file to avoid interference with other tests
    state_file = "test_thread_safety_rate_limiter_state.json"
    
    # Force clean up any existing state file to start fresh
    cache_path = Path("cache") / state_file
    try:
        cache_path.unlink(missing_ok=True)
    except:
        pass
    try:
        Path(state_file).unlink(missing_ok=True)
    except:
        pass
    
    # Create rate limiter with reasonable limits
    test_limits = {
        'thread_test_api': {
            'requests_per_minute': 50,
            'requests_per_hour': 200,
            'requests_per_day': 1000,
            'requests_per_month': 5000
        }
    }
    
    try:
        limiter = RateLimiter(limits_config=test_limits, state_file=state_file)
        
        success_count = [0]  # Use list to modify from inner function
        total_requests = 100
        
        def make_requests():
            for _ in range(10):
                if limiter.acquire('thread_test_api', 'normal'):
                    success_count[0] += 1
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_requests)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        print(f"Successful requests: {success_count[0]}/{total_requests}")
        
        # Verify that we didn't exceed the minute limit
        stats = limiter.get_usage_stats('thread_test_api')
        actual_usage = stats['current_usage']['minute']
        
        print(f"Actual usage recorded: {actual_usage}")
        assert actual_usage == success_count[0], "Usage count should match successful requests"
        assert actual_usage <= 50, "Should not exceed minute limit"
        
        print("✅ Thread safety works correctly\n")
        
    finally:
        # Clean up the test state file in both locations
        try:
            Path(state_file).unlink(missing_ok=True)
        except:
            pass
        try:
            (Path("cache") / state_file).unlink(missing_ok=True)
        except:
            pass


def test_api_config_loading():
    """Test API configuration loading"""
    print("=== Testing API Configuration Loading ===")
    
    try:
        config = get_api_config()
        print(f"Loaded config successfully")
        print(f"API priorities: {config.api_priorities}")
        
        # Test that we can create an APIConfig object
        manual_config = APIConfig(rapid_api_key="test_key_for_testing")
        print(f"Manual config created successfully")
        
        print("✅ API configuration loading works correctly\n")
        
    except Exception as e:
        print(f"⚠️  API configuration loading failed (expected if no .env file): {e}\n")


def test_type_annotations():
    """Test that type annotations are working correctly"""
    print("=== Testing Type Annotations ===")
    
    # Use isolated state file to avoid interference with other tests
    state_file = "test_type_annotations_rate_limiter_state.json"
    
    # Clean up any existing state file
    try:
        Path(state_file).unlink(missing_ok=True)
    except:
        pass
    
    try:
        limiter = RateLimiter(state_file=state_file)
        
        # Test return types
        availability = limiter.check_availability('rapidapi_tennis_live', 'normal')
        assert isinstance(availability, dict), "check_availability should return dict"
        
        result = limiter.acquire('rapidapi_tennis_live', 'normal')  
        assert isinstance(result, bool), "acquire should return bool"
        
        stats = limiter.get_usage_stats('rapidapi_tennis_live')
        assert isinstance(stats, dict), "get_usage_stats should return dict"
        
        delay = limiter.get_recommended_delay('rapidapi_tennis_live', 'normal')
        assert isinstance(delay, (int, float)), "get_recommended_delay should return number"
        
        print("✅ Type annotations work correctly\n")
        
    finally:
        # Clean up the test state file
        try:
            Path(state_file).unlink(missing_ok=True)
        except:
            pass


async def main():
    """Run all tests"""
    print("🚀 Starting comprehensive rate limiter tests...\n")
    
    try:
        # Basic functionality tests
        test_rate_limiter_basic()
        test_rate_limiter_priority()
        test_rate_limiter_state_persistence()
        test_rate_limiter_usage_stats()
        test_rate_limiter_edge_cases()
        test_rate_limiter_thread_safety()
        test_api_config_loading()
        test_type_annotations()
        
        # Async tests
        await test_rate_limiter_async()
        
        print("🎉 All tests passed successfully!")
        
        # Clean up test files
        for test_file in ["test_rate_limiter_state.json", "test_async_rate_limiter_state.json"]:
            Path(test_file).unlink(missing_ok=True)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)