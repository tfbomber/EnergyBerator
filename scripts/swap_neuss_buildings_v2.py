"""
swap_neuss_buildings_v2.py
============================
Swaps generate_neuss_buildings.py's unified 8-PLZ direct-PBF extraction
(data/neuss_buildings_v2.parquet, 25,827 rows) into data/buildings.parquet,
replacing ALL 8 NEUSS_PLZ* segments in one pass — superseding both the
original 7-PLZ geojson-snapshot chain (build_neuss_buildings_from_geojson.py
+ build_neuss_buildings_final.py + swap_neuss_buildings.py) and the interim
41470-only surgical fix (extract_neuss_41470_polygons.py +
swap_neuss_41470_polygons.py, 2026-07-14 earlier today).

Why a full 8-PLZ re-swap instead of another scoped patch: after promoting
Neuss into _FIELD02_VALIDATED_CITIES on the 41470-only fix, discovered the
2026-03-15 geojson snapshot underlying the OTHER 7 PLZ has its own, much
bigger coverage gap — 138 real streets / 4,067 buildings entirely absent
(72 of them PASS/QUALIFIED under the legacy path), producing hollow
zero-count Foundation records (e.g. Weststraße, PLZ 41472, 91.3% SFH under
legacy, silently zeroed by the gap). User confirmed (2026-07-14): extend the
direct-PBF-extraction fix to all 8 PLZ rather than patch the symptom again.

Preserved out-of-scope segments (unchanged from swap_neuss_buildings.py):
  ALLERHEILIGEN_PILOT_SEG_01, NEUSS_DENSE_01, NEUSS_OLD_TOWN_01,
  NEUSS_SUBURBAN_01, NEUSS_VILLA_01 (931 rows total).

Safety: backs up pre-swap buildings.parquet before writing; hard-asserts
row-count/dedup invariants; tolerates only the known, pre-investigated
ALLERHEILIGEN_PILOT_SEG_01 <-> NEUSS_PLZ41469 building_id overlap (see
swap_neuss_buildings.py's docstring for the original investigation).
"""

import os
import shutil
from datetime import datetime, timezone

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CURRENT_PATH = os.path.join(BASE_DIR, "data", "buildings.parquet")
NEW_PATH = os.path.join(BASE_DIR, "data", "neuss_buildings_v2.parquet")
BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")

KNOWN_NEUSS_PLZ = ["41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472"]
NEUSS_8PLZ_SEGMENTS = {f"NEUSS_PLZ{plz}" for plz in KNOWN_NEUSS_PLZ}
EXPECTED_PRESERVED_SEGS = {
    "ALLERHEILIGEN_PILOT_SEG_01", "NEUSS_DENSE_01", "NEUSS_OLD_TOWN_01",
    "NEUSS_SUBURBAN_01", "NEUSS_VILLA_01",
}


