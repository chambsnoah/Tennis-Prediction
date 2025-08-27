#!/usr/bin/env python3
"""
Comprehensive Bug Fix Test
Tests all three critical implementation bugs after fixes
"""

import traceback

def test_tournament_draw_fix():
    """Test TournamentDraw category parameter fix"""
    print("Testing TournamentDraw fix...")
    from tennis_api.models.tournament_data import TournamentDraw
    
    # Test with minimal data (missing category)
    test_data = {
        'tournament_id': 'test_id',
        'tournament_name': 'Test Tournament',
        'year': 2024,
        'surface': 'hard'
        # Note: missing 'category' field
    }
    
    tournament = TournamentDraw.from_dict(test_data)
    assert tournament.category == 'Unknown'  # Default value
    assert tournament.tournament_name == 'Test Tournament'
    print("  ✅ TournamentDraw.from_dict works with missing category")
    
    # Test with extra unknown fields
    test_data_extra = test_data.copy()
    test_data_extra['unknown_field'] = 'should_be_filtered'
    test_data_extra['first_serve_pct'] = 0.65
    
    tournament2 = TournamentDraw.from_dict(test_data_extra)
    assert tournament2.category == 'Unknown'
    print("  ✅ Extra fields are filtered out correctly")

def test_player_stats_fix():
    """Test PlayerStats serialization fix"""
    print("\nTesting PlayerStats serialization fix...")
    from tennis_api.models.player_stats import PlayerStats
    
    # Test basic serialization
    player = PlayerStats(name="Test Player", current_ranking=10)
    player_dict = player.to_dict()
    restored = PlayerStats.from_dict(player_dict)
    assert restored.name == "Test Player"
    print("  ✅ Basic serialization works")
    
    # Test with problematic first_serve_pct field
    test_data = player_dict.copy()
    test_data['first_serve_pct'] = 0.65  # This caused the original error
    test_data['unknown_field'] = 'test'
    
    restored_extra = PlayerStats.from_dict(test_data)
    assert restored_extra.name == "Test Player"
    print("  ✅ Extra fields (including first_serve_pct) are filtered")

def test_rate_limiter_fix():
    """Test Rate Limiter priority handling fix"""
    print("\nTesting Rate Limiter priority fix...")
    from tennis_api.cache.rate_limiter import RateLimiter
    
    # Create rate limiter
    rate_limiter = RateLimiter()
    
    # Test with valid API name (this should work)
    high_result = rate_limiter.check_availability('rapidapi_tennis_live', 'high')
    normal_result = rate_limiter.check_availability('rapidapi_tennis_live', 'normal')
    
    # Check that both have priority_factor
    assert 'priority_factor' in high_result
    assert 'priority_factor' in normal_result
    print("  ✅ Priority factors are included in results")
    
    # Check that high priority > normal priority
    high_factor = high_result['priority_factor']
    normal_factor = normal_result['priority_factor']
    
    assert high_factor > normal_factor, f"High: {high_factor}, Normal: {normal_factor}"
    assert high_factor == 0.8, f"Expected 0.8, got {high_factor}"
    assert normal_factor == 0.6, f"Expected 0.6, got {normal_factor}"
    print(f"  ✅ Priority handling correct: High={high_factor}, Normal={normal_factor}")

def test_import_health():
    """Test that all imports work correctly"""
    print("\nTesting import health...")
    # Test critical imports
    from tennis_api.cache.rate_limiter import RateLimiter
    from tennis_api.models.player_stats import PlayerStats
    from tennis_api.models.tournament_data import TournamentDraw
    from tennis_api.tests.test_framework import APITestFramework
    print("  ✅ All critical imports successful")
    
    # Assert that imports were successful
    assert RateLimiter is not None
    assert PlayerStats is not None
    assert TournamentDraw is not None
    assert APITestFramework is not None

def main():
    print("=== COMPREHENSIVE BUG FIX VERIFICATION ===")
    print("Testing all three critical implementation bugs...")
    print("=" * 60)
    
    tests = [
        ("Import Health", test_import_health),
        ("TournamentDraw Fix", test_tournament_draw_fix),
        ("PlayerStats Fix", test_player_stats_fix),
        ("Rate Limiter Fix", test_rate_limiter_fix),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_name} failed: {e}")
            traceback.print_exc()
    
    print(f"\n=== FINAL RESULTS ===")
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 ALL BUGS FIXED - Ready for test suite!")
    else:
        print("🔧 Some fixes still needed")

if __name__ == "__main__":
    main()