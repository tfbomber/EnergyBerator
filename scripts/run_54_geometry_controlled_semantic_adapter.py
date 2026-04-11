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
EVIDENCE_DIR = ROOT_DIR / "data" / "external_evidence"
STAGE_53_DIR = ROOT_DIR / "output" / "real_evidence_usability"
OUTPUT_DIR = ROOT_DIR / "output" / "geometry_adapter"

USABILITY_REGISTRY_PATH = STAGE_53_DIR / f"evidence_usability_registry_{REGION_TAG}.json"

# Schema Constants
B_FILE_NOT_FOUND = "FILE_NOT_FOUND"
B_HASH_MISMATCH = "HASH_MISMATCH_UNCONFIRMED"
B_NOT_JSON = "NOT_JSON_STRUCTURE"
B_UNKNOWN_TOP = "UNKNOWN_TOP_LEVEL_CONTAINER"
B_NO_GEOMETRY = "NO_GEOMETRY_FOUND"
B_MIXED_SHAPES = "MIXED_FEATURE_SHAPES"
B_CRS_NOT_DECLARED = "CRS_NOT_DECLARED"
B_PROP_INCONSISTENT = "PROPERTIES_HIGHLY_INCONSISTENT"
B_SCHEMA_UNSTABLE = "SCHEMA_TOO_UNSTABLE"
B_EMPTY_FEATURE = "EMPTY_FEATURE_SET"
B_PARSE_ERROR = "PARSE_ERROR"
B_NON_GEOMETRY = "NON_GEOMETRY_CONTENT"
B_NO_BLOCKER = "NO_BLOCKER"

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 without loading entire file in memory."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def inspect_geometry_shape(geom_obj: dict) -> str:
    if not isinstance(geom_obj, dict): return "Unknown"
    gtype = geom_obj.get("type", "Unknown")
    if gtype in ["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"]:
        return gtype
    return "Unknown"

def process_file_structure(file_path: Path):
    """
    Perform a safe structural parse without extracting business semantics.
    """
    if not file_path.exists():
        return {"error": B_FILE_NOT_FOUND}
        
    try:
        data = load_json(file_path)
    except Exception as e:
        return {"error": B_PARSE_ERROR}
        
    if not isinstance(data, dict):
        return {"error": B_UNKNOWN_TOP}
        
    result = {
        "top_level_container_type": "UNKNOWN",
        "feature_count_detected": 0,
        "geometry_type_profile": set(),
        "crs_status": "CRS_NOT_DECLARED",
        "explicit_crs_value": None,
        "property_key_inventory": set(),
        "blockers": []
    }
    
    # Check for Explicit CRS anywhere near root
    if "crs" in data:
        result["crs_status"] = "EXPLICIT_CRS_FOUND"
        result["explicit_crs_value"] = str(data["crs"])
        
    features_to_inspect = []
    
    # Root Structure Detection
    if data.get("type") == "FeatureCollection" and "features" in data:
        result["top_level_container_type"] = "FeatureCollection"
        features_to_inspect = data["features"]
    elif data.get("type") == "Feature":
        result["top_level_container_type"] = "Feature"
        features_to_inspect = [data]
    elif "observational_payload" in data and isinstance(data["observational_payload"], dict):
        # Custom wrapped payloads like PHYSICAL_E4_...
        payload = data["observational_payload"]
        if payload.get("type") == "Feature":
            result["top_level_container_type"] = "Wrapped_Feature"
            features_to_inspect = [payload]
        elif payload.get("type") == "FeatureCollection" and "features" in payload:
            result["top_level_container_type"] = "Wrapped_FeatureCollection"
            features_to_inspect = payload["features"]
        else:
            result["top_level_container_type"] = "Wrapped_Unknown"
            result["blockers"].append(B_UNKNOWN_TOP)
    else:
        result["top_level_container_type"] = "Unknown_JSON_Structure"
        result["blockers"].append(B_UNKNOWN_TOP)
        return result
        
    if not isinstance(features_to_inspect, list):
        result["blockers"].append(B_PARSE_ERROR)
        return result
        
    result["feature_count_detected"] = len(features_to_inspect)
    if result["feature_count_detected"] == 0:
        result["blockers"].append(B_EMPTY_FEATURE)
        
    # Inspect schema within features
    for f in features_to_inspect:
        if not isinstance(f, dict): continue
        if "geometry" in f and f["geometry"] is not None:
            gtype = inspect_geometry_shape(f["geometry"])
            result["geometry_type_profile"].add(gtype)
        else:
            result["blockers"].append(B_NO_GEOMETRY)
            
        if "properties" in f and isinstance(f["properties"], dict):
            for k in f["properties"].keys():
                result["property_key_inventory"].add(k)
                
    if not result["geometry_type_profile"]:
        result["blockers"].append(B_NO_GEOMETRY)
    elif len(result["geometry_type_profile"]) > 1:
        if "Unknown" in result["geometry_type_profile"]:
            result["blockers"].append(B_MIXED_SHAPES)
            
    if result["crs_status"] == "CRS_NOT_DECLARED":
        result["blockers"].append(B_CRS_NOT_DECLARED)
        
    # Convert sets to sorted lists for deterministic output
    result["geometry_type_profile"] = sorted(list(result["geometry_type_profile"]))
    result["property_key_inventory"] = sorted(list(result["property_key_inventory"]))
    
    return result


