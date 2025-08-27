#!/usr/bin/env python3
"""
API Test Framework Runner
Runs the official test framework and reports results
"""

def run_test_framework():
    try:
        from tennis_api.tests.test_framework import run_api_tests
        
        print("=== RUNNING OFFICIAL API TEST FRAMEWORK ===")
        print("Running comprehensive test suite...")
        
        # Run the official test framework
        report = run_api_tests(use_live_apis=False, max_live_requests=0)
        
        print("\n=== OFFICIAL TEST RESULTS ===")
        print(f"Total Tests: {report['summary']['total_tests']}")
        print(f"Passed: {report['summary']['passed']}")
        print(f"Failed: {report['summary']['failed']}")
        print(f"Success Rate: {report['summary']['success_rate']}%")
        print(f"Required: >= 80%")
        
        # Show errors if any
        errors = report.get('errors', [])
        if errors:
            print(f"\nRemaining Errors ({len(errors)}):")
            for i, error in enumerate(errors, 1):
                print(f"  {i}. {error}")
        else:
            print("\n✅ No errors found!")
        
        # Final assessment
        success_rate = report['summary']['success_rate']
        if success_rate >= 80:
            print(f"\n🎉 SUCCESS: {success_rate}% >= 80% threshold")
            print("✅ Test suite ready for production!")
            return True
        else:
            print(f"\n❌ STILL FAILING: {success_rate}% < 80% threshold")
            print(f"Need to fix {report['summary']['failed']} more tests")
            return False
            
    except Exception as e:
        print(f"ERROR: Test framework execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    run_test_framework()