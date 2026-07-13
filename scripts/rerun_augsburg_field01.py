"""Re-run Field 01 only for Augsburg with the merge-isolation fix.

Same isolate-then-restore pattern as rerun_kaarst_field01.py /
run_augsburg_fields.py's Field 01 step: temporarily scope the shared
field_02_building_type.parquet to Augsburg-only rows so field_01's
building_id merge can't fan out across cities, run field_01, then restore
the full field_02 parquet from a backup. Writes (append-only, replacing
only AUGSBURG_ rows) into field_01_roof_potential.parquet.
"""
import os, sys, shutil
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fields import field_01_roof_potential

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS_DIR = os.path.join(BASE_DIR, "data", "fields")
BLD_PATH   = os.path.join(BASE_DIR, "data", "augsburg_buildings.parquet")

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
f02_backup_path = f02_full_path + ".pre_augsburg_field01_backup"

df_f02_full     = pd.read_parquet(f02_full_path)
df_f02_augsburg = df_f02_full[df_f02_full["segment_id"].str.startswith("AUGSBURG_")]

shutil.copy2(f02_full_path, f02_backup_path)
try:
    df_f02_augsburg.to_parquet(f02_full_path, index=False)
    df_f01 = field_01_roof_potential.run(buildings_df)
finally:
    shutil.copy2(f02_backup_path, f02_full_path)
    os.remove(f02_backup_path)

print("Field01 result:")
print(df_f01[["segment_id", "building_count", "field_value"]].sort_values("segment_id").to_string(index=False))
append_to_parquet(df_f01, "field_01_roof_potential.parquet")
