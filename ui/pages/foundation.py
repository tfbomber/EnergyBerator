"""
ui/pages/foundation.py
======================
Foundation Layer — Residential Structure Filter

PURPOSE: Inspection console only. 
This page answers ONLY:
1. What is the housing composition of each cluster?
2. Is this cluster structurally eligible?
3. Why did it pass or fail?

NO scoring. NO commercial logic. NO action labels. NO probability claims.

Data source: output/foundation/foundation_structure_results.json
"""

import os
import json
import streamlit as st
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FOUNDATION_DATA_PATH = os.path.join(BASE_DIR, "output", "foundation", "foundation_structure_results.json")

# --- Gate constants from spec (Phase 15 revised) ---
# MIN_CLUSTER_SIZE removed — size is no longer a gate criterion (Phase 15 Finding A)
PASS_MAX_MFH_RATIO = 0.25
PASS_MIN_SFH_RATIO = 0.50
REVIEW_MAX_MFH_RATIO = 0.40
STANDALONE_MIN_SIZE = 15  # used for execution_scale_flag, NOT for gate

GATE_COLORS = {
    "PASS":   "#28a745",
    "REVIEW": "#fd7e14",
    "FAIL":   "#dc3545",
}

PROFILE_ICONS = {
    "SFH_DOMINANT":     "🟢 SFH_DOMINANT",
    "MIXED_RESIDENTIAL":"🟡 MIXED_RESIDENTIAL",
    "MFH_HEAVY":        "🔴 MFH_HEAVY",
}


