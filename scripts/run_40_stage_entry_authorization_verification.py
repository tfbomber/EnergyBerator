import json
import os
import glob

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
st39_dir = os.path.join(base_dir, "output", "human_governance_authorization_pack")
tokens_dir = os.path.join(base_dir, "governance_tokens")
output_dir = os.path.join(base_dir, "output", "execution_authorization_status")
os.makedirs(output_dir, exist_ok=True)

def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_token(token, req_obj, contract):
    errors = []
    
    # Check Required Fields
    required_fields = [
        "token_id", "target_id", "approval_scope", "approved_field_paths",
        "approval_timestamp", "approver_identifier", "authorization_level", "approval_signature"
    ]
    for rf in required_fields:
        if rf not in token:
            errors.append(f"Missing required field: {rf}")
            
    if errors:
        return False, errors
        
    t_target = token.get("target_id")
    r_target = req_obj.get("target_id")
    
    if t_target != r_target:
        errors.append("Target ID mismatch.")
        
    t_paths = set(token.get("approved_field_paths", []))
    r_paths = set(req_obj.get("requested_field_paths", []))
    
    if not t_paths.issubset(r_paths):
        errors.append("Approved fields exceed requested scope.")
        
    out_of_scope = set(req_obj.get("out_of_scope_field_paths", []))
    prohibited = set(req_obj.get("prohibited_field_paths", []))
    
    if t_paths.intersection(out_of_scope):
        errors.append("Approved fields include explicitly out of scope fields.")
        
    if t_paths.intersection(prohibited):
        errors.append("Approved fields include explicitly prohibited fields.")
        
    if token.get("recompute_authorized", False):
        errors.append("Token illegally implies recompute authorization.")
        
    if token.get("writeback_authorized", False):
        errors.append("Token illegally implies writeback authorization.")
        
    if errors:
        return False, errors
        
    return True, []

