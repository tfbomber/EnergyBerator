import json, sys
sys.stdout.reconfigure(encoding="utf-8")

with open(r"output\foundation\foundation_structure_results.json", encoding="utf-8") as f:
    fnd = json.load(f)

print(f"Records: {len(fnd)}")
print()

# Check new Task A fields exist
sample = fnd[0]
task_a_fields = ["cluster_sfh_detached_count", "cluster_sfh_semi_count", "cluster_sfh_rowhouse_count"]
for field in task_a_fields:
    val = sample.get(field)
    print(f"  {field}: {val} ({'PRESENT' if field in sample else 'MISSING'})")
print()

# Spot check: Tannenweg
tannen = next((r for r in fnd if r["street_name"] == "Tannenweg"), None)
if tannen:
    print("=== Tannenweg (v2: full street, ratio=1.0) ===")
    print(f"  cluster_building_count    = {tannen['cluster_building_count']}")
    print(f"  building_count_total      = {tannen['building_count_total']}")
    print(f"  sfh_detached_count        = {tannen['sfh_detached_count']}  (whole street)")
    print(f"  cluster_sfh_detached      = {tannen['cluster_sfh_detached_count']}  (cluster-scoped)")
    print(f"  sfh_semi_detached_count   = {tannen['sfh_semi_detached_count']}")
    print(f"  cluster_sfh_semi          = {tannen['cluster_sfh_semi_count']}")
    print(f"  sfh_rowhouse_count        = {tannen['sfh_rowhouse_count']}")
    print(f"  cluster_sfh_rowhouse      = {tannen['cluster_sfh_rowhouse_count']}")
    ratio = tannen['cluster_building_count'] / tannen['building_count_total'] if tannen['building_count_total'] else 0
    print(f"  scale_ratio               = {ratio:.3f}")
print()

# Multi-cluster street check: find a street with big discrepancy
from collections import defaultdict
by_street = defaultdict(list)
for r in fnd:
    by_street[r["street_name"]].append(r)

multi_cluster = [(s, rows) for s, rows in by_street.items() if len(rows) > 1]
print(f"=== Streets with >1 cluster: {len(multi_cluster)} ===")
for street, rows in sorted(multi_cluster, key=lambda x: -len(x[1]))[:5]:
    print(f"\n  {street} ({len(rows)} clusters):")
    for r in rows:
        tot = r["building_count_total"]
        cc = r["cluster_building_count"]
        ratio = cc/tot if tot else 0
        efh_whole = r["sfh_detached_count"]
        efh_cluster = r["cluster_sfh_detached_count"]
        print(f"    {r['cluster_id']}  range={r['address_range']:<20} "
              f"total={tot}  cluster={cc}  ratio={ratio:.2f}  "
              f"EFH: {efh_whole}->{efh_cluster}")
