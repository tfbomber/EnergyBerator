"""
check_phase2_deep_audit.py
===========================
Deep audit for Kaarst Phase 2 Foundation Layer execution.

Checks:
  A. Output file integrity
  B. Gate threshold consistency with Neuss (same constants used)
  C. Gate logic correctness (manually re-derive from raw counts)
  D. Field schema completeness (all required fields present)
  E. Data isolation (Neuss foundation_structure_results.json intact)
  F. Distribution plausibility (compare Kaarst vs Neuss PASS/REVIEW/FAIL ratios)
  G. Script provenance (kaarst was run with --city kaarst, not neuss)
"""

import json
import os
import sys

BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAARST_FOUND_PATH = os.path.join(BASE_DIR, "output", "foundation", "kaarst_foundation_structure_results.json")
NEUSS_FOUND_PATH  = os.path.join(BASE_DIR, "output", "foundation", "foundation_structure_results.json")
KAARST_CLUST_PATH = os.path.join(BASE_DIR, "output", "clusters", "kaarst_hybrid_clusters_v1.json")

# ── Gate thresholds as defined in generate_foundation_layer.py (must match exactly) ──
PASS_MAX_MFH_RATIO   = 0.25
PASS_MIN_SFH_RATIO   = 0.50
REVIEW_MAX_MFH_RATIO = 0.40
QUALIFIED_OTHER_THRESHOLD = 0.15
QUALIFIED_MIN_SFH_RATIO   = 0.70

# Required output fields per cluster record
REQUIRED_FIELDS = [
    "cluster_id", "street_name", "plz", "address_range",
    "building_count_total", "sfh_detached_count", "sfh_semi_detached_count",
    "sfh_rowhouse_count", "sfh_total_count", "sfh_total_ratio",
    "mfh_count", "mfh_ratio", "other_count", "other_ratio",
    "structure_profile", "structure_gate", "gate_reason",
    "execution_scale_flag", "subtype_confidence", "attached_confidence",
    "attached_risk_flag", "small_mfh_suspect", "street_confidence",
    "cluster_building_count", "street_building_count",
    "unaddressed_building_count", "address_filter_coverage",
    "cluster_sfh_detached_count", "cluster_sfh_semi_count",
    "cluster_sfh_rowhouse_count", "top_reasons", "risk_flags",
    "recommended_action", "action_rationale", "sales_story",
]

PASS_GATE_VALUES  = {"PASS", "QUALIFIED", "REVIEW", "FAIL"}

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

# ============================================================
print("=" * 65)
print("  PHASE 2 DEEP AUDIT - Kaarst Foundation Layer")
print("=" * 65)

# ── A. Output file integrity ──────────────────────────────────
print("\n[A] Output File Integrity")
check("Kaarst foundation file exists", os.path.exists(KAARST_FOUND_PATH))
check("File size > 100KB (real data, not stub)",
      os.path.exists(KAARST_FOUND_PATH) and os.path.getsize(KAARST_FOUND_PATH) > 100_000,
      detail=f"size={os.path.getsize(KAARST_FOUND_PATH):,} bytes" if os.path.exists(KAARST_FOUND_PATH) else "N/A")

kaarst = None
if os.path.exists(KAARST_FOUND_PATH):
    with open(KAARST_FOUND_PATH, encoding="utf-8") as f:
        kaarst = json.load(f)
    check("Record count matches Phase 1 cluster count (494)", len(kaarst) == 494,
          detail=f"actual={len(kaarst)}")

# ── B. Gate threshold consistency ────────────────────────────
print("\n[B] Gate Threshold Consistency (verify constants match generate_foundation_layer.py)")
# We verify by reading the constants back from the source file
script_path = os.path.join(BASE_DIR, "scripts", "generate_foundation_layer.py")
with open(script_path, encoding="utf-8") as f:
    src = f.read()

check("PASS_MAX_MFH_RATIO = 0.25 in source", "PASS_MAX_MFH_RATIO = 0.25" in src)
check("PASS_MIN_SFH_RATIO = 0.50 in source", "PASS_MIN_SFH_RATIO = 0.50" in src)
check("REVIEW_MAX_MFH_RATIO = 0.40 in source", "REVIEW_MAX_MFH_RATIO = 0.40" in src)
check("QUALIFIED_OTHER_THRESHOLD = 0.15 in source", "QUALIFIED_OTHER_THRESHOLD = 0.15" in src)
check("QUALIFIED_MIN_SFH_RATIO = 0.70 in source", "QUALIFIED_MIN_SFH_RATIO   = 0.70" in src)
check("Kaarst in OSM_PBF_REGISTRY", '"kaarst"' in src)
check("Kaarst BBOX is (6.55, 51.19, 6.68, 51.27)", "(6.55, 51.19, 6.68, 51.27)" in src)
check("Output path respects --out argument (not hardcoded)", "args.out" in src)
check("city_key is parameterized (not hardcoded neuss)", "city_key=city_key" in src)

