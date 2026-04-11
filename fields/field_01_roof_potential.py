import pandas as pd
import numpy as np
import os
import logging
from shapely.wkt import loads as wkt_loads
from shapely.ops import transform
from shapely.geometry import MultiPoint
import pyproj

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Field01_Lite")

# Projection for area calculation (UTM 32N for Neuss/Germany)
WGS84 = pyproj.CRS('EPSG:4326')
UTM32N = pyproj.CRS('EPSG:25832')
project = pyproj.Transformer.from_crs(WGS84, UTM32N, always_xy=True).transform

def get_area_m2(geom_wkt):
    try:
        geom = wkt_loads(geom_wkt)
        projected_geom = transform(project, geom)
        return projected_geom.area
    except:
        return 0.0

def run(buildings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Field 01 Lite: Segment PV Potential Proxy.
    Calculates roof pool and adjusted potential score per segment.
    """
    if buildings_df.empty:
        logger.warning("Empty buildings dataframe provided.")
        return pd.DataFrame()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f02_path = os.path.join(base_dir, "data", "fields", "field_02_building_type.parquet")
    
    if not os.path.exists(f02_path):
        logger.error(f"Field 02 data not found at {f02_path}. Cannot calculate utilization factors.")
        # Fallback: assume detached for all if F02 missing? No, better to fail or use a very conservative default.
        df_f02 = pd.DataFrame(columns=['building_id', 'field_value'])
    else:
        df_f02 = pd.read_parquet(f02_path)

    # 1. Calculate individual building areas
    logger.info("Calculating building footprint areas...")
    buildings_df['footprint_area_m2'] = buildings_df['geometry'].apply(get_area_m2)

    # 2. Join with Field 02
    df_merged = pd.merge(
        buildings_df[['building_id', 'segment_id', 'footprint_area_m2', 'geometry']],
        df_f02[['building_id', 'field_value']],
        on='building_id',
        how='left'
    )
    df_merged['field_value'] = df_merged['field_value'].fillna('unknown')

    # 3. Apply Utilization Factors
    # detached: 0.45, semi: 0.40, rowhouse: 0.35, others: 0.20
    utilization_factors = {
        'detached': 0.45,
        'semi': 0.40,
        'rowhouse': 0.35,
        'apartment': 0.20,
        'large_block': 0.20,
        'unknown': 0.20
    }
    
    def get_factor(b_type, area):
        # Heuristic for MFH if not explicitly typed but large
        if b_type == 'unknown' and area > 400:
            return 0.20
        return utilization_factors.get(b_type, 0.20)

    df_merged['utilization_factor'] = df_merged.apply(lambda x: get_factor(x['field_value'], x['footprint_area_m2']), axis=1)
    df_merged['adjusted_area_m2'] = df_merged['footprint_area_m2'] * df_merged['utilization_factor']

    # 4. Aggregate to Segment Level
    logger.info("Aggregating to segment level...")
    segment_groups = df_merged.groupby('segment_id')
    
    results = []
    for s_id, group in segment_groups:
        roof_pool_area = group['footprint_area_m2'].sum()
        roof_pool_adjusted = group['adjusted_area_m2'].sum()
        building_count = len(group)
        
        # Calculate Segment Area Proxy: Convex Hull + 10m buffer
        try:
            points = []
            for geom_wkt in group['geometry']:
                if geom_wkt:
                    g = wkt_loads(geom_wkt)
                    points.extend(list(g.exterior.coords))
            
            if points:
                multi_point = MultiPoint(points)
                hull = multi_point.convex_hull
                # Transform to metric for buffering
                hull_metric = transform(project, hull)
                buffered_hull = hull_metric.buffer(10)
                segment_area_m2 = buffered_hull.area
            else:
                segment_area_m2 = 0
        except Exception as e:
            logger.warning(f"Failed to calculate segment area for {s_id}: {e}")
            segment_area_m2 = 0

        # Plan A fix (v2, 2026-03-27): score = adjusted / pool_area
        # = weighted-average PV utilization rate across all buildings in segment.
        # Range: [0, max_util_factor] where max = 0.45 (all detached).
        # Scale-invariant: does NOT depend on segment geographic extent.
        # segment_area_m2_proxy is retained for audit/reference ONLY.
        pv_score = roof_pool_adjusted / roof_pool_area if roof_pool_area > 0 else 0.0

        results.append({
            "segment_id": s_id,
            "field_id": "field_01",
            "building_count": building_count,
            "roof_pool_area_m2": round(roof_pool_area, 2),
            "roof_pool_adjusted_m2": round(roof_pool_adjusted, 2),
            "segment_area_m2_proxy": round(segment_area_m2, 2),  # retained for audit, NOT used in score
            "field_value": round(pv_score, 4),  # = adjusted / pool (v2)
            "confidence": 0.85,
            "source": "statistical_proxy_v2_utilization_rate",
            "notes": (
                f"v2: field_value = roof_pool_adjusted_m2 / roof_pool_area_m2 "
                f"(weighted-average PV utilization rate). "
                f"Util factors: {utilization_factors}. "
                f"segment_area_m2_proxy (ConvexHull+10m) retained for audit only."
            )
        })

    return pd.DataFrame(results)

if __name__ == "__main__":
    buildings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "buildings.parquet")
    if os.path.exists(buildings_path):
        buildings = pd.read_parquet(buildings_path)
        output = run(buildings)
        print(output.to_string())
        
        # Save output for integration check
        output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fields", "field_01_roof_potential.parquet")
        output.to_parquet(output_path, index=False)
        logger.info(f"Field 01 Lite results saved to {output_path}")
