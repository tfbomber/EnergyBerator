#!/usr/bin/env python3
"""
field_04_plz_allocator.py
========================
Senior Planning Architect Baseline for FIELD_04 PV Social Proof.
Implements the PLZ-to-Segment Proportional Allocation model.

Truth Level: E3 (Allocated Proxy)
Architecture:
- Phase 1: Aggregation of MaStR CSV records by PLZ
- Phase 2: Proportional allocation to Segment Target
- Phase 3: Business Logic Mapping (Status, Signal, Score)
- Phase 4: Audit Artifact Emission

Logic anchored in field_04_plz_allocation_plan.md
"""

import pandas as pd
import json
import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')
logger = logging.getLogger("FIELD_04_ALLOCATOR")

# ---------------------------------------------------------------------------
# CONFIGURATION & BASELINES
# ---------------------------------------------------------------------------
PILOT_DEFAULTS = {
    "NEUSS_NORF_01": {
        "plz": "41470",
        "segment_building_count": 298,
        "plz_total_building_count": 4250, # Baseline estimate for 41470 (Neuss Norf/Rosellerheide)
        "city": "Neuss",
        "morphology_factor": 1.1          # Slight uplift for residential density suitability
    }
}

CSV_COLUMNS = [
    "field_id", "city", "segment_id", "source_truth_level", "location_accuracy",
    "allocation_method", "allocation_basis", "pv_installation_count_est",
    "pv_total_kwp_est", "pv_adoption_intensity_raw", "pv_adoption_status",
    "pv_signal_strength", "pv_adoption_score", "evidence_tier", "data_honesty_note"
]