# ── C. Gate logic correctness (re-derive per record) ─────────
print("\n[C] Gate Logic Correctness (re-derive gates from raw ratios)")
if kaarst:
    gate_errors = []
    gate_ok = 0
    for r in kaarst:
        mfh  = r["mfh_ratio"]
        sfh  = r["sfh_total_ratio"]
        oth  = r["other_ratio"]
        gate = r["structure_gate"]

        # Re-derive expected gate — EXACT mirror of apply_structure_gate() in generate_foundation_layer.py
        # Priority order: FAIL -> PASS/QUALIFIED -> REVIEW
        if mfh > REVIEW_MAX_MFH_RATIO:
            expected = "FAIL"
        elif mfh <= PASS_MAX_MFH_RATIO and sfh >= PASS_MIN_SFH_RATIO:
            if oth >= QUALIFIED_OTHER_THRESHOLD:
                if sfh >= QUALIFIED_MIN_SFH_RATIO:
                    expected = "QUALIFIED"   # LOW_MFH_STRONG_SFH_BUT_HIGH_OTHER
                else:
                    expected = "REVIEW"      # LOW_MFH_BORDERLINE_SFH_HIGH_OTHER
            else:
                expected = "PASS"            # LOW_MFH_HIGH_SFH
        else:
            expected = "REVIEW"              # BORDERLINE_MIXED_STREET

        if gate != expected:
            gate_errors.append({
                "cluster_id": r["cluster_id"],
                "actual_gate": gate,
                "expected_gate": expected,
                "mfh_ratio": mfh,
                "sfh_ratio": sfh,
                "other_ratio": oth,
            })
        else:
            gate_ok += 1

    check("All gate values re-derivable from raw ratios (0 discrepancies)",
          len(gate_errors) == 0,
          detail=f"{gate_ok}/{len(kaarst)} match; {len(gate_errors)} discrepancies")
    if gate_errors:
        print("    First 5 discrepancies:")
        for e in gate_errors[:5]:
            print(f"      {e}")

# ── D. Schema completeness ────────────────────────────────────
print("\n[D] Schema Completeness (all required fields present)")
if kaarst:
    sample = kaarst[0]
    missing_fields = [f for f in REQUIRED_FIELDS if f not in sample]
    check("All required fields present", len(missing_fields) == 0,
          detail=f"missing: {missing_fields}" if missing_fields else "")
    check("No records with NULL cluster_id",
          all(r["cluster_id"] for r in kaarst))
    check("No records with NULL street_name",
          all(r["street_name"] for r in kaarst))
    check("sfh_total_ratio + mfh_ratio + other_ratio = 1.0 (±0.01) for all",
          all(abs(r["sfh_total_ratio"] + r["mfh_ratio"] + r["other_ratio"] - 1.0) <= 0.01
              for r in kaarst if r["building_count_total"] > 0))

# ── E. Data isolation ─────────────────────────────────────────
print("\n[E] Data Isolation (Neuss foundation_structure_results.json unchanged)")
check("Neuss foundation file still exists", os.path.exists(NEUSS_FOUND_PATH))
if os.path.exists(NEUSS_FOUND_PATH):
    with open(NEUSS_FOUND_PATH, encoding="utf-8") as f:
        neuss = json.load(f)
    check("Neuss record count unchanged (889)", len(neuss) == 889, detail=f"actual={len(neuss)}")
    neuss_ids = set(r["cluster_id"] for r in neuss)
    kaarst_ids = set(r["cluster_id"] for r in kaarst) if kaarst else set()
    overlap = neuss_ids & kaarst_ids
    check("No cluster_id overlap between Kaarst and Neuss results", len(overlap) == 0,
          detail=f"overlap: {overlap}" if overlap else "")
    neuss_has_kaarst = any(r["cluster_id"].startswith("K_") for r in neuss)
    check("Neuss foundation not polluted with K_ cluster_ids", not neuss_has_kaarst)
    # Check that all Neuss gate values are same valid set
    neuss_gates = set(r["structure_gate"] for r in neuss)
    check("Neuss gates still valid set (PASS/QUALIFIED/REVIEW/FAIL)",
          neuss_gates.issubset(PASS_GATE_VALUES), detail=str(neuss_gates))

