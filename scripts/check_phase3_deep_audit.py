"""
check_phase3_deep_audit.py
===========================
Deep audit for Kaarst Phase 3 Field Calculations.

Checks:
  A. Field 02 - Building type distribution validity
  B. Field 01 - Roof score arithmetic re-derivation
  C. Field 03 - Heating data isolation & source integrity
  D. Field 04 - PV score arithmetic re-derivation from raw MaStR parameters
  E. Cross-field consistency (segment_ids align across all fields)
  F. Data isolation - Neuss parquets bit-identical counts
  G. File provenance (kaarst_buildings.parquet content check)
"""

import os
import sys
import json
import pandas as pd

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

# ── Load all parquets once ────────────────────────────────────────────────────
p = lambda name: pd.read_parquet(os.path.join(FIELDS_DIR, name))
bld_path = os.path.join(BASE_DIR, "data", "kaarst_buildings.parquet")

df_f01 = p("field_01_roof_potential.parquet")
df_f02 = p("field_02_building_type.parquet")
df_f03 = p("field_03_district_heating.parquet")
df_f04 = p("field_04_pv_adoption.parquet")
df_bld = pd.read_parquet(bld_path)

k_f01 = df_f01[df_f01["segment_id"] == "KAARST_OSM_41564"]
k_f02 = df_f02[df_f02["segment_id"] == "KAARST_OSM_41564"]
k_f03 = df_f03[df_f03["segment_id"] == "KAARST_OSM_41564"]
k_f04 = df_f04[df_f04["segment_id"] == "KAARST_OSM_41564"]
k_bld = df_bld[df_bld["segment_id"] == "KAARST_OSM_41564"]

print("=" * 70)
print("  PHASE 3 DEEP AUDIT - Kaarst Field Engine")
print("=" * 70)

# ── A. Field 02 - Building Type Distribution ──────────────────────────────────
print("\n[A] Field 02: Building Type Distribution")
vc = k_f02["field_value"].value_counts().to_dict()
total_k02 = len(k_f02)
print(f"    Building type breakdown (n={total_k02}):")
for bt, cnt in sorted(vc.items(), key=lambda x: -x[1]):
    print(f"      {bt:<25} {cnt:>6}  ({cnt/total_k02:.1%})")

valid_types = {"MFH_CONFIRMED","SFH_CONFIRMED","MFH_SUSPECT","SFH_WEAK","UNCERTAIN"}
bad_types = set(vc.keys()) - valid_types
check("All field_values are valid types", len(bad_types) == 0, detail=f"invalid: {bad_types}")

sfh_count = vc.get("SFH_CONFIRMED", 0) + vc.get("SFH_WEAK", 0)
mfh_count = vc.get("MFH_CONFIRMED", 0) + vc.get("MFH_SUSPECT", 0)
sfh_ratio = sfh_count / total_k02
mfh_ratio = mfh_count / total_k02
check("SFH dominates (>50%) - consistent with Kaarst suburb profile", sfh_ratio > 0.50,
      detail=f"sfh_ratio={sfh_ratio:.1%}")
check("MFH < 20% - consistent with low mfh_ratio in Foundation Layer", mfh_ratio < 0.20,
      detail=f"mfh_ratio={mfh_ratio:.1%}")
check("No UNCERTAIN records exceed 30% of total", vc.get("UNCERTAIN", 0)/total_k02 < 0.30,
      detail=f"uncertain={vc.get('UNCERTAIN',0)/total_k02:.1%}")

# check row_recovery_hint column is present
check("row_recovery_hint column present in F02", "row_recovery_hint" in k_f02.columns)

# Check confidence values are in valid range
conf_ok = k_f02["confidence"].between(0.0, 1.0).all()
check("All confidence values in [0.0, 1.0]", conf_ok)

# Check source field uses stage1/stage2 pattern
valid_sources = k_f02["source"].str.startswith("stage")
check("All source values are stage1/stage2_adjacency_v2", valid_sources.all(),
      detail=f"non-stage sources: {(~valid_sources).sum()}")

# ── B. Field 01 - Roof Score Re-derivation ────────────────────────────────────
print("\n[B] Field 01: Roof Score Arithmetic Verification")
row01 = k_f01.iloc[0]
roof_pool     = row01["roof_pool_area_m2"]
roof_adjusted = row01["roof_pool_adjusted_m2"]
bld_count     = row01["building_count"]
pv_score      = row01["field_value"]

print(f"    segment_id:           {row01['segment_id']}")
print(f"    building_count:       {bld_count}")
print(f"    roof_pool_area_m2:    {roof_pool:.2f}")
print(f"    roof_pool_adjusted:   {roof_adjusted:.2f}")
print(f"    field_value (score):  {pv_score:.4f}")

