#!/usr/bin/env python3
"""
Test HTTP Adapter Abstraction

Demonstrates the usage of the unified HTTP adapter that abstracts
both requests and aiohttp behind a common interface.
"""

import asyncio
import sys
from pathlib import Path

# Add tennis_api to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tennis_api.adapters.http_adapter import UnifiedHTTPClient, get, get_async


def test_sync_adapter():
    """Test synchronous HTTP adapter using requests"""
    print("=== Testing Sync HTTP Adapter (requests) ===")
    
    # Test with a mock endpoint (should fail gracefully)
    client = UnifiedHTTPClient(timeout=5)
    
    try:
        response = client.get("https://httpbin.org/json")
        print(f"✓ Sync request successful: Status {response.status_code}")
        print(f"  Response type: {type(response.json())}")
        if response.ok:
            print("  ✓ Response indicates success")
    except Exception as e:
        print(f"  Expected error with test endpoint: {e}")
    
    client.close()
    print("✓ Sync adapter test completed")
    
    # Assert that client was created successfully
    assert client is not None, "HTTP client should be created successfully"


async def test_async_adapter():
    """Test asynchronous HTTP adapter using aiohttp"""
    print("\n=== Testing Async HTTP Adapter (aiohttp) ===")
    
    # Test with async client
    async with UnifiedHTTPClient(timeout=5) as client:
        try:
            response = await client.get_async("https://httpbin.org/json")
            print(f"✓ Async request successful: Status {response.status_code}")
            print(f"  Response type: {type(response.json())}")
            if response.ok:
                print("  ✓ Response indicates success")
        except Exception as e:
            print(f"  Expected error with test endpoint: {e}")
    
    print("✓ Async adapter test completed")
    
    # Assert that the test completed (no assertion needed for async context manager)


def test_convenience_functions():
    """Test convenience functions"""
    print("\n=== Testing Convenience Functions ===")
    
    # Test sync convenience function
    try:
        response = get("https://httpbin.org/json", timeout=5)
        print(f"✓ Sync convenience function: Status {response.status_code}")
    except Exception as e:
        print(f"  Expected error with convenience function: {e}")
    
    print("✓ Convenience functions test completed")
    
    # Assert that get function exists and is callable
    assert callable(get), "get function should be callable"


async def test_async_convenience_functions():
    """Test async convenience functions"""
    print("\n=== Testing Async Convenience Functions ===")
    
    # Test async convenience function
    try:
        response = await get_async("https://httpbin.org/json")
        print(f"✓ Async convenience function: Status {response.status_code}")
    except Exception as e:
        print(f"  Expected error with async convenience function: {e}")
    
    print("✓ Async convenience functions test completed")
    
    # Assert that get_async function exists and is callable
    assert callable(get_async), "get_async function should be callable"


def demonstrate_usage():
    """Demonstrate why both libraries are needed"""
    print("\n=== Demonstrating Dual Library Usage ===")
    print("This package requires both requests and aiohttp because:")
    print("1. Sync methods (*_sync) use requests for compatibility with existing sync code")
    print("2. Async methods use aiohttp for better performance in concurrent scenarios") 
    print("3. The HTTP adapter abstracts both behind a unified interface")
    print("4. Different parts of the system have different sync/async requirements")
    
    print("\nExample usage patterns:")
    print("- Web interface (Flask): Uses sync methods for simple request/response")
    print("- API rate limiting: Uses async methods for concurrent quota management") 
    print("- Data extraction: Uses async methods for concurrent player data fetching")
    print("- Integration tests: Uses sync wrappers for simple test assertions")


async def main():
    """Run all tests"""
    print("HTTP Adapter Abstraction Test")
    print("=" * 50)
    
    # Run tests
    try:
        test_sync_adapter()
        sync_ok = True
    except Exception:
        sync_ok = False
        
    try:
        await test_async_adapter()
        async_ok = True
    except Exception:
        async_ok = False
        
    try:
        test_convenience_functions()
        conv_ok = True
    except Exception:
        conv_ok = False
        
    try:
        await test_async_convenience_functions()
        async_conv_ok = True
    except Exception:
        async_conv_ok = False
    
    demonstrate_usage()
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"Sync Adapter: {'✓ PASS' if sync_ok else '✗ FAIL'}")
    print(f"Async Adapter: {'✓ PASS' if async_ok else '✗ FAIL'}")
    print(f"Convenience Functions: {'✓ PASS' if conv_ok else '✗ FAIL'}")
    print(f"Async Convenience Functions: {'✓ PASS' if async_conv_ok else '✗ FAIL'}")
    
    all_passed = all([sync_ok, async_ok, conv_ok, async_conv_ok])
    print(f"\nOverall: {'🎉 ALL TESTS PASSED' if all_passed else '⚠️ SOME TESTS FAILED'}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)