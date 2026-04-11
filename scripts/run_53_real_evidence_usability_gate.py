import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# =====================================================================
# CONFIGURATION & PATHS
# =====================================================================
REGION_TAG = "NEUSS"
ROOT_DIR = Path(r"d:\Stock Analysis\D-Energy Berater\d-ess-engine")
INTAKE_DIR = ROOT_DIR / "output" / "real_evidence_intake"
OUTPUT_DIR = ROOT_DIR / "output" / "real_evidence_usability"

# Input Files
FILE_REGISTRY_PATH = INTAKE_DIR / f"evidence_file_registry_{REGION_TAG}.json"
CLASSIFICATION_PATH = INTAKE_DIR / f"evidence_type_classification_{REGION_TAG}.json"
ACCEPTANCE_PATH = INTAKE_DIR / f"evidence_acceptance_decisions_{REGION_TAG}.json"
BLOCKER_PATH = INTAKE_DIR / f"evidence_blocker_register_{REGION_TAG}.json"

# Enums (as strings)
# USABILITY_SCOPE
SCOPE_FIELD_03 = "FIELD_03_HEAT_GATE"
SCOPE_FIELD_04 = "FIELD_04_SOCIAL_PROOF"
SCOPE_GEOMETRY = "GEOMETRY_BUILDING_FOOTPRINT"
SCOPE_HEAT_PLAN = "HEAT_PLANNING_REFERENCE"
SCOPE_MANUAL = "MANUAL_SUPPORTING_DOCUMENT"
SCOPE_GENERAL = "GENERAL_REFERENCE_ONLY"
SCOPE_NOT_USABLE = "NOT_USABLE_YET"

# USABILITY_STATUS
STATUS_READY = "READY_FOR_FUTURE_SEMANTIC_PARSE"
STATUS_CONDITIONAL = "CONDITIONALLY_USABLE"
STATUS_BLOCKED_DEP = "BLOCKED_MISSING_DEPENDENCY"
STATUS_BLOCKED_REL = "BLOCKED_LOW_RELEVANCE"
STATUS_BLOCKED_TYPE = "BLOCKED_UNSUPPORTED_TYPE"
STATUS_BLOCKED_SCHEMA = "BLOCKED_SCHEMA_RISK"
STATUS_RETAIN = "RETAIN_ONLY"

# EVIDENCE_ROLE
ROLE_CRITICAL = "CRITICAL"
ROLE_SUPPORTING = "SUPPORTING"
ROLE_AUXILIARY = "AUXILIARY"
ROLE_UNKNOWN = "UNKNOWN"

# BLOCKER_REASONS
B_NO_STRUCTURAL = "NO_STRUCTURAL_ACCEPTANCE"
B_UNKNOWN_REL = "UNKNOWN_FILE_RELEVANCE"
B_NON_TARGET = "NON_TARGET_REGION_UNCONFIRMED"
B_NEEDS_SCHEMA = "NEEDS_FUTURE_SCHEMA_ADAPTER"
B_NEEDS_MANUAL = "NEEDS_MANUAL_REVIEW"
B_INSUFFICIENT = "INSUFFICIENT_MODULE_MATCH"
B_DUPLICATE = "DUPLICATE_OR_REDUNDANT"
B_MISSING_DEP = "MISSING_COMPANION_DATASET"
B_UNSUPPORTED = "UNSUPPORTED_FORMAT"
B_STAGE52_REJECTED = "STAGE_52_REJECTED"
B_STAGE52_UNREAD = "STAGE_52_UNREADABLE"
B_STAGE52_UNSUPP = "STAGE_52_UNSUPPORTED"
B_NO_BLOCKER = "NO_BLOCKER"

