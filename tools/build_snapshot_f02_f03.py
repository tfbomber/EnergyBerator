import pandas as pd
import os
import logging

# Setup simple logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SnapshotBuilder")

def build_snapshot():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f02_path = os.path.join(base_dir, "data", "fields", "field_02_building_type.parquet")
    f03_path = os.path.join(base_dir, "data", "fields", "field_03_district_heating.parquet")
    buildings_path = os.path.join(base_dir, "data", "buildings.parquet")
    
    output_dir = os.path.join(base_dir, "data", "snapshots")
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Load Data
    logger.info("Loading field datasets...")
    df_f02 = pd.read_parquet(f02_path)
    df_f03 = pd.read_parquet(f03_path)
    df_buildings = pd.read_parquet(buildings_path)
    
    # 2. Join Validation
    logger.info(f"F02 rows: {len(df_f02)}, F03 rows: {len(df_f03)}")
    
    # Merge
    df_snapshot = pd.merge(
        df_f02[['building_id', 'segment_id', 'field_value', 'confidence', 'source', 'notes']],
        df_f03[['building_id', 'segment_id', 'field_value', 'confidence', 'source', 'notes']],
        on=['building_id', 'segment_id'],
        how='outer',
        suffixes=('_f02', '_f03')
    )
    
    logger.info(f"Joined snapshot rows: {len(df_snapshot)}")
    
    if len(df_snapshot) != len(df_f02) or len(df_snapshot) != len(df_f03):
        logger.warning("MISMATCH DETECTED: Row counts do not align perfectly across fields.")
        # We continue as per instructions to report mismatches, not fail silently.
    
    # 3. Building-Level Formatting
    # Required columns: building_id, segment_id, building_type, dh_status, 
    # field_02_confidence, field_03_confidence, field_02_source, field_03_source
    df_bld_snapshot = df_snapshot.rename(columns={
        'field_value_f02': 'building_type',
        'field_value_f03': 'dh_status',
        'confidence_f02': 'field_02_confidence',
        'confidence_f03': 'field_03_confidence',
        'source_f02': 'field_02_source',
        'source_f03': 'field_03_source'
    })
    
    # Enrich with geometry basis from buildings.parquet
    if 'geometry' in df_buildings.columns:
        # Just a flag for basis
        df_bld_snapshot = pd.merge(
            df_bld_snapshot,
            df_buildings[['building_id', 'geometry']],
            on='building_id',
            how='left'
        )
        df_bld_snapshot['building_geometry_basis'] = df_bld_snapshot['geometry'].apply(
            lambda x: "OSM_WKT" if pd.notnull(x) else "UNKNOWN"
        )
        df_bld_snapshot = df_bld_snapshot.drop(columns=['geometry'])
    else:
        df_bld_snapshot['building_geometry_basis'] = "UNKNOWN"
        
    # Save Building Snapshot
    bld_parquet = os.path.join(output_dir, "building_snapshot_f02_f03.parquet")
    bld_csv = os.path.join(output_dir, "building_snapshot_f02_f03.csv")
    df_bld_snapshot.to_parquet(bld_parquet, index=False)
    df_bld_snapshot.to_csv(bld_csv, index=False)
    logger.info(f"Saved building snapshot to {bld_parquet}")

    # 4. Segment-Level Aggregation
    logger.info("Generating segment-level snapshot...")
    
    # Counts and Ratios
    # We can use groupby on segment_id
    segments = []
    for s_id, group in df_bld_snapshot.groupby('segment_id'):
        b_count = len(group)
        
        # F02 counts
        t_counts = group['building_type'].value_counts()
        d_count = t_counts.get('detached', 0)
        s_count = t_counts.get('semi', 0)
        r_count = t_counts.get('rowhouse', 0)
        
        # F03 counts
        h_counts = group['dh_status'].value_counts()
        ex_dh = h_counts.get('EXISTING', 0)
        pl_dh = h_counts.get('PLANNED', 0)
        no_dh = h_counts.get('NONE', 0)
        un_dh = h_counts.get('UNKNOWN', 0)
        
        # Cross metrics
        # count(rowhouse AND NONE)
        rh_no_dh = len(group[(group['building_type'] == 'rowhouse') & (group['dh_status'] == 'NONE')])
        se_no_dh = len(group[(group['building_type'] == 'semi') & (group['dh_status'] == 'NONE')])
        de_no_dh = len(group[(group['building_type'] == 'detached') & (group['dh_status'] == 'NONE')])

        segments.append({
            "segment_id": s_id,
            "building_count": b_count,
            
            "detached_count": d_count,
            "semi_count": s_count,
            "rowhouse_count": r_count,
            
            "detached_ratio": d_count / b_count if b_count > 0 else 0,
            "semi_ratio": s_count / b_count if b_count > 0 else 0,
            "rowhouse_ratio": r_count / b_count if b_count > 0 else 0,
            
            "existing_dh_count": ex_dh,
            "planned_dh_count": pl_dh,
            "none_dh_count": no_dh,
            "unknown_dh_count": un_dh,
            
            "existing_dh_ratio": ex_dh / b_count if b_count > 0 else 0,
            "planned_dh_ratio": pl_dh / b_count if b_count > 0 else 0,
            "none_dh_ratio": no_dh / b_count if b_count > 0 else 0,
            "unknown_dh_ratio": un_dh / b_count if b_count > 0 else 0,
            
            "detached_none_dh_count": de_no_dh,
            "semi_none_dh_count": se_no_dh,
            "rowhouse_none_dh_count": rh_no_dh
        })
        
    df_seg_snapshot = pd.DataFrame(segments)
    
    # Save Segment Snapshot
    seg_parquet = os.path.join(output_dir, "segment_snapshot_f02_f03.parquet")
    seg_csv = os.path.join(output_dir, "segment_snapshot_f02_f03.csv")
    df_seg_snapshot.to_parquet(seg_parquet, index=False)
    df_seg_snapshot.to_csv(seg_csv, index=False)
    logger.info(f"Saved segment snapshot to {seg_parquet}")
    
    return df_bld_snapshot, df_seg_snapshot

if __name__ == "__main__":
    build_snapshot()
