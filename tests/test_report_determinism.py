import pytest
import json
import os
import sys
import hashlib
from unittest.mock import patch
from copy import deepcopy

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
REPORT_OUTPUT_DIR = os.path.join(base_dir, "tests", "reports")

VOLATILE_FIELDS = {
    "generated_at",
    "generated_at_utc",
    "run_id",
    "trace_id",
    "execution_time",
    "timestamp",
    "last_policy_sync_timestamp",
    "export_path"
}

def normalize_report(obj):
    """
    Recursively normalize report for determinism check.
    1. Removes volatile fields.
    2. Sorts runtime_tags.
    3. Sorts audit_trail by stable keys.
    """
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            if k in VOLATILE_FIELDS:
                continue
            new_obj[k] = normalize_report(v)
        
        # Special handling for runtime_status (tags) if it's a list
        if "runtime_status" in new_obj and isinstance(new_obj["runtime_status"], list):
            new_obj["runtime_status"].sort()
        
        return new_obj
    elif isinstance(obj, list):
        # Normalize items
        items = [normalize_report(x) for x in obj]
        
        # Sort collections that should be deterministic
        # For audit_trail, we sort by step_id or code or type if available
        if items and isinstance(items[0], dict):
            # Try to find a stable key to sort by
            stable_keys = ["step_id", "code", "type", "rule_id"]
            sort_key = None
            for key in stable_keys:
                if all(key in item for item in items):
                    sort_key = key
                    break
            
            if sort_key:
                items.sort(key=lambda x: str(x[sort_key]))
            else:
                # Fallback to string representation sorting
                items.sort(key=lambda x: json.dumps(x, sort_keys=True))
        else:
            items.sort(key=lambda x: str(x))
            
        return items
    else:
        return obj

def get_hash(obj):
    content = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def test_report_determinism_e2e_01():
    # 1. Load pack and find E2E-01
    with open(PACK_PATH, "r", encoding="utf-8") as f:
        pack = json.load(f)
    
    case = next((c for c in pack["cases"] if c["case_id"] == "E2E-01"), None)
    assert case is not None, "E2E-01 not found in pack"
    
    policy_path = os.path.join(FIXTURES_DIR, "policies", case["policy_ref"])
    input_path = os.path.join(FIXTURES_DIR, "cases", case["input_ref"])
    
    # Mock evidence_index
    mock_evidence_index_path = os.path.join(FIXTURES_DIR, "evidence", "evidence_index.json")
    with open(mock_evidence_index_path, "r", encoding="utf-8") as f:
        mock_evidence_data = json.load(f)
        
    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
    temp_output_dir = os.path.join(base_dir, "tmp", "determinism_runs")
    os.makedirs(temp_output_dir, exist_ok=True)

    reports = []
    
    with patch("core.dess_main.load_evidence_index") as mock_load:
        mock_load.return_value = mock_evidence_data
        
        # Run 1
        report1 = run_engine(policy_path, input_path, output_dir=temp_output_dir)
        reports.append(report1)
        
        # Run 2
        report2 = run_engine(policy_path, input_path, output_dir=temp_output_dir)
        reports.append(report2)

    # Normalize
    norm_report1 = normalize_report(deepcopy(report1))
    norm_report2 = normalize_report(deepcopy(report2))
    
    hash1 = get_hash(norm_report1)
    hash2 = get_hash(norm_report2)
    
    summary_path = os.path.join(REPORT_OUTPUT_DIR, "determinism_check.txt")
    
    if hash1 != hash2:
        # Debugging: write diff to summary
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"FAIL\nhash1: {hash1}\nhash2: {hash2}\n")
            f.write("Normalized Report 1:\n")
            f.write(json.dumps(norm_report1, indent=2, sort_keys=True))
            f.write("\nNormalized Report 2:\n")
            f.write(json.dumps(norm_report2, indent=2, sort_keys=True))
        
        pytest.fail(f"Determinism failure! hashes: {hash1} vs {hash2}. See {summary_path} for details.")
    else:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("PASS")
        print(f"\nDeterminism Check: PASS (Hash: {hash1})")

if __name__ == "__main__":
    test_report_determinism_e2e_01()
