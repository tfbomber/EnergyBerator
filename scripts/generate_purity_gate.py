"""
generate_purity_gate.py
=======================
PHASE 8 — OFFLINE SIMULATION ONLY. NO UI CHANGES. NO PIPELINE CHANGES.
2.4 Purity Gate: identify SFH_STRONG clusters embedded in MFH-heavy context.

Signal Architecture:
  Primary   (0.55): local MFH pressure from K=5 nearest clusters (distance-decay weighted)
  Secondary (0.20): smooth inner-city prior (distance decay to 1200m)
  Tertiary  (max 0.15 effective): street semantics fallback (functional zones only)

Thresholds compared: 0.50 / 0.55 / 0.60
"""

import os
import sys
import json
import math
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")
logger = logging.getLogger("PurityGate")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "output", "purity_gate")

# Neuss city center
NEUSS_CENTER_LAT = 51.198
NEUSS_CENTER_LON = 6.689
INNER_CITY_FADE_M = 1200.0  # smooth decay fades to 0 at this radius

# K-nearest neighbors for local MFH pressure
K_NEIGHBORS = 5

# Street semantics (functional zones only; Ring/Allee excluded)
SEMANTIC_NEGATIVE = {
    "hafen": 0.35, "bahnhof": 0.30, "bahn": 0.30,
    "industrie": 0.28, "gewerbe": 0.28,
    "gladbacher": 0.20, "krefelder": 0.20, "düsseldorfer": 0.20,
    "kölner": 0.20, "jülicher": 0.20,
    "daimler": 0.25, "porsche": 0.25, "benz": 0.25,
}
SEMANTIC_POSITIVE = {
    "weg": -0.04, "pfad": -0.04, "hof": -0.04, "garten": -0.04,
}
SEMANTIC_WEIGHT = 0.25
SEMANTIC_CAP = 0.15

# Threshold labels
THRESHOLDS = [
    (0.60, "t060", "Aggressive"),
    (0.55, "t055", "Moderate"),
    (0.50, "t050", "Conservative"),
]

# Acceptance criteria: clusters that MUST downgrade at 0.55+0.60
MUST_DOWNGRADE = ["gladbacher straße", "daimlerstraße", "porschestraße"]
# Clusters that MUST NOT downgrade under 0.55
MUST_STAY = ["mergelsweg", "im stüttgesfeld"]


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def compute_semantic(street_name: str):
    name_lower = street_name.lower()
    raw_penalty = 0.0
    for kw, val in SEMANTIC_NEGATIVE.items():
        if kw in name_lower:
            raw_penalty = max(raw_penalty, val)
    for kw, val in SEMANTIC_POSITIVE.items():
        if name_lower.endswith(kw) or f" {kw}" in name_lower:
            raw_penalty += val  # can go negative (reduction)
    raw_penalty = max(0.0, raw_penalty)
    capped = min(SEMANTIC_WEIGHT * raw_penalty, SEMANTIC_CAP)
    return raw_penalty, capped


