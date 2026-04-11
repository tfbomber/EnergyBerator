import pytest
import json
import os
import sys
from unittest.mock import patch

# Add d-ess-engine and core to path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path:
    sys.path.append(core_dir)

from core.dess_main import run_engine

def test_report_contract_shape():
    """
    Mandatory Guardrail: Ensures the report output ALWAYS contains 
    the core audit fields required for Qualified Audit compliance.
    """
    # Use E2E-01 as the baseline happy path representative
    policy_path = os.path.join(base_dir, "tests", "fixtures", "e2e", "policies", "v1.2_mock.json")
    case_path = os.path.join(base_dir, "tests", "fixtures", "e2e", "cases", "E2E-01_input.json")
    output_dir = os.path.join(base_dir, "tmp", "contract_test")
    
    # Mock evidence_index location to avoid dependency on global state
    mock_evidence_index_path = os.path.join(base_dir, "tests", "fixtures", "e2e", "evidence", "evidence_index.json")

    with patch("core.dess_main.load_evidence_index") as mock_load:
        # Load our mock index
        with open(mock_evidence_index_path, "r", encoding="utf-8") as f:
            mock_load.return_value = json.load(f)
            
        report = run_engine(policy_path, case_path, output_dir=output_dir)
    
    # 1. Top-level Contract
    assert "report_id" in report, "Missing report_id"
    assert "status" in report, "Missing status"
    assert "audit_trail" in report, "Missing audit_trail"
    assert "report_meta" in report, "Missing report_meta"
    assert "runtime_gate" in report, "Missing runtime_gate"
    
    # 2. Audit Trail Contract
    audit_trail = report["audit_trail"]
    assert len(audit_trail) > 0, "Audit trail is empty"
    
    # policy_hash MUST be present (front-loaded)
    has_policy_hash = any("policy_hash" in entry for entry in audit_trail)
    assert has_policy_hash, "policy_hash MUST be present in audit_trail"
    
    # 3. Runtime Tags Contract
    # Ensure runtime_status/tags exist in report_meta
    meta = report["report_meta"]
    assert "runtime_status" in meta, "runtime_status missing in report_meta"
    # It should be a list (even if empty) or a clear status string
    
    # 4. Mandatory Export Flag
    has_export_ok = any("export_ok" in entry for entry in audit_trail)
    assert has_export_ok, "export_ok flag missing in audit_trail"

if __name__ == "__main__":
    pytest.main([__file__])
