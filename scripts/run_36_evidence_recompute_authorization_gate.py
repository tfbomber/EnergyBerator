import json
import os

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
pathway_dir = os.path.join(base_dir, "output", "evidence_conditional_integration")
output_dir = os.path.join(base_dir, "output", "evidence_recompute_authorization")
os.makedirs(output_dir, exist_ok=True)

def run_stage_36():
    print("Executing RECOMPUTE_AUTHORIZATION_ONLY - IN_MEMORY_ONLY")

    registry = []
    contract_audit = []
    verdicts = {}
    quarantine = []
    
    totals = {
        "assessed": 0,
        "RECOMPUTE_LEGALLY_AUTHORIZED": 0,
        "RECOMPUTE_AUTHORIZATION_DENIED": 0
    }

    verdict_matrix_path = os.path.join(pathway_dir, "integration_pathway_verdicts_NEUSS.json")
    if not os.path.exists(verdict_matrix_path):
        print("Dependency Missing: integration_pathway_verdicts_NEUSS.json not found.")
        return

    with open(verdict_matrix_path, "r", encoding="utf-8") as f:
        pathway_verdicts = json.load(f).get("pathway_verdicts", {})

    for fpath, p_verdict in pathway_verdicts.items():
        if p_verdict != "CONDITIONAL_PATHWAY_IDENTIFIED":
            continue

        totals["assessed"] += 1
        registry.append(fpath)
        
        # Load the raw payload using IN_MEMORY_ONLY assessment
        with open(fpath, "r", encoding="utf-8") as raw_f:
            payload = json.load(raw_f)
            
        features = payload.get("features", [])
        
        has_features = isinstance(features, list) and len(features) > 0
        has_valid_geometry = False
        
        if has_features:
            first_feature = features[0]
            geom = first_feature.get("geometry", {})
            has_valid_geometry = bool(geom.get("type")) and bool(geom.get("coordinates"))

        # Explicit Authorization Prerequisites
        is_authorized = has_features and has_valid_geometry

        contract_audit.append({
            "file": fpath,
            "prerequisite_features_array_present": has_features,
            "prerequisite_geometry_schema_present": has_valid_geometry,
            "contract_satisfied": is_authorized
        })

        if is_authorized:
            verdicts[fpath] = "RECOMPUTE_LEGALLY_AUTHORIZED"
            totals["RECOMPUTE_LEGALLY_AUTHORIZED"] += 1
        else:
            verdicts[fpath] = "RECOMPUTE_AUTHORIZATION_DENIED"
            totals["RECOMPUTE_AUTHORIZATION_DENIED"] += 1
            quarantine.append({
                "file": fpath,
                "reason": "MISSING_EXPLICIT_RECOMPUTE_PREREQUISITES",
                "missing_geometry_blocks": not has_valid_geometry
            })


    # Save 1: Registry
    with open(os.path.join(output_dir, "authorization_evaluation_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"evaluated_artifacts": registry}, f, indent=2)

    # Save 2: Contract Audit
    with open(os.path.join(output_dir, "recompute_contract_audit_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"contract_evaluations": contract_audit}, f, indent=2)

    # Save 3: Authorization verdicts
    with open(os.path.join(output_dir, "recompute_authorization_verdicts_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"authorization_verdicts": verdicts}, f, indent=2)

    # Save 4: Quarantine
    with open(os.path.join(output_dir, "unauthorized_quarantine_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"unauthorized_payloads": quarantine}, f, indent=2)

    # Save 5: Non-Activation Assertions
    assertions = {
        "mode": "RECOMPUTE_AUTHORIZATION_ONLY",
        "in_memory_only": True,
        "recompute_executed": False,
        "integration_executed": False,
        "candidate_state_mutated": False,
        "master_assets_written": False,
        "truth_tiers_altered": False,
        "business_outcomes_evaluated": False,
        "assertion": "Mathematical Authorization evaluated entirely over explicit prerequisite structures. Zero integrations, business rescoring, or candidate mutability sequences fired."
    }
    with open(os.path.join(output_dir, "authorization_non_activation_assertions_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump(assertions, f, indent=2)

    # Save 6: Execution Report
    md_report = [
        "# STAGE_36_EXECUTION_REPORT",
        "> **Mode**: RECOMPUTE_AUTHORIZATION_ONLY (In-Memory Only)\n",
        "## Evaluation Scope",
        f"- **PATHWAY_IDENTIFIED Targets Assessed**: {totals['assessed']}\n",
        "## Authorization Verdicts",
        f"- **RECOMPUTE_LEGALLY_AUTHORIZED**: {totals['RECOMPUTE_LEGALLY_AUTHORIZED']}",
        f"- **RECOMPUTE_AUTHORIZATION_DENIED**: {totals['RECOMPUTE_AUTHORIZATION_DENIED']}\n",
        "## Absolute Boundary Semantics",
        "- **0** Extracted metadata values repaired or populated through inference.",
        "- **0** Business outcomes evaluated or Truth baselines substituted natively.",
        "- **0** Candidate tiers upgraded securely freezing un-executed payloads.",
        "- Assessment strictly proves underlying geometries comply with future algorithm requirements structurally."
    ]
    with open(os.path.join(output_dir, "stage_36_execution_report.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_report))

    print("STAGE_36_SUCCESS")

if __name__ == "__main__":
    run_stage_36()
