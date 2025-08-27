#!/usr/bin/env python3
"""
Quick test to verify no hanging issues after fixes
"""

import time
import sys

def test_basic_functionality():
    """Test basic functionality without hanging"""
    print("=== Testing Basic Functionality (No Hang Version) ===")
    
    start_time = time.time()
    
    print("1. Testing imports...")
    from tennis_api.clients.tennis_api_client import TennisAPIClient
    from tennis_api.config.test_config import TestConfig
    print("   ✓ Imports completed successfully")
    
    print("2. Testing configuration loading...")
    config = TestConfig.get_mock_config()
    print("   ✓ Mock configuration loaded")        
    print("3. Testing client initialization...")
    client = TennisAPIClient(config)
    print(f"   ✓ Client initialized with {len(client.clients)} sub-clients")
    
    print("4. Testing basic client operations...")
    stats = client.get_client_stats()
    print(f"   ✓ Client stats retrieved: {len(stats)} items")
    
    elapsed = time.time() - start_time
    print(f"\n✓ All tests completed successfully in {elapsed:.2f} seconds")
    
    if elapsed > 10:
        print("⚠️  WARNING: Tests took longer than expected")
    else:
        print("✅ Tests completed within reasonable time")
        
    # Assert that basic functionality works
    assert client is not None, "Client should be initialized"
    assert len(client.clients) > 0, "Client should have sub-clients"
    assert isinstance(stats, dict), "Stats should be a dictionary"
    assert elapsed < 30, f"Test should complete within 30 seconds, took {elapsed:.2f}s"

def test_timeout_protection():
    """Test that timeout protection works with actual API call"""
    print("\n=== Testing Timeout Protection ===")
    
    import asyncio
    from tennis_api.clients.tennis_api_client import TennisAPIClient
    from tennis_api.config.test_config import TestConfig
    
    config = TestConfig.get_mock_config()
    client = TennisAPIClient(config)
    
    print("1. Testing sync wrapper with actual get_player_stats_sync call...")
    start_time = time.time()
    
    timeout_worked = False
    error_message = ""
    
    try:
        # This should fail quickly because the mock endpoint doesn't exist
        # but should NOT hang due to rate limiter issues
        stats = client.get_player_stats_sync("Test Player")
        print("   ⚠️  Request completed unexpectedly")
    except Exception as e:
        elapsed = time.time() - start_time
        error_message = str(e)
        # Should fail quickly (within 10 seconds) without hanging
        if elapsed < 10:
            timeout_worked = True
            print(f"   ✓ Call failed quickly without hanging: {e} (took {elapsed:.1f}s)")
        else:
            print(f"   ❌ Still hanging or slow: {e} (took {elapsed:.1f}s)")
    
    # Assert that timeout protection is working (no hanging)
    assert timeout_worked, f"Should not hang. Error: {error_message}. Time elapsed: {time.time() - start_time:.1f}s"

if __name__ == "__main__":
    print("Tennis API No-Hang Test Suite")
    print("=" * 50)
    
    try:
        test_basic_functionality()
        basic_test = True
    except Exception as e:
        print(f"Basic functionality test failed: {e}")
        basic_test = False
        
    try:
        test_timeout_protection()
        timeout_test = True
    except Exception as e:
        print(f"Timeout protection test failed: {e}")
        timeout_test = False
    
    print("\n" + "=" * 50)
    print("FINAL RESULTS:")
    print(f"Basic Functionality: {'✅ PASS' if basic_test else '❌ FAIL'}")
    print(f"Timeout Protection: {'✅ PASS' if timeout_test else '❌ FAIL'}")
    
    if basic_test and timeout_test:
        print("\n🎉 All hanging issues have been resolved!")
        sys.exit(0)
    else:
        print("\n⚠️  Some issues remain - please investigate further")
        sys.exit(1)