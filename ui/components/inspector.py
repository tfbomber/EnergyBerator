import streamlit as st

def render_inspector():
    st.markdown("<div class='inspector-panel'>", unsafe_allow_html=True)
    st.markdown("### 🔎 Inspector")
    st.caption("D-ESS 证据追溯引擎面板")
    
    state = st.session_state.project_state
    
    if state == "S2":
        report = st.session_state.get("current_report", {})
        if not report:
            st.info("No report to inspect yet.")
            return
            
        # Dynamically fetch values from math_trace
        math_trace = report.get("math_trace", {})
        eligible_cents = math_trace.get("eligible_cost_total_cents", 0)
        total_cents = report.get("subsidy_total_cents", 0)
        
        # City vs Federal (Assume city is report total for now, or fetch from audit)
        city_cents = total_cents
        kfw_cents = 0 # Baseline assumption: no other subsidies provided in simple UI demo
        
        # Check for stacking info in audit trail
        stacking_step = next((s for s in report.get("audit_trail", []) if s.get("step_id") == "STACKING_VALIDATION"), {})
        stacking_desc = stacking_step.get("description", "No deduction needed")
        # Extract percentage (e.g., "Max 60%") via simple regex or logic
        import re
        pct_match = re.search(r"Max (\d+)%", stacking_desc)
        pct = int(pct_match.group(1)) if pct_match else 100
        limit_cents = (eligible_cents * pct) // 100
        
        # Düsseldorf raw calculation (before stacking)
        # In simple solver cases, this is city_cents if no stacking applied, or solver's raw input
        # Let's just find the last NON-stacking calculation
        raw_calc_step = next((s for s in report.get("audit_trail", []) if s.get("step_id") == "SUBSIDY_CALCULATION"), {})
        # Note: raw_calc_step might have been capped by base cap, but let's just use city_cents for display
        
        eligible_eur = eligible_cents / 100
        total_eur = total_cents / 100
        kfw_eur = kfw_cents / 100
        city_raw_eur = city_cents / 100 # Simplification for demo
        limit_eur = limit_cents / 100
        current_total_eur = kfw_eur + city_raw_eur
        
        is_blocked = math_trace.get("grant_status") == "BLOCKED_BY_REDLINE"
        
        if total_eur == 0 and not is_blocked:
            st.info("💡 **Inspector Note**\n\nThis case is currently evaluated in **PV-only baseline mode**. No municipal subsidy or KfW grant has been applied in the baseline scenario.\n\nValues shown as **0.00 €** mean one of the following:\n- Subsidy logic not activated\n- Subsidy not applicable to this scenario\n- Subsidy reserved for another path / future extension\n\nThese values do NOT indicate calculation failure.")
        
        if is_blocked:
            blocked_by = math_trace.get("blocked_by", ["Unknown Redline"])
            st.markdown(f"#### ⛔ Plan A 核心解释: 资格丧失 (0.00 €)")
            st.error(f"**金额归零原因：触发红线 Gate 拦截**\n\n您触发了不可逆的自动拒绝项: `{', '.join(blocked_by)}`。")
            st.info("此拦截独立于费用数学计算 (Kumulierungsgrenze)。因为核心合规门禁未通过，直接截断补贴。")
            
            with st.expander("INFORMATIONAL ONLY: 若合规本可获得多少 (IF ELIGIBLE)"):
                st.code(f"""[Düsseldorf 理论计算源 Tracker]
Total Cost: {eligible_eur:,.2f} €
KfW 458 Share: {kfw_eur:,.2f} €
Düsseldorf Raw Calculation: {city_raw_eur:,.2f} €
Max Allowed Subsidy: {eligible_eur:,.2f} * {pct}% = {limit_eur:,.2f} €
Is {current_total_eur:,.2f} <= {limit_eur:,.2f} ? {'YES' if current_total_eur <= limit_eur else 'NO'}.
If Eligible Theoretical City Share: {limit_eur if current_total_eur > limit_eur else city_raw_eur:,.2f} €""")
        else:
            st.markdown(f"#### 👉 Plan A 核心解释 ({total_eur:,.2f} €)")
            st.markdown("**1. 这笔钱由于 Kumulierungsgrenze (叠加限制) 是怎么算出来的？**")
            st.code(f"""[Düsseldorf 计算源 Tracker]
Total Cost: {eligible_eur:,.2f} €
KfW 458 Share: {kfw_eur:,.2f} €
Düsseldorf Raw Calculation: {city_raw_eur:,.2f} €
Max Allowed Subsidy: {eligible_eur:,.2f} * {pct}% = {limit_eur:,.2f} €
Current Total: {kfw_eur:,.2f} + {city_raw_eur:,.2f} = {current_total_eur:,.2f} €
Is {current_total_eur:,.2f} <= {limit_eur:,.2f} ? {'YES' if current_total_eur <= limit_eur else 'NO'}. ({'No deduction needed' if current_total_eur <= limit_eur else 'Capped to limit'})
Estimated Düsseldorf Share (Provisional): {total_eur:,.2f} €""")
        
        st.markdown("**2. 什么是条件合同？**")
        st.info("“aufschiebende Bedingung” 是一种免责条款，证明该合同只有在拿到补贴承诺后才生效，因此不被视为“提前开工(Vorhabenbeginn)”。")
        st.markdown("🔗 [Richtlinie 19.303, Punkt 4.1](https://www.duesseldorf.de/fileadmin/...)")
        st.caption("版本: [Stand 12.12.2024]")
        
    elif state == "S3":
        st.markdown("#### ⛔ 红线规则解释 (Vorhabenbeginn)")
        st.error("“Vorhabenbeginn（提前开工阻断）”是德国补贴最严格的条款。若在申请前就签订了具备法律约束力的供货安装合同，补贴资格将永久丧失。")
        st.markdown("🔗 **审计依据:** ")
        st.markdown("`DUS_HEAT_PUMP_2025` -> `timing_rules.blocking_actions.CONTRACT_SIGNED`")
        
    else:
        st.write("点击画布左侧的下划线名词或感叹号，此处将自动显示计算公式与 PDF 原始文段锚点。")
        
    st.markdown("</div>", unsafe_allow_html=True)
