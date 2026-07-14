"""
build_leipzig_plz_boundaries.py
=================================
Prep script (D3=a, .ai/implementation_plan_leipzig_plz_spatial.md Step 1):
pre-extracts Leipzig's 34 PLZ boundary polygons from the local
data/osm/sachsen-latest.osm.pbf `boundary=postal_code` relations, once,
into a committed config/boundaries/leipzig_plz_boundaries.geojson —
mirroring the existing leipzig_admin_boundary.geojson.

Verified interactively before writing this script (2026-07-14): pyosmium's
modern FileProcessor(...).with_areas() + osmium.geom.WKTFactory finds all
34/34 target PLZ as boundary=postal_code area relations in a single pass
(~140s), zero assembly errors. No osmium CLI needed.

Consumed downstream by:
  - generate_leipzig_buildings.py (spatial PLZ fallback for untagged buildings)
  - generate_leipzig_osm_clusters.py (same fallback, second independent
    extractor — see implementation_plan's "execution-discovered correction")
"""

import json
import os
import time

import osmium
import osmium.geom as geom
from shapely import wkt as shapely_wkt
from shapely.geometry import mapping

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PBF_PATH = os.path.join(BASE_DIR, "data", "osm", "sachsen-latest.osm.pbf")
OUT_PATH = os.path.join(BASE_DIR, "config", "boundaries", "leipzig_plz_boundaries.geojson")

KNOWN_LEIPZIG_PLZ = {
    "04103", "04105", "04107", "04109", "04129", "04155", "04157", "04158",
    "04159", "04177", "04178", "04179", "04205", "04207", "04209", "04229",
    "04249", "04275", "04277", "04279", "04288", "04289", "04299", "04315",
    "04316", "04317", "04318", "04319", "04328", "04329", "04347", "04349",
    "04356", "04357",
}


def main():
    print(f"Scanning {PBF_PATH} for boundary=postal_code relations "
          f"(34 known Leipzig PLZ)...")
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
        if plz not in KNOWN_LEIPZIG_PLZ or plz in found:
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
    print(f"Found {len(found)}/{len(KNOWN_LEIPZIG_PLZ)} known Leipzig PLZ.")
    missing = KNOWN_LEIPZIG_PLZ - set(found.keys())
    if missing:
        print(f"WARNING — missing PLZ boundaries (no boundary=postal_code "
              f"relation found): {sorted(missing)}")
    if errors:
        print(f"WARNING — {len(errors)} PLZ failed polygon assembly: {errors}")

    if len(found) < len(KNOWN_LEIPZIG_PLZ):
        print("ABORTING WRITE — coverage is not 34/34. Investigate before "
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
                    "Extracted from data/osm/sachsen-latest.osm.pbf "
                    "boundary=postal_code relation via pyosmium "
                    "FileProcessor.with_areas() (2026-07-14). Used by "
                    "generate_leipzig_buildings.py / "
                    "generate_leipzig_osm_clusters.py for spatial PLZ "
                    "fallback on untagged buildings (KI-012 follow-up, "
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
