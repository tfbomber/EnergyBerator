"""
audit_sfh_denominator_fix.py
============================
Post-fix audit script for the SFH denominator fix (2026-05-04).
Run from d-ess-engine root. Exits with code 1 if any assertion fails.
"""
import sys
import os
from pathlib import Path

BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
from core.building_universe import count_buildings_per_segment

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

errors = []
warnings = []

print("=" * 65)
print("  SFH DENOMINATOR FIX — FULL AUDIT REPORT")
print(f"  Run from: {BASE_DIR}")
print("=" * 65)
print()

# ── 1. building_universe module ──────────────────────────────────────────────
print("--- AUDIT 1: core.building_universe output ---")
counts = count_buildings_per_segment()
expected_segs = [
    "NEUSS_PLZ41460", "NEUSS_PLZ41462", "NEUSS_PLZ41464",
    "NEUSS_PLZ41466", "NEUSS_PLZ41468", "NEUSS_PLZ41469",
    "NEUSS_PLZ41470", "NEUSS_PLZ41472",
]
for seg in expected_segs:
    n = counts.get(seg, 0)
    ok = n > 0
    flag = PASS if ok else FAIL
    print(f"  {flag} | {seg}: {n:,} total buildings")
    if not ok:
        errors.append(f"Missing building count for {seg}")

# Specific known values (reference from OSM/foundation)
assert_min = {
    "NEUSS_PLZ41460": 800,   # 844 from buildings.parquet, foundation may differ
    "NEUSS_PLZ41470": 1000,  # Allerheiligen: ~1498 in parquet
    "NEUSS_PLZ41472": 3000,  # Large suburb
}
for seg, minv in assert_min.items():
    n = counts.get(seg, 0)
    flag = PASS if n >= minv else FAIL
    print(f"  {flag} | {seg} >= {minv:,}: actual={n:,}")
    if n < minv:
        errors.append(f"{seg} count {n} < expected minimum {minv}")

print()

# ── 2. layer2_mvp_input_table.parquet ────────────────────────────────────────
print("--- AUDIT 2: layer2_mvp_input_table.parquet ---")
parq = BASE_DIR / "data" / "layer2" / "layer2_mvp_input_table.parquet"
if not parq.exists():
    errors.append("layer2_mvp_input_table.parquet NOT FOUND")
    print(f"  {FAIL} | {parq} does not exist!")
else:
    df = pd.read_parquet(parq)
    usable = df[df["row_usable_for_ranking"] == True]
    print(f"  {PASS} | Parquet found: {len(df)} rows, {len(usable)} usable")

    # Required columns
    required_cols = [
        "unit_id", "unit_status", "row_usable_for_ranking",
        "effective_sfh_share", "sfh_friendly_share", "sfh_confirmed_share",
        "f02_building_count", "f02_classified_count",
    ]
    print()
    print("  Required columns:")
    for c in required_cols:
        flag = PASS if c in df.columns else FAIL
        print(f"    {flag} | {c}")
        if c not in df.columns:
            errors.append(f"Missing column: {c}")

    print()
    print("  SFH share values per usable segment:")
    for _, row in usable.iterrows():
        uid = row["unit_id"]
        eff = row.get("effective_sfh_share")
        total = row.get("f02_building_count")
        classified = row.get("f02_classified_count")
        ratio_str = f"classified={classified:,}/{total:,} ({classified/total:.0%})" if total and classified else "N/A"
        print(f"    {uid:22s} | effective_sfh={eff:.2%} | {ratio_str}")

    print()

    # KEY ASSERTION: 41460 must NOT be inflated
    row_41460 = usable[usable["unit_id"] == "NEUSS_PLZ41460"]
    if row_41460.empty:
        errors.append("NEUSS_PLZ41460 not found in usable rows")
        print(f"  {FAIL} | NEUSS_PLZ41460 not in usable rows!")
    else:
        v = float(row_41460["effective_sfh_share"].iloc[0])
        if v < 0.30:
            print(f"  {PASS} | PLZ41460 (Innenstadt) effective_sfh_share = {v:.2%} — correctly LOW (< 30%)")
        else:
            print(f"  {FAIL} | PLZ41460 effective_sfh_share = {v:.2%} — STILL INFLATED (expected < 30%)!")
            errors.append(f"PLZ41460 sfh_share={v:.4f} still inflated")

    # SANITY: 41472 (suburban) must remain high
    row_41472 = usable[usable["unit_id"] == "NEUSS_PLZ41472"]
    if not row_41472.empty:
        v = float(row_41472["effective_sfh_share"].iloc[0])
        if v > 0.50:
            print(f"  {PASS} | PLZ41472 (Holzheim) effective_sfh_share = {v:.2%} — correctly HIGH (> 50%)")
        else:
            print(f"  {FAIL} | PLZ41472 effective_sfh_share = {v:.2%} — unexpectedly LOW!")
            errors.append(f"PLZ41472 sfh_share={v:.4f} dropped too low")

    # CONSISTENCY: universe total must always >= classified count
    print()
    print("  Universe >= classified integrity check:")
    for _, row in usable.iterrows():
        uid = row["unit_id"]
        total = row.get("f02_building_count")
        classified = row.get("f02_classified_count")
        if total is not None and classified is not None:
            if total >= classified:
                print(f"    {PASS} | {uid}: universe={total:,} >= classified={classified:,}")
            else:
                print(f"    {FAIL} | {uid}: universe={total:,} < classified={classified:,}!")
                errors.append(f"{uid}: universe {total} < classified {classified}")

