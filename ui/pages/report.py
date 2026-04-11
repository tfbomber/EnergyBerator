import streamlit as st

def render_report(navigate_to):
    st.title("📊 D-ESS 项目交付大屏 (Report & Handoff)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🧑‍💼 向客户交付 (B2C View)")
        st.info("""
        **尊敬的客户，您的补贴执行计划已生成：**
        
        您可以从这套价值 30,000 € 的热泵/光伏升级计划中，通过我们的精确申报，**无风险获取 12,750 € 的现金返还**。
        
        #### 下一步行动 (Action Items)
        1. 签名并反馈《附条件供销合同》附件A。
        2. 配合提供房产证扫描件。
        
        您的顾问已经为您排除了“提前开工违规”、“叠加总额超出 60% 上限”等一切潜在地雷。
        """)
        st.button("📥 下载精简版 PDF", type="primary")
        
        st.markdown("#### 🤝 安装商/顾问协作 (Collaboration)")
        st.info("将此项目链接分享给您的专属安装商，他们可直接在此工作台上为您填报设备参数与排期。")
        st.button("🔗 生成加密协作邀请链接")

    with col2:
        st.markdown("### 🏛️ 审计局与后端存档 (B2B Audit View)")
        st.warning("""
        **[CONFIDENTIAL] 核心合规溯源报告**
        
        **Engine Run Hash:** `def6793d2b...`
        **Timestamp:** `2026-02-21T10:00Z`
        **Rule Base:** `DUS_HEAT_PUMP_2025` & `KFW_458_2024`
        
        **Compliance Assertions:**
        - `Vorhabenbeginn Check`: PASS (Override active via KfW Aufschiebende Bedingung). Evidence Anchor -> `19.303 Punkt 4.1`
        - `Kumulierung Check`: PASS. Max allowed subsidy = Base(30K) * 0.6 = 18K. Proposed sum (12.75K) < 18K. 
        """)
        st.button("📥 导出 JSON 原始快照")
        
    st.markdown("---")
    st.button("👈 返回工作台 Canvas", on_click=lambda: navigate_to("Workspace"))
