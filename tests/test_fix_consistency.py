import os
import sys
import json
import pytest
import subprocess
import time

# Add core and root to sys.path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
core_dir = os.path.join(base_dir, "core")
for d in [base_dir, core_dir]:
    if d not in sys.path:
        sys.path.insert(0, d)

from core.dess_main import run_engine

def cleanup_processes():
    """Cleanup stale streamlit/python processes if any are hanging."""
    if os.name == 'nt':
        # Windows
        try:
            # We only kill processes that might be related to our tests if possible, 
            # but usually taskkill is used for blunt force in these envs if they are stuck.
            # subprocess.run(["taskkill", "/F", "/IM", "streamlit.exe", "/T"], capture_output=True)
            pass 
        except:
            pass
    else:
        # Unix
        try:
            subprocess.run(["pkill", "-f", "streamlit"], capture_output=True)
        except:
            pass

@pytest.fixture(autouse=True)
def setup_teardown():
    cleanup_processes()
    yield
    cleanup_processes()

def test_t1_s2_baseline_quick_1000():
    """T1: S2 baseline (Quick=1000) should have correct costs and unlocked final."""
    policy_path = os.path.join(base_dir, "policies", "dus_balcony_pv.json")
    
    case = {
        "case_id": "T1-QUICK-1000",
        "project_type": "DUS_BALCONY_PV_2025",
        "attributes": {},
        "costs": {
            "buckets": {
                "HARDWARE": {
                    "amount": "1000.00",
                    "amount_basis": "GROSS",
                    "certainty": "ESTIMATE"
                }
            }
        },
        "timeline_events": [
            {"event_type": "APPLICATION_SUBMITTED", "date": "2025-05-01"}
        ]
    }
    
    # Save temp case
    case_path = os.path.join(base_dir, "tmp", "t1_case.json")
    os.makedirs(os.path.dirname(case_path), exist_ok=True)
    with open(case_path, 'w') as f:
        json.dump(case, f)
        
    report = run_engine(policy_path, case_path, output_dir="reports/test_results")
    
    if report["math_trace"]["eligible_cost_total_cents"] != 100000:
        print(f"\nDEBUG: Full Report for T1:\n{json.dumps(report, indent=2)}")

    assert report["math_trace"]["eligible_cost_total_cents"] == 100000
    assert report["math_trace"]["final_locked"] is False
    # Check that grant total is 500 (50% of 1000)
    assert float(report["subsidy_total_eur"]) == 500.00

def test_t2_repeat_run_separation():
    """T2: Successive runs should not bleed state."""
    policy_path = os.path.join(base_dir, "policies", "dus_balcony_pv.json")
    
    def run_with_amount(case_id, amt):
        case = {
            "case_id": case_id,
            "project_type": "DUS_BALCONY_PV_2025",
            "attributes": {},
            "costs": {
                "buckets": {
                    "HARDWARE": { "amount": amt, "amount_basis": "GROSS", "certainty": "ESTIMATE" }
                }
            },
            "timeline_events": [{"event_type": "APPLICATION_SUBMITTED", "date": "2025-05-01"}]
        }
        case_path = os.path.join(base_dir, "tmp", f"{case_id}.json")
        with open(case_path, 'w') as f:
            json.dump(case, f)
        return run_engine(policy_path, case_path, output_dir="reports/test_results")

    rep1 = run_with_amount("T2-R1", "1000.00")
    rep2 = run_with_amount("T2-R2", "2000.00")
    
    assert rep1["math_trace"]["eligible_cost_total_cents"] == 100000
    assert rep2["math_trace"]["eligible_cost_total_cents"] == 200000
    assert "1000" not in str(rep2["math_trace"])

def test_t3_pd1_duessepass_zero_inference():
    """T3: DüssePass=YES with missing ENERGY_CONSULT_PROOF should trigger NEEDS_INFO."""
    policy_path = os.path.join(base_dir, "policies", "dus_balcony_pv.json")
    
    case = {
        "case_id": "T3-PD1-NULL-PROOF",
        "project_type": "DUS_BALCONY_PV_2025",
        "attributes": {
            "bonuses": ["DUESSELPASS"]
            # Missing ENERGY_CONSULT_PROOF
        },
        "costs": {
            "buckets": {
                "HARDWARE": { "amount": "1000.00", "amount_basis": "GROSS", "certainty": "FIRM_QUOTE" }
            }
        },
        "timeline_events": [{"event_type": "APPLICATION_SUBMITTED", "date": "2025-05-01"}]
    }
    
    case_path = os.path.join(base_dir, "tmp", "t3_case.json")
    with open(case_path, 'w') as f:
        json.dump(case, f)
        
    report = run_engine(policy_path, case_path, output_dir="reports/test_results")
    
    # In V1.2 (default for T3 id), it should be NEEDS_INFO
    assert report["status"] in ["NEEDS_INFO", "NEEDS_INPUT"]
    
    # Check if violation mentions the missing field
    found_missing = False
    for v in report["violations"]:
        if "ENERGY_CONSULT_PROOF" in v.get("message", ""):
            found_missing = True
            break
    assert found_missing, f"Report should mention missing ENERGY_CONSULT_PROOF. Violations: {report['violations']}"

if __name__ == "__main__":
    pytest.main([__file__])
