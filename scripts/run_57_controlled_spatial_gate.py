import json
import os
import hashlib
from datetime import datetime
from pathlib import Path

# =====================================================================
# CONFIGURATION & PATHS
# =====================================================================
REGION_TAG = "NEUSS"
ROOT_DIR = Path(r"d:\Stock Analysis\D-Energy Berater\d-ess-engine")
EVIDENCE_DIR = ROOT_DIR / "data" / "external_evidence"
STAGE_56_DIR = ROOT_DIR / "output" / "geometry_dry_run_sandbox"
OUTPUT_DIR = ROOT_DIR / "output" / "controlled_spatial_gate"

SANDBOX_REGISTRY_PATH = STAGE_56_DIR / f"geometry_sandbox_execution_registry_{REGION_TAG}.json"

# Gate Enums
STAT_ADM = "TECHNICALLY_ADMISSIBLE"
STAT_ADM_LIM = "ADMISSIBLE_WITH_LIMITATIONS"
STAT_AMB = "TECHNICALLY_AMBIGUOUS"
STAT_NOT_ADM = "NOT_TECHNICALLY_ADMISSIBLE"

READ_MATCH = "READY_FOR_CONTROLLED_MATCHING_GATE"
READ_LIM = "READY_WITH_LIMITATIONS"
READ_MANUAL = "NEEDS_MANUAL_SPATIAL_REVIEW"
READ_BLOCKED = "BLOCKED_FOR_SPATIAL_STAGE"

CRS_RISK_LOW = "LOW"
CRS_RISK_MOD = "MODERATE"
CRS_RISK_HIGH = "HIGH"
CRS_RISK_CRIT = "CRITICAL"

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def resolve_jsonpath(payload, path_str):
    if path_str == "UNRESOLVED": return False, None
    if path_str == "$": return True, payload
    parts = path_str.split('.')
    curr = payload
    for part in parts[1:]:
        if curr is None: return False, None
        if part.endswith("[*]"):
            key = part[:-3]
            if isinstance(curr, dict) and key in curr:
                curr = curr[key]
                if not isinstance(curr, list): return False, None
            else: return False, None
        else:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else: return False, None
    return True, curr

def extract_flat_coordinates(coords, flat_list):
    """
    Recursively flatten coordinate arrays to inspect max/min ranges safely.
    """
    if not isinstance(coords, list):
        return
    if len(coords) > 0 and isinstance(coords[0], (int, float)):
        # Found a point e.g. [lon, lat]
        if len(coords) >= 2:
            flat_list.append((coords[0], coords[1]))
    else:
        for c in coords:
            extract_flat_coordinates(c, flat_list)

def inspect_coordinate_range(coords):
    """
    Technically inspect coordinates without inferring real-world truth.
    Returns: (is_degree_like, is_projected_like, min_x, min_y, max_x, max_y)
    """
    pts = []
    extract_flat_coordinates(coords, pts)
    
    if not pts:
        return False, False, None, None, None, None
        
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    # Highly naive heuristic for WG84 vs WebMercator/UTM
    # Degrees are usually bounded within [-180, 180] and [-90, 90]
    is_degree = (-185 <= min_x <= 185) and (-95 <= min_y <= 95)
    is_proj = (min_x > 1000 or min_x < -1000 or min_y > 1000 or min_y < -1000)
    
    return is_degree, is_proj, min_x, min_y, max_x, max_y

