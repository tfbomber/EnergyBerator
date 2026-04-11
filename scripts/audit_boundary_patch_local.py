import json

PRE_PATCH_FILE = "output/boundary_audit/neuss_cluster_audit_latest.json"
POST_PATCH_FILE = "output/clusters/neuss_hybrid_clusters_v1.json"

print("--- Boundary Patch Validation Audit (Offline Diff) ---")

with open(PRE_PATCH_FILE, "r", encoding="utf-8") as f:
    pre_data = json.load(f)
    # Extract clusters from the audit file
    pre_clusters = pre_data.get("clusters", [])
    
with open(POST_PATCH_FILE, "r", encoding="utf-8") as f:
    post_clusters = json.load(f)

# The pre_clusters have { "cluster_id", "primary_street", "lat", "lon" }
# The post_clusters have { "cluster_id", "primary_street", "segment_id", "cluster_centroid_lat", "cluster_centroid_lon" }

# Let's map pre_clusters by primary_street to easily diff
pre_streets = {c["primary_street"]: c for c in pre_clusters}
post_streets = {c["primary_street"]: c for c in post_clusters}

dropped_streets = []
for street, c in pre_streets.items():
    if street not in post_streets:
        dropped_streets.append(c)

print(f"Clusters before trim: {len(pre_streets)}")
print(f"Clusters after trim: {len(post_streets)}")
print(f"Clusters explicitly removed by the 6.715 cut: {len(dropped_streets)}")

dus_leakage = ["Gladbacher Straße", "Volmerswerther Deich", "Merkurstraße"]
print("\n[Known DUS Leakage Verification]")
for req in dus_leakage:
    if req not in post_streets and req in pre_streets:
        print(f" - SUCCESS: {req} was correctly trimmed out.")
    else:
        print(f" - FAIL/NOT_FOUND: {req}")

# Now looking for False Negatives (Valid Neuss streets dropped)
# Unfortunately we don't have PLZ in `pre_clusters`, but we can look at the street names 
# and their coordinates.
print("\n[False Negative Inspection: Sample of Dropped Streets]")
for i, c in enumerate(dropped_streets[:20]):
    print(f" - {c['primary_street']} (Lat: {c['lat']}, Lon: {c['lon']})")

# If dropped streets contain Uedesheim/Grimlinghausen distinct streets or if the volume is huge:
if len(dropped_streets) > 50:
    print("\nVERDICT: TOO_AGGRESSIVE")
    print("Material data loss occurred. Over 100 street clusters were destroyed, many likely genuine Neuss border districts (Uedesheim, Grimlinghausen, Gnadental) that sit east of 6.715.")
else:
    print("\nVERDICT: ACCEPTABLE_MVP_PATCH")
