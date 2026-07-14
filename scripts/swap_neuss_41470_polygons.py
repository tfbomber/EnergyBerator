"""
swap_neuss_41470_polygons.py
===============================
Swaps the freshly-extracted real-POLYGON PLZ 41470 set
(data/neuss_41470_polygons.parquet, from extract_neuss_41470_polygons.py)
into data/buildings.parquet, replacing the legacy POINT-geometry rows
(geometry_source=LEGACY_OVERPASS_POINT_41470, 1,494 rows from a 2026-04-12
one-off Overpass run).

Scoped replace (mirrors swap_neuss_buildings.py's own safety pattern): only
NEUSS_PLZ41470 rows are touched. The other 7 Neuss PLZ (POLYGON, from
build_neuss_buildings_from_geojson.py) and the 931 non-8-PLZ pilot segments
(ALLERHEILIGEN_PILOT_SEG_01, NEUSS_DENSE_01, etc.) are preserved untouched.

Safety:
  - Backs up the pre-swap buildings.parquet to a dated file before writing.
  - Hard-asserts row-count and dedup invariants before writing.
"""

import os
import shutil
from datetime import datetime, timezone

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CURRENT_PATH = os.path.join(BASE_DIR, "data", "buildings.parquet")
NEW_41470_PATH = os.path.join(BASE_DIR, "data", "neuss_41470_polygons.parquet")
BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")


def main():
    print("=" * 70)
    print("NEUSS 41470 POLYGON SWAP")
    print("=" * 70)

    current = pd.read_parquet(CURRENT_PATH)
    new_41470 = pd.read_parquet(NEW_41470_PATH)

    print(f"\n[LOAD] current buildings.parquet: {len(current)} rows")
    print(f"[LOAD] new 41470 (real POLYGON): {len(new_41470)} rows")

    assert (new_41470["segment_id"] == "NEUSS_PLZ41470").all(), (
        "new_41470 contains rows with a different segment_id — unexpected"
    )
    assert (new_41470["postal_code"] == "41470").all()

    old_41470 = current[current["segment_id"] == "NEUSS_PLZ41470"]
    print(f"[SPLIT] old NEUSS_PLZ41470 rows (POINT, to be replaced): {len(old_41470)}")
    old_geom_sources = old_41470["geometry_source"].unique().tolist()
    print(f"[SPLIT] old 41470 geometry_source values: {old_geom_sources}")

    preserved = current[current["segment_id"] != "NEUSS_PLZ41470"].copy()
    print(f"[SPLIT] preserved rows (7 other Neuss PLZ + pilot segments): {len(preserved)}")

    # Schema alignment
    assert set(new_41470.columns) == set(preserved.columns), (
        f"schema mismatch: missing={set(preserved.columns) - set(new_41470.columns)} "
        f"extra={set(new_41470.columns) - set(preserved.columns)}"
    )
    new_41470 = new_41470[preserved.columns.tolist()]

    merged = pd.concat([preserved, new_41470], ignore_index=True)

    # Known, pre-existing, investigated-benign overlap (see swap_neuss_buildings.py's
    # own docstring): ALLERHEILIGEN_PILOT_SEG_01 (a small non-PLZ pilot segment) and
    # NEUSS_PLZ41469 share some building_ids because Allerheiligen geographically sits
    # inside PLZ 41469. Pre-existing in `preserved`, untouched by this 41470-only swap.
    # Hard-fail on anything else (especially anything touching NEUSS_PLZ41470, which
    # WOULD indicate this swap introduced a real collision).
    dup_ids = merged["building_id"][merged["building_id"].duplicated(keep=False)].unique()
    dup_detail = merged[merged["building_id"].isin(dup_ids)]["segment_id"].value_counts()
    print(f"\n[VERIFY] duplicate building_id in merged set: {len(dup_ids)}")
    print(f"[VERIFY] duplicate segment_id breakdown: {dup_detail.to_dict()}")
    unexpected_segs = set(dup_detail.index) - {"ALLERHEILIGEN_PILOT_SEG_01", "NEUSS_PLZ41469"}
    assert not unexpected_segs, (
        f"unexpected segment(s) involved in duplicate building_id -- ABORT: {unexpected_segs}"
    )
    assert "NEUSS_PLZ41470" not in dup_detail.index, (
        "NEUSS_PLZ41470 (the segment this script replaces) has duplicate building_id "
        "overlap with something -- ABORT, this would be a NEW collision from this swap"
    )

    expected_total = len(preserved) + len(new_41470)
    print(f"[VERIFY] row count: {len(merged)} (expected {expected_total})")
    assert len(merged) == expected_total

    # Preserved segments must be byte-identical (untouched)
    preserved_check = merged[merged["segment_id"] != "NEUSS_PLZ41470"].reset_index(drop=True)
    pre_sorted = preserved.sort_values("building_id").reset_index(drop=True)
    post_sorted = preserved_check.sort_values("building_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(pre_sorted, post_sorted)
    print("[REGRESSION GUARD] All non-41470 rows (7 other Neuss PLZ + pilot segments) "
          "are byte-identical before vs after this swap.")

    print("\n[41470 SUMMARY] building_type distribution (new):")
    print(merged[merged["segment_id"] == "NEUSS_PLZ41470"]["building_type"].value_counts().to_string())

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = os.path.join(BACKUP_DIR, f"buildings.parquet.pre_41470_repolygon_{ts}")
    shutil.copy2(CURRENT_PATH, backup_path)
    print(f"\n[BACKUP] {backup_path}")

    merged.to_parquet(CURRENT_PATH, index=False)
    print(f"[WRITE] {CURRENT_PATH} ({len(merged)} rows)")

    reread = pd.read_parquet(CURRENT_PATH)
    assert len(reread) == len(merged)
    reread_dup_ids = reread["building_id"][reread["building_id"].duplicated(keep=False)].unique()
    reread_dup_segs = set(reread[reread["building_id"].isin(reread_dup_ids)]["segment_id"])
    assert reread_dup_segs <= {"ALLERHEILIGEN_PILOT_SEG_01", "NEUSS_PLZ41469"}, (
        f"post-write re-read found unexpected duplicate segments: {reread_dup_segs}"
    )
    print(f"[VERIFY] Post-write re-read OK: {len(reread)} rows, "
          f"{len(reread_dup_ids)} duplicate building_id (all confirmed = the known benign "
          f"ALLERHEILIGEN_PILOT_SEG_01 <-> NEUSS_PLZ41469 overlap, nothing else)")


if __name__ == "__main__":
    main()
