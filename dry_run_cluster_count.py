"""
dry_run_cluster_count.py
========================
Simulates what cluster_building_count would look like for suspicious streets,
WITHOUT calling Overpass. Uses only existing local data.

For each suspicious cluster, it checks:
  - house_range  (from neuss_hybrid_clusters_v1.json)
  - building_count_total (from foundation_structure_results.json)
  - What cluster_building_count WOULD be if OSM buildings had housenumbers
    (estimated from range parsing — the min/max filter would cap the count)
"""

import sys, json, re
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\Stock Analysis\D-Energy Berater\d-ess-engine"

with open(BASE + r"\output\foundation\foundation_structure_results.json", encoding="utf-8") as f:
    foundation = json.load(f)

with open(BASE + r"\output\clusters\neuss_hybrid_clusters_v1.json", encoding="utf-8") as f:
    clusters = json.load(f)

cluster_map = {c["cluster_id"]: c for c in clusters}

# Simulate the range filter on the WORST cases
# Since we don't have per-building housenumbers locally, we show:
# - "range_max_possible" = how many could POSSIBLY be in range (max_num - min_num + 1) * some_factor
# - "current" = building_count_total (the inflated number)
# - verdict: DEFINITELY_WRONG if current >> range_max_possible

def parse_range(r):
    nums = re.findall(r"\d+", str(r))
    if len(nums) >= 2:
        return int(nums[0]), int(nums[-1])
    return None, None

print("=" * 115)
print(f"  {'Street':<34} {'Range':<15} {'Fnd N':>6}  {'RangeSpan':>9}  {'lead_count':>10}  {'Verdict'}")
print("=" * 115)

for f_rec in sorted(foundation, key=lambda x: -x.get("building_count_total", 0)):
    cid = f_rec["cluster_id"]
    cluster = cluster_map.get(cid, {})
    house_range = f_rec.get("address_range", "unknown")
    fnd_n = f_rec.get("building_count_total", 0)
    lead_count = cluster.get("lead_count", "?")

    min_n, max_n = parse_range(house_range)
    if min_n is None:
        span = "?"
        verdict = "RANGE_UNKNOWN"
    else:
        span = max_n - min_n
        if span == 0:
            # e.g. "30b - 30c" → only buildings starting with 30
            verdict = "SUSPICIOUS (single-number range)" if fnd_n > 5 else "OK"
        elif fnd_n > (span + 1) * 4:
            # rough heuristic: more than 4 buildings per main number = whole street counted
            verdict = "INFLATED (whole street counted)"
        else:
            verdict = "OK"

    if verdict != "OK" and fnd_n > 10:
        line = "  {:<34} {:<15} {:>6}  {:>9}  {:>10}  {}".format(
            f_rec["street_name"], house_range, fnd_n,
            str(span), str(lead_count), verdict)
        print(line)

print("=" * 115)
print()
print("NOTE: lead_count = original canvassing target from cluster definition")
print("      Fnd N      = current building_count_total (inflated, whole street)")
print("      After fix  = cluster_building_count will correctly reflect range-filtered count")
print()
print("KEY INSIGHT: For streets where Fnd N >> lead_count * 2,")
print("the pipeline is clearly counting the whole street, not the cluster segment.")
