"""
build_neuss_buildings_final.py
================================
Neuss building-data rebuild — Phase 2 / Stage A (non-destructive).

Combines the Phase-1 rebuilt 7-PLZ polygon set (`data/buildings_neuss_rebuilt.parquet`,
built by `build_neuss_buildings_from_geojson.py` from the normalized OSM geojson) with
the 8th PLZ (41470), which is ABSENT from the source geojson snapshot (a source-data
gap, not a pipeline bug — see scratch/neuss_rebuild_phase1.md in the sibling territoryai
repo). The 41470 rows are recovered from the CURRENT `data/buildings.parquet`, which
still holds 1,498 real, non-duplicated, non-fabricated-postcode 41470 rows (this PLZ
was run as a separate one-off extraction on 2026-04-12, after the other PLZ were
already persisted, so it happened to escape the cross-PLZ dedup-gap bug documented in
docs/neuss_buildings_duplicate_building_id_root_cause.md).

Recovered-41470 handling (D2-consistent):
  - 1,494 of the 1,498 rows carry a real `street` (POINT geometry, legacy Overpass
    centroid extraction, pre-polygon-backfill). Kept.
  - 4 of the 1,498 rows have NULL street/city/lat/lon/building_type (only geometry +
    postal_code populated) -- likely stray artifacts of the later polygon-backfill
    pass. These fail the same D2 "must have a real street tag" bar the rest of this
    rebuild enforces everywhere else, so they are DROPPED here for consistency (not
    silently kept with blank street, and not fabricated). Their building_ids/geometry
    are printed below for auditability.
  - Kept rows get a distinct `geometry_source` marker (`LEGACY_OVERPASS_POINT_41470`)
    so their point-vs-polygon provenance stays visible and distinguishable from the
    Phase-1 rebuild's `OSM_OVERPASS_POLYGON_REBUILD_2026-07` marker.

PHASE 2 STAGE A SAFETY: this script only ever WRITES to a new file,
`data/buildings_neuss_final.parquet`. It never writes `data/buildings.parquet`.
The swap into `data/buildings.parquet` is Stage B, gated on this stage's audit
(`check_neuss_rebuild_audit.py --input data/buildings_neuss_final.parquet`) passing.

Output: data/buildings_neuss_final.parquet
"""

import os

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REBUILT_PATH = os.path.join(BASE_DIR, "data", "buildings_neuss_rebuilt.parquet")
CURRENT_PATH = os.path.join(BASE_DIR, "data", "buildings.parquet")
OUT_PATH = os.path.join(BASE_DIR, "data", "buildings_neuss_final.parquet")

KNOWN_NEUSS_PLZ = {
    "41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472",
}

RECOVERED_41470_GEOMETRY_SOURCE = "LEGACY_OVERPASS_POINT_41470"


def main():
    print("=" * 70)
    print("NEUSS BUILDINGS FINAL BUILD — PHASE 2 STAGE A (non-destructive)")
    print("=" * 70)

    rebuilt = pd.read_parquet(REBUILT_PATH)
    current = pd.read_parquet(CURRENT_PATH)
    print(f"\n[LOAD] rebuilt (7-PLZ): {len(rebuilt)} rows, columns={list(rebuilt.columns)}")
    print(f"[LOAD] current buildings.parquet: {len(current)} rows")

    rebuilt_plz = set(rebuilt["postal_code"].astype(str).unique())
    print(f"[CHECK] rebuilt PLZ set: {sorted(rebuilt_plz)} (expect 7 of 8, missing 41470)")
    assert "41470" not in rebuilt_plz, "rebuilt set unexpectedly already contains 41470"

    # --- Recover 41470 from current buildings.parquet ---
    sub = current[current["segment_id"] == "NEUSS_PLZ41470"].copy()
    print(f"\n[RECOVER 41470] {len(sub)} rows with segment_id == NEUSS_PLZ41470")
    assert len(sub) == 1498, f"expected 1498 NEUSS_PLZ41470 rows, found {len(sub)} -- investigate before proceeding"

    dup_in_sub = int(sub["building_id"].duplicated().sum())
    print(f"[RECOVER 41470] duplicate building_id within 41470 subset: {dup_in_sub}")
    assert dup_in_sub == 0

    no_street_mask = sub["street"].isna() | (sub["street"].astype(str).str.strip() == "")
    dropped = sub[no_street_mask]
    kept = sub[~no_street_mask].copy()
    print(f"[RECOVER 41470] D2-consistency filter (drop null/blank street): "
          f"{len(sub)} -> {len(kept)} kept, {len(dropped)} dropped")
    if len(dropped):
        print("[RECOVER 41470] DROPPED rows (no real street tag -- full record for audit trail):")
        print(dropped.to_string())

    # --- Provenance markers on the kept recovered rows ---
    kept["geometry_source"] = RECOVERED_41470_GEOMETRY_SOURCE
    kept["address_source"] = "OSM"
    kept["building_type_source"] = "OSM"
    kept["building_type_confidence"] = "MEDIUM"

    # --- Align schema exactly (column set + order) to the rebuilt frame ---
    missing_in_kept = set(rebuilt.columns) - set(kept.columns)
    extra_in_kept = set(kept.columns) - set(rebuilt.columns)
    assert not missing_in_kept, f"recovered 41470 rows missing columns vs rebuilt schema: {missing_in_kept}"
    assert not extra_in_kept, f"recovered 41470 rows have extra columns vs rebuilt schema: {extra_in_kept}"
    kept = kept[rebuilt.columns.tolist()]

    # --- Concatenate ---
    final = pd.concat([rebuilt, kept], ignore_index=True)

    # --- Hard verification gate ---
    print("\n[VERIFY]")
    dup_final = int(final["building_id"].duplicated().sum())
    print(f"  duplicate building_id across combined set: {dup_final}")
    assert dup_final == 0, "duplicate building_id found in final combined set -- ABORT"

    final_plz = set(final["postal_code"].astype(str).unique())
    print(f"  PLZ present: {sorted(final_plz)}")
    assert final_plz == KNOWN_NEUSS_PLZ, f"expected exactly the 8 known Neuss PLZ, got {sorted(final_plz)}"

    schema_ok = list(final.columns) == list(rebuilt.columns) == list(current.columns)
    print(f"  schema identical to buildings_neuss_rebuilt.parquet AND current buildings.parquet: {schema_ok}")
    assert schema_ok

    print("\n[PLZ DISTRIBUTION] (final combined set)")
    print(final["postal_code"].value_counts().sort_index().to_string())

    print("\n[GEOMETRY_SOURCE DISTRIBUTION]")
    print(final["geometry_source"].value_counts().to_string())

    print(f"\n[TOTAL] {len(final)} rows ({len(rebuilt)} rebuilt 7-PLZ + {len(kept)} recovered 41470, "
          f"{len(dropped)} dropped for missing street)")

    final.to_parquet(OUT_PATH, index=False)
    print(f"\n[OUTPUT] Wrote {len(final)} rows to {OUT_PATH}")
    print("[OUTPUT] data/buildings.parquet was NOT touched (Stage B does the swap).")


if __name__ == "__main__":
    main()
