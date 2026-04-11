import pandas as pd
import numpy as np
import os
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Field01_Audit")

def run_audit():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    segments_path = os.path.join(base_dir, "data", "segments.parquet")
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    if not os.path.exists(segments_path):
        logger.error(f"Segments data not found at {segments_path}")
        return

    logger.info(f"Loading segment data from {segments_path}...")
    df = pd.read_parquet(segments_path)
    
    audit_results = {
        "total_segments_analyzed": len(df),
        "segments_excluded_non_residential": 0,
        "segments_with_errors": 0,
        "segments_with_warnings": 0,
        "flags": []
    }

    report_lines = []
    report_lines.append("# Audit Report: Field 01 Lite — Segment PV Potential Proxy")
    report_lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("\n## Audit Summary")

    # Task A & G: Data Integrity & Error Classification
    checks_df = df.copy()
    checks_df['anomaly_flags'] = ""
    checks_df['explanation'] = ""

    # Dominant Type
    def get_dominant(row):
        ratios = {
            'detached': row.get('detached_ratio', 0),
            'semi': row.get('semi_ratio', 0),
            'rowhouse': row.get('rowhouse_ratio', 0)
        }
        return max(ratios, key=ratios.get) if any(ratios.values()) else "unknown"

    checks_df['dominant_building_type'] = checks_df.apply(get_dominant, axis=1)

    segments_table = []
    
    for idx, row in checks_df.iterrows():
        s_id = row['segment_id']
        flags = []
        explanations = []

        # Task A: Non-residential
        if row['building_count'] == 0:
            flags.append("non_residential_segment")
            explanations.append("No buildings found in segment.")
            audit_results["segments_excluded_non_residential"] += 1
            continue

        # Task B: Geometry Consistency
        if row['roof_pool_area_m2'] > 1.1 * row['segment_area_m2']:
            flags.append("geometry_error")
            explanations.append(f"Roof area ({row['roof_pool_area_m2']:.1f}) exceeds segment area ({row['segment_area_m2']:.1f}) by >10%.")
            audit_results["segments_with_errors"] += 1

        # Task C: Mathematical Consistency
        if row['roof_pool_adjusted_m2'] > row['roof_pool_area_m2'] + 0.01: # Small epsilon
            flags.append("utilization_calculation_error")
            explanations.append("Adjusted area exceeds raw roof area.")
            audit_results["segments_with_errors"] += 1

        # Task E: Distribution Sanity
        if row['pv_segment_score'] < 0.05 or row['pv_segment_score'] > 0.60:
            flags.append("distribution_anomaly")
            explanations.append(f"Score {row['pv_segment_score']:.4f} outside expected residential range [0.05, 0.60].")
            audit_results["segments_with_warnings"] += 1

        # Task D: Structural Consistency (Warning if detached but low score compared to others)
        # (This is harder to test with a single segment, but we flag if score is extremely low for detached)
        if row['dominant_building_type'] == 'detached' and row['pv_segment_score'] < 0.10:
             flags.append("structural_warning")
             explanations.append("Detached dominant segment has unexpectedly low PV score.")
             audit_results["segments_with_warnings"] += 1

        checks_df.at[idx, 'anomaly_flags'] = ", ".join(flags)
        checks_df.at[idx, 'explanation'] = "; ".join(explanations)
        
        segments_table.append({
            "segment_id": s_id,
            "building_count": int(row['building_count']),
            "dominant": row['dominant_building_type'],
            "seg_area": round(row['segment_area_m2'], 1),
            "roof_area": round(row['roof_pool_area_m2'], 1),
            "adj_area": round(row['roof_pool_adjusted_m2'], 1),
            "score": round(row['pv_segment_score'], 4),
            "flags": ", ".join(flags)
        })

    # Task H: Final Audit Conclusion
    conclusion = "PASS"
    if audit_results["segments_with_errors"] > 0:
        conclusion = "FAIL"
    elif audit_results["segments_with_warnings"] > 0:
        conclusion = "PASS_WITH_WARNINGS"

    report_lines.append(f"- **Final Verdict**: {conclusion}")
    report_lines.append(f"- Total segments: {audit_results['total_segments_analyzed']}")
    report_lines.append(f"- Excluded (non-res): {audit_results['segments_excluded_non_residential']}")
    report_lines.append(f"- With Errors: {audit_results['segments_with_errors']}")
    report_lines.append(f"- With Warnings: {audit_results['segments_with_warnings']}")
    
    scores = checks_df[checks_df['building_count'] > 0]['pv_segment_score']
    if not scores.empty:
        report_lines.append(f"- Score Distribution: min={scores.min():.4f}, median={scores.median():.4f}, max={scores.max():.4f}")

    # Task F: Summary Table (Allerheiligen)
    report_lines.append("\n## Allerheiligen Pilot Summary")
    pilot_df = pd.DataFrame(segments_table)
    if not pilot_df.empty:
        pilot_df = pilot_df.sort_values(by="score", ascending=False)
        report_lines.append(pilot_df.to_markdown(index=False))

    # Task G: detailed anomaly log
    if any(checks_df['anomaly_flags'] != ""):
        report_lines.append("\n## Anomaly Details")
        anomalies = checks_df[checks_df['anomaly_flags'] != ""][['segment_id', 'anomaly_flags', 'explanation']]
        report_lines.append(anomalies.to_markdown(index=False))

    report_path = os.path.join(reports_dir, "field_01_lite_audit_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    
    logger.info(f"Audit complete. Report saved to {report_path}")
    print(f"AUDIT_RESULT={conclusion}")

if __name__ == "__main__":
    run_audit()
