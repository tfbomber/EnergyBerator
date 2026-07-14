import os
import sys
import pandas as pd
from shapely.geometry import Polygon
import osmium

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.boundary_filter import _load_polygon, _point_in_polygon
from core.plz_lookup import LeipzigPlzLookup

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
    """Single-pass extractor: collects residential buildings with
    addr:street (the parquet consumed everywhere downstream).

    PLZ assignment (KI-012 follow-up, 2026-07-14, D1=a/D2=a/D6 —
    .ai/implementation_plan_leipzig_plz_spatial.md): a tagged addr:postcode
    is trusted as-is (fast path, untouched). A MISSING addr:postcode no
    longer buckets the building into LEIPZIG_OSM_GENERAL unconditionally —
    it first gets a point-in-polygon lookup against the 34 real Leipzig PLZ
    boundary polygons (LeipzigPlzLookup). Only a building that falls outside
    ALL 34 polygons (true noise / genuinely outside Leipzig's PLZ set) stays
    GENERAL. The city-boundary polygon filter below still runs first (D6) —
    unrelated concern, prevents cross-town contamination independent of PLZ
    assignment.

    D4=gamma (2026-07-14): the plz_buildings denominator field_04 uses for
    PV-adoption-intensity normalization is now the RESIDENTIAL building
    count (this parquet's own per-segment row count), not a separate
    all-type-including-non-residential count — so this extractor no longer
    tracks a separate plz_building_counts dict. See run_leipzig_fields.py."""

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

        # Residential-only, addr:street-required — the parquet.
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

        postal_code_raw = tags.get("addr:postcode", "")
        if postal_code_raw in KNOWN_LEIPZIG_PLZ:
            # Fast path (D1=a) — tagged buildings are never touched by the
            # spatial fallback.
            postal_code = postal_code_raw
            segment_id = f"LEIPZIG_OSM_{postal_code}"
        else:
            spatial_plz = self.plz_lookup.lookup(c_lon, c_lat)
            if spatial_plz is not None:
                postal_code = spatial_plz
                segment_id = f"LEIPZIG_OSM_{spatial_plz}"
                self.n_spatial_recovered += 1
            else:
                # Genuinely outside all 34 known Leipzig PLZ polygons — a
                # stray neighboring-municipality/noise building (e.g. 04195,
                # 1 building) that leaked through the boundary polygon edge.
                postal_code = ""
                segment_id = "LEIPZIG_OSM_GENERAL"
                self.n_still_general += 1

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

    print("Loading 34 Leipzig PLZ boundary polygons for spatial fallback...")
    plz_lookup = LeipzigPlzLookup()

    print("Extracting residential buildings (tag-first + spatial PLZ fallback)...")
    handler = LeipzigBuildingExtractor(bbox=LEIPZIG_BBOX, polygon=polygon, plz_lookup=plz_lookup)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")

    print(f"Extracted {len(handler.buildings)} residential buildings.")
    print(f"Spatially recovered (untagged, PiP-matched): {handler.n_spatial_recovered}")
    print(f"Still GENERAL (untagged, outside all 34 PLZ polygons): {handler.n_still_general}")
    df = pd.DataFrame(handler.buildings)

    print("segment_id breakdown:")
    print(df["segment_id"].value_counts())

    out_path = os.path.join(BASE_DIR, "data", "leipzig_buildings.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
