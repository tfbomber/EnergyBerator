"""
generate_neuss_audit.py
One-shot script: runs boundary filter on real cluster data and writes the audit artifact.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.boundary_filter import filter_clusters_to_neuss

cluster_file = os.path.join("output", "clusters", "neuss_hybrid_clusters_v1.json")
with open(cluster_file, "r", encoding="utf-8") as f:
    clusters = json.load(f)

result = filter_clusters_to_neuss(clusters, source_file=cluster_file)
m = result["meta"]

print(f"=== BOUNDARY FILTER — LIVE VALIDATION ===")
print(f"Status         : {result['boundary_status']}")
print(f"Method         : {m['boundary_method']}")
print(f"Total Input    : {m['total_input']}")
print(f"KEPT           : {m['kept_count']}")
print(f"REJECTED       : {m['rejected_count']}")
print()
print("--- REJECTED clusters ---")
for v in result["cluster_verdicts"]:
    if v["verdict"] != "KEPT":
        print(f"  {v['cluster_id']:6s} | {str(v['primary_street'])[:35]:35s} | lat={v['lat']} lon={v['lon']} | {v['verdict']}")
print()
print("--- KEPT clusters ---")
kept_v = [v for v in result["cluster_verdicts"] if v["verdict"] == "KEPT"]
for v in kept_v:
    print(f"  {v['cluster_id']:6s} | {str(v['primary_street'])[:35]:35s} | lat={v['lat']:.5f} lon={v['lon']:.5f}")
print()
print(f"Audit artifact: output/boundary_audit/neuss_cluster_audit_latest.json")
