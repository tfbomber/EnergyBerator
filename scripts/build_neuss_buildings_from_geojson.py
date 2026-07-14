"""
build_neuss_buildings_from_geojson.py
======================================
Neuss building-data rebuild — Phase 1 (non-destructive).

Rebuilds Neuss's `buildings.parquet` population from the already-fetched
normalized OSM geojson, modeled directly on `generate_augsburg_buildings.py`
(the proven-good reference: 93.39% building-weighted street-match rate).

Root cause being fixed (see docs/neuss_buildings_duplicate_building_id_root_cause.md
and scratch/neuss_fix_research.md in the sibling territoryai repo): the current
`extract_osm_buildings_by_plz.py` reuses one whole-city bbox for 4 of 8 PLZ,
fabricates `postal_code` for address-less buildings, and never dedupes across
PLZ within a single run -> 27,681 rows but only 18,559 unique building_id.

This rebuild takes the opposite approach on every axis (Augsburg-strict, D2):
  - Requires a REAL `addr:street` tag on every kept feature.
  - PLZ assignment (spatial-PLZ P3, 2026-07-14 — extends
    .ai/implementation_plan_leipzig_plz_spatial.md to Neuss): a tagged
    `addr:postcode` in KNOWN_NEUSS_PLZ is trusted as-is (fast path, D1=a —
    the original 2026-07-11 rebuild's tagged rows are untouched by this
    change). A missing/foreign-tag building gets a point-in-polygon lookup
    against the 8 real Neuss PLZ boundary polygons (PlzLookup) instead of
    being unconditionally dropped. Never fabricates a postcode from a query
    target — a spatially-resolved PLZ is a real geographic fact, not a
    guess, so this preserves the "never fabricate" principle while
    recovering real Neuss buildings the original 2026-07-11 rebuild
    silently dropped for lacking a postcode tag. Only a building that falls
    outside ALL 8 PLZ polygons (true noise, or genuinely outside the known
    set) is still dropped, matching this script's original philosophy.
  - Applies a MANDATORY real point-in-polygon boundary filter against
    `config/boundaries/neuss_admin_boundary.geojson` (1,614-vertex Nominatim
    polygon) as a second, independent safety net beyond the postcode-set
    restriction — catches buildings that carry an in-range postcode tag but
    sit geographically outside the city (or vice versa / mistagged edge cases).
  - `segment_id` is derived PER BUILDING from its own real (or spatially
    resolved) postcode, never from a query target.
  - Single pass over one geojson snapshot -> duplication is structurally
    impossible (unlike the per-PLZ-query original), verified by an explicit
    drop_duplicates(building_id) safety check anyway.

PHASE 1 SAFETY: this script only ever WRITES to a new file,
`data/buildings_neuss_rebuilt.parquet`. It never reads or writes
`data/buildings.parquet`. Replacement (Phase 2) is a separate, later step
gated on `check_neuss_rebuild_audit.py` clearing the >=88% match-rate bar.

Source: data/sources/buildings/osm_overpass/2026-03-15/neuss_osm_buildings_normalized.geojson
        (93,759 real polygon features, real per-feature OSM tag dicts)
Boundary: config/boundaries/neuss_admin_boundary.geojson (real Nominatim polygon)
Output:  data/buildings_neuss_rebuilt.parquet
"""

import json
import os
import sys

import pandas as pd
from shapely.geometry import Polygon, Point
from shapely.prepared import prep

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.boundary_filter import _load_polygon  # noqa: E402
from core.plz_lookup import PlzLookup  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GEOJSON_PATH = os.path.join(
    BASE_DIR, "data", "sources", "buildings", "osm_overpass", "2026-03-15",
    "neuss_osm_buildings_normalized.geojson",
)
BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "neuss_admin_boundary.geojson")
CURRENT_BUILDINGS_PATH = os.path.join(BASE_DIR, "data", "buildings.parquet")
OUT_PATH = os.path.join(BASE_DIR, "data", "buildings_neuss_rebuilt.parquet")

# The 8 real, shipped Neuss PLZ (per PLZ_TO_SEGMENT in extract_osm_buildings_by_plz.py
# and field_08_street_level_ranking.py — confirmed identical in both).
KNOWN_NEUSS_PLZ = {
    "41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472",
}