print()

# ── 3. street_ranking_v1.parquet ─────────────────────────────────────────────
print("--- AUDIT 3: street_ranking_v1.parquet (field 07 output) ---")
sr_parq = BASE_DIR / "data" / "layer2" / "street_ranking_v1.parquet"
if not sr_parq.exists():
    errors.append("street_ranking_v1.parquet NOT FOUND")
    print(f"  {FAIL} | {sr_parq} does not exist!")
else:
    sr = pd.read_parquet(sr_parq)
    print(f"  {PASS} | Found {len(sr)} ranked segments")
    print()
    print("  Segment rankings:")
    for _, row in sr.sort_values("rank").iterrows():
        sid = row.get("street_id", row.get("unit_id", "?"))
        rank = int(row["rank"])
        score = float(row["final_score"])
        tier = row.get("canvass_tier", "?")
        print(f"    #{rank:2d} | {sid:22s} | final_score={score:.4f} | tier={tier}")

    # PLZ41460 should be last (rank 8)
    row_41460 = sr[sr["street_id"] == "NEUSS_PLZ41460"]
    if not row_41460.empty:
        r = int(row_41460["rank"].iloc[0])
        flag = PASS if r >= 7 else WARN
        print(f"\n  {flag} | PLZ41460 (Innenstadt) rank={r} (expected 7 or 8 given low SFH share)")
        if r < 7:
            warnings.append(f"PLZ41460 is ranked {r}, lower than expected but not critical")

print()

# ── 4. UI chip consistency check ─────────────────────────────────────────────
print("--- AUDIT 4: UI chip consistency (api_server.py + street_ranking_client.py) ---")

api_server = BASE_DIR.parent.parent / "territoryai" / "api_server.py"
client_file = BASE_DIR.parent.parent / "territoryai" / "ui" / "customer" / "street_ranking_client.py"

for f in [api_server, client_file]:
    if not f.exists():
        print(f"  {WARN} | {f.name} not found (path may differ)")
        continue
    content = f.read_text(encoding="utf-8")
    has_sfh_gebiet = "SFH-Gebiet" in content
    has_viele_efh = "Viele EFH" in content
    has_050_threshold = ">= 0.50" in content or ">=0.50" in content
    has_040_threshold_chip = False
    # Check if 0.40 still appears as a chip threshold (not in other contexts like PV)
    for line in content.splitlines():
        if ">= 0.40" in line and "sfh" in line.lower():
            has_040_threshold_chip = True

    flag_label = PASS if (has_sfh_gebiet and not has_viele_efh) else FAIL
    flag_thr = PASS if has_050_threshold else WARN
    flag_stale = PASS if not has_040_threshold_chip else FAIL

    print(f"  {flag_label} | {f.name}: SFH-Gebiet={'YES' if has_sfh_gebiet else 'NO'}, Viele EFH={'STALE!' if has_viele_efh else 'cleaned'}")
    print(f"  {flag_thr} | {f.name}: threshold >= 0.50 present: {has_050_threshold}")
    print(f"  {flag_stale} | {f.name}: stale 0.40 SFH chip threshold: {has_040_threshold_chip}")

    if has_viele_efh:
        errors.append(f"{f.name} still contains stale 'Viele EFH'")
    if not has_sfh_gebiet:
        errors.append(f"{f.name} missing 'SFH-Gebiet'")

print()

# ── 5. Parity check: territoryai data matches engine output ──────────────────
print("--- AUDIT 5: Data parity (territoryai/data/layer2 vs d-ess-engine/data/layer2) ---")
tai_dir = BASE_DIR.parent.parent / "territoryai" / "data" / "layer2"
engine_dir = BASE_DIR / "data" / "layer2"

for fname in ["layer2_mvp_input_table.parquet", "street_ranking_v1.parquet", "street_level_ranking_v1.parquet"]:
    tai_f = tai_dir / fname
    eng_f = engine_dir / fname
    if tai_f.exists() and eng_f.exists():
        tai_size = tai_f.stat().st_size
        eng_size = eng_f.stat().st_size
        match = tai_size == eng_size
        flag = PASS if match else WARN
        print(f"  {flag} | {fname}: engine={eng_size:,}B, territoryai={tai_size:,}B {'MATCH' if match else 'SIZE MISMATCH'}")
        if not match:
            warnings.append(f"{fname} size mismatch — territoryai may have stale data")
    elif not tai_f.exists():
        print(f"  {FAIL} | {fname}: missing in territoryai/data/layer2/")
        errors.append(f"{fname} missing in territoryai")
    elif not eng_f.exists():
        print(f"  {WARN} | {fname}: missing in engine output")

print()

# ── Final summary ────────────────────────────────────────────────────────────
print("=" * 65)
print("  AUDIT SUMMARY")
print("=" * 65)
if errors:
    print(f"  {FAIL} {len(errors)} ERROR(S) FOUND:")
    for e in errors:
        print(f"    - {e}")
else:
    print(f"  {PASS} ALL CHECKS PASSED — 0 errors")

if warnings:
    print(f"\n  {WARN} {len(warnings)} WARNING(S):")
    for w in warnings:
        print(f"    - {w}")

print()
sys.exit(1 if errors else 0)
