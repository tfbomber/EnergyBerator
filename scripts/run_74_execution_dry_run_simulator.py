import os
import json
from datetime import datetime, timezone
import uuid

# --- Stage 74: Contact Execution Dry-Run Simulator ---
# Mode: NON_EXECUTING / READ_ONLY_UPSTREAM / SIMULATION_ONLY

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_73_DIR = os.path.join(ROOT_DIR, "output", "manual_activation_warrant")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "execution_dry_run")

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

def run_gate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(STAGE_73_DIR, exist_ok=True)

    warrant_file = os.path.join(STAGE_73_DIR, "manual_activation_warrant_registry_NEUSS.json")
    pool_file = os.path.join(STAGE_73_DIR, "future_contact_pool_registry_NEUSS.json")
    matrix_file = os.path.join(STAGE_73_DIR, "warrant_governance_lock_matrix_NEUSS.json")

    warrant_data = load_json(warrant_file)
    pool_data = load_json(pool_file)
    matrix_data = load_json(matrix_file)

    summary = {
        "total_records_seen": 0,
        "total_records_in_future_contact_pool": 0,
        "total_records_in_warrant_registry": 0,
        "eligible_for_simulation": 0,
        "skipped_due_to_missing_data": 0,
        "skipped_due_to_invalid_warrant": 0,
        "skipped_due_to_pool_mismatch": 0,
        "skipped_due_to_lock_failure": 0,
        "skipped_due_to_lineage_failure": 0,
        "simulated_contact_drafts": 0,
        "simulated_crm_tasks": 0,
        "simulated_appointments": 0,
        "simulated_installer_matches": 0,
        "global_abort_triggered": False,
        "execution_attempts_detected": 0,
        "hard_lock_integrity_status": "PASS"
    }
    
    audit_lines = []
    audit_lines.append(f"STAGE 74 AUDIT LOG - {datetime.now(timezone.utc).isoformat()}")
    audit_lines.append("="*80)

    # 1. Global Abort Checks
    global_abort = False
    
    if warrant_data is None:
        audit_lines.append("GLOBAL ABORT: manual_activation_warrant_registry_NEUSS.json is missing.")
        global_abort = True
    elif warrant_data == "PARSE_ERROR":
        audit_lines.append("GLOBAL ABORT: manual_activation_warrant_registry_NEUSS.json is malformed.")
        global_abort = True
        
    if pool_data is None:
        audit_lines.append("GLOBAL ABORT: future_contact_pool_registry_NEUSS.json is missing.")
        global_abort = True
    elif pool_data == "PARSE_ERROR":
        audit_lines.append("GLOBAL ABORT: future_contact_pool_registry_NEUSS.json is malformed.")
        global_abort = True
        
    if matrix_data is None:
        audit_lines.append("GLOBAL ABORT: warrant_governance_lock_matrix_NEUSS.json is missing.")
        global_abort = True
    elif matrix_data == "PARSE_ERROR":
        audit_lines.append("GLOBAL ABORT: warrant_governance_lock_matrix_NEUSS.json is malformed.")
        global_abort = True

    if global_abort:
        summary["global_abort_triggered"] = True
        summary["hard_lock_integrity_status"] = "FAIL"
        audit_lines.append("Execution halted due to Global Abort rule. No drafts generated.")
        
        write_json({"records": []}, "contact_execution_dry_run_registry_NEUSS.json")
        write_json({"records": []}, "crm_task_simulation_registry_NEUSS.json")
        write_json({"records": []}, "appointment_simulation_registry_NEUSS.json")
        write_json({"records": []}, "installer_matching_simulation_registry_NEUSS.json")
        write_json(summary, "execution_simulation_summary_NEUSS.json")
        write_json({"records": []}, "governance_execution_lock_verification_NEUSS.json")
        
        with open(os.path.join(OUTPUT_DIR, "audit_log.txt"), 'w', encoding='utf-8') as f:
            f.write("\n".join(audit_lines) + "\n")
        
        print("Stage 74 completed with GLOBAL_ABORT.")
        return

    # Process Maps
    warrant_records = warrant_data.get("records", [])
    pool_records = pool_data.get("records", [])
    matrix_records = matrix_data.get("records", [])
    
    summary["total_records_in_warrant_registry"] = len(warrant_records)
    summary["total_records_in_future_contact_pool"] = len(pool_records)
    
    # Establish dictionary lookups for O(1) correlation and lineage uniqueness
    pool_dict = {}
    pool_duplicates = set()
    for p in pool_records:
        cid = p.get("contact_id")
        if cid in pool_dict:
            pool_duplicates.add(cid)
        pool_dict[cid] = p
        
    matrix_dict = {}
    matrix_duplicates = set()
    for m in matrix_records:
        cid = m.get("contact_id")
        if cid in matrix_dict:
            matrix_duplicates.add(cid)
        matrix_dict[cid] = m

    warrant_dict = {}
    warrant_duplicates = set()
    for w in warrant_records:
        cid = w.get("contact_id")
        if cid in warrant_dict:
            warrant_duplicates.add(cid)
        warrant_dict[cid] = w

    summary["total_records_seen"] = len(warrant_records) # Usually the driving pool is warrant

    # New explicitly log pool items NOT in warrant (Case G part 2)
    for contact_id in pool_dict:
        if contact_id not in warrant_dict:
            summary["skipped_due_to_pool_mismatch"] += 1
            audit_lines.append(f"SKIP [{contact_id}]: Found in pool but completely missing from warrant_registry.")

    dry_run_registry = {"records": []}
    crm_registry = {"records": []}
    appointment_registry = {"records": []}
    installer_registry = {"records": []}
    verification_matrix = {"records": []}

    for contact_id, w_rec in warrant_dict.items():
        if not contact_id:
            summary["skipped_due_to_missing_data"] += 1
            audit_lines.append("SKIP: Missing contact_id in warrant_registry.")
            continue
            
        w_block = w_rec.get("manual_activation_warrant", {})
        verdict = w_block.get("warrant_verdict")
        
        # 1. Pool Mismatch (in warrant, missing in pool)
        if contact_id not in pool_dict:
            summary["skipped_due_to_pool_mismatch"] += 1
            audit_lines.append(f"SKIP [{contact_id}]: Not found in future_contact_pool_registry.")
            continue

        # 2. Valid Warrant (Checked after ensuring it exists in both dicts)
        if verdict != "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE":
            summary["skipped_due_to_invalid_warrant"] += 1
            audit_lines.append(f"SKIP [{contact_id}]: Warrant != GRANTED_FOR_FUTURE_CONTACT_STAGE ({verdict}).")
            continue
            
        # 3. Lineage Uniqueness
        if contact_id in warrant_duplicates or contact_id in pool_duplicates or contact_id in matrix_duplicates:
            summary["skipped_due_to_lineage_failure"] += 1
            audit_lines.append(f"SKIP [{contact_id}]: Lineage not uniquely mappable (Duplicate encountered).")
            continue
            
        # 4. Lock Governance
        lock_rec = matrix_dict.get(contact_id)
        if not lock_rec:
            summary["skipped_due_to_lock_failure"] += 1
            summary["hard_lock_integrity_status"] = "FAIL"
            audit_lines.append(f"SKIP [{contact_id}]: No governance lock entry found.")
            continue
            
        if lock_rec.get("AUTO_CONTACT_ALLOWED") != "FORBIDDEN" or \
           lock_rec.get("MANUAL_CONTACT_EXECUTION_ALLOWED") != "FORBIDDEN" or \
           lock_rec.get("CRM_TASK_CREATION_ALLOWED") != "FORBIDDEN" or \
           lock_rec.get("APPOINTMENT_BOOKING_ALLOWED") != "FORBIDDEN" or \
           lock_rec.get("INSTALLER_ASSIGNMENT_ALLOWED") != "FORBIDDEN":
            summary["skipped_due_to_lock_failure"] += 1
            summary["hard_lock_integrity_status"] = "FAIL"
            audit_lines.append(f"SKIP [{contact_id}]: Governance locks breached! Flag is not FORBIDDEN.")
            continue
            
        # Eligible!
        summary["eligible_for_simulation"] += 1
        audit_lines.append(f"SIMULATED [{contact_id}]: Lineage pure, locks intact. Generating drafts.")
        
        trace_id = str(uuid.uuid4())
        timestamp_str = datetime.now(timezone.utc).isoformat()
        
        contact_draft = {
            "channel": "LETTER", # Fallback conservative
            "message_template": "TEMPLATE_A_GENERIC_WARM_UP",
            "personalization_fields": {"salutation": "PLACEHOLDER", "address": "PLACEHOLDER"},
            "draft_status": "SIMULATED_ONLY",
            "compliance_note": "DO NOT SEND - SIMULATION ONLY"
        }
        
        crm_draft = {
            "task_type": "INITIAL_OUTREACH",
            "priority": "LOW", # Fallback conservative
            "recommended_timing": "T+14 days", # Fallback conservative
            "status": "SIMULATED_ONLY",
            "compliance_note": "DO NOT CREATE IN CRM - SIMULATION ONLY"
        }
        
        appt_draft = {
            "appointment_type": "ONSITE_ASSESSMENT",
            "suggested_window": "NEXT_4_WEEKS", # Fallback conservative
            "status": "NOT_BOOKED_SIMULATION",
            "compliance_note": "DO NOT BOOK - SIMULATION ONLY"
        }
        
        installer_draft = {
            "installer_candidates": [],
            "matching_score": 0.0,
            "candidate_source": "STATIC_PLACEHOLDER",
            "assignment_status": "NOT_ASSIGNED_SIMULATION",
            "compliance_note": "DO NOT ASSIGN - SIMULATION ONLY"
        }
        
        record = {
            "contact_id": contact_id,
            "simulation_metadata": {
                "SIMULATION_ONLY": True,
                "EXECUTION_ALLOWED": False,
                "source_stage": "STAGE_74_DRY_RUN",
                "timestamp": timestamp_str,
                "trace_id": trace_id,
                "lineage": {
                    "warrant_registry_source": "manual_activation_warrant_registry_NEUSS.json",
                    "future_pool_source": "future_contact_pool_registry_NEUSS.json",
                    "lock_matrix_source": "warrant_governance_lock_matrix_NEUSS.json"
                }
            },
            "contact_draft": contact_draft,
            "crm_task_draft": crm_draft,
            "appointment_draft": appt_draft,
            "installer_matching_draft": installer_draft
        }
        
        dry_run_registry["records"].append(record)
        
        # Sub-Extraction Modules
        crm_registry["records"].append({"contact_id": contact_id, "trace_id": trace_id, "crm_task_draft": crm_draft})
        appointment_registry["records"].append({"contact_id": contact_id, "trace_id": trace_id, "appointment_draft": appt_draft})
        installer_registry["records"].append({"contact_id": contact_id, "trace_id": trace_id, "installer_matching_draft": installer_draft})
        
        verification_matrix["records"].append({
            "contact_id": contact_id,
            "trace_id": trace_id,
            "AUTO_CONTACT_ALLOWED": False,
            "MANUAL_CONTACT_EXECUTION_ALLOWED": False,
            "CRM_TASK_CREATION_ALLOWED": False,
            "APPOINTMENT_BOOKING_ALLOWED": False,
            "INSTALLER_ASSIGNMENT_ALLOWED": False
        })
        
        summary["simulated_contact_drafts"] += 1
        summary["simulated_crm_tasks"] += 1
        summary["simulated_appointments"] += 1
        summary["simulated_installer_matches"] += 1

    audit_lines.append("="*80)
    audit_lines.append(f"Final Lock Verification Result: {summary['hard_lock_integrity_status']}")

    # Write Outputs
    write_json(dry_run_registry, "contact_execution_dry_run_registry_NEUSS.json")
    write_json(crm_registry, "crm_task_simulation_registry_NEUSS.json")
    write_json(appointment_registry, "appointment_simulation_registry_NEUSS.json")
    write_json(installer_registry, "installer_matching_simulation_registry_NEUSS.json")
    write_json(summary, "execution_simulation_summary_NEUSS.json")
    write_json(verification_matrix, "governance_execution_lock_verification_NEUSS.json")

    with open(os.path.join(OUTPUT_DIR, "audit_log.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(audit_lines) + "\n")

    print(f"Stage 74 completed safely. Integrity: {summary['hard_lock_integrity_status']}. Global abort: {summary['global_abort_triggered']}")

if __name__ == "__main__":
    run_gate()
