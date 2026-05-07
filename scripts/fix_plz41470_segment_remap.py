"""
fix_plz41470_segment_remap.py
=================================
PLZ 41470 buildings are already in buildings.parquet but tagged with
wrong segment_ids (41472/41466 bbox overlap). This script:
  1. Fetches correct OSM building IDs for PLZ 41470 via Overpass
     (strict addr:postcode=41470 filter)
  2. Updates matching rows in buildings.parquet to segment_id=NEUSS_PLZ41470
  3. Skips NULL-lat ALLERHEILIGEN_PILOT_SEG_01 stubs (corrupt, not fixed here)
"""
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
log = logging.getLogger("FIX_41470")

BASE          = Path(r'd:\Stock Analysis\D-Energy Berater\d-ess-engine')
BUILDINGS_P   = BASE / 'data' / 'buildings.parquet'
OVERPASS_URL  = "https://overpass.kumi.systems/api/interpreter"
TARGET_PLZ    = "41470"
TARGET_SEG    = "NEUSS_PLZ41470"
TIMEOUT       = 90

def fetch_confirmed_osm_ids(plz: str) -> set[str]:
    """
    Fetch OSM building IDs strictly tagged addr:postcode=41470.
    This is slower than bbox query but guaranteed correct PLZ.
    Fallback: use bbox + strict postcode tag filter.
    """
    # Bbox for Allerheiligen/Rosellen + surrounding area (intentionally wide)
    query = f"""
[out:json][timeout:{TIMEOUT}];
(
  way["building"]["addr:postcode"="{plz}"]
      (51.100,6.580,51.200,6.780);
);
out center tags;
"""
    log.info(f"[OSM] Querying Overpass — strict addr:postcode={plz} filter...")
    resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=TIMEOUT + 15)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])
    log.info(f"[OSM] {len(elements)} buildings confirmed with postcode={plz}")

    ids = set()
    for el in elements:
        ids.add(f"OSM_{el['id']}")

    return ids


def main():
    log.info("=== FIX: PLZ 41470 segment remap ===")

    # Load
    bldg = pd.read_parquet(BUILDINGS_P)
    log.info(f"[LOAD] {len(bldg)} buildings. Segments: {sorted(bldg['segment_id'].unique())}")

    # Fetch confirmed PLZ 41470 OSM IDs
    confirmed_ids = fetch_confirmed_osm_ids(TARGET_PLZ)

    if not confirmed_ids:
        log.error("[ABORT] No confirmed OSM IDs returned. Overpass may be down.")
        return

    # Find matching rows in buildings.parquet
    mask_osm   = bldg['building_id'].isin(confirmed_ids)
    mask_wrong = bldg['segment_id'] != TARGET_SEG
    mask_fix   = mask_osm & mask_wrong

    to_fix = bldg[mask_fix].copy()
    log.info(f"[REMAP] Found {mask_osm.sum()} buildings with PLZ 41470 OSM IDs")
    log.info(f"[REMAP] {len(to_fix)} need segment_id correction (not already NEUSS_PLZ41470)")
    log.info(f"[REMAP] Current segment_id distribution of these:")
    for seg, cnt in to_fix['segment_id'].value_counts().items():
        log.info(f"  {seg}: {cnt}")

    if len(to_fix) == 0:
        log.info("[DONE] Nothing to fix.")
        return

    # Apply remap
    bldg_updated = bldg.copy()
    bldg_updated.loc[mask_fix, 'segment_id'] = TARGET_SEG
    bldg_updated.loc[mask_fix, 'postal_code'] = TARGET_PLZ

    # Write back
    bldg_updated.to_parquet(BUILDINGS_P, index=False)
    log.info(f"[WRITE] buildings.parquet updated: {len(to_fix)} rows remapped -> {TARGET_SEG}")

    # Verify
    after = pd.read_parquet(BUILDINGS_P)
    log.info(f"[VERIFY] NEUSS_PLZ41470 count: {(after['segment_id']==TARGET_SEG).sum()}")

    print("\n=== SEGMENT COUNTS AFTER REMAP ===")
    print(after['segment_id'].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
