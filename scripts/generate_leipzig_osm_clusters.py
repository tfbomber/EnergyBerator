"""
generate_leipzig_osm_clusters.py
==================================
Generates the Leipzig cluster feed using the local Sachsen PBF extract.
Adapted from generate_augsburg_osm_clusters.py (itself adapted from
generate_kaarst_osm_clusters.py / generate_neuss_osm_clusters_v2.py).

Also serves as the EXPLORATORY pass to discover Leipzig's real PLZ set from
actually-tagged buildings (same two-step process as Augsburg: this script's
PLZ breakdown log is the ground truth used to hardcode KNOWN_LEIPZIG_PLZ in
generate_leipzig_buildings.py / fetch_leipzig_pvgis_yield.py afterward — not
guessed from a postal-code map).

Clustering logic:
  - Group by (street_name + PLZ)
  - Minimum 3 buildings per cluster
  - house_range = min-to-max housenumber found in that group
  - lead_count = number of buildings in that group

PLZ assignment (KI-012 follow-up, 2026-07-14 — execution-discovered
correction, see .ai/implementation_plan_leipzig_plz_spatial.md "执行期修正"):
this script does its OWN independent PBF pass (separate from
generate_leipzig_buildings.py) and previously bucketed every building
missing addr:postcode straight into plz="UNKNOWN" -> segment_id=
LEIPZIG_OSM_GENERAL, with no spatial fallback. Since Foundation
(generate_foundation_layer.py) parses a cluster's PLZ from THIS script's own
segment_id — not from the buildings parquet — that GENERAL segment_id was
the actual mechanism by which streets like Triftsiedlung/Falterstrasse
vanished from the ranked output (their cluster's plz parsed to "UNKNOWN" and
got dropped by build_leipzig_layer2.py's 34-PLZ filter), independent of
whatever generate_leipzig_buildings.py assigned. Fixed identically here:
tagged addr:postcode in KNOWN_LEIPZIG_PLZ is trusted as-is (fast path); a
missing/foreign tag gets a point-in-polygon lookup via the SAME
LeipzigPlzLookup the other extractor uses, so the two scripts can never
diverge on a building's PLZ.
"""

import os
import sys
import json
import re
import logging
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.boundary_filter import _load_polygon, _point_in_polygon
from core.plz_lookup import LeipzigPlzLookup
import osmium

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")
logger = logging.getLogger("ClusterGenLeipzig")

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH   = os.path.join(BASE_DIR, "data", "osm", "sachsen-latest.osm.pbf")
LEIPZIG_BBOX = (12.2366519, 51.2381704, 12.5424918, 51.4481145)   # lon_min, lat_min, lon_max, lat_max
LEIPZIG_BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "leipzig_admin_boundary.geojson")

# Must match generate_leipzig_buildings.py's KNOWN_LEIPZIG_PLZ exactly — the
# two independent extractors both need identical fast-path/fallback
# behavior (KI-012 follow-up, 2026-07-14, .ai/implementation_plan_leipzig_plz_spatial.md).
KNOWN_LEIPZIG_PLZ = {
    "04103", "04105", "04107", "04109", "04129", "04155", "04157", "04158",
    "04159", "04177", "04178", "04179", "04205", "04207", "04209", "04229",
    "04249", "04275", "04277", "04279", "04288", "04289", "04299", "04315",
    "04316", "04317", "04318", "04319", "04328", "04329", "04347", "04349",
    "04356", "04357",
}

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
    Extracts buildings with addr:street from PBF, filtered to Leipzig bbox.
    """
    def __init__(self, bbox, polygon, plz_lookup):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.bbox = bbox         # (lon_min, lat_min, lon_max, lat_max)
        self.polygon = polygon   # Leipzig boundary polygon for precise PiP check
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

        # Precise boundary polygon check (Leipzig boundary)
        if self.polygon and not _point_in_polygon(c_lat, c_lon, self.polygon):
            return

        postal_code_raw = tags.get("addr:postcode", "")
        if postal_code_raw in KNOWN_LEIPZIG_PLZ:
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
    logger.info("=== Leipzig Cluster Generation ===")
    logger.info(f"PBF: {PBF_PATH}")

    if not os.path.exists(PBF_PATH):
        logger.error(f"PBF not found: {PBF_PATH}")
        sys.exit(1)

    # Load Leipzig boundary polygon
    polygon = _load_polygon(LEIPZIG_BOUNDARY_PATH)
    if not polygon:
        logger.error(f"Failed to load Leipzig boundary polygon at {LEIPZIG_BOUNDARY_PATH}.")
        sys.exit(1)

    logger.info("Loading 34 Leipzig PLZ boundary polygons for spatial fallback...")
    plz_lookup = LeipzigPlzLookup()

    # Extract buildings from PBF
    logger.info("Extracting residential buildings from PBF (Leipzig bbox + boundary)...")
    handler = _BuildingExtractorV2(bbox=LEIPZIG_BBOX, polygon=polygon, plz_lookup=plz_lookup)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")
    buildings = handler.buildings

    logger.info(f"Extracted {len(buildings)} buildings with addr:street inside Leipzig boundary.")
    logger.info(f"Spatially recovered (untagged/foreign-tag, PiP-matched): {handler.n_spatial_recovered}")
    logger.info(f"Still UNKNOWN (outside all 34 PLZ polygons): {handler.n_still_unknown}")

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
        seg_id = f"LEIPZIG_OSM_{plz_clean}" if data["plz"] != "UNKNOWN" else "LEIPZIG_OSM_GENERAL"
        A_count = max(1, int(count * 0.4))
        B_count = count - A_count

        out_clusters.append({
            "cluster_id":            f"L_{c_idx:03d}",
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
    out_path = os.path.join(BASE_DIR, "output", "clusters", "leipzig_hybrid_clusters_v1.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_clusters, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved: {out_path}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
