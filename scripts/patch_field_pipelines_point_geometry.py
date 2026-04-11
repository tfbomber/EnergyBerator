"""
patch_field_pipelines_point_geometry.py
========================================
Layer 2 Expansion — Point Geometry Workaround

Problem:
    OSM buildings fetched with `out center tags` have POINT geometry (centroid only).
    field_02 (spatial adjacency) and field_01 (convex hull area) both require polygon
    geometry and fail silently on POINT data.

Fix (MVP-appropriate):
    1. field_02 for POINT-geometry segments:
       Use OSM building tag (already stored in buildings.parquet `building_type` column)
       to directly assign field_value. This is more accurate than 0-neighbor adjacency anyway.
       Caveats are logged explicitly.

    2. field_01 for POINT-geometry segments:
       Apply standard German residential footprint area proxy:
         detached  → 130 m2 (typical EFH footprint)
         semi      → 80 m2 per unit
         rowhouse  → 60 m2 per unit
         apartment → 200 m2 (full floor plate / unit)
         unknown   → 100 m2
       This proxy is conservative and documented. Confidence is reduced to 0.65.

Affected segments:
    NEUSS_SUBURB_01  (3,436 POINT buildings from PLZ 41472)

Output:
    data/fields/field_02_building_type.parquet  (appended, not replaced for other segments)
    data/fields/field_01_roof_potential.parquet (NEUSS_SUBURB_01 row updated)

Audit trail:
    output/layer2/patch_point_geometry_<ts>.json
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("POINT_PATCH")

BASE_DIR      = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILDINGS_P   = BASE_DIR / "data" / "buildings.parquet"
FIELD02_P     = BASE_DIR / "data" / "fields" / "field_02_building_type.parquet"
FIELD01_P     = BASE_DIR / "data" / "fields" / "field_01_roof_potential.parquet"
AUDIT_DIR     = BASE_DIR / "output" / "layer2"

# Standard German residential footprint proxies (m²) per unit
FOOTPRINT_PROXY = {
    "detached":  130.0,
    "semi":       80.0,
    "rowhouse":   60.0,
    "apartment": 200.0,
    "unknown":   100.0,
}

# PV utilization factors (from field_01 — matching existing pipeline values)
UTILIZATION_FACTORS = {
    "detached":  0.45,
    "semi":      0.40,
    "rowhouse":  0.35,
    "apartment": 0.20,
    "unknown":   0.20,
}

# Segment area proxy: sum of buffered footprint areas (use 110% of footprint sum as proxy)
AREA_PROXY_MULTIPLIER = 3.5    # realistic building density: footprint ≈ 1/3.5 of segment area

TARGET_SEGMENTS_POINT = {"NEUSS_SUBURB_01", "NEUSS_GRIML_01"}

# ---------------------------------------------------------------------------
# Stage 1 tag sets — mirrored from fields/field_02_building_type.py
# For POINT geometry, Stage 2 (footprint×adjacency) is NOT available.
# UNCERTAIN buildings remain UNCERTAIN (fail-closed).
# ---------------------------------------------------------------------------
_STAGE1_MFH_CONFIRMED_TAGS: frozenset = frozenset({
    "apartments", "apartment",
    "flat", "dormitory",
    "residential_block", "block_of_flats",
})
_STAGE1_SFH_CONFIRMED_TAGS: frozenset = frozenset({
    "detached", "detached_house",
    "semidetached_house", "semi",
    "terrace", "terraced_house",
    "rowhouse",   # normalised from OSM terrace in buildings.parquet
    "bungalow",
})


def patch_field02(buildings_df: pd.DataFrame) -> pd.DataFrame:
    """
    For POINT-geometry segments: use OSM building_type tag with Stage 1
    mapping to assign confirmed field_02 label.

    Stage 1 outputs: SFH_CONFIRMED / MFH_CONFIRMED / UNCERTAIN
    Stage 2 (footprint fallback) is NOT available for POINT geometry
    (no real polygon geometry). UNCERTAIN stays UNCERTAIN — fail-closed.

    Returns updated field_02 parquet (writes in-place).
    """
    logger.info("[PATCH F02] Stage 1 OSM tag mapping for POINT-geometry segments...")
    existing_f02 = pd.read_parquet(FIELD02_P) if FIELD02_P.exists() else pd.DataFrame()

    rows = []
    for seg_id in TARGET_SEGMENTS_POINT:
        seg_bldgs = buildings_df[buildings_df["segment_id"] == seg_id]
        if seg_bldgs.empty:
            logger.warning(f"[PATCH F02] No buildings found for {seg_id}, skipping")
            continue

        seg_counts = {"SFH_CONFIRMED": 0, "MFH_CONFIRMED": 0, "UNCERTAIN": 0}
        for _, row in seg_bldgs.iterrows():
            raw_tag = row.get("building_type") or ""

            # Stage 1 classification
            if raw_tag in _STAGE1_MFH_CONFIRMED_TAGS:
                b_type = "MFH_CONFIRMED"
                conf   = 0.90
            elif raw_tag in _STAGE1_SFH_CONFIRMED_TAGS:
                b_type = "SFH_CONFIRMED"
                conf   = 0.90
            else:
                # POINT geometry — no footprint, no adjacency — fail-closed
                b_type = "UNCERTAIN"
                conf   = 0.40

            seg_counts[b_type] = seg_counts.get(b_type, 0) + 1
            rows.append({
                "building_id":       row["building_id"],
                "segment_id":        seg_id,
                "field_id":          "field_02",
                "field_value":       b_type,
                "confidence":        conf,
                "source":            "stage1_osm_tag_proxy_v2",
                "row_recovery_hint": False,
                "notes": (
                    f"Stage 1: raw_tag={raw_tag!r} → {b_type}. "
                    "POINT geometry: Stage 2 fallback not available. "
                    "UNCERTAIN = fail-closed (no footprint proxy for building type)."
                ),
            })

        # Audit log (light check)
        total = len(seg_bldgs)
        logger.info(
            f"[PATCH F02 AUDIT] {seg_id} ({total} bldgs): "
            f"SFH_CONFIRMED={seg_counts['SFH_CONFIRMED']} ({seg_counts['SFH_CONFIRMED']/total:.1%}) | "
            f"MFH_CONFIRMED={seg_counts['MFH_CONFIRMED']} ({seg_counts['MFH_CONFIRMED']/total:.1%}) | "
            f"UNCERTAIN={seg_counts['UNCERTAIN']} ({seg_counts['UNCERTAIN']/total:.1%})"
        )

    if not rows:
        logger.warning("[PATCH F02] No rows generated")
        return existing_f02

    new_f02 = pd.DataFrame(rows)

    # Remove any existing rows for these segments to avoid duplicates
    if not existing_f02.empty:
        existing_f02 = existing_f02[~existing_f02["segment_id"].isin(TARGET_SEGMENTS_POINT)]

    combined = pd.concat([existing_f02, new_f02], ignore_index=True)
    combined.to_parquet(FIELD02_P, index=False)
    logger.info(f"[PATCH F02] field_02 saved: {len(combined)} rows total ({len(new_f02)} new)")
    return combined


def patch_field01(buildings_df: pd.DataFrame) -> pd.DataFrame:
    """
    For POINT-geometry segments: estimate field_01 using standard footprint area proxy.
    Updates NEUSS_SUBURB_01 row in field_01 parquet.
    """
    logger.info("[PATCH F01] Computing field_01 area proxy for POINT-geometry segments...")
    existing_f01 = pd.read_parquet(FIELD01_P) if FIELD01_P.exists() else pd.DataFrame()

    new_rows = []
    for seg_id in TARGET_SEGMENTS_POINT:
        seg_bldgs = buildings_df[buildings_df["segment_id"] == seg_id]
        if seg_bldgs.empty:
            logger.warning(f"[PATCH F01] No buildings found for {seg_id}, skipping")
            continue

        n_buildings = len(seg_bldgs)
        building_types = seg_bldgs["building_type"].fillna("unknown").tolist()

        roof_pool_area    = 0.0
        roof_pool_adjusted = 0.0

        for b_type in building_types:
            fp = FOOTPRINT_PROXY.get(b_type, FOOTPRINT_PROXY["unknown"])
            util = UTILIZATION_FACTORS.get(b_type, UTILIZATION_FACTORS["unknown"])
            roof_pool_area     += fp
            roof_pool_adjusted += fp * util

        # Plan A fix (v2, 2026-03-27): align with field_01_roof_potential.py v2.
        # score = adjusted / pool_area = weighted-average PV utilization rate.
        # segment_area_proxy retained in output for audit ONLY — not used in score.
        pv_score = roof_pool_adjusted / roof_pool_area if roof_pool_area > 0 else 0.0
        segment_area_proxy = roof_pool_area * AREA_PROXY_MULTIPLIER  # audit only

        type_counts = {}
        for t in building_types:
            type_counts[t] = type_counts.get(t, 0) + 1

        new_rows.append({
            "segment_id":             seg_id,
            "field_id":               "field_01",
            "building_count":         n_buildings,
            "roof_pool_area_m2":      round(roof_pool_area, 2),
            "roof_pool_adjusted_m2":  round(roof_pool_adjusted, 2),
            "segment_area_m2_proxy":  round(segment_area_proxy, 2),  # audit only
            "field_value":            round(pv_score, 4),  # = adjusted / pool (v2)
            "confidence":             0.65,   # lower than polygon path (0.85)
            "source":                 "osm_point_footprint_proxy_v2_utilization_rate",
            "notes": (
                f"v2: field_value = roof_pool_adjusted_m2 / roof_pool_area_m2 "
                f"(weighted-average utilization rate, aligned with field_01 v2). "
                f"⚠️ POINT geometry: footprint proxy used. "
                f"Proxies={FOOTPRINT_PROXY}. TypeCounts={{type_counts}}. "
                f"SegAreaProxy (audit only) = footprintSum × {AREA_PROXY_MULTIPLIER}."
            ),
        })
        logger.info(
            f"[PATCH F01] {seg_id}: {n_buildings} bldgs, "
            f"roof_pool={roof_pool_area:.0f} m2, adj={roof_pool_adjusted:.0f} m2, "
            f"score={pv_score:.4f}"
        )

    if not new_rows:
        logger.warning("[PATCH F01] No rows generated")
        return existing_f01

    new_f01 = pd.DataFrame(new_rows)

    # Remove existing rows for these segments
    if not existing_f01.empty:
        existing_f01 = existing_f01[~existing_f01["segment_id"].isin(TARGET_SEGMENTS_POINT)]

    combined = pd.concat([existing_f01, new_f01], ignore_index=True)
    combined.to_parquet(FIELD01_P, index=False)
    logger.info(f"[PATCH F01] field_01 saved: {len(combined)} rows total ({len(new_f01)} new)")
    return combined


def main():
    logger.info("=" * 60)
    logger.info("  POINT GEOMETRY FIELD PIPELINE PATCH")
    logger.info("=" * 60)

    # Load buildings
    logger.info(f"[LOAD] Loading buildings.parquet...")
    df = pd.read_parquet(BUILDINGS_P)
    logger.info(f"[LOAD] {len(df)} rows, segments: {df['segment_id'].unique().tolist()}")

    # Check which segments are POINT geometry
    for seg_id in TARGET_SEGMENTS_POINT:
        seg = df[df["segment_id"] == seg_id]
        n_point = (seg["geometry_source"] == "OSM").sum()
        logger.info(f"[LOAD] {seg_id}: {len(seg)} rows, {n_point} OSM point-geometry rows")

    # Patch field_02
    f02_df = patch_field02(df)

    # Patch field_01 (uses buildings df directly, not f02 parquet)
    f01_df = patch_field01(df)

    # Summary
    print(f"\n{'='*60}")
    print("  FIELD_02 — NEW DISTRIBUTION")
    print(f"{'='*60}")
    for seg_id in TARGET_SEGMENTS_POINT:
        sub = f02_df[f02_df["segment_id"] == seg_id]
        if not sub.empty:
            print(f"\n{seg_id} ({len(sub)} buildings):")
            print(sub["field_value"].value_counts().to_string())

    print(f"\n{'='*60}")
    print("  FIELD_01 — UPDATED SCORES")
    print(f"{'='*60}")
    print(f01_df[["segment_id", "building_count", "roof_pool_adjusted_m2",
                   "field_value", "confidence", "source"]].to_string(index=False))

    # Audit
    audit = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target_segments":   list(TARGET_SEGMENTS_POINT),
        "patch_method":      "osm_building_tag + standard_footprint_proxy",
        "footprint_proxies": FOOTPRINT_PROXY,
        "utilization_factors": UTILIZATION_FACTORS,
        "area_proxy_multiplier": AREA_PROXY_MULTIPLIER,
        "f02_confidence": 0.70,
        "f01_confidence": 0.65,
        "caveats": [
            "OSM building tags may not reflect true attachment status",
            "Footprint areas are proxies, not measured polygon areas",
            "Segment area proxy is a density-based estimate, not a real boundary",
            "Use as weak signal only — do not claim polygon-grade accuracy",
        ],
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_path = AUDIT_DIR / f"patch_point_geometry_{ts}.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    logger.info(f"[AUDIT] → {audit_path}")
    logger.info("=" * 60)
    logger.info("  DONE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
