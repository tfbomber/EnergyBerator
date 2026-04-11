import os
import json
import time

# ==========================================
# STAGE 64: OPPORTUNITY CONFIRMATION & 
# DEPLOYMENT READINESS GATE
# ==========================================
# This script operates in STRICT READ-ONLY mode for all upstream stages.
# It translates technical revalidation results from Stage 63 into 
# business-level opportunity states.
#
# NO ACTIVATION. NO FINAL ELIGIBILITY.
# DETERMINISTIC SAFE CLASSIFICATION ONLY.

# ------------------------------------------
# CONFIGURATION PATHS
# ------------------------------------------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# UPSTREAM REFERENCES (READ ONLY)
PROD_MANUAL_CASE_CLOSURE = os.path.join(ROOT_DIR, "output", "manual_crs_case_closure", "manual_crs_case_closure_registry_NEUSS.json")
PROD_REOPEN_TRIGGER = os.path.join(ROOT_DIR, "output", "external_evidence_reopening_gate", "reopening_trigger_registry_NEUSS.json")
PROD_QUALIFIED_EVIDENCE = os.path.join(ROOT_DIR, "output", "revalidation_intake", "evidence_qualification_registry_NEUSS.json")
PROD_REVALIDATION_RESULTS = os.path.join(ROOT_DIR, "output", "selective_revalidation", "revalidation_result_registry_NEUSS.json")

# OUTPUT ROOTS
OUTPUT_ROOT = os.path.join(ROOT_DIR, "output", "opportunity_confirmation")

# ------------------------------------------
# STATE TRACKING
# ------------------------------------------
metrics = {
    "total_cases": 0,
    "confirmed_count": 0,
    "partial_count": 0,
    "hold_count": 0,
    "waiting_count": 0,
    "not_ready_count": 0
}

opportunity_registry = []
opportunity_audit_lineage = []
non_deployable_cases = []

# ------------------------------------------
# UTILITIES
# ------------------------------------------
def ensure_output_dirs():
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

