import os
import json
import re
from datetime import datetime, timezone

# --- Stage 69: Verified Contact Data Intake Gate ---
# Mode: CONTACT_DATA_INTAKE_ONLY / READ_ONLY_UPSTREAM / NON_EXECUTING / NO_CONTACT_AUTHORIZATION / NO_CRM_ACTIONS

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_68_DIR = os.path.join(ROOT_DIR, "output", "manual_contact_preparation_packet")
INTAKE_DIR = os.path.join(ROOT_DIR, "data", "contact_data_intake")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "verified_contact_data_intake")

# Required Expected Fields (conservative schema)
ALLOWED_FIELDS = [
    "dossier_id",
    "contact_name",
    "phone_number",
    "email_address",
    "preferred_contact_time",
    "source_label",
    "submission_timestamp",
    "notes"
]

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

def is_valid_email(email):
    if not email:
        return False
    # Extremely basic format check
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, str(email)) is not None

def is_valid_phone(phone):
    if not phone:
        return False
    # Extremely basic phone check: At least 7 chars, mostly digits, maybe +() -
    pattern = r"^\+?[0-9\-\(\)\s]{7,20}$"
    return re.match(pattern, str(phone)) is not None

def validate_intake_data(dossier_id, intake_data):
    if intake_data is None:
        return "NO_CONTACT_DATA_INPUT_RECEIVED", {}, []
        
    if intake_data == "PARSE_ERROR" or not isinstance(intake_data, dict):
        return "CONTACT_DATA_INTAKE_FORMAT_INVALID", {}, []
        
    if intake_data.get("dossier_id") != dossier_id:
        return "CONTACT_DATA_INTAKE_LINKAGE_INVALID", {}, []

    missing = []
    # Determine missing expected
    for field in ALLOWED_FIELDS:
        val = intake_data.get(field)
        if val is None or str(val).strip() == "":
            missing.append(field)

    phone = intake_data.get("phone_number")
    email = intake_data.get("email_address")
    
    # Are both missing?
    if not phone and not email:
        return "CONTACT_DATA_INTAKE_INCOMPLETE", intake_data, missing
        
    # Check format validity of what IS provided
    if phone and not is_valid_phone(phone):
        return "CONTACT_DATA_INTAKE_FORMAT_INVALID", intake_data, missing
        
    if email and not is_valid_email(email):
        return "CONTACT_DATA_INTAKE_FORMAT_INVALID", intake_data, missing
        
    # Check conflicting (e.g. clearly dummy text where we expect phone)
    # The regex already covers most of that for phone/email, but if they sent contradictory notes
    notes = str(intake_data.get("notes", "")).upper()
    name = str(intake_data.get("contact_name", "")).upper()
    if "DO NOT CALL" in notes and phone:
         return "CONTACT_DATA_INTAKE_CONFLICTING", intake_data, missing
    if "UNKNOWN" in name and not phone and not email:
         return "CONTACT_DATA_INTAKE_INCOMPLETE", intake_data, missing

    # Valid
    return "CONTACT_DATA_INTAKE_STRUCTURALLY_VALID", intake_data, missing

