import os
import json
from datetime import datetime, timezone

# --- Stage 76: Remediation Intake & Revalidation Loop ---
# Mode: NON_EXECUTING / READ_ONLY_UPSTREAM / REVALIDATION_ONLY

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_75_DIR = os.path.join(ROOT_DIR, "output", "non_executable_clearance")
INPUT_PAYLOADS_DIR = os.path.join(ROOT_DIR, "data", "incoming_remediation_payloads")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "remediation_revalidation_loop")

def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return "PARSE_ERROR"

def write_json(data, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return filepath

def run_loop():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(INPUT_PAYLOADS_DIR, exist_ok=True)
    
    # 1. Inputs
    pool_file = os.path.join(STAGE_75_DIR, "stage_75_recoverable_pool.json")
    payloads_file = os.path.join(INPUT_PAYLOADS_DIR, "stage_76_incoming_remediation_payloads_NEUSS.json")

    pool_data = load_json(pool_file)
    payloads_data = load_json(payloads_file)

    audit_lines = []
    audit_lines.append(f"STAGE 76 AUDIT LOG - {datetime.now(timezone.utc).isoformat()}")
    audit_lines.append("="*80)

    if not pool_data or pool_data == "PARSE_ERROR":
        audit_lines.append("GLOBAL ABORT: Recoverable pool missing or malformed.")
        return
        
    if not payloads_data or payloads_data == "PARSE_ERROR":
        audit_lines.append("GLOBAL ABORT: Incoming remediation payloads missing or malformed.")
        return

    pool_records = pool_data.get("records", [])
    payloads = payloads_data.get("payloads", [])

    # Index pool for quick filtering
    recoverable_index = {}
    for r in pool_records:
        recoverable_index[r.get("contact_id")] = r.get("deficiencies", [])

    # 2. Output Containers
    intake_registry = {"records": []}
    lineage = {"records": []}
    revalidation_plan = {"records": []}
    revalidation_results = {"records": []}
    transition_registry = {"records": []}
    lock_matrix = {"records": []}
    
    summary = {
        "total_incoming_payloads": len(payloads),
        "payloads_accepted_for_revalidation": 0,
        "payloads_rejected_not_in_pool": 0,
        "cases_upgraded_to_ready": 0,
        "cases_remained_visible": 0,
        "cases_downgraded_to_blocked": 0
    }

    # Process Payloads
    for p in payloads:
        cid = p.get("case_id")
        
        # Validation 1: Does it exist in the Recoverable Pool?
        if cid not in recoverable_index:
            summary["payloads_rejected_not_in_pool"] += 1
            audit_lines.append(f"REJECTED INTAKE [{cid}]: Case not present in Stage 75 NON_EXECUTABLE_BUT_VISIBLE pool. Evidence discarded.")
            continue
            
        summary["payloads_accepted_for_revalidation"] += 1
        
        # Full Prompt Constraint Fields
        prior_status = "NON_EXECUTABLE_BUT_VISIBLE"
        blocker_targeted = p.get("blocker_targeted", [])
        evidence_file_name = p.get("evidence_file_name", "UNKNOWN")
        evidence_hash = p.get("evidence_hash", "UNKNOWN")
        intake_timestamp = p.get("intake_timestamp", datetime.now(timezone.utc).isoformat())
        remediation_source = p.get("remediation_source", "UNKNOWN")
        reviewer_or_intake_actor = p.get("reviewer_or_intake_actor", "SYSTEM_DEFAULT")
        targeted_modules = p.get("targeted_modules_for_revalidation", [])
        
        # Intake Registry
        intake_registry["records"].append({
            "case_id": cid,
            "prior_status": prior_status,
            "blocker_targeted": blocker_targeted,
            "evidence_file_name": evidence_file_name,
            "evidence_hash": evidence_hash,
            "intake_timestamp": intake_timestamp,
            "remediation_source": remediation_source,
            "reviewer_or_intake_actor": reviewer_or_intake_actor,
            "targeted_modules_for_revalidation": targeted_modules
        })
        
        # Lineage Tracking
        known_deficiencies = recoverable_index[cid]
        lineage["records"].append({
            "case_id": cid,
            "known_deficiencies": known_deficiencies,
            "submitted_evidence_hash": evidence_hash,
            "claims_to_resolve": blocker_targeted
        })
        
        # Revalidation Plan
        revalidation_plan["records"].append({
            "case_id": cid,
            "modules_to_execute": targeted_modules,
            "skip_full_recomputation": True 
        })
        
        # Perform Simulated Execution of Selective Revalidation
        simulated_validity = p.get("SIMULATED_EVIDENCE_VALIDITY", "VALID")
        resolves_all = set(known_deficiencies).issubset(set(blocker_targeted))
        
        result_details = {
            "case_id": cid,
            "evidence_valid": False,
            "fatal_flaw_introduced": False,
            "all_prior_blockers_resolved": False,
            "modules_executed": targeted_modules
        }
        
        new_status = "NON_EXECUTABLE_BUT_VISIBLE"
        
        if simulated_validity == "VALID":
            result_details["evidence_valid"] = True
            if resolves_all:
                result_details["all_prior_blockers_resolved"] = True
                new_status = "READY_FOR_CONTROLLED_EXECUTION"
                audit_lines.append(f"UPGRADE [{cid}]: Evidence valid, all blockers resolved. Status -> READY_FOR_CONTROLLED_EXECUTION")
                summary["cases_upgraded_to_ready"] += 1
            else:
                audit_lines.append(f"INCOMPLETE [{cid}]: Evidence valid but did not resolve all known blockers. Remaining -> Visible.")
                summary["cases_remained_visible"] += 1
                
        elif simulated_validity == "INVALID_EVIDENCE_MALFORMED":
            # Invalid evidence that undermines traceability
            result_details["evidence_valid"] = False
            result_details["fatal_flaw_introduced"] = True
            new_status = "FULLY_BLOCKED"
            audit_lines.append(f"DOWNGRADE [{cid}]: Invalid evidence submitted. Integrity failure. Status -> FULLY_BLOCKED")
            summary["cases_downgraded_to_blocked"] += 1
            
        elif simulated_validity == "FATAL_OVERSIGHT_REVEALED":
            # Remediation reveals a deeper fatal blocker (e.g. proof of consent fraud)
            result_details["evidence_valid"] = True
            result_details["fatal_flaw_introduced"] = True
            new_status = "FULLY_BLOCKED"
            audit_lines.append(f"DOWNGRADE [{cid}]: Evidence revealed fatal contradiction. Status -> FULLY_BLOCKED")
            summary["cases_downgraded_to_blocked"] += 1
            
        revalidation_results["records"].append(result_details)
        
        transition_registry["records"].append({
            "case_id": cid,
            "prior_status": prior_status,
            "new_status": new_status,
            "revalidation_success": new_status == "READY_FOR_CONTROLLED_EXECUTION"
        })
        
        # Matrix Enforcement
        handoff_allowed = True if new_status == "READY_FOR_CONTROLLED_EXECUTION" else False
        lock_matrix["records"].append({
            "contact_id": cid,
            "clearance_state": new_status,
            "AUTO_CONTACT": "FORBIDDEN",
            "CRM_TASK_CREATION_ALLOWED": "FORBIDDEN",
            "APPOINTMENT_BOOKING_ALLOWED": "FORBIDDEN",
            "EMAIL_DISPATCH_ALLOWED": "FORBIDDEN",
            "EXPORT_ALLOWED": "FORBIDDEN",
            "SYNC_TO_EXECUTION_ENV": "FORBIDDEN",
            "MANUAL_REVIEW_HANDOFF_ALLOWED": handoff_allowed
        })
        
    audit_lines.append("="*80)
    audit_lines.append(f"Loop Complete. Upgraded: {summary['cases_upgraded_to_ready']}, Maintained: {summary['cases_remained_visible']}, Downngraded: {summary['cases_downgraded_to_blocked']}")

    # Writes
    write_json(intake_registry, "stage_76_remediation_intake_registry.json")
    write_json(lineage, "stage_76_remediation_lineage.json")
    write_json(revalidation_plan, "stage_76_targeted_revalidation_plan.json")
    write_json(revalidation_results, "stage_76_revalidation_results.json")
    write_json(transition_registry, "stage_76_status_transition_registry.json")
    write_json(lock_matrix, "stage_76_execution_lock_matrix.json")
    write_json(summary, "stage_76_summary_report.json")

    with open(os.path.join(OUTPUT_DIR, "audit_log.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(audit_lines) + "\n")

    print(f"Stage 76 complete. Read {summary['total_incoming_payloads']} payloads.")

if __name__ == "__main__":
    run_loop()
