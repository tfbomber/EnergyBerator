"""Re-run Field 01 only for Kaarst with the merge-isolation fix."""
import os, sys, shutil
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fields import field_01_roof_potential

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS_DIR = os.path.join(BASE_DIR, "data", "fields")
BLD_PATH   = os.path.join(BASE_DIR, "data", "kaarst_buildings.parquet")

def append_to_parquet(df_new, file_name):
    path = os.path.join(FIELDS_DIR, file_name)
    if os.path.exists(path):
        df_old = pd.read_parquet(path)
        segs = df_new["segment_id"].unique()
        df_old = df_old[~df_old["segment_id"].isin(segs)]
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new
    df_combined.to_parquet(path, index=False)
    print(f"Saved {len(df_new)} rows -> {file_name}. Total={len(df_combined)}")

buildings_df = pd.read_parquet(BLD_PATH)
f02_full_path   = os.path.join(FIELDS_DIR, "field_02_building_type.parquet")
f02_backup_path = f02_full_path + ".backup"

df_f02_full      = pd.read_parquet(f02_full_path)
df_f02_kaarst    = df_f02_full[df_f02_full["segment_id"] == "KAARST_OSM_41564"]

shutil.copy2(f02_full_path, f02_backup_path)
try:
    df_f02_kaarst.to_parquet(f02_full_path, index=False)
    df_f01 = field_01_roof_potential.run(buildings_df)
finally:
    shutil.copy2(f02_backup_path, f02_full_path)
    os.remove(f02_backup_path)

print("Field01 result:", df_f01[["segment_id","building_count","field_value"]].to_dict("records"))
append_to_parquet(df_f01, "field_01_roof_potential.parquet")