check("Building count matches kaarst_buildings.parquet size (exact, post-merge-fix)", bld_count == len(k_bld),
      detail=f"f01={bld_count} vs bld={len(k_bld)}")
check("roof_pool_area_m2 > 0", roof_pool > 0)
check("roof_pool_adjusted <= roof_pool_area (can't use more than full roof)", roof_adjusted <= roof_pool)

# Rederive score: field_value = roof_pool_adjusted_m2 / roof_pool_area_m2
expected_score = round(roof_adjusted / roof_pool, 4) if roof_pool > 0 else 0.0
score_match = abs(pv_score - expected_score) < 0.001
check("field_value = roof_adjusted / roof_pool (score formula verified)", score_match,
      detail=f"computed={expected_score:.4f} stored={pv_score:.4f}")
check("Avg footprint per building is plausible (50-500 m²)",
      50 <= (roof_pool / bld_count) <= 500 if bld_count > 0 else False,
      detail=f"avg={roof_pool/bld_count:.1f}m²")
check("source = statistical_proxy_v2_utilization_rate", row01["source"] == "statistical_proxy_v2_utilization_rate")

# ── C. Field 03 - Heating isolation ──────────────────────────────────────────
print("\n[C] Field 03: District Heating Isolation & Integrity")
print(f"    Kaarst F03 records:  {len(k_f03)}")
print(f"    Unique statuses:     {k_f03['field_value'].unique().tolist()}")
print(f"    Unique sources:      {k_f03['source'].unique().tolist()}")

check("All Kaarst heating field_value == NONE", (k_f03["field_value"] == "NONE").all())
check("All Kaarst heating confidence == 0.8 (proxy default)", (k_f03["confidence"] == 0.80).all(),
      detail=f"unique={k_f03['confidence'].unique()}")
check("Source is OSM_PROXY for all Kaarst records", (k_f03["source"] == "OSM_PROXY").all())
check("No Kaarst building_id overlaps with Neuss F03 building_ids",
      len(set(k_f03["building_id"]) & set(df_f03[df_f03["segment_id"] != "KAARST_OSM_41564"]["building_id"])) == 0)

# Check detail parquet
detail_path = os.path.join(FIELDS_DIR, "field_03_district_heating_detail.parquet")
check("field_03_district_heating_detail.parquet exists", os.path.exists(detail_path))
if os.path.exists(detail_path):
    df_detail = pd.read_parquet(detail_path)
    k_detail  = df_detail[df_detail["segment_id"] == "KAARST_OSM_41564"]
    check("Kaarst present in detail parquet", len(k_detail) == 9949,
          detail=f"actual={len(k_detail)}")
    # Neuss detail parquet originally only contained ALLERHEILIGEN_PILOT_SEG_01 (298 rows).
    # The other 4 Neuss segments (DENSE/OLD_TOWN/SUBURBAN/VILLA) were only in the main parquet,
    # not the detail parquet. The detail append logic preserves those 298 rows.
    check("Neuss detail rows untouched (298 original rows in detail parquet)",
          len(df_detail[df_detail["segment_id"] != "KAARST_OSM_41564"]) == 298)

# ── D. Field 04 - PV Score Re-derivation ─────────────────────────────────────
print("\n[D] Field 04: PV Adoption Score Arithmetic Verification")
row04 = k_f04.iloc[0]
e3_score = row04["field_value"]
conf04   = row04["confidence"]
src04    = row04["source"]
print(f"    segment_id:     {row04['segment_id']}")
print(f"    field_value:    {e3_score}")
print(f"    confidence:     {conf04}")
print(f"    source:         {src04}")

# Known parameters used at runtime
SEGMENT_BUILDINGS = 9949
PLZ_BUILDINGS     = 12000
MORPH_FACTOR      = 1.0
PLZ_COUNT_ACTIVE_RES = 2749   # from runtime log
ADOPTION_BENCHMARK = 0.20
E3_PENALTY        = 0.50
E3_CAP            = 0.50

base_ratio  = SEGMENT_BUILDINGS / PLZ_BUILDINGS
final_ratio = min(base_ratio * MORPH_FACTOR, 1.0)
pv_est      = round(PLZ_COUNT_ACTIVE_RES * final_ratio)
intensity   = pv_est / SEGMENT_BUILDINGS
raw_norm    = min(intensity / ADOPTION_BENCHMARK, 1.0)
expected_e3 = round(min(raw_norm * E3_PENALTY, E3_CAP), 4)

print(f"    Re-derived: base_ratio={base_ratio:.4f} -> final={final_ratio:.4f} -> pv_est={pv_est} -> intensity={intensity:.2%} -> score={expected_e3:.4f}")

check("E3 score is correctly computed (tolerance 0.01)", abs(e3_score - expected_e3) <= 0.01,
      detail=f"stored={e3_score} vs re-derived={expected_e3:.4f}")
