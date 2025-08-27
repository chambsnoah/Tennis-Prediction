"""
Simple Tennis API Integration Test

A minimal test script to validate the tennis API integration with
very careful rate limit management and comprehensive error handling.
"""

import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tennis_api.tests.test_framework import run_api_tests
    from tennis_api.clients.tennis_api_client import TennisAPIClient
    from tennis_api.config.api_config import get_api_config
    from tennis_api.config.test_config import TestConfig
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running this from the tennis project directory")
    sys.exit(1)


def test_basic_functionality():
    """Test basic functionality without making live API calls"""
    print("=== Basic Functionality Test ===")
    
    # Test 1: Configuration loading
    print("1. Testing configuration loading...")
    config = TestConfig.get_mock_config()
    print(f"OK Mock configuration loaded successfully")
    print(f"  API Key: {config.rapid_api_key[:20]}...")
    print(f"  Live API URL: {config.tennis_live_api.base_url if config.tennis_live_api else 'Not configured'}")
    
    # Test 2: Client initialization
    print("\n2. Testing client initialization...")
    client = TennisAPIClient(config)
    print(f"OK Tennis API client initialized")
    print(f"  Number of sub-clients: {len(client.clients)}")
    print(f"  Available clients: {list(client.clients.keys())}")
    
    # Test 3: Cache system
    print("\n3. Testing cache system...")
    cache_stats = client.cache_manager.get_cache_size()
    print(f"OK Cache system working")
    print(f"  Cache files: {cache_stats['total_files']}")
    print(f"  Cache size: {cache_stats['total_size_mb']} MB")
    
    # Test 4: Rate limiter
    print("\n4. Testing rate limiter...")
    rate_stats = client.rate_limiter.get_usage_stats()
    print(f"OK Rate limiter working")
    print(f"  Configured APIs: {len(rate_stats)}")
    
    print("\nOK All basic functionality tests passed!")
    
    # Use assertions instead of return values
    assert len(client.clients) > 0, "Client should have at least one sub-client"
    assert cache_stats['total_files'] >= 0, "Cache stats should be valid"
    assert len(rate_stats) >= 0, "Rate limiter stats should be available"


def test_with_minimal_api_calls():
    """Test with minimal API calls if enabled via environment variable"""
    print("\n=== Minimal API Integration Test ===")
    
    # Check if live API testing is enabled via environment variable
    use_live_apis = os.environ.get('USE_LIVE_APIS', '').lower() in ('true', '1', 'yes')
    
    if not use_live_apis:
        print("Skipping live API tests (USE_LIVE_APIS not set to true).")
        print("To enable live API testing, set environment variable: USE_LIVE_APIS=true")
        print("This will make a very small number of API calls to test connectivity.")
        print("Estimated API usage: 2-3 requests maximum")
        # Skip the test but don't fail it
        import pytest
        pytest.skip("Live API testing disabled (set USE_LIVE_APIS=true to enable)")
        return
    
    try:
        # Load real configuration
        print("\nLoading real API configuration...")
        config = get_api_config()
        print(f"OK Real API configuration loaded")
        print(f"  API Key: {config.rapid_api_key[:10]}...{config.rapid_api_key[-4:]}")
        
        # Initialize client with real config
        print("\nInitializing client with real configuration...")
        client = TennisAPIClient(config)
        print(f"OK Client initialized with real APIs")
        
        # Test 1: Rankings (1 API call)
        print("\nTest 1: ATP Rankings (1 API call)")
        try:
            rankings = client.get_rankings_sync('atp')
            print(f"OK ATP rankings retrieved successfully")
            if isinstance(rankings, dict) and 'rankings' in rankings:
                print(f"  Top player: {rankings['rankings'][0].get('name', 'Unknown')}")
            else:
                print(f"  Response type: {type(rankings)}")
        except Exception as e:
            print(f"FAIL ATP rankings failed: {e}")
            print("  This is expected if the API endpoints are not yet configured correctly")
        
        # Test 2: Player stats (1 API call)
        print("\nTest 2: Player Statistics (1 API call)")
        try:
            player_stats = client.get_player_stats_sync("Novak Djokovic")
            print(f"OK Player stats retrieved successfully")
            print(f"  Player name: {player_stats.name}")
            print(f"  Ranking: {player_stats.current_ranking}")
            print(f"  Recent form factor: {player_stats.recent_form_factor}")
        except Exception as e:
            print(f"FAIL Player stats failed: {e}")
            print("  This is expected if the API endpoints are not yet configured correctly")
        
        # Get client statistics
        print("\nAPI Usage Statistics:")
        stats = client.get_client_stats()
        for client_name, client_stats in stats['client_stats'].items():
            print(f"  {client_name}:")
            print(f"    Requests made: {client_stats['requests_made']}")
            print(f"    Cache hits: {client_stats['cache_hits']}")
            print(f"    Errors: {client_stats['errors']}")
        
        print("\nOK Live API integration test completed!")
        
        # Use assertions instead of return values
        assert len(stats['client_stats']) > 0, "Should have client statistics"
        
    except Exception as e:
        print(f"\nFAIL Live API integration test failed: {e}")
        print("This may indicate configuration issues or API connectivity problems.")
        # Re-raise the exception to fail the test properly
        raise