def main():
    logger.info("Starting Phase 8: 2.4 Purity Gate Simulation")

    gate_path = os.path.join(BASE_DIR, "output", "gate", "household_gate_results.csv")
    if not os.path.exists(gate_path):
        logger.error(f"Gate results not found: {gate_path}")
        sys.exit(1)

    df = pd.read_csv(gate_path)
    total_all = len(df)
    immutable_count = len(df[df["gate_tier"].isin([2.1, 2.2])])
    df_24 = df[df["gate_tier"] == 2.4].copy().reset_index(drop=True)
    df_other = df[df["gate_tier"] != 2.4].copy()

    # Re-join centroid coordinates from clusters JSON (not stored in gate CSV)
    clusters_path_v2 = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v2.json")
    clusters_path_v1 = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v1.json")
    clusters_path = clusters_path_v2 if os.path.exists(clusters_path_v2) else clusters_path_v1
    logger.info(f"[ClusterFeed] Using: {os.path.basename(clusters_path)}")
    if not os.path.exists(clusters_path):
        logger.error(f"Clusters file not found: {clusters_path}")
        sys.exit(1)
    import json as _json
    with open(clusters_path, "r", encoding="utf-8") as f:
        raw_clusters = _json.load(f)
    df_clusters = pd.DataFrame(raw_clusters)[["cluster_id", "cluster_centroid_lat", "cluster_centroid_lon"]]
    df_24 = df_24.merge(df_clusters, on="cluster_id", how="left")
    # Also merge coords into full df for building the neighbor lookup
    df = df.merge(df_clusters, on="cluster_id", how="left")

    logger.info(f"Total clusters: {total_all} | 2.4 candidates: {len(df_24)} | Others (immutable): {len(df_other)}")

    # Build coordinate lookup for ALL clusters for neighbor search
    coord_cols = ["cluster_id", "cluster_centroid_lat", "cluster_centroid_lon", "mfh_risk_score"]
    df_coords = df[coord_cols].dropna(subset=["cluster_centroid_lat", "cluster_centroid_lon"]).copy()

    # ---------- Per-cluster computation ----------
    results = []
    for _, row in df_24.iterrows():
        cid = row["cluster_id"]
        street = row["street_name"]
        lat = row.get("cluster_centroid_lat")
        lon = row.get("cluster_centroid_lon")
        sfh_str = float(row.get("sfh_strength_score", 0.0)) if pd.notna(row.get("sfh_strength_score")) else 0.0

        # --- Primary: Local MFH pressure (K=5 nearest, distance-decay) ---
        local_mfh_pressure = None
        fallback_note = ""
        if pd.notna(lat) and pd.notna(lon):
            dists = []
            for _, r2 in df_coords.iterrows():
                if r2["cluster_id"] == cid:
                    continue
                d = haversine_m(float(lat), float(lon),
                                float(r2["cluster_centroid_lat"]),
                                float(r2["cluster_centroid_lon"]))
                dists.append((d, float(r2["mfh_risk_score"]) if pd.notna(r2["mfh_risk_score"]) else 0.0))
            dists.sort(key=lambda x: x[0])
            neighbors = dists[:K_NEIGHBORS]
            if neighbors:
                weights = [1.0 / (d + 100) for d, _ in neighbors]
                local_mfh_pressure = sum(w * s for w, (_, s) in zip(weights, neighbors)) / sum(weights)
            else:
                local_mfh_pressure = 0.0
                fallback_note = "no neighbors found; local_mfh_pressure=0"
        else:
            local_mfh_pressure = 0.0
            fallback_note = "missing centroid coords; local_mfh_pressure=0 (conservative fallback)"

        # --- Secondary: Smooth inner-city prior ---
        dist_center = None
        inner_contribution = 0.0
        if pd.notna(lat) and pd.notna(lon):
            dist_center = haversine_m(float(lat), float(lon), NEUSS_CENTER_LAT, NEUSS_CENTER_LON)
            raw_inner = max(0.0, 1.0 - dist_center / INNER_CITY_FADE_M)
            inner_contribution = 0.07 * raw_inner

        # --- Tertiary: Street semantics fallback ---
        sem_raw, sem_capped = compute_semantic(street)

        # --- Composite ---
        P_context = 0.55 * local_mfh_pressure + inner_contribution + sem_capped
        purity_score_final = sfh_str * (1.0 - P_context)

        # --- Threshold labels ---
        sim = {}
        for thresh, tkey, _ in THRESHOLDS:
            sim[f"sim_label_{tkey}"] = "2.3_DOWNGRADED" if purity_score_final < thresh else "2.4_RETAINED"

        results.append({
            "cluster_id": cid,
            "street_name": street,
            "building_count": int(row.get("building_count", 0)),
            "original_label": "2.4",
            "sfh_strength_score": round(sfh_str, 4),
            "local_mfh_pressure": round(local_mfh_pressure, 4),
            "inner_contribution": round(inner_contribution, 4),
            "semantic_penalty_raw": round(sem_raw, 4),
            "semantic_effect_capped": round(sem_capped, 4),
            "P_context": round(P_context, 4),
            "purity_score_final": round(purity_score_final, 4),
            "sim_label_t060": sim["sim_label_t060"],
            "sim_label_t055": sim["sim_label_t055"],
            "sim_label_t050": sim["sim_label_t050"],
            "fallback_note": fallback_note,
        })

    df_sim = pd.DataFrame(results)
    os.makedirs(OUT_DIR, exist_ok=True)

    # ---------- Full simulation output ----------
    sim_path = os.path.join(OUT_DIR, "purity_gate_simulation_NEUSS.json")
    with open(sim_path, "w", encoding="utf-8") as f:
        json.dump(df_sim.to_dict(orient="records"), f, ensure_ascii=False, indent=2)

    # ---------- Threshold summary ----------
    total_24_bldg = int(df_24["building_count"].sum())
    summary_data = {}
    for thresh, tkey, tlabel in THRESHOLDS:
        col = f"sim_label_{tkey}"
        downgraded = df_sim[df_sim[col] == "2.3_DOWNGRADED"]
        retained = df_sim[df_sim[col] == "2.4_RETAINED"]
        summary_data[tlabel] = {
            "threshold": thresh,
            "key": tkey,
            "downgraded_clusters": int(len(downgraded)),
            "downgraded_buildings": int(downgraded["building_count"].sum()),
            "retained_clusters": int(len(retained)),
            "retained_buildings": int(retained["building_count"].sum()),
        }
    with open(os.path.join(OUT_DIR, "purity_gate_threshold_summary_NEUSS.json"), "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    # ---------- Case audit ----------
    audit_streets = set(MUST_DOWNGRADE + MUST_STAY)
    audit_rows = []
    for _, r in df_sim.iterrows():
        if any(s in r["street_name"].lower() for s in audit_streets):
            audit_rows.append(r.to_dict())
    with open(os.path.join(OUT_DIR, "purity_gate_case_audit_NEUSS.json"), "w", encoding="utf-8") as f:
        json.dump(audit_rows, f, ensure_ascii=False, indent=2)

    # ---------- Acceptance check ----------
    def cluster_label(df_sim, street_part, col):
        matches = df_sim[df_sim["street_name"].str.lower().str.contains(street_part, na=False)]
        if matches.empty:
            return "NOT_FOUND"
        return matches.iloc[0][col]

    checks = {}
    for thresh, tkey, tlabel in THRESHOLDS:
        col = f"sim_label_{tkey}"
        retained = df_sim[df_sim[col] == "2.4_RETAINED"]
        total_24_bldg_retained = int(retained["building_count"].sum())
        checks[tlabel] = {
            "threshold": thresh,
            "gladbacher_straße": cluster_label(df_sim, "gladbacher", col),
            "daimlerstraße": cluster_label(df_sim, "daimler", col),
            "porschestraße": cluster_label(df_sim, "porsche", col),
            "mergelsweg": cluster_label(df_sim, "mergelsweg", col),
            "im_stüttgesfeld": cluster_label(df_sim, "stüttgesfeld", col),
            "2.4_retained_buildings": total_24_bldg_retained,
            "2.1_2.2_touched": 0,  # immutable, not processed
        }

    # ---------- Markdown report ----------
    lines = [
        "# Purity Gate Simulation Report — Neuss",
        "",
        f"**Date:** 2026-03-20 | **Scope:** 2.4 Purity Gate (offline only)",
        f"**Total 2.4 candidates evaluated:** {len(df_sim)}",
        f"**Total 2.4 buildings at stake:** {total_24_bldg}",
        f"**2.1/2.2 touched:** 0 (immutable — confirmed)",
        "",
        "## Threshold Summary",
        "",
        "| Threshold | Label | Downgraded Clusters | Downgraded Bldgs | Retained Clusters | Retained Bldgs |",
        "|---|---|---|---|---|---|",
    ]
    for thresh, tkey, tlabel in THRESHOLDS:
        s = summary_data[tlabel]
        lines.append(f"| {thresh} | {tlabel} | {s['downgraded_clusters']} | {s['downgraded_buildings']} | {s['retained_clusters']} | {s['retained_buildings']} |")

    lines += ["", "## Acceptance Criteria Audit", ""]
    lines.append("| Case | T=0.60 | T=0.55 | T=0.50 | Requirement |")
    lines.append("|---|---|---|---|---|")

    for street_part, req in [
        ("gladbacher", "MUST downgrade at 0.55 and 0.60"),
        ("daimler", "MUST downgrade"),
        ("porsche", "MUST downgrade"),
        ("mergelsweg", "MUST retain at 0.55"),
        ("stüttgesfeld", "MUST retain at 0.55"),
    ]:
        t60 = cluster_label(df_sim, street_part, "sim_label_t060")
        t55 = cluster_label(df_sim, street_part, "sim_label_t055")
        t50 = cluster_label(df_sim, street_part, "sim_label_t050")
        def fmt(v): return "❌ RETAIN" if v == "2.4_RETAINED" else ("✅ DOWN" if v == "2.3_DOWNGRADED" else v)
        lines.append(f"| {street_part} | {fmt(t60)} | {fmt(t55)} | {fmt(t50)} | {req} |")

    lines += [
        "",
        "## Signal Architecture (as implemented)",
        "",
        "- **Primary (0.55):** K=5 nearest cluster MFH risk, distance-decay weighted (w = 1/(d+100))",
        "- **Secondary (smooth):** inner_contribution = 0.07 × max(0, 1 − dist/1200m)",
        "- **Tertiary (capped):** semantic_effect = min(0.25 × raw_penalty, 0.15)",
        "- **Formula:** `P_context = 0.55 × local_mfh_pressure + inner_contribution + semantic_effect`",
        "- **Purity score:** `purity_score_final = sfh_strength_score × (1 − P_context)`",
        "",
        "## Missing Data Fallback",
        "",
        "- Missing centroid coordinates → `local_mfh_pressure = 0` (conservative; no penalty applied)",
        "- Missing `sfh_strength_score` → treated as 0.0 (cluster would score 0 purity, likely already ambiguous)",
        "- All fallback cases documented in `fallback_note` field of simulation output",
    ]

    report_path = os.path.join(OUT_DIR, "purity_gate_report_NEUSS.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Print summary to terminal
    print("\n========== PURITY GATE SIMULATION SUMMARY ==========")
    for thresh, tkey, tlabel in THRESHOLDS:
        s = summary_data[tlabel]
        c = checks[tlabel]
        print(f"\n--- {tlabel} (threshold={thresh}) ---")
        print(f"  Downgraded: {s['downgraded_clusters']} clusters / {s['downgraded_buildings']} buildings")
        print(f"  Retained 2.4: {s['retained_clusters']} clusters / {s['retained_buildings']} buildings")
        print(f"  Gladbacher Str: {c['gladbacher_straße']}")
        print(f"  Daimlerstraße:  {c['daimlerstraße']}")
        print(f"  Porschestraße:  {c['porschestraße']}")
        print(f"  Mergelsweg:     {c['mergelsweg']}")
        print(f"  Im Stüttgesfeld:{c['im_stüttgesfeld']}")
        print(f"  2.1/2.2 touched: 0 ✅")
    print("\n=====================================================")
    logger.info(f"All outputs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
