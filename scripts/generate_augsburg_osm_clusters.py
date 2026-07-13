"""
generate_augsburg_osm_clusters.py
==================================
Generates the Augsburg cluster feed using the local Schwaben PBF extract.
Adapted from generate_kaarst_osm_clusters.py (itself adapted from
generate_neuss_osm_clusters_v2.py).

Clustering logic:
  - Group by (street_name + PLZ)
  - Minimum 3 buildings per cluster
  - house_range = min-to-max housenumber found in that group
  - lead_count = number of buildings in that group
"""

import os
import sys
import json
import re
import logging
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.boundary_filter import _load_polygon, _point_in_polygon
import osmium

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")
logger = logging.getLogger("ClusterGenAugsburg")

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH   = os.path.join(BASE_DIR, "data", "osm", "schwaben-latest.osm.pbf")
AUGSBURG_BBOX = (10.7633615, 48.2581444, 10.9593328, 48.4586541)   # lon_min, lat_min, lon_max, lat_max
AUGSBURG_BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "augsburg_admin_boundary.geojson")

# All building tags we consider residential
RESIDENTIAL_BUILDING_TAGS = {
    "yes",
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
    Extracts buildings with addr:street from PBF, filtered to Augsburg bbox.
    """
    def __init__(self, bbox, polygon):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.bbox = bbox         # (lon_min, lat_min, lon_max, lat_max)
        self.polygon = polygon   # Augsburg boundary polygon for precise PiP check

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

        # Precise boundary polygon check (Augsburg boundary)
        if self.polygon and not _point_in_polygon(c_lat, c_lon, self.polygon):
            return

        self.buildings.append({
            "street":      street,
            "housenumber": tags.get("addr:housenumber", ""),
            "plz":         tags.get("addr:postcode", "UNKNOWN"),
            "building":    building_tag,
            "lat":         c_lat,
            "lon":         c_lon,
        })


def sort_housenumber(s):
    m = re.search(r"\d+", str(s))
    return int(m.group()) if m else 99999


def main():
    logger.info("=== Augsburg Cluster Generation ===")
    logger.info(f"PBF: {PBF_PATH}")

    if not os.path.exists(PBF_PATH):
        logger.error(f"PBF not found: {PBF_PATH}")
        sys.exit(1)

    # Load Augsburg boundary polygon
    polygon = _load_polygon(AUGSBURG_BOUNDARY_PATH)
    if not polygon:
        logger.error(f"Failed to load Augsburg boundary polygon at {AUGSBURG_BOUNDARY_PATH}.")
        sys.exit(1)

    # Extract buildings from PBF
    logger.info("Extracting residential buildings from PBF (Augsburg bbox + boundary)...")
    handler = _BuildingExtractorV2(bbox=AUGSBURG_BBOX, polygon=polygon)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")
    buildings = handler.buildings

    logger.info(f"Extracted {len(buildings)} buildings with addr:street inside Augsburg boundary.")

    # --- Tag breakdown (diagnostic) ---
    from collections import Counter
    tag_counts = Counter(b["building"] for b in buildings)
    logger.info("Building tag breakdown:")
    for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {tag:<25} {cnt:>5}")

    # --- Real PLZ breakdown (diagnostic — this IS the authoritative PLZ list,
    # derived from actual tagged buildings, not a guess) ---
    plz_counts = Counter(b["plz"] for b in buildings)
    logger.info("PLZ breakdown (real, from tagged buildings):")
    for plz, cnt in sorted(plz_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {plz:<10} {cnt:>6}")

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
        seg_id = f"AUGSBURG_OSM_{plz_clean}" if data["plz"] != "UNKNOWN" else "AUGSBURG_OSM_GENERAL"
        A_count = max(1, int(count * 0.4))
        B_count = count - A_count

        out_clusters.append({
            "cluster_id":            f"A_{c_idx:03d}",
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
            "_v2_generated_at":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "_v2_buildings_in_pbf":  count,
            "_v2_housenumber_coverage": round(len(hns) / count, 3) if count else 0.0,
        })
        c_idx += 1

    logger.info(f"Skipped {skipped_small} street+PLZ groups with < 3 buildings.")
    logger.info(f"Generated {len(out_clusters)} clusters.")

    # --- Save ---
    out_path = os.path.join(BASE_DIR, "output", "clusters", "augsburg_hybrid_clusters_v1.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_clusters, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved: {out_path}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
