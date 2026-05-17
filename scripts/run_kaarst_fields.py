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
logger = logging.getLogger("KaarstFields")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIELDS_DIR = os.path.join(DATA_DIR, "fields")

def append_to_parquet(df_new, file_name, segment_col="segment_id"):
    if df_new.empty:
        logger.warning(f"No data returned for {file_name}")
        return
    path = os.path.join(FIELDS_DIR, file_name)
    if os.path.exists(path):
        df_old = pd.read_parquet(path)
        # Remove any existing rows for the segments we are processing
        segs = df_new[segment_col].unique()
        df_old = df_old[~df_old[segment_col].isin(segs)]
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new
    df_combined.to_parquet(path, index=False)
    logger.info(f"Appended {len(df_new)} rows to {file_name}. Total rows: {len(df_combined)}")

def main():
    logger.info("=== Starting Kaarst Phase 3 Fields ===")
    kaarst_b_path = os.path.join(DATA_DIR, "kaarst_buildings.parquet")
    if not os.path.exists(kaarst_b_path):
        logger.error(f"{kaarst_b_path} not found!")
        return
    
    buildings_df = pd.read_parquet(kaarst_b_path)
    logger.info(f"Loaded {len(buildings_df)} Kaarst buildings.")

    # 1. Field 02: Building Type
    logger.info("--- Running Field 02 (Building Type) ---")
    df_f02 = field_02_building_type.run(buildings_df)
    append_to_parquet(df_f02, "field_02_building_type.parquet")
    
    # Temporarily copy field_02_building_type.parquet to the data folder if Field 01 strictly looks there
    # Wait, in field 01 it reads from os.path.join(base_dir, "data", "fields", "field_02_building_type.parquet")
    # which is exactly FIELDS_DIR, so we are good.

    # 2. Field 01: Roof Potential
    # IMPORTANT: field_01.run() internally reads field_02_building_type.parquet from disk
    # and does a left-merge on building_id. Because the full F02 parquet now contains both
    # Neuss and Kaarst rows, and some OSM building_ids appear in multiple Neuss segments
    # (border buildings), the merge would produce duplicate rows and inflate building_count.
    # FIX: temporarily write a Kaarst-only snapshot of F02, run Field 01, then restore.
    logger.info("--- Running Field 01 (Roof Potential) ---")
    f02_full_path = os.path.join(FIELDS_DIR, "field_02_building_type.parquet")
    f02_backup_path = f02_full_path + ".neuss_backup"
    df_f02_full = pd.read_parquet(f02_full_path)
    df_f02_kaarst_only = df_f02_full[df_f02_full["segment_id"] == "KAARST_OSM_41564"]

    import shutil
    shutil.copy2(f02_full_path, f02_backup_path)
    try:
        df_f02_kaarst_only.to_parquet(f02_full_path, index=False)
        df_f01 = field_01_roof_potential.run(buildings_df)
    finally:
        shutil.copy2(f02_backup_path, f02_full_path)
        os.remove(f02_backup_path)
    append_to_parquet(df_f01, "field_01_roof_potential.parquet")

    # 3. Field 03: District Heating
    logger.info("--- Running Field 03 (District Heating) ---")
    df_f03 = field_03_district_heating.run(buildings_df)
    append_to_parquet(df_f03, "field_03_district_heating.parquet")
    
    # 4. Field 04: PV Adoption
    logger.info("--- Running Field 04 (PV Adoption) ---")
    field_04_pv_adoption.REAL_GROUNDED_SEGMENTS["KAARST_OSM_41564"] = {
        "plz": "41564",
        "segment_buildings": 9949,   
        "plz_buildings": 12000,      
        "morphology_factor": 1.0,    
        "city": "Kaarst",
        "persistent_id": "KAARST_OSM_41564",
    }
    # field_04 run() returns a dataframe with all segments.
    df_f04_all = field_04_pv_adoption.run()
    # Extract only Kaarst rows to append properly
    df_f04_kaarst = df_f04_all[df_f04_all["segment_id"] == "KAARST_OSM_41564"]
    append_to_parquet(df_f04_kaarst, "field_04_pv_adoption.parquet")
    
    logger.info("=== Phase 3 Fields completed successfully. ===")

if __name__ == "__main__":
    main()
