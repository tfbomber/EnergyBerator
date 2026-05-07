import json, sys
sys.stdout.reconfigure(encoding="utf-8")
with open("output/clusters/neuss_hybrid_clusters_v2.json", encoding="utf-8") as f:
    v2 = json.load(f)
tannen = [c for c in v2 if "Tannenweg" in c["primary_street"]]
print(f"Tannenweg clusters in v2: {len(tannen)}")
for c in tannen:
    cid = c["cluster_id"]
    rng = c["house_range"]
    lead = c["lead_count"]
    cov = c.get("_v2_housenumber_coverage", "?")
    print(f"  {cid}  range={rng}  lead_count={lead}  nr_coverage={cov}")