def run_allocation(args):
    base_dir = Path(r"d:\Stock Analysis\D-Energy Berater\d-ess-engine")
    input_file = base_dir / "data" / "derived" / "mastr" / "mastr_solar_points_2026-03-12.csv"
    output_dir = base_dir / "output" / "field_04" / "runs"
    
    segment_id = args.segment_id
    if segment_id not in PILOT_DEFAULTS:
        logger.error(f"Segment {segment_id} not found in pilot defaults.")
        return

    config = PILOT_DEFAULTS[segment_id]
    target_plz = config["plz"]
    seg_buildings = config["segment_building_count"]
    plz_buildings = config["plz_total_building_count"]
    city = config["city"]
    morph_factor = config["morphology_factor"]

    # 1. Load & Aggregate MaStR Data
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    logger.info(f"Loading MaStR data from {input_file}...")
    df_mastr = pd.read_csv(input_file, dtype={'plz': str})
    
    # Filter for target PLZ
    df_plz = df_mastr[df_mastr['plz'] == target_plz]
    if df_plz.empty:
        logger.warning(f"No records found for PLZ {target_plz}. Allocation will yield 0.")
        plz_count = 0
        plz_kwp = 0.0
    else:
        plz_count = len(df_plz)
        plz_kwp = df_plz['kwp'].sum()
    
    logger.info(f"Target PLZ {target_plz} Truth: {plz_count} units, {round(plz_kwp, 1)} kWp")

    # 2. Arithmetic Allocation
    # Base Ratio = (Segment Buildings / PLZ Buildings) * Morphology
    base_ratio = (seg_buildings / plz_buildings)
    final_ratio = base_ratio * morph_factor
    
    # Force max constraint to prevent mathematical blowup
    final_ratio = min(final_ratio, 1.0)
    
    pv_est = round(plz_count * final_ratio)
    kwp_est = round(plz_kwp * final_ratio, 1)
    intensity = pv_est / seg_buildings if seg_buildings > 0 else 0
    
    logger.info(f"Allocation complete. Result: {pv_est} units, {kwp_est} kWp")

    # 3. Business Logic Mapping
    # Adoption Status
    if intensity > 0.15: status = "STRONG"
    elif intensity > 0.05: status = "MODERATE"
    else: status = "WEAK"
    
    # Signal Strength (Confidence)
    # We use MEDIUM because it's an allocation but based on hard PLZ truth
    signal = "MEDIUM"
    
    # Adoption Score (Normalized 0-100 logic)
    # Benchmark: 20% intensity = 100 points
    # BUT for E3 (Allocated Proxy), we enforce an evidence penalty and score cap.
    raw_score = round(min(intensity / 0.20, 1.0) * 100, 1)
    
    # E3 Confidence Constraint Enforcement
    confidence_penalty_factor = 0.5
    e3_max_allowable_score = 50.0
    
    penalized_score = min(raw_score * confidence_penalty_factor, e3_max_allowable_score)
    adoption_score = round(penalized_score, 1)
    
    # 4. Construct Audit Payload
    report = {
        "field_id": "FIELD_04",
        "city": city,
        "segment_id": segment_id,
        "source_truth_level": "POSTAL_CODE_AGGREGATE",
        "location_accuracy": "ALLOCATED_PROXY",
        "allocation_method": "LINEAR_PROPORTIONAL",
        "allocation_basis": "BUILDING_COUNT_RATIO",
        "pv_installation_count_est": int(pv_est),
        "pv_total_kwp_est": float(kwp_est),
        "pv_adoption_intensity_raw": round(intensity, 4),
        "pv_adoption_status": status,
        "pv_signal_strength": signal,
        "pv_adoption_score": adoption_score,
        "evidence_tier": "E3",
        "estimation_nature": {
            "pv_count_estimation_type": "PLZ_ALLOCATION",
            "pv_kwp_estimation_type": "PLZ_ALLOCATION",
            "spatial_confirmability": "UNCONFIRMABLE_AT_POINT_LEVEL",
            "spatial_truth_scope": "POSTAL_CODE_LEVEL",
            "proxy_distribution_assumption": "UNIFORM_BUILDING_DISTRIBUTION"
        },
        "confidence_evidence_layer": {
            "evidence_confidence_level": "LIMITED_PROXY",
            "confidence_penalty_applied": True,
            "confidence_penalty_factor": confidence_penalty_factor,
            "score_cap_applied": True,
            "score_cap_basis": "E3_MAX_ALLOWABLE_SCORE",
            "max_score_allowed_by_evidence_tier": e3_max_allowable_score
        },
        "audit_use_constraints": {
            "allowed_for_segment_level_ranking": True,
            "allowed_for_social_proof_proxy_display": True,
            "allowed_for_point_level_installation_claims": False,
            "allowed_for_street_level_targeting": False,
            "allowed_for_subsegment_spatial_clustering": False
        },
        "narrative_honesty": {
            "business_interpretation": "Segment exhibits strong PV adoption intensity at the aggregate PLZ level, but exact point-specific installations within the segment cannot be verified.",
            "audit_conclusion": "Evidence tier E3 triggers automatic confidence penalty and score capping. Allocated proxy metrics must not be presented as exact observations."
        },
        "data_honesty_note": "Score is an allocated proxy derived from PLZ-level data. Exact spatial coordinates are currently unavailable. Figures represent statistical probability, not point-confirmed installations.",
        "metadata": {
            "plz_basis": target_plz,
            "plz_total_pv_units": plz_count,
            "plz_total_pv_kwp": round(plz_kwp, 1),
            "denominator_segment_buildings": seg_buildings,
            "denominator_plz_buildings": plz_buildings,
            "morphology_factor_applied": morph_factor,
            "run_timestamp": datetime.now(timezone.utc).isoformat()
        }
    }

    # 5. Emit Artifact
    run_id = f"RUN_FIELD04_ALLOC_{segment_id}_{datetime.now().strftime('%Y%m%d_%H%M')}"
    os.makedirs(output_dir, exist_ok=True)
    out_path = output_dir / f"{run_id}.json"
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Final E3 Audit Report saved to {out_path}")
    print("\n" + "="*60)
    print(f" FIELD_04 ALLOCATION SUCCESS: {segment_id}")
    print("="*60)
    print(f" Estimated PV Units  : {pv_est}")
    print(f" Estimated Total kWp : {kwp_est}")
    print(f" Adoption Intensity  : {round(intensity*100, 2)}%")
    print(f" Evidence Tier       : E3 (ALLOCATED)")
    print(f" Output Path         : {out_path}")
    print("="*60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FIELD_04 PLZ-level Proportional Allocator")
    parser.add_argument("--segment-id", default="NEUSS_NORF_01", help="Target Segment ID")
    run_allocation(parser.parse_args())
