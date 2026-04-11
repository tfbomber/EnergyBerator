import os
import json
from datetime import datetime, timezone

# --- Stage 75: Non-Executable Clearance Layer ---
# Mode: NON_EXECUTING / READ_ONLY_UPSTREAM / GOVERNANCE_ROUTING_ONLY

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_74_5_DIR = os.path.join(ROOT_DIR, "output", "commercial_readiness_audit")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "non_executable_clearance")

FATAL_BLOCKERS = set([
    "DATA_CONTROLLER_UNDEFINED",
    "DATA_ORIGIN_NOT_TRACEABLE",
    "CONSENT_MISSING",
    "CONSENT_NOT_EXPLICIT",
    "LEGAL_BASIS_UNDEFINED",
    "LEGAL_BASIS_NOT_CONFIRMED",
    "IDENTITY_MAPPING_FAILED",
    "ROLE_ASSIGNMENT_INCOMPLETE",
    "UNAPPROVED_EXTERNAL_SOURCE",
    "FORBIDDEN_CONTACT_PATH_DETECTED",
    "COMMERCIAL_PATH_UNKNOWN"
])

# If it's not fatal, it's recoverable mapping
REMEDIATION_MAP = {
    "MISSING_ACTIVITY_APPROVAL": "REQUEST_ACTIVITY_APPROVAL_ARTIFACT",
    "INSTALLER_READINESS_NOT_PROVEN": "REQUEST_INSTALLER_READINESS_EVIDENCE",
    "SUPPORTING_DOCUMENTS_INCOMPLETE": "REQUEST_MISSING_SUPPORTING_DOCUMENTS",
    "WORKFLOW_CLOSURE_UNCLEAR": "REQUEST_PROCESS_CLOSURE_EVIDENCE",
    "EXECUTION_CHAIN_NOT_DEFINED": "REQUEST_EXECUTION_CHAIN_DESIGN",
    "CRM_INTEGRATION_NOT_DEFINED": "REQUEST_CRM_INTEGRATION_DESIGN",
    "INSTALLER_PIPELINE_NOT_DEFINED": "REQUEST_INSTALLER_PIPELINE_DESIGN",
    "FALLBACK_NOT_DEFINED": "REQUEST_FALLBACK_DESIGN",
    "CONTACT_EXECUTOR_UNDEFINED": "REQUEST_CONTACT_EXECUTOR_DEFINITION"
}

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

def run_layer():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    input_file = os.path.join(STAGE_74_5_DIR, "commercial_readiness_audit_registry_NEUSS.json")
    audit_data = load_json(input_file)
    
    audit_lines = []
    audit_lines.append(f"STAGE 75 AUDIT LOG - {datetime.now(timezone.utc).isoformat()}")
    audit_lines.append("="*80)
    
    if not audit_data or audit_data == "PARSE_ERROR":
        audit_lines.append("GLOBAL ABORT: Stage 74.5 audit registry missing or malformed.")
        return # Safety abort

    records = audit_data.get("records", [])

    clearance_registry = {"records": []}
    lock_matrix = {"records": []}
    recoverable_pool = {"records": []}
    fully_blocked_registry = {"records": []}
    remediation_actions = {"records": []}

    summary = {
        "total_evaluated": len(records),
        "ready_for_controlled_execution": 0,
        "non_executable_but_visible": 0,
        "fully_blocked": 0,
        "total_fatal_blockers_found": 0,
        "total_remediation_actions_issued": 0
    }

    for rec in records:
        cid = rec.get("contact_id")
        blockers = rec.get("blocking_reasons", [])
        
        has_fatal = False
        recoverable_deficiencies = []
        
        for b in blockers:
            if b in FATAL_BLOCKERS:
                has_fatal = True
                summary["total_fatal_blockers_found"] += 1
            else:
                recoverable_deficiencies.append(b)
                
        # Determine State
        if has_fatal:
            state = "FULLY_BLOCKED"
            summary["fully_blocked"] += 1
            audit_lines.append(f"[{cid}] -> FULLY_BLOCKED (Fatal blockers present: {[b for b in blockers if b in FATAL_BLOCKERS]})")
        elif len(recoverable_deficiencies) > 0:
            state = "NON_EXECUTABLE_BUT_VISIBLE"
            summary["non_executable_but_visible"] += 1
            audit_lines.append(f"[{cid}] -> NON_EXECUTABLE_BUT_VISIBLE (Recoverable blockers present)")
        else:
            state = "READY_FOR_CONTROLLED_EXECUTION"
            summary["ready_for_controlled_execution"] += 1
            audit_lines.append(f"[{cid}] -> READY_FOR_CONTROLLED_EXECUTION (Pristine Audit)")

        # Generate Action Records
        clearance_registry["records"].append({
            "contact_id": cid,
            "clearance_state": state,
            "fatal_blocker_count": len([b for b in blockers if b in FATAL_BLOCKERS]),
            "recoverable_blocker_count": len(recoverable_deficiencies)
        })

        if state == "FULLY_BLOCKED":
            fully_blocked_registry["records"].append({
                "contact_id": cid,
                "fatal_reasons": [b for b in blockers if b in FATAL_BLOCKERS],
                "recoverable_reasons": recoverable_deficiencies
            })
            
        elif state == "NON_EXECUTABLE_BUT_VISIBLE":
            actions = []
            for r in recoverable_deficiencies:
                action = REMEDIATION_MAP.get(r, f"REQUEST_MANUAL_REVIEW_FOR_UNKNOWN_BLOCKER_{r}")
                actions.append({"blocker": r, "remediation": action})
                summary["total_remediation_actions_issued"] += 1
                
            recoverable_pool["records"].append({
                "contact_id": cid,
                "deficiencies": recoverable_deficiencies,
                "remediation_required": True
            })
            remediation_actions["records"].append({
                "contact_id": cid,
                "actions": actions
            })
            
        # Mandatory Execution Lock Policy
        handoff_allowed = True if state == "READY_FOR_CONTROLLED_EXECUTION" else False
        
        lock_matrix["records"].append({
            "contact_id": cid,
            "AUTO_CONTACT": "FORBIDDEN",
            "CRM_TASK_CREATION_ALLOWED": "FORBIDDEN",
            "APPOINTMENT_BOOKING_ALLOWED": "FORBIDDEN",
            "EMAIL_DISPATCH_ALLOWED": "FORBIDDEN",
            "EXPORT_ALLOWED": "FORBIDDEN",
            "SYNC_TO_EXECUTION_ENV": "FORBIDDEN",
            "MANUAL_REVIEW_HANDOFF_ALLOWED": handoff_allowed
        })
        
    audit_lines.append("="*80)
    audit_lines.append(f"Evaluation Complete. Ready: {summary['ready_for_controlled_execution']}, Visible: {summary['non_executable_but_visible']}, Blocked: {summary['fully_blocked']}")

    # Write Outputs (Exactly 6 json + 1 md expected per prompt, handle md separately via write tool)
    write_json(clearance_registry, "stage_75_clearance_registry.json")
    write_json(lock_matrix, "stage_75_execution_lock_matrix.json")
    write_json(recoverable_pool, "stage_75_recoverable_pool.json")
    write_json(fully_blocked_registry, "stage_75_fully_blocked_registry.json")
    write_json(remediation_actions, "stage_75_remediation_actions.json")
    write_json(summary, "stage_75_summary_report.json")

    with open(os.path.join(OUTPUT_DIR, "audit_log.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(audit_lines) + "\n")

    print(f"Stage 75 execution completed successfully. Modeled {summary['total_evaluated']} records.")

if __name__ == "__main__":
    run_layer()
