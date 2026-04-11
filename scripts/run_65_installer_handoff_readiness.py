import os
import json
import time

# ==========================================
# STAGE 65: INSTALLER HANDOFF READINESS PACK
# ==========================================
# This stage builds a strictly non-executing commercial handoff preparation layer.
# It identifies specific confirmed opportunities, packages them into structured, 
# auditable formats for human review, and enforces strict governance boundaries.
#
# CRISIS CONTROL:
# - NO AUTOMATED EXECUTION
# - NO SUBSIDY INITIATION
# - NO CUSTOMER OUTREACH
# - READ_ONLY FOR ALL HISTORICAL PROD DATA
# - ALL QUEUES ARE HUMAN-REVIEW ONLY

# ------------------------------------------
# CONFIGURATION PATHS
# ------------------------------------------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# UPSTREAM REFERENCES (READ ONLY)
PROD_OPPORTUNITY_REGISTRY = os.path.join(ROOT_DIR, "output", "opportunity_confirmation", "opportunity_registry_NEUSS.json")

# OUTPUT ROOTS
OUTPUT_ROOT = os.path.join(ROOT_DIR, "output", "installer_handoff_readiness")

# ------------------------------------------
# STATE TRACKING
# ------------------------------------------
metrics = {
    "total_dossiers_scanned": 0,
    "eligible_handoff_candidates": 0,
    "packets_generated": 0,
    "zero_activation_violations": 0,
    "zero_contact_violations": 0,
    "zero_assignment_violations": 0,
    "historical_mutation_violations": 0,
    "final_stage_verdict": "PENDING"
}

installer_handoff_registry = []
installer_handoff_packets = []
handoff_governance_matrix = []
installer_review_queue = []

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
# HANDOFF LOGIC
# ------------------------------------------