# Provenance tag for rows produced by this rebuild — distinct from the existing
# "OSM_OVERPASS_POLYGON" value (used by the earlier centroid->polygon backfill)
# so the two generations remain distinguishable if ever needed.
GEOMETRY_SOURCE = "OSM_OVERPASS_POLYGON_REBUILD_2026-07"


def _map_building_tag(tag: str) -> str:
    """Maps OSM building tag to field_02-compatible building_type label.
    Identical mapping to extract_osm_buildings_by_plz.py._map_building_tag,
    reused here so the rebuilt rows use the same vocabulary as existing rows."""
    tag = (tag or "").lower()
    if tag in ("house", "detached"):
        return "detached"
    if tag in ("semi", "semi_detached", "semidetached_house"):
        return "semi"
    if tag in ("residential", "terrace", "rowhouse"):
        return "rowhouse"
    if tag in ("apartments", "apartment", "multi_family", "dormitory"):
        return "apartment"
    return "unknown"


def load_boundary_polygon():
    """Load the real Neuss admin boundary and return a shapely prepared
    polygon for fast point-in-polygon tests over ~94k candidate buildings."""
    coords = _load_polygon(BOUNDARY_PATH)  # list of (lon, lat)
    if coords is None:
        raise RuntimeError(f"Could not load boundary polygon from {BOUNDARY_PATH}")
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly, prep(poly)


