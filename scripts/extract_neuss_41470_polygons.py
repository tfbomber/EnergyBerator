"""
extract_neuss_41470_polygons.py
==================================
Targeted fix (Neuss Foundation KI-012 promotion — territoryai
.ai/implementation_plan_neuss_foundation_ki012.md, D6/option A): replaces
PLZ 41470's legacy POINT-geometry recovery (from a 2026-04-12 one-off
Overpass run, `geometry_source=LEGACY_OVERPASS_POINT_41470`) with a real
POLYGON extraction, straight from the local
data/osm/duesseldorf-regbez-latest.osm.pbf — the same source
`build_neuss_buildings_from_geojson.py` uses for the other 7 Neuss PLZ, but
that script's 2026-03-15 geojson snapshot never had 41470 coverage at all
(a source-data gap, not a pipeline bug).

Deliberately surgical (D1 minimal-blast-radius): only extracts and replaces
41470. The other 7 already-POLYGON Neuss PLZ (from
build_neuss_buildings_from_geojson.py) are completely untouched — this
script does not read or write anything about them.

Why this matters: 41470's POINT-only geometry meant field_02's Stage 2
footprint classifier (needs real polygon area) could never run on it —
74.4% of its 1,494 buildings fell back to UNCERTAIN (vs ~3-8% for the
7 POLYGON PLZ), which would have badly diluted 41470's structure_gate
under the KI-012 path. This gives it real polygons so field_02 can
classify it the same way as every other PLZ.

PLZ assignment: tag-first if addr:postcode is a real Neuss PLZ (fast
path — matches the convention already used for Leipzig/Augsburg/Neuss's
other 7 PLZ); spatial point-in-polygon fallback via the same
core/plz_lookup.PlzLookup + config/boundaries/neuss_plz_boundaries.geojson
built for the 2026-07-14 spatial-PLZ P3, for untagged/foreign-tag
buildings. Output is filtered to segment_id == NEUSS_PLZ41470 only —
any building spatially resolving to one of the other 7 PLZ is discarded
here (it's already covered by the geojson-based extraction).
"""

import os
import sys

import pandas as pd
from shapely.geometry import Polygon
import osmium

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.boundary_filter import _load_polygon, _point_in_polygon
from core.plz_lookup import PlzLookup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH = os.path.join(BASE_DIR, "data", "osm", "duesseldorf-regbez-latest.osm.pbf")
NEUSS_BBOX = (6.61, 51.13, 6.77, 51.25)
NEUSS_BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "neuss_admin_boundary.geojson")
NEUSS_PLZ_BOUNDARIES_PATH = os.path.join(BASE_DIR, "config", "boundaries", "neuss_plz_boundaries.geojson")

KNOWN_NEUSS_PLZ = {
    "41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472",
}

RESIDENTIAL_BUILDING_TAGS = {
    "yes", "residential", "house", "apartments", "detached",
    "semidetached_house", "terrace", "multi_family", "dormitory", "rowhouse",
}

GEOMETRY_SOURCE = "OSM_PBF_POLYGON_41470_2026-07"


def _map_building_tag(tag: str) -> str:
    """Identical mapping to build_neuss_buildings_from_geojson.py's
    _map_building_tag, reused so 41470's rows use the same vocabulary."""
    tag = (tag or "").lower()
    if tag in ("house", "detached"):
        return "detached"
    if tag in ("semi", "semi_detached", "semidetached_house"):
        return "semi"
    if tag in ("residential", "terrace", "rowhouse"):
        return "rowhouse"
    if tag in ("apartments", "apartment", "multi_family", "dormitory"):
        return "apartment"
    return "unknown"


class _Neuss41470Extractor(osmium.SimpleHandler):
    def __init__(self, bbox, city_polygon, plz_lookup):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.bbox = bbox
        self.city_polygon = city_polygon
        self.plz_lookup = plz_lookup
        self.n_spatial_recovered = 0
        self.n_discarded_other_plz = 0
        self.n_discarded_unresolvable = 0

    def way(self, w):
        tags = w.tags
        street = tags.get("addr:street", "")
        if not street:
            return

        building_tag_raw = tags.get("building", "").lower().strip()
        if building_tag_raw not in RESIDENTIAL_BUILDING_TAGS:
            return

        nodes = [(n.location.lon, n.location.lat) for n in w.nodes if n.location.valid()]
        if len(nodes) < 3:
            return

        c_lon = sum(x for x, _ in nodes) / len(nodes)
        c_lat = sum(y for _, y in nodes) / len(nodes)

        lon_min, lat_min, lon_max, lat_max = self.bbox
        if not (lat_min <= c_lat <= lat_max and lon_min <= c_lon <= lon_max):
            return
        if self.city_polygon and not _point_in_polygon(c_lat, c_lon, self.city_polygon):
            return

        postal_code_raw = tags.get("addr:postcode", "")
        if postal_code_raw in KNOWN_NEUSS_PLZ:
            postal_code = postal_code_raw
        else:
            spatial_plz = self.plz_lookup.lookup(c_lon, c_lat)
            if spatial_plz is not None:
                postal_code = spatial_plz
                self.n_spatial_recovered += 1
            else:
                self.n_discarded_unresolvable += 1
                return

        if postal_code != "41470":
            self.n_discarded_other_plz += 1
            return

        try:
            poly = Polygon(nodes)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                return
            geom_wkt = poly.wkt
        except Exception:
            return

        self.buildings.append({
            "building_id": f"OSM_{w.id}",
            "segment_id": "NEUSS_PLZ41470",
            "geometry": geom_wkt,
            "neighbors": [],
            "city": "Neuss",
            "street": street,
            "house_number": tags.get("addr:housenumber", ""),
            "postal_code": postal_code,
            "lat": c_lat,
            "lon": c_lon,
            "building_type": _map_building_tag(building_tag_raw),
            "geometry_source": GEOMETRY_SOURCE,
            "address_source": "OSM",
            "building_type_source": "OSM",
            "building_type_confidence": "MEDIUM",
        })


def main():
    print("Loading Neuss city boundary + 8 PLZ polygons...")
    city_polygon = _load_polygon(NEUSS_BOUNDARY_PATH)
    plz_lookup = PlzLookup(NEUSS_PLZ_BOUNDARIES_PATH, expected_count=8)

    print(f"Extracting PLZ 41470 buildings from {PBF_PATH} (residential + addr:street, "
          f"tag-first + spatial PLZ fallback, output filtered to 41470 only)...")
    handler = _Neuss41470Extractor(bbox=NEUSS_BBOX, city_polygon=city_polygon, plz_lookup=plz_lookup)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")

    print(f"Kept (PLZ 41470): {len(handler.buildings)}")
    print(f"Spatially recovered (untagged/foreign-tag, resolved to 41470 among these): "
          f"{handler.n_spatial_recovered}")
    print(f"Discarded (spatially resolved to one of the OTHER 7 Neuss PLZ, already covered "
          f"elsewhere): {handler.n_discarded_other_plz}")
    print(f"Discarded (unresolvable — outside all 8 PLZ polygons): {handler.n_discarded_unresolvable}")

    df = pd.DataFrame(handler.buildings)
    dup = int(df["building_id"].duplicated().sum())
    print(f"Duplicate building_id within this extraction: {dup}")
    if dup:
        df = df.drop_duplicates(subset=["building_id"], keep="first")
        print(f"Dropped duplicates -> {len(df)} rows")

    print("building_type distribution:")
    print(df["building_type"].value_counts().to_string())

    out_path = os.path.join(BASE_DIR, "data", "neuss_41470_polygons.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")


if __name__ == "__main__":
    main()
