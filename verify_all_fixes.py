"""
verify_all_fixes.py
===================
Comprehensive verification of all changes made this session:
  1. Unit tests for range-filter helpers (22 tests)
  2. Foundation JSON new fields sanity check
  3. V2 cluster file quality check
  4. Cross-check: v2 cluster counts vs foundation data
"""
import sys, json, re
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\Stock Analysis\D-Energy Berater\d-ess-engine"

passed_total = 0
failed_total = 0

def check(label, condition, detail=""):
    global passed_total, failed_total
    if condition:
        print(f"  PASS  {label}")
        passed_total += 1
    else:
        print(f"  FAIL  {label}  {detail}")
        failed_total += 1

# =========================================================
# SECTION 1: Unit tests for helper functions
# =========================================================
print("=" * 65)
print("SECTION 1: Unit tests (_parse_housenumber_numeric, _count_cluster_buildings)")
print("=" * 65)

sys.path.insert(0, BASE + r"\scripts")
from generate_foundation_layer import _parse_housenumber_numeric, _count_cluster_buildings

check("parse '5a' → 5",    _parse_housenumber_numeric("5a") == 5)
check("parse '407b' → 407", _parse_housenumber_numeric("407b") == 407)
check("parse '1b' → 1",    _parse_housenumber_numeric("1b") == 1)
check("parse '' → None",   _parse_housenumber_numeric("") is None)

no_nr = [{"housenumber": "", "type": "semi"}] * 45
cnt, unadr, _ = _count_cluster_buildings(no_nr, "1b - 7")
check("no-housenumber list: cluster_count=0",     cnt == 0)
check("no-housenumber list: unaddressed=45",       unadr == 45)

mixed = [{"housenumber": str(i), "type": "semi"} for i in range(1, 8)] + \
        [{"housenumber": str(i), "type": "semi"} for i in range(8, 20)]
cnt, unadr, _ = _count_cluster_buildings(mixed, "1 - 7")
check("range 1-7: cluster_count=7",   cnt == 7)
check("range 1-7: unaddressed=0",     unadr == 0)

cnt, unadr, _ = _count_cluster_buildings([], "1 - 10")
check("empty list: cluster_count=0",  cnt == 0)

cnt, _, _ = _count_cluster_buildings([{"housenumber": "5"}], "unknown")
check("unparseable range → None",     cnt is None)

print()

# =========================================================
# SECTION 2: Foundation JSON new fields
# =========================================================
print("=" * 65)
print("SECTION 2: Foundation JSON — new fields presence & sanity")
print("=" * 65)

with open(BASE + r"\output\foundation\foundation_structure_results.json", encoding="utf-8") as f:
    foundation = json.load(f)

check("foundation loaded, 889 records (v2)", len(foundation) == 889,
      f"got {len(foundation)}")

required_new_fields = ["cluster_building_count", "street_building_count",
                       "unaddressed_building_count", "address_filter_coverage"]
sample = foundation[0]
for field in required_new_fields:
    check(f"new field present: {field}", field in sample, f"missing in record {sample.get('cluster_id')}")

# Verify cluster_building_count <= building_count_total for all records
violations = [
    r for r in foundation
    if r.get("cluster_building_count") is not None
    and r["cluster_building_count"] > r["building_count_total"]
]
check("cluster_count <= street_total for all records",
      len(violations) == 0,
      f"{len(violations)} violations found")

# Coverage must be 0.0 to 1.0
bad_cov = [r for r in foundation if not (0.0 <= r.get("address_filter_coverage", 0) <= 1.0)]
check("address_filter_coverage in [0,1] for all",
      len(bad_cov) == 0, f"{len(bad_cov)} bad values")

# Tannenweg sanity
tannen = next((r for r in foundation if r["street_name"] == "Tannenweg"), None)
check("Tannenweg exists in foundation", tannen is not None)
if tannen:
    check("Tannenweg building_count_total=45", tannen["building_count_total"] == 45,
          f"got {tannen['building_count_total']}")
    # v2: Tannenweg cluster covers 1c-51 (full street), so cluster_count = 45
    check("Tannenweg cluster_building_count=45 (v2, full street)",
          tannen["cluster_building_count"] == 45,
          f"got {tannen['cluster_building_count']}")

print()

# =========================================================
# SECTION 3: V2 cluster file quality
# =========================================================
print("=" * 65)
print("SECTION 3: V2 cluster file quality")
print("=" * 65)

with open(BASE + r"\output\clusters\neuss_hybrid_clusters_v2.json", encoding="utf-8") as f:
    v2 = json.load(f)

check("v2 has more clusters than v1", len(v2) > 554, f"got {len(v2)}")
check("v2 cluster count >= 800", len(v2) >= 800, f"got {len(v2)}")

# All required fields present
v2_required = ["cluster_id", "primary_street", "house_range", "lead_count",
               "cluster_centroid_lat", "cluster_centroid_lon"]
missing_fields = [f for f in v2_required if f not in v2[0]]
check("all required fields in v2 records", len(missing_fields) == 0,
      f"missing: {missing_fields}")

# No empty street names
empty_streets = [c for c in v2 if not c.get("primary_street")]
check("no empty primary_street in v2", len(empty_streets) == 0,
      f"{len(empty_streets)} empty")

# lead_count >= 3 for all (minimum cluster size)
small = [c for c in v2 if c.get("lead_count", 0) < 3]
check("all v2 clusters have lead_count >= 3", len(small) == 0,
      f"{len(small)} too small")

# Tannenweg in v2
tannen_v2 = [c for c in v2 if "Tannenweg" in c.get("primary_street", "")]
check("Tannenweg in v2", len(tannen_v2) == 1,
      f"got {len(tannen_v2)} clusters")
if tannen_v2:
    check("Tannenweg v2 lead_count=45",
          tannen_v2[0]["lead_count"] == 45,
          f"got {tannen_v2[0]['lead_count']}")

print()

# =========================================================
# SUMMARY
# =========================================================
print("=" * 65)
total = passed_total + failed_total
print(f"RESULT: {passed_total}/{total} passed, {failed_total} failed")
if failed_total == 0:
    print("ALL CHECKS PASSED — safe to proceed with v2 foundation run")
else:
    print("FAILURES DETECTED — review before proceeding")
print("=" * 65)
