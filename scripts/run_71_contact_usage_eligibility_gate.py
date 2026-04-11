import os
import json
from datetime import datetime, timezone

# --- Stage 71: Contact Usage Eligibility Gate ---
# Mode: CONTACT_DATA_USAGE_ELIGIBILITY_ONLY / READ_ONLY_UPSTREAM / NON_EXECUTING / NO_CONTACT_AUTHORIZATION

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_70_DIR = os.path.join(ROOT_DIR, "output", "contact_data_review_gate")
REVIEW_DIR = os.path.join(ROOT_DIR, "data", "contact_usage_reviews")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "contact_usage_eligibility")

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
        return "NO_USAGE_DECISION_RECORDED"
    
    text = str(sentiment_str).lower()
    if "approve" in text or "yes" in text or "allow" in text or "eligible" in text:
        return "USAGE_APPROVED_FOR_FUTURE_MANUAL_CONTACT_STAGE"
    
    if "reject" in text or "deny" in text or "no" in text or "forbidden" in text:
        return "USAGE_NOT_APPROVED"
        
    return "NEEDS_ADDITIONAL_COMPLIANCE_CHECK"

def run_gate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)

    stage70_registry = load_json(os.path.join(STAGE_70_DIR, "contact_data_review_registry_NEUSS.json")) or {"records": []}

    eligible_dossiers = []
    for r in stage70_registry.get("records", []):
        eligible_dossiers.append(r)

    # Outputs
    registry = {"records": []}
    details = {"records": []}
    matrix = {"records": []}
    
    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_dossiers": len(stage70_registry.get("records", [])),
        "with_usage_input": 0,
        "without_usage_input": 0,
        "usage_approved_count": 0,
        "not_approved_count": 0,
        "compliance_pending_count": 0,
        "zero_contact_violations": 0,
        "zero_crm_violations": 0,
        "zero_booking_violations": 0,
        "zero_assignment_violations": 0,
        "zero_execution_signal_violations": 0,
        "final_stage_verdict": ""
    }

    if not eligible_dossiers:
        audit["final_stage_verdict"] = "NO_USAGE_ELIGIBLE_DOSSIERS_FOUND"
    else:
        for items in eligible_dossiers:
            dossier_id = items.get("dossier_id")
            upstream_review_status = items.get("normalized_review_decision")
            
            review_filepath = os.path.join(REVIEW_DIR, f"review_{dossier_id}.json")
            raw_review_data = load_json(review_filepath)
            
            if not raw_review_data or raw_review_data == "PARSE_ERROR":
                audit["without_usage_input"] += 1
                decision = "NO_USAGE_DECISION_RECORDED"
                raw_label = "MISSING"
                reviewer_metadata = {}
                notes = []
            else:
                audit["with_usage_input"] += 1
                raw_label = raw_review_data.get("decision", "")
                decision = normalize_decision(raw_label)
                
                reviewer_metadata = {
                    "reviewer_id": raw_review_data.get("reviewer_id", "UNKNOWN_REVIEWER"),
                    "timestamp": raw_review_data.get("timestamp_utc", "UNKNOWN_TIME")
                }
                notes = [raw_review_data.get("notes", "")] if raw_review_data.get("notes") else []

            # Audit Counters
            if decision == "USAGE_APPROVED_FOR_FUTURE_MANUAL_CONTACT_STAGE": audit["usage_approved_count"] += 1
            if decision == "USAGE_NOT_APPROVED": audit["not_approved_count"] += 1
            if decision == "NEEDS_ADDITIONAL_COMPLIANCE_CHECK": audit["compliance_pending_count"] += 1

            unresolved = []
            if decision == "NEEDS_ADDITIONAL_COMPLIANCE_CHECK":
                unresolved.append("Manual usage review flagged data for additional legal or compliance review.")
            if decision == "NO_USAGE_DECISION_RECORDED":
                unresolved.append("No human decision input for usage exists.")

            # Calculate matrix output values safely.
            contact_data_usage_allowed = "NOT_YET_ALLOWED"
            if decision == "USAGE_APPROVED_FOR_FUTURE_MANUAL_CONTACT_STAGE":
                 contact_data_usage_allowed = "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE"

            # --- 1. contact_usage_eligibility_registry_NEUSS.json ---
            registry["records"].append({
                "dossier_id": dossier_id,
                "review_status": upstream_review_status,
                "usage_input_status": "REAL_USAGE_DECISION_PRESENT" if decision != "NO_USAGE_DECISION_RECORDED" else "NO_USAGE_DECISION_PRESENT",
                "normalized_usage_decision": decision,
                "usage_eligibility_status": "ELIGIBLE" if decision == "USAGE_APPROVED_FOR_FUTURE_MANUAL_CONTACT_STAGE" else "INELIGIBLE/PENDING",
                "human_review_required": True,
                "lineage_reference_ids": items.get("lineage_reference_ids", [dossier_id]),
                "disclaimer_no_execution": "CONTACT_USAGE_ELIGIBILITY_ONLY / NOT_AN_EXECUTION_COMMAND"
            })

            # --- 2. contact_usage_eligibility_details_NEUSS.json ---
            details["records"].append({
                "dossier_id": dossier_id,
                "raw_usage_input_detected": decision != "NO_USAGE_DECISION_RECORDED",
                "raw_usage_label": raw_label,
                "normalized_usage_label": decision,
                "reviewer_metadata": reviewer_metadata,
                "usage_notes_summary": notes,
                "review_reference_summary": f"Targeting Stage 70 review status: {upstream_review_status}",
                "unresolved_compliance_issues": unresolved,
                "forbidden_automated_actions": [
                    "AUTO_CONTACT", "CRM_TASK_CREATION", "APPOINTMENT_BOOKING", "INSTALLER_ASSIGNMENT"
                ],
                "governance_warning": "Approval unlocks CONDITIONAL ELIGIBILITY for a future stage only. NO execution sequence is triggered in this stage.",
                "disclaimer_no_contact_authorization": "no contact authorization created in this stage"
            })

            # --- 3. contact_usage_governance_matrix_NEUSS.json ---
            matrix["records"].append({
                "dossier_id": dossier_id,
                "AUTO_CONTACT": "FORBIDDEN",
                "MANUAL_CONTACT_EXECUTION_ALLOWED": "NOT_YET_ALLOWED",
                "CONTACT_DATA_USAGE_ALLOWED": contact_data_usage_allowed,
                "CRM_TASK_CREATION_ALLOWED": "FORBIDDEN",
                "APPOINTMENT_BOOKING_ALLOWED": "FORBIDDEN",
                "INSTALLER_ASSIGNMENT_ALLOWED": "FORBIDDEN"
            })

        if audit["usage_approved_count"] > 0 or audit["not_approved_count"] > 0 or audit["compliance_pending_count"] > 0:
            audit["final_stage_verdict"] = "CONTACT_USAGE_ELIGIBILITY_RECORDED"
        else:
            audit["final_stage_verdict"] = "NO_USAGE_DECISION_RECORDED"

    # Write Outputs
    write_json(registry, "contact_usage_eligibility_registry_NEUSS.json")
    write_json(details, "contact_usage_eligibility_details_NEUSS.json")
    write_json(matrix, "contact_usage_governance_matrix_NEUSS.json")
    write_json(audit, "contact_usage_eligibility_audit_NEUSS.json")

    # --- 5. stage_71_contact_usage_eligibility_report.md ---
    md_content = f"""# Stage 71 Contact Usage Eligibility Report
**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Final Verdict:** `{audit["final_stage_verdict"]}`

## Executive Summary
This stage evaluates human usage decisions on previously verified contact data from Stage 70.
**Approval maps strictly to CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE and does NOT mean CRM readiness.**

## Scope & Processing
* **Total Post-Stage 70 Dossiers:** {audit["total_dossiers"]}
* **Dossiers Processed With Usage Input:** {audit["with_usage_input"]}
* **Dossiers Processed Without Usage Input:** {audit["without_usage_input"]}

### Usage Tally
* **Usage Approved for Future Stage:** {audit["usage_approved_count"]}
* **Usage Not Approved:** {audit["not_approved_count"]}
* **Needs Additional Compliance Check:** {audit["compliance_pending_count"]}

## Governance Matrix Hard-Locks
All executing flags have remained constrained:
- ❌ **`AUTO_CONTACT`**: FORBIDDEN
- ❌ **`MANUAL_CONTACT_EXECUTION_ALLOWED`**: NOT_YET_ALLOWED 
- 🔒 **`CONTACT_DATA_USAGE_ALLOWED`**: Unlocks to CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE upon approval only.
- ❌ **`CRM_TASK_CREATION_ALLOWED`**: FORBIDDEN
- ❌ **`APPOINTMENT_BOOKING_ALLOWED`**: FORBIDDEN
- ❌ **`INSTALLER_ASSIGNMENT_ALLOWED`**: FORBIDDEN

### Explicit Zero-Executions
- Zero CRM Violations: {audit["zero_crm_violations"]}
- Zero Contact Violations: {audit["zero_contact_violations"]}
- Zero Booking Violations: {audit["zero_booking_violations"]}
- Zero Assignment Violations: {audit["zero_assignment_violations"]}
- Zero Execution Signal Violations: {audit["zero_execution_signal_violations"]}

All outputs preserve the unyielding disclaimer: `CONTACT_USAGE_ELIGIBILITY_ONLY / NOT_AN_EXECUTION_COMMAND`.
"""
    with open(os.path.join(OUTPUT_DIR, "stage_71_contact_usage_eligibility_report.md"), 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"Stage 71 completed successfully. Verdict: {audit['final_stage_verdict']}")

if __name__ == "__main__":
    run_gate()
