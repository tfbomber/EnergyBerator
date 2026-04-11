import streamlit as st
import pandas as pd
import os

# D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization.
# General Base Model v1: Strictly structural-first prioritization.

st.set_page_config(page_title="D-ESS Area Opportunity Radar MVP", layout="wide")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MVP_BASE = os.path.join(ROOT_DIR, "mvp_radar")
TOP_AREAS_CSV = os.path.join(MVP_BASE, "outputs", "top_areas_neuss.csv")
FEATURE_CSV = os.path.join(MVP_BASE, "outputs", "area_features.csv")

st.title("D-ESS Neuss Area Opportunity Radar (General Base Model v1)")

st.warning("""
**DISCLAIMER**: This is an area-level prioritization tool. It does NOT confirm individual households, and it does not contain execution automation or activation pathways. 
It is based entirely on public signals and macroscopic proxies suitable for high-level targeting prioritization (Stage 76 Frozen Baseline excluded).
""")

if not os.path.exists(TOP_AREAS_CSV):
    st.error("No top areas output found. Please run the pipeline building and scoring scripts first.")
    st.stop()

top_df = pd.read_csv(TOP_AREAS_CSV)
feat_df = pd.read_csv(FEATURE_CSV)

# Merge coordinates for mapping
map_df = pd.merge(top_df, feat_df[['area_id', 'geometry_centroid_lat', 'geometry_centroid_lon']], on='area_id')
map_df.rename(columns={'geometry_centroid_lat': 'lat', 'geometry_centroid_lon': 'lon'}, inplace=True)

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Top Priority Areas (Ranked)")
    
    # Format the dataframe for rendering
    display_df = top_df[['rank', 'general_priority_score', 'PLZ', 'Stadtteil', 'structure_signal', 'purity_signal', 'scale_signal', 'why_this_area']].copy()
    display_df.rename(columns={
        'general_priority_score': 'Score',
        'structure_signal': 'Structure',
        'purity_signal': 'Purity',
        'scale_signal': 'Scale',
        'why_this_area': 'Why this area'
    }, inplace=True)
    
    display_df['Score'] = display_df['Score'].apply(lambda x: f"{x:.4f}")
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.subheader("Spatial Opportunity Map")
    if not map_df.empty and 'lat' in map_df.columns:
        valid_map_df = map_df.dropna(subset=['lat', 'lon'])
        st.map(valid_map_df[['lat', 'lon']], zoom=13)
    else:
        st.info("No spatial coordinates available. Map disabled.")

with col2:
    st.subheader("Area Detail Panel")
    selected_area = st.selectbox("Select Area ID", top_df["area_id"].unique())
    
    if selected_area:
        row = top_df[top_df["area_id"] == selected_area].iloc[0]
        
        # Classification Badge
        cls_color = "green" if row["classification"] == "STRONG_GENERAL_CANDIDATE" else ("orange" if row["classification"] == "REVIEW_GENERAL_CANDIDATE" else "red")
        st.markdown(f"### <span style='color:{cls_color}'>{row['classification']}</span>", unsafe_allow_html=True)
        
        st.metric("Priority Band", row["priority_band"])
        st.metric("General Priority Score", f"{row['general_priority_score']:.4f}")
        
        st.markdown("---")
        st.markdown("#### WHY THIS AREA IS GOOD")
        st.success(row["why_this_area"])
        
        st.markdown("#### WHAT HOLDS IT BACK")
        st.warning(row["holds_back"])
        
        st.markdown("---")
        st.markdown("### Top Reasons (Core Components)")
        st.info(f"**Structure**: {row['reason_struc']}")
        st.info(f"**Purity**: {row['reason_pur']}")
        st.info(f"**Scale**: {row['reason_scale']}")
        
        if st.button("Generate Tactical One-Pager"):
            st.success("Brief Generated via Console Engine! (General Strategy)")

st.markdown("---")
st.text("D-ESS MVP Area Radar | General Base Model v1 | Legacy Governance Frozen at Stage 76")
