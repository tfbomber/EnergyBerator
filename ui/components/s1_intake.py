import streamlit as st
import os
import json
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from ui.adapter import run_dess_engine, business_json_to_case_payload
from ui.components.test_generator import json_to_white_talk

def load_spec():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec_path = os.path.join(base_dir, "specs", "intake_question_tree_v0_1.json")
    with open(spec_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize_amount(raw: str) -> tuple[str, list[str]]:
    notices = []
    s = raw.strip()
    if not s:
        return "", []
    if "," in s and "." not in s:
        normalized = s.replace(",", ".")
        notices.append(f"已将欧式小数逗号转换为点号：{s} -> {normalized}")
        s = normalized
    
    if " " in s:
        raise ValueError("Amount contains space")
    if ("," in s and "." in s) or (s.count(".") > 1):
        raise ValueError("Thousands separator not allowed")
        
    try:
        d = Decimal(s)
        if d < 0:
            raise ValueError("NEGATIVE_NOT_ALLOWED")
        if "." in s:
            dp = len(s.split(".")[1])
            if dp > 2:
                raise ValueError("Too many decimals")
        return (str(d.quantize(Decimal("0.01"))) if "." in s else str(d), notices)
    except InvalidOperation:
        raise ValueError("Invalid decimal format")

def build_payload(state_answers: dict) -> dict:
    payload = {
        "project_type": state_answers.get("Q0_PROJECT_TYPE", "PLEASE_SELECT"),
        "attributes": {
            "bonuses": []
        },
        "costs": {
            "currency": "EUR",
            "buckets": {}
        },
        "timeline_events": [],
        "_unknowns_answered": []
    }

    ans_bus = state_answers.get("Q1_IS_BUSINESS")
    if ans_bus == "YES":
        payload["attributes"]["is_business"] = True
    elif ans_bus == "NO":
        payload["attributes"]["is_business"] = False
    elif ans_bus == "UNKNOWN":
        payload["_unknowns_answered"].append("A.IS_BUSINESS")

    ans_dp = state_answers.get("Q2_HAS_DUESSELPASS")
    if ans_dp == "YES":
        payload["attributes"]["bonuses"].append("DUESSELPASS")
    elif ans_dp == "UNKNOWN":
        payload["_unknowns_answered"].append("A.BONUS.DUESSELPASS")

    ans_consult = state_answers.get("Q10_HAS_ENERGY_CONSULT_PROOF")
    if ans_consult == "YES":
        payload["attributes"]["ENERGY_CONSULT_PROOF"] = True
    elif ans_consult == "NO":
        payload["attributes"]["ENERGY_CONSULT_PROOF"] = False
    elif ans_consult == "UNKNOWN":
        payload["_unknowns_answered"].append("A.ENERGY_CONSULT_PROOF")
        
    def add_event(key, ev_type):
        ans = state_answers.get(key)
        if ans and not isinstance(ans, str) and getattr(ans, "year", None):
            payload["timeline_events"].append({"event_type": ev_type, "date": ans.isoformat()})

    add_event("Q3_APPLICATION_DATE", "APPLICATION_SUBMITTED")
    add_event("Q4_CONTRACT_DATE", "CONTRACT_SIGNED")
    add_event("Q5_WORK_START_DATE", "WORK_STARTED")
    
    order = {"APPLICATION_SUBMITTED": 1, "CONTRACT_SIGNED": 2, "WORK_STARTED": 3}
    payload["timeline_events"].sort(key=lambda x: order.get(x["event_type"], 99))
    
    # Hardware
    hw_amt = state_answers.get("Q6_HARDWARE_AMOUNT_val")
    hw_unk = state_answers.get("Q6_HARDWARE_AMOUNT_unk")
    if hw_unk:
        payload["_unknowns_answered"].append("C.HARDWARE.AMOUNT")
        payload["_unknowns_answered"].append("C.HARDWARE.BASIS")
    else:
        if hw_amt:
            try:
                norm_amt, _ = normalize_amount(hw_amt)
                if "HARDWARE" not in payload["costs"]["buckets"]: payload["costs"]["buckets"]["HARDWARE"] = {}
                payload["costs"]["buckets"]["HARDWARE"]["amount"] = norm_amt
            except ValueError:
                pass
        hw_basis = state_answers.get("Q7_HARDWARE_BASIS")
        if hw_basis and hw_basis != "UNKNOWN":
            if "HARDWARE" not in payload["costs"]["buckets"]: payload["costs"]["buckets"]["HARDWARE"] = {}
            payload["costs"]["buckets"]["HARDWARE"]["amount_basis"] = hw_basis
        
        hw_cert = state_answers.get("Q6_HARDWARE_AMOUNT_certainty")
        if hw_cert:
            if "HARDWARE" not in payload["costs"]["buckets"]: payload["costs"]["buckets"]["HARDWARE"] = {}
            payload["costs"]["buckets"]["HARDWARE"]["certainty"] = hw_cert
        elif hw_amt:
            if "HARDWARE" not in payload["costs"]["buckets"]: payload["costs"]["buckets"]["HARDWARE"] = {}
            payload["costs"]["buckets"]["HARDWARE"]["certainty"] = "CONTRACT"
        elif hw_basis == "UNKNOWN" and hw_amt:
            payload["_unknowns_answered"].append("C.HARDWARE.BASIS")

    # Labor
    lb_amt = state_answers.get("Q8_LABOR_AMOUNT_val")
    lb_unk = state_answers.get("Q8_LABOR_AMOUNT_unk")
    if lb_unk:
        payload["_unknowns_answered"].append("C.LABOR.AMOUNT")
        payload["_unknowns_answered"].append("C.LABOR.BASIS")
    else:
        if lb_amt:
            try:
                norm_amt, _ = normalize_amount(lb_amt)
                if "LABOR" not in payload["costs"]["buckets"]: payload["costs"]["buckets"]["LABOR"] = {}
                payload["costs"]["buckets"]["LABOR"]["amount"] = norm_amt
            except ValueError:
                pass
        lb_basis = state_answers.get("Q9_LABOR_BASIS")
        if lb_basis and lb_basis != "UNKNOWN":
            if "LABOR" not in payload["costs"]["buckets"]: payload["costs"]["buckets"]["LABOR"] = {}
            payload["costs"]["buckets"]["LABOR"]["amount_basis"] = lb_basis
        
        lb_cert = state_answers.get("Q8_LABOR_AMOUNT_certainty")
        if lb_cert:
            if "LABOR" not in payload["costs"]["buckets"]: payload["costs"]["buckets"]["LABOR"] = {}
            payload["costs"]["buckets"]["LABOR"]["certainty"] = lb_cert
        elif lb_amt:
            if "LABOR" not in payload["costs"]["buckets"]: payload["costs"]["buckets"]["LABOR"] = {}
            payload["costs"]["buckets"]["LABOR"]["certainty"] = "CONTRACT"
        elif lb_basis == "UNKNOWN" and lb_amt:
            payload["_unknowns_answered"].append("C.LABOR.BASIS")

    return payload

def compute_completeness(payload: dict, spec: dict) -> tuple:
    must_haves = spec["completeness_rules"]["must_haves"]
    nice_to_haves = spec["completeness_rules"]["nice_to_haves"]
    unknowns = set(payload.get("_unknowns_answered", []))
    blockers = []
    mh_score = 0
    nh_score = 0

    if any(e["event_type"] == "APPLICATION_SUBMITTED" for e in payload["timeline_events"]):
        mh_score += 1
    if any(e["event_type"] == "CONTRACT_SIGNED" for e in payload["timeline_events"]):
        mh_score += 1
    if any(e["event_type"] == "WORK_STARTED" for e in payload["timeline_events"]):
        mh_score += 1

    hw_amount_answered = "amount" in payload["costs"]["buckets"].get("HARDWARE", {})
    if hw_amount_answered:
        mh_score += 1
    elif "C.HARDWARE.AMOUNT" in unknowns:
        mh_score += 1
        blockers.append("C.HARDWARE.AMOUNT (Unknown — 将阻断精确计算)")

    hw_basis_answered = "amount_basis" in payload["costs"]["buckets"].get("HARDWARE", {})
    if hw_basis_answered:
        mh_score += 1
    elif "C.HARDWARE.BASIS" in unknowns:
        mh_score += 1
        blockers.append("C.HARDWARE.BASIS (Unknown — 将阻断精确计算)")

    lb_amount_answered = "amount" in payload["costs"]["buckets"].get("LABOR", {})
    if lb_amount_answered:
        mh_score += 1
    elif "C.LABOR.AMOUNT" in unknowns:
        mh_score += 1
        blockers.append("C.LABOR.AMOUNT (Unknown — 将阻断精确计算)")

    lb_basis_answered = "amount_basis" in payload["costs"]["buckets"].get("LABOR", {})
    if lb_basis_answered:
        mh_score += 1
    elif "C.LABOR.BASIS" in unknowns:
        mh_score += 1
        blockers.append("C.LABOR.BASIS (Unknown — 将阻断精确计算)")

    if "is_business" in payload["attributes"]:
        nh_score += 1
    elif "A.IS_BUSINESS" in unknowns:
        nh_score += 1
        blockers.append("A.IS_BUSINESS (Unknown — Bonus 路径待定)")

    if "DUESSELPASS" in payload["attributes"].get("bonuses", []):
        nh_score += 1
    elif "A.BONUS.DUESSELPASS" in unknowns:
        nh_score += 1
        blockers.append("A.BONUS.DUESSELPASS (Unknown — 无法触发 Düsselpass Bonus)")

    energy_proof = payload["attributes"].get("ENERGY_CONSULT_PROOF")
    if energy_proof is not None:
        nh_score += 1
    elif "A.ENERGY_CONSULT_PROOF" in unknowns:
        nh_score += 1
        blockers.append("A.ENERGY_CONSULT_PROOF (Unknown — Düsselpass 特殊档 80%/800€ 无法确认)")

    total_mh = len(must_haves)
    total_nh = len(nice_to_haves)
    score = min(1.0, (mh_score / total_mh) * 0.7 + (nh_score / total_nh) * 0.3)
    return score, mh_score, total_mh, nh_score, total_nh, blockers

def render_risk_warnings(payload):
    events = {e["event_type"]: e["date"] for e in payload.get("timeline_events", [])}
    app_date = events.get("APPLICATION_SUBMITTED")
    con_date = events.get("CONTRACT_SIGNED")
    wrk_date = events.get("WORK_STARTED")
    
    if con_date and app_date and con_date < app_date:
        st.error("🚨 事实提示：合同签署 早于 申请提交，可能触发 Vorhabenbeginn（先签后申）红线导致驳回。此提示仅供参考，生成报告后将由 Core Engine 最终判定。")
    if wrk_date and app_date and wrk_date < app_date:
        st.error("🚨 事实提示：开工日期 早于 申请提交，可能触发 Vorhabenbeginn（先开工后申）红线导致驳回。此提示仅供参考，生成报告后将由 Core Engine 最终判定。")
    if wrk_date and con_date and wrk_date < con_date:
        st.warning("🟠 事实提示：开工日期 早于 合同签署，这在常识上时间线可能不一致，请与安装商或业主确认。")

def render_json_intake(spec):
    st.subheader("🤖 JSON Case Import (业务级逻辑导入)")
    st.info("💡 粘贴业务级 JSON 事实协议，系统将自动提炼关键点并交由引擎审计。")
    
    json_text = st.text_area("粘贴 JSON 协议", height=200, 
                             placeholder='{"case_id": "...", "applicant": {...}, ...}',
                             key="s1_json_input")
    
    if json_text:
        try:
            data = json.loads(json_text)
            payload = business_json_to_case_payload(data)
            st.markdown("---")
            st.markdown("#### 🔍 业务事实预审 (提炼自 JSON)")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**1. Project Core**")
                st.code(f"TYPE: {payload.get('project_type')}")
                st.markdown("**2. Entity Rules**")
                attr = payload.get("attributes", {})
                ent = "Enterprise" if attr.get("is_business") else "Private"
                dp = "YES" if "DUESSELPASS" in attr.get("bonuses", []) else "NO"
                st.code(f"ENTITY: {ent}\nDUESSELPASS: {dp}")
            
            with col2:
                st.markdown("**3. Timing (Events)**")
                for ev in payload.get("timeline_events", []):
                    st.code(f"{ev['event_type']}: {ev['date']}")
                st.markdown("**4. Costs**")
                hw = payload["costs"]["buckets"].get("HARDWARE", {})
                st.code(f"HARDWARE: {hw.get('amount')} EUR ({hw.get('amount_basis')})")

            score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, spec)
            st.markdown(f"**Data Completeness:** {int(score*100)}%")
            st.progress(score)
            st.caption(f"Must: {mh_c}/{mh_t} | Nice: {nh_c}/{nh_t}")
            
            if blockers:
                with st.expander(f"⚠️ {len(blockers)} 个缺失字段（阻断精确核定）"):
                    for b in blockers: st.markdown(f"- `{b}`")
            
            render_risk_warnings(payload)

            st.markdown("---")
            if st.button("🚀 确认并直接执行物理隔绝审计", type="primary", use_container_width=True):
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                pol_path = os.path.join(base_dir, "policies", st.session_state.get("selected_policy", "dus_balcony_pv.json"))
                with st.spinner("D-ESS Engine: 正在执行引擎审计..."):
                    report = run_dess_engine(payload, pol_path)
                st.session_state.current_case_input = payload
                st.session_state.current_report = report
                hist_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "policy": st.session_state.get("selected_policy", "dus_balcony_pv.json"),
                    "status": report.get("status", "UNKNOWN"),
                    "amount": report.get("subsidy_total_eur", "N/A")
                }
                if "history" not in st.session_state: st.session_state.history = []
                st.session_state.history.insert(0, hist_entry)
                st.session_state.active_view = "📊 Report Preview"
                st.rerun()
                
        except json.JSONDecodeError:
            st.error("❌ 无效的 JSON 格式。")
        except Exception as e:
            st.error(f"❌ 解析/执行失败: {str(e)}")

