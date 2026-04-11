import json
import os

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
dropzone_dir = os.path.join(base_dir, "data", "external_evidence")
output_dir = os.path.join(base_dir, "output", "evidence_structural_validation")
os.makedirs(output_dir, exist_ok=True)

MANDATORY_METADATA_FIELDS = [
    "evidence_source", "evidence_class", "city", "segment_binding",
    "observation_date", "acquisition_timestamp", "lineage_anchor",
    "schema_version", "artifact_identifier"
]

def run_stage_33():
    print("Executing VALIDATION_ONLY - Structural Integrity Pass")

    registry = []
    schema_presence = []
    metadata_integrity = []
    lineage_integrity = []
    malformed = []
    verdicts = {}
    
    totals = {
        "scanned": 0,
        "STRUCTURALLY_VALID": 0,
        "STRUCTURALLY_INCOMPLETE": 0,
        "MALFORMED": 0,
        "SCHEMA_MISMATCH": 0,
        "LINEAGE_INCOMPLETE": 0,
        "METADATA_INVALID": 0
    }

    for zone in ["geometry", "field", "manual_review"]:
        zone_path = os.path.join(dropzone_dir, zone)
        if not os.path.exists(zone_path):
            continue

        for fname in os.listdir(zone_path):
            if not fname.endswith(".json"):
                continue
            
            fpath = os.path.join(zone_path, fname)
            totals["scanned"] += 1
            registry.append(fpath)
            
            # 1. JSON Parse Check
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                totals["MALFORMED"] += 1
                malformed.append({"file": fpath, "reason": "JSON_UNPARSEABLE"})
                verdicts[fpath] = "MALFORMED"
                continue

            # 2. Schema Roots Check
            if not isinstance(data, dict):
                totals["MALFORMED"] += 1
                malformed.append({"file": fpath, "reason": "ROOT_NOT_DICT"})
                verdicts[fpath] = "MALFORMED"
                continue

            metadata = data.get("evidence_metadata")
            payload = data.get("observational_payload")
            
            schema_keys = list(data.keys())
            schema_presence.append({"file": fpath, "root_keys": schema_keys})

            if metadata is None or payload is None:
                totals["SCHEMA_MISMATCH"] += 1
                verdicts[fpath] = "SCHEMA_MISMATCH"
                continue

            if not isinstance(metadata, dict):
                totals["METADATA_INVALID"] += 1
                metadata_integrity.append({"file": fpath, "reason": "METADATA_NOT_DICT"})
                verdicts[fpath] = "METADATA_INVALID"
                continue

            # 3. Metadata Completeness Check
            missing_fields = []
            for m_field in MANDATORY_METADATA_FIELDS:
                val = metadata.get(m_field)
                if val is None or val == "":
                    missing_fields.append(m_field)
            
            metadata_integrity.append({
                "file": fpath, 
                "missing_fields": missing_fields,
                "note": "Missing fields explicitly recorded without applying fabricated placeholders."
            })

            # 4. Lineage Check
            anchor = metadata.get("lineage_anchor")
            has_lineage = bool(anchor)
            lineage_integrity.append({
                "file": fpath,
                "lineage_anchor_present": has_lineage,
                "anchor_value": anchor if has_lineage else None
            })

            if not has_lineage:
                totals["LINEAGE_INCOMPLETE"] += 1
                verdicts[fpath] = "LINEAGE_INCOMPLETE"
                continue

            if len(missing_fields) > 0:
                totals["STRUCTURALLY_INCOMPLETE"] += 1
                verdicts[fpath] = "STRUCTURALLY_INCOMPLETE"
                continue

            # If it passes all structural checks natively
            totals["STRUCTURALLY_VALID"] += 1
            verdicts[fpath] = "STRUCTURALLY_VALID"

    # Save 1: Registry
    with open(os.path.join(output_dir, "structural_validation_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"files_validated": registry}, f, indent=2)

    # Save 2: Schema Presence Audit
    with open(os.path.join(output_dir, "schema_presence_audit_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"schema_checks": schema_presence}, f, indent=2)

    # Save 3: Metadata Integrity
    with open(os.path.join(output_dir, "metadata_integrity_audit_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"metadata_checks": metadata_integrity}, f, indent=2)

    # Save 4: Lineage Integrity
    with open(os.path.join(output_dir, "lineage_integrity_audit_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"lineage_checks": lineage_integrity}, f, indent=2)

    # Save 5: Malformed Payload
    with open(os.path.join(output_dir, "malformed_payload_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"malformed_entries": malformed}, f, indent=2)

    # Save 6: Verdict Matrix
    # Ensures no BUSINESS_USABLE or INTEGRATION_READY leaks in.
    with open(os.path.join(output_dir, "structural_verdict_matrix_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"verdicts": verdicts}, f, indent=2)

    # Save 7: Non-Activation Assertions
    assertions = {
        "mode": "VALIDATION_ONLY",
        "spatial_mapping_performed": False,
        "candidate_matching_performed": False,
        "unlock_decisions_triggered": False,
        "recompute_logic_triggered": False,
        "integration_evaluated": False,
        "business_mutation_occurred": False,
        "evidence_sufficiency_judged": False,
        "assertion": "The pipeline explicitly restricted verifications to JSON structure. Zero integrations fired."
    }
    with open(os.path.join(output_dir, "validation_non_activation_assertions_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump(assertions, f, indent=2)

    # Save 8: Execution Report
    md_report = [
        "# STAGE_33_EXECUTION_REPORT",
        "> **Mode**: VALIDATION_ONLY (Read-Only Validation)\n",
        "## Execution Scope",
        f"- **Scanned Target**: `/data/external_evidence/`",
        f"- **Total Payloads Validated**: {totals['scanned']}\n",
        "## Structural Evaluation Results",
        f"- **STRUCTURALLY_VALID**: {totals['STRUCTURALLY_VALID']}",
        f"- **STRUCTURALLY_INCOMPLETE**: {totals['STRUCTURALLY_INCOMPLETE']}",
        f"- **MALFORMED**: {totals['MALFORMED']}",
        f"- **SCHEMA_MISMATCH**: {totals['SCHEMA_MISMATCH']}",
        f"- **LINEAGE_INCOMPLETE**: {totals['LINEAGE_INCOMPLETE']}",
        f"- **METADATA_INVALID**: {totals['METADATA_INVALID']}\n",
        "## Core Disconnected Semantics",
        "- **0** Spatial Mappings were performed.",
        "- **0** Candidate / Business states were mutated.",
        "- **0** Data inference algorithms repaired missing fields (missing explicit arrays remained `null`).",
        "- **0** Operational Integration triggers were engaged.",
        "- Structural validation unconditionally decoupled from `evidence sufficiency/admissibility`."
    ]
    with open(os.path.join(output_dir, "stage_33_execution_report.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_report))

    print("STAGE_33_SUCCESS")

if __name__ == "__main__":
    run_stage_33()
