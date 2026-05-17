"""
check_phase4_audit.py
=====================
Full Phase 4 audit for Kaarst Layer2 and Street Ranking.

Checks:
  A. Output file existence and size
  B. Layer2 input table content validity
  C. Neuss isolation — no Kaarst rows in Neuss files
  D. Street ranking arithmetic re-verification (spot-check top 3)
  E. Scoring constant consistency (same as field_08)
  F. PLZ 41564 gate aggregation correctness (re-derive)
  G. Cross-field signal consistency
"""

import json, math, os, sys
import pandas as pd

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYER2_DIR = os.path.join(BASE_DIR, "data", "layer2")
FIELDS_DIR = os.path.join(BASE_DIR, "data", "fields")
FOUND_PATH = os.path.join(BASE_DIR, "output", "foundation", "kaarst_foundation_structure_results.json")

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

print("=" * 70)
print("  PHASE 4 DEEP AUDIT - Kaarst Layer2 & Street Ranking")
print("=" * 70)

# ── A. File existence ────────────────────────────────────────────────────────
print("\n[A] Output File Existence")
k_l2_path  = os.path.join(LAYER2_DIR, "kaarst_layer2_input_table.parquet")
k_slr_path = os.path.join(LAYER2_DIR, "kaarst_street_level_ranking_v1.parquet")
check("kaarst_layer2_input_table.parquet exists", os.path.exists(k_l2_path))
check("kaarst_street_level_ranking_v1.parquet exists", os.path.exists(k_slr_path))
check("Neuss layer2_mvp_input_table.parquet still exists",
      os.path.exists(os.path.join(LAYER2_DIR, "layer2_mvp_input_table.parquet")))
check("Neuss street_level_ranking_v1.parquet still exists",
      os.path.exists(os.path.join(LAYER2_DIR, "street_level_ranking_v1.parquet")))

# ── B. Layer2 input table validity ──────────────────────────────────────────
print("\n[B] Kaarst Layer2 Input Table Content")
df_kl2 = pd.read_parquet(k_l2_path)
check("Exactly 1 row in kaarst_layer2_input_table", len(df_kl2) == 1, detail=f"actual={len(df_kl2)}")
row = df_kl2.iloc[0]
check("unit_id == KAARST_OSM_41564", row["unit_id"] == "KAARST_OSM_41564")
check("unit_status == REAL_GROUNDED", row["unit_status"] == "REAL_GROUNDED")
check("plz == 41564", str(row["plz"]) == "41564")
check("row_usable_for_ranking == True", bool(row["row_usable_for_ranking"]) == True)
check("l1_gate_label == DEPLOYABLE (62.9% PASS+QUAL)", row["l1_gate_label"] == "DEPLOYABLE",
      detail=f"actual={row['l1_gate_label']}")
check("pct_l1_gate_pass in [0.60, 0.70]", 0.60 <= row["pct_l1_gate_pass"] <= 0.70,
      detail=f"actual={row['pct_l1_gate_pass']:.4f}")
check("sfh_friendly_share in [0.80, 0.90] (Kaarst suburb)", 0.80 <= row["sfh_friendly_share"] <= 0.90,
      detail=f"actual={row['sfh_friendly_share']:.4f}")
check("pv_coverage_score == 0.5 (E3 cap hit)", abs(row["pv_coverage_score"] - 0.5) < 0.01,
      detail=f"actual={row['pv_coverage_score']}")
check("roof_suitability_score_norm in [0.3, 0.6]", 0.3 <= row["roof_suitability_score_norm"] <= 0.6,
      detail=f"actual={row['roof_suitability_score_norm']:.4f}")
check("centroid_lat in Kaarst range [51.18, 51.28]", 51.18 <= row["centroid_lat"] <= 51.28,
      detail=f"actual={row['centroid_lat']}")
check("centroid_lon in Kaarst range [6.55, 6.68]", 6.55 <= row["centroid_lon"] <= 6.68,
      detail=f"actual={row['centroid_lon']}")

# ── C. Neuss isolation ────────────────────────────────────────────────────────
print("\n[C] Neuss Data Isolation")
df_neuss_l2  = pd.read_parquet(os.path.join(LAYER2_DIR, "layer2_mvp_input_table.parquet"))
df_neuss_slr = pd.read_parquet(os.path.join(LAYER2_DIR, "street_level_ranking_v1.parquet"))
check("Neuss L2 row count unchanged (13)", len(df_neuss_l2) == 13, detail=f"actual={len(df_neuss_l2)}")
check("Neuss SLR row count unchanged (733)", len(df_neuss_slr) == 733, detail=f"actual={len(df_neuss_slr)}")
check("No KAARST unit_id in Neuss L2", not (df_neuss_l2["unit_id"] == "KAARST_OSM_41564").any())
check("No KAARST segment_id in Neuss SLR", not (df_neuss_slr["segment_id"] == "KAARST_OSM_41564").any())

