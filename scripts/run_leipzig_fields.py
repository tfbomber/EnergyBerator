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
logger = logging.getLogger("LeipzigFields")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIELDS_DIR = os.path.join(DATA_DIR, "fields")

# Real per-PLZ residential building counts, recomputed from the current
# leipzig_buildings.parquet (2026-07-14, post spatial-PLZ-fallback
# re-extraction — see scripts/generate_leipzig_buildings.py and
# .ai/implementation_plan_leipzig_plz_spatial.md). Values refreshed via
# `df.groupby("segment_id").size()`, replacing the pre-fix counts (which
# excluded the ~22.6% of buildings that lacked addr:postcode).
#
# D4=gamma (2026-07-14, locked): plz_buildings denominator is now the SAME
# residential count as segment_buildings — a true residential PV-adoption
# rate (pv_est / residential_buildings), not the old separate all-type
# denominator (leipzig_plz_buildings_denominator.json, no longer produced —
# generate_leipzig_buildings.py dropped it since D4=gamma has no use for a
# non-residential count). morphology_factor = 1.0 (neutral) for every
# segment — same rationale as Augsburg: no evidence basis here to justify
# differentiated per-PLZ morphology adjustment, so no adjustment is applied
# rather than fabricating one.
_SEGMENT_BUILDINGS_COUNTS = {
    "04103": 401, "04105": 963, "04107": 562, "04109": 593,
    "04129": 1206, "04155": 1244, "04157": 1261, "04158": 3874,
    "04159": 3588, "04177": 1224, "04178": 2102, "04179": 1356,
    "04205": 985, "04207": 1929, "04209": 63, "04229": 2255,
    "04249": 3514, "04275": 1209, "04277": 2283, "04279": 1187,
    "04288": 3214, "04289": 1080, "04299": 1087, "04315": 643,
    "04316": 1846, "04317": 598, "04318": 466, "04319": 1959,
    "04328": 588, "04329": 461, "04347": 1087, "04349": 1759,
    "04356": 761, "04357": 912,
}

LEIPZIG_PLZ_BUILDING_COUNTS = {
    plz: {
        "segment_buildings": count,
        "plz_buildings": count,  # D4=gamma: denominator == residential count
    }
    for plz, count in _SEGMENT_BUILDINGS_COUNTS.items()
}


def append_to_parquet(df_new, file_name, segment_col="segment_id"):
    """
    BUGFIX (2026-07-14, found while executing the PLZ-spatial-fallback fix):
    the old dedup (`~isin(segs)`, segs = this run's OWN segment_id set) only
    drops old rows whose segment_id is STILL present in the new output. That
    silently breaks the moment a segment_id vanishes entirely from a rerun —
    exactly what happens here: LEIPZIG_OSM_GENERAL produced 10,916 rows
    before the spatial-PLZ fix and ZERO after (every one of those buildings
    now resolves to a real PLZ). The old logic left 10,916 stale
    LEIPZIG_OSM_GENERAL rows in field_01/02/03's parquets, duplicating every
    reassigned building_id (once under its old GENERAL label, once under its
    new correct segment_id) — which would have silently doubled every
    building street_building_types.compute_street_type_counts joins by
    building_id downstream. Fix: drop ALL prior LEIPZIG_* rows (this script
    only ever processes Leipzig's own segment universe, so a full-city
    replace is always correct here), not just the subset whose segment_id
    happens to reappear in this run.
    """
    if df_new.empty:
        logger.warning(f"No data returned for {file_name}")
        return
    path = os.path.join(FIELDS_DIR, file_name)
    if os.path.exists(path):
        df_old = pd.read_parquet(path)
        df_old = df_old[~df_old[segment_col].astype(str).str.startswith("LEIPZIG_")]
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new
    df_combined.to_parquet(path, index=False)
    logger.info(f"Appended {len(df_new)} rows to {file_name}. Total rows: {len(df_combined)}")


def main():
    logger.info("=== Starting Leipzig Fields ===")
    leipzig_b_path = os.path.join(DATA_DIR, "leipzig_buildings.parquet")
    if not os.path.exists(leipzig_b_path):
        logger.error(f"{leipzig_b_path} not found!")
        return

    buildings_df = pd.read_parquet(leipzig_b_path)
    logger.info(f"Loaded {len(buildings_df)} Leipzig buildings across "
                f"{buildings_df['segment_id'].nunique()} segments.")

    # 1. Field 02: Building Type
    logger.info("--- Running Field 02 (Building Type) ---")
    df_f02 = field_02_building_type.run(buildings_df)
    append_to_parquet(df_f02, "field_02_building_type.parquet")

    # 2. Field 01: Roof Potential
    # Same isolate-then-restore pattern as run_augsburg_fields.py: field_01
    # internally re-reads the GLOBAL field_02_building_type.parquet and
    # left-merges on building_id. OSM way IDs are globally unique and
    # Leipzig/Neuss/Kaarst/Augsburg are geographically disjoint, so a
    # cross-city building_id collision is not possible — restrict to
    # Leipzig-only rows during the run as a defensive measure anyway
    # (matches the documented Neuss historical-duplicate caution).
    logger.info("--- Running Field 01 (Roof Potential) ---")
    f02_full_path = os.path.join(FIELDS_DIR, "field_02_building_type.parquet")
    f02_backup_path = f02_full_path + ".pre_leipzig_backup"
    df_f02_full = pd.read_parquet(f02_full_path)
    df_f02_leipzig_only = df_f02_full[df_f02_full["segment_id"].str.startswith("LEIPZIG_")]

    import shutil
    shutil.copy2(f02_full_path, f02_backup_path)
    try:
        df_f02_leipzig_only.to_parquet(f02_full_path, index=False)
        df_f01 = field_01_roof_potential.run(buildings_df)
    finally:
        shutil.copy2(f02_backup_path, f02_full_path)
        os.remove(f02_backup_path)
    append_to_parquet(df_f01, "field_01_roof_potential.parquet")

    # 3. Field 03: District Heating
    # No Leipzig district-heating geodata source exists in this repo (same
    # as Kaarst/Augsburg) — trivially returns NONE/neutral for every segment.
    logger.info("--- Running Field 03 (District Heating) ---")
    df_f03 = field_03_district_heating.run(buildings_df)
    append_to_parquet(df_f03, "field_03_district_heating.parquet")

    # 4. Field 04: PV Adoption
    logger.info("--- Running Field 04 (PV Adoption) ---")
    for plz, counts in LEIPZIG_PLZ_BUILDING_COUNTS.items():
        segment_id = f"LEIPZIG_OSM_{plz}"
        field_04_pv_adoption.REAL_GROUNDED_SEGMENTS[segment_id] = {
            "plz": plz,
            "segment_buildings": counts["segment_buildings"],
            "plz_buildings": counts["plz_buildings"],
            "morphology_factor": 1.0,
            "city": "Leipzig",
            "persistent_id": segment_id,
        }
    # field_04 run() processes ALL registered REAL_GROUNDED_SEGMENTS (mutated
    # in-process dict — includes Neuss + Kaarst + Augsburg + Leipzig if this
    # process previously ran their onboarding too, but each city's onboarding
    # is a separate process invocation in practice) and returns a dataframe
    # with everything currently registered.
    df_f04_all = field_04_pv_adoption.run()
    df_f04_leipzig = df_f04_all[df_f04_all["segment_id"].str.startswith("LEIPZIG_")]
    append_to_parquet(df_f04_leipzig, "field_04_pv_adoption.parquet")

    logger.info("=== Leipzig Fields completed successfully. ===")


if __name__ == "__main__":
    main()