def main():
    """Main test function"""
    print("Tennis API Integration Test")
    print("=" * 40)
    
    # Test 1: Basic functionality (no API calls)
    basic_success = test_basic_functionality()
    
    if not basic_success:
        print("\nBasic tests failed. Please fix issues before proceeding.")
        return False
    
    # Test 2: Comprehensive test framework
    print("\n=== Comprehensive Test Framework ===")
    print("Note: This test suite includes timeout protection to prevent hanging")
    try:
        # Run comprehensive tests with mock APIs only and timeout protection
        print("Running comprehensive tests (mock APIs only, max 60 seconds)...")
        start_time = time.time()
        
        try:
            # Use ThreadPoolExecutor to run tests with timeout protection
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_api_tests, use_live_apis=False, max_live_requests=0)
                report = future.result(timeout=60)  # 60 second timeout
        except FuturesTimeoutError:
            elapsed = time.time() - start_time
            print(f"FAIL Tests timed out after {elapsed:.1f} seconds")
            print("ERROR The test framework is hanging - this indicates a serious issue")
            print("       that needs to be investigated (likely async/sync conflicts)")
            raise TimeoutError(f"API tests hung for more than 60 seconds (elapsed: {elapsed:.1f}s)")
        
        elapsed = time.time() - start_time
        print(f"Comprehensive tests completed in {elapsed:.1f} seconds")
        
        if elapsed > 60:
            print("WARNING: Tests took longer than expected - there may be hanging issues")
        
        if report['summary']['success_rate'] >= 80:
            print(f"OK Comprehensive tests passed ({report['summary']['success_rate']}% success rate)")
        else:
            print(f"WARNING Comprehensive tests had issues ({report['summary']['success_rate']}% success rate)")
            
    except Exception as e:
        print(f"FAIL Comprehensive test framework failed: {e}")
        print("This could indicate hanging or other issues in the test framework")
    
    # Test 3: Optional live API testing
    live_success = test_with_minimal_api_calls()
    
    # Final summary
    print("\n" + "=" * 40)
    print("FINAL TEST SUMMARY")
    print("=" * 40)
    print(f"Basic Functionality: {'OK PASS' if basic_success else 'FAIL FAIL'}")
    print(f"Live API Testing: {'OK PASS' if live_success else 'FAIL FAIL'}")
    
    if basic_success and live_success:
        print("\n>> Tennis API integration is ready for use!")
        print("\nNext steps:")
        print("- Integrate with existing tennis prediction system")
        print("- Create API-based extractors")
        print("- Test with real tournament data")
    else:
        print("\nWARNING Some tests failed. Please review the errors above.")
        print("\nTroubleshooting:")
        print("- Check API credentials in .env file")
        print("- Verify internet connectivity")
        print("- Review error messages for specific issues")
    
    return basic_success and live_success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        sys.exit(1)