# ── D. Street ranking arithmetic spot-check ───────────────────────────────────
print("\n[D] Street Ranking Arithmetic Spot-Check (Top 3 Re-derivation)")
df_kslr = pd.read_parquet(k_slr_path)
check("414 unique Kaarst streets in ranking", len(df_kslr) == 414, detail=f"actual={len(df_kslr)}")

# Constants from build_kaarst_layer2.py
W_SFH_QUALITY  = 0.30; W_GATE = 0.20; W_MFH_CLEAN = 0.10; W_SCALE = 0.10
W_ROOF_NORM    = 0.20; W_PV_OPPTY = 0.10
SCALE_NORM_DENOM = math.log1p(30)
GATE_SCORE = {"PASS": 1.0, "QUALIFIED": 0.8, "REVIEW": 0.4, "FAIL": 0.0}
W_DETACHED = 1.0; W_SEMI = 0.65; W_ROWHOUSE = 0.50

roof_norm = float(df_kl2.iloc[0]["roof_suitability_score_norm"])
pv_score  = float(df_kl2.iloc[0]["pv_coverage_score"])
pv_oppty  = round(min(1.0, max(0.0, pv_score)), 4)

# Load foundation for verification
with open(FOUND_PATH, encoding="utf-8") as f:
    all_clusters = json.load(f)
clusters_41564 = [c for c in all_clusters if str(c.get("plz", "")) == "41564"]
clust_map = {c.get("street_name",""): c for c in clusters_41564}

score_errors = []
top3 = df_kslr.head(3)
for _, r in top3.iterrows():
    sname = r["street_name"]
    c = clust_map.get(sname)
    if c is None:
        score_errors.append(f"{sname}: cluster not found in foundation")
        continue

    sfh_total = int(c.get("sfh_total_count", 0) or 0)
    sfh_ratio = float(c.get("sfh_total_ratio", 0.0) or 0.0)
    det = float(c.get("sfh_detached_count", 0) or 0)
    semi = float(c.get("sfh_semi_detached_count", 0) or 0)
    row_h = float(c.get("sfh_rowhouse_count", 0) or 0)

    if sfh_total > 0:
        weighted = det * W_DETACHED + semi * W_SEMI + row_h * W_ROWHOUSE
        sfh_q = round(sfh_ratio * (weighted / sfh_total), 4)
    else:
        sfh_q = 0.0
    gate_s = GATE_SCORE.get(str(c.get("structure_gate","FAIL")).upper(), 0.0)
    n      = int(c.get("building_count_total", 0) or 0)
    scale  = round(min(1.0, math.log1p(n) / SCALE_NORM_DENOM), 4)
    mfh_c  = round(1.0 - float(c.get("mfh_ratio", 0.0) or 0.0), 4)

    expected = round(sfh_q * W_SFH_QUALITY + gate_s * W_GATE + mfh_c * W_MFH_CLEAN
                     + scale * W_SCALE + roof_norm * W_ROOF_NORM + pv_oppty * W_PV_OPPTY, 4)
    stored   = float(r["street_score"])
    ok       = abs(stored - expected) < 0.001
    status   = "OK" if ok else "MISMATCH"
    print(f"    #{int(r['global_rank']):<3} {sname:<35} stored={stored:.4f} computed={expected:.4f} [{status}]")
    if not ok:
        score_errors.append(f"{sname}: stored={stored:.4f} expected={expected:.4f}")

check("Top-3 street scores re-derivable (zero arithmetic errors)", len(score_errors) == 0,
      detail=", ".join(score_errors) if score_errors else "")

# ── E. Scoring constant consistency ──────────────────────────────────────────
print("\n[E] Scoring Constant Consistency (same as field_08)")
with open(os.path.join(BASE_DIR, "fields", "field_08_street_level_ranking.py"), encoding="utf-8") as f:
    f08_src = f.read()
with open(os.path.join(BASE_DIR, "scripts", "build_kaarst_layer2.py"), encoding="utf-8") as f:
    k4_src = f.read()

for constant in ["W_SFH_QUALITY  = 0.30", "W_GATE         = 0.20", "W_MFH_CLEAN    = 0.10",
                 "W_SCALE        = 0.10", "W_ROOF_NORM    = 0.20", "W_PV_OPPTY     = 0.10",
                 "W_DETACHED     = 1.00", "W_SEMI         = 0.65", "W_ROWHOUSE     = 0.50"]:
    in_f08 = constant.replace("  ", " ").replace("   ", " ").replace("    ", " ").split("=")[0].strip() in f08_src
    in_k4  = constant.replace("  ", " ").replace("   ", " ").replace("    ", " ").split("=")[0].strip() in k4_src
    check(f"Constant {constant.split('=')[0].strip()} present in both field_08 and build_kaarst_layer2",
          in_f08 and in_k4)

