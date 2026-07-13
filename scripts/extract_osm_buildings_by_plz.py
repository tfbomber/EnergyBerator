"""
extract_osm_buildings_by_plz.py
================================
Layer 2 Expansion — Step 2: Real OSM Building Extraction

Fetches residential building ways from the Overpass API for specific
Neuss PLZ codes, assigns them to Layer 2 expansion segments, and appends
real-grounded rows to buildings.parquet.

Target segments (expansion round 1):
    NEUSS_PLZ41472   ← PLZ 41472  (confirmed: 63 foundation clusters, 81% PASS)
    NEUSS_PLZ41464    ← PLZ 41464  (confirmed: 107 foundation clusters, 51% PASS)

Guardrails:
    - Only building ways with addr:postcode matching target PLZ are kept
    - City tag must be "Neuss" (or empty — OSM tags are incomplete) 
    - Duplicate building_ids with existing buildings.parquet are skipped
    - Synthetic rows (segment_id in existing data without geometry_source) are NOT deleted
    - New rows are appended with geometry_source=OSM

Output:
    data/buildings.parquet   (appended, not overwritten)
    output/layer2/expansion_extract_<ts>.json  (audit trail)

================================================================================
DEPRECATED — 2026-07-11. DO NOT RUN THIS SCRIPT. Use
`build_neuss_buildings_from_geojson.py` (+ `build_neuss_buildings_final.py`) instead.
================================================================================
Confirmed root cause (see docs/neuss_buildings_duplicate_building_id_root_cause.md):
this script has THREE compounding defects that together corrupted `buildings.parquet`
for Neuss (27,681 rows written, only 18,559 unique building_id):

  1. Whole-city bounding boxes for 4 of 8 PLZ. `PLZ_BBOX` (below) gives PLZ 41462,
     41466, 41468, and 41469 the SAME oversized box covering the entire city, while
     the other PLZ get tight neighborhood boxes. Each Overpass query for those four
     PLZ therefore returns the same city-wide set of ways.
  2. Fabricated `postal_code` for address-less buildings. `elements_to_rows` keeps a
     building with NO `addr:postcode` tag and stamps it with the query's TARGET PLZ
     rather than skipping it or routing it to a general/unknown bucket. Every
     address-less way returned by the city-wide query above is therefore kept and
     mislabeled once per PLZ that queried for it.
  3. No cross-PLZ dedup within a single run. `deduplicate_against_existing` only
     removes building_ids already present in the pre-run `buildings.parquet`
     snapshot; it never dedupes across PLZ within the same run, and all PLZ's rows
     are concatenated at the end. The same address-less building extracted under
     41462 and again under 41466 survives both times.

  Net effect: every address-less building in the whole-city box was cloned into
  4-5 different PLZ segments, each with a fabricated postal_code equal to that
  segment's PLZ — 12,157 duplicated rows across 3,035 distinct building_ids.

The replacement (`build_neuss_buildings_from_geojson.py`, modeled on the proven-good
`generate_augsburg_buildings.py`) fixes all three: single pass over one pre-fetched
geojson snapshot (duplication structurally impossible), REQUIRES a real
`addr:street` + `addr:postcode` on every kept feature (never fabricates), and adds a
mandatory point-in-polygon boundary filter. It lifted the Neuss building-weighted
street-match rate from 58.7% to ~87-88%. See
`.ai/implementation_plan_neuss_fix.md` (territoryai repo) for the full writeup.

This script is kept for historical reference only and is NOT deleted. Do not run it
against `data/buildings.parquet` again — it will reintroduce the duplicate/fabricated
data this fix removed.
"""

import json
import logging
import os
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

