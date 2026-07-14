"""
build_neuss_plz_boundaries.py
================================
Prep script (P3 — extends .ai/implementation_plan_leipzig_plz_spatial.md's
spatial-PLZ-fallback fix to Neuss): pre-extracts Neuss's 8 PLZ boundary
polygons from the local data/osm/duesseldorf-regbez-latest.osm.pbf
`boundary=postal_code` relations, once, into a committed
config/boundaries/neuss_plz_boundaries.geojson.

Verified interactively before writing this script (2026-07-14): the
duesseldorf-regbez PBF has all 8/8 target PLZ as boundary=postal_code area
relations (pyosmium FileProcessor(...).with_areas(), ~2 minutes, zero
assembly errors).
"""

import json
import os
import time

import osmium
import osmium.geom as geom
from shapely import wkt as shapely_wkt
from shapely.geometry import mapping

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH = os.path.join(BASE_DIR, "data", "osm", "duesseldorf-regbez-latest.osm.pbf")
OUT_PATH = os.path.join(BASE_DIR, "config", "boundaries", "neuss_plz_boundaries.geojson")

KNOWN_NEUSS_PLZ = {
    "41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472",
}


def main():
    print(f"Scanning {PBF_PATH} for boundary=postal_code relations "
          f"(8 known Neuss PLZ)...")
    t0 = time.time()

    wkt_factory = geom.WKTFactory()
    found: dict[str, dict] = {}
    errors: list[str] = []

    fp = osmium.FileProcessor(PBF_PATH).with_areas()
    n_areas = 0
    for obj in fp:
        if not obj.is_area():
            continue
        n_areas += 1
        tags = obj.tags
        if tags.get("boundary") != "postal_code":
            continue
        plz = tags.get("postal_code") or tags.get("ref") or tags.get("name")
        if plz not in KNOWN_NEUSS_PLZ or plz in found:
            continue
        try:
            wkt_str = wkt_factory.create_multipolygon(obj)
            geom_obj = shapely_wkt.loads(wkt_str)
            if not geom_obj.is_valid:
                geom_obj = geom_obj.buffer(0)
            found[plz] = {
                "osm_relation_id": obj.orig_id(),
                "geometry": geom_obj,
            }
        except Exception as exc:
            errors.append(f"{plz} (relation {obj.orig_id()}): {exc}")

    elapsed = time.time() - t0
    print(f"Scanned {n_areas} area candidates in {elapsed:.1f}s.")
    print(f"Found {len(found)}/{len(KNOWN_NEUSS_PLZ)} known Neuss PLZ.")
    missing = KNOWN_NEUSS_PLZ - set(found.keys())
    if missing:
        print(f"WARNING — missing PLZ boundaries: {sorted(missing)}")
    if errors:
        print(f"WARNING — {len(errors)} PLZ failed polygon assembly: {errors}")

    if len(found) < len(KNOWN_NEUSS_PLZ):
        print("ABORTING WRITE — coverage is not 8/8. Investigate before "
              "trusting spatial fallback for the missing PLZ(s).")
        return 1

    features = []
    for plz in sorted(found):
        entry = found[plz]
        features.append({
            "type": "Feature",
            "properties": {
                "plz": plz,
                "osm_relation_id": entry["osm_relation_id"],
                "note": (
                    "Extracted from data/osm/duesseldorf-regbez-latest.osm.pbf "
                    "boundary=postal_code relation via pyosmium "
                    "FileProcessor.with_areas() (2026-07-14). Used by "
                    "build_neuss_buildings_from_geojson.py for spatial PLZ "
                    "fallback on untagged buildings (KI-012/spatial-PLZ P3, "
                    ".ai/implementation_plan_leipzig_plz_spatial.md)."
                ),
            },
            "geometry": mapping(entry["geometry"]),
        })

    fc = {"type": "FeatureCollection", "features": features}

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    print(f"Saved {len(features)} PLZ polygons -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
