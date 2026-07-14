"""
swap_neuss_buildings.py
========================
Neuss building-data rebuild — Phase 2 / Stage B (destructive, backed up).

Swaps the Stage A output (`data/buildings_neuss_final.parquet`, 19,541 rows across
the 8 real Neuss PLZ, 0 duplicate building_id, 0 fabricated postcode) into
`data/buildings.parquet`.

IMPORTANT: `data/buildings.parquet` is NOT Neuss-PLZ-only. Besides the 8
`NEUSS_PLZ{plz}` segments (26,750 rows pre-swap), it also holds:
  - `ALLERHEILIGEN_PILOT_SEG_01` (294 rows) — an unrelated pilot segment.
  - `NEUSS_DENSE_01` / `NEUSS_OLD_TOWN_01` / `NEUSS_SUBURBAN_01` / `NEUSS_VILLA_01`
    (637 rows total) — named "typology pilot" segments, distinct from and never
    covered by the PLZ-based OSM extraction/rebuild.
These 931 rows are OUT OF SCOPE for this fix (never touched by
`build_neuss_buildings_from_geojson.py` or `build_neuss_buildings_final.py`) and
MUST be preserved untouched. This script therefore does a **scoped** replace: it
drops only the 8 `NEUSS_PLZ*` segments from the current file and re-adds the
Stage A final set in their place, leaving every other row byte-identical.

Safety:
  - Backs up the pre-swap `data/buildings.parquet` to
    `data/backups/buildings.parquet.pre_neuss_fix_2026-07-11` BEFORE writing.
  - Hard-asserts row-count and dedup invariants before writing.

Known, investigated, benign cross-namespace overlap (NOT the bug pattern being fixed):
  82 building_ids are shared between `ALLERHEILIGEN_PILOT_SEG_01` (a preserved,
  out-of-scope, non-PLZ pilot segment covering the Allerheiligen neighborhood) and the
  new `NEUSS_PLZ41469` rows. Investigated: in all 82 cases the ALLERHEILIGEN copy has
  NULL street/postal_code/lat/lon (a thin early pilot extraction) while the NEUSS_PLZ41469
  copy has full real attributes -- i.e. Allerheiligen geographically sits inside PLZ 41469,
  and the comprehensive geojson-based rebuild now correctly captures it (the old buggy
  per-PLZ bbox extraction for 41469 apparently missed this pocket -- zero overlap existed
  pre-swap). This is architecturally different from the original bug (the same building
  fraudulently cloned across multiple CO-EQUAL PLZ segments with a fabricated postal_code
  each): here one building legitimately belongs to both a PLZ segment (its true postal
  code) and a thematic/geographic pilot sub-segment. `core/building_universe.py`'s
  `count_buildings_per_segment` counts rows via a per-segment_id `value_counts()`, so this
  cross-namespace overlap does not inflate or corrupt any single segment's own count --
  confirmed by reading that function before writing this script. The checks below
  therefore hard-fail on ANY duplication among the 8 NEUSS_PLZ* segments (the real bug
  pattern) or against the other 4 non-PLZ NEUSS_* pilot segments, but explicitly tolerate
  (and print in full) the ALLERHEILIGEN_PILOT_SEG_01 <-> NEUSS_PLZ41469 overlap.
"""

import os
import shutil

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CURRENT_PATH = os.path.join(BASE_DIR, "data", "buildings.parquet")
FINAL_PATH = os.path.join(BASE_DIR, "data", "buildings_neuss_final.parquet")
# NOTE (2026-07-14, second run — spatial-PLZ P3): this is a NEW backup path
# for THIS swap, distinct from the 2026-07-11 fix's own backup. Reusing the
# 2026-07-11 path would fail its own idempotency check for the right reason
# (buildings.parquet legitimately changed between the two runs, via that
# first fix) — both backups are kept, not one overwritten by the other.
BACKUP_PATH = os.path.join(BASE_DIR, "data", "backups", "buildings.parquet.pre_neuss_plz_spatial_fix_2026-07-14")

