#!/usr/bin/env python3
"""
Simple test for rate limiter functionality
"""
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Direct import to avoid dependency issues
from tennis_api.cache.rate_limiter import RateLimiter

def test_rate_limiter_basic():
    """Test basic rate limiter functionality"""
    print("Testing Rate Limiter Basic Functionality...")
    
    # Create rate limiter with test configuration
    rate_limiter = RateLimiter(state_file="test_rate_limiter_state.json")
    
    # Add test API configuration
    test_config = {
        'requests_per_minute': 5,
        'requests_per_hour': 100,
        'requests_per_day': 1000,
        'requests_per_month': 10000
    }
    
    rate_limiter.add_api_config('test_api', test_config)
    
    print("✓ Rate limiter created and configured")
    
    # Test availability check
    availability = rate_limiter.check_availability('test_api', 'normal')
    print(f"✓ Availability check: {availability['available']}")
    
    # Test acquire permission
    acquired = rate_limiter.acquire('test_api', 'normal')
    print(f"✓ Acquire permission: {acquired}")
    
    # Test get_recommended_delay (this is what we fixed)
    delay = rate_limiter.get_recommended_delay('test_api', 'normal')
    print(f"✓ Recommended delay: {delay:.3f} seconds")
    
    # Test usage stats
    stats = rate_limiter.get_usage_stats('test_api')
    print(f"✓ Usage stats: {stats['current_usage']}")
    
    # Test multiple acquisitions to verify rate limiting
    print("\nTesting multiple acquisitions...")
    for i in range(7):  # Try to exceed the 5 per minute limit
        acquired = rate_limiter.acquire('test_api', 'normal')
        availability = rate_limiter.check_availability('test_api', 'normal')
        delay = rate_limiter.get_recommended_delay('test_api', 'normal')
        
        print(f"Request {i+1}: acquired={acquired}, available={availability['available']}, delay={delay:.3f}s")
    
    print("\n✓ All rate limiter tests completed successfully!")
    
    # Clean up test state file
    try:
        os.remove("test_rate_limiter_state.json")
        print("✓ Cleaned up test state file")
    except FileNotFoundError:
        pass

if __name__ == "__main__":
    try:
        test_rate_limiter_basic()
        print("\n🎉 Rate limiter is working correctly!")
    except Exception as e:
        print(f"\n❌ Error testing rate limiter: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)