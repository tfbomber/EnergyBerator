import os
import pandas as pd
import glob
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SegmentAggregator")

def aggregate_to_segments():
    """
    Aggregates building-level field results to segment-level metrics.
    Focuses on building type ratios for Field 02.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fields_dir = os.path.join(base_dir, "data", "fields")
    output_path = os.path.join(base_dir, "data", "segments.parquet")

    if not os.path.exists(fields_dir):
        logger.error(f"Fields directory not found: {fields_dir}")
        return

    # Process F02 (Building Type)
    f02_pattern = os.path.join(fields_dir, "field_02_building_type.parquet")
    f02_files = glob.glob(f02_pattern)
    
    # Process F03 (District Heating)
    f03_pattern = os.path.join(fields_dir, "field_03_district_heating.parquet")
    f03_files = glob.glob(f03_pattern)

    # Process F01 (PV Potential Lite)
    f01_pattern = os.path.join(fields_dir, "field_01_roof_potential.parquet")
    f01_files = glob.glob(f01_pattern)
    
    # Base summary dataframe
    segment_summary = pd.DataFrame()

    # 1. Process F02
    if f02_files:
        df_b2 = pd.read_parquet(f02_files[0])
        counts_b2 = df_b2.groupby('segment_id').size().rename('building_count')
        type_counts = df_b2.pivot_table(index='segment_id', columns='field_value', aggfunc='size', fill_value=0)
        for col in ['detached', 'semi', 'rowhouse']:
            if col not in type_counts.columns: type_counts[col] = 0
        ratios_b2 = type_counts.div(counts_b2, axis=0)
        ratios_b2.columns = [f"{c}_ratio" for c in ratios_b2.columns]
        segment_summary = pd.concat([ratios_b2, counts_b2], axis=1)

    # 2. Process F01 (Merge into F02 base)
    if f01_files:
        df_f01 = pd.read_parquet(f01_files[0])
        df_f01_clean = df_f01[['segment_id', 'roof_pool_area_m2', 'roof_pool_adjusted_m2', 'segment_area_m2_proxy', 'field_value']].rename(
            columns={
                'field_value': 'pv_segment_score',
                'segment_area_m2_proxy': 'segment_area_m2'
            }
        )
        if segment_summary.empty:
            segment_summary = df_f01_clean.set_index('segment_id')
        else:
            segment_summary = segment_summary.join(df_f01_clean.set_index('segment_id'), how='outer')

    # 3. Process F03 (Merge into base)
    if f03_files:
        df_b3 = pd.read_parquet(f03_files[0])
        counts_b3 = df_b3.groupby('segment_id').size()
        dh_counts = df_b3.pivot_table(index='segment_id', columns='field_value', aggfunc='size', fill_value=0)
        
        target_statuses = ['EXISTING', 'PLANNED', 'NONE', 'UNKNOWN']
        for s in target_statuses:
            if s not in dh_counts.columns: dh_counts[s] = 0
            
        dh_counts.columns = [f"{s.lower()}_dh_count" for s in dh_counts.columns]
        dh_ratios = dh_counts.div(counts_b3, axis=0)
        dh_ratios.columns = [c.replace('_count', '_ratio') for c in dh_counts.columns]
        
        if segment_summary.empty:
            segment_summary = pd.concat([dh_counts, dh_ratios], axis=1)
        else:
            segment_summary = segment_summary.join(pd.concat([dh_counts, dh_ratios], axis=1), how='outer')

    # 4. Process F04 (PV Adoption Signal)
    f04_pattern = os.path.join(fields_dir, "field_04_pv_adoption.parquet")
    f04_files = glob.glob(f04_pattern)
    if f04_files:
        df_f04 = pd.read_parquet(f04_files[0])
        df_f04_clean = df_f04[['segment_id', 'field_value']].rename(
            columns={'field_value': 'pv_adoption_signal'}
        )
        if segment_summary.empty:
            segment_summary = df_f04_clean.set_index('segment_id')
        else:
            segment_summary = segment_summary.join(df_f04_clean.set_index('segment_id'), how='outer')

    # 5. Process F10 (Street Opportunity Score)
    f10_pattern = os.path.join(fields_dir, "field_10_opportunity_score.parquet")
    f10_files = glob.glob(f10_pattern)
    if f10_files:
        df_f10 = pd.read_parquet(f10_files[0])
        df_f10_clean = df_f10[['segment_id', 'field_value']].rename(
            columns={'field_value': 'opportunity_score'}
        )
        if segment_summary.empty:
            segment_summary = df_f10_clean.set_index('segment_id')
        else:
            segment_summary = segment_summary.join(df_f10_clean.set_index('segment_id'), how='outer')

    if not segment_summary.empty:
        segment_summary = segment_summary.reset_index()
        if 'index' in segment_summary.columns:
            segment_summary = segment_summary.drop(columns=['index'])
        
        # Force segment_id to string and ensure no index name
        segment_summary['segment_id'] = segment_summary['segment_id'].astype(str)
        segment_summary.index.name = None

    # Save output
    segment_summary.to_parquet(output_path, index=False)
    logger.info(f"✅ Segment aggregation complete. Saved to {output_path}")
    print(segment_summary.to_string())

if __name__ == "__main__":
    aggregate_to_segments()
