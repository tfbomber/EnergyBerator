import json
import os

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
dropzone_dir = os.path.join(base_dir, "data", "external_evidence")
output_dir = os.path.join(base_dir, "output", "evidence_discovery")
os.makedirs(output_dir, exist_ok=True)

def run_stage_32():
    print("Executing DISCOVERY_ONLY - Read Only Scan")

    discovery_reg = []
    catalog = []
    malformed = []
    duplicates = []
    unknown_family = []
    
    seen_shas = set()

    for zone in ["geometry", "field", "manual_review"]:
        zone_path = os.path.join(dropzone_dir, zone)
        if os.path.exists(zone_path):
            for fname in os.listdir(zone_path):
                fpath = os.path.join(zone_path, fname)
                if fname.endswith(".json"):
                    discovery_reg.append(fpath)
                    
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except json.JSONDecodeError:
                        malformed.append({"file": fpath, "reason": "unreadable_json"})
                        continue

                    metadata = data.get("evidence_metadata", {})
                    if not metadata:
                        malformed.append({"file": fpath, "reason": "missing_evidence_metadata_block"})
                        continue
                    
                    target_class = metadata.get("evidence_class", "")
                    if target_class not in ["E4_Geometry", "E5_ManualReview"]:
                        unknown_family.append({"file": fpath, "extracted_class": target_class})
                    
                    anchor = metadata.get("lineage_anchor", "MISSING_ANCHOR")
                    
                    if anchor in seen_shas and anchor != "MISSING_ANCHOR":
                        duplicates.append({"file": fpath, "duplicate_anchor": anchor})
                    else:
                        seen_shas.add(anchor)

                    catalog.append({
                        "file_origin": fpath,
                        "parsed_metadata": {
                            "evidence_source": metadata.get("evidence_source", "UNKNOWN"),
                            "evidence_class": target_class,
                            "segment_binding": metadata.get("segment_binding", "UNKNOWN"),
                            "lineage_anchor": anchor,
                            "schema_version": metadata.get("schema_version", "UNKNOWN")
                        }
                    })

    # 1. Discovery Registry
    with open(os.path.join(output_dir, "discovery_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"discovered_files": discovery_reg}, f, indent=2)

    # 2. Evidence Catalog
    with open(os.path.join(output_dir, "evidence_catalog_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"cataloged_items": catalog}, f, indent=2)

    # 3. Malformed / Unreadable Registry
    with open(os.path.join(output_dir, "malformed_unreadable_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"malformed_entries": malformed}, f, indent=2)

    # 4. Duplicate Signature Registry
    with open(os.path.join(output_dir, "duplicate_signature_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"duplicate_entries": duplicates}, f, indent=2)

    # 5. Unknown Family Quarantine
    with open(os.path.join(output_dir, "unknown_family_quarantine_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"quarantined_entries": unknown_family}, f, indent=2)

    # 6. Non-Activation Assertions
    assertions = {
        "mode": "DISCOVERY_ONLY",
        "spatial_joins_executed": False,
        "candidate_mappings_executed": False,
        "business_conclusions_generated": False,
        "STILL_BLOCKED_status_mutated": False,
        "assertion": "Metadata parse success is strictly decoupled from downstream validity. No inferred data was generated for MISSING properties."
    }
    with open(os.path.join(output_dir, "non_activation_assertions_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump(assertions, f, indent=2)

    # 7. Execution Report
    md_report = [
        "# STAGE_32_EXECUTION_REPORT",
        "> **Mode**: DISCOVERY_ONLY (Read Only)\n",
        "## Catalog Metrics",
        f"- **Total Files Discovered**: {len(discovery_reg)}",
        f"- **Packages successfully cataloged**: {len(catalog)}",
        f"- **Malformed/Unreadable**: {len(malformed)}",
        f"- **Quarantined Families**: {len(unknown_family)}",
        f"- **Duplicate Signatures**: {len(duplicates)}\n",
        "## Execution Proofs",
        "- All evidence files were read identically as static blocks.",
        "- No spatial joints, candidate evaluations, or integration tests occurred.",
        "- Missing data was captured exactly as 'UNKNOWN' without derivation.",
        "- Execution halted natively yielding a pre-flight database catalog."
    ]
    with open(os.path.join(output_dir, "stage_32_execution_report.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_report))

    print("STAGE_32_SUCCESS")

if __name__ == "__main__":
    run_stage_32()
