import pandas as pd
import os
import logging

# Setup logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UnifiedSnapshot")

def build_unified_snapshot():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fields_dir = os.path.join(base_dir, "data", "fields")
    output_dir = os.path.join(base_dir, "data", "snapshots")
    os.makedirs(output_dir, exist_ok=True)
    
    # Paths
    f01_p = os.path.join(fields_dir, "field_01_roof_potential.parquet")
    f02_p = os.path.join(fields_dir, "field_02_building_type.parquet")
    f03_p = os.path.join(fields_dir, "field_03_district_heating.parquet")
    buildings_p = os.path.join(base_dir, "data", "buildings.parquet")

    logger.info("Loading field datasets...")
    # F01 is currently segment-level only in its primary output, 
    # but we might want individual building areas if available.
    # However, for the 'Unified Snapshot', we'll focus on Segment level first 
    # as that's where the Opportunity Score lives.
    
    # Let's load the buildings to get the structure
    df_buildings = pd.read_parquet(buildings_p)
    
    # Load F02 & F03 (Building level)
    df_f02 = pd.read_parquet(f02_p)
    df_f03 = pd.read_parquet(f03_p)
    
    # Merge Building level data
    df_b_unified = pd.merge(
        df_buildings[['building_id', 'segment_id']],
        df_f02[['building_id', 'field_value', 'confidence']].rename(columns={'field_value': 'building_type', 'confidence': 'f02_conf'}),
        on='building_id', how='left'
    )
    df_b_unified = pd.merge(
        df_b_unified,
        df_f03[['building_id', 'field_value', 'confidence']].rename(columns={'field_value': 'dh_status', 'confidence': 'f03_conf'}),
        on='building_id', how='left'
    )

    # Save Building Unified Snapshot
    b_out = os.path.join(output_dir, "unified_building_snapshot.parquet")
    df_b_unified.to_parquet(b_out, index=False)
    logger.info(f"Saved unified building snapshot to {b_out} (Rows: {len(df_b_unified)})")

    # Now Segment Level - this is where F01 lives
    segments_master_p = os.path.join(base_dir, "data", "segments.parquet")
    if os.path.exists(segments_master_p):
        df_seg = pd.read_parquet(segments_master_p)
        logger.info(f"Loaded master segments data with {len(df_seg)} rows.")
        
        # Save Segment Unified Snapshot (Alias of master segments but in snap folder for audit consistency)
        s_out = os.path.join(output_dir, "unified_segment_snapshot.parquet")
        df_seg.to_parquet(s_out, index=False)
        logger.info(f"Saved unified segment snapshot to {s_out}")
    else:
        logger.warning("Master segments.parquet not found. Skipping segment snapshot.")

if __name__ == "__main__":
    build_unified_snapshot()
