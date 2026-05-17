"""
check_phase2_audit.py
=====================
Phase 2 audit script for Kaarst expansion.
Verifies the generated foundation layer output.
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOUNDATION_PATH   = os.path.join(BASE_DIR, "output", "foundation", "kaarst_foundation_structure_results.json")

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

print("=" * 60)
print("  PHASE 2 AUDIT - Kaarst Foundation Layer")
print("=" * 60)

print("\n[A] Output File")
check("File exists", os.path.exists(FOUNDATION_PATH))
if os.path.exists(FOUNDATION_PATH):
    with open(FOUNDATION_PATH, encoding="utf-8") as f:
        data = json.load(f)

    check("Generated count matches Phase 1 (494)", len(data) == 494, detail=f"actual={len(data)}")

    # Check structural data presence
    missing_buildings = [c for c in data if c["building_count_total"] == 0]
    check("No clusters with 0 building_count_total", len(missing_buildings) == 0, detail=f"found {len(missing_buildings)}")

    bad_ids = [c["cluster_id"] for c in data if not c["cluster_id"].startswith("K_")]
    check("All cluster_ids use K_ prefix", len(bad_ids) == 0)

    # Check that structural gates are applied
    gates = set(c["structure_gate"] for c in data)
    valid_gates = {"PASS", "QUALIFIED", "REVIEW", "FAIL"}
    check("All structure_gates are valid", gates.issubset(valid_gates), detail=f"found: {gates}")

    pass_ratio = sum(1 for c in data if c["structure_gate"] == "PASS") / len(data)
    check("PASS ratio is plausible (>30%)", pass_ratio > 0.30, detail=f"ratio={pass_ratio:.1%}")

print("\n" + "=" * 60)
total  = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
warns  = sum(1 for _, s, _ in results if s == WARN)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"  RESULT: {passed}/{total} PASS  |  {warns} WARN  |  {failed} FAIL")
print("=" * 60)

if failed > 0:
    sys.exit(1)
