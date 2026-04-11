import os
import sys
import json
import uuid
from typing import Dict, Any, List

# Setup paths
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
core_dir = os.path.join(root_dir, "core")
# Both root and core must be in path because adapter uses core.dess_main 
# but dess_main uses dess_state_machine (relative to core)
if root_dir not in sys.path: sys.path.append(root_dir)
if core_dir not in sys.path: sys.path.append(core_dir)

from core.dess_main import run_engine
from ui.adapter import business_json_to_case_payload, run_dess_engine

def cleanup_processes():
    import subprocess
    try:
        if os.name == 'nt':
            # Windows - only kill streamlit if it's actually running to avoid noise
            subprocess.run(['taskkill', '/F', '/IM', 'streamlit.exe', '/T'], capture_output=True)
    except:
        pass

def simulate_ui_render(report: Dict[str, Any], state_id: str, project_type: str):
    results = {}
    
    # Orientation Banner Count
    banner_count = 0
    status = report.get("status", "UNKNOWN")
    runtime = report.get("policy_runtime_status", {})
    if runtime.get("status") == "PAUSED":
        banner_count += 1
    
    # Check for "Orientation only" in violations (PROVISIONAL_MATH)
    for v in report.get("violations", []):
        if "orientation only" in v.get("message", "").lower():
            banner_count += 1
            
    results["orientation_banner_count"] = banner_count
    results["policy_id"] = report.get("policy_id", "N/A")
    
    # Final Amount
    math_trace = report.get("math_trace", {})
    final_locked = math_trace.get("final_locked", False)
    grant_total = float(report.get("subsidy_total_eur", "0.00"))
    
    if final_locked:
        results["final_amount"] = f"{grant_total:.2f}"
    else:
        results["final_amount"] = "—"
        
    results["grant_estimate"] = grant_total
    results["inspector_status"] = "AVAILABLE" if report else "No report to inspect yet."
    
    # Copilot Logic
    if state_id in ["S0", "S1", "S2"]: results["copilot_stage_text"] = "坚决不行"
    elif state_id == "S3": results["copilot_stage_text"] = "需谨慎核对"
    else: results["copilot_stage_text"] = "可以签约"
        
    if project_type == "BALCONY_PV":
        results["copilot_examples"] = "插座式光伏"
    elif "HEAT_PUMP" in project_type:
        results["copilot_examples"] = "热泵 JAZ"
    else:
        results["copilot_examples"] = "Ask Copilot"
    return results

def run_case(case_id: str, delta: Dict[str, Any]) -> Dict[str, Any]:
    business_json = {
        "case_id": case_id,
        "policy_id": "DUS_BALCONY_PV_2025",
        "as_of": "2026-02-28",
        "measure": { "type": "BALCONY_PV" },
        "applicant": { "is_private_person": "YES", "has_duessepass": "NO" },
        "timeline": {
            "application_submitted_date": "2026-03-01",
            "contract_signed_date": "2026-03-05",
            "has_conditional_clause": "YES",
            "down_payment_made": "NO",
            "work_started": "NO"
        },
        "costs": { "mode": "QUICK", "total_estimate_eur": 1000.00 }
    }
    
    def deep_update(d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict): deep_update(d[k], v)
            else: d[k] = v
        return d
    deep_update(business_json, delta)
    
    payload = business_json_to_case_payload(business_json)
    # Align policy path
    policy_path = os.path.join(root_dir, "policies", "dus_balcony_pv.json")
    
    state_id = delta.get("_mock_state_id", "S2")
    report = run_dess_engine(payload, policy_path)
    render_results = simulate_ui_render(report, state_id, business_json["measure"]["type"])
    
    return { "CaseID": case_id, "Payload": payload, "Report": report, "UIRender": render_results }

