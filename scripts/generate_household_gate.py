"""
generate_household_gate.py
==========================
PHASE 7 - ISOLATED SIMULATION ONLY. NO UI CHANGES. NO RANKING CHANGES.
4-Tier Household Sales Suitability Gate for the Neuss Territory Radar.

Input: output/proxy/sfh_mfh_cluster_proxy_summary.csv + neuss_hybrid_clusters_v1.json + stage6_segment_explainer.csv
Output: output/gate/household_gate_results.csv + tier candidate CSVs + impact_report.txt

Tiers:
  2.1  MFH_CERTAIN / EXCLUDE       -> mfh_risk_score high, little SFH evidence
  2.2  MFH_HEAVY / LOW_PRIORITY    -> notable MFH risk, poor fit for door-to-door HH outreach
  2.3  MOSTLY_SFH_OR_MIXED / NEUTRAL -> active, no strong promotion or suppression
  2.4  SFH_STRONG / PRIORITY       -> owner-decision-friendly, prioritize household outreach
"""

import os
import sys
import json
import math
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")
logger = logging.getLogger("HouseholdGate")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Neuss city center reference (Neuss Markt / Hauptbahnhof approx.)
NEUSS_CENTER_LAT = 51.198
NEUSS_CENTER_LON = 6.689
# Soft inner city radius in meters (<= this distance = inner city MFH prior uplift)
INNER_CITY_RADIUS_M = 800.0
# Soft MFH uplift for inner-city clusters (only if signals are neutral, not decisive)
INNER_CITY_UPLIFT = 0.08

# Weights for mfh_risk_score:
#   mfh_tag_ratio is the strongest signal (OSM has explicitly labeled apartments)
#   medium-large footprint band captures German Mehrfamilienhaus missed by >400m cutoff
#   high-rise: auxiliary
W_MFH_TAG = 0.55
W_MFH_FOOTPRINT_BAND = 0.30   # footprint band 200-1000m² weighted ratio
W_MFH_HIGHRISE = 0.15

# Weights for sfh_strength_score:
W_SFH_TAG = 0.50              # house, detached, terrace all explicitly SFH-intent
W_SFH_SMALL_FP = 0.30         # small footprint ratio
W_SFH_LOWRISE = 0.20          # low-rise ratio (only when tag coverage > 20%)

# Tier thresholds
MFH_CERTAIN_THRESHOLD = 0.55   # mfh_risk_score >= this -> 2.1 if sfh_strength is also low
MFH_HEAVY_THRESHOLD = 0.35    # mfh_risk_score >= this -> 2.2
SFH_STRONG_THRESHOLD = 0.60   # sfh_strength_score >= this AND mfh_risk_score below 0.25 -> 2.4


