import streamlit as st
from ui.components.state_bar import render_state_bar
from ui.components.navigator import render_navigator
from ui.components.canvas import render_canvas
from ui.components.inspector import render_inspector
from ui.components.copilot import render_copilot
from ui.components.test_generator import render_test_generator

def render_workspace(navigate_to):
    # 0. State Init
    if "workspace_view" not in st.session_state:
        st.session_state.workspace_view = "PROPERTY"

    # 1. Navigator (Left Sidebar)
    with st.sidebar:
        st.markdown("### D-ESS Navigator 🧭")
        render_navigator(navigate_to)

    if st.session_state.workspace_view == "PROPERTY":
        # 2. State Bar (Top)
        render_state_bar()

        st.markdown("---")

        # 3. Canvas & Inspector (Main Columns)
        # Give canvas 70% width, inspector 30% width
        col_canvas, col_inspector = st.columns([7, 3])
        
        with col_canvas:
            render_canvas()
            
        with col_inspector:
            render_inspector()
            
        st.markdown("---")
        
        # 4. Copilot & Test Generator (Bottom)
        with st.expander("🤖 D-ESS Copilot (当前项目防呆助手)", expanded=True):
            render_copilot()

        with st.expander("🧪 测试用例快捷生成器 (JSON ➔ 白话双向协议)", expanded=False):
            render_test_generator()
            
    elif st.session_state.workspace_view == "NEUSS_MVP":
        from ui.components.opportunity_mvp import render_opportunity_mvp
        render_opportunity_mvp()

    elif st.session_state.workspace_view == "FOUNDATION_FILTER":
        from ui.pages.foundation import render_foundation_filter
        render_foundation_filter()

    elif st.session_state.workspace_view == "GENERAL_WORKSPACE":
        from ui.general_workspace import render_general_workspace
        render_general_workspace()

    elif st.session_state.workspace_view == "LAYER2_REVIEW":
        from ui.components.layer2_review import render_layer2_review
        render_layer2_review()

    elif st.session_state.workspace_view == "STREET_RANKING":
        from ui.components.street_ranking_view import render_street_ranking_view
        render_street_ranking_view()

    elif st.session_state.workspace_view == "STREET_ROI_FULL":
        # Full ROI report launched from the global street ranking compact card
        from ui.components.s2_roi_report import render_roi_report
        context = st.session_state.get("street_roi_context", "Straßenprofil")
        report  = st.session_state.get("street_roi_report", {})

        # Back navigation bar
        col_back, col_title = st.columns([1, 6])
        with col_back:
            if st.button("← Zurück zur Rangfolge", use_container_width=True):
                st.session_state.workspace_view = "STREET_RANKING"
                st.rerun()
        with col_title:
            st.markdown(
                f"<small style='color:#666;'>Vollbericht für: <strong>{context}</strong></small>",
                unsafe_allow_html=True,
            )

        st.markdown("---")
        render_roi_report(report)


