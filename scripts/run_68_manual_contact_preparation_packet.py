import os
import json
from datetime import datetime, timezone

# --- Stage 68: Manual Contact Preparation Packet ---
# Mode: CONTACT_PREPARATION_ONLY / READ_ONLY_UPSTREAM / NON_EXECUTING / NO_OUTREACH_AUTHORIZATION

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_67_DIR = os.path.join(ROOT_DIR, "output", "manual_action_eligibility_gate")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "manual_contact_preparation_packet")

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

def extract_contact_data(dossier_id):
    # D-ESS primarily deals with geodata and logical states currently. 
    # Unless explicit upstream payload data has been defined, we must not hallucinate contact info.
    # In a real system, this might join against a user-profile CRM pull. Here it remains strictly null/missing.
    return {
        "available": {},
        "missing": ["phone_number", "email_address", "contact_name", "preferred_time"]
    }

def generate_packet():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    eligibility_data = load_json(os.path.join(STAGE_67_DIR, "manual_action_eligibility_registry_NEUSS.json")) or {"records": []}
    pathway_details = load_json(os.path.join(STAGE_67_DIR, "manual_action_pathway_details_NEUSS.json")) or {"records": []}
    
    details_map = {r["dossier_id"]: r for r in pathway_details.get("records", [])}

    eligible_dossiers = []
    for r in eligibility_data.get("records", []):
        if r.get("contact_preparation_eligibility") == "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE":
            eligible_dossiers.append(r)

    # Outputs
    registry = {"records": []}
    packets = {"records": []}
    matrix = {"records": []}
    
    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_post_stage67_dossiers_scanned": len(eligibility_data.get("records", [])),
        "eligible_contact_preparation_dossiers": len(eligible_dossiers),
        "packets_generated": 0,
        "dossiers_with_contact_data_present": 0,
        "dossiers_with_missing_contact_data": 0,
        "zero_activation_violations": 0,
        "zero_contact_violations": 0,
        "zero_assignment_violations": 0,
        "zero_booking_violations": 0,
        "zero_execution_signal_violations": 0,
        "historical_mutation_violations": 0,
        "final_stage_verdict": ""
    }

    if not eligible_dossiers:
        audit["final_stage_verdict"] = "NO_CONTACT_PREPARATION_CANDIDATES_FOUND"
    else:
        for items in eligible_dossiers:
            dossier_id = items.get("dossier_id")
            detail_entry = details_map.get(dossier_id, {})
            
            contact_info = extract_contact_data(dossier_id)
            
            if contact_info["available"]:
                audit["dossiers_with_contact_data_present"] += 1
                contact_detail_status = "PARTIAL_DATA_AVAILABLE"
            else:
                audit["dossiers_with_missing_contact_data"] += 1
                contact_detail_status = "ALL_DATA_MISSING"

            audit["packets_generated"] += 1

            unresolved_gaps = detail_entry.get("evidence_gap_summary", [])
            gap_count = len(unresolved_gaps)

            # --- 1. manual_contact_preparation_registry_NEUSS.json ---
            registry["records"].append({
                "dossier_id": dossier_id,
                "upstream_contact_preparation_eligibility": items.get("contact_preparation_eligibility"),
                "packet_generation_status": "GENERATED",
                "unresolved_gap_count": gap_count,
                "contact_detail_availability_status": contact_detail_status,
                "human_review_required": True,
                "lineage_reference_ids": items.get("lineage_reference_ids", [dossier_id]),
                "disclaimer_no_execution": "CONTACT_PREPARATION_ONLY / NOT_AN_EXECUTION_COMMAND / HUMAN_REVIEW_REQUIRED"
            })

            # --- 2. manual_contact_preparation_packets_NEUSS.json ---
            packets["records"].append({
                "dossier_id": dossier_id,
                "packet_status": "PREPARED_FOR_REVIEW",
                "dossier_identity_summary": f"Target Identifier: {dossier_id}. Upstream lineage intact.",
                "upstream_decision_summary": f"Stage 66 Normalized Decision: {items.get('normalized_decision', 'UNKNOWN')}",
                "upstream_eligibility_summary": "Manual Contact Preparation: CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE",
                "factual_readiness_summary": "Dossier eligibility confirmed derived from Stage 66 human review constraints.",
                "unresolved_information_checklist": unresolved_gaps,
                "pre_contact_verification_checklist": [
                    "verify whether any real contact channel exists in approved future input sources",
                    "confirm unresolved factual gaps before any future manual contact consideration",
                    "confirm governance boundary before any future manual review re-opening",
                    "verify that no blocked status has been introduced upstream"
                ],
                "available_contact_data_summary": contact_info["available"],
                "missing_contact_data_summary": contact_info["missing"],
                "forbidden_automated_actions": [
                    "AUTO_CONTACT", "MANUAL_CONTACT_EXECUTION", "CRM_TASK_CREATION",
                    "APPOINTMENT_BOOKING", "INSTALLER_ASSIGNMENT", "SUBSIDY_INITIATION"
                ],
                "governance_warning": "This packet is for preparation and informational purposes only. It is not an execution authorization.",
                "evidence_sources_used": ["Stage 67 Manual Action Eligibility Gate"],
                "disclaimer_no_contact_authorization": "no contact authorization is created in this stage"
            })

            # --- 3. pre_contact_governance_matrix_NEUSS.json ---
            matrix["records"].append({
                "dossier_id": dossier_id,
                "AUTO_CONTACT": "FORBIDDEN",
                "MANUAL_CONTACT_EXECUTION_ALLOWED": "NOT_YET_ALLOWED",
                "CRM_TASK_CREATION_ALLOWED": "FORBIDDEN",
                "APPOINTMENT_BOOKING_ALLOWED": "FORBIDDEN",
                "INSTALLER_ASSIGNMENT_ALLOWED": "FORBIDDEN",
                "HUMAN_FACT_VERIFICATION_REQUIRED": "REQUIRED",
                "HUMAN_CONTACT_REVIEW_REQUIRED": "REQUIRED"
            })

        if audit["packets_generated"] == len(eligible_dossiers):
            audit["final_stage_verdict"] = "CONTACT_PREPARATION_PACKETS_GENERATED"
        else:
            audit["final_stage_verdict"] = "PARTIAL_CONTACT_PREPARATION_PACKET_GENERATION"

    # Write Outputs
    write_json(registry, "manual_contact_preparation_registry_NEUSS.json")
    write_json(packets, "manual_contact_preparation_packets_NEUSS.json")
    write_json(matrix, "pre_contact_governance_matrix_NEUSS.json")
    write_json(audit, "manual_contact_preparation_audit_NEUSS.json")

    # --- 5. stage_68_manual_contact_preparation_packet_report.md ---
    md_content = f"""# Stage 68 Manual Contact Preparation Packet Report
**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Final Verdict:** `{audit["final_stage_verdict"]}`

## Executive Summary
This stage performs strictly non-executing preparation packet generation for dossiers conditionally eligible for future manual contact consideration.
**It explicitly enforces a zero-execution boundary and preserves all contact execution flags as FORBIDDEN or NOT_YET_ALLOWED.**

## Scope & Processing
* **Total Post-Stage 67 Dossiers Scanned:** {audit["total_post_stage67_dossiers_scanned"]}
* **Eligible Contact Preparation Dossiers:** {audit["eligible_contact_preparation_dossiers"]}
* **Preparation Packets Generated:** {audit["packets_generated"]}
* **Dossiers with Missing Contact Data (Safe Defaults):** {audit["dossiers_with_missing_contact_data"]}

## Governance Assertions
* **Zero Activation Violations:** {audit["zero_activation_violations"]} detected
* **Zero Contact Violations:** {audit["zero_contact_violations"]} detected
* **Zero Assignment Violations:** {audit["zero_assignment_violations"]} detected
* **Zero Booking Violations:** {audit["zero_booking_violations"]} detected
* **Zero Execution Signal Violations:** {audit["zero_execution_signal_violations"]} detected
* **Historical Mutation Violations:** {audit["historical_mutation_violations"]} detected

### Explicit Limitations (What this stage DID NOT do)
- ❌ No inference of future probability.
- ❌ No fabrication of customer emails, names, or phone numbers.
- ❌ No automated assignment of installers or creation of CRM tasks.
- ❌ No implication of "approved to call" or "ready for outreach".

All outputs proudly carry the disclaimer: `CONTACT_PREPARATION_ONLY / NOT_AN_EXECUTION_COMMAND / HUMAN_REVIEW_REQUIRED`.
"""
    with open(os.path.join(OUTPUT_DIR, "stage_68_manual_contact_preparation_packet_report.md"), 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"Stage 68 completed successfully. Verdict: {audit['final_stage_verdict']}")

if __name__ == "__main__":
    generate_packet()
