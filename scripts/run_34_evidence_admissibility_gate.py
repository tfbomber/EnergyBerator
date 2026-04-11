import json
import os

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
structural_dir = os.path.join(base_dir, "output", "evidence_structural_validation")
output_dir = os.path.join(base_dir, "output", "evidence_admissibility")
os.makedirs(output_dir, exist_ok=True)

AUTHORIZED_SOURCES = ["OpenStreetMap", "MaStR", "Kataster", "SWN", "Reviewer_Direct"]
AUTHORIZED_SCHEMAS = ["1.0"]

def run_stage_34():
    print("Executing ADMISSIBILITY_ONLY - Admissibility Gates")

    registry = []
    source_audit = []
    verdicts = {}
    quarantine = []
    
    totals = {
        "assessed": 0,
        "ADMISSIBLE": 0,
        "REJECTED": 0
    }

    verdict_matrix_path = os.path.join(structural_dir, "structural_verdict_matrix_NEUSS.json")
    if not os.path.exists(verdict_matrix_path):
        print("Dependency Missing: structural_verdict_matrix_NEUSS.json not found.")
        return

    with open(verdict_matrix_path, "r", encoding="utf-8") as f:
        structural_verdicts = json.load(f).get("verdicts", {})

    for fpath, s_verdict in structural_verdicts.items():
        if s_verdict != "STRUCTURALLY_VALID":
            continue

        totals["assessed"] += 1
        registry.append(fpath)
        
        # Load the raw payload using ADMISSIBILITY_ONLY semantics (Read-Only)
        with open(fpath, "r", encoding="utf-8") as raw_f:
            payload = json.load(raw_f)
            
        metadata = payload.get("evidence_metadata", {})
        
        src = metadata.get("evidence_source", "UNKNOWN")
        schema_v = metadata.get("schema_version", "UNKNOWN")
        obs_date = metadata.get("observation_date")
        acq_date = metadata.get("acquisition_timestamp")

        # 1. Source Authority Check
        source_approved = src in AUTHORIZED_SOURCES
        source_audit.append({
            "file": fpath,
            "declared_source": src,
            "source_authorized": source_approved
        })

        # Admissibility Determinism
        if not source_approved:
            verdicts[fpath] = "REJECTED"
            quarantine.append({"file": fpath, "reason": "UNAUTHORIZED_SOURCE_ORIGIN"})
            totals["REJECTED"] += 1
            continue
            
        if schema_v not in AUTHORIZED_SCHEMAS:
            verdicts[fpath] = "REJECTED"
            quarantine.append({"file": fpath, "reason": "UNSUPPORTED_SCHEMA_VERSION"})
            totals["REJECTED"] += 1
            continue

        if not obs_date or not acq_date:
            verdicts[fpath] = "REJECTED"
            quarantine.append({"file": fpath, "reason": "TEMPORAL_ADMISSIBILITY_FAILED_MISSING_DATES"})
            totals["REJECTED"] += 1
            continue

        # Passes absolute deterministic origin contracts. No spatial evaluations or inferences invoked.
        verdicts[fpath] = "ADMISSIBLE"
        totals["ADMISSIBLE"] += 1


    # Save 1: Registry
    with open(os.path.join(output_dir, "admissibility_evaluation_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"evaluated_artifacts": registry}, f, indent=2)

    # Save 2: Source Authority Audit
    with open(os.path.join(output_dir, "source_authority_audit_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"source_authority_checks": source_audit}, f, indent=2)

    # Save 3: Admissibility Verdicts
    with open(os.path.join(output_dir, "evidence_admissibility_verdicts_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"admissibility_verdicts": verdicts}, f, indent=2)

    # Save 4: Quarantine
    with open(os.path.join(output_dir, "rejected_evidence_quarantine_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"rejected_payloads": quarantine}, f, indent=2)

    # Save 5: Non-Activation Assertions
    assertions = {
        "mode": "ADMISSIBILITY_ONLY",
        "spatial_mapping_performed": False,
        "segment_mapping_performed": False,
        "candidate_matching_performed": False,
        "sufficiency_judged": False,
        "integration_readiness_assessed": False,
        "recompute_logic_triggered": False,
        "business_mutation_occurred": False,
        "assertion": "The pipeline explicitly assigned ADMISSIBLE tracking limits via determinism over explicit origin properties. Zero inference injected. Zero candidate mappings unlocked."
    }
    with open(os.path.join(output_dir, "admissibility_non_activation_assertions_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump(assertions, f, indent=2)

    # Save 6: Execution Report
    md_report = [
        "# STAGE_34_EXECUTION_REPORT",
        "> **Mode**: ADMISSIBILITY_ONLY (Read-Only Determinism)\n",
        "## Evaluation Scope",
        f"- **STRUCTURALLY_VALID Targets Assessed**: {totals['assessed']}\n",
        "## Admissibility Verdicts",
        f"- **ADMISSIBLE**: {totals['ADMISSIBLE']}",
        f"- **REJECTED**: {totals['REJECTED']}\n",
        "## Absolute Boundary Semantics",
        "- **0** Extracted metadata values normalized or inferred through proxy injections.",
        "- **0** Geographic Spatial Joins applied to underlying coordinate payloads.",
        "- **0** Candidate / Business states mutated (Artifacts remain entirely dormant in cache).",
        "- Structural validity successfully detached from 'admissibility guarantees' (Only Explicit Origins survive)."
    ]
    with open(os.path.join(output_dir, "stage_34_execution_report.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_report))

    print("STAGE_34_SUCCESS")

if __name__ == "__main__":
    run_stage_34()
