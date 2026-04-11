"""
extract_osm_plz41464_retry.py
==============================
Single-PLZ retry extractor for PLZ 41464 → NEUSS_GRIML_01.

Differences from extract_osm_buildings_by_plz.py:
  - Only PLZ 41464 (NEUSS_GRIML_01)
  - Dual-endpoint fallback: kumi.systems first, then overpass-api.de
  - 10s pre-request cooldown to respect rate limits
  - Tight bbox: (51.130, 6.660, 51.165, 6.720) — Grimlinghausen / Allerheiligen core
  - Same PLZ postcode secondary filter as round-1 extractor
  - Appends to buildings.parquet (deduplicates first)
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("OSM_PLZ41464")

BASE_DIR      = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILDINGS_OUT = BASE_DIR / "data" / "buildings.parquet"
AUDIT_DIR     = BASE_DIR / "output" / "layer2"

PLZ       = "41464"
SEGMENT   = "NEUSS_GRIML_01"
BBOX      = (51.130, 6.660, 51.165, 6.720)   # Grimlinghausen / Allerheiligen core

ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "http://overpass-api.de/api/interpreter",
]
TIMEOUT   = 90   # seconds per attempt


FOOTPRINT_PROXY = {
    "detached":  130.0,
    "semi":       80.0,
    "rowhouse":   60.0,
    "apartment": 200.0,
    "unknown":   100.0,
}
UTILIZATION_FACTORS = {
    "detached":  0.45,
    "semi":      0.40,
    "rowhouse":  0.35,
    "apartment": 0.20,
    "unknown":   0.20,
}


def _map_building_tag(tag: str) -> str:
    tag = tag.lower()
    if tag in ("house", "detached"):   return "detached"
    if tag in ("semi", "semi_detached"): return "semi"
    if tag in ("residential", "terrace"): return "rowhouse"
    if tag in ("apartments", "apartment"): return "apartment"
    return "unknown"


def fetch_elements() -> list[dict]:
    s, w, n, e = BBOX
    query = f"""
[out:json][timeout:{TIMEOUT}];
(
  way["building"~"residential|house|apartments|detached|semi|terrace"]({s},{w},{n},{e});
);
out center tags;
"""
    for endpoint in ENDPOINTS:
        logger.info(f"[OSM] Trying {endpoint} for PLZ={PLZ} bbox={BBOX}...")
        logger.info("[OSM] Waiting 10s cooldown before request...")
        time.sleep(10)
        try:
            resp = requests.post(endpoint, data={"data": query}, timeout=TIMEOUT + 15)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            logger.info(f"[OSM] OK: {len(elements)} ways from {endpoint}")
            return elements
        except Exception as e:
            logger.warning(f"[OSM] Failed ({endpoint}): {e}. Trying next endpoint...")
    logger.error("[OSM] All endpoints failed for PLZ 41464")
    return []


def elements_to_rows(elements: list[dict]) -> list[dict]:
    rows = []
    skipped_no_center = 0
    skipped_wrong_plz = 0

    for el in elements:
        center = el.get("center")
        if not center:
            skipped_no_center += 1
            continue

        tags = el.get("tags", {})
        city        = tags.get("addr:city", "")
        postal_code = tags.get("addr:postcode", "")
        building_tag = tags.get("building", "house")

        if city and city.strip().lower() not in ("neuss", ""):
            skipped_wrong_plz += 1
            continue

        if postal_code and postal_code.strip() != PLZ:
            skipped_wrong_plz += 1
            continue

        if not postal_code:
            postal_code = PLZ

        lat         = center["lat"]
        lon         = center["lon"]
        street      = tags.get("addr:street", "")
        housenumber = tags.get("addr:housenumber", "")
        b_type      = _map_building_tag(building_tag)

        rows.append({
            "building_id":             f"OSM_{el['id']}",
            "segment_id":              SEGMENT,
            "geometry":                f"POINT ({lon} {lat})",
            "neighbors":               None,
            "city":                    city or "Neuss",
            "street":                  street,
            "house_number":            housenumber,
            "postal_code":             postal_code,
            "lat":                     lat,
            "lon":                     lon,
            "building_type":           b_type,
            "geometry_source":         "OSM",
            "address_source":          "OSM",
            "building_type_source":    "OSM",
            "building_type_confidence": "MEDIUM",
        })

    logger.info(
        f"[OSM] {len(rows)} valid rows "
        f"(skipped: no_center={skipped_no_center}, wrong_plz={skipped_wrong_plz})"
    )
    return rows


def main():
    logger.info("=" * 60)
    logger.info(f"  OSM EXTRACTOR — PLZ {PLZ} → {SEGMENT}")
    logger.info("=" * 60)

    df_existing = pd.read_parquet(BUILDINGS_OUT) if BUILDINGS_OUT.exists() else pd.DataFrame()
    logger.info(f"[LOAD] Existing buildings.parquet: {len(df_existing)} rows")

    existing_ids = set(df_existing["building_id"].tolist()) if not df_existing.empty else set()
    if SEGMENT in (df_existing["segment_id"].unique().tolist() if not df_existing.empty else []):
        logger.info(f"[LOAD] {SEGMENT} already has {(df_existing['segment_id']==SEGMENT).sum()} rows — these will be skipped (dedup)")

    elements = fetch_elements()
    rows     = elements_to_rows(elements)

    # Dedup
    rows_deduped = [r for r in rows if r["building_id"] not in existing_ids]
    logger.info(f"[DEDUP] {len(rows)} → {len(rows_deduped)} after removing {len(rows)-len(rows_deduped)} duplicates")

    audit = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "plz":               PLZ,
        "segment":           SEGMENT,
        "bbox":              BBOX,
        "overpass_count":    len(elements),
        "valid_rows":        len(rows_deduped),
    }

    if not rows_deduped:
        logger.warning("[OUTPUT] No new rows — buildings.parquet unchanged")
    else:
        new_df   = pd.DataFrame(rows_deduped)
        combined = pd.concat([df_existing, new_df], ignore_index=True)
        combined.to_parquet(BUILDINGS_OUT, index=False)
        logger.info(f"[OUTPUT] buildings.parquet updated: {len(combined)} total (+{len(rows_deduped)})")

        print(f"\n{'='*60}")
        print(f"  {SEGMENT}: {len(rows_deduped)} new buildings")
        print(f"  building_type distribution:")
        print(new_df["building_type"].value_counts().to_string())
        print(f"\nbuildings.parquet: {len(combined)} total rows")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_path = AUDIT_DIR / f"extract_plz41464_{ts}.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    logger.info(f"[AUDIT] → {audit_path}")
    logger.info("=" * 60)
    logger.info("  DONE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
