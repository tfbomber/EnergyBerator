import streamlit as st
import os
import json
from ui.adapter import run_dess_engine

def render_roi_intake_form():
    st.subheader("ROI MVP: 热泵家庭光伏收益估算 (极简输入版)")
    st.info("💡 系统将根据 6 个核心选项，自动调用基准政策与经验参数得出 20 年财务测算。")

    col1, col2 = st.columns(2)
    
    with col1:
        household_size = st.selectbox(
            "1. 人口规模 (Household Size)", 
            options=["1", "2", "3", "4", "5"],
            index=2 # Default 3
        )
        
        hp_mode = st.radio(
            "2. 热泵信息输入模式 (HP Input Mode)",
            options=["MODE_A (按年用电区间)", "MODE_B (按居住面积区间)"],
            index=1 # Default Mode B
        )
        mode_token = "MODE_A" if "MODE_A" in hp_mode else "MODE_B"
        
        heating_area_band = st.selectbox(
            "3. 建筑供暖面积/热泵区间",
            options=["100_150"],
            index=0
        )

    with col2:
        st.text_input("4. 地区 (Region)", value="Neuss/41470", disabled=True)
        
        financing_enabled = st.checkbox(
            "5. 启用融资计算 (Financing Enabled)", 
            value=True,
            help="开启后将根据 CAPEX 自动测算 100% 贷款、10年期的月供与现金流模型。"
        )
        
        electric_vehicle = st.selectbox(
            "6. 新能源车规划 (EV Planning)",
            options=["NONE", "PLAN", "YES"],
            index=0
        )

    st.markdown("---")
    
    if st.button("🚀 开始 ROI 估算 (Run ROI MVP)", type="primary", use_container_width=True):
        # Build Case Payload for ROI
        case_data = {
            "case_id": f"ROI_{household_size}P_{heating_area_band}_EV_{electric_vehicle}",
            "attributes": {
                "has_heat_pump": True,
                "has_pv": False,
                "household_size": household_size,
                "hp_input_mode": mode_token,
                "hp_bucket": heating_area_band,
                "financing_enabled": financing_enabled,
                "electric_vehicle": electric_vehicle
            },
            "_dess_version": "V3.5"
        }
        
        policies_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "policies")
        policy_path = os.path.join(policies_dir, "roi_hp_mvp_neuss_2026.json")
        
        with st.spinner("正在进行全整数化 ROI 模拟计算..."):
            report = run_dess_engine(case_data, policy_path)
            st.session_state.engine_report = report
            st.session_state.current_report = report
            st.session_state.project_state = "S2"
            st.rerun()

    st.caption("注：计算采用全整数逻辑，避免浮点误差，确保结果可复现且符合保守性原则。")
