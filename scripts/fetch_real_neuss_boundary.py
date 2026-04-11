import json
import os
import sys
import time
import urllib.request
import urllib.error

print("Fetching OSM boundary from Nominatim search.php...")

URL = "https://nominatim.openstreetmap.org/search.php?q=Neuss&polygon_geojson=1&format=jsonv2"
OUT_PATH = "config/boundaries/neuss_admin_boundary.geojson"

req = urllib.request.Request(
    URL,
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ',
        'Accept': 'application/json'
    }
)

max_retries = 3
for attempt in range(max_retries):
    try:
        print(f"Attempt {attempt+1}/{max_retries}...")
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            target = None
            for r in data:
                if r.get("osm_type") == "relation" and r.get("osm_id") == 62710:
                    target = r
                    break
            
            if not target and data:
                target = data[0]
                
            if not target:
                print("No results from search.")
                sys.exit(1)
                
            geom = target.get("geojson")
            if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
                print("Invalid geometry returned.")
                sys.exit(1)
                
            feature_collection = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "name": target.get("name", "Neuss"),
                            "osm_relation_id": target.get("osm_id", 62710),
                            "note": "Authoritative high-precision OSM geometry from Nominatim."
                        },
                        "geometry": geom
                    }
                ]
            }

            os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(feature_collection, f, indent=2, ensure_ascii=False)
                
            print(f"SUCCESS: High-precision {geom['type']} written to {OUT_PATH}")
            sys.exit(0)
            
    except Exception as e:
        print(f"Error on attempt {attempt+1}: {e}")
        time.sleep(3)

print("Failed to fetch properly.")
sys.exit(1)
