import requests
import json
import os
from shapely.geometry import shape, Polygon, LineString, mapping
import time

def extract_neuss_heating(output_heating):
    overpass_url = "http://overpass-api.de/api/interpreter"
    # Neuss roughly: [6.6, 51.1, 6.8, 51.3]
    # bbox format: minLat, minLon, maxLat, maxLon
    neuss_bbox = "51.15,6.6,51.25,6.8" 
    
    query = f"""
    [out:json][timeout:60];
    (
      way["heating"="district"]({neuss_bbox});
      way["man_made"="pipeline"]["substance"="hot_water"]({neuss_bbox});
    );
    out body;
    >;
    out skel qt;
    """
    
    try:
        print("[OSM] Fetching Neuss heating infrastructure...")
        response = requests.post(overpass_url, data={'data': query}, timeout=90)
        response.raise_for_status()
        data = response.json()
        
        nodes = {n['id']: (n['lon'], n['lat']) for n in data['elements'] if n['type'] == 'node'}
        features = []
        for el in data['elements']:
            if el['type'] == 'way' and 'nodes' in el:
                coords = [nodes[nid] for nid in el['nodes'] if nid in nodes]
                if len(coords) >= 2:
                    geom = LineString(coords)
                    features.append({
                        "type": "Feature",
                        "geometry": mapping(geom),
                        "properties": {**el.get('tags', {}), "id": el['id']}
                    })
        
        with open(output_heating, "w") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f)
        print(f"[OSM] Saved {len(features)} heating features to {output_heating}")
        
    except Exception as e:
        print(f"[OSM] Error: {e}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    extract_neuss_heating(os.path.join(base_dir, "data", "neuss_osm_heating.geojson"))