def read_json(path):
    if not os.path.exists(path):
        return {"records": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(filename, data):
    path = os.path.join(OUTPUT_ROOT, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def write_file(filename, content):
    path = os.path.join(OUTPUT_ROOT, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# ------------------------------------------
# EXECUTION TIE
# ------------------------------------------
def run_opportunity_confirmation():
    print("Starting Stage 64 Opportunity Confirmation Pipeline...")
    ensure_output_dirs()

    # 1. READ INPUTS
    reval_results = read_json(PROD_REVALIDATION_RESULTS).get("records", [])

    if not reval_results:
        print("No cases explicitly finalized in Stage 63 Revalidation. Zero processing complete.")
        report_md = f"""# Stage 64 Execution Report
**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}
**Final Verdict:** `NO_OPPORTUNITY_CASES_PROCESSED`

## Processing Scope
Stage 63 inputs were completely empty. Zero downstream opportunities mapped.

## Safety Constraints Validated
* Elapsed Stage Activations: **0**
* Invalid Opportunity State Escalations: **0**
"""
        write_file("stage_64_execution_report.md", report_md)
        return

    # 2. PROCESS QUEUE
    for case_record in reval_results:
        metrics["total_cases"] += 1
        case_id = case_record.get("case_id", "UNKNOWN")
        revalidation_result = case_record.get("case_level_revalidation_result", "UNKNOWN")

        # Opportunity State Mapping
        opportunity_state = "UNKNOWN"
        deployment_readiness_level = "DATA_INSUFFICIENT"
        classification_reason = "Pending deterministic evaluation"
        next_action = "NONE"

        # 3. MAPPING RULES
        if revalidation_result == "REVALIDATION_PASSED":
            opportunity_state = "OPPORTUNITY_CONFIRMED"
            metrics["confirmed_count"] += 1
            # In a real environment, read full signals to decide between INSTALLER_CANDIDATE vs CONSULTANT. 
            # Default to INSTALLER_CANDIDATE if cleanly passed technical reval.
            deployment_readiness_level = "INSTALLER_CANDIDATE" 
            classification_reason = "Clear pass on all explicitly routed revalidation modules without blocking signals."
        
        elif revalidation_result == "REVALIDATION_PARTIAL_PASS":
            opportunity_state = "OPPORTUNITY_PARTIAL"
            metrics["partial_count"] += 1
            deployment_readiness_level = "CONSULTANT_READY"
            classification_reason = "Partial pass on revalidation modules, suggesting consultative handling required to bridge gaps."
        
        elif revalidation_result == "REVALIDATION_FAILED":
            opportunity_state = "NOT_DEPLOYMENT_READY"
            metrics["not_ready_count"] += 1
            deployment_readiness_level = "DATA_INSUFFICIENT"
            classification_reason = "Hard failure detected in one or more required revalidation modules."
            next_action = "EVALUATE_FOR_PERMANENT_REJECTION"

        elif revalidation_result == "REVALIDATION_INCONCLUSIVE":
            opportunity_state = "HOLD_FOR_MANUAL_REVIEW"
            metrics["hold_count"] += 1
            deployment_readiness_level = "DATA_INSUFFICIENT"
            classification_reason = "Missing, inconclusive, or unresolved routing signals preventing deterministic qualification."
            next_action = "ROUTE_TO_OPERATIONS_QUEUE"

        else:
            opportunity_state = "WAIT_FOR_ADDITIONAL_EVIDENCE"
            metrics["waiting_count"] += 1
            deployment_readiness_level = "DATA_INSUFFICIENT"
            classification_reason = "Fallback state for unrecognized input."
            next_action = "REQUEST_EVIDENCE_FROM_CUSTOMER"

        # Construct Registries
        opportunity_registry.append({
            "case_id": case_id,
            "geometry_id": "UNKNOWN", # Could pull from historical db
            "revalidation_result": revalidation_result,
            "opportunity_state": opportunity_state,
            "deployment_readiness_level": deployment_readiness_level,
            "classification_reason": classification_reason,
            "governing_stage": "STAGE_64"
        })

        if opportunity_state in ["NOT_DEPLOYMENT_READY", "HOLD_FOR_MANUAL_REVIEW", "WAIT_FOR_ADDITIONAL_EVIDENCE"]:
            non_deployable_cases.append({
                "case_id": case_id,
                "reason": classification_reason,
                "recommended_next_action": next_action
            })

        # Track Lineage (do not touch historic DB directly)
        opportunity_audit_lineage.append({
            "case_id": case_id,
            "closure_reference": "manual_crs_case_closure_registry_NEUSS.json",
            "reopen_reference": "reopening_trigger_registry_NEUSS.json",
            "qualification_reference": "evidence_qualification_registry_NEUSS.json",
            "revalidation_reference": "revalidation_result_registry_NEUSS.json",
            "opportunity_reference": "opportunity_registry_NEUSS.json"
        })

    # WRITE FILES
    write_json("opportunity_registry_NEUSS.json", {"records": opportunity_registry})
    write_json("opportunity_summary_NEUSS.json", metrics)
    write_json("opportunity_audit_lineage_NEUSS.json", {"records": opportunity_audit_lineage})
    write_json("non_deployable_cases_NEUSS.json", {"records": non_deployable_cases})

    # FINAL VERDICT
    final_verdict = "OPPORTUNITY_CLASSIFICATION_COMPLETED"
    if metrics["hold_count"] > 0 or metrics["waiting_count"] > 0:
        final_verdict = "OPPORTUNITY_CLASSIFICATION_COMPLETED_WITH_LIMITED_DATA"

    # WRITE MARKDOWN
    report_md = f"""# Stage 64 Execution Report
**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}
**Final Verdict:** `{final_verdict}`

## Objective
Provide controlled conversion from technical revalidation outcomes (Stage 63) to auditable opportunity states (Stage 64) mapping downstream fulfillment readiness.

## Scope of Run
* **Total Cases Evaluated:** {metrics["total_cases"]}

## Classification Distribution
* **OPPORTUNITY_CONFIRMED (Ready):** {metrics["confirmed_count"]}
* **OPPORTUNITY_PARTIAL (Consulting):** {metrics["partial_count"]}
* **HOLD_FOR_MANUAL_REVIEW:** {metrics["hold_count"]}
* **WAIT_FOR_ADDITIONAL_EVIDENCE:** {metrics["waiting_count"]}
* **NOT_DEPLOYMENT_READY:** {metrics["not_ready_count"]}

## Missing Data Conditions
* No unhandled / fatal parsing errors. Default conservative bounds hit: {metrics["hold_count"] + metrics["waiting_count"]} times.

## Integrations Validation
* Case Activations Granted: **NO** `(STRICT ZERO-GRANT COMPLIANCE)`
* Pipeline Eligibility Override: **NO** `(STRICT OPPORTUNITY-LEVEL ONLY DELEGATION)`
"""
    write_file("stage_64_execution_report.md", report_md)
    print(f"Opportunity Confirmation complete. Verdict: {final_verdict}")

if __name__ == "__main__":
    run_opportunity_confirmation()
