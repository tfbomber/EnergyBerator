import pandas as pd
import json
import os
from shapely.geometry import shape, Point
from shapely.wkt import loads as wkt_loads
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Field03_RealSource")

def run(buildings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Field 03: District Heating Overlay (Real-Source Upgrade).
    Uses real buildings (WKT geometry) and OSM-based heating data.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    osm_heating_path = os.path.join(base_dir, "data", "neuss_osm_heating.geojson")
    
    # Load Heating Data (Priority 4: OSM_PROXY)
    heating_sc = []
    if os.path.exists(osm_heating_path):
        with open(osm_heating_path, "r") as f:
            data = json.load(f)
            features = data.get("features", [])
            for f in features:
                heating_sc.append(shape(f['geometry']))
    
    # Source type classification for metadata
    source_type = "OSM_PROXY"
    if not heating_sc:
        notes_global = "OSM search returned 0 heating features for this area."
    else:
        notes_global = f"Performed intersection with {len(heating_sc)} OSM heating features."

    results = []
    
    for _, row in buildings_df.iterrows():
        b_id = row.get("building_id")
        s_id = row.get("segment_id")
        geom_wkt = row.get("geometry")
        
        status = "NONE"
        gate = "NEUTRAL"
        confidence = 0.80 # Lower confidence for PROXY source
        
        if geom_wkt:
            try:
                b_geom = wkt_loads(geom_wkt)
                # Check for intersection or proximity (e.g. within 20m)
                for h_geom in heating_sc:
                    if b_geom.distance(h_geom) < 0.0002: # Approx 20m in degrees for Neuss
                        status = "EXISTING"
                        gate = "SOFT_NEGATIVE"
                        confidence = 0.70 # Proximity via proxy is lower confidence
                        break
            except Exception as e:
                logger.warning(f"Geometry error for {b_id}: {e}")
                status = "UNKNOWN"
        
        results.append({
            "building_id": b_id,
            "segment_id": s_id,
            "field_id": "field_03",
            "field_value": status,
            "confidence": confidence,
            "source": source_type,
            "notes": f"{notes_global} | Strategy: {gate}"
        })
            
    df_standard = pd.DataFrame(results)
    
    # Save Detailed Artifact as well
    output_base_dir = os.path.join(base_dir, "data", "fields")
    os.makedirs(output_base_dir, exist_ok=True)
    
    detail_results = []
    for r in results:
        detail_results.append({
            "building_id": r['building_id'],
            "segment_id": r['segment_id'],
            "dh_status": r['field_value'],
            "dh_strategy_gate": "SOFT_NEGATIVE" if r['field_value'] in ["EXISTING", "PLANNED"] else "NEUTRAL",
            "dh_source_type": source_type,
            "dh_source_name": "Overpass_API_OSM",
            "dh_confidence": r['confidence'],
            "dh_notes": r['notes'],
            "dh_geometry_basis": "OSM_WKT_Overlay"
        })
    df_detail = pd.DataFrame(detail_results)
    detail_path = os.path.join(output_base_dir, "field_03_district_heating_detail.parquet")
    if os.path.exists(detail_path):
        existing_detail = pd.read_parquet(detail_path)
        # Replace only the rows for segments currently being processed
        seg_ids = df_detail["segment_id"].unique()
        existing_detail = existing_detail[~existing_detail["segment_id"].isin(seg_ids)]
        df_detail = pd.concat([existing_detail, df_detail], ignore_index=True)
    df_detail.to_parquet(detail_path, index=False)
    logger.info(f"Detailed artifact saved to {detail_path}")

    return df_standard

if __name__ == "__main__":
    b_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "buildings.parquet")
    if os.path.exists(b_path):
        buildings = pd.read_parquet(b_path)
        print(run(buildings).head())