def main():
    print("=" * 70)
    print("NEUSS BUILDINGS SWAP v2 — unified 8-PLZ direct-PBF extraction")
    print("=" * 70)

    current = pd.read_parquet(CURRENT_PATH)
    new_neuss = pd.read_parquet(NEW_PATH)
    print(f"\n[LOAD] current buildings.parquet: {len(current)} rows")
    print(f"[LOAD] new unified 8-PLZ Neuss set: {len(new_neuss)} rows")

    assert set(new_neuss["segment_id"].unique()) == NEUSS_8PLZ_SEGMENTS, (
        f"new extraction segment_id set != expected 8 PLZ -- ABORT. "
        f"got={set(new_neuss['segment_id'].unique())}"
    )
    assert new_neuss["building_id"].duplicated().sum() == 0, (
        "duplicate building_id WITHIN new extraction -- ABORT"
    )

    seg = current["segment_id"].astype(str)
    old_8plz = current[seg.isin(NEUSS_8PLZ_SEGMENTS)]
    preserved = current[~seg.isin(NEUSS_8PLZ_SEGMENTS)].copy()
    print(f"\n[SPLIT] old 8-PLZ Neuss rows (to be replaced): {len(old_8plz)}")
    print(f"[SPLIT] preserved rows (out of scope): {len(preserved)}")
    print("[SPLIT] preserved segment_id distribution:")
    print(preserved["segment_id"].value_counts().to_string())

    preserved_segs = set(preserved["segment_id"].astype(str).unique())
    assert preserved_segs == EXPECTED_PRESERVED_SEGS, (
        f"preserved segments differ from expected out-of-scope set -- ABORT. "
        f"got={preserved_segs} expected={EXPECTED_PRESERVED_SEGS}"
    )
    assert len(preserved) == 931, f"expected 931 preserved rows, got {len(preserved)} -- ABORT"

    assert list(new_neuss.columns) == list(current.columns), (
        f"schema mismatch -- ABORT. current={list(current.columns)} new={list(new_neuss.columns)}"
    )

    print("\n[VERIFY]")
    cross_ids = set(preserved["building_id"]) & set(new_neuss["building_id"])
    cross_detail = preserved[preserved["building_id"].isin(cross_ids)]["segment_id"].value_counts()
    print(f"  building_id overlap between preserved segments and new Neuss set: {len(cross_ids)}")
    print(f"  overlap breakdown by preserved segment_id:\n{cross_detail.to_string()}")

    bug_pattern_segs = {"NEUSS_DENSE_01", "NEUSS_OLD_TOWN_01", "NEUSS_SUBURBAN_01", "NEUSS_VILLA_01"}
    bad_overlap = set(cross_detail.index) & bug_pattern_segs
    assert not bad_overlap, (
        f"unexpected building_id overlap with NEUSS_* pilot segment(s) {bad_overlap} -- ABORT"
    )
    assert set(cross_detail.index) <= {"ALLERHEILIGEN_PILOT_SEG_01"}, (
        f"overlap with unexpected preserved segment(s) -- ABORT: {set(cross_detail.index)}"
    )

    new_buildings = pd.concat([preserved, new_neuss], ignore_index=True)
    expected_total = len(preserved) + len(new_neuss)
    print(f"  row count: {len(new_buildings)} (expected {expected_total})")
    assert len(new_buildings) == expected_total

    print("\n  new segment_id distribution (all segments):")
    print(new_buildings["segment_id"].value_counts().sort_index().to_string())

    # Preserved segments must be byte-identical (untouched)
    preserved_check = new_buildings[new_buildings["segment_id"].isin(EXPECTED_PRESERVED_SEGS)].reset_index(drop=True)
    pre_sorted = preserved.sort_values("building_id").reset_index(drop=True)
    post_sorted = preserved_check.sort_values("building_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(pre_sorted, post_sorted)
    print("[REGRESSION GUARD] All 5 out-of-scope pilot segments are byte-identical before vs after this swap.")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = os.path.join(BACKUP_DIR, f"buildings.parquet.pre_8plz_rebuild_{ts}")
    shutil.copy2(CURRENT_PATH, backup_path)
    print(f"\n[BACKUP] {backup_path}")

    new_buildings.to_parquet(CURRENT_PATH, index=False)
    print(f"[WRITE] {CURRENT_PATH} ({len(new_buildings)} rows)")

    reread = pd.read_parquet(CURRENT_PATH)
    assert len(reread) == len(new_buildings)
    reread_dup_ids = reread.loc[reread["building_id"].duplicated(keep=False), "building_id"].unique()
    for bid in reread_dup_ids:
        segs_for_id = set(reread.loc[reread["building_id"] == bid, "segment_id"])
        assert segs_for_id == {"ALLERHEILIGEN_PILOT_SEG_01", "NEUSS_PLZ41469"}, (
            f"post-write re-read found an unexpected duplicate building_id {bid} "
            f"across segments {segs_for_id} -- investigate"
        )
    print(f"[VERIFY] Post-write re-read OK: {len(reread)} rows, "
          f"{len(reread_dup_ids)} duplicate building_id (all confirmed = the known benign "
          f"ALLERHEILIGEN_PILOT_SEG_01 <-> NEUSS_PLZ41469 overlap, nothing else)")


if __name__ == "__main__":
    main()
