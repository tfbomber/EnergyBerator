import streamlit as st


def set_view_and_nav(view_name, nav_func, target=None):
    st.session_state.workspace_view = view_name
    if target and nav_func:
        nav_func(target)


def render_navigator(navigate_to):

    # ================================================================
    # SECTION 1 — DATA INTAKE
    # ================================================================
    st.markdown("#### 📥 Data Intake")

    is_prop = st.session_state.get("workspace_view", "PROPERTY") == "PROPERTY"

    st.button(
        "📄 1. 项目概览 (Overview)",
        use_container_width=True,
        type="primary" if st.session_state.project_state in ["S0", "S1"] and is_prop else "secondary",
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, None),
    )
    st.button(
        "📝 2. 资料输入 (Input Facts)",
        use_container_width=True,
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, None),
    )
    st.markdown("- 🏠 房屋信息")
    st.markdown("- ⚡ 项目类型 (PV/WP)")
    st.markdown("- 💶 报价单/合同")

    st.markdown("**补贴路径 (自动衍生)**")
    st.checkbox("KfW 458 联邦计划", value=True, disabled=True)
    st.checkbox("BAFA 联邦计划 (可选)", value=False, disabled=True)
    st.checkbox("Düsseldorf 地方计划", value=True, disabled=True)

    st.markdown("**输出模块**")
    st.button(
        "⏳ 合规时间线 (Timeline)",
        use_container_width=True,
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, None),
    )
    st.button(
        "📊 报告与导出 (Report)",
        use_container_width=True,
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, "Report"),
    )

    st.divider()

    # ================================================================
    # SECTION 2 — CORE ANALYSIS (Internal)
    # ================================================================
    st.markdown("#### 🔬 Core Analysis")

    is_neuss = st.session_state.get("workspace_view") == "NEUSS_MVP"
    st.button(
        "📍 诺伊斯 MVP (Neuss Target)",
        use_container_width=True,
        type="primary" if is_neuss else "secondary",
        on_click=set_view_and_nav, args=("NEUSS_MVP", navigate_to, None),
    )

    is_foundation = st.session_state.get("workspace_view") == "FOUNDATION_FILTER"
    st.button(
        "🏗️ Foundation Filter (结构筛查)",
        use_container_width=True,
        type="primary" if is_foundation else "secondary",
        on_click=set_view_and_nav, args=("FOUNDATION_FILTER", navigate_to, None),
    )

    is_l2review = st.session_state.get("workspace_view") == "LAYER2_REVIEW"
    st.button(
        "🔍 Layer 2 Review (排名预览)",
        use_container_width=True,
        type="primary" if is_l2review else "secondary",
        on_click=set_view_and_nav, args=("LAYER2_REVIEW", navigate_to, None),
    )

    is_general = st.session_state.get("workspace_view") == "GENERAL_WORKSPACE"
    st.button(
        "📊 General Track Workspace",
        use_container_width=True,
        type="primary" if is_general else "secondary",
        on_click=set_view_and_nav, args=("GENERAL_WORKSPACE", navigate_to, None),
    )

    is_street_ranking = st.session_state.get("workspace_view") == "STREET_RANKING"
    st.button(
        "🏘 PV Street Ranking (Internal)",
        use_container_width=True,
        type="primary" if is_street_ranking else "secondary",
        on_click=set_view_and_nav, args=("STREET_RANKING", navigate_to, None),
    )

    st.divider()

    # ================================================================
    # SECTION 3 — CUSTOMER VIEW
    # ================================================================
    st.markdown("#### 👤 Customer View")

    is_client_ranking = st.session_state.get("workspace_view") == "CLIENT_STREET_RANKING"
    st.button(
        "🏘 PV Street Ranking (Kunde)",
        use_container_width=True,
        type="primary" if is_client_ranking else "secondary",
        on_click=set_view_and_nav, args=("CLIENT_STREET_RANKING", navigate_to, None),
    )

    is_client_roi = st.session_state.get("workspace_view") == "CLIENT_ROI_REPORT"
    st.button(
        "📄 ROI Bericht (Kunde)",
        use_container_width=True,
        type="primary" if is_client_roi else "secondary",
        on_click=set_view_and_nav, args=("CLIENT_ROI_REPORT", navigate_to, None),
    )

    st.divider()
    st.button(
        "👈 返回 Quick Scan",
        use_container_width=True,
        on_click=set_view_and_nav, args=("PROPERTY", navigate_to, "Landing"),
    )
