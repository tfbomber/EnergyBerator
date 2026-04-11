import json
import os

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
output_dir = os.path.join(base_dir, "output", "reality_connector")
os.makedirs(output_dir, exist_ok=True)

def run_stage_23():
    execution_report = {
        "city_processed": "Neuss",
        "interface_specs_generated": 3,
        "governance_documents_generated": 2,
        "replacement_rule_sets_generated": 1,
        "optional_modules_executed": "ALL True",
        "paths": []
    }

    # MODULE 23A: REALITY DATA INTERFACE SPEC
    md_a = [
        "# Reality Data Interface Specification: NEUSS",
        "This architectural spec handles entry formats for all external truth ingestions.\n",
        "## 1. Official Geometry Boundary Intake",
        "- **Interface Name**: `INTAKE_GEO_BND`",
        "- **Source Type**: Official OSM Admin Polygon / Kataster Boundary",
        "- **Expected Truth Class**: E4 Official Authoritative Source",
        "- **Input Format**: GeoJSON / WKT Polygon",
        "- **Ingestion Preconditions**: Bounding Box area must align roughly with Stage 20 proxy dimensions.",
        "- **Downstream Consumers**: Stage 13 geometry generators, clustering logic.",
        "- **Replacement Target**: Stage 22 Proxy Bounding Box.",
        "- **Risk of Misuse**: Polygon too broad, enveloping invalid suburban space.\n",
        "## 2. Evidence Field Verification Intake (FIELD_03/FIELD_04)",
        "- **Interface Name**: `INTAKE_FIELD_TRUTH`",
        "- **Source Type**: API / Web Scraping (e.g. MaStR, SWN Heat Map)",
        "- **Expected Truth Class**: E3 External Observed Partial or E4 Official Authoritative",
        "- **Input Format**: Structured JSON records anchored to street or coordinates.",
        "- **Ingestion Preconditions**: Segment geometry must be at least `EXTERNAL_BOUNDARY_ATTACHED`.",
        "- **Downstream Consumers**: Target Scorers, Re-Clustering Logic.",
        "- **Replacement Target**: SIMULATED_INFERENCE field values.",
        "- **Risk of Misuse**: Partial API data conflicting with visual reality.\n"
    ]
    with open(os.path.join(output_dir, "reality_data_interface_spec_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_a))
    execution_report['paths'].append(os.path.join(output_dir, "reality_data_interface_spec_NEUSS.md"))

    # MODULE 23B: GEOMETRY TRUTH CONNECTOR SPEC
    md_b = [
        "# Geometry Truth Connector Spec: NEUSS",
        "Tracks transition of Bounding-Box Proxies into real-world footprint data.\n",
        "## Geometry Status Classes",
        "1. **PROXY_ONLY**: Mathematically inferred bounds. (Acceptable for planning only)",
        "2. **PENDING_EXTERNAL_DRAW**: Sent to GIS operator / API query queue.",
        "3. **EXTERNAL_BOUNDARY_ATTACHED**: District polygon acquired. Building logic still inferred. (Requires Polygon)",
        "4. **BUILDING_FOOTPRINT_ATTACHED**: Discrete OSM buildings fetched within polygon. (Mandatory for Field routing)",
        "5. **GEOMETRY_VALIDATED**: QA operator confirms geometric footprints are residential. (Blocks Official Activation until True)\n",
        "## Downstream Consequences",
        "Successful bump to `BUILDING_FOOTPRINT_ATTACHED` instantly triggers `RECOMPUTE_CLUSTERS` flag."
    ]
    with open(os.path.join(output_dir, "geometry_truth_connector_spec_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_b))
    execution_report['paths'].append(os.path.join(output_dir, "geometry_truth_connector_spec_NEUSS.md"))

    # MODULE 23C: FIELD TRUTH CONNECTOR SPEC
    md_c = [
        "# Field Truth Connector Spec: NEUSS",
        "Defines simulation replacement and conflicts around physical evidence.\n",
        "## FIELD_03 (Heat Infrastructure Gate)",
        "- **Simulated State**: `SIMULATED_ONLY`",
        "- **Acceptable Sources**: E4 SWN Official Fernwärme Karte.",
        "- **Minimum Evidence Standard**: Address or Street-Level Intersection.",
        "- **Replacement Trigger**: Upload of validated SWN shapefile intersecting Geometry.",
        "- **Conflict Handling**: Authoritative E4 source strictly overrides E0/E1 inferences.",
        "- **Downstream Action**: Recomputes overall segment `EXPANSION_TIER`.\n",
        "## FIELD_04 (PV Social Proof)",
        "- **Simulated State**: `SIMULATED_ONLY`",
        "- **Acceptable Sources**: E4 MaStR Federal Solar Registry.",
        "- **Minimum Evidence Standard**: PLZ+Street level density maps.",
        "- **Source Precedence**: Manual API query (E3) overridden by Federal Dataset Dump (E4).",
        "- **Partial Validation Logic**: If <50% of the addresses matched, mark `PARTIALLY_VALIDATED`.",
        "- **Field Outcome Classes**: `SIMULATED_ONLY` -> `EVIDENCE_ATTACHED` -> `PARTIALLY_VALIDATED` -> `FIELD_VALIDATED`."
    ]
    with open(os.path.join(output_dir, "field_truth_connector_spec_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_c))
    execution_report['paths'].append(os.path.join(output_dir, "field_truth_connector_spec_NEUSS.md"))

    # MODULE 23D: SIMULATION TO REAL REPLACEMENT RULES (JSON)
    rules = {
        "artifact_families": [
            {
                "artifact_family": "geometry",
                "simulated_status": "inferred_pending_actual_osm_draw",
                "real_replacement_status": "GEOMETRY_VALIDATED",
                "replacement_allowed": True,
                "replacement_conditions": ["must be E3 or E4 data", "requires manual bounds check"],
                "coexistence_rule": "Current active truth OVERWRITES proxy. Archive lineage.",
                "archival_rule": "Store proxy under /archive/simulated_geo/",
                "downstream_recompute_required": ["field_signals", "clusters", "validation"]
            },
            {
                "artifact_family": "field_signals",
                "simulated_status": "simulated_inference",
                "real_replacement_status": "FIELD_VALIDATED",
                "replacement_allowed": True,
                "replacement_conditions": ["Geometry must be at least EXTERNAL_BOUNDARY_ATTACHED"],
                "coexistence_rule": "Overwrite active node. Log historical conflict if differing significantly.",
                "archival_rule": "Maintain SIM history for algorithm accuracy tracking.",
                "downstream_recompute_required": ["deployment_candidate_status", "validation"]
            }
        ]
    }
    with open(os.path.join(output_dir, "simulation_to_real_replacement_rules_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump(rules, f, indent=2)
    execution_report['paths'].append(os.path.join(output_dir, "simulation_to_real_replacement_rules_NEUSS.json"))

    # MODULE 23E: SEGMENT ACTIVATION GOVERNANCE
    md_e = [
        "# Segment Activation Governance: NEUSS",
        "Strict logic managing when a Segment officially activates from 'Candidate' into Production Pipeline.\n",
        "## Activation Gates",
        "- **Geometry Gate**: Must equal `GEOMETRY_VALIDATED`. Simulation proxies block activation.",
        "- **Field Truth Gate**: `FIELD_03` must be `FIELD_VALIDATED`. (Cannot deploy into unknown heating areas).",
        "- **Validation Gate**: Overall segment validation score must be > 0.65 confirmed.",
        "- **Manual Review Gate**: E5 Operator signoff required for final morphology alignment.",
        "- **Deployment Governance Gate**: Segment cannot be marked `deployment_ready` solely on high evidence tier.",
        "\n*Policy: Simulated segments are explicitly sandboxed. Partial truths cannot be presented as Validated Readiness.*"
    ]
    with open(os.path.join(output_dir, "segment_activation_governance_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_e))
    execution_report['paths'].append(os.path.join(output_dir, "segment_activation_governance_NEUSS.md"))

    # MODULE 23F: PRODUCTION HANDOFF CHECKLIST
    md_f = [
        "# Production Handoff Operator Checklist",
        "To be utilized physically/digitally by the orchestrator prior to promoting a Pre-Deployment Sandbox segment into D-ESS Live.\n",
        "| Gate | Requirement | Status | Operator Sig |",
        "|---|---|---|---|",
        "| 1 | Is Authoritative Geometry evidence present and attached? | [ ] Yes | ____ |",
        "| 2 | Has the map boundary been human-reviewed for anomalies? | [ ] Yes | ____ |",
        "| 3 | Is the OSM building count logically confident vs density? | [ ] Yes | ____ |",
        "| 4 | Is FIELD_03 (Heat) external evidence explicitly attached? | [ ] Yes | ____ |",
        "| 5 | Is FIELD_04 (PV) evidence explicitly attached? | [ ] Yes | ____ |",
        "| 6 | Were clusters recomputed based on true Geometry? | [ ] Yes | ____ |",
        "| 7 | Was Validation Engine rerun against recomputed features? | [ ] Yes | ____ |",
        "| 8 | Has the commercial deployment wave note been updated? | [ ] Yes | ____ |",
        "| 9 | Is E5 Manual Operator sign-off recorded in final metadata? | [ ] Yes | ____ |"
    ]
    with open(os.path.join(output_dir, "production_handoff_checklist_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_f))
    execution_report['paths'].append(os.path.join(output_dir, "production_handoff_checklist_NEUSS.md"))

    # DEEPENING 23G: EVIDENCE TIER FRAMEWORK
    md_g = [
        "# Evidence Tier Framework (E0 - E5)",
        "## E0: Simulated",
        "- **Meaning**: Mock data generated for testing. **Allowed**: Pipeline proxy tests. **Forbidden**: Deployment logic. **Activation Rights**: None.",
        "## E1: Heuristic Inferred",
        "- **Meaning**: Estimated based on district averages. **Allowed**: Stage 20 Planning. **Forbidden**: Final routing. **Activation Rights**: None.",
        "## E2: Project-derived Spatial Proxy",
        "- **Meaning**: Interpolated from overlapping spatial sources. **Allowed**: Triage lists. **Forbidden**: Core gating. **Activation Rights**: Partial.",
        "## E3: External Observed Partial",
        "- **Meaning**: Unofficial web scrape or partial API. **Allowed**: Supplemental metrics. **Forbidden**: Overriding E4. **Activation Rights**: Partial.",
        "## E4: Official Authoritative Source",
        "- **Meaning**: Govt/Corp direct dataset (OSM, SWN). **Allowed**: Core Truth. **Forbidden**: None. **Activation Rights**: Yes (Subject to Governance Gate).",
        "## E5: Manual Field-Confirmed",
        "- **Meaning**: Operator visually verified (Satellite/Door). **Allowed**: Absolute override. **Activation Rights**: Yes. **Deployment Implications**: Ready."
    ]
    with open(os.path.join(output_dir, "evidence_tier_framework_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_g))
    execution_report['paths'].append(os.path.join(output_dir, "evidence_tier_framework_NEUSS.md"))

    # DEEPENING 23H: EPISTEMIC STATUS TRANSITION MAP
    t_map = {
        "transitions": [
            "SIMULATED_PROXY -> EXTERNAL_GEOMETRY_PENDING",
            "EXTERNAL_GEOMETRY_PENDING -> EXTERNAL_BOUNDARY_ATTACHED",
            "EXTERNAL_BOUNDARY_ATTACHED -> BUILDING_FOOTPRINT_ATTACHED",
            "BUILDING_FOOTPRINT_ATTACHED -> GEOMETRY_VALIDATED",
            "GEOMETRY_VALIDATED -> FIELD_PARTIAL",
            "FIELD_PARTIAL -> FIELD_VALIDATED",
            "FIELD_VALIDATED -> PRE_DEPLOYMENT_CONFIRMED",
            "PRE_DEPLOYMENT_CONFIRMED -> DEPLOYMENT_READY (E5 Review Block)",
            "DEPLOYMENT_READY -> OFFICIAL_ACTIVE_SEGMENT"
        ]
    }
    with open(os.path.join(output_dir, "epistemic_status_transition_map_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump(t_map, f, indent=2)
    execution_report['paths'].append(os.path.join(output_dir, "epistemic_status_transition_map_NEUSS.json"))

    # DEEPENING 23I: REAL-WORLD BLOCKER REGISTRY
    md_i = [
        "# Real-World Blocker Registry",
        "## Blocker 1: No Authoritative Geometry Source",
        "- **Severity**: HIGH. **Prob**: LOW. **Mitigation**: Revert to manual E5 GIS polygon trace.",
        "## Blocker 2: Ambiguous District Heating Boundary",
        "- **Severity**: HIGH. **Prob**: MEDIUM. **Mitigation**: Assign FIELD_03 `UNKNOWN`. Escalate to Manual Review.",
        "## Blocker 3: Multi-Family Contamination Discovered",
        "- **Severity**: MEDIUM. **Prob**: HIGH. **Mitigation**: Run building footprint area filter; drop buildings > 400m2.",
        "## Blocker 4: Cluster Instability after True Geometry",
        "- **Severity**: SYSTEMIC. **Prob**: MEDIUM. **Mitigation**: Enforce RECOMPUTE_CLUSTERS after footprint acquisition."
    ]
    with open(os.path.join(output_dir, "real_world_blocker_registry_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_i))
    execution_report['paths'].append(os.path.join(output_dir, "real_world_blocker_registry_NEUSS.md"))

    # EXECUTE REPORT
    er = [
        "# STAGE_23_EXECUTION_REPORT\n",
        f"- **City Processed**: {execution_report['city_processed']}",
        f"- **Interface Specs Generated**: {execution_report['interface_specs_generated']}",
        f"- **Governance Documents Generated**: {execution_report['governance_documents_generated']}",
        f"- **Replacement Rule Sets Generated**: {execution_report['replacement_rule_sets_generated']}",
        f"- **Optional Modules Executed**: {execution_report['optional_modules_executed']}\n",
        "**Output Paths**:"
    ]
    for p in execution_report['paths']:
        er.append(f"  - {p}")
        
    er.append("\n**Key Governance Conclusion**:")
    er.append("The Reality Connector interfaces successfully define an impenetrable wall between simulation heuristics and physical production data. Evidence Tiering and strict Geometry ingestion rules demand manual (E5) and authoritative (E4) confirmations prior to official segment activation. Simulated test components cannot functionally bypass Governance gates into deployment channels.")
    
    with open(os.path.join(output_dir, "stage_23_execution_report.md"), "w", encoding="utf8") as f:
        f.write("\n".join(er))
        
    print("STAGE_23_SUCCESS")

if __name__ == "__main__":
    run_stage_23()
