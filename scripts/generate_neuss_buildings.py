"""
generate_neuss_buildings.py
==============================
Unified direct-PBF building extractor for all 8 real Neuss PLZ, replacing
the prior two-source architecture:
  - build_neuss_buildings_from_geojson.py (7 PLZ from a static 2026-03-15
    Overpass geojson snapshot) + build_neuss_buildings_final.py (PLZ 41470
    recovered separately from legacy POINT-geometry data) + swap_neuss_
    buildings.py.
  - The interim extract_neuss_41470_polygons.py / swap_neuss_41470_polygons.py
    (2026-07-14, D6 fix for 41470's POINT geometry only).

Why replace both, not just patch 41470 (Neuss Foundation KI-012 promotion,
territoryai .ai/implementation_plan_neuss_foundation_ki012.md): after fixing
41470 alone and promoting Neuss into _FIELD02_VALIDATED_CITIES, discovered
the 2026-03-15 geojson snapshot underlying the OTHER 7 PLZ has its own,
much bigger coverage gap relative to the live PBF — 138 real Neuss streets
(4,067 buildings, 72 of them currently PASS/QUALIFIED under the legacy
path) are entirely ABSENT from buildings.parquet, producing hollow
zero-count Foundation records once promoted (e.g. Weststraße, PLZ 41472,
91.3% SFH / PASS under legacy, silently zeroed out under the geojson-gap
data). A snapshot from one point in time will always eventually drift from
what a live PBF pull captures; the fix mirrors Leipzig/Augsburg's own
buildings extraction architecture (direct PBF pass, not an intermediate
static export) rather than patching the geojson-gap symptom twice.

PLZ assignment: tag-first if addr:postcode is a real Neuss PLZ (fast path);
spatial point-in-polygon fallback via core.plz_lookup.PlzLookup +
config/boundaries/neuss_plz_boundaries.geojson (built for the 2026-07-14
spatial-PLZ P3) for untagged/foreign-tag buildings — same pattern as
Leipzig/Augsburg/the 41470-only interim fix.

building_type vocabulary: kept identical to Neuss's existing historical
convention (_map_building_tag: detached/semi/rowhouse/apartment/unknown),
NOT switched to Leipzig/Augsburg's raw-OSM-tag convention — field_02's
Stage 1 explicit-tag sets already recognize both vocabularies (its own
docstring notes "normalised values ... are included"), so there is no
correctness reason to change it, and keeping it avoids an unnecessary
schema-convention change for a file other code may already assume the
shape of.

Output: data/neuss_buildings_v2.parquet (all 8 PLZ). Swapped into
data/buildings.parquet by swap_neuss_buildings_v2.py, replacing the 8
NEUSS_PLZ* segments and preserving the 5 non-8-PLZ pilot segments (931
rows: ALLERHEILIGEN_PILOT_SEG_01, NEUSS_DENSE_01, NEUSS_OLD_TOWN_01,
NEUSS_SUBURBAN_01, NEUSS_VILLA_01) untouched.
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
# Padded to fully cover neuss_admin_boundary.geojson's true extent (lon 6.6148-6.7984,
# lat 51.1168-51.2356) — the old (6.61, 51.13, 6.77, 51.25) bbox used elsewhere in this
# repo silently cut off PLZ 41468's eastern/southern edge (discovered 2026-07-14: 36
# entire streets + small per-street undercounts, e.g. Koblenzer Straße at lon 6.781
# fell just outside lon_max=6.77). The city boundary polygon check right after this bbox
# remains the authoritative filter, so widening only removes false negatives.
NEUSS_BBOX = (6.60, 51.10, 6.81, 51.25)
NEUSS_BOUNDARY_PATH = os.path.join(BASE_DIR, "config", "boundaries", "neuss_admin_boundary.geojson")
NEUSS_PLZ_BOUNDARIES_PATH = os.path.join(BASE_DIR, "config", "boundaries", "neuss_plz_boundaries.geojson")

KNOWN_NEUSS_PLZ = {
    "41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472",
}

RESIDENTIAL_BUILDING_TAGS = {
    "yes", "residential", "house", "apartments", "detached",
    "semidetached_house", "terrace", "multi_family", "dormitory", "rowhouse",
}

GEOMETRY_SOURCE = "OSM_PBF_POLYGON_2026-07-14"


def _map_building_tag(tag: str) -> str:
    """Identical mapping to build_neuss_buildings_from_geojson.py's
    _map_building_tag, kept for schema/vocabulary consistency."""
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


class _NeussBuildingExtractor(osmium.SimpleHandler):
    def __init__(self, bbox, city_polygon, plz_lookup):
        osmium.SimpleHandler.__init__(self)
        self.buildings = []
        self.bbox = bbox
        self.city_polygon = city_polygon
        self.plz_lookup = plz_lookup
        self.n_spatial_recovered = 0
        self.n_still_general = 0

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
                postal_code = ""
                self.n_still_general += 1
                return  # true noise — outside all 8 known Neuss PLZ polygons

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
            "segment_id": f"NEUSS_PLZ{postal_code}",
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

    print(f"Extracting all 8 Neuss PLZ buildings from {PBF_PATH} "
          f"(residential + addr:street, tag-first + spatial PLZ fallback)...")
    handler = _NeussBuildingExtractor(bbox=NEUSS_BBOX, city_polygon=city_polygon, plz_lookup=plz_lookup)
    handler.apply_file(PBF_PATH, locations=True, idx="flex_mem")

    print(f"Extracted {len(handler.buildings)} residential buildings.")
    print(f"Spatially recovered (untagged/foreign-tag, PiP-matched): {handler.n_spatial_recovered}")
    print(f"Discarded (outside all 8 PLZ polygons): {handler.n_still_general}")

    df = pd.DataFrame(handler.buildings)
    dup = int(df["building_id"].duplicated().sum())
    print(f"Duplicate building_id: {dup}")
    if dup:
        df = df.drop_duplicates(subset=["building_id"], keep="first")
        print(f"Dropped duplicates -> {len(df)} rows")

    print("segment_id breakdown:")
    print(df["segment_id"].value_counts().sort_index().to_string())

    out_path = os.path.join(BASE_DIR, "data", "neuss_buildings_v2.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")


if __name__ == "__main__":
    main()
