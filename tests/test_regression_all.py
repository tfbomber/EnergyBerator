import pytest
import os
import sys

# Add the d-ess-engine directory to sys.path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.append(base_dir)

def test_run_all_regressions():
    """
    Main Entry Point for CI/CD.
    Executes Module 2 (Logic) and Module 3 (E2E Integration) suites.
    """
    test_files = [
        # Module 2 (Logic & Plan)
        os.path.join(base_dir, "tests", "test_regression.py"),
        
        # Module 3 (E2E Baseline)
        os.path.join(base_dir, "tests", "test_e2e_smoke.py"),
        
        # Module 3 (Robustness & Edge Cases)
        os.path.join(base_dir, "tests", "test_e2e_hardening.py"),
        
        # Contract Shape Gate
        os.path.join(base_dir, "tests", "test_contract_report_shape.py")
    ]
    
    # Check if all files exist
    for f in test_files:
        assert os.path.exists(f), f"Test file missing: {f}"
        
    print(f"\n[CI] Starting Global Regression Meta Suite ({len(test_files)} files)...")
    
    # We use pytest.main to run them in the same process or separate, 
    # but for a simple orchestrator, we'll just run them.
    # We use -x (fail-fast) as requested.
    exit_code = pytest.main(["-x", "-v"] + test_files)
    
    assert exit_code == 0, f"Global regression failed with exit code {exit_code}"

if __name__ == "__main__":
    test_run_all_regressions()
