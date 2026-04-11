import json
import os
import sys
import pytest
from unittest.mock import MagicMock

# Add core to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core")))
import main

def test_paused_gate_blocks_calculation(tmp_path):
    # Setup mock policy and case
    policy_data = {
        "policy_id": "TEST_PAUSED_POLICY",
        "status": "OPEN",
        "citations": {
            "source_url": "https://example.org",
            "doc_version": "v1",
            "last_policy_sync_timestamp": "2026-01-01T00:00:00Z"
        },
        "calculation": {
            "grant_rate": 0.5,
            "cap_cents": 100000,
            "evidence_anchor": "RECHT"
        }
    }
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(policy_data))
    
    case_data = {
        "case_id": "CASE_PAUSED_TEST",
        "attributes": {},
        "costs": {"currency": "EUR", "buckets": {}},
        "timeline_events": []
    }
    case_file = tmp_path / "case.json"
    case_file.write_text(json.dumps(case_data))
    
    # Mock load_policy_with_overlay to return PAUSED status
    original_loader = main.load_policy_with_overlay
    def mock_loader(path, base_dir):
        p = original_loader(path, base_dir)
        p["status"] = "PAUSED"
        p["_runtime_status"] = {
            "source": "OVERLAY",
            "status": "PAUSED",
            "status_reason_de": "Programm wird überarbeitet",
            "health": "OK",
            "last_checked_utc": "2026-02-26T12:00:00Z",
            "snapshot_id": "snap_123",
            "matched_keywords": ["überarbeitet"]
        }
        return p
    
    main.load_policy_with_overlay = mock_loader
    
    # Run engine
    report = main.run_engine(str(policy_file), str(case_file), str(tmp_path))
    
    # Verify
    assert report["status"] == "PAUSED / NEEDS_MANUAL_REVIEW"
    assert report["subsidy_total_cents"] == 0
    assert report["runtime_gate"]["policy_status"] == "PAUSED"
    assert "überarbeitet" in report["runtime_gate"]["matched_keywords"]
    assert any(v["code"] == "POLICY_PAUSED" for v in report["violations"])
    
    # Clean up
    main.load_policy_with_overlay = original_loader

if __name__ == "__main__":
    pytest.main([__file__])