def render_intake_form():
    spec = load_spec()
    st.header("Case Intake (S1)")
    st.markdown("Please provide facts securely. *Missing data is acceptable and will resolve dynamically via Core Engine.*")
    
    input_mode = st.toggle("🤖 使用 Business JSON 协议快速导入", value=False)
    if input_mode:
        render_json_intake(spec)
        return

    if "intake_state" not in st.session_state:
        st.session_state.intake_state = {}
    if "confirm_phase" not in st.session_state:
        st.session_state.confirm_phase = False

    if st.session_state.confirm_phase:
        st.subheader("📝 Confirm Facts (摘要确认)")
        st.info("生成官方审计报告前，请核实即将被送入引擎进行物理隔绝计算的参数流。")
        payload = build_payload(st.session_state.intake_state)
        st.json(payload)
        render_risk_warnings(payload)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ Edit Inputs", use_container_width=True):
                st.session_state.confirm_phase = False
                st.rerun()
        with col2:
            if st.button("✅ Confirm & Generate Audit Report", type="primary", use_container_width=True):
                st.session_state.current_case_input = payload
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                pol_path = os.path.join(base_dir, "policies", st.session_state.selected_policy)
                with st.spinner("Executing D-ESS Engine strictly..."):
                    report = run_dess_engine(payload, pol_path)
                st.session_state.current_report = report
                hist_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "policy": st.session_state.selected_policy,
                    "status": report.get("status", "UNKNOWN"),
                    "amount": report.get("subsidy_total_eur", "N/A")
                }
                st.session_state.history.insert(0, hist_entry)
                if len(st.session_state.history) > 3:
                    st.session_state.history.pop()
                st.session_state.confirm_phase = False
                st.session_state.active_view = "📊 Report Preview"
                st.rerun()
        return

    with st.form("intake_form"):
        st.subheader("1. Project Core")
        q0 = spec["questions"][0]
        q0_options = [o["value"] for o in q0["options"]]
        q0_labels = {o["value"]: o["text"] for o in q0["options"]}
        selected_project_type = st.selectbox(q0["label"], q0_options, format_func=lambda x: q0_labels[x], index=0)
        st.session_state.intake_state[q0["id"]] = selected_project_type
        if selected_project_type == "PLEASE_SELECT":
            st.warning("⚠️ 请先选择项目类型，系统将据此加载评估逻辑。")
        st.caption(q0["help"])
        
        st.subheader("2. Entity Rules")
        q1 = spec["questions"][1]
        st.session_state.intake_state[q1["id"]] = st.radio(q1["label"], [o["value"] for o in q1["options"]], format_func=lambda x: next(o["text"] for o in q1["options"] if o["value"]==x), index=2)
        st.caption(q1["help"])
        
        q2 = spec["questions"][2]
        q2_ans = st.radio(q2["label"], [o["value"] for o in q2["options"]], format_func=lambda x: next(o["text"] for o in q2["options"] if o["value"]==x), index=2)
        st.session_state.intake_state[q2["id"]] = q2_ans
        st.caption(q2["help"])

        if q2_ans == "YES":
            st.info("ℹ️ **Düsselpass 特殊档说明（仅提示，不裁决）**")
            st.session_state.intake_state["Q10_HAS_ENERGY_CONSULT_PROOF"] = st.radio(
                "是否有 Energiesparberatung 证明？",
                ["YES", "NO", "UNKNOWN"],
                format_func=lambda x: {"YES": "是", "NO": "否", "UNKNOWN": "我不知道"}[x],
                index=2
            )
        else:
            st.session_state.intake_state["Q10_HAS_ENERGY_CONSULT_PROOF"] = "NO"
        
        st.subheader("3. Timing (Critical)")
        for q in spec["questions"][3:6]:
            col1, col2 = st.columns([3, 1])
            with col1: st.session_state.intake_state[q["id"]] = st.date_input(q["label"], value=None)
            with col2:
                unk = st.checkbox(f"Unknown", key=q["id"]+"_unk")
                if unk: st.session_state.intake_state[q["id"]] = None
        
        st.subheader("4. Costs Definitions")
        col1, col2, col3 = st.columns(3)
        q_hw_amt = spec["questions"][6]
        q_hw_bas = spec["questions"][7]
        with col1:
            raw_hw = st.text_input(q_hw_amt["label"])
            if raw_hw:
                norm, notices = normalize_amount(raw_hw)
                st.session_state.intake_state[q_hw_amt["id"]+"_val"] = raw_hw
        with col2: st.session_state.intake_state[q_hw_bas["id"]] = st.selectbox(q_hw_bas["label"], [o["value"] for o in q_hw_bas["options"]], format_func=lambda x: next(o["text"] for o in q_hw_bas["options"] if o["value"]==x), index=2)
        with col3:
            if st.checkbox(f"Unknown HW", key="hw_unk"): st.session_state.intake_state[q_hw_amt["id"]+"_unk"] = True
            else:
                st.session_state.intake_state[q_hw_amt["id"]+"_unk"] = False
                st.session_state.intake_state[q_hw_amt["id"]+"_certainty"] = "ESTIMATE" if not raw_hw else "CONTRACT"
                
        col1, col2, col3 = st.columns(3)
        q_lb_amt = spec["questions"][8]
        q_lb_bas = spec["questions"][9]
        with col1:
            raw_lb = st.text_input(q_lb_amt["label"])
            if raw_lb:
                norm, notices = normalize_amount(raw_lb)
                st.session_state.intake_state[q_lb_amt["id"]+"_val"] = raw_lb
        with col2: st.session_state.intake_state[q_lb_bas["id"]] = st.selectbox(q_lb_bas["label"], [o["value"] for o in q_lb_bas["options"]], format_func=lambda x: next(o["text"] for o in q_lb_bas["options"] if o["value"]==x), index=2)
        with col3:
            if st.checkbox(f"Unknown LB", key="lb_unk"): st.session_state.intake_state[q_lb_amt["id"]+"_unk"] = True
            else:
                st.session_state.intake_state[q_lb_amt["id"]+"_unk"] = False
                st.session_state.intake_state[q_lb_amt["id"]+"_certainty"] = "ESTIMATE" if not raw_lb else "CONTRACT"

        submitted = st.form_submit_button("Review Facts", type="primary")

    if not st.session_state.confirm_phase:
        payload = build_payload(st.session_state.intake_state)
        render_risk_warnings(payload)

    if submitted:
        st.session_state.confirm_phase = True
        st.rerun()
