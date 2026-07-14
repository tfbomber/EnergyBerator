"""
generate_neuss_osm_clusters_v2.py
==================================
Regenerates the Neuss cluster feed using the local PBF extract.

Key fixes vs v1:
  1. Data source: local Geofabrik PBF (no Overpass dependency)
  2. Building tag set: adds 'yes' and 'residential' which v1 missed,
     fixing the gap where buildings tagged building=yes were never clustered.
  3. Output: neuss_hybrid_clusters_v2.json (does NOT overwrite v1)

Clustering logic (unchanged from v1):
  - Group by (street_name + PLZ)
  - Minimum 3 buildings per cluster
  - house_range = min-to-max housenumber found in that group
  - lead_count = number of buildings in that group

PLZ assignment (Neuss Foundation KI-012 promotion, 2026-07-14 — territoryai
.ai/implementation_plan_neuss_foundation_ki012.md): this script does its OWN
independent PBF pass (separate from buildings.parquet's own extraction) and
previously bucketed every building missing addr:postcode straight into
plz="UNKNOWN" -> segment_id=NEUSS_OSM_GENERAL, with no spatial fallback —
the exact same bug already found and fixed for Leipzig
(generate_leipzig_osm_clusters.py) and Augsburg
(generate_augsburg_osm_clusters.py) the same week: Foundation resolves a
cluster's PLZ from the CLUSTER's own segment_id (not buildings.parquet), so
an unpatched cluster generator silently reintroduces contamination/UNKNOWN
regardless of how clean buildings.parquet itself is. Fixed identically:
tagged addr:postcode in KNOWN_NEUSS_PLZ is trusted as-is (fast path); a
missing/foreign tag gets a point-in-polygon lookup via the same
core.plz_lookup.PlzLookup + config/boundaries/neuss_plz_boundaries.geojson
built for the 2026-07-14 spatial-PLZ P3.
"""

import os
import sys
import json
import re
import logging
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.boundary_filter import _load_polygon, _point_in_polygon, DEFAULT_BOUNDARY_PATH
from core.plz_lookup import PlzLookup
import osmium

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")
logger = logging.getLogger("ClusterGenV2")

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH   = os.path.join(BASE_DIR, "data", "osm", "duesseldorf-regbez-latest.osm.pbf")
# Widened 2026-07-14 (Neuss Foundation KI-012 full-8-PLZ promotion): the old
# (6.61, 51.13, 6.77, 51.25) bbox cut off PLZ 41468's eastern/southern edge —
# neuss_admin_boundary.geojson's true extent is lon 6.6148-6.7984, lat
# 51.1168-51.2356. Found via generate_neuss_buildings.py's coverage diff
# (36 whole streets silently dropped). The boundary polygon check right after
# this bbox remains authoritative, so widening only removes false negatives.
NEUSS_BBOX = (6.60, 51.10, 6.81, 51.25)   # lon_min, lat_min, lon_max, lat_max
NEUSS_PLZ_BOUNDARIES_PATH = os.path.join(BASE_DIR, "config", "boundaries", "neuss_plz_boundaries.geojson")

KNOWN_NEUSS_PLZ = {
    "41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472",
}

# All building tags we consider residential (superset of v1)
RESIDENTIAL_BUILDING_TAGS = {
    "yes",               # ← NEW: was missing in v1 (most common generic tag)
    "residential",
    "house",
    "apartments",
    "detached",
    "semidetached_house",
    "terrace",
    "multi_family",
    "dormitory",
}


class _BuildingExtractorV2(osmium.SimpleHandler):
    """
    Extracts buildings with addr:street from PBF, filtered to Neuss bbox.
    Includes building=yes which was missing from the v1 Overpass query.
    """
    def __init__(self, bbox, polygon, plz_lookup):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.bbox = bbox         # (lon_min, lat_min, lon_max, lat_max)
        self.polygon = polygon   # Neuss boundary polygon for precise PiP check
        self.plz_lookup = plz_lookup
        self.n_spatial_recovered = 0
        self.n_still_unknown = 0

    def way(self, w):
        tags = w.tags

        # Must have addr:street to be useful for clustering
        street = tags.get("addr:street", "")
        if not street:
            return

        # Must be a residential building
        building_tag = tags.get("building", "").lower().strip()
        if building_tag not in RESIDENTIAL_BUILDING_TAGS:
            return

        # Get centroid (requires locations=True)
        nodes = [(n.location.lon, n.location.lat) for n in w.nodes if n.location.valid()]
        if not nodes:
            return

        c_lon = sum(x for x, _ in nodes) / len(nodes)
        c_lat = sum(y for _, y in nodes) / len(nodes)

        # Bbox pre-filter (fast)
        lon_min, lat_min, lon_max, lat_max = self.bbox
        if not (lat_min <= c_lat <= lat_max and lon_min <= c_lon <= lon_max):
            return

        # Precise boundary polygon check (Neuss boundary)
        if self.polygon and not _point_in_polygon(c_lat, c_lon, self.polygon):
            return

        postal_code_raw = tags.get("addr:postcode", "")
        if postal_code_raw in KNOWN_NEUSS_PLZ:
            plz = postal_code_raw  # fast path — tagged, untouched
        else:
            spatial_plz = self.plz_lookup.lookup(c_lon, c_lat)
            if spatial_plz is not None:
                plz = spatial_plz
                self.n_spatial_recovered += 1
            else:
                plz = "UNKNOWN"
                self.n_still_unknown += 1

        self.buildings.append({
            "street":      street,
            "housenumber": tags.get("addr:housenumber", ""),
            "plz":         plz,
            "building":    building_tag,
            "lat":         c_lat,
            "lon":         c_lon,
        })


def sort_housenumber(s):
    m = re.search(r"\d+", str(s))
    return int(m.group()) if m else 99999


