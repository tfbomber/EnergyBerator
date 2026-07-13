"""
backfill_neuss_building_polygons.py
===================================
Backfill real OSM building footprints (WKT POLYGON) into data/buildings.parquet
for Neuss building_ids that currently carry only a POINT centroid.

Why this exists
---------------
buildings.parquet (Neuss) was assembled by extract_osm_buildings_by_plz.py, which
used Overpass `out center tags` and therefore stored only a centroid POINT per
building ("Full polygon WKT would require fetching way nodes — too heavy for MVP",
see that script line ~150). As a result 26,746 of 27,681 rows (96.6%) are POINT,
not real footprints — even though geometry_source is stamped "OSM".

Meanwhile the *original* Overpass extraction produced full polygons and was saved
to data/sources/buildings/osm_overpass/2026-03-15/neuss_osm_buildings_normalized.geojson
(93,759 real Polygon features) but was never merged back into buildings.parquet.
~74.5% of the point-only building_ids already have a real polygon sitting in that
file. This script merges them back.

Behaviour
---------
- Source of footprints: neuss_osm_buildings_normalized.geojson.
- Matching key: building_id == f"OSM_{feature.properties.osm_id}".
- Only rows whose CURRENT geometry is a WKT POINT are eligible for upgrade.
- A row is upgraded iff its building_id has a matching Polygon in the geojson.
- Non-matching POINT rows and already-POLYGON rows are left exactly as-is.
- lat / lon columns are preserved (they remain a valid representative point).
- Upgraded rows get geometry_source = "OSM_OVERPASS_POLYGON" so the operation is
  self-documenting and trivially reversible (geometry_source is not consumed
  anywhere in core/ fields/ pipeline/ — verified — so this is a safe marker).
- A timestamped backup of buildings.parquet is written to data/backups/ first.
- An audit JSON (counts, per-segment breakdown) is written to output/layer2/.

Scope guardrails
----------------
- Neuss only. Does NOT touch kaarst_buildings.parquet / augsburg_buildings.parquet
  (already 100% real polygons).
- Idempotent: re-running only ever considers POINT rows, so already-upgraded rows
  are skipped on subsequent runs.

Run
---
    python scripts/backfill_neuss_building_polygons.py            # apply
    python scripts/backfill_neuss_building_polygons.py --dry-run  # report only
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
from shapely.geometry import shape

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDINGS_PATH = os.path.join(BASE_DIR, "data", "buildings.parquet")
GEOJSON_PATH = os.path.join(
    BASE_DIR, "data", "sources", "buildings", "osm_overpass",
    "2026-03-15", "neuss_osm_buildings_normalized.geojson",
)
BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")
AUDIT_DIR = os.path.join(BASE_DIR, "output", "layer2")

BACKFILL_SOURCE_TAG = "OSM_OVERPASS_POLYGON"


def _geom_kind(wkt) -> str:
    """Classify a WKT geometry string without fully parsing it."""
    if not isinstance(wkt, str):
        return "NULL"
    s = wkt.lstrip().upper()
    if s.startswith("MULTIPOLYGON"):
        return "MULTIPOLYGON"
    if s.startswith("POLYGON"):
        return "POLYGON"
    if s.startswith("POINT"):
        return "POINT"
    return "OTHER"


def load_polygon_lookup(geojson_path: str):
    """
    Parse the Overpass geojson into { "OSM_<osm_id>": wkt_polygon }.
    Invalid polygons are repaired with buffer(0), mirroring the generate_*
    scripts. Returns (lookup, stats).
    """
    with open(geojson_path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    feats = gj.get("features", [])

    lookup = {}
    stats = {
        "features_total": len(feats),
        "features_no_osm_id": 0,
        "features_no_geometry": 0,
        "features_unconvertible": 0,
        "features_repaired": 0,
        "duplicate_osm_ids": 0,
    }
    for ft in feats:
        props = ft.get("properties") or {}
        oid = props.get("osm_id")
        if oid is None:
            stats["features_no_osm_id"] += 1
            continue
        geom = ft.get("geometry")
        if not geom:
            stats["features_no_geometry"] += 1
            continue
        key = f"OSM_{oid}"
        if key in lookup:
            stats["duplicate_osm_ids"] += 1
            continue
        try:
            poly = shape(geom)
            if not poly.is_valid:
                poly = poly.buffer(0)
                stats["features_repaired"] += 1
            if poly.is_empty:
                stats["features_unconvertible"] += 1
                continue
            lookup[key] = poly.wkt
        except Exception:
            stats["features_unconvertible"] += 1
            continue

    return lookup, stats


def main(dry_run: bool = False):
    ts_utc = datetime.now(timezone.utc)
    ts_tag = ts_utc.strftime("%Y%m%d_%H%M%S")

    print("=" * 66)
    print("  NEUSS BUILDING POLYGON BACKFILL" + ("  [DRY RUN]" if dry_run else ""))
    print("=" * 66)

    if not os.path.exists(BUILDINGS_PATH):
        sys.exit(f"[FATAL] buildings.parquet not found at {BUILDINGS_PATH}")
    if not os.path.exists(GEOJSON_PATH):
        sys.exit(f"[FATAL] source geojson not found at {GEOJSON_PATH}")

    print(f"[LOAD] buildings.parquet ...")
    df = pd.read_parquet(BUILDINGS_PATH)
    n_total = len(df)
    print(f"       {n_total} rows, {df['building_id'].nunique()} unique building_id")

    # Guardrail: this file must be Neuss. Refuse to run on Kaarst/Augsburg data.
    cities = set(str(c).strip().lower() for c in df.get("city", pd.Series()).dropna().unique())
    if cities and cities - {"neuss", ""}:
        sys.exit(f"[FATAL] buildings.parquet contains non-Neuss cities {cities} — refusing to run.")

    kind = df["geometry"].map(_geom_kind)
    point_before = int((kind == "POINT").sum())
    poly_before = int(kind.isin(["POLYGON", "MULTIPOLYGON"]).sum())
    print(f"       geometry before: POINT={point_before}  POLYGON={poly_before}")

    print(f"[LOAD] {os.path.basename(GEOJSON_PATH)} ...")
    lookup, gj_stats = load_polygon_lookup(GEOJSON_PATH)
    print(f"       {gj_stats['features_total']} features -> "
          f"{len(lookup)} unique OSM polygons "
          f"(repaired={gj_stats['features_repaired']}, "
          f"bad={gj_stats['features_unconvertible']})")

    # Eligible rows: currently POINT AND building_id has a polygon in the geojson.
    point_mask = kind == "POINT"
    match_mask = point_mask & df["building_id"].isin(lookup.keys())
    upgrade_idx = df.index[match_mask]

    rows_to_upgrade = int(match_mask.sum())
    unique_point_ids = int(df.loc[point_mask, "building_id"].nunique())
    matched_unique_ids = int(df.loc[match_mask, "building_id"].nunique())
    point_rows_remaining = point_before - rows_to_upgrade

    # Per-segment breakdown of what will be upgraded.
    by_segment = (
        df.loc[match_mask]
        .groupby("segment_id")
        .size()
        .sort_values(ascending=False)
        .to_dict()
    )

    print("-" * 66)
    print(f"  unique POINT building_ids ............. {unique_point_ids}")
    print(f"  ...with a polygon in geojson ......... {matched_unique_ids} "
          f"({matched_unique_ids / unique_point_ids:.1%})")
    print(f"  POINT rows to upgrade -> POLYGON ..... {rows_to_upgrade} "
          f"({rows_to_upgrade / point_before:.1%} of POINT rows)")
    print(f"  POINT rows left as-is (no match) ..... {point_rows_remaining}")
    print("-" * 66)
    print("  upgrades by segment:")
    for seg, cnt in by_segment.items():
        print(f"    {seg:32s} {cnt}")
    print("-" * 66)

    audit = {
        "run_timestamp_utc": ts_utc.isoformat(),
        "dry_run": dry_run,
        "source_geojson": os.path.relpath(GEOJSON_PATH, BASE_DIR).replace("\\", "/"),
        "source_geojson_stats": gj_stats,
        "parquet": os.path.relpath(BUILDINGS_PATH, BASE_DIR).replace("\\", "/"),
        "backfill_source_tag": BACKFILL_SOURCE_TAG,
        "rows_total": n_total,
        "geometry_before": {"point": point_before, "polygon": poly_before},
        "unique_point_building_ids": unique_point_ids,
        "matched_unique_building_ids": matched_unique_ids,
        "rows_upgraded_point_to_polygon": rows_to_upgrade,
        "point_rows_left_unmatched": point_rows_remaining,
        "upgrades_by_segment": by_segment,
    }

    if dry_run:
        print("[DRY RUN] No files written. Re-run without --dry-run to apply.")
        audit["geometry_after"] = {
            "point": point_rows_remaining,
            "polygon": poly_before + rows_to_upgrade,
        }
        _write_audit(audit, ts_tag, dry_run=True)
        return

    # ── Apply ────────────────────────────────────────────────────────────────
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"buildings_pre_polygon_backfill_{ts_tag}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"[BACKUP] {os.path.relpath(backup_path, BASE_DIR)}")

    new_geom = df.loc[upgrade_idx, "building_id"].map(lookup)
    df.loc[upgrade_idx, "geometry"] = new_geom
    if "geometry_source" in df.columns:
        df.loc[upgrade_idx, "geometry_source"] = BACKFILL_SOURCE_TAG

    # Sanity: recount after mutation.
    kind_after = df["geometry"].map(_geom_kind)
    point_after = int((kind_after == "POINT").sum())
    poly_after = int(kind_after.isin(["POLYGON", "MULTIPOLYGON"]).sum())
    assert point_after == point_rows_remaining, (point_after, point_rows_remaining)
    assert poly_after == poly_before + rows_to_upgrade, (poly_after, poly_before, rows_to_upgrade)

    df.to_parquet(BUILDINGS_PATH, index=False)
    print(f"[WRITE] {os.path.relpath(BUILDINGS_PATH, BASE_DIR)}  "
          f"geometry after: POINT={point_after}  POLYGON={poly_after}")

    audit["backup_path"] = os.path.relpath(backup_path, BASE_DIR).replace("\\", "/")
    audit["geometry_after"] = {"point": point_after, "polygon": poly_after}
    _write_audit(audit, ts_tag, dry_run=False)

    print("=" * 66)
    print(f"  DONE -- upgraded {rows_to_upgrade} rows from POINT to real POLYGON")
    print("=" * 66)


def _write_audit(audit: dict, ts_tag: str, dry_run: bool):
    os.makedirs(AUDIT_DIR, exist_ok=True)
    suffix = "_dryrun" if dry_run else ""
    audit_path = os.path.join(AUDIT_DIR, f"polygon_backfill_{ts_tag}{suffix}.json")
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(f"[AUDIT] {os.path.relpath(audit_path, BASE_DIR)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Backfill real OSM polygons into Neuss buildings.parquet")
    ap.add_argument("--dry-run", action="store_true", help="report only, write no parquet")
    args = ap.parse_args()
    main(dry_run=args.dry_run)
