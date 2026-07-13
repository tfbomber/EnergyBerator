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

    2. field_01 — DIRECT building_type computation for ALL Neuss segments
       (REARCH 2026-07-11, see docs/neuss_buildings_duplicate_building_id_root_cause.md):
       Reads `buildings_df['building_type']` directly (bypassing field_02's parquet
       join entirely) and picks the area source per building based on its actual
       geometry type:
         - real POLYGON geometry (7 of 8 Neuss PLZ, post Stage A/B rebuild) →
           real measured footprint area via shapely (same UTM32N projection as
           field_01_roof_potential.py::get_area_m2).
         - POINT geometry (NEUSS_PLZ41470 only, LEGACY_OVERPASS_POINT_41470) →
           standard German residential footprint area proxy:
             detached  → 130 m2 (typical EFH footprint)
             semi      → 80 m2 per unit
             rowhouse  → 60 m2 per unit
             apartment → 200 m2 (full floor plate / unit)
             unknown   → 100 m2
       This deliberately bypasses field_01_roof_potential.py's own field_02-join path,
       whose `utilization_factors` dict is keyed to a vocabulary
       (detached/semi/rowhouse/apartment/unknown) that does NOT match field_02's real
       Stage1/2 output labels (SFH_CONFIRMED/MFH_CONFIRMED/SFH_WEAK/MFH_SUSPECT/
       UNCERTAIN) — that mismatch silently collapses every building to the 0.20
       fallback (confirmed live in production for Augsburg's 14 segments as of
       2026-07-11; tracked as a separate, out-of-scope follow-up, NOT fixed here to
       avoid touching Augsburg/Kaarst's already-shipped shared-dict-derived scores).
       Confidence: 0.85 for real-polygon-area segments, 0.65 for the POINT segment
       (unchanged from the original proxy-only confidence).

Affected segments (field_01 — REARCH 2026-07-11):
    NEUSS_PLZ41460, NEUSS_PLZ41462, NEUSS_PLZ41464, NEUSS_PLZ41466, NEUSS_PLZ41468,
    NEUSS_PLZ41469, NEUSS_PLZ41472  (real POLYGON — measured area)
    NEUSS_PLZ41470  (POINT — footprint proxy, replaces the orphaned pre-Stage-A/B
    ALLERHEILIGEN_PILOT_SEG_01 snapshot that no longer matches buildings.parquet)

Affected segments (field_02 — unchanged scope):
    NEUSS_PLZ41470 only (the other 7 PLZ now run through field_02_building_type.py's
    real Stage1/2 spatial-adjacency pipeline directly — see POINT_SEGS there).

Output:
    data/fields/field_02_building_type.parquet  (appended, not replaced for other segments)
    data/fields/field_01_roof_potential.parquet (8 Neuss PLZ rows updated)

Audit trail:
    output/layer2/patch_point_geometry_<ts>.json
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyproj
from shapely.ops import transform
from shapely.wkt import loads as wkt_loads

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

# field_02 patch scope (REARCH 2026-07-11): only NEUSS_PLZ41470 remains POINT geometry.
# The other 7 PLZ are real POLYGON post Stage A/B rebuild and run through
# field_02_building_type.py's real Stage1/2 spatial-adjacency pipeline directly.
TARGET_SEGMENTS_POINT = {"NEUSS_PLZ41470"}

# field_01 patch scope (REARCH 2026-07-11): ALL 8 Neuss PLZ. field_01 is computed
# here directly from buildings_df['building_type'] (bypassing the field_02 join —
# see module docstring for why) for every Neuss segment, with area sourced from
# real polygon geometry where available and the footprint proxy only for the
# remaining POINT segment (41470).
TARGET_SEGMENTS_F01_DIRECT = {
    "NEUSS_PLZ41460", "NEUSS_PLZ41462", "NEUSS_PLZ41464", "NEUSS_PLZ41466",
    "NEUSS_PLZ41468", "NEUSS_PLZ41469", "NEUSS_PLZ41470", "NEUSS_PLZ41472",
}

# Projection for real polygon area calculation (UTM 32N for Neuss/Germany) —
# matches field_01_roof_potential.py::get_area_m2.
_WGS84  = pyproj.CRS("EPSG:4326")
_UTM32N = pyproj.CRS("EPSG:25832")
_project = pyproj.Transformer.from_crs(_WGS84, _UTM32N, always_xy=True).transform


def _real_area_m2(geom_wkt: str) -> float | None:
    """Real measured footprint area in m² from a POLYGON WKT string. Returns None on failure
    (e.g. the geometry is a POINT, which has zero area — caller falls back to the proxy)."""
    try:
        geom = wkt_loads(geom_wkt)
        if geom.geom_type != "Polygon":
            return None
        projected = transform(_project, geom)
        area = projected.area
        return area if area > 0 else None
    except Exception:
        return None

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
    Direct building_type computation for all 8 Neuss PLZ (REARCH 2026-07-11).
    Bypasses field_01_roof_potential.py's field_02-join path entirely (see module
    docstring for why). Area is sourced per-building: real measured polygon area
    where the geometry is a real POLYGON (7 of 8 PLZ post Stage A/B rebuild),
    footprint-area proxy where it is still POINT (NEUSS_PLZ41470 only).
    Updates all 8 NEUSS_PLZ{plz} rows in the field_01 parquet.
    """
    logger.info("[PATCH F01] Computing field_01 (direct building_type) for all 8 Neuss PLZ...")
    existing_f01 = pd.read_parquet(FIELD01_P) if FIELD01_P.exists() else pd.DataFrame()

    new_rows = []
    for seg_id in TARGET_SEGMENTS_F01_DIRECT:
        seg_bldgs = buildings_df[buildings_df["segment_id"] == seg_id]
        if seg_bldgs.empty:
            logger.warning(f"[PATCH F01] No buildings found for {seg_id}, skipping")
            continue

        n_buildings = len(seg_bldgs)

        roof_pool_area     = 0.0
        roof_pool_adjusted = 0.0
        n_real_area  = 0
        n_proxy_area = 0

        for _, row in seg_bldgs.iterrows():
            b_type = row.get("building_type") or "unknown"
            util = UTILIZATION_FACTORS.get(b_type, UTILIZATION_FACTORS["unknown"])

            real_area = _real_area_m2(row.get("geometry"))
            if real_area is not None:
                fp = real_area
                n_real_area += 1
            else:
                fp = FOOTPRINT_PROXY.get(b_type, FOOTPRINT_PROXY["unknown"])
                n_proxy_area += 1

            roof_pool_area     += fp
            roof_pool_adjusted += fp * util

        # Plan A fix (v2, 2026-03-27): align with field_01_roof_potential.py v2.
        # score = adjusted / pool_area = weighted-average PV utilization rate.
        # segment_area_proxy retained in output for audit ONLY — not used in score.
        pv_score = roof_pool_adjusted / roof_pool_area if roof_pool_area > 0 else 0.0
        segment_area_proxy = roof_pool_area * AREA_PROXY_MULTIPLIER  # audit only

        type_counts = {}
        for t in seg_bldgs["building_type"].fillna("unknown").tolist():
            type_counts[t] = type_counts.get(t, 0) + 1

        is_real_area_majority = n_real_area >= n_proxy_area
        confidence = 0.85 if is_real_area_majority else 0.65
        area_source = (
            f"real_polygon_area({n_real_area}/{n_buildings})"
            if n_proxy_area == 0 else
            f"mixed_real{n_real_area}_proxy{n_proxy_area}"
            if n_real_area > 0 else
            f"footprint_proxy({n_proxy_area}/{n_buildings})"
        )
        source_label = (
            "osm_polygon_direct_type_v1_utilization_rate"
            if is_real_area_majority else
            "osm_point_footprint_proxy_v2_utilization_rate"
        )

        new_rows.append({
            "segment_id":             seg_id,
            "field_id":               "field_01",
            "building_count":         n_buildings,
            "roof_pool_area_m2":      round(roof_pool_area, 2),
            "roof_pool_adjusted_m2":  round(roof_pool_adjusted, 2),
            "segment_area_m2_proxy":  round(segment_area_proxy, 2),  # audit only
            "field_value":            round(pv_score, 4),  # = adjusted / pool (v2)
            "confidence":             confidence,
            "source":                 source_label,
            "notes": (
                f"v2: field_value = roof_pool_adjusted_m2 / roof_pool_area_m2 "
                f"(weighted-average utilization rate, aligned with field_01 v2). "
                f"REARCH 2026-07-11: building_type read directly from buildings.parquet "
                f"(bypasses field_02 join — see module docstring). "
                f"AreaSource={area_source}. "
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
        existing_f01 = existing_f01[~existing_f01["segment_id"].isin(TARGET_SEGMENTS_F01_DIRECT)]

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

    # Check geometry composition for all 8 Neuss PLZ (informational)
    for seg_id in sorted(TARGET_SEGMENTS_F01_DIRECT):
        seg = df[df["segment_id"] == seg_id]
        n_point = seg["geometry"].astype(str).str.startswith("POINT").sum()
        n_poly  = seg["geometry"].astype(str).str.startswith("POLYGON").sum()
        logger.info(f"[LOAD] {seg_id}: {len(seg)} rows, {n_poly} POLYGON, {n_point} POINT")

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
        "target_segments_field02_point_only": list(TARGET_SEGMENTS_POINT),
        "target_segments_field01_direct":     sorted(TARGET_SEGMENTS_F01_DIRECT),
        "patch_method": (
            "field_02: osm_building_tag Stage1 proxy (POINT-only, 41470). "
            "field_01: direct building_type lookup (bypasses field_02 join) + "
            "real polygon area where available, footprint proxy otherwise (REARCH 2026-07-11)."
        ),
        "footprint_proxies": FOOTPRINT_PROXY,
        "utilization_factors": UTILIZATION_FACTORS,
        "area_proxy_multiplier": AREA_PROXY_MULTIPLIER,
        "f02_confidence": 0.70,
        "f01_confidence_real_area":  0.85,
        "f01_confidence_proxy_area": 0.65,
        "caveats": [
            "OSM building tags may not reflect true attachment status",
            "field_01 utilization_factor is still a per-type constant, not a measured PV yield",
            "NEUSS_PLZ41470 footprint area remains a proxy (still POINT geometry)",
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
