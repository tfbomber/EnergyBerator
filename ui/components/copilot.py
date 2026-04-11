import streamlit as st

def render_copilot():
    st.markdown("<div class='copilot-chat'>", unsafe_allow_html=True)
    
    # Get context from session state
    case_input = st.session_state.get("current_case_input", {})
    project_type = case_input.get("project_type", "UNKNOWN")
    report = st.session_state.get("current_report", {})
    status = report.get("status", "S1") # Default to S1 if no report
    
    # Decide context message
    eligible_eur = report.get("math_trace", {}).get("eligible_cost_total", 0.0)
    st.caption(f"当前上下文限定: 杜塞尔多夫 | 项目类型 {project_type} | 预算 {eligible_eur:,.2f}€")
    
    if "REJECTED" in status or "BLOCKED" in status:
        st.error("🚨 Copilot 侦测到致命红线拦截！")
        
        # 1. Filter out info level / deduplicate
        violations = report.get("violations", [])
        high_violations = [v for v in violations if v.get("severity") in ["HIGH", "REJECTED", "BLOCKED", "INELIGIBLE_REJECTED"]]
        if not high_violations:
            high_violations = violations # fallback
            
        if high_violations:
            worst = high_violations[0] # Take the most severe
            code = worst.get("code", "UNKNOWN")
            
            # Extract real dates
            events = case_input.get("timeline_events", [])
            payment_date = next((e.get("date") for e in events if e.get("event_type") in ["FIRST_PAYMENT_MADE", "PAYMENT_MADE"]), "未知")
            work_started_date = next((e.get("date") for e in events if e.get("event_type") == "WORK_STARTED"), "未知")
            contract_date = next((e.get("date") for e in events if e.get("event_type") == "CONTRACT_SIGNED"), "未知")
            app_date = next((e.get("date") for e in events if e.get("event_type") == "APPLICATION_SUBMITTED"), "未知")
            
            # Custom message based on code
            if "VORHABENBEGINN" in code or code in ["PAYMENT_BINDING", "WORK_STARTED_BINDING"]:
                if code == "PAYMENT_BINDING" or "payment" in code.lower():
                    violating_date = payment_date
                    event_name = "PAYMENT_MADE"
                elif "contract" in code.lower() or code == "VORHABENBEGINN_BEFORE_APPLICATION":
                    violating_date = contract_date
                    event_name = "CONTRACT_SIGNED"
                else:
                    violating_date = work_started_date
                    event_name = "WORK_STARTED"
                
                # Check conditionality for contracts
                is_cond = False
                if event_name == "CONTRACT_SIGNED":
                    contract_event = next((e for e in events if e.get("event_type") == "CONTRACT_SIGNED"), {})
                    is_cond = contract_event.get("is_conditional", False)
                
                # Try to calculate delta_days if both dates look like ISO dates (at least 10 chars)
                delta_str = ""
                if len(violating_date) >= 10 and len(app_date) >= 10 and violating_date != "未知" and app_date != "未知":
                    try:
                        from datetime import datetime
                        v_date = datetime.fromisoformat(violating_date[:10])
                        a_date = datetime.fromisoformat(app_date[:10])
                        delta_days = (a_date - v_date).days
                        if delta_days > 0:
                            delta_str = f" is {delta_days} days before Application {app_date[:10]}"
                    except:
                        pass
                
                if event_name == "CONTRACT_SIGNED":
                    st.markdown(f"**Copilot (分析结果)**: 被认定为 Vorhabenbeginn 的风险事件：合同签署（无豁免条款）。")
                    st.error(f"Contract signed {violating_date[:10]}{delta_str}.")
                    if not is_cond:
                        st.markdown("这违反了先批后建的红线原则。注意：您的合同未勾选/未声明附带“aufschiebende Bedingung”（特定豁免条款）。")
                else:
                    st.markdown(f"**Copilot (分析结果)**: 系统探测到您在未获批前已触发了实质性开工行为（Vorhabenbeginn）。")
                    st.error(f"{event_name} on {violating_date[:10]}{delta_str}.")
                    st.markdown("这违反了先批后建的红线原则。")
            else:
                st.markdown(f"**Copilot (分析结果)**: 触发红线 `{code}`。{worst.get('message', '')}")
                
            st.markdown("""
            *建议行动 (Remedy)*: 该红线在现行政策下通常不可逆转，**本项目已丧失获取联邦/市政直接补贴的资格**。
            
            **[可尝试的补救措施（需人工协助并与市政局确认）]**:
            1. 撤销/作废旧合同证据。
            2. 重新签订新合同，且**必须**包含 `aufschiebende Bedingung`（附条件条款）。
            3. 询问具有审批权的市政部门是否接受该补救方案。
            
            如果补救失败，请直接执行 **Plan B（税收抵扣路径）**。
            """)
    else:
        # Mock chat history
        st.markdown("**User**: 我现在能签合同吗？安装商催我了。")
        
        # Determine stage logic (S1/S2/S3)
        findings = report.get("findings", getattr(report, "findings", []))
        has_conditional_pass = any(f.get("reason_code_raw") == "CONDITIONAL_CLAUSE" for f in findings)
        
        if has_conditional_pass and "VORHABENBEGINN_PASS" in [f.get("reason_code_raw") for f in findings]:
            st.markdown("""
            **Copilot**: 🟡 **条件允许 (Conditional OK)**。
            在此阶段您允许签合同，但**必须要带有附加的免责条款** (aufschiebende Bedingung)。
            
            *条款提醒*：请确保合同里写明：“本合同仅在获得杜塞尔多夫或相关机构的资助承诺(Zusage)后才正式生效”。
            """)
        elif status in ["NEEDS_INFO", "NEEDS_INPUT", "APPROVED", "S1", "S2"]:
            st.markdown("""
            **Copilot**: 🔴 **不要签**。
            您当前处于 `方案决断期`，尚未获得 KfW 或 Düsseldorf 城市的资金承诺信（Zusage）。
            如果立刻签署不具备“特定豁免条款”的无条件合同，您将**构成提前开工 (Vorhabenbeginn) 并永久丧失资金**。
            
            *建议行动*：请在主画布锁定您的方案，前往 `S3 申请阶段` 获取申请批号。如果安装商催得很急，请使用“附条件合同”专用话术。
            """)
        elif status in ["NEEDS_INFO", "NEEDS_INPUT"]:
            # Gather missing facts
            missing_facts = []
            for v in report.get("violations", []):
                if v.get("missing_facts"):
                    missing_facts.extend(v["missing_facts"])
            missing_facts = list(set(missing_facts))
            
            if missing_facts:
                mf_str = ", ".join(missing_facts)
                st.markdown(f"**Copilot**: 🟡 **无法推演**。你缺少关键信息 `{mf_str}`。")
                st.markdown(f"*建议行动*：由于 D-ESS 遵循 Zero-Inference 零猜测原则，我们无法为您凭空捏造该证明文件状态。请返回左侧面板补充该字段。")
            else:
                st.markdown("**Copilot**: 🟡 **无法推演，存在未知数据**。")
        else:
            st.markdown("**Copilot**: 🟢 **可以签约**。您已进入 S4/S5 阶段，无“提前开工”违规风险。")
        
    # Dynamic examples based on project type
    example_placeholder = "向 Copilot 提问当前项目的合规难题..."
    if project_type == "BALCONY_PV":
        example_placeholder = "例如：插座式光伏需要电表更换吗？"
    elif "HEAT_PUMP" in project_type:
        example_placeholder = "例如：我的热泵 JAZ 只有 2.9 能拿钱吗？"
        
    st.text_input("Ask Copilot...", placeholder=example_placeholder)
    
    st.markdown("</div>", unsafe_allow_html=True)