KNOWN_NEUSS_PLZ = ["41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472"]
NEUSS_8PLZ_SEGMENTS = {f"NEUSS_PLZ{plz}" for plz in KNOWN_NEUSS_PLZ}


def main():
    print("=" * 70)
    print("NEUSS BUILDINGS SWAP — PHASE 2 STAGE B (destructive, backed up)")
    print("=" * 70)

    current = pd.read_parquet(CURRENT_PATH)
    final_neuss = pd.read_parquet(FINAL_PATH)
    print(f"\n[LOAD] current buildings.parquet: {len(current)} rows")
    print(f"[LOAD] Stage A final Neuss set: {len(final_neuss)} rows")

    # --- Backup BEFORE any write (idempotent: an earlier run may have already backed
    #     up and then safely aborted pre-write on a stricter duplicate check -- in that
    #     case data/buildings.parquet is still byte-for-byte the pre-swap original, so
    #     re-verify the existing backup matches instead of re-copying / failing). ---
    os.makedirs(os.path.dirname(BACKUP_PATH), exist_ok=True)
    if os.path.exists(BACKUP_PATH):
        backup_check = pd.read_parquet(BACKUP_PATH)
        assert len(backup_check) == len(current), (
            f"Backup already exists at {BACKUP_PATH} but its row count ({len(backup_check)}) "
            f"does not match the current file ({len(current)}) -- ABORT, investigate: this "
            f"would mean buildings.parquet changed since the backup was taken."
        )
        assert backup_check["building_id"].tolist() == current["building_id"].tolist(), (
            "Backup exists but building_id sequence differs from current file -- ABORT, investigate."
        )
        print(f"\n[BACKUP] Pre-existing backup at {BACKUP_PATH} verified identical to current "
              f"file ({len(backup_check)} rows) -- reusing, not re-copying.")
    else:
        shutil.copy2(CURRENT_PATH, BACKUP_PATH)
        print(f"\n[BACKUP] Copied current buildings.parquet -> {BACKUP_PATH}")
        backup_check = pd.read_parquet(BACKUP_PATH)
        assert len(backup_check) == len(current), "backup row count mismatch -- ABORT"
        print(f"[BACKUP] Verified backup readable, {len(backup_check)} rows match original")

    # --- Split current file: 8-PLZ Neuss rows (to be replaced) vs everything else (preserved) ---
    seg = current["segment_id"].astype(str)
    old_neuss_8plz = current[seg.isin(NEUSS_8PLZ_SEGMENTS)]
    preserved = current[~seg.isin(NEUSS_8PLZ_SEGMENTS)].copy()
    print(f"\n[SPLIT] old 8-PLZ Neuss rows (to be replaced): {len(old_neuss_8plz)}")
    print(f"[SPLIT] preserved rows (untouched, out of scope): {len(preserved)}")
    print("[SPLIT] preserved segment_id distribution:")
    print(preserved["segment_id"].value_counts().to_string())

    # --- Sanity: preserved set must be exactly the known out-of-scope segments ---
    preserved_segs = set(preserved["segment_id"].astype(str).unique())
    expected_preserved_segs = {
        "ALLERHEILIGEN_PILOT_SEG_01", "NEUSS_DENSE_01", "NEUSS_OLD_TOWN_01",
        "NEUSS_SUBURBAN_01", "NEUSS_VILLA_01",
    }
    assert preserved_segs == expected_preserved_segs, (
        f"preserved segments differ from expected out-of-scope set -- ABORT. "
        f"got={preserved_segs} expected={expected_preserved_segs}"
    )
    assert len(preserved) == 931, f"expected 931 preserved rows, got {len(preserved)} -- ABORT"

    # --- Schema alignment check ---
    assert list(final_neuss.columns) == list(current.columns), "schema mismatch -- ABORT"

    # --- Scoped duplicate checks (see module docstring for why a global zero-dup
    #     assertion is wrong here: a benign cross-namespace overlap with the
    #     out-of-scope ALLERHEILIGEN_PILOT_SEG_01 pilot segment is expected). ---
    print("\n[VERIFY]")
    dup_within_final = int(final_neuss["building_id"].duplicated().sum())
    print(f"  duplicate building_id WITHIN Stage A final Neuss set: {dup_within_final}")
    assert dup_within_final == 0, "duplicate building_id within final Neuss set -- ABORT"

    dup_within_preserved = int(preserved["building_id"].duplicated().sum())
    print(f"  duplicate building_id WITHIN preserved (out-of-scope) rows: {dup_within_preserved}")
    assert dup_within_preserved == 0, "duplicate building_id within preserved rows -- ABORT"

    cross_ids = set(preserved["building_id"]) & set(final_neuss["building_id"])
    cross_detail = preserved[preserved["building_id"].isin(cross_ids)]["segment_id"].value_counts()
    print(f"  building_id overlap between preserved segments and Stage A final Neuss set: {len(cross_ids)}")
    print(f"  overlap breakdown by preserved segment_id:\n{cross_detail.to_string()}")

    # Hard-fail only if the overlap touches a PLZ-tier-equivalent NEUSS_* pilot segment
    # (that WOULD reproduce the original bug pattern: same building double-claimed by
    # two co-equal segments). Overlap with ALLERHEILIGEN_PILOT_SEG_01 (a different,
    # smaller, non-PLZ neighborhood pilot) is investigated-benign (see docstring) and
    # explicitly tolerated.
    bug_pattern_segs = {"NEUSS_DENSE_01", "NEUSS_OLD_TOWN_01", "NEUSS_SUBURBAN_01", "NEUSS_VILLA_01"}
    bad_overlap = set(cross_detail.index) & bug_pattern_segs
    assert not bad_overlap, (
        f"unexpected building_id overlap with NEUSS_* pilot segment(s) {bad_overlap} -- "
        f"this WOULD reproduce the original bug pattern -- ABORT, investigate before proceeding"
    )
    assert set(cross_detail.index) <= {"ALLERHEILIGEN_PILOT_SEG_01"}, (
        f"overlap with unexpected preserved segment(s) -- ABORT, investigate: {set(cross_detail.index)}"
    )

    # --- Build new combined file ---
    new_buildings = pd.concat([preserved, final_neuss], ignore_index=True)

    expected_total = len(preserved) + len(final_neuss)
    print(f"  row count: {len(new_buildings)} (expected {expected_total} = "
          f"{len(preserved)} preserved + {len(final_neuss)} final Neuss)")
    assert len(new_buildings) == expected_total

    print("\n  new segment_id distribution (all segments):")
    print(new_buildings["segment_id"].value_counts().to_string())

    # --- Write (the actual swap) ---
    new_buildings.to_parquet(CURRENT_PATH, index=False)
    print(f"\n[SWAP] Wrote {len(new_buildings)} rows to {CURRENT_PATH}")

    # --- Post-write re-read verification ---
    reread = pd.read_parquet(CURRENT_PATH)
    assert len(reread) == len(new_buildings)
    reread_dup_ids = reread.loc[reread["building_id"].duplicated(keep=False), "building_id"].unique()
    for bid in reread_dup_ids:
        segs_for_id = set(reread.loc[reread["building_id"] == bid, "segment_id"])
        assert segs_for_id == {"ALLERHEILIGEN_PILOT_SEG_01", "NEUSS_PLZ41469"}, (
            f"post-write re-read found an unexpected duplicate building_id {bid} "
            f"across segments {segs_for_id} -- investigate"
        )
    assert len(reread_dup_ids) == len(cross_ids)
    print(f"[SWAP] Post-write re-read verified: {len(reread)} rows, "
          f"{len(reread_dup_ids)} duplicate building_id (all confirmed = the known benign "
          f"ALLERHEILIGEN_PILOT_SEG_01 <-> NEUSS_PLZ41469 overlap, nothing else)")
    print(f"\n[DONE] Old file preserved at {BACKUP_PATH}")


if __name__ == "__main__":
    main()
