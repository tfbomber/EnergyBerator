"""
check_phase3_audit.py
=====================
Audit script for Kaarst Phase 3 Field Calculations.
Verifies data integrity, isolation, and completeness of Field 01-04 for Kaarst.
"""

import os
import sys
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS_DIR = os.path.join(BASE_DIR, "data", "fields")

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

results = []

def check(label, condition, level=PASS, detail=""):
    status = PASS if condition else FAIL
    if not condition and level == WARN:
        status = WARN
    results.append((label, status, detail))
    icon = "[OK]  " if status == PASS else ("[WARN]" if status == WARN else "[FAIL]")
    print(f"  {icon} [{status}] {label}" + (f" - {detail}" if detail else ""))

print("=" * 65)
print("  PHASE 3 AUDIT - Kaarst Field Engine")
print("=" * 65)

# 1. Check Field 02 (Building Type)
print("\n[A] Field 02: Building Type")
f02_path = os.path.join(FIELDS_DIR, "field_02_building_type.parquet")
check("field_02_building_type.parquet exists", os.path.exists(f02_path))
if os.path.exists(f02_path):
    df_f02 = pd.read_parquet(f02_path)
    kaarst_f02 = df_f02[df_f02["segment_id"] == "KAARST_OSM_41564"]
    neuss_f02  = df_f02[df_f02["segment_id"] != "KAARST_OSM_41564"]
    
    check("Exactly 9,949 Kaarst building records generated", len(kaarst_f02) == 9949, detail=f"actual={len(kaarst_f02)}")
    check("Neuss F02 data untouched (26,187 records)", len(neuss_f02) == 26187, detail=f"actual={len(neuss_f02)}")
    
    null_types = kaarst_f02["field_value"].isnull().sum()
    check("No NULL field_values in Kaarst records", null_types == 0, detail=f"nulls={null_types}")

# 2. Check Field 01 (Roof Potential)
print("\n[B] Field 01: Roof Potential")
f01_path = os.path.join(FIELDS_DIR, "field_01_roof_potential.parquet")
check("field_01_roof_potential.parquet exists", os.path.exists(f01_path))
if os.path.exists(f01_path):
    df_f01 = pd.read_parquet(f01_path)
    kaarst_f01 = df_f01[df_f01["segment_id"] == "KAARST_OSM_41564"]
    neuss_f01  = df_f01[df_f01["segment_id"] != "KAARST_OSM_41564"]
    
    check("Exactly 1 Kaarst segment record generated", len(kaarst_f01) == 1, detail=f"actual={len(kaarst_f01)}")
    check("Neuss F01 data untouched (12 records)", len(neuss_f01) == 12, detail=f"actual={len(neuss_f01)}")
    if len(kaarst_f01) == 1:
        pv_score = kaarst_f01.iloc[0]["field_value"]
        check("PV utilization score in plausible range [0.1, 0.45]", 0.1 <= pv_score <= 0.45, detail=f"score={pv_score:.4f}")

# 3. Check Field 03 (District Heating)
print("\n[C] Field 03: District Heating")
f03_path = os.path.join(FIELDS_DIR, "field_03_district_heating.parquet")
check("field_03_district_heating.parquet exists", os.path.exists(f03_path))
if os.path.exists(f03_path):
    df_f03 = pd.read_parquet(f03_path)
    kaarst_f03 = df_f03[df_f03["segment_id"] == "KAARST_OSM_41564"]
    neuss_f03  = df_f03[df_f03["segment_id"] != "KAARST_OSM_41564"]
    
    check("Exactly 9,949 Kaarst heating records generated", len(kaarst_f03) == 9949, detail=f"actual={len(kaarst_f03)}")
    check("Neuss F03 data untouched (848 records)", len(neuss_f03) == 848, detail=f"actual={len(neuss_f03)}")
    
    # We expect all Kaarst to be "NONE" because we didn't inject a Kaarst heating GeoJSON
    non_none = kaarst_f03[kaarst_f03["field_value"] != "NONE"]
    check("All Kaarst heating statuses are NONE (safe fallback)", len(non_none) == 0, detail=f"violations={len(non_none)}")

# 4. Check Field 04 (PV Adoption)
print("\n[D] Field 04: PV Adoption")
f04_path = os.path.join(FIELDS_DIR, "field_04_pv_adoption.parquet")
check("field_04_pv_adoption.parquet exists", os.path.exists(f04_path))
if os.path.exists(f04_path):
    df_f04 = pd.read_parquet(f04_path)
    kaarst_f04 = df_f04[df_f04["segment_id"] == "KAARST_OSM_41564"]
    neuss_f04  = df_f04[df_f04["segment_id"] != "KAARST_OSM_41564"]
    
    check("Exactly 1 Kaarst PV record generated", len(kaarst_f04) == 1, detail=f"actual={len(kaarst_f04)}")
    check("Neuss F04 data untouched (8 records)", len(neuss_f04) == 8, detail=f"actual={len(neuss_f04)}")
    if len(kaarst_f04) == 1:
        e3_score = kaarst_f04.iloc[0]["field_value"]
        check("E3 PV Adoption score capped correctly (<= 0.5)", e3_score <= 0.5, detail=f"score={e3_score}")

print("\n" + "=" * 65)
total  = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
warns  = sum(1 for _, s, _ in results if s == WARN)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"  RESULT: {passed}/{total} PASS  |  {warns} WARN  |  {failed} FAIL")
print("=" * 65)

if failed > 0:
    sys.exit(1)
