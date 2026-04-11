"""
ui/general/foundation_tab.py
==============================
General Workspace — Foundation Tab

PURPOSE: Display General Foundation outputs only.
- Reads ONLY from output/foundation/foundation_structure_results.json
- Does NOT display or consume any ranking fields
- Does NOT apply any ranking or scoring logic
- Structure matches the existing Foundation Filter page behaviour

Note: This tab replaces and wraps the standalone Foundation Filter page
within the General Workspace two-tab view.
"""

import os
import json
import streamlit as st
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FOUNDATION_DATA_PATH = os.path.join(BASE_DIR, "output", "foundation", "foundation_structure_results.json")

GATE_COLORS = {"PASS": "#28a745", "REVIEW": "#fd7e14", "FAIL": "#dc3545"}


@st.cache_data(ttl=120)
def _load_foundation() -> pd.DataFrame | None:
    if not os.path.exists(FOUNDATION_DATA_PATH):
        return None
    with open(FOUNDATION_DATA_PATH, encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


def render_foundation_tab(shared_filters: dict):
    """Render the Structure Foundation tab content."""
    df = _load_foundation()

    if df is None or df.empty:
        st.warning(
            "⚠️ Foundation data not found. Run `scripts/generate_foundation_layer.py` first."
        )
        return

    # Apply shared filters
    from ui.general.shared_filters import apply_shared_filters
    df = apply_shared_filters(df, shared_filters)

    # KPI Bar
    total = len(df)
    pass_c = (df["structure_gate"] == "PASS").sum()
    review_c = (df["structure_gate"] == "REVIEW").sum()
    fail_c = (df["structure_gate"] == "FAIL").sum()
    avg_sfh = df["sfh_total_ratio"].mean() if total > 0 else 0.0
    avg_mfh = df["mfh_ratio"].mean() if total > 0 else 0.0

    cols = st.columns(6)
    for col, (label, val, color) in zip(cols, [
        ("🏘️ Total", str(total), "#6c757d"),
        ("✅ PASS", str(pass_c), GATE_COLORS["PASS"]),
        ("🔔 REVIEW", str(review_c), GATE_COLORS["REVIEW"]),
        ("❌ FAIL", str(fail_c), GATE_COLORS["FAIL"]),
        ("📊 Avg SFH", f"{avg_sfh:.1%}", "#007bff"),
        ("📊 Avg MFH", f"{avg_mfh:.1%}", "#e83e8c"),
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

    # Tab-local gate filter
    gate_sel = st.multiselect(
        "Gate Filter", ["PASS", "REVIEW", "FAIL"], default=[], placeholder="All Gates",
        key="found_tab_gate"
    )
    if gate_sel:
        df = df[df["structure_gate"].isin(gate_sel)]

    st.caption(f"Showing **{len(df)}** clusters")

    if df.empty:
        st.info("No clusters match the current filters.")
        return

    # Sort: PASS first, SFH desc, MFH asc
    gate_order = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
    df = df.copy()
    df["_g"] = df["structure_gate"].map(gate_order)
    df_sorted = df.sort_values(["_g", "sfh_total_ratio", "mfh_ratio"], ascending=[True, False, True]).drop(columns=["_g"])

    # Display subset of columns (Foundation only, no ranking)
    display = df_sorted[[
        "street_name", "plz", "address_range", "building_count_total",
        "sfh_detached_count", "sfh_semi_detached_count", "sfh_rowhouse_count",
        "sfh_total_count", "sfh_total_ratio", "mfh_count", "mfh_ratio",
        "other_count", "structure_profile", "structure_gate",
        "execution_scale_flag", "attached_confidence", "subtype_confidence", "gate_reason",
    ]].rename(columns={
        "street_name": "Street", "plz": "PLZ", "address_range": "Range",
        "building_count_total": "Total Bldgs",
        "sfh_detached_count": "Det.", "sfh_semi_detached_count": "Semi.", "sfh_rowhouse_count": "Row.",
        "sfh_total_count": "SFH Total", "sfh_total_ratio": "SFH %",
        "mfh_count": "MFH Count", "mfh_ratio": "MFH %",
        "other_count": "Other", "structure_profile": "Profile",
        "structure_gate": "Gate",
        "execution_scale_flag": "Scale",
        "attached_confidence": "Attached ℹ️",
        "subtype_confidence": "Subtype ℹ️",
        "gate_reason": "Reason",
    }).copy()
    display["SFH %"] = display["SFH %"].apply(lambda v: f"{v:.1%}")
    display["MFH %"] = display["MFH %"].apply(lambda v: f"{v:.1%}")
    display["Scale"] = display["Scale"].apply(
        lambda s: "📍 STANDALONE" if s == "STANDALONE" else "🔗 APPEND"
    )
    def _fmt_conf(c: str) -> str:
        if c == "HIGH": return "✅ HIGH"
        if c == "MEDIUM": return "〜 MEDIUM"
        return "⚠️ Approx."
    display["Attached ℹ️"] = display["Attached ℹ️"].apply(_fmt_conf)
    display["Subtype ℹ️"] = display["Subtype ℹ️"].apply(_fmt_conf)

    st.dataframe(display, use_container_width=True, hide_index=True, height=380)

    with st.expander("ℹ️ Confidence Signals — what do these mean?", expanded=False):
        st.markdown(
            "**Attached ℹ️** — Can we trust the Detached vs Attached split?\n\n"
            "- ✅ **HIGH** — Few `building=house` tags; explicit typed tags dominate. Detached count is reliable.\n"
            "- 〜 **MEDIUM** — Some generic tags. Detached count may be slightly overstated.\n"
            "- ⚠️ **Approx.** — Many `house` tags. Detached likely inflated; real attached homes may be hidden.\n\n"
            "**Subtype ℹ️** — Can we trust the Det./Semi./Row. subtype split?\n\n"
            "- ✅ **HIGH** — Explicit subtype tags (e.g. `detached`, `semidetached_house`) dominate.\n"
            "- ⚠️ **Approx.** — Generic tags dominate; rely on **SFH Total**, not subtype counts.\n\n"
            "*Neither signal affects Foundation gate or General Ranking.*"
        )

