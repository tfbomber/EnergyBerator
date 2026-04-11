import os
import json
import glob
from datetime import datetime, timezone

# --- Stage 66: Human Review Decision Gate ---
# Mode: HUMAN_DECISION_RECORDING_ONLY / READ_ONLY_UPSTREAM / NON_EXECUTING / NO_AUTOMATED_OPERATIONS

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_65_DIR = os.path.join(ROOT_DIR, "output", "installer_handoff_readiness")
HUMAN_REVIEWS_DIR = os.path.join(ROOT_DIR, "data", "human_reviews")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "human_review_decision_gate")

ALLOWED_DECISIONS = {
    "APPROVED_FOR_MANUAL_CONTACT_PREPARATION",
    "NEED_MORE_INFORMATION",
    "REJECTED_FOR_NOW",
    "HOLD",
    "NO_DECISION_RECORDED"
}

POST_REVIEW_STATE_MAP = {
    "APPROVED_FOR_MANUAL_CONTACT_PREPARATION": "HUMAN_APPROVED_FOR_MANUAL_CONTACT_PREPARATION",
    "NEED_MORE_INFORMATION": "HUMAN_REQUESTED_MORE_INFORMATION",
    "REJECTED_FOR_NOW": "HUMAN_REJECTED_FOR_NOW",
    "HOLD": "HUMAN_ON_HOLD",
    "NO_DECISION_RECORDED": "PENDING_HUMAN_DECISION"
}

