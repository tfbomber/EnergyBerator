import streamlit as st
import copy
import os
import json
from ui.adapter import run_dess_engine

def render_demo_loader():
    st.write("Run predefined test cases to quickly simulate different verdicts.")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cases_dir = os.path.join(base_dir, "cases")
    
    available_cases = [f for f in os.listdir(cases_dir) if f.endswith("_input.json")]
    available_cases.sort()

    if not available_cases:
        st.info("No golden case input files found in /cases.")
        return
    
    selected_case = st.selectbox("Select Golden Case", available_cases)
    
    if st.button("Run Golden Case", use_container_width=True):
        case_path = os.path.join(cases_dir, selected_case)
        try:
            with open(case_path, "r", encoding="utf-8") as f:
                case_data = json.load(f)

            policy_name = st.session_state.get("selected_policy", "dus_balcony_pv.json")
            policy_path = os.path.join(base_dir, "policies", policy_name)
            if not os.path.exists(policy_path):
                st.error(f"Selected policy file not found: {policy_name}")
                return

            st.session_state.current_case_input = case_data

            with st.spinner(f"Running {selected_case}..."):
                report = run_dess_engine(copy.deepcopy(case_data), policy_path)

            st.session_state.current_report = report
            st.session_state.demo_case_selected = case_data
            st.session_state.active_view = "📊 Report Preview"
            st.success(f"Case {selected_case} executed. Redirecting to Report Preview...")
        except Exception as e:
            st.error(f"Failed to load case: {e}")