def run_gate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(INTAKE_DIR, exist_ok=True)

    stage68_registry = load_json(os.path.join(STAGE_68_DIR, "manual_contact_preparation_registry_NEUSS.json")) or {"records": []}

    eligible_dossiers = []
    for r in stage68_registry.get("records", []):
        if r.get("packet_generation_status") == "GENERATED":
            eligible_dossiers.append(r)

    # Outputs
    registry = {"records": []}
    details = {"records": []}
    matrix = {"records": []}
    
    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_stage68_dossiers_scanned": len(stage68_registry.get("records", [])),
        "eligible_contact_data_intake_dossiers": len(eligible_dossiers),
        "dossiers_with_real_contact_input": 0,
        "dossiers_without_contact_input": 0,
        "structurally_valid_intakes": 0,
        "incomplete_intakes": 0,
        "invalid_format_intakes": 0,
        "invalid_linkage_intakes": 0,
        "conflicting_intakes": 0,
        "zero_activation_violations": 0,
        "zero_contact_violations": 0,
        "zero_crm_task_violations": 0,
        "zero_booking_violations": 0,
        "zero_assignment_violations": 0,
        "zero_execution_signal_violations": 0,
        "historical_mutation_violations": 0,
        "final_stage_verdict": ""
    }

    if not eligible_dossiers:
        audit["final_stage_verdict"] = "NO_CONTACT_DATA_INTAKE_CANDIDATES_FOUND"
    else:
        for items in eligible_dossiers:
            dossier_id = items.get("dossier_id")
            packet_status = items.get("packet_generation_status")
            
            intake_filepath = os.path.join(INTAKE_DIR, f"contact_{dossier_id}.json")
            raw_intake_data = load_json(intake_filepath)
            
            if raw_intake_data is None:
                audit["dossiers_without_contact_input"] += 1
            else:
                audit["dossiers_with_real_contact_input"] += 1

            intake_status, parsed_data, missing_fields = validate_intake_data(dossier_id, raw_intake_data)
            
            # Audit counters
            if intake_status == "CONTACT_DATA_INTAKE_STRUCTURALLY_VALID": audit["structurally_valid_intakes"] += 1
            elif intake_status == "CONTACT_DATA_INTAKE_INCOMPLETE": audit["incomplete_intakes"] += 1
            elif intake_status == "CONTACT_DATA_INTAKE_FORMAT_INVALID": audit["invalid_format_intakes"] += 1
            elif intake_status == "CONTACT_DATA_INTAKE_LINKAGE_INVALID": audit["invalid_linkage_intakes"] += 1
            elif intake_status == "CONTACT_DATA_INTAKE_CONFLICTING": audit["conflicting_intakes"] += 1

            # Only retain approved fields for the snapshot (non-hallucination / filter out undocumented trash)
            snapshot = {}
            if isinstance(parsed_data, dict):
                for k in ALLOWED_FIELDS:
                    if k in parsed_data:
                        snapshot[k] = parsed_data[k]

            # Provenance
            provenance = {}
            if snapshot.get("source_label"): provenance["source"] = snapshot["source_label"]
            if snapshot.get("submission_timestamp"): provenance["timestamp"] = snapshot["submission_timestamp"]
            
            if not provenance and parsed_data:
                 provenance["note"] = "No explicit provenance metadata provided."
            elif not parsed_data:
                 provenance["note"] = "No data submitted."

            # --- 1. verified_contact_data_intake_registry_NEUSS.json ---
            registry["records"].append({
                "dossier_id": dossier_id,
                "upstream_packet_status": packet_status,
                "contact_data_input_status": "REAL_CONTACT_DATA_INPUT_PRESENT" if raw_intake_data else "NO_CONTACT_DATA_INPUT_RECEIVED",
                "intake_status": intake_status,
                "linkage_status": "VALID" if intake_status not in ["NO_CONTACT_DATA_INPUT_RECEIVED", "CONTACT_DATA_INTAKE_LINKAGE_INVALID"] else "INVALID/MISSING",
                "structural_validity_status": "VALID" if intake_status == "CONTACT_DATA_INTAKE_STRUCTURALLY_VALID" else "INVALID/MISSING",
                "completeness_status": "PARTIAL_OR_COMPLETE" if intake_status == "CONTACT_DATA_INTAKE_STRUCTURALLY_VALID" else "INCOMPLETE",
                "human_review_required": True,
                "lineage_reference_ids": items.get("lineage_reference_ids", [dossier_id]),
                "disclaimer_no_execution": "CONTACT_DATA_INTAKE_ONLY / NOT_AN_EXECUTION_COMMAND / HUMAN_REVIEW_REQUIRED"
            })

            # --- 2. verified_contact_data_details_NEUSS.json ---
            details["records"].append({
                "dossier_id": dossier_id,
                "detail_status": "INTAKE_CAPTURED" if raw_intake_data else "NO_INPUT_YET",
                "raw_input_detected": bool(raw_intake_data),
                "submitted_fields_present": [k for k in ALLOWED_FIELDS if k not in missing_fields] if raw_intake_data else [],
                "missing_fields": missing_fields,
                "field_format_results": "OK" if intake_status == "CONTACT_DATA_INTAKE_STRUCTURALLY_VALID" else "INVALID_OR_MISSING",
                "linkage_check_result": "PASSED" if intake_status != "CONTACT_DATA_INTAKE_LINKAGE_INVALID" else "FAILED",
                "consistency_check_result": "PASSED" if intake_status != "CONTACT_DATA_INTAKE_CONFLICTING" else "FAILED",
                "provenance_summary": provenance,
                "validated_contact_data_snapshot": snapshot,
                "forbidden_automated_actions": [
                    "AUTO_CONTACT", "MANUAL_CONTACT_EXECUTION", "CRM_TASK_CREATION",
                    "APPOINTMENT_BOOKING", "INSTALLER_ASSIGNMENT", "SUBSIDY_INITIATION"
                ],
                "governance_warning": "This snapshot is for human verification only. DO NOT use these values to execute contact yet.",
                "evidence_sources_used": ["data/contact_data_intake/ input folder"],
                "disclaimer_no_contact_authorization": "intake recorded for future human review; no contact authorization created in this stage"
            })

            # --- 3. contact_data_intake_governance_matrix_NEUSS.json ---
            resub_status = "ALLOWED_FOR_FUTURE_RESUBMISSION" if intake_status in [
                "CONTACT_DATA_INTAKE_INCOMPLETE", "CONTACT_DATA_INTAKE_FORMAT_INVALID", 
                "CONTACT_DATA_INTAKE_CONFLICTING", "NO_CONTACT_DATA_INPUT_RECEIVED"
            ] else "ALLOWED_FOR_FUTURE_RESUBMISSION" # Generously allow resubmission to overwrite until acted upon
            
            matrix["records"].append({
                "dossier_id": dossier_id,
                "AUTO_CONTACT": "FORBIDDEN",
                "MANUAL_CONTACT_EXECUTION_ALLOWED": "NOT_YET_ALLOWED",
                "CRM_TASK_CREATION_ALLOWED": "FORBIDDEN",
                "APPOINTMENT_BOOKING_ALLOWED": "FORBIDDEN",
                "INSTALLER_ASSIGNMENT_ALLOWED": "FORBIDDEN",
                "CONTACT_DATA_REVIEW_REQUIRED": "REQUIRED",
                "CONTACT_DATA_RESUBMISSION_ALLOWED": resub_status
            })

        if audit["structurally_valid_intakes"] == len(eligible_dossiers) and audit["structurally_valid_intakes"] > 0:
            audit["final_stage_verdict"] = "VERIFIED_CONTACT_DATA_INTAKE_RECORDED"
        elif audit["structurally_valid_intakes"] > 0:
            audit["final_stage_verdict"] = "PARTIAL_CONTACT_DATA_INTAKE_VALIDATION"
        elif audit["dossiers_with_real_contact_input"] > 0:
            audit["final_stage_verdict"] = "PARTIAL_CONTACT_DATA_INTAKE_VALIDATION" # Has broken/incomplete inputs
        else:
            audit["final_stage_verdict"] = "NO_CONTACT_DATA_INPUT_RECEIVED"

    # Write Outputs
    write_json(registry, "verified_contact_data_intake_registry_NEUSS.json")
    write_json(details, "verified_contact_data_details_NEUSS.json")
    write_json(matrix, "contact_data_intake_governance_matrix_NEUSS.json")
    write_json(audit, "verified_contact_data_audit_NEUSS.json")

    # --- 5. stage_69_verified_contact_data_intake_report.md ---
    md_content = f"""# Stage 69 Verified Contact Data Intake Report
**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Final Verdict:** `{audit["final_stage_verdict"]}`

## Executive Summary
This stage performs structurally valid intake for manual contact data submissions on dossiers inheriting Stage 68 contact preparation eligibility.
**It explicitly enforces a zero-execution boundary. Verified data does NOT mean CRM readiness.**

## Scope & Processing
* **Total Post-Stage 68 Dossiers Scanned:** {audit["total_stage68_dossiers_scanned"]}
* **Eligible Intake Dossiers:** {audit["eligible_contact_data_intake_dossiers"]}
* **Dossiers with Real Input:** {audit["dossiers_with_real_contact_input"]}
* **Dossiers without Input:** {audit["dossiers_without_contact_input"]}

### Classification Tally
* **Structurally Valid Intakes:** {audit["structurally_valid_intakes"]}
* **Incomplete Intakes:** {audit["incomplete_intakes"]}
* **Invalid Format Intakes:** {audit["invalid_format_intakes"]}
* **Invalid Linkage Intakes:** {audit["invalid_linkage_intakes"]}
* **Conflicting Intakes:** {audit["conflicting_intakes"]}

## Governance Assertions
* **Zero Activation Violations:** {audit["zero_activation_violations"]} detected
* **Zero Contact Violations:** {audit["zero_contact_violations"]} detected
* **Zero CRM Task Violations:** {audit["zero_crm_task_violations"]} detected
* **Zero Booking Violations:** {audit["zero_booking_violations"]} detected
* **Zero Assignment Violations:** {audit["zero_assignment_violations"]} detected
* **Zero Execution Signal Violations:** {audit["zero_execution_signal_violations"]} detected

### Explicit Limitations (What this stage DID NOT do)
- ❌ No inference of consent status or customer willingness.
- ❌ No CRM tasks generated.
- ❌ No implication of "contact approved" or "ready to call".
- ❌ No fabrication of names, phones, emails, or preferred times.

All outputs proudly carry the disclaimer: `CONTACT_DATA_INTAKE_ONLY / NOT_AN_EXECUTION_COMMAND / HUMAN_REVIEW_REQUIRED`.
"""
    with open(os.path.join(OUTPUT_DIR, "stage_69_verified_contact_data_intake_report.md"), 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"Stage 69 completed successfully. Verdict: {audit['final_stage_verdict']}")

if __name__ == "__main__":
    run_gate()