warnings.warn(
    "extract_osm_buildings_by_plz.py is DEPRECATED (2026-07-11) and known to "
    "corrupt data/buildings.parquet for Neuss: it uses whole-city bounding boxes "
    "for 4 of 8 PLZ, fabricates postal_code for address-less buildings, and never "
    "dedupes across PLZ within a single run, producing duplicate building_id rows "
    "with fabricated postal codes. Use build_neuss_buildings_from_geojson.py + "
    "build_neuss_buildings_final.py instead. See "
    "docs/neuss_buildings_duplicate_building_id_root_cause.md for the full root-cause "
    "analysis. This warning fires at import time — running this script's main() will "
    "reintroduce the bug it documents.",
    category=DeprecationWarning,
    stacklevel=2,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("OSM_EXPAND")

BASE_DIR      = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILDINGS_OUT = BASE_DIR / "data" / "buildings.parquet"
AUDIT_DIR     = BASE_DIR / "output" / "layer2"
OVERPASS_URL  = "https://overpass.kumi.systems/api/interpreter"

# PLZ → segment mapping (expansion round 1)
# Cross-checked with foundation JSON PLZ coverage
PLZ_TO_SEGMENT = {
    "41472": "NEUSS_PLZ41472",    # Holzheim / Grefrath
    "41464": "NEUSS_PLZ41464",    # Pomona / Westfeld
    "41460": "NEUSS_PLZ41460",
    "41462": "NEUSS_PLZ41462",
    "41466": "NEUSS_PLZ41466",
    "41468": "NEUSS_PLZ41468",
    "41469": "NEUSS_PLZ41469",
    "41470": "NEUSS_PLZ41470",    # Allerheiligen / Rosellen — added 2026-04-12
}

# Tight bounding boxes per PLZ (south,west,north,east)
# Derived from standard German PLZ geography for Neuss area.
# deliberately conservative (slightly over-inclusive) — city+PLZ tag filter
# acts as secondary verification inside fetch function.
PLZ_BBOX = {
    "41472": (51.140, 6.650, 51.180, 6.730),   # Holzheim / Grefrath
    "41464": (51.145, 6.680, 51.180, 6.760),   # Pomona / Westfeld
    "41460": (51.180, 6.660, 51.220, 6.720),
    "41462": (51.100, 6.600, 51.250, 6.800),
    "41466": (51.100, 6.600, 51.250, 6.800),
    "41468": (51.100, 6.600, 51.250, 6.800),
    "41469": (51.100, 6.600, 51.250, 6.800),
    "41470": (51.125, 6.620, 51.165, 6.700),   # Allerheiligen / Rosellen (south-west Neuss)
}

OVERPASS_TIMEOUT = 90   # seconds — increased from 60


def fetch_osm_buildings_for_plz(plz: str) -> list[dict]:
    """
    Queries Overpass API for residential buildings within the PLZ bounding box,
    then second-filters by addr:postcode tag or city=Neuss.
    Bbox query is much faster than PLZ tag filter on the public API.
    """
    bbox = PLZ_BBOX.get(plz)
    if not bbox:
        logger.warning(f"[OSM] No bbox defined for PLZ={plz}, skipping")
        return []

    s, w, n, e = bbox
    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT}];
