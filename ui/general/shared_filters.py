"""
ui/general/shared_filters.py
==============================
General Workspace — Shared filter state utilities.

Both foundation_tab.py and ranking_tab.py may use these helpers
to read and write PLZ / street filters from session state.

Rules:
- This module must NOT contain scoring or gate logic.
- It may only manage filter state that is shared ACROSS tabs.
"""

import streamlit as st


def render_shared_header_filters(available_plz: list[str]) -> dict:
    """
    Render a shared filter row (PLZ and street search) above both tabs.

    Returns:
        dict with keys: "plz_selection", "street_search"
    """
    col1, col2 = st.columns([2, 3])
    with col1:
        plz_sel = st.multiselect(
            "PLZ Filter",
            options=available_plz,
            default=[],
            placeholder="All PLZ",
            key="general_workspace_plz",
        )
    with col2:
        street_search = st.text_input(
            "🔎 Street Name Search",
            value="",
            key="general_workspace_street_search",
        )
    return {"plz_selection": plz_sel, "street_search": street_search}


def apply_shared_filters(df, shared: dict):
    """
    Apply PLZ and street name filters to a DataFrame.
    Safe to call from both foundation_tab and ranking_tab.
    Does NOT mutate in place.
    """
    out = df.copy()
    if shared["plz_selection"]:
        out = out[out["plz"].isin(shared["plz_selection"])]
    if shared["street_search"].strip():
        out = out[out["street_name"].str.contains(shared["street_search"].strip(), case=False, na=False)]
    return out
