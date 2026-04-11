import streamlit as st
import json
import pandas as pd
from datetime import datetime

def render_trace_view():
    st.header("Evidence & Trace (Internal S2)")
    
    if st.session_state.view_mode != "Internal Audit View":
        st.info("🔒 This view is restricted to Internal Auditors. Please switch 'View Mode' in the sidebar.")
        return
        
    report = st.session_state.current_report
    if not report:
        st.info("👈 No report generated yet.")
        return
        
    st.subheader("System Metadata")
    st.code(f"Report ID: {report.get('report_id', 'N/A')}\nPolicy Version: {report.get('policy_version_set', 'N/A')}\nDisclaimer Hash: {report.get('disclaimer_hash', 'N/A')}\nGenerated (UTC): {report.get('generated_at_utc', 'N/A')}")
    
    st.subheader("Action Trace Log")
    audits = report.get("audit_trail", [])
    if not audits:
        st.write("No trace logs available.")
    else:
        df = pd.DataFrame(audits)
        # Reorder to highlight evidence anchors
        if "evidence_anchor" in df.columns:
            st.dataframe(df, use_container_width=True)
            
            st.subheader("Evidence Anchor Breakdown")
            for step in audits:
                anchor = step.get("evidence_anchor")
                if anchor and anchor != "N/A":
                    st.markdown(f"**{step.get('step_id')}**: `{anchor}` ([Source]({step.get('source_url', '#')}))")
                    

def render_export_view():
    st.header("Export & Download (S2)")
    st.write("Securely download your audit-ready JSON artifacts.")
    
    report = st.session_state.current_report
    case_input = st.session_state.current_case_input
    
    if not report:
        st.info("👈 No report generated yet to export.")
        return
        
    case_id = report.get("case_id", "UNKNOWN")
    date_str = datetime.utcnow().strftime("%Y%m%d")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. Report Payload")
        st.write("Contains the final verdict, blockings, and calculation traces.")
        report_json = json.dumps(report, indent=2, sort_keys=True)
        st.download_button(
            label="Download engine_report.json",
            data=report_json,
            file_name=f"DESS_{case_id}_Report_{date_str}.json",
            mime="application/json",
            type="primary"
        )
        
    with col2:
        st.subheader("2. Case Input Payload")
        st.write("Contains the zero-inference input facts you submitted.")
        if case_input:
            input_json = json.dumps(case_input, indent=2, sort_keys=True)
            st.download_button(
                label="Download case_input.json",
                data=input_json,
                file_name=f"DESS_{case_id}_Input_{date_str}.json",
                mime="application/json"
            )
        else:
            st.write("No input data available.")