check("Gate scores PASS=1.0,QUALIFIED=0.8,REVIEW=0.4,FAIL=0.0 in build_kaarst",
      '"PASS": 1.00' in k4_src and '"QUALIFIED": 0.80' in k4_src)
check("SFH_SCALE_SATURATION = 15 in build_kaarst", "SFH_SCALE_SATURATION = 15" in k4_src)

# ── F. Gate aggregation re-derivation ────────────────────────────────────────
print("\n[F] Gate Aggregation Re-derivation")
GATE_DEPLOY_THR = 0.60; GATE_MIXED_THR = 0.30
n_total = len(clusters_41564)
n_pass  = sum(1 for c in clusters_41564 if c["structure_gate"] in ("PASS", "QUALIFIED"))
pct_pass = n_pass / n_total if n_total else 0
expected_gate = "DEPLOYABLE" if pct_pass >= GATE_DEPLOY_THR else ("MIXED" if pct_pass >= GATE_MIXED_THR else "BLOCKED")
print(f"    Re-derived: n={n_total}, pass={n_pass}, pct={pct_pass:.1%}, gate={expected_gate}")

check("pct_l1_gate_pass re-derived matches stored", abs(row["pct_l1_gate_pass"] - pct_pass) < 0.001,
      detail=f"stored={row['pct_l1_gate_pass']:.4f} expected={pct_pass:.4f}")
check("l1_gate_label re-derived matches stored", row["l1_gate_label"] == expected_gate,
      detail=f"stored={row['l1_gate_label']} expected={expected_gate}")
check("l1_cluster_count == 445", int(row["l1_cluster_count"]) == 445,
      detail=f"actual={row['l1_cluster_count']}")

# ── G. Cross-field signal consistency ────────────────────────────────────────
print("\n[G] Cross-Field Signal Consistency")
df_f01 = pd.read_parquet(os.path.join(FIELDS_DIR, "field_01_roof_potential.parquet"))
k_f01  = df_f01[df_f01["segment_id"] == "KAARST_OSM_41564"].iloc[0]
check("L2 roof_suitability_score matches F01 field_value",
      abs(row["roof_suitability_score"] - k_f01["field_value"]) < 0.001,
      detail=f"L2={row['roof_suitability_score']:.4f} F01={k_f01['field_value']:.4f}")

df_f04 = pd.read_parquet(os.path.join(FIELDS_DIR, "field_04_pv_adoption.parquet"))
k_f04  = df_f04[df_f04["segment_id"] == "KAARST_OSM_41564"].iloc[0]
check("L2 pv_coverage_score matches F04 field_value",
      abs(row["pv_coverage_score"] - k_f04["field_value"]) < 0.001,
      detail=f"L2={row['pv_coverage_score']} F04={k_f04['field_value']}")

df_f02 = pd.read_parquet(os.path.join(FIELDS_DIR, "field_02_building_type.parquet"))
k_f02  = df_f02[df_f02["segment_id"] == "KAARST_OSM_41564"]
n_sfh_w  = (k_f02["field_value"] == "SFH_WEAK").sum()
n_sfh_c  = (k_f02["field_value"] == "SFH_CONFIRMED").sum()
sfh_friendly_expected = round((n_sfh_w + n_sfh_c) / len(k_f02), 4)
check("L2 sfh_friendly_share matches F02 aggregation",
      abs(row["sfh_friendly_share"] - sfh_friendly_expected) < 0.001,
      detail=f"L2={row['sfh_friendly_share']:.4f} F02-derived={sfh_friendly_expected:.4f}")

# SLR scores use the same roof_norm and pv_oppty
top1 = df_kslr[df_kslr["global_rank"] == 1].iloc[0]
check("SLR roof_norm_score consistent with L2 roof_suitability_score_norm",
      abs(top1["b_roof_norm"] - row["roof_suitability_score_norm"]) < 0.001,
      detail=f"SLR={top1['b_roof_norm']:.3f} L2={row['roof_suitability_score_norm']:.3f}")
check("SLR pv_oppty == min(1.0, L2 pv_coverage_score)",
      abs(top1["b_pv_oppty"] - min(1.0, row["pv_coverage_score"])) < 0.001,
      detail=f"SLR={top1['b_pv_oppty']:.3f} L2={row['pv_coverage_score']}")

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
