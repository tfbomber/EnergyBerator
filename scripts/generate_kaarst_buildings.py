import os
import sys
import pandas as pd
from shapely.geometry import Polygon
import osmium

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.boundary_filter import _load_polygon, _point_in_polygon

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH   = os.path.join(BASE_DIR, "data", "osm", "duesseldorf-regbez-latest.osm.pbf")
KAARST_BBOX = (6.55, 51.19, 6.68, 51.27)
KAARST_BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "kaarst_admin_boundary.geojson")

RESIDENTIAL_BUILDING_TAGS = {
    "yes", "residential", "house", "apartments", "detached",
    "semidetached_house", "terrace", "multi_family", "dormitory", "rowhouse"
}

class KaarstBuildingExtractor(osmium.SimpleHandler):
    def __init__(self, bbox, polygon):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.bbox = bbox
        self.polygon = polygon

    def way(self, w):
        tags = w.tags
        street = tags.get("addr:street", "")
        if not street:
            return

        building_tag = tags.get("building", "").lower().strip()
        if building_tag not in RESIDENTIAL_BUILDING_TAGS:
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

        try:
            poly = Polygon(nodes)
            if not poly.is_valid:
                poly = poly.buffer(0)
            geom_wkt = poly.wkt
        except Exception:
            return

        # postal_code: hardcoded like segment_id above, not read from
        # addr:postcode (Kaarst KI-012 promotion, 2026-07-14 — territoryai
        # .ai/implementation_plan_kaarst_ki012_promotion.md). Discovered during
        # execution: this field WAS reading the raw tag, so 636 of 9,949
        # buildings (6.4%, missing addr:postcode entirely) got postal_code=""
        # even though segment_id was already correctly hardcoded — and
        # merge_building_geometry_into_territoryai.py drops any row with a
        # blank postal_code before it ever reaches the map. Same root cause,
        # same fix, as the sibling generate_kaarst_osm_clusters.py bug fixed
        # in this same round: Kaarst has exactly one real PLZ, so a building
        # that already passed the boundary-polygon check above IS Kaarst,
        # regardless of what its own addr:postcode tag says (or doesn't say).
        self.buildings.append({
            "building_id": f"OSM_{w.id}",
            "segment_id": "KAARST_OSM_41564",
            "geometry": geom_wkt,
            "building_type": building_tag,
            "city": "Kaarst",
            "street": street,
            "house_number": tags.get("addr:housenumber", ""),
            "postal_code": "41564",
            "neighbors": []
        })

def main():
    print("Loading Kaarst boundary...")
    polygon = _load_polygon(KAARST_BOUNDARY_PATH)
    
    print("Extracting buildings...")
    handler = KaarstBuildingExtractor(bbox=KAARST_BBOX, polygon=polygon)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")
    
    print(f"Extracted {len(handler.buildings)} buildings.")
    df = pd.DataFrame(handler.buildings)
    
    out_path = os.path.join(BASE_DIR, "data", "kaarst_buildings.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Saved to {out_path}")

if __name__ == "__main__":
    main()
