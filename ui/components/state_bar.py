import streamlit as st

def render_state_bar():
    st.markdown("<div class='state-bar'>", unsafe_allow_html=True)
    
    state = st.session_state.project_state
    light = st.session_state.compliance_light
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.markdown(f"**State ID:** `{state}`")
        if state == "S0": st.markdown("意向评估期 (Intent)")
        elif state == "S1": st.markdown("资料准备期 (Preparation)")
        elif state == "S2": st.markdown("方案决断期 (Path Selection)")
        elif state == "S3": st.markdown("递交申请中 (Applying)")
        elif state == "S4": st.markdown("合同签署期 (Contracting)")
        elif state == "S5": st.markdown("施工核销期 (Auditing)")
        
    # E2E Link: Override light based on real engine status
    engine_report = st.session_state.get("engine_report", {})
    if engine_report:
        rpt_sts = engine_report.get("status", "")
        if "REJECTED" in rpt_sts or "BLOCKED" in rpt_sts:
            light = "RED"
        elif "PROVISIONAL" in rpt_sts or "NEEDS" in rpt_sts:
            light = "YELLOW"
        else:
            light = "GREEN"
            
    with col2:
        if light == "GREEN":
            st.markdown("🚦 **合规红绿灯:** <span class='green-light'>GREEN (允许前行)</span>", unsafe_allow_html=True)
        elif light == "YELLOW":
            st.markdown("🚦 **合规红绿灯:** <span class='yellow-light'>YELLOW (可推进但结果待确认)</span>", unsafe_allow_html=True)
        else:
            st.markdown("🚦 **合规红绿灯:** <span class='red-light'>RED (政策红线阻断/违规操作)</span>", unsafe_allow_html=True)
            
        if state in ["S2", "S3", "S4", "S5"]:
            st.markdown("🌟 **当前方案评分 (Score):** `95` (Excellent)")
            
    with col3:
        if state == "S1":
            st.progress(20, "资料完整度: 20%")
        elif state == "S2":
            st.progress(40, "资料完整度: 100% | 方案待选")
        elif state == "S3":
            st.progress(60, "审批进度: 城市已提交")
        else:
            st.progress(5, "项目建立中")
            
    st.markdown("</div>", unsafe_allow_html=True)
