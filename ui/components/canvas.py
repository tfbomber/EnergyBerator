import streamlit as st
import os
import sys
from datetime import datetime
from ui.adapter import business_json_to_case_payload, run_dess_engine
from ui.components.s1_roi_intake import render_roi_intake_form
from ui.components.s2_roi_report import render_roi_report

def render_canvas():
    """
    D-ESS Main Canvas: Operates in two primary modes:
    - Module 2: Plan (Quick orientation & Redlines)
    - Module 3: Audit (Detailed evidence & Compliance check)
    """
    if "project_state" not in st.session_state:
        st.session_state.project_state = "S1"
    
    state = st.session_state.project_state
    
    # Global Disclaimer
    st.caption("⚠️ Orientation only / requires manual verification / based on last known rules.")

    if state == "S1":
        render_intake_view()
    elif state == "S2":
        render_report_view()
    else:
        # Fallback for legacy states S3-S5
        st.markdown(f"### 📍 项目进行中 (状态: {state})")
        st.info("该阶段正在根据 v1.1 规范进行模块化对接。")
        if st.button("返回工作台"):
            st.session_state.project_state = "S1"
            st.rerun()

def render_intake_view():
    st.markdown("### 🏗️ D-ESS 数据录入 (Data Intake)")
    
    # Toggle for Mode
    # Use session state to remember mode across reruns
    if "ui_mode" not in st.session_state:
        st.session_state.ui_mode = "Module 2: Plan (极速推演)"
        
    mode = st.radio("选择操作模式", ["Module 2: Plan (极速推演)", "Module 3: Audit (项目审计)", "ROI MVP (光伏收益)"], 
                    index=0 if "Plan" in st.session_state.ui_mode else (1 if "Audit" in st.session_state.ui_mode else 2),
                    horizontal=True)
    st.session_state.ui_mode = mode
    is_audit = "Audit" in mode
    is_roi = "ROI" in mode

    if is_roi:
        render_roi_intake_form()
        return
        
    with st.form("intake_form"):
        # 2. General Project Meta
        col1, col2 = st.columns(2)
        with col1:
            policy_id = st.selectbox("选择补贴政策", ["DUS_BALCONY_PV_2025", "DUS_HEAT_PUMP_2025"])
            applicant_type = st.selectbox("申请人属性 (Private)", ["UNKNOWN", "YES", "NO"])
            has_duessepass = st.selectbox("是否持有 DüssePass（社会福利卡）?", ["UNKNOWN", "YES", "NO"])
        with col2:
            as_of = st.date_input("分析基准日 (As of)", value=datetime(2026, 2, 28))
            case_id = st.text_input("项目编号 (Case ID)", value=f"PRJ-{datetime.now().strftime('%Y%m%d')}")

        st.markdown("---")
        
        # 3. Timing Ledger (State Machine Input)
        st.markdown("##### 📅 时间轴核查 (Timing Ledger)")
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            app_date = st.text_input("申请递交日期 (dd.mm.yyyy 或 ISO)", placeholder="如: 01.03.2026")
            contract_date = st.text_input("合同签署日期", placeholder="如: 10.02.2026")
        with t_col2:
            is_cond = st.selectbox("是否包含【附条件条款】(Conditional Clause)?", ["UNKNOWN", "YES", "NO"])
            down_made = st.selectbox("是否已发生付款 (Down Payment Made)?", ["UNKNOWN", "YES", "NO"])
            payment_date = st.text_input("付款日期 (若无则不填)", placeholder="如: 10.02.2026")
            work_started = st.selectbox("是否已开工 (Work Started)?", ["UNKNOWN", "YES", "NO"])
            work_start_date = st.text_input("开工日期 (若无则不填)", placeholder="如: 12.02.2026")

        st.markdown("---")
        
        # 4. Costs Entry (Module 2 vs 3 Logic)
        st.markdown("##### 💶 费用与开销 (Costs)")
        cost_mode = "QUICK"
        total_estimate = 0.0
        itemized_items = []
        
        if not is_audit:
            # Plan Mode: Quick Estimate preferred
            cost_choice = st.radio("费用录入方式", ["快速估算 (Quick)", "精确明细 (Exact)"], horizontal=True)
            if cost_choice == "快速估算 (Quick)":
                cost_mode = "QUICK"
                total_estimate = st.number_input("硬件设备估算总价 (€)", min_value=0.0, value=1000.0, step=10.0)
            else:
                cost_mode = "EXACT"
                st.info("Plan精确模式 (MVP简易版): 输入单项硬件金额。")
                hw_val = st.number_input("硬件单项金额 (Exact HW)", value=1000.0)
                itemized_items = [{"label": "Hardware Item", "amount_eur": hw_val, "is_eligible": "YES"}]
        else:
            # Audit Mode: Force Exact / Itemized
            cost_mode = "EXACT"
            st.warning("Audit 模式要求录入精确的费用清单。")
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1: label = st.text_input("费用描述", value="PV Pack V1")
            with c2: amount = st.text_input("金额 (€)", value="1.099,00")
            with c3: elig = st.checkbox("合规 (Eligible)", value=True)
            itemized_items = [{"label": label, "amount_eur": amount, "is_eligible": "YES" if elig else "NO"}]

        st.markdown("---")
        
        # 5. Evidence Checklist (Module 3 only)
        if is_audit:
            st.markdown("##### 📑 审计证据链 (Evidence Checklist)")
            st.checkbox("已上传合同副本 (CONTRACT_COPY)", value=False)
            st.checkbox("已上传申请回执 (APPLICATION_RECEIPT)", value=False)
            st.text_area("备注 (Audit Notes)", placeholder="填写异常说明...")

        submitted = st.form_submit_button("执行智能审计 / 推演方案", type="primary")
        
        if submitted:
            # Map Stable Key to Filename
            policy_file_map = {
                "DUS_BALCONY_PV_2025": "dus_balcony_pv.json",
                "DUS_HEAT_PUMP_2025": "dus_heat_pump.json"
            }
            physical_policy = policy_file_map.get(policy_id, "dus_balcony_pv.json")
            
            # Prepare Business JSON
            business_json = {
                "case_id": case_id,
                "as_of": as_of.isoformat(),
                "policy_id": policy_id, # Keep stable key in JSON
                "applicant": {
                    "is_private_person": applicant_type,
                    "has_duessepass": has_duessepass
                },
                "costs": {
                    "mode": cost_mode,
                    "total_estimate_eur": total_estimate
                },
                "timeline": {
                    "application_submitted_date": app_date if app_date else None,
                    "contract_signed_date": contract_date if contract_date else None,
                    "has_conditional_clause": is_cond,
                    "down_payment_made": down_made,
                    "down_payment_date": payment_date if payment_date else None,
                    "work_started": work_started,
                    "work_started_date": work_start_date if work_start_date else None
                },
                "measure": {"type": "BALCONY_PV"}
            }
            
            # Only exact mode gets items
            if cost_mode == "EXACT":
                business_json["costs"]["items"] = itemized_items
                
            if is_audit:
                business_json["evidence_pack"] = {
                    "contract": {"status": "UNKNOWN", "ref": None},
                    "invoice": {"status": "UNKNOWN", "ref": None},
                    "receipt": {"status": "UNKNOWN", "ref": None}
                }
            
            # 1. Adapter Mapping
            case_payload = business_json_to_case_payload(business_json)
            st.session_state.last_payload = case_payload
            
            # 2. Engine Execution
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            policy_path = os.path.join(base_dir, "policies", physical_policy)

            
            with st.spinner("D-ESS Engine Running..."):
                report = run_dess_engine(case_payload, policy_path)
            
            st.session_state.business_json = business_json
            st.session_state.engine_report = report
            st.session_state.current_report = report # Fix Inspector binding
            st.session_state.current_case_input = case_payload # Fix Copilot binding
            st.session_state.project_state = "S2"
            st.rerun()

