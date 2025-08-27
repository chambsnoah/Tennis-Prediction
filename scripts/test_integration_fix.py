#!/usr/bin/env python3
"""
Verification script for the fixed integration tests.
This script tests that the integration tests work properly with pytest.
"""

import subprocess
import sys
import os

def run_test(test_name, description):
    """Run a specific test and report results"""
    print(f"\n=== {description} ===")
    
    try:
        # Run the specific test
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            f"tennis_api/tests/test_api_integration.py::{test_name}",
            "-v", "--tb=short"
        ], capture_output=True, text=True, timeout=30)
        
        print(f"Exit code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
            
        # Check for specific issues
        if "OSError: pytest: reading from stdin" in result.stdout:
            print("❌ FAIL: Still has input() issue")
            return False
        elif "PytestReturnNotNoneWarning" in result.stdout:
            print("❌ FAIL: Still has return value warning")
            return False
        elif result.returncode == 0:
            print("✅ PASS: Test completed successfully")
            return True
        elif "SKIPPED" in result.stdout:
            print("⏭️ SKIP: Test was skipped (expected for live API test)")
            return True
        else:
            print("❌ FAIL: Test failed for other reasons")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ TIMEOUT: Test took too long (>30s)")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    """Main verification function"""
    print("Integration Test Fix Verification")
    print("=" * 50)
    
    # Change to project directory
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_dir)
    print(f"Working directory: {os.getcwd()}")
    
    # Test 1: Basic functionality test
    test1_pass = run_test("test_basic_functionality", 
                         "Testing basic functionality (should pass)")
    
    # Test 2: Minimal API calls test (should be skipped by default)
    test2_pass = run_test("test_with_minimal_api_calls", 
                         "Testing minimal API calls (should be skipped)")
    
    # Test 3: Run both tests together
    print(f"\n=== Running both tests together ===")
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tennis_api/tests/test_api_integration.py",
            "-v", "--tb=short"
        ], capture_output=True, text=True, timeout=60)
        
        print(f"Exit code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        
        if "OSError: pytest: reading from stdin" in result.stdout:
            print("❌ FAIL: Still has input() issue")
            test3_pass = False
        elif "PytestReturnNotNoneWarning" in result.stdout:
            print("❌ FAIL: Still has return value warning") 
            test3_pass = False
        elif result.returncode == 0:
            print("✅ PASS: Both tests completed successfully")
            test3_pass = True
        else:
            print("❌ FAIL: Tests failed for other reasons")
            test3_pass = False
            
    except subprocess.TimeoutExpired:
        print("❌ TIMEOUT: Tests took too long (>60s)")
        test3_pass = False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        test3_pass = False
    
    # Summary
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY")
    print("=" * 50)
    print(f"Basic functionality test: {'✅ PASS' if test1_pass else '❌ FAIL'}")
    print(f"Minimal API calls test: {'✅ PASS' if test2_pass else '❌ FAIL'}")
    print(f"Combined test run: {'✅ PASS' if test3_pass else '❌ FAIL'}")
    
    overall_success = test1_pass and test2_pass and test3_pass
    
    if overall_success:
        print("\n🎉 SUCCESS: All integration test fixes are working!")
        print("\nThe issues have been resolved:")
        print("- ❌ Removed interactive input() calls that don't work in pytest")
        print("- ❌ Replaced return statements with proper assertions")
        print("- ✅ Live API tests are now controlled by USE_LIVE_APIS environment variable")
        print("- ✅ Tests properly skip when live APIs are disabled")
        print("\nTo run live API tests: USE_LIVE_APIS=true pytest tennis_api/tests/test_api_integration.py")
    else:
        print("\n❌ FAILURE: Some issues remain to be fixed")
        
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)