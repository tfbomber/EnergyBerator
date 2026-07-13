"""
fetch_leipzig_pvgis_yield.py
==============================
Queries the EU JRC PVGIS API (PVcalc endpoint) for real specific PV yield
(kWh/kWp/yr) at each Leipzig PLZ's building centroid.

Same fixed methodology as fetch_augsburg_pvgis_yield.py (matches
territoryai's implementation_plan_leipzig.md Batch B1 assumptions, so
results are reproducible and comparable across ALL cities queried the same
way — Neuss/Kaarst/Augsburg/Leipzig):
  - peakpower  = 1 kWp     -> PVGIS's E_y (yearly energy, kWh) IS the
                              specific yield in kWh/kWp/yr directly.
  - loss       = 14 %      -> combined system loss assumption.
  - angle      = 35 deg    -> fixed tilt (not PVGIS auto-optimized).
  - aspect     = 0 deg     -> south-facing (PVGIS convention: 0 = south).
  - pvtechchoice = crystSi -> crystalline silicon (standard).
  - mountingplace = free   -> free-standing/rack-mounted equivalent.
  - raddatabase = PVGIS default for this region.

OUTPUT: data/derived/pvgis/leipzig_plz_yield_kwh_kwp.json
  {plz: {"lat":..., "lon":..., "n_buildings":..., "yield_kwh_kwp_yr":...}}
"""

import json
import os
import time
import pandas as pd
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDINGS_PATH = os.path.join(BASE_DIR, "data", "leipzig_buildings.parquet")
OUT_DIR = os.path.join(BASE_DIR, "data", "derived", "pvgis")
OUT_PATH = os.path.join(OUT_DIR, "leipzig_plz_yield_kwh_kwp.json")

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
HEADERS = {"User-Agent": "VeldAI-Leipzig-Pipeline/1.0 (research; contact: jiudi.wu@gmail.com)"}

FIXED_PARAMS = {
    "peakpower": 1,
    "loss": 14,
    "angle": 35,
    "aspect": 0,
    "pvtechchoice": "crystSi",
    "mountingplace": "free",
    "outputformat": "json",
}

KNOWN_LEIPZIG_PLZ = {
    "04103", "04105", "04107", "04109", "04129", "04155", "04157", "04158",
    "04159", "04177", "04178", "04179", "04205", "04207", "04209", "04229",
    "04249", "04275", "04277", "04279", "04288", "04289", "04299", "04315",
    "04316", "04317", "04318", "04319", "04328", "04329", "04347", "04349",
    "04356", "04357",
}


def compute_plz_centroids() -> dict:
    """Real PLZ centroids from actual extracted building geometries (not
    guessed/city-wide-centroid) — each PLZ's centroid is the mean of its own
    buildings' representative points, parsed from the stored WKT polygons."""
    from shapely import wkt as shapely_wkt

    df = pd.read_parquet(BUILDINGS_PATH)
    df = df[df["segment_id"].str.startswith("LEIPZIG_OSM_")]
    df = df[df["segment_id"] != "LEIPZIG_OSM_GENERAL"]

    centroids = {}
    for plz in KNOWN_LEIPZIG_PLZ:
        seg_id = f"LEIPZIG_OSM_{plz}"
        sub = df[df["segment_id"] == seg_id]
        if sub.empty:
            continue
        lats, lons = [], []
        for g in sub["geometry"]:
            try:
                c = shapely_wkt.loads(g).centroid
                lons.append(c.x)
                lats.append(c.y)
            except Exception:
                continue
        if not lats:
            continue
        centroids[plz] = {
            "lat": sum(lats) / len(lats),
            "lon": sum(lons) / len(lons),
            "n_buildings": len(sub),
        }
    return centroids


def query_pvgis(lat: float, lon: float) -> float:
    params = dict(FIXED_PARAMS)
    params["lat"] = round(lat, 5)
    params["lon"] = round(lon, 5)
    resp = requests.get(PVGIS_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return float(data["outputs"]["totals"]["fixed"]["E_y"])


def main():
    print("Computing real per-PLZ centroids from extracted building geometries...")
    centroids = compute_plz_centroids()
    print(f"Got centroids for {len(centroids)} PLZs.")

    results = {}
    for plz, info in sorted(centroids.items()):
        print(f"Querying PVGIS for PLZ {plz} (lat={info['lat']:.5f}, lon={info['lon']:.5f}, "
              f"n_buildings={info['n_buildings']})...")
        try:
            yield_kwh_kwp = query_pvgis(info["lat"], info["lon"])
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        print(f"  -> {yield_kwh_kwp:.1f} kWh/kWp/yr")
        results[plz] = {
            "lat": round(info["lat"], 6),
            "lon": round(info["lon"], 6),
            "n_buildings": info["n_buildings"],
            "yield_kwh_kwp_yr": round(yield_kwh_kwp, 1),
        }
        time.sleep(1.0)  # be polite to the free public API

    os.makedirs(OUT_DIR, exist_ok=True)
    out = {
        "source": "PVGIS v5.2 PVcalc API (https://re.jrc.ec.europa.eu/api/v5_2/PVcalc)",
        "methodology": FIXED_PARAMS,
        "note": (
            "yield_kwh_kwp_yr = E_y from PVGIS PVcalc at peakpower=1 kWp, "
            "i.e. directly the specific yield in kWh/kWp/yr. Fixed tilt=35deg, "
            "azimuth=south, loss=14% applied uniformly across all PLZs for "
            "reproducibility/comparability (not PVGIS auto-optimized per point)."
        ),
        "plz_yield": results,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {OUT_PATH}")
    print("\nSummary:")
    for plz, r in sorted(results.items()):
        print(f"  {plz}: {r['yield_kwh_kwp_yr']} kWh/kWp/yr")


if __name__ == "__main__":
    main()
