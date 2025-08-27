#!/usr/bin/env python3
"""
Standalone test for rate limiter get_recommended_delay functionality
"""
import sys
import os
import tempfile

# Add the tennis_api cache directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tennis_api', 'cache'))

# Import the RateLimiter directly
from tennis_api.cache.rate_limiter import RateLimiter

def test_get_recommended_delay():
    """Test the get_recommended_delay method that was fixed"""
    print("Testing get_recommended_delay method...")
    
    # Create a temporary state file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_state_file = f.name
    
    try:
        # Initialize rate limiter
        rate_limiter = RateLimiter(state_file=temp_state_file)
        
        # Add test API configuration
        test_config = {
            'requests_per_minute': 10,
            'requests_per_hour': 100,
            'requests_per_day': 1000,
            'requests_per_month': 10000
        }
        
        rate_limiter.add_api_config('test_api', test_config)
        print("✓ Rate limiter configured")
        
        # Test get_recommended_delay with no usage
        delay = rate_limiter.get_recommended_delay('test_api', 'normal')
        print(f"✓ Recommended delay (no usage): {delay:.3f} seconds")
        assert delay > 0, "Delay should be positive"
        
        # Test with some usage
        for i in range(3):
            acquired = rate_limiter.acquire('test_api', 'normal')
            print(f"  Acquired request {i+1}: {acquired}")
        
        # Test get_recommended_delay with some usage
        delay = rate_limiter.get_recommended_delay('test_api', 'normal')
        print(f"✓ Recommended delay (with usage): {delay:.3f} seconds")
        
        # Test with high priority
        delay_high = rate_limiter.get_recommended_delay('test_api', 'high')
        print(f"✓ Recommended delay (high priority): {delay_high:.3f} seconds")
        
        # Test with low priority
        delay_low = rate_limiter.get_recommended_delay('test_api', 'low')
        print(f"✓ Recommended delay (low priority): {delay_low:.3f} seconds")
        
        # Test unknown API
        delay_unknown = rate_limiter.get_recommended_delay('unknown_api', 'normal')
        print(f"✓ Recommended delay (unknown API): {delay_unknown:.3f} seconds")
        assert delay_unknown == 1.0, "Unknown API should return 1.0 second delay"
        
        print("\n🎉 All get_recommended_delay tests passed!")
        
        # Assertions for all delays
        assert isinstance(delay, (int, float)), "Delay should be numeric"
        assert isinstance(delay_high, (int, float)), "High priority delay should be numeric"
        assert isinstance(delay_low, (int, float)), "Low priority delay should be numeric"
        assert isinstance(delay_unknown, (int, float)), "Unknown API delay should be numeric"
        
    finally:
        # Cleanup
        try:
            os.unlink(temp_state_file)
        except FileNotFoundError:
            pass

if __name__ == "__main__":
    try:
        test_get_recommended_delay()
        print("\n🎉 Test completed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)