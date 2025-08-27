#!/usr/bin/env python3
"""
Simple test script to verify rate limiter functionality
"""

import sys
from pathlib import Path

# Add tennis_api to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    print("Testing imports...")
    from tennis_api.cache.rate_limiter import RateLimiter
    print("✓ RateLimiter imported successfully")
    
    from tennis_api.config.api_config import get_api_config
    print("✓ get_api_config imported successfully")
    
    from tennis_api.clients.base_client import APIException
    print("✓ APIException imported successfully")
    
    print("\nTesting rate limiter creation...")
    limiter = RateLimiter()
    print("✓ RateLimiter created successfully")
    
    print("\nTesting basic functionality...")
    availability = limiter.check_availability('rapidapi_tennis_live', 'normal')
    print(f"✓ check_availability returned: {availability['available']}")
    
    result = limiter.acquire('rapidapi_tennis_live', 'normal')
    print(f"✓ acquire returned: {result}")
    
    stats = limiter.get_usage_stats('rapidapi_tennis_live')
    print(f"✓ get_usage_stats returned {len(stats)} fields")
    
    print("\nTesting configuration...")
    try:
        config = get_api_config()
        print("✓ Configuration loaded successfully")
    except Exception as e:
        print(f"⚠️  Configuration failed (expected if no .env): {e}")
    
    print("\n🎉 All basic tests passed successfully!")
    
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)