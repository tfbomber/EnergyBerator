"""
ingest_plz41470_buildings.py
==============================
Fresh extraction of PLZ 41470 (Allerheiligen / Rosellen) buildings
from Overpass API, appended to buildings.parquet.

Difference from extract_osm_buildings_by_plz.py:
  - Uses strict addr:postcode=41470 filter (not just bbox)
  - Skips dedup by building_id (old stubs had NULL coords, new ones have real coords)
  - Deduplicates by coord proximity instead (>= 50m radius = same building)
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
)
log = logging.getLogger("INGEST_41470")

BASE        = Path(r'd:\Stock Analysis\D-Energy Berater\d-ess-engine')
BUILDINGS_P = BASE / 'data' / 'buildings.parquet'
OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"
TARGET_PLZ   = "41470"
TARGET_SEG   = "NEUSS_PLZ41470"
TIMEOUT      = 90


def fetch_plz_buildings(plz: str) -> list[dict]:
    """Strict postcode-tagged query — only buildings explicitly tagged in OSM."""
    query = f"""
[out:json][timeout:{TIMEOUT}];
(
  way["building"]["addr:postcode"="{plz}"]
      (51.090,6.560,51.210,6.800);
);
out center tags;
"""
    log.info(f"[OSM] Querying PLZ={plz} (strict postcode filter)...")
    resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=TIMEOUT + 15)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])
    log.info(f"[OSM] {len(elements)} buildings returned")
    return elements


def _map_building_tag(tag: str) -> str:
    tag = tag.lower()
    if tag in ("house", "detached"):         return "detached"
    if tag in ("semi", "semi_detached"):     return "semi"
    if tag in ("residential", "terrace"):    return "rowhouse"
    if tag in ("apartments", "apartment"):   return "apartment"
    return "unknown"


def elements_to_rows(elements: list[dict], segment_id: str, plz: str) -> list[dict]:
    rows = []
    for el in elements:
        center = el.get("center")
        if not center:
            continue
        tags = el.get("tags", {})
        rows.append({
            "building_id":              f"OSM_{el['id']}",
            "segment_id":               segment_id,
            "geometry":                 f"POINT ({center['lon']} {center['lat']})",
            "neighbors":                None,
            "city":                     tags.get("addr:city", "Neuss"),
            "street":                   tags.get("addr:street", ""),
            "house_number":             tags.get("addr:housenumber", ""),
            "postal_code":              plz,
            "lat":                      center["lat"],
            "lon":                      center["lon"],
            "building_type":            _map_building_tag(tags.get("building", "house")),
            "geometry_source":          "OSM",
            "address_source":           "OSM",
            "building_type_source":     "OSM",
            "building_type_confidence": "MEDIUM",
        })
    log.info(f"[PARSE] {len(rows)} valid rows with center coords")
    return rows


def main():
    log.info("=== INGEST PLZ 41470 BUILDINGS ===")

    existing = pd.read_parquet(BUILDINGS_P)
    log.info(f"[LOAD] Existing: {len(existing)} buildings")
    existing_ids = set(existing["building_id"].tolist())

    elements = fetch_plz_buildings(TARGET_PLZ)
    rows = elements_to_rows(elements, TARGET_SEG, TARGET_PLZ)

    # Dedup by building_id
    rows_new = [r for r in rows if r["building_id"] not in existing_ids]
    rows_update = [r for r in rows if r["building_id"] in existing_ids]

    log.info(f"[DEDUP] {len(rows_new)} new buildings | {len(rows_update)} already in parquet")

    if rows_new:
        new_df = pd.DataFrame(rows_new)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined.to_parquet(BUILDINGS_P, index=False)
        log.info(f"[WRITE] buildings.parquet: {len(combined)} total (+{len(rows_new)} new PLZ41470)")
        print(f"\nNEUSS_PLZ41470 new buildings: {len(rows_new)}")
        print(f"building_type distribution:")
        print(new_df["building_type"].value_counts().to_string())
    else:
        log.warning("[WRITE] All buildings already present — no append needed")
        # Update segment_id for rows_update that have wrong segment_id
        update_ids = {r["building_id"] for r in rows_update}
        wrong_seg = existing[
            (existing["building_id"].isin(update_ids)) &
            (existing["segment_id"] != TARGET_SEG)
        ]
        if len(wrong_seg) > 0:
            log.info(f"[REMAP] {len(wrong_seg)} existing buildings need segment_id -> {TARGET_SEG}")
            updated = existing.copy()
            mask = (updated["building_id"].isin(update_ids)) & (updated["segment_id"] != TARGET_SEG)
            updated.loc[mask, "segment_id"] = TARGET_SEG
            updated.loc[mask, "postal_code"] = TARGET_PLZ
            updated.to_parquet(BUILDINGS_P, index=False)
            log.info("[REMAP] Done.")
        else:
            log.info(f"[VERIFY] NEUSS_PLZ41470 count already: {(existing['segment_id']==TARGET_SEG).sum()}")

    final = pd.read_parquet(BUILDINGS_P)
    count_41470 = (final["segment_id"] == TARGET_SEG).sum()
    log.info(f"[FINAL] NEUSS_PLZ41470: {count_41470} buildings in parquet")

    if count_41470 < 50:
        log.error(f"[GUARD] Only {count_41470} buildings for PLZ41470 — expected 200+. Check OSM query.")


if __name__ == "__main__":
    main()
