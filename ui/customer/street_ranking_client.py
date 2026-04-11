"""
street_ranking_client.py  —  Section 3: Customer View
======================================================
Customer-facing PV Street Ranking.

Currently delegates to the internal ranking view for data rendering.
TODO (when ready to differentiate):
  - Hide technical scores (priority_score, adjusted_street_score raw values)
  - Add German sales copy / region narratives
  - Simplify gate labels to plain German
  - Remove analyst-only expanders
"""

import streamlit as st


def render_street_ranking_client() -> None:
    st.markdown("## 🏘 PV Opportunity — Ihr Wohngebiet")
    st.caption("Kundenansicht  ·  Powered by D-ESS Engine")

    st.info(
        "**Vorläufige Ansicht** — Daten werden direkt aus dem Kernsystem geladen.  "
        "Diese Ansicht wird vor der Kundenpräsentation noch verfeinert.",
        icon="🔧",
    )

    st.markdown("---")

    # Delegate to internal view — same data, same render, replace when ready
    from ui.components.street_ranking_view import render_street_ranking_view
    render_street_ranking_view()
