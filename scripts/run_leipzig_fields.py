import json
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

# Real per-PLZ building counts, both derived from actual osmium extraction
# passes over data/osm/sachsen-latest.osm.pbf (NOT hand-estimated) — see
# scripts/generate_leipzig_buildings.py (single combined pass, 2026-07-13):
#   segment_buildings = residential buildings with addr:street tag
#   plz_buildings      = ALL building=* ways (any type) with a recognized
#                        addr:postcode tag, within the Leipzig boundary
#                        (data/leipzig_plz_buildings_denominator.json)
# morphology_factor = 1.0 (neutral) for every segment — same rationale as
# Augsburg: no evidence basis here to justify differentiated per-PLZ
# morphology adjustment, so no adjustment is applied rather than fabricating one.
with open(os.path.join(DATA_DIR, "leipzig_plz_buildings_denominator.json"), encoding="utf-8") as f:
    _PLZ_BUILDINGS_DENOM = json.load(f)

_SEGMENT_BUILDINGS_COUNTS = {
    "04103": 351, "04105": 913, "04107": 541, "04109": 578, "04129": 793,
    "04155": 1166, "04157": 1208, "04158": 2949, "04159": 3117, "04177": 1161,
    "04178": 1564, "04179": 1312, "04205": 528, "04207": 741, "04209": 45,
    "04229": 2035, "04249": 2576, "04275": 1188, "04277": 2232, "04279": 569,
    "04288": 1408, "04289": 990, "04299": 996, "04315": 609, "04316": 1156,
    "04317": 562, "04318": 368, "04319": 1768, "04328": 434, "04329": 188,
    "04347": 1034, "04349": 1047, "04356": 369, "04357": 848,
}

LEIPZIG_PLZ_BUILDING_COUNTS = {
    plz: {
        "segment_buildings": _SEGMENT_BUILDINGS_COUNTS[plz],
        "plz_buildings": _PLZ_BUILDINGS_DENOM[plz],
    }
    for plz in _SEGMENT_BUILDINGS_COUNTS
}


def append_to_parquet(df_new, file_name, segment_col="segment_id"):
    if df_new.empty:
        logger.warning(f"No data returned for {file_name}")
        return
    path = os.path.join(FIELDS_DIR, file_name)
    if os.path.exists(path):
        df_old = pd.read_parquet(path)
        segs = df_new[segment_col].unique()
        df_old = df_old[~df_old[segment_col].isin(segs)]
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
