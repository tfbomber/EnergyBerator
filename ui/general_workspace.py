"""
ui/general_workspace.py
=========================
General Track — Two-Tab Workspace Entry Point

Tabs:
    A: Structure Foundation  — Foundation outputs only
    B: General Ranking       — Ranking outputs only

Rules:
    - Foundation tab reads ONLY foundation output JSON
    - Ranking tab reads ONLY ranking output JSON
    - DataFrames from the two tabs must NOT be merged
    - Shared filters (PLZ, street search) are managed via shared_filters.py
"""

import os
import json
import streamlit as st
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOUNDATION_DATA_PATH = os.path.join(BASE_DIR, "output", "foundation", "foundation_structure_results.json")


def _get_all_plz() -> list[str]:
    """Load all available PLZ values from Foundation data for shared filters."""
    if not os.path.exists(FOUNDATION_DATA_PATH):
        return []
    with open(FOUNDATION_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    plz_set = sorted({rec.get("plz", "UNKNOWN") for rec in data})
    return plz_set


def render_general_workspace():
    """Main entry point for the General Track two-tab workspace."""

    st.markdown(
        """
        <h2 style='margin-bottom:0'>
            🏘️ General Track Workspace
        </h2>
        <p style='color:#6c757d;font-size:13px;margin-top:4px'>
            Structural eligibility + street-level prioritization · General Track only · No product logic
        </p>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Shared filters above both tabs
    from ui.general.shared_filters import render_shared_header_filters
    all_plz = _get_all_plz()
    shared_filters = render_shared_header_filters(all_plz)

    st.markdown("---")

    # Two-tab layout
    tab_found, tab_rank = st.tabs([
        "🏗️ Tab A — Structure Foundation",
        "📊 Tab B — General Ranking",
    ])

    with tab_found:
        from ui.general.foundation_tab import render_foundation_tab
        render_foundation_tab(shared_filters)

    with tab_rank:
        from ui.general.ranking_tab import render_ranking_tab
        render_ranking_tab(shared_filters)
