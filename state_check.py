"""
state_check.py
==============
Quick snapshot of v2 foundation quality to decide what to do next.
Checks:
  1. cluster_count vs street_total discrepancy distribution
  2. Address coverage distribution
  3. Gate distribution vs v1
  4. Top streets where type breakdown might still be off
"""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\Stock Analysis\D-Energy Berater\d-ess-engine"

with open(BASE + r"\output\foundation\foundation_structure_results.json", encoding="utf-8") as f:
    fnd = json.load(f)

print(f"Foundation records: {len(fnd)}")
print()

# --- 1. cluster_count vs street_total discrepancy ---
exact_match   = 0   # cluster_count == building_count_total
small_diff    = 0   # within 10%
large_diff    = 0   # >10% off
null_count    = 0   # cluster_count is None (unparseable range)

diffs = []
for r in fnd:
    cc = r.get("cluster_building_count")
    tot = r.get("building_count_total", 0)
    if cc is None:
        null_count += 1
        continue
    if tot == 0:
        exact_match += 1
        continue
    diff_pct = abs(cc - tot) / tot
    diffs.append(diff_pct)
    if diff_pct == 0:
        exact_match += 1
    elif diff_pct <= 0.10:
        small_diff += 1
    else:
        large_diff += 1

print("=== cluster_building_count vs building_count_total ===")
print(f"  Exact match (same number)   : {exact_match}")
print(f"  Small diff (<=10%)          : {small_diff}")
print(f"  Large diff (>10%)           : {large_diff}  ← types might be off here")
print(f"  Null cluster_count          : {null_count}")
if diffs:
    avg = sum(diffs)/len(diffs)
    print(f"  Avg discrepancy             : {avg:.1%}")
print()

# --- 2. Large-diff streets (where Task A matters) ---
large_diff_records = sorted(
    [r for r in fnd
     if r.get("cluster_building_count") is not None
     and r.get("building_count_total", 0) > 0
     and abs(r["cluster_building_count"] - r["building_count_total"]) / r["building_count_total"] > 0.10],
    key=lambda x: abs(x["cluster_building_count"] - x["building_count_total"]),
    reverse=True
)

print(f"=== Top streets where type breakdown may be off (>10% discrepancy) ===")
print(f"{'Street':<35} {'range':<20} {'cluster':>7} {'total':>6} {'diff%':>6}")
print("-" * 80)
for r in large_diff_records[:15]:
    cc   = r["cluster_building_count"]
    tot  = r["building_count_total"]
    diff = abs(cc - tot) / tot if tot else 0
    print(f"  {r['street_name']:<33} {r.get('address_range','?'):<20} {cc:>7} {tot:>6} {diff:>5.0%}")
print()

# --- 3. Gate distribution ---
from collections import Counter
gates = Counter(r.get("structure_gate","?") for r in fnd)
print("=== Gate distribution (v2) ===")
for g, cnt in sorted(gates.items()):
    print(f"  {g:<12}: {cnt:>4}  ({cnt/len(fnd):.1%})")
print()

# --- 4. Address filter coverage distribution ---
cov_buckets = {"1.0 (100%)": 0, ">=0.8": 0, ">=0.5": 0, "<0.5": 0}
for r in fnd:
    cov = r.get("address_filter_coverage", 0)
    if cov == 1.0:
        cov_buckets["1.0 (100%)"] += 1
    elif cov >= 0.8:
        cov_buckets[">=0.8"] += 1
    elif cov >= 0.5:
        cov_buckets[">=0.5"] += 1
    else:
        cov_buckets["<0.5"] += 1

print("=== Address filter coverage distribution ===")
for k, v in cov_buckets.items():
    print(f"  coverage {k:<12}: {v:>4}  ({v/len(fnd):.1%})")
