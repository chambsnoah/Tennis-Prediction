# Test & Verification Scripts

This directory contains various test runners and verification scripts for the Tennis API project.

## 🧪 **Test Runners**

### [`run_full_tests.py`](run_full_tests.py)
**Comprehensive Test Suite Runner**
- Runs the complete API integration test framework
- Provides detailed failure analysis and error reporting
- Includes individual test analysis for debugging
- Generates comprehensive test reports
- **Usage:** `python scripts/run_full_tests.py`

### [`run_official_tests.py`](run_official_tests.py) 
**Official Test Framework Runner**
- Runs the official API test framework with standard reporting
- Simpler output compared to run_full_tests.py
- Focuses on pass/fail rates and core metrics
- **Usage:** `python scripts/run_official_tests.py`

## ✅ **Verification Scripts**

### [`simple_verify.py`](simple_verify.py)
**Quick Bug Fix Verification**  
- Rapid 3-line test to verify the three critical bug fixes:
  1. TournamentDraw category parameter fix
  2. PlayerStats serialization fix  
  3. Rate limiter priority handling fix
- **Usage:** `python scripts/simple_verify.py`

### [`verify_fixes.py`](verify_fixes.py)
**Comprehensive Bug Fix Verification**
- Detailed verification of all three critical implementation bugs
- Tests exact scenarios from the original test framework failures
- Provides step-by-step verification output
- **Usage:** `python scripts/verify_fixes.py`

### [`final_verification.py`](final_verification.py)
**Final State Documentation & Verification**
- Documents all fixes applied to achieve 100% test success rate
- Provides before/after analysis
- Runs final component verification
- **Usage:** `python scripts/final_verification.py`

## 🔬 **Specialized Test Scripts**

### [`validate_cache_edge_cases.py`](validate_cache_edge_cases.py)
**Cache System Edge Case Testing**
- Comprehensive cache manager edge case validation
- Tests TTL expiry boundaries, type parsing, memory cache collisions
- Tests LRU behavior, cache integrity validation
- Tests warmup behavior and atomic operations
- **Usage:** `python scripts/validate_cache_edge_cases.py`

## 🎯 **Usage Examples**

```bash
# Quick verification of core fixes
python scripts/simple_verify.py

# Comprehensive test suite
python scripts/run_full_tests.py

# Cache system validation  
python scripts/validate_cache_edge_cases.py

# Final project state verification
python scripts/final_verification.py
```

## 🔗 **Related Files**

- **Main Test Suite:** `tennis_api/tests/` - Contains all unit tests  
- **Test Reports:** `reports/` - Contains generated test reports
- **Pytest Config:** `pytest.ini` - Main pytest configuration

## 📝 **Notes**

- All scripts can be run independently
- Scripts assume the tennis_api package is properly installed/accessible
- Some scripts generate reports in the `reports/` directory
- Use `-v` flag with pytest for verbose output