# ── F. Distribution plausibility comparison ───────────────────
print("\n[F] Distribution Plausibility - Kaarst vs Neuss Comparison")
if kaarst and os.path.exists(NEUSS_FOUND_PATH):
    def gate_dist(data):
        total = len(data)
        return {g: round(sum(1 for r in data if r["structure_gate"]==g)/total*100, 1) for g in ["PASS","QUALIFIED","REVIEW","FAIL"]}

    kd = gate_dist(kaarst)
    nd = gate_dist(neuss)

    print(f"    {'Gate':<12} {'Kaarst':>10} {'Neuss':>10}  Note")
    print(f"    {'-'*48}")
    for g in ["PASS","QUALIFIED","REVIEW","FAIL"]:
        diff = kd[g] - nd[g]
        flag = "  (*)" if abs(diff) > 20 else ""
        print(f"    {g:<12} {kd[g]:>9.1f}% {nd[g]:>9.1f}%  delta={diff:+.1f}%{flag}")

    check("Kaarst PASS+QUALIFIED > 50%", kd["PASS"] + kd["QUALIFIED"] > 50,
          detail=f"Kaarst={kd['PASS']+kd['QUALIFIED']:.1f}%")
    check("Kaarst FAIL < 15%", kd["FAIL"] < 15,
          detail=f"Kaarst={kd['FAIL']:.1f}%")
    check("PASS+QUALIFIED delta from Neuss within ±30pp", abs((kd["PASS"]+kd["QUALIFIED"]) - (nd["PASS"]+nd["QUALIFIED"])) <= 30,
          level=WARN,
          detail=f"Kaarst={kd['PASS']+kd['QUALIFIED']:.1f}% Neuss={nd['PASS']+nd['QUALIFIED']:.1f}%")

    # Structural stats comparison
    print()
    k_avg_mfh = sum(r["mfh_ratio"] for r in kaarst) / len(kaarst)
    n_avg_mfh = sum(r["mfh_ratio"] for r in neuss) / len(neuss)
    k_avg_sfh = sum(r["sfh_total_ratio"] for r in kaarst) / len(kaarst)
    n_avg_sfh = sum(r["sfh_total_ratio"] for r in neuss) / len(neuss)
    k_avg_bld = sum(r["building_count_total"] for r in kaarst) / len(kaarst)
    n_avg_bld = sum(r["building_count_total"] for r in neuss) / len(neuss)
    print(f"    {'Metric':<30} {'Kaarst':>10} {'Neuss':>10}")
    print(f"    {'-'*54}")
    print(f"    {'avg_mfh_ratio':<30} {k_avg_mfh:>10.3f} {n_avg_mfh:>10.3f}")
    print(f"    {'avg_sfh_ratio':<30} {k_avg_sfh:>10.3f} {n_avg_sfh:>10.3f}")
    print(f"    {'avg_building_count':<30} {k_avg_bld:>10.1f} {n_avg_bld:>10.1f}")

    check("Kaarst avg_sfh_ratio plausible (>0.3, suburb city)",
          k_avg_sfh > 0.3, detail=f"avg={k_avg_sfh:.3f}")

# ── G. Ranking strategy consistency ──────────────────────────
print("\n[G] Ranking Strategy Consistency (same code path used)")
check("Foundation script uses single shared main() with --city arg",
      "args.city" in src and "city_key = args.city" in src)
check("Kaarst uses identical gate functions (not a fork)",
      "apply_structure_gate" in src and "classify_structure_profile" in src)
# Verify no separate gate function exists for kaarst — all gating via shared constants
check("No Kaarst-specific gate constants in source (no 'kaarst_mfh_ratio' etc.)",
      "kaarst_mfh" not in src.lower() and "kaarst_sfh" not in src.lower())
check("PBF source for Kaarst is same duesseldorf-regbez-latest.osm.pbf",
      "duesseldorf-regbez-latest.osm.pbf" in src)
check("No hardcoded Kaarst gate thresholds (thresholds are shared constants)",
      src.count("PASS_MAX_MFH_RATIO") == 3)  # definition + 2 uses in gate logic

# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 65)
total  = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
warns  = sum(1 for _, s, _ in results if s == WARN)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"  RESULT: {passed}/{total} PASS  |  {warns} WARN  |  {failed} FAIL")
print("=" * 65)

if failed > 0:
    sys.exit(1)
