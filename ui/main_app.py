import os

import streamlit as st

from ui.components.demo import render_demo_loader
from ui.components.s1_intake import render_intake_form
from ui.components.s1_roi_intake import render_roi_intake_form
from ui.components.s2_report import render_report_preview
from ui.components.s2_roi_report import render_roi_report
from ui.components.trace_export import render_export_view, render_trace_view
from ui.theme import inject_global_styles

VIEW_INTAKE = "📥 Case Intake"
VIEW_REPORT = "📊 Report Preview"
VIEW_TRACE = "🔍 Evidence & Trace"
VIEW_EXPORT = "💾 Export"
VIEWS = [VIEW_INTAKE, VIEW_REPORT, VIEW_TRACE, VIEW_EXPORT]


def run_dashboard(show_legacy_notice: bool = False) -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(current_dir)
    policies_dir = os.path.join(base_dir, "policies")

    st.set_page_config(
        page_title="D-ESS Audit Workspace",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_global_styles()

    if show_legacy_notice:
        st.info("Legacy entrypoint detected: please use `d-ess-engine/app.py` for future runs.")

    if "current_case_input" not in st.session_state:
        st.session_state.current_case_input = {}
    if "current_report" not in st.session_state:
        st.session_state.current_report = None
    if "history" not in st.session_state:
        st.session_state.history = []
    if "selected_policy" not in st.session_state:
        st.session_state.selected_policy = "dus_balcony_pv.json"
    if "view_mode" not in st.session_state:
        st.session_state.view_mode = "Client View"
    if "demo_case_selected" not in st.session_state:
        st.session_state.demo_case_selected = None
    if "active_view" not in st.session_state or st.session_state.active_view not in VIEWS:
        st.session_state.active_view = VIEW_INTAKE
    if "roi_mode" not in st.session_state:
        st.session_state.roi_mode = False

    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/lightning-bolt.png", width=60)
        st.markdown("## D-ESS Workspace MVP")

        st.markdown("### 1. Global Settings")
        st.session_state.view_mode = st.radio(
            "View Mode",
            ["Client View", "Internal Audit View"],
            index=0 if st.session_state.view_mode == "Client View" else 1,
        )

        st.markdown("### 1.5 Calculation Mode")
        mode = st.radio(
            "Engine Pipeline",
            ["Subsidy Audit", "ROI MVP (PV Yield)"],  # LOW-01 FIX (2026-04-02): removed Chinese labels
            index=1 if st.session_state.roi_mode else 0
        )
        st.session_state.roi_mode = "ROI MVP" in mode

        available_policies = [f for f in os.listdir(policies_dir) if f.endswith(".json")]
        if not available_policies:
            st.error("No policy JSON files found in the policies directory.")
            st.stop()
        if "dus_balcony_pv.json" in available_policies:
            idx = available_policies.index("dus_balcony_pv.json")
        else:
            idx = 0
        st.session_state.selected_policy = st.selectbox("Policy Engine", available_policies, index=idx)
        st.text_input("Jurisdiction (Locked)", value="DE.NRW.DUS", disabled=True)
        st.text_input("Project Type (Locked)", value="BALCONY_PV", disabled=True)
        st.session_state.advanced_mode = st.toggle("Advanced Mode (Show Anchors & Trace)", value=False)

        st.markdown("### 2. Actions")
        if st.button("Reset Case", type="primary", use_container_width=True):
            st.session_state.current_case_input = {}
            st.session_state.current_report = None
            st.session_state.demo_case_selected = None
            st.session_state.intake_state = {}
            st.session_state.confirm_phase = False
            st.session_state.active_view = VIEW_INTAKE
            st.rerun()

        st.markdown("### 3. Demo & Golden Cases")
        render_demo_loader()

    st.title("D-ESS: Zero-Inference Subsidy Solver")

    current_view = st.radio(
        "Workspace View",
        VIEWS,
        index=VIEWS.index(st.session_state.active_view),
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state.active_view = current_view

    if current_view == VIEW_INTAKE:
        if st.session_state.roi_mode:
            render_roi_intake_form()
        else:
            render_intake_form()
    elif current_view == VIEW_REPORT:
        report = st.session_state.get("current_report")
        if report and report.get("roi_result"):
            render_roi_report(report)
        else:
            render_report_preview()
    elif current_view == VIEW_TRACE:
        render_trace_view()
    elif current_view == VIEW_EXPORT:
        render_export_view()
