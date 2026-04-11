import pandas as pd
import numpy as np
import os
import logging
from shapely.geometry import Point, box, Polygon
from shapely.wkt import dumps as wkt_dumps

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MockScaler")

def generate_mock_segments():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    fields_dir = os.path.join(data_dir, "fields")

    # 1. Load Original Data to maintain schema
    df_b_orig = pd.read_parquet(os.path.join(data_dir, "buildings.parquet"))
    df_f01_orig = pd.read_parquet(os.path.join(fields_dir, "field_01_roof_potential.parquet"))
    df_f02_orig = pd.read_parquet(os.path.join(fields_dir, "field_02_building_type.parquet"))
    df_f03_orig = pd.read_parquet(os.path.join(fields_dir, "field_03_district_heating.parquet"))

    # 2. Define New Segments
    new_segments = [
        {"id": "NEUSS_DENSE_01", "type": "dense_rowhouse", "center": (6.76, 51.16), "count": 200},
        {"id": "NEUSS_VILLA_01", "type": "detached_high", "center": (6.77, 51.17), "count": 80},
        {"id": "NEUSS_OLD_TOWN_01", "type": "high_density_mixed", "center": (6.78, 51.18), "count": 150},
        {"id": "NEUSS_SUBURBAN_01", "type": "mixed_neutral", "center": (6.79, 51.19), "count": 120}
    ]

    new_b_rows = []
    new_f01_rows = []
    new_f02_rows = []
    new_f03_rows = []

    for seg in new_segments:
        s_id = seg["id"]
        center_lon, center_lat = seg["center"]
        
        # Stats for F01, F02, F03
        if seg["type"] == "dense_rowhouse":
            pv_score = 0.045
            b_types = ["rowhouse"] * 180 + ["semi"] * 20
            dh_status = "NONE"
            util_f = 0.40
        elif seg["type"] == "detached_high":
            pv_score = 0.12
            b_types = ["detached"] * 75 + ["semi"] * 5
            dh_status = "EXISTING"
            util_f = 0.70
        elif seg["type"] == "high_density_mixed":
            pv_score = 0.015
            b_types = ["rowhouse"] * 100 + ["apartment"] * 50
            dh_status = "PLANNED"
            util_f = 0.35
        elif seg["type"] == "mixed_neutral":
            pv_score = 0.06
            b_types = ["detached"] * 40 + ["semi"] * 40 + ["rowhouse"] * 40
            dh_status = "UNKNOWN"
            util_f = 0.50
        else:
            pv_score = 0.05
            b_types = ["detached"] * seg["count"]
            dh_status = "NONE"
            util_f = 0.50

        # Generate fake buildings in a grid
        count = seg["count"]
        side = int(np.sqrt(count))
        for i in range(count):
            b_id = f"MOCK_{s_id}_{i:03d}"
            
            dx = (i % side) * 0.0002
            dy = (i // side) * 0.0002
            lon = center_lon + dx
            lat = center_lat + dy
            poly = box(lon, lat, lon + 0.0001, lat + 0.0001)
            wkt = wkt_dumps(poly)
            
            # Buildings Table
            new_b_rows.append({
                "building_id": b_id, 
                "segment_id": s_id, 
                "geometry": wkt, 
                "neighbors": np.array([], dtype=object)
            })
            
            # F02 Row
            b_type = b_types[i] if i < len(b_types) else b_types[-1]
            new_f02_rows.append({
                "building_id": b_id, "segment_id": s_id, "field_id": "field_02", 
                "field_value": b_type, "confidence": 0.95, "source": "mock_generator_v1", "notes": ""
            })
            
            # F03 Row
            new_f03_rows.append({
                "building_id": b_id, "segment_id": s_id, "field_id": "field_03", 
                "field_value": dh_status, "confidence": 0.95, "source": "mock_generator_v1", "notes": ""
            })

        raw_area = seg["count"] * 120
        adj_area = raw_area * util_f
        seg_area = raw_area * 5
        
        new_f01_rows.append({
            "segment_id": s_id,
            "roof_pool_area_m2": float(raw_area),
            "roof_pool_adjusted_m2": float(adj_area),
            "segment_area_m2_proxy": float(seg_area),
            "field_id": "field_01",
            "field_value": float(pv_score),
            "confidence": 0.95,
            "source": "mock_generator_v1",
            "notes": f"Synthetic {seg['type']}"
        })

    # 3. Concatenate and Save
    df_b_final = pd.concat([df_b_orig, pd.DataFrame(new_b_rows)], ignore_index=True)
    df_f01_final = pd.concat([df_f01_orig, pd.DataFrame(new_f01_rows)], ignore_index=True)
    df_f02_final = pd.concat([df_f02_orig, pd.DataFrame(new_f02_rows)], ignore_index=True)
    df_f03_final = pd.concat([df_f03_orig, pd.DataFrame(new_f03_rows)], ignore_index=True)

    df_b_final.to_parquet(os.path.join(data_dir, "buildings.parquet"), index=False)
    df_f01_final.to_parquet(os.path.join(fields_dir, "field_01_roof_potential.parquet"), index=False)
    df_f02_final.to_parquet(os.path.join(fields_dir, "field_02_building_type.parquet"), index=False)
    df_f03_final.to_parquet(os.path.join(fields_dir, "field_03_district_heating.parquet"), index=False)

    logger.info(f"Successfully scaled dataset to {len(df_b_final)} buildings across 5 segments.")

if __name__ == "__main__":
    generate_mock_segments()
