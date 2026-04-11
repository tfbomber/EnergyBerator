"""
roi_report_client.py  —  Section 3: Customer View
==================================================
Customer-facing ROI Report.

Currently delegates to the internal ROI report renderer.
TODO (when ready to differentiate):
  - Remove technical audit fields (evidence_chain, schema_version, etc.)
  - Simplify subsidy breakdown to plain German summary
  - Add customer-friendly cover page / branding
  - Generate client PDF directly from this view
"""

import streamlit as st


def render_roi_report_client() -> None:
    st.markdown("## 📄 Ihr PV-Angebot & ROI-Bericht")
    st.caption("Kundenansicht  ·  Powered by D-ESS Engine")

    report = st.session_state.get("street_roi_report", {})
    if not report:
        st.info(
            "Kein Bericht geladen. Bitte wählen Sie zuerst eine Straße "
            "im **PV Street Ranking (Kunde)** aus.",
            icon="📍",
        )
        if st.button("→ Zum PV Street Ranking (Kunde)"):
            st.session_state.workspace_view = "CLIENT_STREET_RANKING"
            st.rerun()
        return

    st.markdown("---")

    # Delegate to internal report renderer — replace when ready
    from ui.components.s2_roi_report import render_roi_report
    render_roi_report(report)
