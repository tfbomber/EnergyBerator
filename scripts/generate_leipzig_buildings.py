import json
import os
import sys
import pandas as pd
from shapely.geometry import Polygon
import osmium

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.boundary_filter import _load_polygon, _point_in_polygon

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH   = os.path.join(BASE_DIR, "data", "osm", "sachsen-latest.osm.pbf")
LEIPZIG_BBOX = (12.2366519, 51.2381704, 12.5424918, 51.4481145)
LEIPZIG_BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "leipzig_admin_boundary.geojson")

# Leipzig's real PLZ set, confirmed from actually-tagged buildings (see
# generate_leipzig_osm_clusters.py run log, 2026-07-13). One additional PLZ
# (04195) appeared with exactly 1 building — treated as boundary-edge noise
# / mistagging, same disposition as Augsburg's 86316/86356/86391 (<20
# buildings each) — excluded from the known set below. Unlike Kaarst (single
# PLZ, single hardcoded segment_id), Leipzig has 34 PLZs, so segment_id must
# be derived PER BUILDING from its own postal_code.
KNOWN_LEIPZIG_PLZ = {
    "04103", "04105", "04107", "04109", "04129", "04155", "04157", "04158",
    "04159", "04177", "04178", "04179", "04205", "04207", "04209", "04229",
    "04249", "04275", "04277", "04279", "04288", "04289", "04299", "04315",
    "04316", "04317", "04318", "04319", "04328", "04329", "04347", "04349",
    "04356", "04357",
}

RESIDENTIAL_BUILDING_TAGS = {
    "yes", "residential", "house", "apartments", "detached",
    "semidetached_house", "terrace", "multi_family", "dormitory", "rowhouse"
}


class LeipzigBuildingExtractor(osmium.SimpleHandler):
    """Single-pass extractor: collects (a) residential buildings with
    addr:street (the parquet consumed everywhere downstream) AND (b) a count
    of ALL building=* ways with a recognized addr:postcode tag regardless of
    building type/addr:street (the plz_buildings denominator field_04 needs
    for PV-adoption-intensity normalization) — avoids parsing the 253MB PBF
    twice, unlike Augsburg's apparent two-separate-script approach."""

    def __init__(self, bbox, polygon):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.plz_building_counts = {}  # ALL building=* with addr:postcode, any type
        self.bbox = bbox
        self.polygon = polygon

    def way(self, w):
        tags = w.tags
        building_tag_raw = tags.get("building", "")
        if not building_tag_raw:
            return

        nodes = [(n.location.lon, n.location.lat) for n in w.nodes if n.location.valid()]
        if len(nodes) < 3:
            return

        c_lon = sum(x for x, _ in nodes) / len(nodes)
        c_lat = sum(y for _, y in nodes) / len(nodes)

        lon_min, lat_min, lon_max, lat_max = self.bbox
        if not (lat_min <= c_lat <= lat_max and lon_min <= c_lon <= lon_max):
            return
        if self.polygon and not _point_in_polygon(c_lat, c_lon, self.polygon):
            return

        postal_code = tags.get("addr:postcode", "")

        # (b) broad plz_buildings denominator — any building=* type, any
        # addr:street presence, just needs a recognized Leipzig postal code.
        if postal_code in KNOWN_LEIPZIG_PLZ:
            self.plz_building_counts[postal_code] = self.plz_building_counts.get(postal_code, 0) + 1

        # (a) residential-only, addr:street-required — the parquet.
        street = tags.get("addr:street", "")
        if not street:
            return
        building_tag = building_tag_raw.lower().strip()
        if building_tag not in RESIDENTIAL_BUILDING_TAGS:
            return

        try:
            poly = Polygon(nodes)
            if not poly.is_valid:
                poly = poly.buffer(0)
            geom_wkt = poly.wkt
        except Exception:
            return

        if postal_code in KNOWN_LEIPZIG_PLZ:
            segment_id = f"LEIPZIG_OSM_{postal_code}"
        else:
            # Untagged, or a stray neighboring-municipality/noise PLZ (e.g.
            # 04195, 1 building) that leaked through the boundary polygon
            # edge — bucket generically rather than mint a segment_id for a
            # PLZ we haven't registered anywhere.
            segment_id = "LEIPZIG_OSM_GENERAL"

        self.buildings.append({
            "building_id": f"OSM_{w.id}",
            "segment_id": segment_id,
            "geometry": geom_wkt,
            "building_type": building_tag,
            "city": "Leipzig",
            "street": street,
            "house_number": tags.get("addr:housenumber", ""),
            "postal_code": postal_code,
            "neighbors": []
        })


def main():
    print("Loading Leipzig boundary...")
    polygon = _load_polygon(LEIPZIG_BOUNDARY_PATH)

    print("Extracting buildings (residential parquet + plz_buildings denominator)...")
    handler = LeipzigBuildingExtractor(bbox=LEIPZIG_BBOX, polygon=polygon)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")

    print(f"Extracted {len(handler.buildings)} residential buildings.")
    df = pd.DataFrame(handler.buildings)

    print("segment_id breakdown:")
    print(df["segment_id"].value_counts())

    out_path = os.path.join(BASE_DIR, "data", "leipzig_buildings.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Saved to {out_path}")

    plz_counts_path = os.path.join(BASE_DIR, "data", "leipzig_plz_buildings_denominator.json")
    with open(plz_counts_path, "w", encoding="utf-8") as f:
        json.dump(handler.plz_building_counts, f, indent=2, sort_keys=True)
    print(f"Saved plz_buildings denominator ({len(handler.plz_building_counts)} PLZ) to {plz_counts_path}")


if __name__ == "__main__":
    main()
