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

PACK_PATH = os.path.join(base_dir, "tests", "packs", "module3_e2e_pack_v1.json")
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
def test_e2e_smoke_case(case):
    policy_path, input_path = get_case_data(case)
    expected = case["expected"]
    
    # Mock evidence_index location to use our fixture
    mock_evidence_index_path = os.path.join(FIXTURES_DIR, "evidence", "evidence_index.json")
    
    with patch("core.dess_main.load_evidence_index") as mock_load:
        # Load our mock index
        with open(mock_evidence_index_path, "r", encoding="utf-8") as f:
            mock_load.return_value = json.load(f)
            
        # Run engine
        # Note: output_dir is a temp dir for tests
        output_dir = os.path.join(base_dir, "tmp", "test_runs")
        report = run_engine(policy_path, input_path, output_dir=output_dir)
        
        # ASSERTIONS
        
        # a) final_verdict
        actual_verdict = report.get("status")
        assert actual_verdict == expected["verdict"], f"Verdict mismatch for {case['case_id']}"
        
        # b) runtime_tags_contains
        if "runtime_tags_contains" in expected:
            actual_tags = report.get("report_meta", {}).get("runtime_status", [])
            # Some reports might use a string or a list, adapter says it's a string 'PAUSED'
            # Let's check against the requirements
            for tag in expected["runtime_tags_contains"]:
                assert tag in str(actual_tags), f"Missing tag {tag} in {actual_tags}"
        
        # c) report.audit_trail must contain policy_hash (Strong validation)
        # We need to check audit_trail or report_meta
        audit_trail = report.get("audit_trail", [])
        
        # User requested: "report.audit_trail 中必须包含 policy_hash"
        # Let's see if we can find it
        found_policy_hash = False
        for entry in audit_trail:
            if "policy_hash" in entry:
                found_policy_hash = True
                break
        
        # Record Missing Trace Fields if not found
        if not found_policy_hash:
            pytest.fail(f"MISSING_TRACE_FIELD: 'policy_hash' not found in audit_trail for {case['case_id']}")

        # d) evidence_check / anchor_result / gate_trigger
        must_keys = expected.get("must_audit_keys", [])
        actual_keys = set()
        for entry in audit_trail:
            actual_keys.update(entry.keys())
        # Also check findings/violations
        for finding in report.get("violations", []):
            actual_keys.update(finding.keys())
            if "trace" in finding:
                actual_keys.update(finding["trace"].keys())

        missing_keys = [k for k in must_keys if k not in actual_keys]
        if missing_keys:
            pytest.fail(f"MISSING_TRACE_FIELDS: {missing_keys} not found in report/audit for {case['case_id']}")