def main():
    logger.info("=== Neuss Cluster Generation v2 ===")
    logger.info(f"PBF: {PBF_PATH}")

    if not os.path.exists(PBF_PATH):
        logger.error(f"PBF not found: {PBF_PATH}")
        sys.exit(1)

    # Load Neuss boundary polygon
    polygon = _load_polygon(DEFAULT_BOUNDARY_PATH)
    if not polygon:
        logger.error("Failed to load Neuss boundary polygon.")
        sys.exit(1)

    logger.info("Loading 8 Neuss PLZ boundary polygons for spatial fallback...")
    plz_lookup = PlzLookup(NEUSS_PLZ_BOUNDARIES_PATH, expected_count=8)

    # Extract buildings from PBF
    logger.info("Extracting residential buildings from PBF (Neuss bbox + boundary)...")
    handler = _BuildingExtractorV2(bbox=NEUSS_BBOX, polygon=polygon, plz_lookup=plz_lookup)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")
    buildings = handler.buildings

    logger.info(f"Extracted {len(buildings)} buildings with addr:street inside Neuss boundary.")
    logger.info(f"Spatially recovered (untagged/foreign-tag, PiP-matched): {handler.n_spatial_recovered}")
    logger.info(f"Still UNKNOWN (outside all 8 PLZ polygons): {handler.n_still_unknown}")

    # --- Tag breakdown (diagnostic) ---
    from collections import Counter
    tag_counts = Counter(b["building"] for b in buildings)
    logger.info("Building tag breakdown:")
    for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1]):
        v1_covered = "✓ v1" if tag in {"house", "residential", "apartments", "detached", "semidetached_house", "terrace"} else "NEW"
        logger.info(f"  {tag:<25} {cnt:>5}  {v1_covered}")

    # --- Cluster by (street + PLZ) ---
    clusters_dict: dict = {}
    for b in buildings:
        key = f"{b['street']}___{b['plz']}"
        if key not in clusters_dict:
            clusters_dict[key] = {
                "street":       b["street"],
                "plz":          b["plz"],
                "lats":         [],
                "lons":         [],
                "housenumbers": [],
            }
        clusters_dict[key]["lats"].append(b["lat"])
        clusters_dict[key]["lons"].append(b["lon"])
        if b["housenumber"]:
            clusters_dict[key]["housenumbers"].append(b["housenumber"])

    logger.info(f"Street+PLZ groups before size filter: {len(clusters_dict)}")

    # --- Build cluster records ---
    out_clusters = []
    c_idx = 1
    skipped_small = 0

    for key, data in sorted(clusters_dict.items()):
        count = len(data["lats"])
        if count < 3:
            skipped_small += 1
            continue

        c_lat = sum(data["lats"]) / count
        c_lon = sum(data["lons"]) / count

        # House range from tagged housenumbers
        hns = [hn for hn in data["housenumbers"] if str(hn).strip()]
        if hns:
            try:
                hns_sorted = sorted(set(hns), key=sort_housenumber)
                house_range = f"{hns_sorted[0]} - {hns_sorted[-1]}" if len(hns_sorted) > 1 else str(hns_sorted[0])
            except Exception:
                house_range = f"{hns[0]}... ({len(set(hns))} parsed)"
        else:
            house_range = "unknown"

        plz_clean = data["plz"].replace(" ", "_")
        seg_id = f"NEUSS_OSM_{plz_clean}" if data["plz"] != "UNKNOWN" else "NEUSS_OSM_GENERAL"
        A_count = max(1, int(count * 0.4))
        B_count = count - A_count

        out_clusters.append({
            "cluster_id":            f"N_{c_idx:03d}",
            "segment_id":            seg_id,
            "primary_street":        data["street"],
            "house_range":           house_range,
            "lead_count":            count,
            "A_count":               A_count,
            "B_count":               B_count,
            "unnamed_attached_count": 0,
            "recommended_action":    "DOOR_TO_DOOR_FIRST" if count > 10 else "DESK_REVIEW_FIRST",
            "cluster_centroid_lat":  round(c_lat, 6),
            "cluster_centroid_lon":  round(c_lon, 6),
            # v2 metadata
            "_v2_generated_at":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "_v2_buildings_in_pbf":  count,
            "_v2_housenumber_coverage": round(len(hns) / count, 3) if count else 0.0,
        })
        c_idx += 1

    logger.info(f"Skipped {skipped_small} street+PLZ groups with < 3 buildings.")
    logger.info(f"Generated {len(out_clusters)} clusters (v1 had 554).")

    # --- Save ---
    out_path = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v2.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_clusters, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved: {out_path}")

    # --- Quick comparison vs v1 ---
    v1_path = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v1.json")
    if os.path.exists(v1_path):
        with open(v1_path, encoding="utf-8") as f:
            v1 = json.load(f)
        v1_streets = {c["primary_street"] for c in v1}
        v2_streets = {c["primary_street"] for c in out_clusters}
        new_streets = v2_streets - v1_streets
        removed_streets = v1_streets - v2_streets
        logger.info(f"\n=== v1 vs v2 Comparison ===")
        logger.info(f"  v1 clusters: {len(v1)}")
        logger.info(f"  v2 clusters: {len(out_clusters)}")
        logger.info(f"  Net change : {len(out_clusters) - len(v1):+d}")
        logger.info(f"  New streets in v2 (were missing): {len(new_streets)}")
        if new_streets:
            for s in sorted(new_streets)[:20]:
                logger.info(f"    + {s}")
        if removed_streets:
            logger.info(f"  Streets in v1 but not v2 (dropped below threshold): {len(removed_streets)}")
            for s in sorted(removed_streets)[:10]:
                logger.info(f"    - {s}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