(
  way["building"~"residential|house|apartments|detached|semi|terrace"]({s},{w},{n},{e});
);
out center tags;
"""
    logger.info(f"[OSM] Querying Overpass for PLZ={plz} bbox={bbox}...")
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=OVERPASS_TIMEOUT + 15)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        logger.info(f"[OSM] PLZ={plz}: {len(elements)} ways returned from bbox query")
        return elements
    except Exception as e:
        logger.error(f"[OSM] Overpass query failed for PLZ={plz}: {e}")
        return []


def elements_to_rows(elements: list[dict], segment_id: str, plz: str) -> list[dict]:
    """
    Converts Overpass way elements to buildings.parquet-compatible row dicts.
    Only keeps elements that have center coords (geometry available).
    """
    rows = []
    skipped_no_center = 0
    skipped_wrong_city = 0

    for el in elements:
        center = el.get("center")
        if not center:
            skipped_no_center += 1
            continue

        tags = el.get("tags", {})
        city = tags.get("addr:city", "")
        postal_code = tags.get("addr:postcode", "")

        # City filter: if city tag exists and is explicitly not Neuss, skip
        if city and city.strip().lower() not in ("neuss", ""):
            skipped_wrong_city += 1
            continue

        # PLZ secondary filter: if postcode tag exists but doesn't match, skip
        # Buildings with NO postcode tag are kept (common in OSM)
        if postal_code and postal_code.strip() != plz:
            skipped_wrong_city += 1
            logger.debug(f"[OSM] Skipping osm_id={el['id']}: postcode='{postal_code}' != '{plz}'")
            continue

        # Use plz as fallback if no postcode tag
        if not postal_code:
            postal_code = plz

        lat          = center["lat"]
        lon          = center["lon"]
        street       = tags.get("addr:street", "")
        housenumber  = tags.get("addr:housenumber", "")
        building_tag = tags.get("building", "house")

        # Derive a simple WKT point for geometry (centre point used)
        # Full polygon WKT would require fetching way nodes — too heavy for MVP
        geometry_wkt = f"POINT ({lon} {lat})"

        rows.append({
            "building_id":   f"OSM_{el['id']}",
            "segment_id":    segment_id,
            "geometry":      geometry_wkt,
            "neighbors":     None,
            "city":          city or "Neuss",
            "street":        street,
            "house_number":  housenumber,
            "postal_code":   postal_code,
            "lat":           lat,
            "lon":           lon,
            "building_type": _map_building_tag(building_tag),
            "geometry_source":        "OSM",
            "address_source":         "OSM",
            "building_type_source":   "OSM",
            "building_type_confidence": "MEDIUM",
        })

    logger.info(
        f"[OSM] PLZ={plz} → {len(rows)} valid rows "
        f"(skipped: no_center={skipped_no_center}, wrong_city={skipped_wrong_city})"
    )
    return rows


def _map_building_tag(tag: str) -> str:
    """Maps OSM building tag to field_02 compatible building_type label."""
    tag = tag.lower()
    if tag in ("house", "detached"):
        return "detached"
    if tag in ("semi", "semi_detached"):
        return "semi"
    if tag in ("residential", "terrace"):
        return "rowhouse"
    if tag in ("apartments", "apartment"):
        return "apartment"
    return "unknown"


def deduplicate_against_existing(
    new_rows: list[dict],
    existing: pd.DataFrame,
) -> list[dict]:
    """Remove any OSM IDs already present in the existing parquet."""
    if existing.empty:
        return new_rows
    existing_ids = set(existing["building_id"].tolist())
    before = len(new_rows)
    filtered = [r for r in new_rows if r["building_id"] not in existing_ids]
    logger.info(f"[DEDUP] {before} rows → {len(filtered)} after removing {before - len(filtered)} duplicates")
    return filtered


def main():
    logger.info("=" * 60)
    logger.info("  OSM BUILDING EXTRACTOR — LAYER 2 EXPANSION")
    logger.info("=" * 60)

    # Load existing buildings.parquet
    existing_df = pd.DataFrame()
    if BUILDINGS_OUT.exists():
        existing_df = pd.read_parquet(BUILDINGS_OUT)
        logger.info(f"[LOAD] Existing buildings.parquet: {len(existing_df)} rows, "
                    f"segments={existing_df['segment_id'].unique().tolist()}")
    else:
        logger.warning("[LOAD] buildings.parquet not found — will create fresh")

    audit = {
        "run_timestamp_utc":  datetime.now(timezone.utc).isoformat(),
        "target_plz_segments": PLZ_TO_SEGMENT,
        "extractions":         [],
        "total_new_rows":      0,
    }

    all_new_rows = []

    # 2026-04-12: targeted run — PLZ 41470 only (others already complete)
    TARGET_PLZ = {"41470": PLZ_TO_SEGMENT["41470"]}

    for plz, segment_id in TARGET_PLZ.items():
        logger.info(f"\n[PLZ={plz}] -> segment={segment_id}")

        # Overpass fetch
        elements = fetch_osm_buildings_for_plz(plz)
        rows = elements_to_rows(elements, segment_id, plz)
        rows = deduplicate_against_existing(rows, existing_df)

        audit["extractions"].append({
            "plz":            plz,
            "segment_id":     segment_id,
            "overpass_count": len(elements),
            "valid_rows":     len(rows),
        })
        all_new_rows.extend(rows)

        # Brief pause between requests to not overload Overpass
        time.sleep(2)

    audit["total_new_rows"] = len(all_new_rows)
    logger.info(f"\n[TOTAL] {len(all_new_rows)} new building rows extracted across {len(PLZ_TO_SEGMENT)} PLZs")

    if not all_new_rows:
        logger.warning("[OUTPUT] No new rows to append — buildings.parquet unchanged")
    else:
        new_df = pd.DataFrame(all_new_rows)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined.to_parquet(BUILDINGS_OUT, index=False)
        logger.info(f"[OUTPUT] buildings.parquet updated: {len(combined)} total rows "
                    f"(was {len(existing_df)}, +{len(all_new_rows)})")

        # Console summary
        print(f"\n{'='*60}")
        print("  NEW BUILDINGS BY SEGMENT")
        print(f"{'='*60}")
        print(new_df.groupby("segment_id").size().to_string())
        print(f"\nbuildings.parquet: {len(combined)} total rows")

    # Emit audit JSON
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_path = AUDIT_DIR / f"expansion_extract_{ts}.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    logger.info(f"[AUDIT] → {audit_path}")
    logger.info("=" * 60)
    logger.info("  DONE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
