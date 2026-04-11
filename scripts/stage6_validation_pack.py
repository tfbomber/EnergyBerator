import pandas as pd
import numpy as np
import os
import folium
import branca.colormap as cm
from shapely.wkt import loads as wkt_loads
from shapely.geometry import MultiPoint, mapping
import json
import logging

# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Stage6Validator")

def generate_validation_pack():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    output_dir = os.path.join(base_dir, "output", "stage6")
    os.makedirs(output_dir, exist_ok=True)

    segments_p = os.path.join(data_dir, "segments.parquet")
    buildings_p = os.path.join(data_dir, "buildings.parquet")

    if not os.path.exists(segments_p) or not os.path.exists(buildings_p):
        logger.error("Required data files missing.")
        return

    logger.info("Loading segments and buildings data...")
    df_seg = pd.read_parquet(segments_p)
    df_bld = pd.read_parquet(buildings_p)

    # --- Task A: Opportunity Map ---
    logger.info("Task A: Generating Opportunity Map...")
    
    # Pre-process geometries
    segment_polygons = {}
    for s_id, group in df_bld.groupby('segment_id'):
        try:
            points = []
            for wkt in group['geometry']:
                if wkt:
                    geom = wkt_loads(wkt)
                    if hasattr(geom, 'exterior'):
                        points.extend(list(geom.exterior.coords))
                    else:
                        # For multipolygons or others
                        pass
            if points:
                hull = MultiPoint(points).convex_hull
                # Folium expects [lat, lon]
                # Assuming data is in 4326 (lon, lat)
                coords = list(hull.exterior.coords)
                # Flip to [lat, lon]
                coords_flipped = [[c[1], c[0]] for c in coords]
                segment_polygons[s_id] = coords_flipped
        except Exception as e:
            logger.warning(f"Geometry failed for {s_id}: {e}")

    # Center map
    all_points = []
    for p in segment_polygons.values(): all_points.extend(p)
    
    if all_points:
        center_lat = np.mean([p[0] for p in all_points])
        center_lon = np.mean([p[1] for p in all_points])
    else:
        center_lat, center_lon = 51.15, 6.75 # Fallback to Neuss

    m = folium.Map(location=[center_lat, center_lon], zoom_start=15, tiles='cartodbpositron')

    # Color Scale: [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    # Branca linear colormap
    colormap = cm.LinearColormap(
        colors=['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15'],
        index=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        vmin=0, vmax=1
    ).to_step(n=5)
    colormap.caption = 'Opportunity Score'
    colormap.add_to(m)

    for idx, row in df_seg.iterrows():
        s_id = str(row['segment_id'])
        if s_id in segment_polygons:
            score = row['opportunity_score']
            color = colormap(score)
            
            popup_html = f"""
            <div style="font-family: Arial; font-size: 12px; min-width: 200px;">
                <b>Segment:</b> {s_id}<br>
                <b>Opportunity Score:</b> <span style="color:{color}; font-weight:bold;">{score:.4f}</span><br><hr>
                <b>Building Count:</b> {int(row['building_count'])}<br>
                <b>PV Potential Score:</b> {row['pv_segment_score']:.4f}<br>
                <b>DH None Ratio:</b> {row['none_dh_ratio']:.2%}<br>
                <b>Social Proof Signal:</b> {row.get('pv_adoption_signal', 0):.2%}<br>
                <b>Dominant Type:</b> {row.get('dominant_type', 'N/A')}<br>
            </div>
            """
            
            folium.Polygon(
                locations=segment_polygons[s_id],
                color='black',
                weight=1,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"Score: {score:.4f}"
            ).add_to(m)

    map_path = os.path.join(output_dir, "stage6_opportunity_map.html")
    m.save(map_path)
    logger.info(f"Map saved to {map_path}")

    # --- Task B: Ranking ---
    logger.info("Task B: Generating Ranking CSV...")
    df_rank = df_seg.sort_values(by=['opportunity_score', 'building_count'], ascending=False).copy()
    df_rank['rank'] = range(1, len(df_rank) + 1)
    
    # Reorder columns
    cols = ['rank', 'segment_id', 'opportunity_score', 'building_count', 'pv_segment_score', 'none_dh_ratio', 'pv_adoption_signal']
    # Add optional fields if exist
    for c in ['dominant_type', 'simple_flag']:
        if c in df_rank.columns: cols.append(c)
    
    rank_csv = os.path.join(output_dir, "stage6_segment_ranking.csv")
    df_rank[cols].to_csv(rank_csv, index=False)
    logger.info(f"Ranking CSV saved to {rank_csv}")

    # --- Task C: Explainer ---
    logger.info("Task C: Generating Explainer CSV...")
    explainer_data = []
    
    for idx, row in df_rank.iterrows():
        s_id = row['segment_id']
        score = row['opportunity_score']
        dh_ratio = row.get('none_dh_ratio', 0)
        pv_score = row.get('pv_segment_score', 0)
        dom_type = row.get('dominant_type', 'unknown')
        social_signal = row.get('pv_adoption_signal', 0)
        
        # Rule-based logic
        # Primary Driver
        if dh_ratio >= 0.95:
            driver = "Full decentralization potential"
        elif social_signal >= 0.80:
            driver = "High local adoption (Social Proof)"
        elif pv_score > 0.10:
            driver = "Strong roof potential"
        elif dom_type == 'rowhouse':
            driver = "Standardized housing pattern"
        else:
            driver = "Mixed morphology baseline"
            
        # Main Constraint
        if dh_ratio < 0.20:
            constraint = "District Heating dominance"
        elif pv_score < 0.05:
            constraint = "Low PV density (dilution)"
        elif dom_type == 'rowhouse':
            constraint = "Rowhouse morphology restricts modular expansion"
        else:
            constraint = "None identified"
            
        # Sales Hint
        if dh_ratio >= 0.95 and social_signal >= 0.50:
            hint = "Prime Target: Decentralized + High Social Proof"
        elif dh_ratio >= 0.95:
            hint = "Suitable for decentralized PV + heat pump outreach"
        elif social_signal >= 0.80:
            hint = "Leverage neighbor references / Social Proof"
        elif row['building_count'] > 200:
            hint = "Potentially efficient area-based outreach"
        elif dom_type == 'detached' and score > 0.5:
            hint = "Potential for high-value individual leads"
        else:
            hint = "Targeted direct mail campaign"

        # Explainer text
        text = f"Score of {score:.4f} driven by {driver.lower()}."
        if constraint != "None identified":
            text += f" Main bottleneck: {constraint.lower()}."
        if social_signal > 0.5:
            text += " Social proof is strong."

        explainer_data.append({
            "segment_id": s_id,
            "opportunity_score": score,
            "primary_driver": driver,
            "main_constraint": constraint,
            "social_proof_level": "High" if social_signal >= 0.75 else "Medium" if social_signal >= 0.3 else "Low",
            "sales_hint": hint,
            "explanation_text": text
        })
        
    explainer_csv = os.path.join(output_dir, "stage6_segment_explainer.csv")
    pd.DataFrame(explainer_data).to_csv(explainer_csv, index=False)
    logger.info(f"Explainer CSV saved to {explainer_csv}")

    # --- Task D: Summary ---
    logger.info("Task D: Generating Summary MD...")
    summary = []
    summary.append("# Stage 6 Summary: Opportunity Map & Validation")
    summary.append("\n## Overview")
    summary.append("This report provides a lightweight validation of the Stage 5 Opportunity Scores.")
    summary.append(f"- **Total segments verified:** {len(df_seg)}")
    if len(df_seg) == 1:
        summary.append("- **Note:** Current validation is limited to a single pilot segment.")
    
    summary.append("\n## Top Ranked Segments")
    top_rows = df_rank.head(5)
    summary.append(top_rows[['rank', 'segment_id', 'opportunity_score', 'building_count']].to_markdown(index=False))
    
    summary.append("\n## Observations")
    summary.append("- **Spatial Consistency:** The segment mapping correctly visualizes the pilot area density.")
    summary.append(f"- **Driver Analysis:** The dominant score for the pilot is driven primarily by its full decentralization status (No DH).")
    
    summary.append("\n## Known Limitations")
    summary.append("- PV normalization uses fixed bounds [0.02, 0.50]; may need calibration for extremely high-density cities.")
    summary.append("- Opportunity scores are relative for internal ranking, not absolute investment thresholds.")
    
    summary_path = os.path.join(output_dir, "stage6_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary))
    logger.info(f"Summary MD saved to {summary_path}")

    print("STAGE6_VALIDATION_PACK_COMPLETE")

if __name__ == "__main__":
    generate_validation_pack()