def extract_buildings(geojson_path: str, boundary_poly, boundary_prepared, plz_lookup):
    with open(geojson_path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    features = gj.get("features", [])
    print(f"[LOAD] {len(features)} raw features from {os.path.basename(geojson_path)}")

    bounds = boundary_poly.bounds  # (minx, miny, maxx, maxy) = (lon_min, lat_min, lon_max, lat_max)

    counters = {
        "total": len(features),
        "missing_street": 0,
        "bad_geometry": 0,
        "outside_boundary_bbox": 0,
        "outside_boundary_polygon": 0,
        "postcode_spatially_recovered": 0,
        "postcode_unresolvable_dropped": 0,
        "missing_osm_id": 0,
        "kept": 0,
    }

    rows = []
    for ft in features:
        props = ft.get("properties") or {}

        street = (props.get("addr:street") or "").strip()

        # --- D2: still requires a real street tag. Never fabricates one. ---
        if not street:
            counters["missing_street"] += 1
            continue

        geometry = ft.get("geometry") or {}
        if geometry.get("type") != "Polygon":
            counters["bad_geometry"] += 1
            continue
        rings = geometry.get("coordinates") or []
        if not rings or len(rings[0]) < 3:
            counters["bad_geometry"] += 1
            continue

        exterior = rings[0]  # list of [lon, lat]
        try:
            nodes = [(float(pt[0]), float(pt[1])) for pt in exterior]
            poly = Polygon(nodes)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                counters["bad_geometry"] += 1
                continue
            centroid = poly.centroid
            c_lon, c_lat = centroid.x, centroid.y
            geom_wkt = poly.wkt
        except Exception:
            counters["bad_geometry"] += 1
            continue

        # --- Cheap bbox pre-check before the more expensive polygon test ---
        if not (bounds[0] <= c_lon <= bounds[2] and bounds[1] <= c_lat <= bounds[3]):
            counters["outside_boundary_bbox"] += 1
            continue

        # --- MANDATORY real point-in-polygon boundary filter ---
        if not boundary_prepared.contains(Point(c_lon, c_lat)):
            counters["outside_boundary_polygon"] += 1
            continue

        # --- PLZ resolution: tag-first (fast path, D1=a), spatial fallback
        # for missing/foreign tags (P3), drop if genuinely unresolvable. ---
        postcode_raw = (props.get("addr:postcode") or "").strip()
        if postcode_raw in KNOWN_NEUSS_PLZ:
            postcode = postcode_raw
        else:
            spatial_plz = plz_lookup.lookup(c_lon, c_lat)
            if spatial_plz is not None:
                postcode = spatial_plz
                counters["postcode_spatially_recovered"] += 1
            else:
                counters["postcode_unresolvable_dropped"] += 1
                continue

        osm_id = props.get("osm_id")
        if osm_id is None:
            counters["missing_osm_id"] += 1
            continue
        building_id = f"OSM_{int(osm_id)}"

        building_tag_raw = (props.get("building") or "").strip().lower()
        city = (props.get("addr:city") or "").strip() or "Neuss"

        rows.append({
            "building_id": building_id,
            "segment_id": f"NEUSS_PLZ{postcode}",
            "geometry": geom_wkt,
            "neighbors": [],
            "city": city,
            "street": street,
            "house_number": (props.get("addr:housenumber") or "").strip(),
            "postal_code": postcode,
            "lat": c_lat,
            "lon": c_lon,
            "building_type": _map_building_tag(building_tag_raw),
            "geometry_source": GEOMETRY_SOURCE,
            "address_source": "OSM",
            "building_type_source": "OSM",
            "building_type_confidence": "MEDIUM",
        })
        counters["kept"] += 1

    return rows, counters


def main():
    print("=" * 70)
    print("NEUSS BUILDINGS REBUILD — PHASE 1 (non-destructive, new-file only)")
    print("=" * 70)

    # --- Print current buildings.parquet schema/dtypes first (per plan step 7) ---
    if os.path.exists(CURRENT_BUILDINGS_PATH):
        current = pd.read_parquet(CURRENT_BUILDINGS_PATH)
        print(f"\n[SCHEMA] Current data/buildings.parquet: {len(current)} rows")
        print(current.dtypes.to_string())
        current_cols = list(current.columns)
    else:
        print("\n[SCHEMA] WARNING: current buildings.parquet not found — cannot verify schema parity")
        current_cols = None

    print(f"\n[BOUNDARY] Loading {BOUNDARY_PATH} ...")
    boundary_poly, boundary_prepared = load_boundary_polygon()
    print(f"[BOUNDARY] Loaded polygon, bounds={boundary_poly.bounds}, "
          f"vertices={len(boundary_poly.exterior.coords)}")

    print("\n[PLZ LOOKUP] Loading 8 Neuss PLZ boundary polygons for spatial fallback...")
    plz_lookup = PlzLookup(
        os.path.join(BASE_DIR, "config", "boundaries", "neuss_plz_boundaries.geojson"),
        expected_count=8,
    )

    print(f"\n[EXTRACT] Reading {GEOJSON_PATH} ...")
    rows, counters = extract_buildings(GEOJSON_PATH, boundary_poly, boundary_prepared, plz_lookup)

    print("\n[FILTER FUNNEL]")
    for k, v in counters.items():
        print(f"  {k:32s} {v}")

    df = pd.DataFrame(rows)

    # --- Defensive dedupe (should be a no-op: single geojson pass, unique osm_id) ---
    before = len(df)
    dup_ids = int(df["building_id"].duplicated().sum())
    if dup_ids:
        print(f"\n[DEDUP] WARNING: {dup_ids} duplicate building_id found — dropping")
        df = df.drop_duplicates(subset=["building_id"], keep="first")
    print(f"\n[DEDUP] {before} -> {len(df)} rows (duplicates removed: {before - len(df)})")

    # --- Schema parity check ---
    if current_cols is not None:
        rebuilt_cols = list(df.columns)
        if rebuilt_cols != current_cols:
            print(f"\n[SCHEMA] WARNING: column order/set differs from current buildings.parquet")
            print(f"  current : {current_cols}")
            print(f"  rebuilt : {rebuilt_cols}")
        else:
            print(f"\n[SCHEMA] OK — rebuilt columns match current buildings.parquet exactly")

    print(f"\n[SEGMENT DISTRIBUTION]")
    print(df["segment_id"].value_counts().to_string())

    print(f"\n[POSTAL CODE DISTRIBUTION]")
    print(df["postal_code"].value_counts().to_string())

    non_neuss_plz = df[~df["postal_code"].isin(KNOWN_NEUSS_PLZ)]
    print(f"\n[BOUNDARY CHECK] rows with postal_code outside the 8 real Neuss PLZ: {len(non_neuss_plz)}")

    df.to_parquet(OUT_PATH, index=False)
    print(f"\n[OUTPUT] Wrote {len(df)} rows to {OUT_PATH}")
    print("[OUTPUT] data/buildings.parquet was NOT touched.")


if __name__ == "__main__":
    main()
