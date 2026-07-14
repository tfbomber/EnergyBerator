import os
import sys
import pandas as pd
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fields import field_02_building_type
from fields import field_01_roof_potential
from fields import field_03_district_heating
from fields import field_04_pv_adoption

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")
logger = logging.getLogger("AugsburgFields")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIELDS_DIR = os.path.join(DATA_DIR, "fields")

# Real per-PLZ residential building counts, recomputed from the current
# augsburg_buildings.parquet (2026-07-14, post spatial-PLZ-fallback
# re-extraction — spatial-PLZ P3, see scripts/generate_augsburg_buildings.py
# and .ai/implementation_plan_leipzig_plz_spatial.md). Values refreshed via
# `df.groupby("segment_id").size()`, replacing the pre-fix counts (which
# excluded the 3.6% of buildings that lacked addr:postcode).
#
# D4=gamma (2026-07-14, same definition locked for Leipzig, applied here for
# consistency): plz_buildings denominator is now the SAME residential count
# as segment_buildings — a true residential PV-adoption rate, not the old
# separate all-type-tagged-only denominator (which was itself a hardcoded
# hand-derived estimate, not reproducibly computed here).
# morphology_factor = 1.0 (neutral) for every segment — unlike Neuss/Kaarst's
# per-PLZ factors (0.80-1.1), there is no evidence basis here to justify
# differentiated per-PLZ morphology adjustment, so no adjustment is applied
# rather than fabricating one.
_SEGMENT_BUILDINGS_COUNTS = {
    "86150": 1365, "86152": 1481, "86153": 1377, "86154": 1865,
    "86156": 4444, "86157": 2752, "86159": 1603, "86161": 1943,
    "86163": 3857, "86165": 2098, "86167": 2038, "86169": 3362,
    "86179": 3997, "86199": 5068,
}

AUGSBURG_PLZ_BUILDING_COUNTS = {
    plz: {
        "segment_buildings": count,
        "plz_buildings": count,  # D4=gamma: denominator == residential count
    }
    for plz, count in _SEGMENT_BUILDINGS_COUNTS.items()
}


def append_to_parquet(df_new, file_name, segment_col="segment_id"):
    """
    BUGFIX (2026-07-14, same fix as run_leipzig_fields.py — found while
    executing the Leipzig spatial-PLZ fix, applied here proactively since
    AUGSBURG_OSM_GENERAL shrinks from 115 to 2 clusters this run, meaning
    most of its building_ids move to a different segment_id and the old
    `~isin(segs)` dedup would otherwise leave stale duplicate rows behind
    for every building whose segment_id changed. Drop ALL prior AUGSBURG_*
    rows (this script only ever processes Augsburg's own segment universe,
    so a full-city replace is always correct here), not just the subset
    whose segment_id happens to reappear in this run.
    """
    if df_new.empty:
        logger.warning(f"No data returned for {file_name}")
        return
    path = os.path.join(FIELDS_DIR, file_name)
    if os.path.exists(path):
        df_old = pd.read_parquet(path)
        df_old = df_old[~df_old[segment_col].astype(str).str.startswith("AUGSBURG_")]
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new
    df_combined.to_parquet(path, index=False)
    logger.info(f"Appended {len(df_new)} rows to {file_name}. Total rows: {len(df_combined)}")


def main():
    logger.info("=== Starting Augsburg Phase 3 Fields ===")
    augsburg_b_path = os.path.join(DATA_DIR, "augsburg_buildings.parquet")
    if not os.path.exists(augsburg_b_path):
        logger.error(f"{augsburg_b_path} not found!")
        return

    buildings_df = pd.read_parquet(augsburg_b_path)
    logger.info(f"Loaded {len(buildings_df)} Augsburg buildings across "
                f"{buildings_df['segment_id'].nunique()} segments.")

    # 1. Field 02: Building Type
    logger.info("--- Running Field 02 (Building Type) ---")
    df_f02 = field_02_building_type.run(buildings_df)
    append_to_parquet(df_f02, "field_02_building_type.parquet")

    # 2. Field 01: Roof Potential
    # Same backup/restore pattern as run_kaarst_fields.py: field_01 internally
    # re-reads the GLOBAL field_02_building_type.parquet and left-merges on
    # building_id. OSM way IDs are globally unique and Augsburg/Neuss/Kaarst
    # are geographically disjoint, so a cross-city building_id collision is
    # not possible here — but a known pre-existing data-quality artifact in
    # Neuss's own historical rows (some building_ids duplicated across
    # segments) means any extra rows in the merge target are still worth
    # excluding defensively. Restrict to Augsburg-only rows during the run.
    logger.info("--- Running Field 01 (Roof Potential) ---")
    f02_full_path = os.path.join(FIELDS_DIR, "field_02_building_type.parquet")
    f02_backup_path = f02_full_path + ".pre_augsburg_backup"
    df_f02_full = pd.read_parquet(f02_full_path)
    df_f02_augsburg_only = df_f02_full[df_f02_full["segment_id"].str.startswith("AUGSBURG_")]

    import shutil
    shutil.copy2(f02_full_path, f02_backup_path)
    try:
        df_f02_augsburg_only.to_parquet(f02_full_path, index=False)
        df_f01 = field_01_roof_potential.run(buildings_df)
    finally:
        shutil.copy2(f02_backup_path, f02_full_path)
        os.remove(f02_backup_path)
    append_to_parquet(df_f01, "field_01_roof_potential.parquet")

    # 3. Field 03: District Heating
    # Same as Kaarst: data/neuss_osm_heating.geojson is empty, so this will
    # trivially return NONE/neutral heating status for every Augsburg
    # segment. Not a bug — matches the existing Kaarst precedent exactly.
    logger.info("--- Running Field 03 (District Heating) ---")
    df_f03 = field_03_district_heating.run(buildings_df)
    append_to_parquet(df_f03, "field_03_district_heating.parquet")

    # 4. Field 04: PV Adoption
    logger.info("--- Running Field 04 (PV Adoption) ---")
    for plz, counts in AUGSBURG_PLZ_BUILDING_COUNTS.items():
        segment_id = f"AUGSBURG_OSM_{plz}"
        field_04_pv_adoption.REAL_GROUNDED_SEGMENTS[segment_id] = {
            "plz": plz,
            "segment_buildings": counts["segment_buildings"],
            "plz_buildings": counts["plz_buildings"],
            "morphology_factor": 1.0,
            "city": "Augsburg",
            "persistent_id": segment_id,
        }
    # field_04 run() processes ALL registered REAL_GROUNDED_SEGMENTS (Neuss +
    # Kaarst + Augsburg, since the dict is mutated in-process, not reloaded
    # from a per-city file) and returns a dataframe with all of them.
    df_f04_all = field_04_pv_adoption.run()
    df_f04_augsburg = df_f04_all[df_f04_all["segment_id"].str.startswith("AUGSBURG_")]
    append_to_parquet(df_f04_augsburg, "field_04_pv_adoption.parquet")

    logger.info("=== Augsburg Phase 3 Fields completed successfully. ===")


if __name__ == "__main__":
    main()