def main():
    cleanup_processes()
    results = []
    
    cases = [
        ("PLAN-BASE-001", {}),
        ("TC-PLAN-MAP-001", {"costs": {"total_estimate_eur": 2000.00}}),
        ("TC-PLAN-MAP-002", {"timeline": {"first_payment_made": "YES", "first_payment_date": "2026-02-01"}}),
        ("TC-PLAN-MAP-003", {"timeline": {"work_started": "YES", "work_started_date": "2026-02-01"}}),
        ("TC-PLAN-PD1-001", {"applicant": {"has_duessepass": "YES"}}),
        ("TC-PLAN-PD1-002", {"applicant": {"has_duessepass": "YES"}}),
        ("TC-PLAN-PD1-003", {
            "applicant": {"has_duessepass": "YES", "has_energy_consult_proof": "YES"},
            "test_hook": {"attributes": {"ENERGY_CONSULT_PROOF": True}}
        }),
        ("PLAN-R1", {"costs": {"total_estimate_eur": 1000.00}}),
        ("PLAN-R2", {"costs": {"total_estimate_eur": 2000.00}})
    ]
    
    for cid, delta in cases:
        results.append(run_case(cid, delta))

    print("| CaseID | PASS/FAIL | Key Actuals (Eligible/Grant/Final/Policy/RAG) | Root Cause Hint |")
    print("|---|---|---|---|")
    
    for r in results:
        cid, rep, ui = r["CaseID"], r["Report"], r["UIRender"]
        eligible = rep.get("math_trace", {}).get("eligible_cost_total", 0)
        grant, final, policy, rag = ui["grant_estimate"], ui["final_amount"], ui["policy_id"], rep.get("status", "UNKNOWN")
        
        is_pass, fail_reasons = True, []
        if ui["orientation_banner_count"] > 1:
            is_pass = False
            fail_reasons.append(f"Banner={ui['orientation_banner_count']}")
        
        # Policy is now correctly propogated in build_report
        if policy in ["UNKNOWN", "N/A"]:
             is_pass = False
             fail_reasons.append("Policy=N/A")
             
        if final == "0.00":
             is_pass = False
             fail_reasons.append("Final=0.00")
             
        if ui["copilot_examples"] == "热泵 JAZ" and r.get("Payload", {}).get("measure", {}).get("type") == "BALCONY_PV":
             is_pass = False
             fail_reasons.append("CopilotMismatch")

        if cid == "TC-PLAN-MAP-001" and eligible != 2000.00:
            is_pass = False
            fail_reasons.append(f"Eligible={eligible}")
        if cid == "TC-PLAN-MAP-002" and rag not in ["REJECTED", "BLOCKED", "RED", "INELIGIBLE_REJECTED"]:
            is_pass = False
            fail_reasons.append(f"RAG={rag}")
        if cid == "TC-PLAN-PD1-002" and rag != "NEEDS_INFO":
            is_pass = False
            fail_reasons.append(f"RAG={rag}")
        if cid == "PLAN-R2" and eligible != 2000.00:
            is_pass = False
            fail_reasons.append(f"Bleeding={eligible}")

        pass_label = "✅ PASS" if is_pass else f"❌ FAIL ({'/'.join(fail_reasons)})"
        actuals = f"E:{eligible}/G:{grant}/F:{final}/Pol:{policy}/RAG:{rag}"
        hint = ""
        if not is_pass:
            if "Banner" in str(fail_reasons): hint = "s2_report.py: Orientation repeat"
            elif "Policy=N/A" in str(fail_reasons): hint = "dess_report.py: policy_id missing"
            elif "Final=0.00" in str(fail_reasons): hint = "s2_report.py: Rendering logic"
            elif "Copilot" in str(fail_reasons): hint = "copilot.py: Static content"
            elif "RAG=APPROVED" in str(fail_reasons): hint = "solver.py: Redlines"
            elif "Bleeding" in str(fail_reasons): hint = "State leak"

        print(f"| {cid} | {pass_label} | {actuals} | {hint} |")

if __name__ == "__main__":
    main()