# MODULES
MOD_FIELD_03 = "MODULE_FIELD_03"
MOD_FIELD_04 = "MODULE_FIELD_04"
MOD_GEOMETRY = "MODULE_GEOMETRY"
MOD_MANUAL = "MODULE_MANUAL_REVIEW"
MOD_EVIDENCE_FUSION = "MODULE_EVIDENCE_FUSION"
MOD_NONE = "NONE"

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def main():
    print("🚀 [STAGE 53] Executing REAL EVIDENCE RELEVANCE & USABILITY GATE...")
    
    # 1. Ensure target dir exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 2. Load Inputs
    file_registry = load_json(FILE_REGISTRY_PATH).get("files", [])
    classes = load_json(CLASSIFICATION_PATH).get("classifications", [])
    accepts = load_json(ACCEPTANCE_PATH).get("decisions", [])
    blockers = load_json(BLOCKER_PATH).get("blockers", [])
    
    # Map for easy lookup by evidence_id
    idx_classes = {item["evidence_id"]: item for item in classes}
    idx_accepts = {item["evidence_id"]: item for item in accepts}
    idx_blockers = {}
    for b in blockers:
        b_target = b.get("evidence_id")
        if b_target:
            if b_target not in idx_blockers:
                idx_blockers[b_target] = []
            idx_blockers[b_target].append(b)

    # Output Data Structures
    usability_registry = []
    field_counts = {
        "FIELD_03_HEAT_GATE": {"ready": 0, "cond": 0, "blocked": 0, "retained": 0},
        "FIELD_04_SOCIAL_PROOF": {"ready": 0, "cond": 0, "blocked": 0, "retained": 0},
        "GEOMETRY_BUILDING_FOOTPRINT": {"ready": 0, "cond": 0, "blocked": 0, "retained": 0},
        "MANUAL_SUPPORTING_DOCUMENT": {"ready": 0, "cond": 0, "blocked": 0, "retained": 0}
    }
    
    # Trackers for aggregates
    module_mapping = {
        MOD_FIELD_03: [], MOD_FIELD_04: [], MOD_GEOMETRY: [], 
        MOD_MANUAL: [], MOD_EVIDENCE_FUSION: [], MOD_NONE: []
    }
    dependency_blockers = []
    files_accepted_for_parse = []
    files_retained_but_not_usable = []
    
    # Process Each File
    for f in file_registry:
        eid = f["evidence_id"]
        fname = f["filename"]
        rpath = f["relative_path"]
        
        cls_data = idx_classes.get(eid, {})
        acc_data = idx_accepts.get(eid, {})
        
        # Extracted Stage 52 traits
        s52_status = acc_data.get("intake_verdict", "UNKNOWN")
        s52_type = cls_data.get("evidence_type", "UNKNOWN_EVIDENCE_TYPE")
        s52_fmt = cls_data.get("evidence_format", "UNKNOWN")
        s52_rel = cls_data.get("relevance_tier", "UNKNOWN_RELEVANCE")
        
        # Default Governance assignments
        u_scope = [SCOPE_NOT_USABLE]
        u_status = STATUS_RETAIN
        u_role = ROLE_UNKNOWN
        b_reasons = []
        f_modules = [MOD_NONE]
        conf_class = "MINIMAL"
        
        # =========================================================
        # APPLYING HARD BOUNDARY RULES
        # =========================================================
        
        # Rule 1 / Intake checks
        if s52_status in ["REJECTED", "UNREADABLE", "UNSUPPORTED"]:
            u_status = STATUS_BLOCKED_TYPE
            if s52_status == "REJECTED": b_reasons.append(B_STAGE52_REJECTED)
            if s52_status == "UNREADABLE": b_reasons.append(B_STAGE52_UNREAD)
            if s52_status == "UNSUPPORTED": b_reasons.append(B_STAGE52_UNSUPP)
            conf_class = "MINIMAL"
        else:
            # File was basically accepted by Stage 52. Evaluate relevance.
            
            # Identify format-based defaults (Rule 3)
            ext_lower = f["extension"].lower()
            if ext_lower in [".pdf", ".docx", ".jpg", ".png", ".txt"]:
                if s52_type == "UNKNOWN_EVIDENCE_TYPE":
                    u_scope = [SCOPE_MANUAL]
                    u_status = STATUS_CONDITIONAL
                    f_modules = [MOD_MANUAL]
                    b_reasons.append(B_NEEDS_MANUAL)
                    conf_class = "LOW"
            
            # Rule 4: Geometry rules
            elif "geometry" in rpath.lower() or ext_lower in [".geojson", ".shp", ".gpkg"]:
                u_scope = [SCOPE_GEOMETRY]
                f_modules = [MOD_GEOMETRY]
                
                if s52_type == "UNKNOWN_EVIDENCE_TYPE" or s52_rel == "UNKNOWN_RELEVANCE":
                    u_status = STATUS_CONDITIONAL
                    b_reasons.append(B_UNKNOWN_REL)
                    b_reasons.append(B_NEEDS_SCHEMA)
                    conf_class = "LOW"
                else:
                    # If it was fully known (not happening currently but logic built-in)
                    u_status = STATUS_CONDITIONAL # Conservatively stay conditional
                    conf_class = "MEDIUM"
            
            # Rule 5 & 6 (Heat and Solar)
            elif "heat" in fname.lower() or "fernwaerme" in fname.lower():
                u_scope = [SCOPE_FIELD_03]
                f_modules = [MOD_FIELD_03]
                u_status = STATUS_CONDITIONAL
                b_reasons.append(B_UNKNOWN_REL)
                conf_class = "LOW"
            elif "solar" in fname.lower() or "mastr" in fname.lower() or "pv" in fname.lower():
                u_scope = [SCOPE_FIELD_04]
                f_modules = [MOD_FIELD_04]
                u_status = STATUS_CONDITIONAL
                b_reasons.append(B_UNKNOWN_REL)
                conf_class = "LOW"
            
            # Catch-all for other accepted files
            else:
                if s52_type == "UNKNOWN_EVIDENCE_TYPE":
                    u_scope = [SCOPE_GENERAL]
                    u_status = STATUS_RETAIN
                    b_reasons.append(B_UNKNOWN_REL)
                    conf_class = "MINIMAL"
                    
        # Filter NO_BLOCKER if blocks exist
        if not b_reasons:
            b_reasons.append(B_NO_BLOCKER)
        else:
            if B_NO_BLOCKER in b_reasons: b_reasons.remove(B_NO_BLOCKER)
            
        # Compile Registry Entry
        entry = {
            "file_id": eid,
            "file_name": fname,
            "sha256": "FROM_STAGE_52_INTAKE_OR_DEFERRED", # We don't hash here to remain read-only on metadata
            "source_path": rpath,
            "accepted_stage_52_status": s52_status,
            "classified_type": s52_type,
            "classified_format": s52_fmt,
            "evidence_role": u_role,
            "usability_scope": u_scope,
            "usability_status": u_status,
            "blocker_reasons": b_reasons,
            "future_consumer_modules": f_modules,
            "confidence_class": conf_class,
            "notes": "Determined via metadata-only conservative governance bounds."
        }
        usability_registry.append(entry)
        
        # Update mappings
        for mod in f_modules:
            module_mapping[mod].append(eid)
            
        for b in b_reasons:
            if b != B_NO_BLOCKER:
                dependency_blockers.append({"file_id": eid, "blocker": b})
                
        if u_status == STATUS_READY:
            files_accepted_for_parse.append(entry)
        elif u_status in [STATUS_RETAIN, STATUS_CONDITIONAL]:
            files_retained_but_not_usable.append(entry)
            
        # Tally counts for field matrix
        # Simple heuristic to bin the exact scope
        for scope in u_scope:
            if scope in field_counts:
                if u_status == STATUS_READY: field_counts[scope]["ready"] += 1
                elif u_status == STATUS_CONDITIONAL: field_counts[scope]["cond"] += 1
                elif u_status == STATUS_RETAIN: field_counts[scope]["retained"] += 1
                else: field_counts[scope]["blocked"] += 1

    # =========================================================
    # BUILD FINAL ARTIFACTS
    # =========================================================
    
    # 2. field_eligibility_matrix
    field_matrix = []
    overall_readiness_candidates = 0
    
    for f_name, counts in field_counts.items():
        if counts["ready"] > 0:
            verdict = "PREPARED_FOR_CONTROLLED_SEMANTIC_PILOT"
            gap = "ADEQUATE"
            overall_readiness_candidates += 1
        elif counts["cond"] > 0:
            verdict = "CONDITIONALLY_PREPARED"
            gap = "SCHEMA_OR_DEPENDENCY_RISK"
        else:
            verdict = "NOT_READY"
            gap = "CRITICAL_MISSING"
            
        field_matrix.append({
            "field_name": f_name,
            "ready_for_future_semantic_parse_count": counts["ready"],
            "conditionally_usable_count": counts["cond"],
            "blocked_count": counts["blocked"],
            "retained_only_count": counts["retained"],
            "critical_gap_status": gap,
            "readiness_verdict": verdict,
            "notes": "Derived without semantic extraction."
        })

    # Overall Verdict
    if overall_readiness_candidates > 1:
        overall_v = "READY_FOR_CONTROLLED_SEMANTIC_STAGE"
    elif overall_readiness_candidates == 1:
        overall_v = "MODULE_SPECIFIC_READY"
    else:
        # Check if anything is conditionally ready
        if any(c["cond"] > 0 for c in field_counts.values()):
            overall_v = "PARTIALLY_READY"
        else:
            overall_v = "NOT_READY"

    # Build Gap Register
    critical_gaps = {
        "FIELD_03_HEAT": "CRITICAL_MISSING" if field_counts["FIELD_03_HEAT_GATE"]["ready"] == 0 else "OBSERVED",
        "FIELD_04_SOLAR": "CRITICAL_MISSING" if field_counts["FIELD_04_SOCIAL_PROOF"]["ready"] == 0 else "OBSERVED",
        "GEOMETRY_ASSETS": "SCHEMA_RISK" if field_counts["GEOMETRY_BUILDING_FOOTPRINT"]["cond"] > 0 else "MISSING"
    }

    # Write JSONs
    def write_out(name, data):
        with open(OUTPUT_DIR / f"{name}_{REGION_TAG}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
    write_out("evidence_usability_registry", {"evidence": usability_registry})
    write_out("field_eligibility_matrix", {"field_matrix": field_matrix})
    write_out("evidence_to_module_mapping", module_mapping)
    write_out("evidence_dependency_blockers", {"blockers": dependency_blockers})
    write_out("critical_evidence_gap_register", {"gaps": critical_gaps})
    write_out("accepted_for_future_semantic_parse", {"files": files_accepted_for_parse})
    write_out("retained_but_not_usable", {"files": files_retained_but_not_usable})

    report = {
        "stage": "53",
        "mode": "REAL_EVIDENCE_USABILITY_GATE",
        "evidence_files_seen": len(usability_registry),
        "ready_for_future_semantic_parse_count": len(files_accepted_for_parse),
        "conditionally_usable_count": sum(1 for x in usability_registry if x["usability_status"] == STATUS_CONDITIONAL),
        "blocked_count": sum(1 for x in usability_registry if "BLOCKED" in x["usability_status"]),
        "retained_only_count": sum(1 for x in usability_registry if x["usability_status"] == STATUS_RETAIN),
        "per_field_readiness": {f["field_name"]: f["readiness_verdict"] for f in field_matrix},
        "overall_verdict": overall_v,
        "governance_summary": "Applied conservative metadata-only rules. Identified unverified geometries and relegated to conditionally usable state.",
        "safety_confirmation": "Confirmed: No semantic extraction performed. No business records mutated. No spatial computations executed. Metadata domain intact."
    }
    
    with open(OUTPUT_DIR / "stage_53_real_evidence_usability_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("✅ Stage 53 Usability Gate execution completed. Outputs saved.")
    print(f"Overall Verdict: {overall_v}")

if __name__ == "__main__":
    main()