def haversine_m(lat1, lon1, lat2, lon2):
    """Compute distance in meters between two WGS84 points."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def compute_medium_large_fp_ratio(row):
    """
    Medium-large footprint band proxy [200-1000m²].
    Uses median_footprint_m2 as a cluster-level heuristic.
    For per-building ratios we don't have exact distribution, so we use
    large_footprint_ratio (>400m²) as the floor and augment with median signal.
    """
    large_r = row["large_footprint_ratio"]
    median_fp = row["median_footprint_m2"]
    # If median footprint is between 200 and 400m² and large_ratio is 0, it still signals MFH-leaning
    medium_signal = max(0.0, (median_fp - 150.0) / 250.0)  # Scales from 0 at 150m² to 1.0 at 400m²
    medium_signal = min(medium_signal, 1.0) * (1.0 - large_r)  # Avoid double-counting
    return large_r + medium_signal * 0.5  # medium_signal at half weight vs confirmed large


def assign_gate_tier(mfh_risk: float, sfh_strength: float, inner_city: bool) -> tuple:
    """
    Returns (tier_label, tier_code, weight, reason)
    """
    # Apply city-center soft uplift only when signals are ambiguous (both scores < 0.35)
    adjusted_mfh = mfh_risk
    center_note = ""
    if inner_city and mfh_risk < 0.35 and sfh_strength < 0.45:
        adjusted_mfh = mfh_risk + INNER_CITY_UPLIFT
        center_note = " [inner-city prior +{:.2f}]".format(INNER_CITY_UPLIFT)
    
    # 2.1: MFH_CERTAIN / EXCLUDE
    # High MFH risk AND low SFH evidence
    if adjusted_mfh >= MFH_CERTAIN_THRESHOLD and sfh_strength < 0.35:
        return ("MFH_CERTAIN", "2.1", 0.0,
                f"mfh_risk={adjusted_mfh:.2f}≥{MFH_CERTAIN_THRESHOLD}, sfh_strength={sfh_strength:.2f}<0.35{center_note}")

    # 2.2: MFH_HEAVY / LOW_PRIORITY
    # Notable MFH risk (even if some SFH signals present)
    if adjusted_mfh >= MFH_HEAVY_THRESHOLD:
        return ("MFH_HEAVY", "2.2", 0.60,
                f"mfh_risk={adjusted_mfh:.2f}≥{MFH_HEAVY_THRESHOLD}{center_note}")

    # 2.4: SFH_STRONG / PRIORITY
    # Strong SFH evidence AND very low MFH risk
    if sfh_strength >= SFH_STRONG_THRESHOLD and adjusted_mfh < 0.25:
        return ("SFH_STRONG", "2.4", 1.10,
                f"sfh_strength={sfh_strength:.2f}≥{SFH_STRONG_THRESHOLD}, mfh_risk={adjusted_mfh:.2f}<0.25{center_note}")

    # 2.3: Default NEUTRAL (includes moderate SFH signals, ambiguous areas, low-metadata clusters)
    return ("MOSTLY_MIXED", "2.3", 1.00,
            f"mfh_risk={adjusted_mfh:.2f}, sfh_strength={sfh_strength:.2f} — neutral zone{center_note}")


def main():
    logger.info("Starting Household Sales Suitability Gate Simulation")

    # --- Load Data ---
    proxy_path = os.path.join(BASE_DIR, "output", "proxy", "sfh_mfh_cluster_proxy_summary.csv")
    clusters_path_v2 = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v2.json")
    clusters_path_v1 = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v1.json")
    clusters_path = clusters_path_v2 if os.path.exists(clusters_path_v2) else clusters_path_v1
    explainer_path = os.path.join(BASE_DIR, "output", "stage6", "stage6_segment_explainer.csv")
    logger.info(f"[ClusterFeed] Using: {os.path.basename(clusters_path)}")

    for p in [proxy_path, clusters_path, explainer_path]:
        if not os.path.exists(p):
            logger.error(f"Required file missing: {p}")
            sys.exit(1)

    df_proxy = pd.read_csv(proxy_path)
    with open(clusters_path, "r", encoding="utf-8") as f:
        clusters_data = json.load(f)
    df_clusters = pd.DataFrame(clusters_data)
    df_explainer = pd.read_csv(explainer_path)

    # Join to get centroid and opportunity_score
    df_merged = df_clusters.merge(df_explainer, on="segment_id", how="left")
    df_all = df_proxy.merge(
        df_merged[["cluster_id", "cluster_centroid_lat", "cluster_centroid_lon", "opportunity_score"]].drop_duplicates("cluster_id"),
        on="cluster_id", how="left"
    )

    logger.info(f"Loaded {len(df_all)} proxy clusters for gate simulation.")

    results = []
    for _, row in df_all.iterrows():
        # --- Compute mfh_risk_score ---
        mfh_fp_band = compute_medium_large_fp_ratio(row)

        high_rise_r = row["high_rise_ratio"] if pd.notna(row["high_rise_ratio"]) else 0.0
        low_rise_r = row["low_rise_ratio"] if pd.notna(row["low_rise_ratio"]) else 0.0
        mfh_tag_r = row["mfh_tag_ratio"] if pd.notna(row["mfh_tag_ratio"]) else 0.0
        sfh_tag_r = row["sfh_tag_ratio"] if pd.notna(row["sfh_tag_ratio"]) else 0.0
        small_fp_r = row["small_footprint_ratio"] if pd.notna(row["small_footprint_ratio"]) else 0.0

        mfh_risk = (
            W_MFH_TAG * mfh_tag_r +
            W_MFH_FOOTPRINT_BAND * mfh_fp_band +
            W_MFH_HIGHRISE * high_rise_r
        )

        # --- Compute sfh_strength_score ---
        # Scale available weights: low_rise only counts if levels metadata is present
        level_coverage = 1.0 if (low_rise_r > 0 or high_rise_r > 0) else 0.0
        if level_coverage > 0:
            sfh_strength = (
                W_SFH_TAG * sfh_tag_r +
                W_SFH_SMALL_FP * small_fp_r +
                W_SFH_LOWRISE * low_rise_r
            )
        else:
            # Re-normalize without levels signal
            adj_w_tag = W_SFH_TAG / (W_SFH_TAG + W_SFH_SMALL_FP)
            adj_w_fp = W_SFH_SMALL_FP / (W_SFH_TAG + W_SFH_SMALL_FP)
            sfh_strength = adj_w_tag * sfh_tag_r + adj_w_fp * small_fp_r

        # --- City center prior ---
        lat = row.get("cluster_centroid_lat")
        lon = row.get("cluster_centroid_lon")
        inner_city = False
        dist_m = None
        if pd.notna(lat) and pd.notna(lon):
            dist_m = haversine_m(float(lat), float(lon), NEUSS_CENTER_LAT, NEUSS_CENTER_LON)
            inner_city = dist_m <= INNER_CITY_RADIUS_M

        # --- Assign Gate Tier ---
        tier_label, tier_code, tier_weight, reason = assign_gate_tier(mfh_risk, sfh_strength, inner_city)

        # Gated score (for simulation only, does NOT modify main pipeline)
        opp_score = row.get("opportunity_score", 0.0)
        if pd.isna(opp_score):
            opp_score = 0.0
        gated_score = round(float(opp_score) * tier_weight, 4)

        results.append({
            "cluster_id": row["cluster_id"],
            "street_name": row["street_name"],
            "building_count": row["building_count"],
            "opportunity_score": round(float(opp_score), 4),
            "mfh_risk_score": round(mfh_risk, 3),
            "sfh_strength_score": round(sfh_strength, 3),
            "inner_city": inner_city,
            "dist_to_center_m": round(dist_m, 0) if dist_m else None,
            "gate_tier": tier_code,
            "gate_label": tier_label,
            "gate_weight": tier_weight,
            "gated_opportunity_score": gated_score,
            "reason": reason
        })

    df_gate = pd.DataFrame(results)

    # --- Output ---
    gate_dir = os.path.join(BASE_DIR, "output", "gate")
    os.makedirs(gate_dir, exist_ok=True)

    gate_summary_path = os.path.join(gate_dir, "household_gate_results.csv")
    df_gate.to_csv(gate_summary_path, index=False)

    for tier_code, tier_label in [("2.1", "exclude"), ("2.2", "low_priority"), ("2.3", "neutral"), ("2.4", "priority")]:
        tier_df = df_gate[df_gate["gate_tier"] == tier_code].sort_values("opportunity_score", ascending=False)
        tier_df.to_csv(os.path.join(gate_dir, f"gate_{tier_label}.csv"), index=False)

    # --- Impact Report ---
    total = len(df_gate)
    top50 = df_gate.sort_values("opportunity_score", ascending=False).head(50)
    top100 = df_gate.sort_values("opportunity_score", ascending=False).head(100)

    tier_counts = df_gate["gate_tier"].value_counts().to_dict()
    sfh_bldg = df_gate[df_gate["gate_tier"] == "2.4"]["building_count"].sum()
    mfh21_count = tier_counts.get("2.1", 0)
    mfh22_count = tier_counts.get("2.2", 0)
    neutral_count = tier_counts.get("2.3", 0)
    sfh_count = tier_counts.get("2.4", 0)

    report_lines = [
        "=" * 60,
        "HOUSEHOLD SALES SUITABILITY GATE — SIMULATION IMPACT REPORT",
        "=" * 60,
        f"Total clusters simulated: {total}",
        "",
        "=== 1. Tier Distribution ===",
        f"  2.1 MFH_CERTAIN / EXCLUDE:     {mfh21_count:>4} ({mfh21_count/total:.1%})",
        f"  2.2 MFH_HEAVY  / LOW_PRIORITY: {mfh22_count:>4} ({mfh22_count/total:.1%})",
        f"  2.3 MOSTLY_MIXED / NEUTRAL:    {neutral_count:>4} ({neutral_count/total:.1%})",
        f"  2.4 SFH_STRONG / PRIORITY:     {sfh_count:>4} ({sfh_count/total:.1%})",
        "",
        "=== 2. Top 50 Tier Redistribution ===",
    ]
    for t_code, t_lbl in [("2.1","EXCLUDE"), ("2.2","LOW_PRI"), ("2.3","NEUTRAL"), ("2.4","PRIORITY")]:
        n = len(top50[top50["gate_tier"] == t_code])
        report_lines.append(f"  {t_code} {t_lbl}: {n} ({n/50:.1%})")

    report_lines += ["", "=== 3. Top 100 Tier Redistribution ==="]
    for t_code, t_lbl in [("2.1","EXCLUDE"), ("2.2","LOW_PRI"), ("2.3","NEUTRAL"), ("2.4","PRIORITY")]:
        n = len(top100[top100["gate_tier"] == t_code])
        report_lines.append(f"  {t_code} {t_lbl}: {n} ({n/100:.1%})")

    report_lines += [
        "",
        "=== 4. Building Count Coverage ===",
        f"  2.4 SFH_STRONG total buildings: {sfh_bldg}",
        f"  (Acceptance threshold: >= 4000 buildings)",
        f"  STATUS: {'PASS' if sfh_bldg >= 4000 else 'FAIL — too conservative'}",
    ]
    supp_pct = len(top50[top50["gate_tier"].isin(["2.1","2.2"])]) / 50
    supp_status = "PASS" if supp_pct <= 0.30 else "WARN — review thresholds"
    report_lines += [
        "",
        "=== 5. Suppression Risk Check ===",
        f"  2.1+2.2 combined (% of Top 50): {supp_pct:.1%}",
        f"  (Acceptance threshold: <= 30% of Top 50)",
        f"  STATUS: {supp_status}",
        "",
        "=== 6. Inner City Prior Coverage ===",
        f"  Clusters with inner_city=True: {df_gate['inner_city'].sum()}",
        f"  Of those pushed to 2.1 or 2.2: {len(df_gate[(df_gate['inner_city']==True) & (df_gate['gate_tier'].isin(['2.1','2.2']))])}",
        "=" * 60,
    ]

    report_path = os.path.join(gate_dir, "impact_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # Print to terminal
    print("\n".join(report_lines))
    logger.info(f"Gate simulation complete. Results written to {gate_dir}")


if __name__ == "__main__":
    main()