check("Confidence is E3 level (0.45)", abs(conf04 - 0.45) < 0.001,
      detail=f"actual={conf04}")
check("Source is PLZ_ALLOCATION_E3", src04 == "PLZ_ALLOCATION_E3")
check("E3 cap applied correctly (score <= 0.50)", e3_score <= E3_CAP)

# Check audit JSON was emitted
audit_dir = os.path.join(BASE_DIR, "output", "field_04", "runs")
audit_files = [f for f in os.listdir(audit_dir)] if os.path.exists(audit_dir) else []
check("Field 04 audit JSON emitted to output/field_04/runs/", len(audit_files) > 0,
      detail=f"files found: {len(audit_files)}")

# ── E. Cross-field consistency ────────────────────────────────────────────────
print("\n[E] Cross-Field Consistency")
# All building_ids in F02 and F03 should match kaarst_buildings
bld_ids_bld = set(k_bld["building_id"])
bld_ids_f02 = set(k_f02["building_id"])
bld_ids_f03 = set(k_f03["building_id"])

check("F02 building_ids == kaarst_buildings building_ids (exact match)",
      bld_ids_f02 == bld_ids_bld,
      detail=f"only_in_f02={len(bld_ids_f02-bld_ids_bld)} only_in_bld={len(bld_ids_bld-bld_ids_f02)}")
check("F03 building_ids == kaarst_buildings building_ids (exact match)",
      bld_ids_f03 == bld_ids_bld,
      detail=f"only_in_f03={len(bld_ids_f03-bld_ids_bld)} only_in_bld={len(bld_ids_bld-bld_ids_f03)}")

# F01 uses segment_id, not building_id
check("F01 segment_id matches KAARST_OSM_41564", k_f01.iloc[0]["segment_id"] == "KAARST_OSM_41564")
check("F04 segment_id matches KAARST_OSM_41564", k_f04.iloc[0]["segment_id"] == "KAARST_OSM_41564")

# ── F. Data isolation verification ───────────────────────────────────────────
print("\n[F] Neuss Data Isolation - Final Counts")
neuss_f01 = df_f01[df_f01["segment_id"] != "KAARST_OSM_41564"]
neuss_f02 = df_f02[df_f02["segment_id"] != "KAARST_OSM_41564"]
neuss_f03 = df_f03[df_f03["segment_id"] != "KAARST_OSM_41564"]
neuss_f04 = df_f04[df_f04["segment_id"] != "KAARST_OSM_41564"]

expected = {"F01": 12, "F02": 26187, "F03": 848, "F04": 8}
actual   = {"F01": len(neuss_f01), "F02": len(neuss_f02), "F03": len(neuss_f03), "F04": len(neuss_f04)}

print(f"    {'Field':<6} {'Expected':>10} {'Actual':>10}  Status")
print(f"    {'-'*40}")
for k, exp in expected.items():
    act = actual[k]
    ok  = act == exp
    print(f"    {k:<6} {exp:>10} {act:>10}  {'OK' if ok else 'FAIL'}")
    check(f"Neuss {k} row count unchanged ({exp})", ok, detail=f"actual={act}")

# No KAARST ids in Neuss Segment rows
kaarst_leak = df_f04[df_f04["segment_id"].str.startswith("KAARST") & (df_f04["segment_id"] != "KAARST_OSM_41564")]
check("No rogue KAARST segment_ids in F04", len(kaarst_leak) == 0)

# ── G. kaarst_buildings.parquet integrity ────────────────────────────────────
print("\n[G] kaarst_buildings.parquet Provenance")
check("9,949 buildings in kaarst_buildings.parquet", len(k_bld) == 9949, detail=f"actual={len(k_bld)}")
check("geometry column exists (WKT)", "geometry" in k_bld.columns)
check("All geometry values non-null", k_bld["geometry"].notna().all())
check("building_type column exists", "building_type" in k_bld.columns)
check("All segment_ids are KAARST_OSM_41564", (k_bld["segment_id"] == "KAARST_OSM_41564").all())

# building_id uniqueness
check("All building_ids are unique", k_bld["building_id"].nunique() == len(k_bld),
      detail=f"unique={k_bld['building_id'].nunique()} total={len(k_bld)}")

# Check building_id format
bad_ids = k_bld[~k_bld["building_id"].str.startswith("OSM_")]
check("All building_ids follow OSM_ prefix convention", len(bad_ids) == 0,
      detail=f"violations={len(bad_ids)}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
total  = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
warns  = sum(1 for _, s, _ in results if s == WARN)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"  RESULT: {passed}/{total} PASS  |  {warns} WARN  |  {failed} FAIL")
print("=" * 70)

if failed > 0:
    sys.exit(1)
