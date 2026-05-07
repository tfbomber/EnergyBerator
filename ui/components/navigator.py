import streamlit as st
from ui.i18n import t, render_lang_switcher


def set_view_and_nav(view_name, nav_func, target=None):
    st.session_state.workspace_view = view_name
    if target and nav_func:
        nav_func(target)


def render_navigator(navigate_to):

    # ================================================================
    # SECTION 1 — DATA INTAKE
    # ================================================================
    st.markdown(t("nav.section_intake"))

    is_prop = st.session_state.get("workspace_view", "PROPERTY") == "PROPERTY"

    st.button(
        t("nav.overview"),
        use_container_width=True,
        type="primary" if st.session_state.project_state in ["S0", "S1"] and is_prop else "secondary",
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, None),
    )
    st.button(
        t("nav.input_facts"),
        use_container_width=True,
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, None),
    )
    st.markdown(t("nav.house_info"))
    st.markdown(t("nav.project_type"))
    st.markdown(t("nav.quote"))

    st.markdown(t("nav.subsidy_path"))
    st.checkbox(t("nav.kfw"),           value=True,  disabled=True)
    st.checkbox(t("nav.bafa"),          value=False, disabled=True)
    st.checkbox(t("nav.city_programme"), value=True, disabled=True)

    st.markdown(t("nav.output_modules"))
    st.button(
        t("nav.timeline"),
        use_container_width=True,
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, None),
    )
    st.button(
        t("nav.report"),
        use_container_width=True,
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, "Report"),
    )

    st.divider()

    # ================================================================
    # SECTION 2 — CORE ANALYSIS (Internal)
    # ================================================================
    st.markdown(t("nav.section_analysis"))

    is_neuss = st.session_state.get("workspace_view") == "NEUSS_MVP"
    st.button(
        t("nav.neuss_mvp"),
        use_container_width=True,
        type="primary" if is_neuss else "secondary",
        on_click=set_view_and_nav, args=("NEUSS_MVP", navigate_to, None),
    )

    is_foundation = st.session_state.get("workspace_view") == "FOUNDATION_FILTER"
    st.button(
        t("nav.foundation_filter"),
        use_container_width=True,
        type="primary" if is_foundation else "secondary",
        on_click=set_view_and_nav, args=("FOUNDATION_FILTER", navigate_to, None),
    )

    is_l2review = st.session_state.get("workspace_view") == "LAYER2_REVIEW"
    st.button(
        t("nav.layer2_review"),
        use_container_width=True,
        type="primary" if is_l2review else "secondary",
        on_click=set_view_and_nav, args=("LAYER2_REVIEW", navigate_to, None),
    )

    is_general = st.session_state.get("workspace_view") == "GENERAL_WORKSPACE"
    st.button(
        t("nav.general_workspace"),
        use_container_width=True,
        type="primary" if is_general else "secondary",
        on_click=set_view_and_nav, args=("GENERAL_WORKSPACE", navigate_to, None),
    )

    is_street_ranking = st.session_state.get("workspace_view") == "STREET_RANKING"
    st.button(
        t("nav.street_ranking_internal"),
        use_container_width=True,
        type="primary" if is_street_ranking else "secondary",
        on_click=set_view_and_nav, args=("STREET_RANKING", navigate_to, None),
    )

    st.divider()

    # ================================================================
    # SECTION 3 — CUSTOMER VIEW
    # ================================================================
    st.markdown(t("nav.section_customer"))

    is_client_ranking = st.session_state.get("workspace_view") == "CLIENT_STREET_RANKING"
    st.button(
        t("nav.street_ranking_customer"),
        use_container_width=True,
        type="primary" if is_client_ranking else "secondary",
        on_click=set_view_and_nav, args=("CLIENT_STREET_RANKING", navigate_to, None),
    )

    is_client_roi = st.session_state.get("workspace_view") == "CLIENT_ROI_REPORT"
    st.button(
        t("nav.roi_report_customer"),
        use_container_width=True,
        type="primary" if is_client_roi else "secondary",
        on_click=set_view_and_nav, args=("CLIENT_ROI_REPORT", navigate_to, None),
    )

    st.divider()
    st.button(
        t("app.back_scan"),
        use_container_width=True,
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, "Landing"),
    )

    # ================================================================
    # LANGUAGE SWITCHER — pinned at bottom of sidebar
    # ================================================================
    st.divider()
    render_lang_switcher()
