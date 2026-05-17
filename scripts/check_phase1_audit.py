"""
check_phase1_audit.py
=====================
Phase 1 audit script for Kaarst expansion.
Verifies boundary GeoJSON, cluster output, data isolation, and script correctness.
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BOUNDARY_PATH     = os.path.join(BASE_DIR, "config", "boundaries", "kaarst_admin_boundary.geojson")
KAARST_CLUSTERS   = os.path.join(BASE_DIR, "output", "clusters", "kaarst_hybrid_clusters_v1.json")
NEUSS_CLUSTERS    = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v2.json")
SCRIPT_PATH       = os.path.join(BASE_DIR, "scripts", "generate_kaarst_osm_clusters.py")

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

results = []

def check(label, condition, level=PASS, detail=""):
    status = PASS if condition else FAIL
    if not condition and level == WARN:
        status = WARN
    results.append((label, status, detail))
    icon = "[OK]  " if status == PASS else ("[WARN]" if status == WARN else "[FAIL]")
    print(f"  {icon} [{status}] {label}" + (f" - {detail}" if detail else ""))

print("=" * 60)
print("  PHASE 1 AUDIT - Kaarst OSM Cluster Generation")
print("=" * 60)

# ── A. Boundary GeoJSON ───────────────────────────────────────
print("\n[A] Boundary GeoJSON")
check("File exists", os.path.exists(BOUNDARY_PATH))
check("File not empty", os.path.exists(BOUNDARY_PATH) and os.path.getsize(BOUNDARY_PATH) > 10000,
      detail=f"size={os.path.getsize(BOUNDARY_PATH):,} bytes" if os.path.exists(BOUNDARY_PATH) else "N/A")

if os.path.exists(BOUNDARY_PATH):
    with open(BOUNDARY_PATH, encoding="utf-8") as f:
        bd = json.load(f)

    geo = bd["features"][0]["geometry"]
    geo_type = geo.get("type", "")
    check("Geometry is Polygon or MultiPolygon", geo_type in ("Polygon", "MultiPolygon"), detail=f"type={geo_type}")

    if geo_type == "MultiPolygon":
        rings = geo["coordinates"][0][0]
    elif geo_type == "Polygon":
        rings = geo["coordinates"][0]
    else:
        rings = []

    lons = [c[0] for c in rings]
    lats = [c[1] for c in rings]

    # Kaarst PLZ 41564 geographic center ~(6.617, 51.226)
    KAARST_LON = 6.617
    KAARST_LAT = 51.226
    check("Lon bbox covers Kaarst center (6.617)", min(lons) < KAARST_LON < max(lons),
          detail=f"lon range: {min(lons):.4f}–{max(lons):.4f}")
    check("Lat bbox covers Kaarst center (51.226)", min(lats) < KAARST_LAT < max(lats),
          detail=f"lat range: {min(lats):.4f}–{max(lats):.4f}")
    check("Coordinate count >= 50 (real polygon, not stub)", len(rings) >= 50,
          detail=f"points={len(rings)}")

# ── B. Cluster Output File ────────────────────────────────────
print("\n[B] Kaarst Cluster Output")
check("File exists", os.path.exists(KAARST_CLUSTERS))

if os.path.exists(KAARST_CLUSTERS):
    with open(KAARST_CLUSTERS, encoding="utf-8") as f:
        kaarst = json.load(f)

    check("Cluster count > 0", len(kaarst) > 0, detail=f"count={len(kaarst)}")
    check("Cluster count realistic for small city (>50)", len(kaarst) >= 50, detail=f"count={len(kaarst)}")

    bad_ids = [c["cluster_id"] for c in kaarst if not c["cluster_id"].startswith("K_")]
    check("All cluster_ids use K_ prefix", len(bad_ids) == 0, detail=f"bad={bad_ids[:3]}" if bad_ids else "")

    bad_segs = [c["segment_id"] for c in kaarst if not c["segment_id"].startswith("KAARST_")]
    check("All segment_ids use KAARST_ prefix", len(bad_segs) == 0, detail=f"bad={bad_segs[:3]}" if bad_segs else "")

    too_small = [c for c in kaarst if c["lead_count"] < 3]
    check("No clusters with lead_count < 3 (filter applied)", len(too_small) == 0,
          detail=f"found {len(too_small)} violations" if too_small else "")

    bad_coords = [c for c in kaarst if not (
        51.17 <= c["cluster_centroid_lat"] <= 51.27 and
        6.55  <= c["cluster_centroid_lon"] <= 6.68
    )]
    check("All centroids inside Kaarst geographic bbox", len(bad_coords) == 0,
          detail=f"{len(bad_coords)} outliers" if bad_coords else "")

    general = [c for c in kaarst if c["segment_id"] == "KAARST_OSM_GENERAL"]
    check("KAARST_OSM_GENERAL count < 15% of total", len(general) < len(kaarst) * 0.15,
          level=WARN, detail=f"count={len(general)}/{len(kaarst)} ({100*len(general)/len(kaarst):.1f}%)")

    cov_avg = sum(c["_v2_housenumber_coverage"] for c in kaarst) / len(kaarst)
    check("Avg housenumber coverage >= 0.80", cov_avg >= 0.80, detail=f"avg={cov_avg:.3f}")

# ── C. Data Isolation ─────────────────────────────────────────
print("\n[C] Data Isolation (Neuss not modified)")
check("Neuss v2 cluster file still exists", os.path.exists(NEUSS_CLUSTERS))

if os.path.exists(NEUSS_CLUSTERS) and os.path.exists(KAARST_CLUSTERS):
    with open(NEUSS_CLUSTERS, encoding="utf-8") as f:
        neuss = json.load(f)

    neuss_cids  = set(c["cluster_id"]  for c in neuss)
    kaarst_cids = set(c["cluster_id"]  for c in kaarst)
    overlap     = neuss_cids & kaarst_cids
    check("No cluster_id overlap between Neuss and Kaarst", len(overlap) == 0,
          detail=f"overlapping: {overlap}" if overlap else "")

    all_n = all(cid.startswith("N_") for cid in neuss_cids)
    check("All Neuss cluster_ids still use N_ prefix", all_n)

    neuss_segs = set(c["segment_id"] for c in neuss)
    kaarst_pollution = any("KAARST" in s for s in neuss_segs)
    check("Neuss file not polluted with Kaarst segment_ids", not kaarst_pollution)

    check("Neuss cluster count unchanged at 889", len(neuss) == 889, detail=f"actual={len(neuss)}")

# ── D. Script Configuration ───────────────────────────────────
print("\n[D] Script Configuration")
check("Script file exists", os.path.exists(SCRIPT_PATH))

if os.path.exists(SCRIPT_PATH):
    with open(SCRIPT_PATH, encoding="utf-8") as f:
        src = f.read()

    check("KAARST_BBOX defined", "KAARST_BBOX" in src)
    check("KAARST_BOUNDARY_PATH defined", "KAARST_BOUNDARY_PATH" in src)
    check("Neuss bbox not used", "NEUSS_BBOX" not in src)
    check("DEFAULT_BOUNDARY_PATH (Neuss boundary) not used", "DEFAULT_BOUNDARY_PATH" not in src)
    check("K_ cluster_id prefix", "K_{c_idx:03d}" in src)
    check("KAARST_OSM_ segment_id prefix", "KAARST_OSM_" in src)
    check("Output file is kaarst_hybrid_clusters_v1.json", "kaarst_hybrid_clusters_v1.json" in src)
    check("Does not write to neuss_hybrid_clusters files", "neuss_hybrid_clusters" not in src)

# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
total  = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
warns  = sum(1 for _, s, _ in results if s == WARN)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"  RESULT: {passed}/{total} PASS  |  {warns} WARN  |  {failed} FAIL")
print("=" * 60)

if failed > 0:
    sys.exit(1)
