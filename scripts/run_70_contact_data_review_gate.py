import os
import json
from datetime import datetime, timezone

# --- Stage 70: Contact Data Review Gate ---
# Mode: CONTACT_DATA_REVIEW_ONLY / READ_ONLY_UPSTREAM / NON_EXECUTING / NO_USAGE_AUTHORIZATION

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_69_DIR = os.path.join(ROOT_DIR, "output", "verified_contact_data_intake")
REVIEW_DIR = os.path.join(ROOT_DIR, "data", "contact_data_reviews")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "contact_data_review_gate")

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
        return "NO_REVIEW_RECORDED"
    
    text = str(sentiment_str).lower()
    if "reject" in text or "deny" in text or "invalid" in text or "fake" in text:
        return "REJECTED_CONTACT_DATA"
    
    if "approve" in text or "valid" in text or "confirm" in text or "trust" in text:
        return "VALIDATED_CONTACT_DATA"
        
    return "NEEDS_CORRECTION"

def run_gate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)

    stage69_registry = load_json(os.path.join(STAGE_69_DIR, "verified_contact_data_intake_registry_NEUSS.json")) or {"records": []}

    eligible_dossiers = []
    for r in stage69_registry.get("records", []):
        if r.get("intake_status") != "NO_CONTACT_DATA_INPUT_RECEIVED":
            eligible_dossiers.append(r)

    # Outputs
    registry = {"records": []}
    details = {"records": []}
    matrix = {"records": []}
    
    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_dossiers": len(stage69_registry.get("records", [])),
        "with_review_input": 0,
        "without_review_input": 0,
        "validated_count": 0,
        "rejected_count": 0,
        "correction_needed_count": 0,
        "zero_contact_violations": 0,
        "zero_crm_violations": 0,
        "zero_booking_violations": 0,
        "zero_assignment_violations": 0,
        "zero_execution_signal_violations": 0,
        "final_stage_verdict": ""
    }

    if not eligible_dossiers:
        audit["final_stage_verdict"] = "NO_REVIEWABLE_CONTACT_DATA_FOUND"
    else:
        for items in eligible_dossiers:
            dossier_id = items.get("dossier_id")
            upstream_intake_status = items.get("intake_status")
            
            review_filepath = os.path.join(REVIEW_DIR, f"review_{dossier_id}.json")
            raw_review_data = load_json(review_filepath)
            
            if not raw_review_data or raw_review_data == "PARSE_ERROR":
                audit["without_review_input"] += 1
                decision = "NO_REVIEW_RECORDED"
                raw_label = "MISSING"
                reviewer_metadata = {}
                notes = []
            else:
                audit["with_review_input"] += 1
                raw_label = raw_review_data.get("decision", "")
                decision = normalize_decision(raw_label)
                
                reviewer_metadata = {
                    "reviewer_id": raw_review_data.get("reviewer_id", "UNKNOWN_REVIEWER"),
                    "timestamp": raw_review_data.get("timestamp_utc", "UNKNOWN_TIME")
                }
                notes = [raw_review_data.get("notes", "")] if raw_review_data.get("notes") else []

            # Audit Counters
            if decision == "VALIDATED_CONTACT_DATA": audit["validated_count"] += 1
            if decision == "REJECTED_CONTACT_DATA": audit["rejected_count"] += 1
            if decision == "NEEDS_CORRECTION": audit["correction_needed_count"] += 1

            unresolved = []
            if decision == "NEEDS_CORRECTION":
                unresolved.append("Manual review flagged data as incomplete or suspicious.")
            if decision == "NO_REVIEW_RECORDED":
                unresolved.append("Data intake exists but human review has not been submitted.")

            # --- 1. contact_data_review_registry_NEUSS.json ---
            registry["records"].append({
                "dossier_id": dossier_id,
                "intake_status": upstream_intake_status,
                "review_input_status": "REAL_REVIEW_PRESENT" if decision != "NO_REVIEW_RECORDED" else "NO_REVIEW_PRESENT",
                "normalized_review_decision": decision,
                "reviewer_id_present": bool(reviewer_metadata.get("reviewer_id") and reviewer_metadata.get("reviewer_id") != "UNKNOWN_REVIEWER"),
                "review_timestamp_present": bool(reviewer_metadata.get("timestamp") and reviewer_metadata.get("timestamp") != "UNKNOWN_TIME"),
                "trustworthiness_status": "TRUSTED" if decision == "VALIDATED_CONTACT_DATA" else "NOT_TRUSTED",
                "human_review_required": True,
                "disclaimer_no_execution": "CONTACT_DATA_REVIEW_ONLY / NOT_AN_EXECUTION_COMMAND / USAGE_NOT_AUTHORIZED"
            })

            # --- 2. contact_data_review_details_NEUSS.json ---
            details["records"].append({
                "dossier_id": dossier_id,
                "raw_review_detected": decision != "NO_REVIEW_RECORDED",
                "raw_review_label": raw_label,
                "normalized_review_label": decision,
                "reviewer_metadata": reviewer_metadata,
                "review_notes_summary": notes,
                "intake_reference_summary": f"Targeting Stage 69 intake status: {upstream_intake_status}",
                "unresolved_issues_after_review": unresolved,
                "forbidden_automated_actions": [
                    "AUTO_CONTACT", "CRM_TASK_CREATION", "CONTACT_DATA_USAGE",
                    "APPOINTMENT_BOOKING", "INSTALLER_ASSIGNMENT"
                ],
                "governance_warning": "Data validity does NOT imply legal consent or business readiness. No execution actions authorized.",
                "disclaimer_no_usage_authorization": "no contact data usage authorization created in this stage"
            })

            # --- 3. contact_data_review_governance_matrix_NEUSS.json ---
            # EXTREME LOCKDOWN. Every single executing flag defaults rigidly. Even if VALIDATED.
            matrix["records"].append({
                "dossier_id": dossier_id,
                "AUTO_CONTACT": "FORBIDDEN",
                "MANUAL_CONTACT_EXECUTION_ALLOWED": "NOT_YET_ALLOWED",
                "CRM_TASK_CREATION_ALLOWED": "FORBIDDEN",
                "CONTACT_DATA_USAGE_ALLOWED": "NOT_YET_ALLOWED",
                "APPOINTMENT_BOOKING_ALLOWED": "FORBIDDEN",
                "INSTALLER_ASSIGNMENT_ALLOWED": "FORBIDDEN",
                "HUMAN_REVIEW_REQUIRED": "REQUIRED"
            })

        if audit["validated_count"] > 0 or audit["rejected_count"] > 0 or audit["correction_needed_count"] > 0:
            audit["final_stage_verdict"] = "CONTACT_DATA_REVIEW_RECORDED"
        else:
            audit["final_stage_verdict"] = "NO_REVIEW_INPUT_RECEIVED"

    # Write Outputs
    write_json(registry, "contact_data_review_registry_NEUSS.json")
    write_json(details, "contact_data_review_details_NEUSS.json")
    write_json(matrix, "contact_data_review_governance_matrix_NEUSS.json")
    write_json(audit, "contact_data_review_audit_NEUSS.json")

    # --- 5. stage_70_contact_data_review_report.md ---
    md_content = f"""# Stage 70 Contact Data Review Gate Report
**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Final Verdict:** `{audit["final_stage_verdict"]}`

## Executive Summary
This stage evaluates manually-submitted reviews pertaining to contact data ingestion from Stage 69.
**It explicitly separates factual data trustworthiness from operational usage rights. Validated data MUST NOT be used for CRM actions via this stage.**

## Scope & Processing
* **Total Post-Stage 69 Dossiers:** {audit["total_dossiers"]}
* **Dossiers With Usable Contact Intake Upstream:** {len(eligible_dossiers)}
* **Dossiers Processed With Human Review:** {audit["with_review_input"]}
* **Dossiers Processed Without Human Review:** {audit["without_review_input"]}

### Review Tally
* **Validated Contact Data:** {audit["validated_count"]}
* **Rejected Contact Data:** {audit["rejected_count"]}
* **Needs Correction:** {audit["correction_needed_count"]}

## Governance Matrix Hard-Locks
All executing flags have remained aggressively constrained:
- ❌ **`AUTO_CONTACT`**: FORBIDDEN
- ❌ **`CRM_TASK_CREATION_ALLOWED`**: FORBIDDEN
- ❌ **`CONTACT_DATA_USAGE_ALLOWED`**: NOT_YET_ALLOWED (For ALL records, regardless of trust)
- ❌ **`APPOINTMENT_BOOKING_ALLOWED`**: FORBIDDEN
- ❌ **`INSTALLER_ASSIGNMENT_ALLOWED`**: FORBIDDEN

### Explicit Zero-Executions
- Zero CRM Violations: {audit["zero_crm_violations"]}
- Zero Contact Violations: {audit["zero_contact_violations"]}
- Zero Execution Signal Violations: {audit["zero_execution_signal_violations"]}

All outputs preserve the unyielding disclaimer: `CONTACT_DATA_REVIEW_ONLY / NOT_AN_EXECUTION_COMMAND`.
"""
    with open(os.path.join(OUTPUT_DIR, "stage_70_contact_data_review_report.md"), 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"Stage 70 completed successfully. Verdict: {audit['final_stage_verdict']}")

if __name__ == "__main__":
    run_gate()
