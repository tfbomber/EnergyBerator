"""
audit_address_coverage.py
=========================
Checks addr:housenumber coverage per street via Overpass API.
"""

import json
import re
import sys
import time

import requests

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\Stock Analysis\D-Energy Berater\d-ess-engine"
FOUNDATION_JSON = BASE + r"\output\foundation\foundation_structure_results.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# --- Load foundation ---
with open(FOUNDATION_JSON, encoding="utf-8") as f:
    foundation = json.load(f)


def range_span(r):
    nums = re.findall(r"\d+", str(r))
    if len(nums) >= 2:
        return abs(int(nums[-1]) - int(nums[0]))
    return 999


# --- Pick target streets ---
suspects = []
for c in foundation:
    n = c.get("building_count_total", 0)
    r = c.get("address_range", "")
    span = range_span(r)
    plz = c.get("plz", "")
    if n >= 20 and span <= 12 and plz.startswith("414"):
        suspects.append(c)

suspects.sort(key=lambda x: x["building_count_total"], reverse=True)
target_streets = suspects[:8]

# Also add 3 "normal" looking streets for baseline comparison
normals = []
for c in foundation:
    n = c.get("building_count_total", 0)
    r = c.get("address_range", "")
    span = range_span(r)
    if 12 <= n <= 20 and span >= 20 and c.get("plz", "").startswith("414"):
        normals.append(c)
normals.sort(key=lambda x: x["building_count_total"])
target_streets += normals[:3]

print("=== Target streets for Overpass audit ===")
print(f"{'Street':<38} {'PLZ':<6} {'N(found)':<10} {'Range':<16} {'Span'}")
for c in target_streets:
    print(f"  {c['street_name']:<36} {c['plz']:<6} {c['building_count_total']:<10} "
          f"{c['address_range']:<16} {range_span(c['address_range'])}")

print()
print("=== Querying Overpass for housenumber coverage ===")

results = []

for c in target_streets:
    street = c["street_name"]
    plz = c["plz"]

    query = f"""
[out:json][timeout:30];
(
  way["building"]["addr:street"="{street}"](51.10,6.55,51.30,6.85);
);
out tags;
"""
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": "TerritoryAI-Audit/1.0"},
            timeout=35,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])

        with_num = sum(1 for e in elements if e.get("tags", {}).get("addr:housenumber"))
        without_num = len(elements) - with_num
        coverage = with_num / len(elements) * 100 if elements else 0

        results.append({
            "street": street,
            "plz": plz,
            "foundation_count": c["building_count_total"],
            "house_range": c["address_range"],
            "osm_total": len(elements),
            "with_housenumber": with_num,
            "without_housenumber": without_num,
            "coverage_pct": round(coverage, 1),
            "sfh_semi": c.get("sfh_semi_detached_count", 0),
            "sfh_row": c.get("sfh_rowhouse_count", 0),
        })

        print(f"  OK  {street:<36} osm={len(elements):>3}  w/nr={with_num:>3}  wo/nr={without_num:>3}  cov={coverage:.0f}%")

    except Exception as e:
        print(f"  ERR {street:<36} {e}")
        results.append({
            "street": street, "plz": plz,
            "foundation_count": c["building_count_total"],
            "house_range": c["address_range"],
            "osm_total": "ERR", "with_housenumber": "ERR",
            "without_housenumber": "ERR", "coverage_pct": "ERR",
        })

    time.sleep(1.5)

# --- Summary table ---
print()
print("=" * 108)
print(f"  {'Street':<34} {'PLZ':<6} {'FndN':<6} {'Range':<15} {'OSM':<6} {'w/Nr':<6} {'wo/Nr':<7} {'Cov%':<7} Flag")
print("=" * 108)
for r in results:
    flag = "[LOW COV]" if isinstance(r["coverage_pct"], float) and r["coverage_pct"] < 50 else ""
    print(
        f"  {r['street']:<34} {r['plz']:<6} {r['foundation_count']:<6} "
        f"{r['house_range']:<15} {str(r['osm_total']):<6} {str(r['with_housenumber']):<6} "
        f"{str(r['without_housenumber']):<7} {str(r['coverage_pct']):<7} {flag}"
    )
print("=" * 108)
print()
print("Legend:")
print("  FndN    = building_count_total (foundation JSON)")
print("  OSM     = total buildings Overpass finds with addr:street=<name>")
print("  w/Nr    = buildings with addr:housenumber (range-filterable)")
print("  wo/Nr   = buildings WITHOUT housenumber (invisible to range filter)")
print("  Cov%    = housenumber coverage (w/Nr / OSM)")
print("  [LOW COV] = <50% coverage - range-based filtering would be unreliable")