def render_report_view():
    report = st.session_state.get("engine_report", {})
    payload = st.session_state.get("last_payload", {})
    business_json = st.session_state.get("business_json", {})
    
    if not report:
        st.error("无法加载报告数据。")
        if st.button("重新录入"):
            st.session_state.project_state = "S1"
            st.rerun()
        return

    is_roi = "ROI" in st.session_state.get("ui_mode", "") or report.get("roi_result")
    if is_roi:
        render_roi_report(report)
        st.divider()
        if st.button("⬅️ 返回修改参数", key="roi_back"):
            st.session_state.project_state = "S1"
            st.rerun()
        return

    # --- 0. 免责声明 ---
    # Moved to Verdict Banner / PROVISIONAL_MATH area to avoid duplication

    # --- 1. Project Summary 简表 ---
    meta = report.get("report_meta", {})
    st.divider()
    st.markdown("#### 📋 项目概览 (Project Summary)")
    ps_col1, ps_col2, ps_col3, ps_col4 = st.columns(4)
    ps_col1.markdown(f"**政策:**\n`{report.get('policy_id', 'N/A')}`") # Fix policy ID read
    ps_col2.markdown(f"**基准日:**\n`{meta.get('as_of', report.get('as_of', 'N/A'))}`")
    
    # Try to resolve project type from payload format v1.1 or v1.2
    proj_type = payload.get('project_type') or payload.get('measure', {}).get('type', 'UNKNOWN')
    ps_col3.markdown(f"**项目类型:**\n`{proj_type}`")
    ps_col4.markdown(f"**城市:**\n`Düsseldorf`")

    # --- 2. Verdict Banner ---
    status = report.get("status", "UNKNOWN")
    violations = report.get("violations", [])
    
    if status == "APPROVED_PROVISIONAL":
        st.warning(f"### 🟡 YELLOW（可推进但结果待确认）\n判定结论: APPROVED_PROVISIONAL")
    elif "APPROVED" in status:
        st.success(f"### ✅ GREEN — 当前事实符合基准条件\n判定结论: {status}")
    elif "ON HOLD" in status:
        st.info(f"### 🟣 ON HOLD — 判定挂起\n判定结论: {status}")
    elif "REJECTED" in status or "FAIL" in status or "BLOCKED" in status:
        st.error(f"### 🔴 RED — 触发合规红线\n判定结论: {status}")
    elif "NEEDS_" in status:
        st.warning(f"### 🟡 YELLOW — 信息缺失或不确定\n判定结论: {status}")
    else:
        st.warning(f"判定结论: {status}")
        
    # Range or Missing Facts display for Plan mode
    has_range = any(f.get("reason_code_raw") == "PROVISIONAL_RANGE" for f in report.get("findings", getattr(report, "findings", [])))
    if has_range:
        st.warning("**🟡 动作暗示 (Action Suggested)**\n您持有 DüsselPass 但尚未提供能源咨询证明 (Energiesparberatung)。已为您展示保守与乐观区间的双轨估算。后续阶段请补充证明以锁定更高金额。")
        
    if "NEEDS_" in status:
        missing_facts = []
        for f in report.get("violations", []) + report.get("findings", getattr(report, "findings", [])):
            if f.get("missing_facts") and isinstance(f.get("missing_facts"), list):
                missing_facts.extend(f.get("missing_facts"))
        if "missing_facts" in report and isinstance(report.get("missing_facts"), list):
            missing_facts.extend(report["missing_facts"])
            
        missing_facts = list(set(missing_facts))
        if missing_facts:
            st.error("**⚠️ 动作要求 (Action Required)**\n系统因关键信息缺失无法进行估算。您必须补充以下维度：")
            for mf in missing_facts:
                label = mf
                if mf == "ENERGY_CONSULT_PROOF": label = "ENERGY_CONSULT_PROOF (Energiesparberatung 证明)"
                elif mf == "application_submitted_date": label = "申请递交日期 (Application Date)"
                st.markdown(f"- **缺失项**: `{label}`")

    is_provisional = any(v.get("code") == "PROVISIONAL_MATH" for v in violations)
    if is_provisional:
        st.caption("🔶 **PROVISIONAL MATH**: 当前金额为快速估算，非精确合规数字")

    # --- 3. Math Metrics ---
    math = report.get("math_trace", {})
    eligible_eur = math.get("eligible_cost_total_cents", 0) / 100
    potential_eur = math.get("potential_subsidy_cents", 0) / 100
    
    prov_suffix = " (~)" if is_provisional else ""

    is_rejected = "REJECTED" in status or "BLOCKED" in status
    
    col1, col2, col3 = st.columns(3)
    col1.metric("合规总费用 (Eligible)", f"{eligible_eur:,.2f} €{prov_suffix}")
    
    if is_rejected:
        col2.metric("城市补贴估算 (Grant)", "0.00 €", delta="- Blocked by Redline", delta_color="inverse")
    else:
        col2.metric("城市补贴估算 (Grant)", f"{potential_eur:,.2f} €{prov_suffix}", help="封顶线 Cap: 600 €")
        
        # Display Graceful Range for DüsselPass
        prange = math.get("provisional_range")
        if prange:
            opt = prange.get("optimistic_cents", 0) / 100
            cons = prange.get("conservative_cents", 0) / 100
            col2.markdown(f'''
            <div style="font-size: 0.85em; margin-top: -10px; color: #666;">
            <b>假设已完成咨询 (Potential):</b> <span style="color:#0f52ba;">{opt:,.2f} €</span><br>
            <b>假设未完成咨询 (Conservative):</b> <span>{cons:,.2f} €</span>
            </div>
            ''', unsafe_allow_html=True)
    
    final_locked = math.get("final_locked", False)
    if final_locked:
        final_eur = math.get("final_subsidy_cents", 0) / 100
        col3.metric("最终补贴金额 (Final)", f"{final_eur:,.2f} €{prov_suffix}")
    else:
        # Plan mode: Final should be —, numeric should be implicitly null mapped via metric
        col3.metric("最终补贴金额 (Final)", "—", help="Plan mode: not locked yet")

    # Standard Tier Fallback Info
    is_biz_unknown = payload.get("attributes", {}).get("is_business") == "UNKNOWN"
    if is_biz_unknown:
        st.info("📋 申请人身份信息未提供，已使用 **Standard Tier（保守档）** 估算。\n若持有 DüssePass 或符合其他资格，补贴金额可能更高。")

    # --- 3.1 Delta Table (Audit Only) ---
    delta = report.get("delta")
    if delta and delta.get("delta_cents", 0) > 0:
        st.markdown("#### 📉 补贴剪刀差 (Delta Analysis)")
        d_col1, d_col2, d_col3 = st.columns(3)
        d_col1.markdown(f"**💡 理想路径:**\n{delta['ideal_final_cents']/100:,.2f} €")
        d_col2.markdown(f"**📂 实际判定:**\n{delta['actual_final_cents']/100:,.2f} €")
        d_col3.markdown(f"**📉 差值 Delta:**\n<span style='color:red; font-weight:bold;'>-{delta['delta_cents']/100:,.2f} €</span>", unsafe_allow_html=True)
        
        codes = delta.get("reason_codes", [])
        if codes:
            st.caption(f"触发原因: {' | '.join([f'`{c}`' for c in codes])}")

    # --- 4. Redline Execution Box ---
    st.markdown("#### 🛡️ 合规操作指引 (Redlines)")
    is_paused = "PAUSED" in status or "ON HOLD" in status
    is_rejected = "REJECTED" in status
    has_high = any(v.get("severity") == "HIGH" or "REJECT" in v.get("code", "") for v in violations)
    has_med = any(v.get("severity", "MED") == "MED" for v in violations)
    needs_input = "NEEDS_INPUT" in status

    if is_paused:
        st.info("🟣 **ON HOLD**: 政策修订中，暂停签约/付款/开工。请等待官方进一步通知。")
    elif is_rejected or has_high:
        st.error("⛔ **FORBIDDEN**: 当前存在合规红线违规，请勿继续签约或执行付款。")
    elif needs_input:
        st.warning("🔘 **CAUTION (信息缺失)**: 存在未知事实，无法完成完整推演。请补充关键信息。")
    elif has_med:
        st.warning("⚠️ **CAUTION**: 存在次要合规风险，建议补充证明材料后再决定是否签署。")
    else:
        st.success("✅ **ALLOWED**: 当前事实符合基准要求，可继续推进申请流程。")
    
    st.caption("⚠ Orientation only / requires manual verification / based on last known rules.")

    # --- 4.1 Remedy & Plan B (Audit Only) ---
    remedy = report.get("remedy")
    if remedy:
        st.markdown("#### ✏️ 合规补救与备选方案 (Remedy)")
        can_fix = remedy.get("can_fix", "UNKNOWN")
        if can_fix == True:
            st.success("✅ **此案可救**: 按照以下步骤操作可能追回补贴。")
        elif can_fix == "UNKNOWN":
            st.warning("🔘 **补救性未知**: 需人工介入确认。")
        else:
            st.error("❌ **无法补救**: 当前红线在当前政策框架下不可逆。")
            
        for step in remedy.get("steps", []):
            st.checkbox(step, key=f"remedy_{step[:10]}")
            
        if remedy.get("plan_b_options"):
            with st.expander("📂 查看备选方案 (Plan B)"):
                for pb in remedy["plan_b_options"]:
                    st.markdown(f"- {pb}")
        st.caption("⚠ 所有补救措施须经政策局人工确认。D-ESS 不构成法律或财务建议。")

    # --- 5. Violations List ---
    HIGH_vs = [v for v in violations if v.get("severity") == "HIGH" or "REJECT" in v.get("code", "")]
    MED_vs  = [v for v in violations if v.get("severity", "MED") == "MED" and v not in HIGH_vs]
    LOW_vs  = [v for v in violations if v not in HIGH_vs and v not in MED_vs]

    for v in HIGH_vs:
        with st.expander(f"🔴 {v['code']}", expanded=True):
            st.write(v["message"])
    for v in MED_vs:
        with st.expander(f"🟡 {v['code']}", expanded=False):
            st.write(v["message"])
    for v in LOW_vs:
        with st.expander(f"🔵 {v['code']}", expanded=False):
            st.write(v["message"])

    if not violations:
        st.success("✅ No violations found. Proceed with caution and verify locally.")

    # --- 6. Next Steps ---
    st.markdown("#### 🗺️ 下一步操作 (Next Steps)")
    if "APPROVED" in status:
        steps = [
            "① 等待申请日到来，提前及开工/付款将导致永久拒绝",
            "② 向 Düsseldorf 市政局提交官方申请",
            "③ 收到官方受理回执 (Eingangsbestätigung) 后再签署安装合同",
            "④ 保留所有购买凭据、发票与施工过程照片",
            "⑤ 完工后凭发票与交付证明申请最终拨款"
        ]
    elif "REJECTED" in status:
        steps = [
            "① 识别违规根因（参见上方红线详情）",
            "② 评估是否具备补救可能（如联系商户修改合同条款）",
            "③ 如不可救，评估 KfW 联邦替代方案",
            "④ 监测下一轮政策窗口开放时间"
        ]
    elif "NEEDS_INPUT" in status:
        steps = [
            "① 补充页面缺失的时间轴或身份信息",
            "② 切换至 Audit 模式进行详细核查并附上备注",
            "③ 重新执行智能推演"
        ]
    else:
        steps = ["① 等待政策局官方通知后再行决策"]

    for s in steps:
        st.markdown(f"- {s}")

    # --- 7. Evidence Checklist (Light) ---
    st.markdown("#### 📑 证据核查 (Evidence)")
    evidence_items = [
        ("合同副本 (Contract)", "contract"),
        ("发票/收据 (Invoice)", "invoice"),
        ("申请回执 (Application Receipt)", "receipt"),
    ]
    evidence_pack = business_json.get("evidence_pack", {})

    e_cols = st.columns(3)
    for i, (label, key) in enumerate(evidence_items):
        with e_cols[i]:
            # Use evidence_pack from business_json (collected in S1) or report metadata
            e_status = evidence_pack.get(key, {}).get("status", "UNKNOWN")
            if e_status == "YES":
                st.success(f"✅ {label}")
            elif e_status == "NO":
                st.error(f"❌ {label}")
            else:
                st.markdown(f"🔘 **{label}**")
                if "Audit" in st.session_state.get("ui_mode", ""):
                    st.caption("⚠️ 缺失审计证据")

    # --- 8. Audit Trace (Traceability) ---
    trace = report.get("trace")
    if trace:
        with st.expander("🔍 审计溯源 (Audit Trace)", expanded=False):
            st.markdown(f"**Policy Hash**: `{trace.get('policy_hash', 'N/A')}`")
            st.markdown(f"**Case ID**: `{trace.get('case_id', 'N/A')}`")
            st.markdown(f"**As Of**: `{trace.get('as_of', 'N/A')}`")
            if trace.get("overlay_gate_applied"):
                st.warning("⚠️ **RUNTIME OVERLAY APPLIED**: 本报告包含动态干预逻辑。")
            st.code(trace.get("calculation_trace_summary", "No trace available"), language="text")

    # --- Footer / Actions ---
    st.divider()
    col_back, col_reset, col_export = st.columns(3)
    with col_back:
        if st.button("⬅️ 修改输入数据"):
            st.session_state.project_state = "S1"
            st.rerun()
    with col_reset:
        if st.button("🔄 重置所有输入", type="secondary"):
            # Clear relevant session state keys
            keys_to_clear = [
                "project_state", "ui_mode", "last_payload", "business_json",
                "engine_report", "current_report", "current_case_input"
            ]
            for k in keys_to_clear:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
    with col_export:
        import json
        report_json = json.dumps(report, indent=2, ensure_ascii=False)
        st.download_button(
            label="💾 导出原始报告 JSON",
            data=report_json,
            file_name=f"dess_report_{meta.get('case_id','unknown')}.json",
            mime="application/json"
        )