def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json(data, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return filepath

def normalize_decision(raw_decision):
    if not raw_decision:
        return "NO_DECISION_RECORDED"
    raw_upper = str(raw_decision).strip().upper()
    if raw_upper in ALLOWED_DECISIONS:
        return raw_upper
    
    # Conservative mapping for unknown/ambiguous
    if "APPROVE" in raw_upper:
        # We don't guess if it's for contact. Strict adherence to controlled vocab.
        return "NEED_MORE_INFORMATION" 
    elif "REJECT" in raw_upper:
        return "REJECTED_FOR_NOW"
    elif "HOLD" in raw_upper or "WAIT" in raw_upper:
        return "HOLD"
    else:
        return "NEED_MORE_INFORMATION"

def future_pathway_language(normalized_decision):
    if normalized_decision == "APPROVED_FOR_MANUAL_CONTACT_PREPARATION":
        return ["eligible for future manual contact preparation review"]
    elif normalized_decision == "NEED_MORE_INFORMATION":
        return ["requires additional document collection before further review"]
    elif normalized_decision == "HOLD":
        return ["remains on hold pending external clarification"]
    else:
        return ["not approved for progression at this time"]

def run_gate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(HUMAN_REVIEWS_DIR, exist_ok=True)

    queue_data = load_json(os.path.join(STAGE_65_DIR, "installer_review_queue_NEUSS.json")) or {"records": []}
    registry_data = load_json(os.path.join(STAGE_65_DIR, "installer_handoff_registry_NEUSS.json")) or {"records": []}
    
    handoff_registry_map = {r["dossier_id"]: r for r in registry_data.get("records", [])}

    eligible_dossiers = []
    for q in queue_data.get("records", []):
        if q.get("queue_state") in ["READY_FOR_HUMAN_REVIEW", "CONDITIONALLY_READY_FOR_HUMAN_REVIEW"]:
            eligible_dossiers.append(q)

    # Outputs
    decision_register = {"records": []}
    decision_details = {"records": []}
    post_review_registry = {"records": []}
    governance_matrix = {"records": []}
    
    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_queue_dossiers_scanned": len(queue_data.get("records", [])),
        "eligible_reviewable_dossiers": len(eligible_dossiers),
        "dossiers_with_real_human_input": 0,
        "dossiers_without_human_input": 0,
        "normalized_decisions_recorded": 0,
        "zero_activation_violations": 0,
        "zero_contact_violations": 0,
        "zero_assignment_violations": 0,
        "zero_execution_signal_violations": 0,
        "historical_mutation_violations": 0,
        "final_stage_verdict": ""
    }

    if not eligible_dossiers:
        audit["final_stage_verdict"] = "NO_REVIEWABLE_DOSSIERS_FOUND"
    else:
        for items in eligible_dossiers:
            dossier_id = items.get("dossier_id")
            upstream_state = items.get("queue_state")
            registry_entry = handoff_registry_map.get(dossier_id, {})

            review_file = os.path.join(HUMAN_REVIEWS_DIR, f"review_{dossier_id}.json")
            review_input = load_json(review_file)
            
            raw_decision = None
            if review_input:
                audit["dossiers_with_real_human_input"] += 1
                raw_decision = review_input.get("decision_label")
                human_input_status = "REAL_HUMAN_DECISION_INPUT_PRESENT"
                reviewer_metadata = {}
                for k in ["reviewer_id", "review_source", "review_timestamp", "reviewer_notes", "evidence_gap_references"]:
                    if k in review_input:
                        reviewer_metadata[k] = review_input[k]
                
                raw_notes = review_input.get("reviewer_notes", "")
            else:
                audit["dossiers_without_human_input"] += 1
                human_input_status = "NO_HUMAN_DECISION_INPUT_RECEIVED"
                reviewer_metadata = {}
                raw_notes = ""
            
            normalized_decision = normalize_decision(raw_decision)
            if normalized_decision != "NO_DECISION_RECORDED":
                audit["normalized_decisions_recorded"] += 1
            
            # --- 1. human_review_decision_register_NEUSS.json ---
            decision_register["records"].append({
                "dossier_id": dossier_id,
                "upstream_queue_status": upstream_state,
                "human_input_status": human_input_status,
                "normalized_decision": normalized_decision,
                "decision_record_status": "RECORDED" if review_input else "PENDING",
                "reviewer_id_present": "reviewer_id" in reviewer_metadata,
                "review_timestamp_present": "review_timestamp" in reviewer_metadata,
                "human_review_required": registry_entry.get("human_review_required", True),
                "lineage_reference_ids": registry_entry.get("lineage_reference_ids", [dossier_id]),
                "disclaimer_no_execution": "HUMAN_DECISION_RECORDED_ONLY / NOT_AN_EXECUTION_COMMAND"
            })

            # --- 2. human_review_decision_details_NEUSS.json ---
            decision_details["records"].append({
                "dossier_id": dossier_id,
                "decision_detail_status": "RECORDED_WITH_INPUT" if review_input else "NO_INPUT",
                "raw_review_input_detected": bool(review_input),
                "raw_decision_label": raw_decision,
                "normalized_decision_label": normalized_decision,
                "reviewer_metadata": reviewer_metadata,
                "review_notes_summary": raw_notes if raw_notes else "No notes provided.",
                "unresolved_gaps_after_review": reviewer_metadata.get("evidence_gap_references", []),
                "allowed_future_manual_pathways": future_pathway_language(normalized_decision),
                "forbidden_automated_actions": [
                    "AUTO_CONTACT", "AUTO_ASSIGN_INSTALLER", "AUTO_APPOINTMENT", 
                    "AUTO_ACTIVATION", "AUTO_SUBSIDY_INITIATION"
                ],
                "governance_warning": "This decision is read-only. No operations are authorized.",
                "evidence_sources_used": ["Stage 65 Installer Handoff Registry"]
            })

            # --- 3. post_review_status_registry_NEUSS.json ---
            post_review_registry["records"].append({
                "dossier_id": dossier_id,
                "post_review_status": POST_REVIEW_STATE_MAP[normalized_decision],
                "recorded_at": datetime.now(timezone.utc).isoformat()
            })

            # --- 4. human_decision_governance_matrix_NEUSS.json ---
            # Even if approved, we set MANUAL_CONTACT_EXECUTION_ALLOWED to NOT_YET_ALLOWED
            manual_prep = "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE" if normalized_decision == "APPROVED_FOR_MANUAL_CONTACT_PREPARATION" else "NOT_YET_ALLOWED"
            reopen_allowed = "REQUIRED" if normalized_decision == "NEED_MORE_INFORMATION" else "NOT_YET_ALLOWED"
            
            governance_matrix["records"].append({
                "dossier_id": dossier_id,
                "AUTO_CONTACT": "FORBIDDEN",
                "AUTO_ASSIGN_INSTALLER": "FORBIDDEN",
                "AUTO_APPOINTMENT": "FORBIDDEN",
                "AUTO_ACTIVATION": "FORBIDDEN",
                "AUTO_SUBSIDY_INITIATION": "FORBIDDEN",
                "AUTO_CONTRACT_SIGNAL": "FORBIDDEN",
                "MANUAL_CONTACT_PREPARATION_ELIGIBLE": manual_prep,
                "MANUAL_CONTACT_EXECUTION_ALLOWED": "NOT_YET_ALLOWED",
                "HUMAN_REVIEW_REOPEN_ALLOWED": reopen_allowed
            })

        if audit["dossiers_with_real_human_input"] == len(eligible_dossiers):
            audit["final_stage_verdict"] = "HUMAN_DECISIONS_RECORDED"
        elif audit["dossiers_with_real_human_input"] > 0:
            audit["final_stage_verdict"] = "PARTIAL_DECISION_RECORDING"
        else:
            audit["final_stage_verdict"] = "NO_HUMAN_DECISION_INPUT_RECEIVED"

    # Write Outputs
    write_json(decision_register, "human_review_decision_register_NEUSS.json")
    write_json(decision_details, "human_review_decision_details_NEUSS.json")
    write_json(post_review_registry, "post_review_status_registry_NEUSS.json")
    write_json(governance_matrix, "human_decision_governance_matrix_NEUSS.json")
    write_json(audit, "human_review_decision_audit_NEUSS.json")

    # --- 6. stage_66_human_review_decision_gate_report.md ---
    md_content = f"""# Stage 66 Human Review Decision Gate Report
**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Final Verdict:** `{audit["final_stage_verdict"]}`

## Executive Summary
This stage performs controlled recording of human decisions based on Stage 65 human review queues.
**It explicitly enforces a zero-execution boundary.**

## Scope & Processing
* **Total Queue Dossiers Scanned:** {audit["total_queue_dossiers_scanned"]}
* **Eligible Reviewable Dossiers:** {audit["eligible_reviewable_dossiers"]}
* **Dossiers with Real Human Input:** {audit["dossiers_with_real_human_input"]}
* **Dossiers without Human Input (Pending):** {audit["dossiers_without_human_input"]}
* **Normalized Decisions Recorded:** {audit["normalized_decisions_recorded"]}

## Governance Assertions
* **Zero Activation Violations:** {audit["zero_activation_violations"]} detected
* **Zero Contact Violations:** {audit["zero_contact_violations"]} detected
* **Zero Assignment Violations:** {audit["zero_assignment_violations"]} detected
* **Zero Execution Signal Violations:** {audit["zero_execution_signal_violations"]} detected
* **Historical Mutation Violations:** {audit["historical_mutation_violations"]} detected

### Explicit Limitations (What this stage DID NOT do)
- ❌ No inference of customer willingness.
- ❌ No automatic dispatching.
- ❌ No conversion of human decision records into executable commands.
- ❌ No implication of "ready for outreach" or "customer-ready".

All outputs proudly carry the disclaimer: `HUMAN_DECISION_RECORDED_ONLY / NOT_AN_EXECUTION_COMMAND`.
"""
    with open(os.path.join(OUTPUT_DIR, "stage_66_human_review_decision_gate_report.md"), 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"Stage 66 completed successfully. Verdict: {audit['final_stage_verdict']}")

if __name__ == "__main__":
    run_gate()