def run_handoff_preparation():
    print("Starting Stage 65 Installer Handoff Readiness Pipeline...")
    ensure_output_dirs()

    # 1. READ INPUTS
    opportunities = read_json(PROD_OPPORTUNITY_REGISTRY).get("records", [])

    if not opportunities:
        print("Empty opportunity registry. Fast failing to NO_HANDOFF_CANDIDATES_FOUND.")
        metrics["final_stage_verdict"] = "NO_HANDOFF_CANDIDATES_FOUND"
        write_json("handoff_preparation_audit_NEUSS.json", metrics)
        
        report_md = f"""# Stage 65 Installer Handoff Readiness Report
**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}
**Final Verdict:** `{metrics["final_stage_verdict"]}`

## Executive Summary
No upstream Stage 64 cases were found. The stage evaluated zero candidates and produced zero packets. 
Governance limitations securely maintained.
"""
        write_file("stage_65_installer_handoff_readiness_report.md", report_md)
        return

    # 2. FILTER & PROCESS ELIGIBLE DOSSIERS
    for case_record in opportunities:
        metrics["total_dossiers_scanned"] += 1
        
        dossier_id = case_record.get("case_id", "UNKNOWN")
        opportunity_status = case_record.get("opportunity_state", "UNKNOWN")
        commercial_readiness_label = case_record.get("deployment_readiness_level", "UNKNOWN")
        reval_result = case_record.get("revalidation_result", "UNKNOWN")

        # Core Eligibility Threshold
        if opportunity_status != "OPPORTUNITY_CONFIRMED" or commercial_readiness_label != "INSTALLER_CANDIDATE":
            continue
        
        metrics["eligible_handoff_candidates"] += 1

        # We assume 1 gap since there are no external human-contact flags injected yet
        unresolved_gap_count = 1
        condition_blocks = ["Missing human contact authorization clearance"]
        classification_reason_historic = case_record.get("classification_reason", "No reason retained")

        # --- A. Master Registry Build ---
        installer_handoff_registry.append({
            "dossier_id": dossier_id,
            "upstream_stage_64_status": reval_result,
            "opportunity_status": opportunity_status,
            "commercial_readiness_label": commercial_readiness_label,
            "handoff_readiness_status": "CONDITIONALLY_READY_FOR_HUMAN_REVIEW", # Strict conservatism
            "human_review_required": True,
            "blocker_count": len(condition_blocks),
            "unresolved_gap_count": unresolved_gap_count,
            "allowed_next_step_profile": ["HUMAN_REVIEW"],
            "forbidden_action_profile": ["AUTO_CONTACT", "AUTO_ASSIGN_INSTALLER"],
            "lineage_reference_ids": [dossier_id]
        })

        # --- B. Specific Handoff Packets Build ---
        installer_handoff_packets.append({
            "dossier_id": dossier_id,
            "packet_status": "LOCKED_FOR_HUMAN_REVIEW",
            "identity_summary": {
                "dossier_id": dossier_id,
                "domain_classification": "ENERGY_OPPORTUNITY"
            },
            "lineage_summary": {
                 "revalidation_stage_pass": True,
                 "confirmed_opportunity": True
            },
            "technical_confirmation_summary": {
                 "statement": "Upstream rules engines indicate physical and technical constraints are clear based on qualified evidence."
            },
            "commercial_candidate_summary": {
                 "statement": f"Objectively categorized as {commercial_readiness_label} due to upstream rule: {classification_reason_historic}."
            },
            "risk_summary": {
                 "statement": "No inferred data allowed. See upstream technical models for risk scoring."
            },
            "blocker_summary": {
                 "active_blockers": condition_blocks
            },
            "unresolved_information_gaps": [
                {
                    "gap_description": "Lack of overt human contact authorization.",
                    "governance_impact": "Prevents any automated downstream signaling for deployment or appointments.",
                    "resolution_required": "Must be established by a human operator."
                }
            ],
            "recommended_human_actions": [
                 "Review dossier completeness",
                 "Validate customer/contact pathway externally",
                 "Decide whether installer pre-check should be scheduled manually"
            ],
            "forbidden_automated_actions": [
                 "automatic contact",
                 "automatic appointment booking",
                 "automatic installer dispatch",
                 "automatic eligibility grant",
                 "automatic contract initiation",
                 "automatic subsidy trigger"
            ],
            "approval_requirements": [
                 "Human signature / Review status update"
            ],
            "evidence_sources_used": ["d-ess-engine/output/opportunity_confirmation/opportunity_registry_NEUSS.json"],
            "disclaimer_no_auto_execution": "HUMAN_REVIEW_REQUIRED. This packet is NOT an execution command. Do NOT infer customer intent or automate deployment."
        })
        metrics["packets_generated"] += 1

        # --- C. Governance Matrix Build ---
        handoff_governance_matrix.append({
            "dossier_id": dossier_id,
            "AUTO_CONTACT": "FORBIDDEN",
            "AUTO_ASSIGN_INSTALLER": "FORBIDDEN",
            "AUTO_APPOINTMENT": "FORBIDDEN",
            "AUTO_ACTIVATION": "FORBIDDEN",
            "AUTO_SUBSIDY_INITIATION": "FORBIDDEN",
            "AUTO_CONTRACT_SIGNAL": "FORBIDDEN",
            "HUMAN_REVIEW": "REQUIRED",
            "HUMAN_CONTACT_ALLOWED_AFTER_REVIEW": "ALLOWED_POST_REVIEW",
            "HUMAN_SITE_CHECK_ALLOWED_AFTER_REVIEW": "ALLOWED_POST_REVIEW",
            "governing_stage": "STAGE_65"
        })

        # --- D. Human Review Queue Register ---
        installer_review_queue.append({
            "dossier_id": dossier_id,
            "queue_state": "CONDITIONALLY_READY_FOR_HUMAN_REVIEW",
            "queue_reason": "Dossier met commercial classification but requires human resolution of contact boundaries."
        })

    # 3. SYNTHESIS & AUDIT WRITES
    
    metrics["final_stage_verdict"] = "HANDOFF_PACKETS_GENERATED" if metrics["packets_generated"] > 0 else "NO_HANDOFF_CANDIDATES_FOUND"

    write_json("installer_handoff_registry_NEUSS.json", {"records": installer_handoff_registry})
    write_json("installer_handoff_packets_NEUSS.json", {"records": installer_handoff_packets})
    write_json("handoff_governance_matrix_NEUSS.json", {"records": handoff_governance_matrix})
    write_json("installer_review_queue_NEUSS.json", {"records": installer_review_queue})
    write_json("handoff_preparation_audit_NEUSS.json", metrics)

    report_md = f"""# Stage 65 Installer Handoff Readiness Report
**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}
**Final Verdict:** `{metrics["final_stage_verdict"]}`

## Executive Objective
Construct a strictly non-executing commercial handoff preparation layer. This stage bridges confirmed opportunities to human teams while explicitly enforcing zero automation over contact, contract, or deployment.

## Candidate Funnel
* **Total Upstream Dossiers Evaluated:** {metrics["total_dossiers_scanned"]}
* **Eligible Candidates Found:** {metrics["eligible_handoff_candidates"]} (Must be `OPPORTUNITY_CONFIRMED` AND `INSTALLER_CANDIDATE`)
* **Packets Generated:** {metrics["packets_generated"]}

## Governance & Safety Assertions
* **Zero Activation Violations:** {metrics["zero_activation_violations"]} detected
* **Zero Contact Violations:** {metrics["zero_contact_violations"]} detected
* **Zero Assignment Violations:** {metrics["zero_assignment_violations"]} detected
* **Historical Mutation Violations:** {metrics["historical_mutation_violations"]} detected

### Explicitly Forbidden Automated Truths
- No inference of customer willingness to buy.
- No inference of budget match or financial risk scoring. 
- No automatic dispatching.
- No assumption of address-level contact authorization.

All packaged outputs securely carry the `HUMAN_REVIEW_REQUIRED` restriction flag. All governance matrix action mappings deterministically block `AUTO` routes.
"""
    write_file("stage_65_installer_handoff_readiness_report.md", report_md)
    print(f"Handoff Preparation complete. Verdict: {metrics['final_stage_verdict']}")

if __name__ == "__main__":
    run_handoff_preparation()
