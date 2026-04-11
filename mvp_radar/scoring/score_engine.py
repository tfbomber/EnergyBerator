import os
import pandas as pd
import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MVP_BASE = os.path.join(ROOT_DIR, "mvp_radar")
FEATURE_CSV = os.path.join(MVP_BASE, "outputs", "area_features.csv")
OUTPUT_CSV = os.path.join(MVP_BASE, "outputs", "area_scores.csv")
TOP_AREAS_CSV = os.path.join(MVP_BASE, "outputs", "top_areas_neuss.csv")

def ensure_scalar(val, default):
    return default if pd.isna(val) else val

def run_scoring():
    if not os.path.exists(FEATURE_CSV):
        print("Required inputs missing. Run build_area_features.py first.")
        return

    df = pd.read_csv(FEATURE_CSV)
    scored_records = []

    for _, row in df.iterrows():
        area_id = row.get("area_id")
        
        # Core data extraction
        sfh_str = row.get("sfh_strength_score")
        sfh_abs = row.get("sfh_absolute_count")
        mfh_risk = row.get("mfh_risk_score")
        purity_val = row.get("purity_score_final")
        purity_flag = row.get("purity_flag")
        lead_count = row.get("lead_count")
        bldg_count = row.get("building_count")
        vol_band = row.get("deployable_volume_band")
        a_count = row.get("A_count")
        
        plz = row.get("PLZ", "UNKNOWN")
        stadtteil = row.get("Stadtteil", "UNKNOWN")
        purity_adj_label = row.get("purity_adjusted_label")

        # [ZERO_INFERENCE] Strict Null Prevention. If explicitly required elements are missing, score is NULL.
        required = [sfh_str, sfh_abs, mfh_risk, purity_val, lead_count, vol_band]
        if any(pd.isna(x) or x is None for x in required):
            scored_records.append({
                "area_id": area_id,
                "general_priority_score": None,
                "priority_band": "SIGNAL_MISSING",
                "classification": "INCOMPLETE_DATA",
                "PLZ": plz, "Stadtteil": stadtteil,
                "structure_signal": "MISSING", "purity_signal": "MISSING", "scale_signal": "MISSING",
                "why_this_area": "Data incomplete. System triggered zero inference guardrail.",
                "holds_back": "Missing vital scoring signals.",
                "reason_struc": "N/A", "reason_pur": "N/A", "reason_scale": "N/A"
            })
            continue

        # Data coercion for math
        sfh_str, sfh_abs, mfh_risk, purity_val = float(sfh_str), float(sfh_abs), float(mfh_risk), float(purity_val)
        lead_count, bldg_count, a_count = float(lead_count), float(ensure_scalar(bldg_count, 0)), float(ensure_scalar(a_count, 0))

        # 1. Structure Score
        struc_score = (sfh_str * 40.0) + (min(sfh_abs / 150.0, 1.0) * 60.0)

        # 2. Purity Score
        pur_base = (purity_val * 100.0) - (mfh_risk * 50.0)
        if purity_flag == "DOWNGRADED":
            pur_base -= 10.0
        pur_score = max(0.0, min(100.0, pur_base))

        # 3. Scale Score
        bscan = {"S": 20, "M": 50, "L": 80, "XL": 100}.get(str(vol_band), 20)
        scale_score = min(bscan * 0.5 + min(lead_count / 100.0, 1.0) * 30.0 + min(a_count / 20.0, 1.0) * 20.0, 100.0)

        # Final Base Model
        raw_gen_score = (struc_score * 0.4) + (pur_score * 0.2) + (scale_score * 0.4)
        
        # 4-Decimal Precision requirement
        gen_score = round(raw_gen_score, 4)

        # Classification Banding
        if gen_score >= 70.0:
            classification = "STRONG_GENERAL_CANDIDATE"
            band = "A_TIER_IMMEDIATE"
        elif gen_score >= 50.0:
            classification = "REVIEW_GENERAL_CANDIDATE"
            band = "B_TIER_SECONDARY"
        else:
            classification = "WEAK_GENERAL_CANDIDATE"
            band = "C_TIER_OPPORTUNISTIC"

        # Explicit UI Reason mappings (no templates, native data injection)
        r_struc = f"Strong cluster: {int(sfh_abs)} SFH units identified (Score: {sfh_str:.0%})" if sfh_abs >= 50 else f"Small structural footprint: {int(sfh_abs)} SFH units (Score: {sfh_str:.0%})"
        r_pur = f"Highly pure context: MFH risk is {mfh_risk:.2f}" if mfh_risk < 0.1 else f"Mixed context: MFH risk is {mfh_risk:.2f}"
        if purity_flag == "DOWNGRADED":
            r_pur += " [Gate Downgraded]"
            
        r_scale = f"Scale {vol_band} with {int(lead_count)} deployable leads."

        why_good = f"Balanced structurally with {int(lead_count)} leads in {vol_band}-band scale." if gen_score >= 50.0 else "Volume metrics do not surpass friction threshold."
        holds_back = "None." if classification == "STRONG_GENERAL_CANDIDATE" else ("Structural mass too tiny to dominate." if sfh_abs < 50 else "High friction environment.")

        scored_records.append({
            "area_id": area_id,
            "general_priority_score": gen_score,
            "priority_band": band,
            "classification": classification,
            "PLZ": plz,
            "Stadtteil": stadtteil,
            "structure_signal": round(struc_score, 2),
            "purity_signal": round(pur_score, 2),
            "scale_signal": round(scale_score, 2),
            "why_this_area": why_good,
            "holds_back": holds_back,
            "reason_struc": r_struc,
            "reason_pur": r_pur,
            "reason_scale": r_scale
        })

    out_df = pd.DataFrame(scored_records)
    out_df.to_csv(OUTPUT_CSV, index=False)
    
    # Generate Top Areas Deliverable
    # Exclude SIGNAL_MISSING
    valid_df = out_df[out_df["priority_band"] != "SIGNAL_MISSING"].copy()
    valid_df = valid_df.sort_values(by="general_priority_score", ascending=False).reset_index(drop=True)
    valid_df.insert(0, 'rank', range(1, 1 + len(valid_df)))
    
    valid_df.to_csv(TOP_AREAS_CSV, index=False)
    print(f"General Base Model scores calculated and exported. Top 10 generated at {TOP_AREAS_CSV}")

if __name__ == "__main__":
    run_scoring()
