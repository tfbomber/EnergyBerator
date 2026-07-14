"""
generate_kaarst_osm_clusters.py
==================================
Generates the Kaarst cluster feed using the local PBF extract.
Adapted from generate_neuss_osm_clusters_v2.py

Clustering logic:
  - Group by (street_name + PLZ)
  - Minimum 3 buildings per cluster
  - house_range = min-to-max housenumber found in that group
  - lead_count = number of buildings in that group

PLZ assignment (Kaarst KI-012 promotion, 2026-07-14 — territoryai
.ai/implementation_plan_kaarst_ki012_promotion.md): this script used to trust
`addr:postcode` directly, unlike `generate_kaarst_buildings.py`'s own
`KaarstBuildingExtractor`, which hardcodes segment_id="KAARST_OSM_41564"
unconditionally once a building passes the real boundary-polygon check
(Kaarst has exactly one real PLZ for this product — there's no multi-PLZ
ambiguity to resolve the way Leipzig/Augsburg/Neuss have). That mismatch put
56 of 494 clusters (600 buildings, 6.1% of all extracted buildings) into
KAARST_OSM_GENERAL — real Kaarst buildings (0% of street-tagged buildings
fall outside the real boundary, confirmed separately), just missing/
foreign-PLZ addr:postcode tags (common OSM address-tagging noise near a town
border). Foundation resolves a cluster's PLZ from the cluster's OWN
segment_id (not buildings.parquet), and `build_kaarst_layer2.py` then hard-
filters to segment plz=="41564" — so these 56 clusters weren't just
downgraded, they were silently dropped from the shipped ranking entirely.
Fixed by mirroring the buildings extractor: once a building passes the
boundary check, assign it plz="41564" unconditionally, the same as that
script already does. No `core/plz_lookup.PlzLookup`-style spatial lookup is
needed here — there's only one possible output PLZ, not several to
disambiguate between.
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
logger = logging.getLogger("ClusterGenKaarst")

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH   = os.path.join(BASE_DIR, "data", "osm", "duesseldorf-regbez-latest.osm.pbf")
KAARST_BBOX = (6.55, 51.19, 6.68, 51.27)   # lon_min, lat_min, lon_max, lat_max
KAARST_BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "kaarst_admin_boundary.geojson")
KAARST_PLZ = "41564"  # the one real PLZ this product tracks for Kaarst

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
    Extracts buildings with addr:street from PBF, filtered to Kaarst bbox.
    """
    def __init__(self, bbox, polygon):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.bbox = bbox         # (lon_min, lat_min, lon_max, lat_max)
        self.polygon = polygon   # Kaarst boundary polygon for precise PiP check

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

        # Precise boundary polygon check (Kaarst boundary)
        if self.polygon and not _point_in_polygon(c_lat, c_lon, self.polygon):
            return

        # PLZ: hardcoded, not read from addr:postcode (see module docstring —
        # Kaarst has exactly one real PLZ; a building's own postcode tag can
        # be missing or carry a neighboring town's code near the border, but
        # having already passed the boundary-polygon check above means it IS
        # a real Kaarst building for this product's purposes).
        self.buildings.append({
            "street":      street,
            "housenumber": tags.get("addr:housenumber", ""),
            "plz":         KAARST_PLZ,
            "building":    building_tag,
            "lat":         c_lat,
            "lon":         c_lon,
        })


def sort_housenumber(s):
    m = re.search(r"\d+", str(s))
    return int(m.group()) if m else 99999


def main():
    logger.info("=== Kaarst Cluster Generation ===")
    logger.info(f"PBF: {PBF_PATH}")

    if not os.path.exists(PBF_PATH):
        logger.error(f"PBF not found: {PBF_PATH}")
        sys.exit(1)

    # Load Kaarst boundary polygon
    polygon = _load_polygon(KAARST_BOUNDARY_PATH)
    if not polygon:
        logger.error(f"Failed to load Kaarst boundary polygon at {KAARST_BOUNDARY_PATH}.")
        sys.exit(1)

    # Extract buildings from PBF
    logger.info("Extracting residential buildings from PBF (Kaarst bbox + boundary)...")
    handler = _BuildingExtractorV2(bbox=KAARST_BBOX, polygon=polygon)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")
    buildings = handler.buildings

    logger.info(f"Extracted {len(buildings)} buildings with addr:street inside Kaarst boundary.")

    # --- Tag breakdown (diagnostic) ---
    from collections import Counter
    tag_counts = Counter(b["building"] for b in buildings)
    logger.info("Building tag breakdown:")
    for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {tag:<25} {cnt:>5}")

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
        seg_id = f"KAARST_OSM_{plz_clean}" if data["plz"] != "UNKNOWN" else "KAARST_OSM_GENERAL"
        A_count = max(1, int(count * 0.4))
        B_count = count - A_count

        out_clusters.append({
            "cluster_id":            f"K_{c_idx:03d}",
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
    out_path = os.path.join(BASE_DIR, "output", "clusters", "kaarst_hybrid_clusters_v1.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_clusters, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved: {out_path}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
