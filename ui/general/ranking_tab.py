"""
ui/general/ranking_tab.py
===========================
General Workspace — General Ranking Tab

PURPOSE: Display General Ranking outputs only.
- Reads ONLY from output/ranking/general_ranking_results.json
- Does NOT redefine or modify Foundation logic
- Does NOT modify the Foundation DataFrame
- Does NOT contain PV, heat-pump, or bundle logic
- Is a pure inspection and prioritization view

Columns shown:
    general_rank, street_name, plz, address_range, general_band,
    general_rank_score, ranking_reason_primary, sfh_total_ratio, mfh_ratio,
    building_count_total
"""

import os
import json
import streamlit as st
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RANKING_DATA_PATH = os.path.join(BASE_DIR, "output", "ranking", "general_ranking_results.json")

BAND_COLORS = {"HIGH": "#28a745", "MEDIUM": "#fd7e14", "LOW": "#dc3545"}
BAND_ICONS = {"HIGH": "🟢 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "🔴 LOW"}


@st.cache_data(ttl=60)
def _load_ranking() -> pd.DataFrame | None:
    if not os.path.exists(RANKING_DATA_PATH):
        return None
    with open(RANKING_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def render_ranking_tab(shared_filters: dict):
    """Render the General Ranking tab content."""

    # Universe toggle
    universe_mode = st.radio(
        "Ranking Universe",
        options=["PASS_ONLY", "PASS_PLUS_REVIEW"],
        index=0,
        horizontal=True,
        key="ranking_tab_universe",
        help="PASS_ONLY is the default. PASS_PLUS_REVIEW is debug mode.",
    )

    df = _load_ranking()

    if df is None:
        st.warning(
            "⚠️ Ranking data not found. Run `tracks/general/ranking/pipeline.py` first.\n\n"
            "```bash\n"
            "python tracks/general/ranking/pipeline.py\n"
            "```"
        )
        return

    if df.empty:
        st.info("No clusters available in the ranking output.")
        return

    # Filter to active universe
    if universe_mode == "PASS_ONLY":
        df = df[df["ranking_universe"] == "PASS_ONLY"]
        if df.empty:
            df = _load_ranking()  # fallback: show all if PASS_ONLY not regenerated

    # Apply shared PLZ/street filters
    from ui.general.shared_filters import apply_shared_filters
    df = apply_shared_filters(df, shared_filters)

    # KPI Bar
    total = len(df)
    high_c = (df["general_band"] == "HIGH").sum() if total > 0 else 0
    med_c = (df["general_band"] == "MEDIUM").sum() if total > 0 else 0
    low_c = (df["general_band"] == "LOW").sum() if total > 0 else 0
    avg_score = df["general_rank_score"].mean() if total > 0 else 0.0
    max_score = df["general_rank_score"].max() if total > 0 else 0.0
    min_score = df["general_rank_score"].min() if total > 0 else 0.0

    cols = st.columns(6)
    for col, (label, val, color) in zip(cols, [
        ("📋 Ranked", str(total), "#6c757d"),
        ("🟢 HIGH", str(high_c), BAND_COLORS["HIGH"]),
        ("🟡 MEDIUM", str(med_c), BAND_COLORS["MEDIUM"]),
        ("🔴 LOW", str(low_c), BAND_COLORS["LOW"]),
        ("⭐ Avg Score", f"{avg_score:.3f}", "#007bff"),
        ("📊 Score Range", f"{min_score:.2f}–{max_score:.2f}", "#adb5bd"),
    ]):
        col.markdown(
            f'<div style="background:#1e2230;border-radius:8px;padding:12px;text-align:center;'
            f'border-top:3px solid {color}">'
            f'<div style="font-size:11px;color:#adb5bd">{label}</div>'
            f'<div style="font-size:22px;font-weight:700;color:{color}">{val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Band filter
    band_sel = st.multiselect(
        "Band Filter", ["HIGH", "MEDIUM", "LOW"], default=[], placeholder="All Bands",
        key="ranking_tab_band"
    )
    if band_sel:
        df = df[df["general_band"].isin(band_sel)]

    st.caption(f"Showing **{len(df)}** ranked clusters (sorted by rank)")

    if df.empty:
        st.info("No clusters match the current filters.")
        return

    # Sort by general_rank ascending (1 = best)
    df_sorted = df.sort_values("general_rank", ascending=True)

    display = df_sorted[[
        "general_rank", "street_name", "plz", "address_range",
        "general_band", "general_rank_score",
        "ranking_reason_primary", "ranking_reason_secondary",
        "sfh_total_ratio", "mfh_ratio", "building_count_total",
    ]].rename(columns={
        "general_rank": "Rank",
        "street_name": "Street",
        "plz": "PLZ",
        "address_range": "Range",
        "general_band": "Band",
        "general_rank_score": "Score",
        "ranking_reason_primary": "Primary Reason",
        "ranking_reason_secondary": "Secondary",
        "sfh_total_ratio": "SFH %",
        "mfh_ratio": "MFH %",
        "building_count_total": "Bldgs",
    }).copy()
    display["SFH %"] = display["SFH %"].apply(lambda v: f"{v:.1%}")
    display["MFH %"] = display["MFH %"].apply(lambda v: f"{v:.1%}")
    display["Band"] = display["Band"].apply(lambda b: BAND_ICONS.get(b, b))

    st.dataframe(display, use_container_width=True, hide_index=True, height=380)

    st.markdown("---")
    st.markdown("#### 🔎 Score Decomposition Panel")
    st.caption("Select a cluster to inspect its three scoring dimensions.")

    if df_sorted.empty:
        return

    options = df_sorted["cluster_id"].tolist()
    labels = {
        r["cluster_id"]: f"#{r['general_rank']} — {r['street_name']} ({r['general_band']})"
        for _, r in df_sorted.iterrows()
    }
    sel_id = st.selectbox(
        "Select Cluster", options, format_func=lambda x: labels.get(x, x),
        key="ranking_decompose_select"
    )
    row = df_sorted[df_sorted["cluster_id"] == sel_id].iloc[0]

    c1, c2 = st.columns(2)
    with c1:
        band_color = BAND_COLORS.get(row["general_band"], "#6c757d")
        st.markdown(
            f"""
            <div style="background:#111827;border-radius:8px;padding:16px;border-left:4px solid {band_color}">
                <div style="color:#adb5bd;font-size:13px"><b>General Rank</b></div>
                <div style="font-size:32px;font-weight:700;color:{band_color}">#{row['general_rank']}</div>
                <div style="color:#94a3b8;font-size:13px">Band: <b>{row['general_band']}</b></div>
                <div style="color:#94a3b8;font-size:13px">Score: <code>{row['general_rank_score']:.4f}</code></div>
                <hr style="border-color:#374151;margin:10px 0">
                <div style="color:#adb5bd;font-size:13px"><b>Ranking Reasons</b></div>
                <div style="color:#cbd5e1;font-size:12px;margin-top:4px">
                    Primary: <code>{row['ranking_reason_primary']}</code><br>
                    Secondary: <code>{row['ranking_reason_secondary']}</code>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown("**Score Dimension Breakdown**")
        dim_data = {
            "Dimension": ["Structure Strength (50%)", "Scale (30%)", "Purity (20%)"],
            "Raw Signal": [
                f"SFH {row['sfh_total_ratio']:.1%} − MFH {row['mfh_ratio']:.1%}",
                f"{row['building_count_total']} buildings",
                f"Other ratio: {row['other_ratio']:.1%}",
            ],
        }
        st.dataframe(pd.DataFrame(dim_data), use_container_width=True, hide_index=True)