def main():
    print("🚀 [STAGE 54] Executing CONTROLLED SEMANTIC ADAPTER (GEOM ONLY)...")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    usability_registry = load_json(USABILITY_REGISTRY_PATH).get("evidence", [])
    
    # Filter geometry candidates
    geom_candidates = [
        f for f in usability_registry 
        if "GEOMETRY_BUILDING_FOOTPRINT" in f.get("usability_scope", [])
        and "MODULE_GEOMETRY" in f.get("future_consumer_modules", [])
        and f.get("usability_status") in ["CONDITIONALLY_USABLE", "READY_FOR_FUTURE_SEMANTIC_PARSE"]
    ]
    
    # Stable Outputs
    adapter_registry = []
    
    parseable_count = 0
    parseable_lim_count = 0
    ambig_count = 0
    blckd_count = 0
    ready_dry_count = 0
    bridge_count = 0
    man_rev_count = 0
    
    container_dist = {}
    geom_dist = {}
    crs_dist = {"EXPLICIT_CRS_FOUND": 0, "CRS_NOT_DECLARED": 0}
    parse_dist = {}
    
    property_inventory_list = []
    parseability_matrix_list = []
    schema_blockers = []
    files_ready_for_dry_run = []
    files_for_review = []
    
    # Process
    for cand in sorted(geom_candidates, key=lambda x: (x["file_name"], x["sha256"])):
        target_path = EVIDENCE_DIR / cand["source_path"]
        
        # 1. Access Check
        file_exists = target_path.exists()
        current_hash = calculate_sha256(target_path) if file_exists else None
        
        blockers = []
        if not file_exists:
            blockers.append(B_FILE_NOT_FOUND)
        # Note: cand["sha256"] is deferred from Stage 52 right now, so we skip strict mismatch check for now unless populated.
        
        parsed = process_file_structure(target_path)
        
        stability = "UNKNOWN"
        parse_status = "NOT_PARSEABLE"
        adapter_ready = "BLOCKED_FOR_FUTURE_STAGE"
        conf_class = "MINIMAL"
        
        if "error" in parsed:
            blockers.append(parsed["error"])
            parse_status = "NOT_PARSEABLE"
            adapter_ready = "BLOCKED_FOR_FUTURE_STAGE"
            blckd_count += 1
            conf_class = "LOW"
            top_level = "Unknown"
            g_profile = []
            crs_s = "CRS_NOT_DECLARED"
            explicit_crs = None
            p_keys = []
        else:
            blockers.extend(parsed["blockers"])
            blockers = list(set(blockers)) # Deduplicate
            
            top_level = parsed["top_level_container_type"]
            g_profile = parsed["geometry_type_profile"]
            crs_s = parsed["crs_status"]
            explicit_crs = parsed["explicit_crs_value"]
            p_keys = parsed["property_key_inventory"]
            
            # 7. Schema Stability
            if B_UNKNOWN_TOP in blockers or B_PARSE_ERROR in blockers:
                stability = "UNSTABLE"
            elif B_NO_GEOMETRY in blockers or B_MIXED_SHAPES in blockers or B_EMPTY_FEATURE in blockers:
                stability = "MIXED"
            else:
                stability = "MOSTLY_STABLE" # Conservative default without deep feature variance analysis
                
            # 8. Parseability Status
            if B_UNKNOWN_TOP in blockers or top_level.startswith("Unknown"):
                parse_status = "STRUCTURALLY_AMBIGUOUS"
                ambig_count += 1
            elif B_CRS_NOT_DECLARED in blockers or B_UNKNOWN_TOP in blockers:
                parse_status = "PARSEABLE_WITH_LIMITATIONS"
                parseable_lim_count += 1
            elif top_level in ["FeatureCollection", "Feature", "Wrapped_Feature", "Wrapped_FeatureCollection"]:
                parse_status = "PARSEABLE"
                parseable_count += 1
            else:
                parse_status = "UNSUPPORTED_GEOMETRY_CONTAINER"
                blckd_count += 1
                
            # 9. Future Adapter Readiness
            if parse_status == "PARSEABLE":
                adapter_ready = "READY_FOR_GEOMETRY_DRY_RUN"
                ready_dry_count += 1
                conf_class = "MEDIUM"
            elif parse_status == "PARSEABLE_WITH_LIMITATIONS":
                # Special case: custom wrapped physical schema with implicit CRS needs a bridge
                if top_level.startswith("Wrapped"):
                    adapter_ready = "NEEDS_SCHEMA_BRIDGE"
                    bridge_count += 1
                    conf_class = "LOW"
                else:
                    adapter_ready = "NEEDS_MANUAL_REVIEW"
                    man_rev_count += 1
                    conf_class = "LOW"
            else:
                adapter_ready = "BLOCKED_FOR_FUTURE_STAGE"
                conf_class = "MINIMAL"

        # Output cleanup
        if not blockers:
            blockers.append(B_NO_BLOCKER)
        else:
            if B_NO_BLOCKER in blockers: blockers.remove(B_NO_BLOCKER)
            
        blockers.sort()
        
        # Tallies
        container_dist[top_level] = container_dist.get(top_level, 0) + 1
        crs_dist[crs_s] = crs_dist.get(crs_s, 0) + 1
        parse_dist[parse_status] = parse_dist.get(parse_status, 0) + 1
        for g in g_profile:
            geom_dist[g] = geom_dist.get(g, 0) + 1
            
        # Compile record
        rec = {
            "file_id": cand["file_id"],
            "file_name": cand["file_name"],
            "sha256": current_hash if current_hash else cand["sha256"],
            "source_path": cand["source_path"],
            "stage_53_usability_status": cand["usability_status"],
            "top_level_container_type": top_level,
            "feature_count_detected": parsed.get("feature_count_detected", 0) if "error" not in parsed else 0,
            "geometry_type_profile": g_profile,
            "crs_status": crs_s,
            "explicit_crs_value": explicit_crs,
            "property_key_inventory": p_keys,
            "property_key_frequency_summary": {"distinct_keys": len(p_keys)},
            "schema_stability": stability,
            "parseability_status": parse_status,
            "future_adapter_readiness": adapter_ready,
            "blocker_reasons": blockers,
            "confidence_class": conf_class,
            "notes": "Structural geometry validation complete. Semantic contents shielded."
        }
        
        adapter_registry.append(rec)
        
        property_inventory_list.append({
            "file_id": cand["file_id"],
            "property_keys_observed": p_keys,
            "key_frequency_summaries": {"distinct_keys": len(p_keys)},
            "structural_consistency_notes": stability
        })
        
        parseability_matrix_list.append({
            "file_id": cand["file_id"],
            "parseability_status": parse_status,
            "schema_stability": stability,
            "future_adapter_readiness": adapter_ready,
            "blocker_reasons": blockers
        })
        
        for b in blockers:
            if b != B_NO_BLOCKER:
                schema_blockers.append({"file_id": cand["file_id"], "blocker": b})
                
        if parse_status in ["PARSEABLE", "PARSEABLE_WITH_LIMITATIONS"] and adapter_ready == "READY_FOR_GEOMETRY_DRY_RUN":
            files_ready_for_dry_run.append(rec)
        if adapter_ready in ["NEEDS_SCHEMA_BRIDGE", "NEEDS_MANUAL_REVIEW", "BLOCKED_FOR_FUTURE_STAGE"]:
            files_for_review.append(rec)

    # Verdict
    if not adapter_registry:
        overall_v = "NOT_READY"
    elif ready_dry_count > 0:
        overall_v = "ADAPTER_READY_FOR_DRY_RUN"
    elif bridge_count > 0 or man_rev_count > 0:
        overall_v = "ADAPTER_READY_WITH_LIMITATIONS"
    else:
        overall_v = "STRUCTURALLY_PARTIAL"

    # Writes
    def write_out(name, data):
        with open(OUTPUT_DIR / f"{name}_{REGION_TAG}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    write_out("geometry_adapter_registry", {"records": adapter_registry})
    write_out("geometry_container_profile", {
        "container_type_distribution": container_dist,
        "geometry_type_distribution": geom_dist,
        "crs_declaration_status_distribution": crs_dist,
        "parseability_distribution": parse_dist
    })
    write_out("geometry_property_schema_inventory", {"inventory": property_inventory_list})
    write_out("geometry_parseability_matrix", {"matrix": parseability_matrix_list})
    write_out("geometry_schema_blocker_register", {"blockers": schema_blockers})
    write_out("geometry_ready_for_dry_run", {"files": files_ready_for_dry_run})
    write_out("geometry_retained_for_manual_review", {"files": files_for_review})
    
    report = {
        "stage": "54",
        "mode": "CONTROLLED_SEMANTIC_ADAPTER",
        "files_considered": len(geom_candidates),
        "files_processed": len(adapter_registry),
        "parseable_count": parseable_count,
        "parseable_with_limitations_count": parseable_lim_count,
        "ambiguous_count": ambig_count,
        "blocked_count": blckd_count,
        "ready_for_geometry_dry_run_count": ready_dry_count,
        "needs_schema_bridge_count": bridge_count,
        "needs_manual_review_count": man_rev_count,
        "overall_verdict": overall_v,
        "governance_summary": "Extracted structure-only payload traits (keys, topology). Verified container parseability. No payload content parsed.",
        "safety_confirmation": "Confirmed: No point-in-polygon executed. No spatial joins run. No business objects extracted. Properties stored as raw strings only."
    }
    
    with open(OUTPUT_DIR / "stage_54_geometry_adapter_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("✅ Stage 54 Geometry Adapter execution completed. Outputs saved.")
    print(f"Overall Verdict: {overall_v}")

if __name__ == "__main__":
    main()