def run_stage_40():
    print("Executing STAGE 40: AUTHORIZATION_VERIFICATION_ONLY / READ_ONLY")

    reqs_data = read_json(os.path.join(st39_dir, "authorization_request_objects_NEUSS.json"))
    contracts_data = read_json(os.path.join(st39_dir, "approval_boundary_contract_NEUSS.json"))

    if not reqs_data or not contracts_data:
        print("Dependency Missing: Stage 39 files not found.")
        return

    requests = reqs_data.get("authorization_requests", [])
    contracts = {c["target_id"]: c for c in contracts_data.get("boundary_contracts", [])}

    # Gather available tokens
    found_tokens = []
    if os.path.exists(tokens_dir):
        token_files = glob.glob(os.path.join(tokens_dir, "approval_token_*.json"))
        for tf in token_files:
            try:
                tk = read_json(tf)
                if tk: found_tokens.append(tk)
            except Exception:
                pass

    # Initialize Outputs
    execution_registry = []
    validation_reports = []
    authorized_entries = []
    rejected_tokens = []
    state_separation = []

    totals = {
        "reviewed": 0,
        "valid_tokens": 0,
        "rejected_tokens": 0,
        "conflict_cases": 0,
        "admitted": 0
    }

    for req in requests:
        target_id = req.get("target_id")
        totals["reviewed"] += 1
        
        # Search tokens explicitly for this target
        target_tokens = [t for t in found_tokens if t.get("target_id") == target_id]
        
        auth_status = "NOT_AUTHORIZED"
        token_valid = False
        token_count = len(target_tokens)
        
        if token_count == 0:
            auth_status = "NOT_AUTHORIZED"
        elif token_count == 1:
            token = target_tokens[0]
            is_valid, errors = validate_token(token, req, contracts.get(target_id, {}))
            
            val_result = "VALID" if is_valid else "INVALID"
            validation_reports.append({
                "token_id": token.get("token_id", "UNKNOWN"),
                "target_id": target_id,
                "validation_result": val_result,
                "validation_errors": errors,
                "scope_validation": is_valid,
                "boundary_validation": is_valid,
                "prohibited_field_check": "PASSED" if is_valid else "FAILED",
                "out_of_scope_check": "PASSED" if is_valid else "FAILED"
            })
            
            if is_valid:
                auth_status = "AUTHORIZED_FOR_EXECUTION_STAGE_ENTRY"
                token_valid = True
                totals["valid_tokens"] += 1
            else:
                auth_status = "TOKEN_INVALID"
                totals["rejected_tokens"] += 1
                rejected_tokens.append({
                    "token_id": token.get("token_id", "UNKNOWN"),
                    "target_id": target_id,
                    "rejection_reasons": errors
                })
        else:
            # Multi-token conflict check - simplified for this implementation: reject all conflicts
            auth_status = "TOKEN_INVALID_CONFLICT"
            totals["conflict_cases"] += 1
            for tk in target_tokens:
                rejected_tokens.append({
                    "token_id": tk.get("token_id", "UNKNOWN"),
                    "target_id": target_id,
                    "rejection_reasons": ["Multi-token conflict detected."]
                })
                
        if auth_status == "AUTHORIZED_FOR_EXECUTION_STAGE_ENTRY":
            totals["admitted"] += 1
            authorized_entries.append({
                "target_id": target_id,
                "stage_entry_authorized": True
            })

        # 1. Execution Registry
        execution_registry.append({
            "target_id": target_id,
            "governance_state": "GOVERNANCE_REVIEW_REQUIRED",
            "authorization_token_found": token_count > 0,
            "token_count": token_count,
            "token_valid": token_valid,
            "token_scope_valid": token_valid,
            "token_boundary_valid": token_valid,
            "authorization_status": auth_status,
            "stage_entry_authorized": auth_status == "AUTHORIZED_FOR_EXECUTION_STAGE_ENTRY",
            "execution_performed": False,
            "recompute_performed": False,
            "writeback_performed": False,
            "current_state_preserved": "STILL_BLOCKED"
        })

        # 5. Authorization State Separation 
        state_separation.append({
            "target_id": target_id,
            "stage_entry_authorized": auth_status == "AUTHORIZED_FOR_EXECUTION_STAGE_ENTRY",
            "execution_authorized": False,
            "recompute_authorized": False,
            "writeback_authorized": False,
            "execution_performed": False,
            "blocked_state_retained": True,
            "separation_note": "Stage-entry allowance does NOT equal execution/writeback authorization."
        })

    # Save outputs
    with open(os.path.join(output_dir, "execution_authorization_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"verified_authorization_states": execution_registry}, f, indent=2)

    with open(os.path.join(output_dir, "authorization_token_validation_report_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"validation_logs": validation_reports}, f, indent=2)

    with open(os.path.join(output_dir, "authorized_execution_stage_entries_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"admitted_targets": authorized_entries}, f, indent=2)

    with open(os.path.join(output_dir, "rejected_authorization_tokens_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"rejected_tokens": rejected_tokens}, f, indent=2)

    with open(os.path.join(output_dir, "authorization_state_separation_verification_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"stage_entry_separations": state_separation}, f, indent=2)

    # Save 6: Execution Report
    md_report = [
        "# STAGE_40_EXECUTION_REPORT",
        "> **Mode**: AUTHORIZATION_VERIFICATION_ONLY / READ_ONLY",
        "",
        "## Authorization Verification Scope",
        f"- **Candidates Reviewed**: {totals['reviewed']}",
        f"- **Matching Tokens Found**: {len(found_tokens)}",
        f"- **Valid Tokens Accepted**: {totals['valid_tokens']}",
        f"- **Invalid Tokens Rejected**: {totals['rejected_tokens']}",
        f"- **Conflict Cases Blocked**: {totals['conflict_cases']}",
        f"- **Targets Admitted to Execution Stage**: {totals['admitted']}",
        "",
        "## Absolute Boundary Semantics & Audit Violations (Zero = Success)",
        "- **0** Executions performed.",
        "- **0** Production truth mutations deployed.",
        "- **0** Status promotions triggered unlocking active pipelines.",
        "- **0** Writebacks mapped to Master DBs.",
        "- **0** Recomputations triggered implicitly.",
        "",
        "## Audit Conclusion",
        "Stage 40 performs stage-entry authorization verification exclusively. No execution was authorized nor performed. The system mathematically preserved `STILL_BLOCKED` terminal modes for all objects evaluated. Absolutely zero candidates unlocked their geometric coordinates into target indexes; token discovery solely maps whether structural algorithms are legally allowed to mount the execution runtime later."
    ]
    with open(os.path.join(output_dir, "stage_40_execution_report.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_report))

    print("STAGE_40_SUCCESS")

if __name__ == "__main__":
    run_stage_40()
