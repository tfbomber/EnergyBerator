import os
import sys
import pandas as pd
from shapely.geometry import Polygon
import osmium

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.boundary_filter import _load_polygon, _point_in_polygon
from core.plz_lookup import PlzLookup

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH   = os.path.join(BASE_DIR, "data", "osm", "schwaben-latest.osm.pbf")
AUGSBURG_BBOX = (10.7633615, 48.2581444, 10.9593328, 48.4586541)
AUGSBURG_BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "augsburg_admin_boundary.geojson")

# Augsburg's real PLZ set, confirmed from actually-tagged buildings in this
# same PBF (see generate_augsburg_osm_clusters.py run log) — used only to
# decide whether a stray edge-of-boundary postal_code (a neighboring
# municipality's PLZ that happens to fall inside the bbox/polygon edge, e.g.
# 86316/86356/86391) should still be trusted as-is or bucketed as GENERAL.
# Unlike Kaarst (single PLZ, single hardcoded segment_id), Augsburg has 14
# PLZs, so segment_id must be derived PER BUILDING from its own postal_code.
KNOWN_AUGSBURG_PLZ = {
    "86150", "86152", "86153", "86154", "86156", "86157", "86159",
    "86161", "86163", "86165", "86167", "86169", "86179", "86199",
}

RESIDENTIAL_BUILDING_TAGS = {
    "yes", "residential", "house", "apartments", "detached",
    "semidetached_house", "terrace", "multi_family", "dormitory", "rowhouse"
}

class AugsburgBuildingExtractor(osmium.SimpleHandler):
    """PLZ assignment (spatial-PLZ P3, 2026-07-14, extends
    .ai/implementation_plan_leipzig_plz_spatial.md to Augsburg): a tagged
    addr:postcode in KNOWN_AUGSBURG_PLZ is trusted as-is (fast path). A
    missing/foreign tag gets a point-in-polygon lookup against the 14 real
    Augsburg PLZ boundary polygons before falling back to GENERAL."""

    def __init__(self, bbox, polygon, plz_lookup):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.bbox = bbox
        self.polygon = polygon
        self.plz_lookup = plz_lookup
        self.n_spatial_recovered = 0
        self.n_still_general = 0

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

        postal_code_raw = tags.get("addr:postcode", "")
        if postal_code_raw in KNOWN_AUGSBURG_PLZ:
            # Fast path — tagged buildings are never touched by the spatial
            # fallback.
            postal_code = postal_code_raw
            segment_id = f"AUGSBURG_OSM_{postal_code}"
        else:
            spatial_plz = self.plz_lookup.lookup(c_lon, c_lat)
            if spatial_plz is not None:
                postal_code = spatial_plz
                segment_id = f"AUGSBURG_OSM_{spatial_plz}"
                self.n_spatial_recovered += 1
            else:
                # Genuinely outside all 14 known Augsburg PLZ polygons — a
                # stray neighboring-municipality/noise building that leaked
                # through the boundary polygon edge.
                postal_code = ""
                segment_id = "AUGSBURG_OSM_GENERAL"
                self.n_still_general += 1

        self.buildings.append({
            "building_id": f"OSM_{w.id}",
            "segment_id": segment_id,
            "geometry": geom_wkt,
            "building_type": building_tag,
            "city": "Augsburg",
            "street": street,
            "house_number": tags.get("addr:housenumber", ""),
            "postal_code": postal_code,
            "neighbors": []
        })

def main():
    print("Loading Augsburg boundary...")
    polygon = _load_polygon(AUGSBURG_BOUNDARY_PATH)

    print("Loading 14 Augsburg PLZ boundary polygons for spatial fallback...")
    plz_lookup = PlzLookup(
        os.path.join(BASE_DIR, "config", "boundaries", "augsburg_plz_boundaries.geojson"),
        expected_count=14,
    )

    print("Extracting buildings (tag-first + spatial PLZ fallback)...")
    handler = AugsburgBuildingExtractor(bbox=AUGSBURG_BBOX, polygon=polygon, plz_lookup=plz_lookup)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")

    print(f"Extracted {len(handler.buildings)} buildings.")
    print(f"Spatially recovered (untagged, PiP-matched): {handler.n_spatial_recovered}")
    print(f"Still GENERAL (untagged, outside all 14 PLZ polygons): {handler.n_still_general}")
    df = pd.DataFrame(handler.buildings)

    print("segment_id breakdown:")
    print(df["segment_id"].value_counts())

    out_path = os.path.join(BASE_DIR, "data", "augsburg_buildings.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Saved to {out_path}")

if __name__ == "__main__":
    main()
