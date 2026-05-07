import sys, json
sys.stdout.reconfigure(encoding="utf-8")

with open(r"output\clusters\neuss_hybrid_clusters_v1.json", encoding="utf-8") as f:
    clusters = json.load(f)

with open(r"output\foundation\foundation_structure_results.json", encoding="utf-8") as f:
    foundation = json.load(f)

fnd_map = {c["cluster_id"]: c for c in foundation}

tannen = [c for c in clusters if "Tannenweg" in c.get("primary_street", "")]
print(f"Clusters with primary_street=Tannenweg: {len(tannen)}")
print()
for c in tannen:
    cid = c["cluster_id"]
    f = fnd_map.get(cid, {})
    rng = c.get("house_range", "?")
    lead = c.get("lead_count", "?")
    tot = f.get("building_count_total", "?")
    clust = f.get("cluster_building_count", "?")
    semi = f.get("sfh_semi_detached_count", "?")
    row = f.get("sfh_rowhouse_count", "?")
    gate = f.get("structure_gate", "?")
    print(f"  cluster_id             = {cid}")
    print(f"  house_range (cluster)  = {rng}")
    print(f"  lead_count             = {lead}")
    print(f"  building_count_total   = {tot}  (whole street)")
    print(f"  cluster_building_count = {clust}  (range-filtered)")
    print(f"  sfh_semi               = {semi}")
    print(f"  sfh_row                = {row}")
    print(f"  structure_gate         = {gate}")
    print()