@st.cache_data(ttl=120)
def load_foundation_data() -> pd.DataFrame | None:
    if not os.path.exists(FOUNDATION_DATA_PATH):
        return None
    with open(FOUNDATION_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame(data)


def render_kpi_bar(df: pd.DataFrame):
    total = len(df)
    pass_c = (df["structure_gate"] == "PASS").sum()
    review_c = (df["structure_gate"] == "REVIEW").sum()
    fail_c = (df["structure_gate"] == "FAIL").sum()
    avg_sfh = df["sfh_total_ratio"].mean()
    avg_mfh = df["mfh_ratio"].mean()

    cols = st.columns(6)
    kpi_data = [
        ("🏘️ Total Clusters", str(total), "#6c757d"),
        ("✅ PASS", str(pass_c), GATE_COLORS["PASS"]),
        ("🔔 REVIEW", str(review_c), GATE_COLORS["REVIEW"]),
        ("❌ FAIL", str(fail_c), GATE_COLORS["FAIL"]),
        ("📊 Avg SFH Ratio", f"{avg_sfh:.1%}", "#007bff"),
        ("📊 Avg MFH Ratio", f"{avg_mfh:.1%}", "#e83e8c"),
    ]
    for col, (label, val, color) in zip(cols, kpi_data):
        col.markdown(
            f"""
            <div style="background:#1e2230;border-radius:8px;padding:14px 12px;text-align:center;border-top:3px solid {color};">
                <div style="font-size:11px;color:#adb5bd;letter-spacing:1px">{label}</div>
                <div style="font-size:24px;font-weight:700;color:{color};margin-top:4px">{val}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_filter_panel(df: pd.DataFrame) -> pd.DataFrame:
    st.markdown("#### 🔍 Filter Panel")
    col1, col2, col3 = st.columns(3)
    col4, col5, col6 = st.columns(3)

    with col1:
        all_plz = sorted(df["plz"].unique().tolist())
        plz_sel = st.multiselect("PLZ", all_plz, default=[], placeholder="All PLZ")

    with col2:
        gate_sel = st.multiselect("Structure Gate", ["PASS", "REVIEW", "FAIL"], default=[], placeholder="All Gates")

    with col3:
        profile_sel = st.multiselect(
            "Structure Profile",
            ["SFH_DOMINANT", "MIXED_RESIDENTIAL", "MFH_HEAVY"],
            default=[],
            placeholder="All Profiles",
        )

    with col4:
        min_bldg = st.slider(
            "Min Building Count",
            min_value=0,
            max_value=int(df["building_count_total"].max() or 200),
            value=0,
            step=5,
        )

    with col5:
        max_mfh = st.slider(
            "Max MFH Ratio",
            min_value=0.0,
            max_value=1.0,
            value=1.0,
            step=0.05,
            format="%.2f",
        )

    with col6:
        street_search = st.text_input("🔎 Street Name Search", value="")

    filtered = df.copy()
    if plz_sel:
        filtered = filtered[filtered["plz"].isin(plz_sel)]
    if gate_sel:
        filtered = filtered[filtered["structure_gate"].isin(gate_sel)]
    if profile_sel:
        filtered = filtered[filtered["structure_profile"].isin(profile_sel)]
    filtered = filtered[filtered["building_count_total"] >= min_bldg]
    filtered = filtered[filtered["mfh_ratio"] <= max_mfh]
    if street_search.strip():
        filtered = filtered[
            filtered["street_name"].str.contains(street_search.strip(), case=False, na=False)
        ]

    return filtered


def render_main_table(df: pd.DataFrame):
    """Render sorted, formatted main table. Default: PASS first, SFH ratio desc, MFH asc."""
    gate_order_map = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
    df = df.copy()
    df["_gate_order"] = df["structure_gate"].map(gate_order_map)
    df_sorted = df.sort_values(
        ["_gate_order", "sfh_total_ratio", "mfh_ratio", "building_count_total"],
        ascending=[True, False, True, False],
    ).drop(columns=["_gate_order"])

    def format_gate(gate):
        icons = {"PASS": "✅ PASS", "REVIEW": "🔔 REVIEW", "FAIL": "❌ FAIL"}
        return icons.get(gate, gate)

    def format_pct(v):
        return f"{v:.1%}" if isinstance(v, float) else v

    display_cols = [
        "street_name", "plz", "address_range", "building_count_total",
        "sfh_detached_count", "sfh_semi_detached_count", "sfh_rowhouse_count",
        "sfh_total_count", "sfh_total_ratio",
        "mfh_count", "mfh_ratio",
        "other_count",
        "structure_profile", "structure_gate",
        "execution_scale_flag", "attached_confidence", "subtype_confidence",
        "gate_reason",
    ]
    col_labels = {
        "street_name": "Street Name",
        "plz": "PLZ",
        "address_range": "Address Range",
        "building_count_total": "Total Bldgs",
        "sfh_detached_count": "Detached",
        "sfh_semi_detached_count": "Semi-Det.",
        "sfh_rowhouse_count": "Row House",
        "sfh_total_count": "SFH Total",
        "sfh_total_ratio": "SFH Ratio",
        "mfh_count": "MFH Count",
        "mfh_ratio": "MFH Ratio",
        "other_count": "Other",
        "structure_profile": "Profile",
        "structure_gate": "Gate",
        "execution_scale_flag": "Scale",
        "attached_confidence": "Attached ℹ️",
        "subtype_confidence": "Subtype ℹ️",
        "gate_reason": "Gate Reason",
    }
    df_display = df_sorted[display_cols].rename(columns=col_labels).copy()
    df_display["SFH Ratio"] = df_display["SFH Ratio"].apply(format_pct)
    df_display["MFH Ratio"] = df_display["MFH Ratio"].apply(format_pct)
    df_display["Gate"] = df_display["Gate"].apply(format_gate)
    df_display["Profile"] = df_display["Profile"].apply(lambda x: PROFILE_ICONS.get(x, x))
    df_display["Scale"] = df_display["Scale"].apply(
        lambda s: "📍 STANDALONE" if s == "STANDALONE" else "🔗 APPEND"
    )
    def _fmt_conf(c: str) -> str:
        if c == "HIGH": return "✅ HIGH"
        if c == "MEDIUM": return "〜 MEDIUM"
        return "⚠️ Approx."
    df_display["Attached ℹ️"] = df_display["Attached ℹ️"].apply(_fmt_conf)
    df_display["Subtype ℹ️"] = df_display["Subtype ℹ️"].apply(_fmt_conf)

    st.dataframe(df_display, use_container_width=True, hide_index=True, height=420)

    return df_sorted


def render_expansion_panel(df_sorted: pd.DataFrame):
    """Row expansion panel: click a cluster_id to see full breakdown."""
    st.markdown("---")
    st.markdown("#### 🔎 Row Inspection Panel")
    st.caption("Select a cluster to see the full structural breakdown and gate reasoning.")

    if df_sorted.empty:
        st.info("No data to inspect. Adjust your filters above.")
        return

    options = df_sorted["cluster_id"].tolist()
    labels = {
        row["cluster_id"]: f"{row['cluster_id']} — {row['street_name']} ({row['structure_gate']})"
        for _, row in df_sorted.iterrows()
    }
    selected_id = st.selectbox(
        "Select Cluster",
        options=options,
        format_func=lambda x: labels.get(x, x),
        index=0,
        key="foundation_cluster_select",
    )

    row = df_sorted[df_sorted["cluster_id"] == selected_id].iloc[0]

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("##### 🏗️ Structure Breakdown")
        bldg_total = row["building_count_total"]
        def pct(n):
            return f"({n/bldg_total:.1%})" if bldg_total > 0 else "(—)"

        breakdown_data = {
            "Type": ["Detached", "Semi-Detached", "Row House", "MFH", "Other"],
            "Count": [
                row["sfh_detached_count"],
                row["sfh_semi_detached_count"],
                row["sfh_rowhouse_count"],
                row["mfh_count"],
                row["other_count"],
            ],
            "Share": [
                pct(row["sfh_detached_count"]),
                pct(row["sfh_semi_detached_count"]),
                pct(row["sfh_rowhouse_count"]),
                pct(row["mfh_count"]),
                pct(row["other_count"]),
            ],
        }
        st.dataframe(pd.DataFrame(breakdown_data), use_container_width=True, hide_index=True)

    with col_right:
        st.markdown("##### 🚦 Gate Explanation")
        gate = row["structure_gate"]
        gate_color = GATE_COLORS.get(gate, "#6c757d")
        scale = row.get("execution_scale_flag", "N/A")
        scale_icon = "📍" if scale == "STANDALONE" else "🔗"
        conf = row.get("subtype_confidence", "N/A")
        conf_icon = "✅" if conf == "HIGH" else ("〜" if conf == "MEDIUM" else "⚠️")
        att_conf = row.get("attached_confidence", "N/A")
        att_icon = "✅" if att_conf == "HIGH" else ("〜" if att_conf == "MEDIUM" else "⚠️")
        st.markdown(
            f"""
            <div style="background:#111827;border-radius:8px;padding:16px;border-left:4px solid {gate_color};">
                <div style="font-size:13px;color:#adb5bd"><b>Gate Thresholds (Phase 15)</b></div>
                <div style="font-size:12px;color:#cbd5e1;margin-top:4px;line-height:2">
                    PASS_MAX_MFH_RATIO = {PASS_MAX_MFH_RATIO}<br>
                    PASS_MIN_SFH_RATIO = {PASS_MIN_SFH_RATIO}<br>
                    REVIEW_MAX_MFH_RATIO = {REVIEW_MAX_MFH_RATIO}<br>
                    STANDALONE_MIN_SIZE = {STANDALONE_MIN_SIZE} (scale flag only)
                </div>
                <hr style="border-color:#374151;margin:12px 0">
                <div style="font-size:13px;color:#adb5bd"><b>Actual Values</b></div>
                <div style="font-size:12px;color:#cbd5e1;margin-top:4px;line-height:2">
                    building_count_total = {bldg_total}<br>
                    sfh_total_ratio = {row['sfh_total_ratio']:.4f} ({row['sfh_total_ratio']:.1%})<br>
                    mfh_ratio = {row['mfh_ratio']:.4f} ({row['mfh_ratio']:.1%})<br>
                    other_ratio = {row['other_ratio']:.4f}
                </div>
                <hr style="border-color:#374151;margin:12px 0">
                <div style="font-size:13px;color:#adb5bd"><b>Classification</b></div>
                <div style="font-size:20px;font-weight:700;color:{gate_color};margin-top:6px">{gate}</div>
                <div style="font-size:13px;color:#94a3b8;margin-top:4px">Reason: <code>{row['gate_reason']}</code></div>
                <div style="font-size:13px;color:#94a3b8">Profile: <b>{row['structure_profile']}</b></div>
                <hr style="border-color:#374151;margin:12px 0">
                <div style="font-size:13px;color:#adb5bd"><b>Scale &amp; Subtype Quality</b></div>
                <div style="font-size:13px;color:#cbd5e1;margin-top:4px;line-height:2">
                    {scale_icon} Scale: <b>{scale}</b><br>
                    {att_icon} Attached Confidence: <b>{att_conf}</b>
                    <span style="font-size:11px;color:#6c757d"> (detached vs attached split reliability)</span><br>
                    {conf_icon} Subtype Confidence: <b>{conf}</b>
                    <span style="font-size:11px;color:#6c757d"> (det/semi/row split reliability)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_foundation_filter():
    """Main entry point for Foundation Layer inspection console."""
    st.markdown(
        """
        <h2 style='margin-bottom:0'>
            🏗️ Foundation — Residential Structure Filter
        </h2>
        <p style='color:#6c757d;font-size:13px;margin-top:4px'>
            Inspection Console · Structural Eligibility Only · No Scoring · No Commercial Logic
        </p>
        """,
        unsafe_allow_html=True,
    )

    df = load_foundation_data()

    if df is None or df.empty:
        st.warning(
            "⚠️ Foundation data not found. "
            "Please run `scripts/generate_foundation_layer.py` first to generate the data."
        )
        st.code(
            "cd d:\\Stock Analysis\\D-Energy Berater\\d-ess-engine\n"
            "python scripts/generate_foundation_layer.py",
            language="bash",
        )
        return

    st.markdown("---")

    # KPI Bar
    render_kpi_bar(df)

    st.markdown("---")

    # Filter Panel
    filtered_df = render_filter_panel(df)
    st.markdown(f"*Showing **{len(filtered_df)}** of {len(df)} clusters.*")

    st.markdown("---")

    # Main Table
    st.markdown("#### 📋 Cluster Structural Composition Table")
    if filtered_df.empty:
        st.info("No clusters match the current filters.")
        return

    df_sorted = render_main_table(filtered_df)

    # Row Expansion
    render_expansion_panel(df_sorted)
