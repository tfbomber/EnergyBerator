import streamlit as st
import time

def render_landing(navigate_to):
    st.title("⚡ D-Energy Berater System (D-ESS)")
    st.subheader("从问 AI 政策，升级为让系统带你正确完成补贴项目。")
    
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### 核心特权
        - 💰 **多拿补贴**：自动计算最优叠加路径 (市级 + 州级 + 联邦 KfW)
        - 🛑 **不踩红线**：防呆状态机拦截“先签约”等致命错误
        - ⏱️ **省时省力**：自动解析报价单，免除手工翻阅 PDF 烦恼
        - 🛡️ **绝对放心**：结论精确到分，并附带 100% 官方文件页码锚点留痕
        """)
        
        st.markdown("### Quick Scan 快速评估")
        with st.form("quick_scan_form"):
            user_intent = st.text_area("用一句话描述你想做什么？", placeholder="例如：我在杜塞尔多夫，想在2026年4月装个热泵，大概花3万欧...")
            plz = st.text_input("项目邮编 (PLZ)", value="40210")
            
            submit = st.form_submit_button("开始评估", type="primary")
            
            if submit:
                with st.spinner("引擎初筛中 (匹配本地政策与状态机)..."):
                    time.sleep(1) # simulate engine
                    st.success("初筛完成！存在大量可用补贴（最高覆盖 60%）。请进入工作台执行下一步。")
                    st.session_state.project_id = "PRJ-DUS-202602"
                    st.session_state.project_state = "S1"
                    time.sleep(0.5)
                    navigate_to("Workspace")
                    
    with col2:
        st.info("""
        **System Status**
        - Policy Engine: `V2.1 (Industrial)`
        - Düsseldorf KWA: `Active`
        - KfW 458: `Active`
        - Engine Mode: `Strict Schema (Decimals)`
        """)