def main():
    print("🚀 [STAGE 57] Executing CONTROLLED SPATIAL GATE...")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sandbox_records = load_json(SANDBOX_REGISTRY_PATH).get("records", [])
    
    # Filter valid Stage 56 lineage
    eligible_records = [
        r for r in sandbox_records
        if r.get("sandbox_execution_status") in ["EXECUTABLE", "EXECUTABLE_WITH_LIMITATIONS"]
        and r.get("future_controlled_spatial_readiness") in ["READY_FOR_CONTROLLED_SPATIAL_GATE", "READY_WITH_LIMITATIONS"]
    ]
    
    # Trackers
    registry = []
    val_matrix = []
    crs_matrix = []
    ext_matrix = []
    blocker_list = []
    files_ready = []
    files_manual = []
    
    adm_count = 0
    adm_lim_count = 0
    amb_count = 0
    not_adm_count = 0
    
    ready_count = 0
    ready_lim_count = 0
    manual_count = 0
    blocked_count = 0
    
    for sr in sorted(eligible_records, key=lambda x: (x["file_name"], x["sha256"])):
        target_path = EVIDENCE_DIR / sr["source_path"]
        file_id = sr["file_id"]
        
        blockers = []
        limitations = sr.get("blocker_reasons", []) # Sandbox inherited
        
        # Base inheritances
        s56_exec = sr["sandbox_execution_status"]
        s56_elig = sr["future_controlled_spatial_readiness"]
        s56_conf = sr["confidence_class"]
        
        # Metrics
        tot_checked = 0
        v_count = 0
        inv_count = 0
        emp_count = 0
        mix_flag = False
        multi_flag = False
        
        crs_stat = "CRS_NOT_DECLARED"
        crs_val = None
        crs_ready = "UNSAFE"
        crs_risk = CRS_RISK_HIGH
        
        rng_prof = "UNREADABLE"
        ext_prof = None
        degen_flag = False
        susp_flag = False
        
        if not target_path.exists():
            blockers.append("FILE_NOT_FOUND")
            g_stat = STAT_NOT_ADM
            r_stat = READ_BLOCKED
            conf = "MINIMAL"
        else:
            payload = load_json(target_path)
            # Re-run extraction specifically to inspect actual ranges
            s_f, features = resolve_jsonpath(payload, sr["feature_extraction_path"])
            
            if s_f and features:
                if not isinstance(features, list): features = [features]
                
                g_path = sr["geometry_extraction_path"].replace("$.", "")
                
                # Check for explicit top-level crs in GeoJSON standard (sometimes it exists outside features)
                top_crs = payload.get("crs")
                if top_crs:
                    crs_stat = "EXPLICIT_CRS_FOUND"
                    crs_val = str(top_crs)
                
                g_types_seen = set()
                all_pts = []
                
                for f in features:
                    g_obj = f.get(g_path)
                    tot_checked += 1
                    
                    if g_obj is None:
                        emp_count += 1
                        continue
                        
                    t = g_obj.get("type")
                    c = g_obj.get("coordinates")
                    
                    if not t or not c:
                        inv_count += 1
                        continue
                        
                    v_count += 1
                    g_types_seen.add(t)
                    if "Multi" in t: multi_flag = True
                    
                    # Accumulate coords for extent calculation
                    extract_flat_coordinates(c, all_pts)
                
                if len(g_types_seen) > 1:
                    mix_flag = True
                    blockers.append("MIXED_GEOMETRY_TYPES")
                    
                if inv_count > 0: blockers.append("INVALID_GEOMETRY_DETECTED")
                if emp_count > 0: blockers.append("EMPTY_GEOMETRY_DETECTED")
                
                # CRS Assessment
                if "CRS_NOT_DECLARED" in limitations and crs_stat != "EXPLICIT_CRS_FOUND":
                    blockers.append("CRS_NOT_DECLARED")
                    blockers.append("CRS_REPROJECTION_UNSAFE")
                    crs_ready = "UNSAFE"
                    crs_risk = CRS_RISK_HIGH
                elif crs_stat == "EXPLICIT_CRS_FOUND":
                    crs_ready = "SAFE_FOR_TRANSLATION"
                    crs_risk = CRS_RISK_LOW
                    
                # Coordinate Range Assessment
                if all_pts:
                    xs = [p[0] for p in all_pts]
                    ys = [p[1] for p in all_pts]
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)
                    
                    is_deg = (-185 <= min_x <= 185) and (-95 <= min_y <= 95)
                    is_proj = (min_x > 1000 or min_x < -1000 or min_y > 1000 or min_y < -1000)
                    
                    if is_deg and not is_proj: rng_prof = "DEGREE_LIKE"
                    elif is_proj and not is_deg: rng_prof = "PROJECTED_LIKE"
                    else: 
                        rng_prof = "AMBIGUOUS"
                        blockers.append("COORDINATE_RANGE_AMBIGUOUS")
                        
                    ext_prof = {
                        "min_x": round(min_x, 6), "max_x": round(max_x, 6),
                        "min_y": round(min_y, 6), "max_y": round(max_y, 6)
                    }
                    
                    # Technical anomaly heuristics
                    width = max_x - min_x
                    height = max_y - min_y
                    if width == 0 and height == 0:
                        degen_flag = True
                        blockers.append("DEGENERATE_EXTENT")
                    elif is_deg and (width > 10 or height > 10):
                        # A single physical file covering 10 degrees is highly suspicious for our localized use case
                        susp_flag = True
                        blockers.append("EXTENT_SUSPICIOUS")
                        
            else:
                blockers.append("GEOMETRY_PARSE_FAILURE")
                
        if blockers:
            blockers = sorted(list(set(blockers)))
            
        blockers = sorted(list(set(blockers + limitations)))
        
        # Assignments
        if "FILE_NOT_FOUND" in blockers or "GEOMETRY_PARSE_FAILURE" in blockers:
            g_stat = STAT_NOT_ADM
            r_stat = READ_BLOCKED
            conf = "MINIMAL"
        elif "INVALID_GEOMETRY_DETECTED" in blockers or "DEGENERATE_EXTENT" in blockers:
            g_stat = STAT_AMB
            r_stat = READ_MANUAL
            conf = "LOW"
        elif "CRS_NOT_DECLARED" in blockers or "EXTENT_SUSPICIOUS" in blockers or "MIXED_GEOMETRY_TYPES" in blockers:
            g_stat = STAT_ADM_LIM
            r_stat = READ_LIM
            conf = "MEDIUM"
        else:
            g_stat = STAT_ADM
            r_stat = READ_MATCH
            conf = "HIGH"
            
        if "NO_BLOCKER" in blockers and len(blockers) > 1:
            blockers.remove("NO_BLOCKER")
        if not blockers: blockers.append("NO_BLOCKER")

        # Build Gate Record
        record = {
            "file_id": file_id,
            "file_name": sr["file_name"],
            "sha256": sr["sha256"],
            "source_path": sr["source_path"],
            
            "stage_56_sandbox_execution_status": s56_exec,
            "stage_56_future_controlled_spatial_readiness": s56_elig,
            "stage_56_confidence_class": s56_conf,
            
            "total_geometry_records_checked": tot_checked,
            "valid_geometry_count": v_count,
            "invalid_geometry_count": inv_count,
            "empty_geometry_count": emp_count,
            "mixed_geometry_type_flag": mix_flag,
            "multipart_geometry_flag": multi_flag,
            
            "crs_status": crs_stat,
            "explicit_crs_value": crs_val,
            "crs_reprojection_readiness": crs_ready,
            "crs_risk_class": crs_risk,
            
            "coordinate_range_profile": rng_prof,
            "extent_profile": ext_prof,
            "degenerate_extent_flag": degen_flag,
            "suspicious_extent_flag": susp_flag,
            
            "spatial_gate_status": g_stat,
            "future_controlled_matching_readiness": r_stat,
            "blocker_reasons": blockers,
            "confidence_class": conf,
            "notes": "Technical geometry bounds and CRS assessed. Ambiguity inherited correctly without masking."
        }
        
        registry.append(record)
        
        if g_stat == STAT_ADM: adm_count += 1
        elif g_stat == STAT_ADM_LIM: adm_lim_count += 1
        elif g_stat == STAT_AMB: amb_count += 1
        else: not_adm_count += 1
        
        if r_stat == READ_MATCH: ready_count += 1
        elif r_stat == READ_LIM: ready_lim_count += 1
        elif r_stat == READ_MANUAL: manual_count += 1
        else: blocked_count += 1
        
        val_matrix.append({
            "file_id": file_id,
            "total_geometry_records_checked": tot_checked,
            "valid_geometry_count": v_count,
            "invalid_geometry_count": inv_count,
            "empty_geometry_count": emp_count,
            "mixed_geometry_type_flag": mix_flag,
            "multipart_geometry_flag": multi_flag,
            "spatial_gate_status": g_stat
        })
        
        crs_matrix.append({
            "file_id": file_id,
            "crs_status": crs_stat,
            "explicit_crs_value": crs_val,
            "crs_reprojection_readiness": crs_ready,
            "crs_risk_class": crs_risk,
            "coordinate_range_profile": rng_prof
        })
        
        ext_matrix.append({
            "file_id": file_id,
            "extent_profile": ext_prof,
            "degenerate_extent_flag": degen_flag,
            "suspicious_extent_flag": susp_flag,
            "technical_extent_notes": "Extent evaluated inside sandbox boundaries only."
        })
        
        for b in blockers:
            if b != "NO_BLOCKER":
                blocker_list.append({"file_id": file_id, "blocker": b})
                
        if g_stat in [STAT_ADM, STAT_ADM_LIM] and r_stat in [READ_MATCH, READ_LIM]:
            files_ready.append(record)
        else:
            files_manual.append(record)
            
    # Verdict Evaluation
    if not eligible_records:
        overall_v = "NOT_READY"
    elif amb_count > 0 and (adm_count == 0 and adm_lim_count == 0):
        overall_v = "SPATIAL_GATE_PARTIAL"
    elif adm_count > 0 and not_adm_count == 0 and sum(1 for b in blocker_list if "CRS" in b["blocker"]) == 0:
        overall_v = "READY_FOR_CONTROLLED_MATCHING_GATE"
    elif adm_lim_count > 0 or adm_count > 0:
        overall_v = "SPATIAL_GATE_ADMISSIBLE_WITH_LIMITATIONS"
    else:
        overall_v = "NOT_READY"

    def write_out(name, data):
        with open(OUTPUT_DIR / f"{name}_{REGION_TAG}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    write_out("controlled_spatial_gate_registry", {"records": registry})
    write_out("geometry_validity_matrix", {"matrix": val_matrix})
    write_out("crs_projection_risk_matrix", {"matrix": crs_matrix})
    write_out("geometry_extent_profile", {"profiles": ext_matrix})
    write_out("controlled_spatial_blocker_register", {"blockers": blocker_list})
    write_out("geometry_ready_for_controlled_matching_gate", {"records": files_ready})
    write_out("geometry_manual_review_for_spatial_gate", {"records": files_manual})
    
    report = {
        "stage": "57",
        "mode": "CONTROLLED_SPATIAL_GATE",
        "files_considered": len(eligible_records),
        "files_processed": len(registry),
        "technically_admissible_count": adm_count,
        "admissible_with_limitations_count": adm_lim_count,
        "technically_ambiguous_count": amb_count,
        "not_technically_admissible_count": not_adm_count,
        "ready_for_controlled_matching_gate_count": ready_count,
        "ready_with_limitations_count": ready_lim_count,
        "needs_manual_spatial_review_count": manual_count,
        "blocked_for_spatial_stage_count": blocked_count,
        "overall_verdict": overall_v,
        "governance_summary": "Technical spatial validity verified. Unresolved CRS statuses securely preserved as High-Risk blockers without fallback guessing.",
        "safety_confirmation": "Confirmed: All extents / boundary boxes were analyzed technically inside the spatial testing sandbox. NO integration with operational Segment objects occurred."
    }
    
    with open(OUTPUT_DIR / "stage_57_controlled_spatial_gate_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("✅ Stage 57 Controlled Spatial Gate completed. Outputs saved.")
    print(f"Overall Verdict: {overall_v}")

if __name__ == "__main__":
    main()
