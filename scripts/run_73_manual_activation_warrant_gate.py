import os
import json
import glob
from datetime import datetime, timezone

# --- Stage 73: Manual Activation Warrant Architect ---
# Mode: NON_EXECUTING / READ_ONLY_UPSTREAM / AUTHORIZATION_LAYER_ONLY

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_72_DIR = os.path.join(ROOT_DIR, "output", "contact_activation_policy")
REVIEW_DIR = os.path.join(ROOT_DIR, "data", "manual_activation_warrants")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "manual_activation_warrant")

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

def normalize_decision(sentiment_str):
    if not sentiment_str:
        return "WARRANT_NOT_GRANTED"
    
    text = str(sentiment_str).lower().strip()
    
    if "approved for internal preparation" in text:
        return "WARRANT_GRANTED_FOR_PREPARATION_ONLY"
    
    if "approved to enter future contact stage after legal sign-off" in text or "approved for future contact stage" in text:
        return "WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE"
        
    if "not approved" in text:
        return "WARRANT_NOT_GRANTED"
        
    if "requires dpo" in text or "compliance review" in text:
        return "NEEDS_ADDITIONAL_COMPLIANCE_REVIEW"
        
    # Any other ambiguous or unmapped phrasing
    return "WARRANT_NOT_GRANTED"

def determine_final_warrant(norm_dec, stage72_verdict):
    if stage72_verdict == "STILL_LOCKED":
        return "MANUAL_WARRANT_NOT_GRANTED", "Pessimistic lock: Upstream policy scored as STILL_LOCKED."
        
    if norm_dec == "WARRANT_NOT_GRANTED":
        return "MANUAL_WARRANT_NOT_GRANTED", "Human explicitly or implicitly rejected warrant."
        
    if norm_dec == "NEEDS_ADDITIONAL_COMPLIANCE_REVIEW":
        return "MANUAL_WARRANT_NOT_GRANTED", "Human requested DPO/compliance review. Suspended."
        
    if norm_dec == "WARRANT_GRANTED_FOR_PREPARATION_ONLY":
        return "MANUAL_WARRANT_GRANTED_FOR_PREPARATION_ONLY", "Human approved for internal preparation only."

    if norm_dec == "WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE":
        if stage72_verdict == "ELIGIBLE_FOR_ACTIVATION":
            return "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE", "Full criteria met. Unlocking future contact pool."
        if stage72_verdict == "READY_FOR_MANUAL_REVIEW":
            return "MANUAL_WARRANT_GRANTED_FOR_PREPARATION_ONLY", "Pessimistic Downgrade: Human approved future pool, but Stage 72 only scored READY. Downgraded to PREPARATION_ONLY."

    return "MANUAL_WARRANT_NOT_GRANTED", "Safety fallback: Unresolved combinatory state."

def build_approved_scope(final_verdict):
    scope = {
      "INTERNAL_PREPARATION_ALLOWED": "FORBIDDEN",
      "EXPORT_TO_FUTURE_CONTACT_POOL_ALLOWED": "FORBIDDEN",
      "AUTO_CONTACT_ALLOWED": "FORBIDDEN",
      "MANUAL_CONTACT_EXECUTION_ALLOWED": "FORBIDDEN",
      "CRM_TASK_CREATION_ALLOWED": "FORBIDDEN",
      "APPOINTMENT_BOOKING_ALLOWED": "FORBIDDEN",
      "INSTALLER_ASSIGNMENT_ALLOWED": "FORBIDDEN"
    }
    
    if final_verdict == "MANUAL_WARRANT_GRANTED_FOR_PREPARATION_ONLY":
        scope["INTERNAL_PREPARATION_ALLOWED"] = "ALLOWED"
    elif final_verdict == "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE":
        scope["INTERNAL_PREPARATION_ALLOWED"] = "ALLOWED"
        scope["EXPORT_TO_FUTURE_CONTACT_POOL_ALLOWED"] = "ALLOWED"
        
    return scope

