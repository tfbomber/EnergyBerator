import json
import os
import glob
from collections import defaultdict

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
st39_dir = os.path.join(base_dir, "output", "human_governance_authorization_pack")
tokens_dir = os.path.join(base_dir, "governance_tokens")
output_dir = os.path.join(base_dir, "output", "token_intake_registry")
os.makedirs(output_dir, exist_ok=True)

def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_stage_41():
    print("Executing STAGE 41: TOKEN_INTAKE_ONLY")

    # Read Stage 39 Requests
    reqs_data = read_json(os.path.join(st39_dir, "authorization_request_objects_NEUSS.json"))
    valid_target_ids = []
    if reqs_data:
        requests = reqs_data.get("authorization_requests", [])
        valid_target_ids = [r.get("target_id") for r in requests]

    # Gather available tokens
    token_files = []
    if os.path.exists(tokens_dir):
        token_files = glob.glob(os.path.join(tokens_dir, "approval_token_*.json"))

    # Initialize Outputs
    intake_registry = []
    structure_audit = []
    unmatched_invalid = []
    readiness = []
    
    target_token_map = defaultdict(list)

    totals = {
        "detected": len(token_files),
        "readable": 0,
        "structurally_invalid": 0,
        "schema_invalid": 0,
        "unmatched": 0,
        "registered": 0
    }

    # First Pass: Structural and Schema Checking
    for tf in token_files:
        filename = os.path.basename(tf)
        token_id = "UNKNOWN"
        target_id = "UNKNOWN"
        is_readable = False
        
        try:
            with open(tf, "r", encoding="utf-8") as f:
                token_data = json.load(f)
            is_readable = True
            token_id = token_data.get("token_id", "UNKNOWN")
            target_id = token_data.get("target_id", "UNKNOWN")
        except Exception:
            token_data = None
            
        if not is_readable:
            totals["structurally_invalid"] += 1
            audit_res = {
                "token_filename": filename,
                "token_id": "UNKNOWN",
                "missing_fields": ["ALL"],
                "malformed_fields": ["FILE_UNREADABLE"],
                "schema_issues": ["JSON parse failed"],
                "structure_result": "FAILED"
            }
            structure_audit.append(audit_res)
            
            unmatched_invalid.append({
                "token_filename": filename,
                "token_id": "UNKNOWN",
                "registry_status": "STRUCTURALLY_INVALID",
                "reasons": ["File unreadable or JSON parse failed"]
            })
            
            intake_registry.append({
                "token_filename": filename,
                "token_id": "UNKNOWN",
                "target_id": "UNKNOWN",
                "json_readable": False,
                "required_fields_present": False,
                "schema_valid": False,
                "target_match_found": False,
                "duplicate_target_token": False,
                "registry_status": "STRUCTURALLY_INVALID",
                "intake_eligible_for_stage40": False,
                "registration_note": "Unreadable file."
            })
            continue

        totals["readable"] += 1
        
        # Check Required Fields
        required_fields = [
            "token_id", "target_id", "approval_scope", "approved_field_paths",
            "approval_timestamp", "approver_identifier", "authorization_level", "approval_signature"
        ]
        
        missing = [rf for rf in required_fields if rf not in token_data]
        
        if missing:
            totals["structurally_invalid"] += 1
            structure_audit.append({
                "token_filename": filename,
                "token_id": token_id,
                "missing_fields": missing,
                "malformed_fields": [],
                "schema_issues": ["Missing required structural fields"],
                "structure_result": "FAILED"
            })
            
            unmatched_invalid.append({
                "token_filename": filename,
                "token_id": token_id,
                "registry_status": "STRUCTURALLY_INVALID",
                "reasons": [f"Missing fields: {missing}"]
            })
            
            intake_registry.append({
                "token_filename": filename,
                "token_id": token_id,
                "target_id": target_id,
                "json_readable": True,
                "required_fields_present": False,
                "schema_valid": False,
                "target_match_found": False,
                "duplicate_target_token": False,
                "registry_status": "STRUCTURALLY_INVALID",
                "intake_eligible_for_stage40": False,
                "registration_note": "Required fields missing."
            })
            continue
            
        # Basic Schema Sanity Check
        schema_issues = []
        if not isinstance(token_data.get("token_id"), str): schema_issues.append("token_id not string")
        if not isinstance(token_data.get("target_id"), str): schema_issues.append("target_id not string")
        if not isinstance(token_data.get("approval_scope"), (str, dict)): schema_issues.append("approval_scope wrong type")
        if not isinstance(token_data.get("approved_field_paths"), list): schema_issues.append("approved_field_paths not array")
        if not isinstance(token_data.get("approval_timestamp"), str): schema_issues.append("approval_timestamp not string")
        if not isinstance(token_data.get("approver_identifier"), str): schema_issues.append("approver_identifier not string")
        if not isinstance(token_data.get("authorization_level"), str): schema_issues.append("authorization_level not string")
        if token_data.get("approval_signature") is None: schema_issues.append("approval_signature is null")
        
        if schema_issues:
            totals["schema_invalid"] += 1
            structure_audit.append({
                "token_filename": filename,
                "token_id": token_id,
                "missing_fields": [],
                "malformed_fields": schema_issues,
                "schema_issues": ["Type checking failed"],
                "structure_result": "FAILED"
            })
            
            unmatched_invalid.append({
                "token_filename": filename,
                "token_id": token_id,
                "registry_status": "SCHEMA_INVALID",
                "reasons": schema_issues
            })
            
            intake_registry.append({
                "token_filename": filename,
                "token_id": token_id,
                "target_id": target_id,
                "json_readable": True,
                "required_fields_present": True,
                "schema_valid": False,
                "target_match_found": False,
                "duplicate_target_token": False,
                "registry_status": "SCHEMA_INVALID",
                "intake_eligible_for_stage40": False,
                "registration_note": "Schema sanity check failed."
            })
            continue
        
        # Target Match Check
        if target_id not in valid_target_ids:
            totals["unmatched"] += 1
            structure_audit.append({
                "token_filename": filename,
                "token_id": token_id,
                "missing_fields": [],
                "malformed_fields": [],
                "schema_issues": [],
                "structure_result": "PASSED"
            })
            
            unmatched_invalid.append({
                "token_filename": filename,
                "token_id": token_id,
                "registry_status": "UNMATCHED_TARGET",
                "reasons": ["Target ID does not match any Stage 39 authorization request"]
            })
            
            intake_registry.append({
                "token_filename": filename,
                "token_id": token_id,
                "target_id": target_id,
                "json_readable": True,
                "required_fields_present": True,
                "schema_valid": True,
                "target_match_found": False,
                "duplicate_target_token": False,
                "registry_status": "UNMATCHED_TARGET",
                "intake_eligible_for_stage40": False,
                "registration_note": "Target ID unknown."
            })
            continue
            
        # Passed primary checks, map for duplicate resolution
        target_token_map[target_id].append({
            "filename": filename,
            "token_id": token_id
        })

    # Second Pass: Duplicate Resolution and Final Registration
    duplicate_registry = []
    
    for target_id, tokens in target_token_map.items():
        is_duplicate = len(tokens) > 1
        reg_status = "DUPLICATE_TARGET_TOKEN" if is_duplicate else "REGISTERED_PENDING_STAGE40_VERIFICATION"
        
        if is_duplicate:
            duplicate_registry.append({
                "target_id": target_id,
                "token_filenames": [t["filename"] for t in tokens],
                "token_ids": [t["token_id"] for t in tokens],
                "duplicate_count": len(tokens),
                "conflict_resolution_deferred_to_stage40": True
            })
            
        for t in tokens:
            totals["registered"] += 1
            
            structure_audit.append({
                "token_filename": t["filename"],
                "token_id": t["token_id"],
                "missing_fields": [],
                "malformed_fields": [],
                "schema_issues": [],
                "structure_result": "PASSED"
            })
            
            intake_registry.append({
                "token_filename": t["filename"],
                "token_id": t["token_id"],
                "target_id": target_id,
                "json_readable": True,
                "required_fields_present": True,
                "schema_valid": True,
                "target_match_found": True,
                "duplicate_target_token": is_duplicate,
                "registry_status": reg_status,
                "intake_eligible_for_stage40": reg_status == "REGISTERED_PENDING_STAGE40_VERIFICATION",
                "registration_note": "Successfully ingested." if not is_duplicate else "Duplicate detected, deferred resolution."
            })
            
            readiness.append({
                "token_id": t["token_id"],
                "target_id": target_id,
                "registry_status": reg_status,
                "intake_eligible_for_stage40": reg_status == "REGISTERED_PENDING_STAGE40_VERIFICATION",
                "readiness_note": "Ready for verification pass." if not is_duplicate else "Duplicate requires resolution prior to verification."
            })

    # Save outputs
    with open(os.path.join(output_dir, "token_intake_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"token_intake": intake_registry}, f, indent=2)

    with open(os.path.join(output_dir, "token_structure_audit_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"structure_audits": structure_audit}, f, indent=2)

    with open(os.path.join(output_dir, "unmatched_or_invalid_tokens_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"invalid_tokens": unmatched_invalid}, f, indent=2)

    with open(os.path.join(output_dir, "duplicate_target_token_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"duplicate_targets": duplicate_registry}, f, indent=2)

    with open(os.path.join(output_dir, "token_stage40_readiness_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"stage40_readiness": readiness}, f, indent=2)

    # Save 6: Summary MD
    num_duplicates = len([r for r in intake_registry if r.get("registry_status") == "DUPLICATE_TARGET_TOKEN"])
    num_registered = len([r for r in intake_registry if r.get("registry_status") == "REGISTERED_PENDING_STAGE40_VERIFICATION"])
    
    md_summary = [
        "# STAGE 41: TOKEN INTAKE SUMMARY",
        "",
        f"- **Tokens Detected**: {totals['detected']}",
        f"- **Readable JSON Tokens**: {totals['readable']}",
        f"- **Structurally Invalid**: {totals['structurally_invalid']}",
        f"- **Schema Invalid**: {totals['schema_invalid']}",
        f"- **Unmatched Targets**: {totals['unmatched']}",
        f"- **Duplicate-Target Tokens**: {num_duplicates}",
        f"- **Registered for Stage 40 Validation**: {num_registered}",
        "",
        "- **Approvals Granted**: 0",
        "- **Executions Performed**: 0"
    ]
    with open(os.path.join(output_dir, "token_intake_summary_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_summary))
        
    # Save 7: Execution Report MD
    md_report = [
        "# STAGE_41_EXECUTION_REPORT",
        "> **Mode**: TOKEN_INTAKE_ONLY / NO_AUTHORIZATION_DECISION",
        "",
        "## Intake Pipeline Objectives",
        "Stage 41 structurally validates all `approval_token_*.json` payloads. It purely ensures JSON parity mapping to Stage 39 bounds.",
        "",
        "## Validation Metrics",
        f"- **Token Files Scanned**: {totals['detected']}",
        f"- **Registry Outcomes Validated**: {num_registered}",
        "",
        "## Absolute Boundary Semantics & Audit Violations (Zero = Success)",
        "- **0** Production mutations executed.",
        "- **0** Authorizations granted (`intake_eligible` does not equal token authorization).",
        "- **0** Pseudo executables ran via external bounds.",
        "",
        "## Audit Conclusion",
        "Stage 41 performs token intake and registration only. No authorization decision was made. No approval was simulated. No execution was performed. No production truth was mutated. No blocked-state control was changed. All targets remain `STILL_BLOCKED`. Final authorization, if any, must still be determined in a later Stage 40 verification pass."
    ]
    with open(os.path.join(output_dir, "stage_41_execution_report.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_report))

    print("STAGE_41_SUCCESS")

if __name__ == "__main__":
    run_stage_41()
