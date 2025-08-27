#!/usr/bin/env python3
"""
Simple Rate Limiter Import Test
Tests if the rate_limiter can be imported after fixing file corruption
"""

def test_rate_limiter_import():
    """Test basic import and instantiation"""
    from tennis_api.cache.rate_limiter import RateLimiter
    print("✅ Successfully imported RateLimiter")
    
    # Test basic instantiation
    rate_limiter = RateLimiter()
    print("✅ Successfully created RateLimiter instance")
    
    # Test basic functionality
    result = rate_limiter.check_availability('rapidapi_tennis_live', 'high')
    print(f"✅ check_availability works: {result}")
    
    # Assert successful operations
    assert rate_limiter is not None, "RateLimiter should be instantiated"
    assert isinstance(result, dict), "check_availability should return a dict"

def test_simple_operations():
    """Test simple operations"""
    from tennis_api.cache.rate_limiter import RateLimiter
    
    rate_limiter = RateLimiter()
    
    # Test priority factor method
    high_factor = rate_limiter._get_priority_factor('high')
    normal_factor = rate_limiter._get_priority_factor('normal')
    
    print(f"High priority factor: {high_factor}")
    print(f"Normal priority factor: {normal_factor}")
    
    assert high_factor > normal_factor, "High priority should have higher factor than normal"
    print("✅ Priority handling works correctly")
    
    # Additional assertions
    assert isinstance(high_factor, (int, float)), "Priority factor should be numeric"
    assert isinstance(normal_factor, (int, float)), "Priority factor should be numeric"

if __name__ == "__main__":
    print("=== RATE LIMITER IMPORT TEST ===")
    
    try:
        test_rate_limiter_import()
        import_success = True
    except Exception as e:
        print(f"Import test failed: {e}")
        import_success = False
    
    try:
        test_simple_operations()
        operations_success = True
    except Exception as e:
        print(f"Operations test failed: {e}")
        operations_success = False
    
    if import_success and operations_success:
        print("\n🎉 Rate Limiter is working correctly!")
    else:
        print("\n❌ Rate Limiter still has issues")