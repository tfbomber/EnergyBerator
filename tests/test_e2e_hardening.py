import pytest
import json
import os
import sys
from unittest.mock import patch
from decimal import Decimal

# Add d-ess-engine to path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path:
    sys.path.append(core_dir)

from core.dess_main import run_engine

PACK_PATH = os.path.join(base_dir, "tests", "packs", "e2e_hardening_pack.json")
FIXTURES_DIR = os.path.join(base_dir, "tests", "fixtures", "e2e")

def load_pack():
    with open(PACK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_case_data(case):
    policy_path = os.path.join(FIXTURES_DIR, "policies", case["policy_ref"])
    input_path = os.path.join(FIXTURES_DIR, "cases", case["input_ref"])
    return policy_path, input_path

pack_data = load_pack()

@pytest.mark.parametrize("case", pack_data["cases"], ids=lambda c: c["case_id"])
def test_e2e_hardening_case(case):
    policy_path, input_path = get_case_data(case)
    expected = case["expected"]
    
    # Mock evidence_index location to use our fixture
    mock_evidence_index_path = os.path.join(FIXTURES_DIR, "evidence", "evidence_index.json")
    
    with patch("core.dess_main.load_evidence_index") as mock_load:
        # Load our mock index
        with open(mock_evidence_index_path, "r", encoding="utf-8") as f:
            mock_load.return_value = json.load(f)
            
        # Run engine
        output_dir = os.path.join(base_dir, "tmp", "test_runs_hardening")
        report = run_engine(policy_path, input_path, output_dir=output_dir)
        
        # ASSERTIONS
        
        # a) final_verdict
        actual_verdict = report.get("status")
        assert actual_verdict == expected["verdict"], f"Verdict mismatch for {case['case_id']}"
        
        # b) policy_hash must be present
        audit_trail = report.get("audit_trail", [])
        found_policy_hash = any("policy_hash" in entry for entry in audit_trail)
        assert found_policy_hash, f"policy_hash missing for {case['case_id']}"
        
        # c) must_audit_keys
        must_keys = expected.get("must_audit_keys", [])
        actual_keys = set()
        for entry in audit_trail:
            actual_keys.update(entry.keys())
        for finding in report.get("violations", []):
            actual_keys.update(finding.keys())
            if "trace" in finding:
                actual_keys.update(finding["trace"].keys())

        missing_keys = [k for k in must_keys if k not in actual_keys]
        assert not missing_keys, f"Missing trace fields {missing_keys} for {case['case_id']}"
        
        # d) Specific field content checks
        if "reason_contains" in expected:
            found_reason = False
            for finding in report.get("violations", []):
                if expected["reason_contains"] in finding.get("reason_code_raw", ""):
                    found_reason = True
                    break
            assert found_reason, f"Expected reason code {expected['reason_contains']} not found in report for {case['case_id']}"
            
        if "subsidy_eur" in expected:
            assert report.get("subsidy_total_eur") == expected["subsidy_eur"], f"Subsidy mismatch for {case['case_id']}"

if __name__ == "__main__":
    pytest.main([__file__])
