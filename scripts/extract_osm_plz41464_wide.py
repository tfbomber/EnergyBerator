"""
Widen PLZ 41464 bbox re-extraction.
Previous bbox (51.130, 6.660, 51.165, 6.720) was too tight — only 59 buildings.
Foundation JSON shows 107 clusters for PLZ 41464 → many more buildings exist.
This script removes existing NEUSS_PLZ41464 rows and re-extracts with wider bbox.
"""
import json, logging, os, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd, requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("OSM_PLZ41464_WIDE")

BASE_DIR      = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILDINGS_OUT = BASE_DIR / "data" / "buildings.parquet"
AUDIT_DIR     = BASE_DIR / "output" / "layer2"
PLZ     = "41464"
SEGMENT = "NEUSS_PLZ41464"

# Wider bbox covering full Grimlinghausen / Allerheiligen-Meertal / cross-PLZ fringe
# PLZ 41464 is known to extend from ~51.130 to ~51.175, 6.640 to 6.750
BBOX = (51.125, 6.635, 51.175, 6.755)

ENDPOINTS = [
    "http://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
TIMEOUT = 90

def _map_building_tag(tag):
    tag = tag.lower()
    if tag in ("house","detached"):        return "detached"
    if tag in ("semi","semi_detached"):    return "semi"
    if tag in ("residential","terrace"):   return "rowhouse"
    if tag in ("apartments","apartment"):  return "apartment"
    return "unknown"

def fetch(bbox):
    s,w,n,e = bbox
    query = f"""
[out:json][timeout:{TIMEOUT}];
(
  way["building"~"residential|house|apartments|detached|semi|terrace"]({s},{w},{n},{e});
);
out center tags;
"""
    for ep in ENDPOINTS:
        logger.info(f"[OSM] Trying {ep} bbox={bbox}...")
        time.sleep(8)
        try:
            r = requests.post(ep, data={"data": query}, timeout=TIMEOUT+15)
            r.raise_for_status()
            els = r.json().get("elements", [])
            logger.info(f"[OSM] OK: {len(els)} ways")
            return els
        except Exception as e:
            logger.warning(f"[OSM] Failed {ep}: {e}")
    return []

def to_rows(elements):
    rows, skip = [], 0
    for el in elements:
        center = el.get("center")
        if not center: continue
        tags = el.get("tags", {})
        city = tags.get("addr:city","")
        pc   = tags.get("addr:postcode","")
        if city and city.strip().lower() not in ("neuss",""):
            skip += 1; continue
        if pc and pc.strip() != PLZ:
            skip += 1; continue
        if not pc: pc = PLZ
        b = _map_building_tag(tags.get("building","house"))
        rows.append({
            "building_id":  f"OSM_{el['id']}", "segment_id": SEGMENT,
            "geometry":     f"POINT ({center['lon']} {center['lat']})",
            "neighbors": None, "city": city or "Neuss",
            "street":       tags.get("addr:street",""),
            "house_number": tags.get("addr:housenumber",""),
            "postal_code":  pc, "lat": center["lat"], "lon": center["lon"],
            "building_type": b, "geometry_source": "OSM",
            "address_source": "OSM", "building_type_source": "OSM",
            "building_type_confidence": "MEDIUM",
        })
    logger.info(f"[OSM] {len(rows)} valid rows ({skip} skipped wrong PLZ)")
    return rows

def main():
    logger.info("="*60)
    logger.info(f"  WIDER bbox re-extraction for PLZ {PLZ}")
    logger.info("="*60)

    df = pd.read_parquet(BUILDINGS_OUT)
    logger.info(f"[LOAD] {len(df)} rows  | {SEGMENT} existing: {(df['segment_id']==SEGMENT).sum()}")

    # Remove existing GRIML_01 rows (we're replacing with wider extraction)
    df_clean = df[df["segment_id"] != SEGMENT].copy()
    existing_ids = set(df_clean["building_id"].tolist())
    logger.info(f"[CLEAN] Dropped {len(df)-len(df_clean)} old {SEGMENT} rows")

    elements = fetch(BBOX)
    rows = to_rows(elements)
    rows_deduped = [r for r in rows if r["building_id"] not in existing_ids]
    logger.info(f"[DEDUP] {len(rows)} → {len(rows_deduped)} after dedup")

    if rows_deduped:
        new_df   = pd.DataFrame(rows_deduped)
        combined = pd.concat([df_clean, new_df], ignore_index=True)
        combined.to_parquet(BUILDINGS_OUT, index=False)
        logger.info(f"[OUTPUT] buildings.parquet: {len(combined)} total (+{len(rows_deduped)} for {SEGMENT})")
        print(f"\n{SEGMENT}: {len(rows_deduped)} buildings")
        print("building_type:\n" + new_df["building_type"].value_counts().to_string())
    else:
        logger.warning("[OUTPUT] No new rows — buildings.parquet unchanged")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(AUDIT_DIR / f"extract_plz41464_wide_{ts}.json", "w") as f:
        json.dump({"plz":PLZ,"segment":SEGMENT,"bbox":BBOX,
                   "overpass_count":len(elements),"valid_rows":len(rows_deduped)}, f, indent=2)
    logger.info("="*60 + "\n  DONE\n" + "="*60)

if __name__ == "__main__":
    main()