def run_gate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)

    stage72_registry = load_json(os.path.join(STAGE_72_DIR, "contact_activation_policy_registry_NEUSS.json")) or {"records": []}

    records = stage72_registry.get("records", [])

    # Outputs
    registry = {"records": []}
    future_pool = {"records": []}
    governance_lock_matrix = {"records": []}
    
    summary = {
        "total_records_seen": len(records),
        "total_structurally_valid_records": 0,
        "total_structurally_invalid_records": 0,
        "total_review_artifacts_found": 0,
        "total_unique_review_artifacts": 0,
        "total_conflicting_review_artifacts": 0,
        "total_unmappable_review_artifacts": 0,
        "total_warrant_not_granted": 0,
        "total_warrant_granted_for_preparation_only": 0,
        "total_warrant_granted_for_future_contact_stage": 0,
        "total_future_contact_pool_records": 0,
        "total_execution_flags_still_forbidden": 0,   # Each record adds 5 locks.
        "hard_lock_integrity_status": "PASS"
    }

    audit_lines = []
    audit_lines.append(f"STAGE 73 AUDIT LOG - {datetime.now(timezone.utc).isoformat()}")
    audit_lines.append("="*80)

    for items in records:
        contact_id = items.get("contact_id")
        stage72_verdict = ""
        is_structurally_valid = True
        
        # 1. Structural Validation
        if not contact_id:
            is_structurally_valid = False
            audit_lines.append("MALFORMED: Missing contact_id in Stage 72 record.")
        else:
            policy_block = items.get("activation_policy", {})
            stage72_verdict = policy_block.get("activation_verdict")
            if not stage72_verdict:
                is_structurally_valid = False
                audit_lines.append(f"MALFORMED: {contact_id} is missing activation_verdict in Stage 72 data.")
                
        if not is_structurally_valid:
            summary["total_structurally_invalid_records"] += 1
            contact_id = contact_id or "UNKNOWN_ID"
            final_verdict = "MANUAL_WARRANT_NOT_GRANTED"
            block_reason = "Structurally invalid Stage 72 record."
            norm_dec = "WARRANT_NOT_GRANTED"
            r_found = False
            r_path = ""
            r_uniqueness = "UNMAPPABLE"
            r_id = ""
            r_time = ""
        else:
            summary["total_structurally_valid_records"] += 1
            # 2. File Searching
            matching_files = glob.glob(os.path.join(REVIEW_DIR, f"*{contact_id}*.json"))
            
            if len(matching_files) == 0:
                summary["total_review_artifacts_found"] += 0
                r_found = False
                r_path = ""
                r_uniqueness = "NOT_FOUND"
                norm_dec = "WARRANT_NOT_GRANTED"
                r_id = ""
                r_time = ""
                final_verdict = "MANUAL_WARRANT_NOT_GRANTED"
                block_reason = "MISSING review artifact."
                audit_lines.append(f"MISSING_ARTIFACT: {contact_id}.")
                
            elif len(matching_files) > 1:
                summary["total_review_artifacts_found"] += len(matching_files)
                summary["total_conflicting_review_artifacts"] += 1
                r_found = True
                r_path = "MULTIPLE_CONFLICTING_PATHS"
                r_uniqueness = "CONFLICTING"
                norm_dec = "WARRANT_NOT_GRANTED"
                r_id = ""
                r_time = ""
                final_verdict = "MANUAL_WARRANT_NOT_GRANTED"
                block_reason = "Duplicate or conflicting review artifacts exist."
                audit_lines.append(f"CONFLICTING_ARTIFACTS: {contact_id} found {len(matching_files)} matching files.")
                
            else:
                summary["total_review_artifacts_found"] += 1
                summary["total_unique_review_artifacts"] += 1
                r_path = matching_files[0]
                raw_data = load_json(r_path)
                
                if not raw_data or raw_data == "PARSE_ERROR" or not isinstance(raw_data, dict):
                    summary["total_unmappable_review_artifacts"] += 1
                    r_found = True
                    r_uniqueness = "UNMAPPABLE"
                    norm_dec = "WARRANT_NOT_GRANTED"
                    r_id = ""
                    r_time = ""
                    final_verdict = "MANUAL_WARRANT_NOT_GRANTED"
                    block_reason = "Malformed JSON review artifact."
                    audit_lines.append(f"MALFORMED_ARTIFACT: {contact_id} artifact could not be parsed.")
                else:
                    r_found = True
                    r_uniqueness = "UNIQUE"
                    r_id = raw_data.get("reviewer_id", "UNKNOWN")
                    r_time = raw_data.get("timestamp_utc", "UNKNOWN")
                    raw_dec = raw_data.get("decision", "")
                    
                    norm_dec = normalize_decision(raw_dec)
                    if norm_dec == "WARRANT_NOT_GRANTED":
                        audit_lines.append(f"AMBIGUOUS/REJECTED_LANGUAGE: {contact_id} normalized '{raw_dec}' to NOT_GRANTED.")
                        
                    final_verdict, block_reason = determine_final_warrant(norm_dec, stage72_verdict)
                    
                    if "Pessimistic Downgrade" in block_reason:
                        audit_lines.append(f"DOWNGRADE: {contact_id} user asked for FUTURE pool but Stage 72 was barely READY. Downgraded to PREPARATION.")

        # Update summary counters
        if final_verdict == "MANUAL_WARRANT_NOT_GRANTED":
            summary["total_warrant_not_granted"] += 1
        elif final_verdict == "MANUAL_WARRANT_GRANTED_FOR_PREPARATION_ONLY":
            summary["total_warrant_granted_for_preparation_only"] += 1
        elif final_verdict == "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE":
            summary["total_warrant_granted_for_future_contact_stage"] += 1
            summary["total_future_contact_pool_records"] += 1
            audit_lines.append(f"GRANTED_FUTURE_POOL: {contact_id} successfully registered into governance sandbox pool.")
            future_pool["records"].append({
                "contact_id": contact_id,
                "inclusion_timestamp": datetime.now(timezone.utc).isoformat(),
                "governance_disclaimer": "This is a governance pool only. IT DOES NOT MEAN EXECUTION. All output action sinks remain FORBIDDEN."
            })

        scope = build_approved_scope(final_verdict)
        
        # Hard Lock Integrity Check
        if scope["AUTO_CONTACT_ALLOWED"] != "FORBIDDEN" or \
           scope["MANUAL_CONTACT_EXECUTION_ALLOWED"] != "FORBIDDEN" or \
           scope["CRM_TASK_CREATION_ALLOWED"] != "FORBIDDEN" or \
           scope["APPOINTMENT_BOOKING_ALLOWED"] != "FORBIDDEN" or \
           scope["INSTALLER_ASSIGNMENT_ALLOWED"] != "FORBIDDEN":
            summary["hard_lock_integrity_status"] = "CRITICAL_FAIL_LOCKS_BREACHED"
        else:
            summary["total_execution_flags_still_forbidden"] += 5

        # 1. Output Registry
        registry["records"].append({
            "contact_id": contact_id,
            "stage_72_activation_verdict": stage72_verdict,
            "manual_activation_warrant": {
                "review_artifact_found": r_found,
                "review_artifact_path": os.path.basename(r_path) if r_path else "",
                "review_artifact_uniqueness": r_uniqueness,
                "reviewer_id": r_id,
                "review_timestamp": r_time,
                "normalized_review_decision": norm_dec,
                "warrant_verdict": final_verdict,
                "approved_scope": scope,
                "blocking_reason": block_reason,
                "notes": "NO EXECUTION PERMITTED IN THIS STAGE."
            }
        })
        
        # 4. Governance Lock Matrix
        governance_lock_matrix["records"].append({
            "contact_id": contact_id,
            "AUTO_CONTACT_ALLOWED": scope["AUTO_CONTACT_ALLOWED"],
            "MANUAL_CONTACT_EXECUTION_ALLOWED": scope["MANUAL_CONTACT_EXECUTION_ALLOWED"],
            "CRM_TASK_CREATION_ALLOWED": scope["CRM_TASK_CREATION_ALLOWED"],
            "APPOINTMENT_BOOKING_ALLOWED": scope["APPOINTMENT_BOOKING_ALLOWED"],
            "INSTALLER_ASSIGNMENT_ALLOWED": scope["INSTALLER_ASSIGNMENT_ALLOWED"]
        })

    audit_lines.append("="*80)
    audit_lines.append(f"Final Lock Verification Result: {summary['hard_lock_integrity_status']}")

    # Write Outputs
    write_json(registry, "manual_activation_warrant_registry_NEUSS.json")
    write_json(summary, "warrant_decision_summary_NEUSS.json")
    write_json(future_pool, "future_contact_pool_registry_NEUSS.json")
    write_json(governance_lock_matrix, "warrant_governance_lock_matrix_NEUSS.json")

    with open(os.path.join(OUTPUT_DIR, "audit_log.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(audit_lines) + "\n")

    print(f"Stage 73 completed successfully. Integrity: {summary['hard_lock_integrity_status']}")

if __name__ == "__main__":
    run_gate()
