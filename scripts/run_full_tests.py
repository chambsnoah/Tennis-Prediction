#!/usr/bin/env python3
"""
Full Test Suite Runner
Runs comprehensive API integration tests and generates detailed failure analysis
"""

from tennis_api.tests.test_framework import run_api_tests, APITestFramework
import json
import traceback
from datetime import datetime

def run_comprehensive_tests():
    print("=== RUNNING FULL TEST SUITE ===")
    print("Running comprehensive API integration tests...")
    print("=" * 60)
    
    try:
        # Run the full test suite
        report = run_api_tests(use_live_apis=False, max_live_requests=0)
        
        print("\n=== TEST RESULTS ANALYSIS ===")
        print(f"Total Tests: {report['summary']['total_tests']}")
        print(f"Passed: {report['summary']['passed']}")
        print(f"Failed: {report['summary']['failed']}")
        print(f"Success Rate: {report['summary']['success_rate']}%")
        print(f"Target: >= 80%")
        
        # Analyze errors
        errors = report.get('errors', [])
        print(f"\nDetailed Error Analysis ({len(errors)} errors):")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        
        # Check if we meet the 80% threshold
        success_rate = report['summary']['success_rate']
        if success_rate >= 80:
            print(f"\n✅ SUCCESS: Test suite meets 80% threshold ({success_rate}%)")
        else:
            print(f"\n❌ FAILING: Test suite below 80% threshold ({success_rate}%)")
            print(f"   Need to fix {report['summary']['failed']} failing tests")
        
        return report
        
    except Exception as e:
        print(f"ERROR: Test execution failed: {e}")
        traceback.print_exc()
        return None

def run_individual_test_analysis():
    """Run specific tests to identify exact failure points"""
    print("\n=== INDIVIDUAL TEST ANALYSIS ===")
    
    try:
        framework = APITestFramework(use_live_apis=False, max_live_requests=0)
        
        # Test the specific areas that were previously failing
        test_methods = [
            ("TournamentDraw Model", framework._test_tournament_draw_model),
            ("Serialization", framework._test_model_serialization),
            ("Priority Handling", framework._test_rate_limiter_priority),
            ("Rate Limiter Basic", framework._test_rate_limiter_basic),
            ("Cache Manager", framework._test_cache_manager),
            ("PlayerStats Model", framework._test_player_stats_model),
        ]
        
        passed = 0
        failed = 0
        failures = []
        
        for test_name, test_method in test_methods:
            try:
                print(f"Running {test_name}...", end=" ")
                test_method()
                print("✅ PASS")
                passed += 1
            except Exception as e:
                print(f"❌ FAIL: {e}")
                failed += 1
                failures.append(f"{test_name}: {str(e)}")
        
        print(f"\nIndividual Test Results:")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        print(f"  Success Rate: {(passed / (passed + failed)) * 100:.2f}%")
        
        if failures:
            print(f"\nFailure Details:")
            for failure in failures:
                print(f"  - {failure}")
        
        return failures
        
    except Exception as e:
        print(f"ERROR: Individual test analysis failed: {e}")
        traceback.print_exc()
        return []

if __name__ == "__main__":
    # Run comprehensive test suite
    report = run_comprehensive_tests()
    
    # Run individual test analysis for more details
    individual_failures = run_individual_test_analysis()
    
    print(f"\n=== FINAL ANALYSIS ===")
    if report and report['summary']['success_rate'] >= 80:
        print("🎉 Test suite ready for production!")
    else:
        print("🔧 Test suite needs fixes before merging")
        if individual_failures:
            print("Priority fixes needed:")
            for failure in individual_failures[:3]:  # Top 3 priorities
                print(f"  1. {failure}")