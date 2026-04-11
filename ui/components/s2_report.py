import streamlit as st
import pandas as pd

def render_report_preview():
    st.header("Report Preview (S2)")
    
    report = st.session_state.get("current_report")
    
    if not report:
        st.info("👈 No report generated yet. Please fill the Intake form and run the engine.")
        return
        
    status = report.get("status", "UNKNOWN")
    runtime = report.get("policy_runtime_status", {})
    debug = report.get("debug", {})
    
    # 0. Debug Tracer
    if debug:
        st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; border: 1px solid #d1d5db; margin-bottom: 20px;">
            <code>Debug Trace: overlay_gate_applied = {debug.get('overlay_gate_applied', False)} | TS: {debug.get('overlay_gate_ts', 'N/A')}</code>
        </div>
        """, unsafe_allow_html=True)

    # 1. Verdict Banner
    if status == "APPROVED" or status == "ELIGIBLE":
        st.markdown(f'<div class="report-verdict-ELIGIBLE">✅ VERDICT: ELIGIBLE / APPROVED</div>', unsafe_allow_html=True)
    elif status == "PROVISIONAL (CALC OK) / ON HOLD (POLICY PAUSED)":
        st.markdown(f'<div class="report-verdict-NEEDS_INPUT">🟡 VERDICT: PROVISIONAL (CALC OK) / ON HOLD (POLICY PAUSED)</div>', unsafe_allow_html=True)
    elif status == "PAUSED / NEEDS_MANUAL_REVIEW":
        st.markdown(f'<div class="report-verdict-NEEDS_INPUT">⏸️ VERDICT: PAUSED / NEEDS MANUAL REVIEW</div>', unsafe_allow_html=True)
    elif status == "REJECTED" or status == "BLOCKED":
        st.markdown(f'<div class="report-verdict-BLOCKED">⛔ VERDICT: BLOCKED / REJECTED</div>', unsafe_allow_html=True)
    elif status == "NEEDS_INPUT":
        st.markdown(f'<div class="report-verdict-NEEDS_INPUT">⚠️ VERDICT: NEEDS INPUT</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="report-verdict-INCONSISTENT">⚠️ VERDICT: INCONSISTENT ({status})</div>', unsafe_allow_html=True)
        
    st.markdown("---")

    runtime_status_val = runtime.get("status")
    if runtime_status_val:
        reason = runtime.get("status_reason_de", "N/A")
        source = runtime.get("source", "STATIC")
        health = runtime.get("health", "N/A")
        if runtime_status_val == "PAUSED":
            # This is the primary orientation warning
            st.warning(f"⚠️ **Note**: Policy runtime status is {runtime_status_val} ({source}) — {reason}. Calculation is for orientation only and requires manual verification.")
        elif runtime_status_val == "CLOSED":
            st.error(f"Policy runtime status is CLOSED ({source}): {reason} | Crawler health: {health}")
        elif runtime_status_val == "UNKNOWN":
            st.info(f"Policy runtime status is UNKNOWN ({source}): {reason} | Crawler health: {health}")
        else:
            st.caption(f"Policy runtime status: {runtime_status_val} ({source})")

    st.markdown("---")
        
    # 2. Blockers (Red Lines) & Missing Facts
    
    # Missing Facts logic
    missing_facts = []
    for f in report.get("violations", []) + getattr(report, "findings", []): # some might be in violations
        if f.get("missing_facts"):
            missing_facts.extend(f.get("missing_facts"))
            
    # Also check top-level report if stored there (though normally under violations/findings)
    if "missing_facts" in report:
        missing_facts.extend(report["missing_facts"])
        
    missing_facts = list(set(missing_facts))
    
    if missing_facts:
        st.markdown(f'<div class="report-verdict-NEEDS_INPUT">📢 <b>Action Required: Missing Information</b></div>', unsafe_allow_html=True)
        st.write("The engine could not complete the calculation because the following facts are missing or UNKNOWN:")
        for mf in missing_facts:
            # Friendly dictionary mapper
            label = mf
            if mf == "application_submitted_date": label = "申请递交日期 (Application Date)"
            elif mf == "ENERGY_CONSULT_PROOF": label = "ENERGY_CONSULT_PROOF (Energiesparberatung 证明)"
            
            st.markdown(f"- **缺失项**: `{label}`")
        st.markdown("---")

    violations = report.get("violations", [])
    if violations:
        st.subheader("🚨 Blocking Violations / Warnings")
        for v in violations:
            msg = v.get("message", "Unknown Violation")
            code = v.get("code", "UNKNOWN_CODE")
            anchor = v.get("evidence_anchor", "N/A")
            
            adv_html = f"<br><small><em>Evidence Anchor: {anchor}</em></small>" if st.session_state.get("advanced_mode", False) else ""
            st.markdown(f"""
            <div class="blocker-card">
                <strong>{code}</strong><br>
                {msg}
                {adv_html}
            </div>
            """, unsafe_allow_html=True)
            
    # 3. The Math
    is_provisional = "PROVISIONAL" in status
    st.subheader("The Math" + (" (Provisional)" if is_provisional else ""))
    
    # Removed redundant orientation warning here (consolidated in runtime status section)
    
    if status == "PAUSED / NEEDS_MANUAL_REVIEW":
        st.error("❗ **Calculation disabled**: program under revision.")
    elif status in ["NEEDS_INPUT", "INCONSISTENT"] and not is_provisional:
        st.warning("N/A - Calculation aborted due to missing or inconsistent data.")
    else:
        # Reconstruct the breakdown
        audits = report.get("audit_trail", [])
        
        eligible_cost = 0.0
        grant_total = float(report.get("subsidy_total_eur", "0.00"))
        if "REJECTED" in status or "BLOCKED" in status:
            grant_total = 0.0
        grant_federal = 0.0
        grant_city = grant_total
        cap_msg = None
        
        for step in audits:
            desc = step.get("description", "")
            amt = step.get("amount_eur", "0.00")
            
            if "Eligible Cost" in desc:
                try: 
                    eligible_cost += float(amt)
                except: pass
                
            if "Cap:" in desc or "Stacking limit" in desc:
                cap_msg = desc
                anchor = step.get("evidence_anchor", "")
                if st.session_state.get("advanced_mode", False) and anchor:
                    cap_msg += f" (Anchor: {anchor})"
                
        is_blocked = math_trace.get("grant_status") == "BLOCKED_BY_REDLINE"
        
        final_locked = math_trace.get("final_locked", False)
        
        if is_blocked:
            st.error(f"❌ **Grant Intercepted (0.00 €)**\n\nThis project is disqualified due to strict policy violations (Gate Block). The subsidy amount is **0€** regardless of equipment costs.\n\n**Reasons:** `{', '.join(math_trace.get('blocked_by', []))}`")
            with st.expander("Show Informational Math (If Eligible)"):
                st.info("The following calculation shows what the grant WOULD have been if no redlines were triggered. NOT ELIGIBLE NOW.")
                st.markdown(f"""
                <table class="math-table">
                    <tr><th>Metric</th><th>Amount (€)</th></tr>
                    <tr><td>Eligible Cost Total</td><td>{eligible_cost:.2f}</td></tr>
                    <tr><td>Federal Grant (KfW)</td><td>{grant_federal:.2f}</td></tr>
                    <tr><td>Theoretical City Share</td><td>{grant_city:.2f}</td></tr>
                </table>
                """, unsafe_allow_html=True)
        else:
            final_label = "Final (Locked Plan)" if final_locked else "Final (— / Plan not selected)"
            final_value = f"{grant_total:.2f}" if final_locked else "—"
            
            estimate_label = "Grant Estimate"
            if not final_locked:
                estimate_label += " (PROVISIONAL_MATH)"
    
            st.markdown(f"""
            <table class="math-table">
                <tr><th>Metric</th><th>Amount (€)</th></tr>
                <tr><td>Eligible Cost Total</td><td>{eligible_cost:.2f}</td></tr>
                <tr><td>Federal Grant (KfW)</td><td>{grant_federal:.2f}</td></tr>
                <tr><td>{estimate_label}</td><td>{grant_city:.2f}</td></tr>
                <tr class="math-total-row"><td>{final_label}</td><td>{final_value}</td></tr>
            </table>
            """, unsafe_allow_html=True)
            
            if cap_msg:
                st.info(f"💡 **Cap Applied**: {cap_msg}")

        st.markdown("---")
    
    # 4. Action Steps
    st.subheader("Next Action Steps" + (" (Safe Mode)" if is_provisional else ""))
    
    if is_provisional or status == "PAUSED / NEEDS_MANUAL_REVIEW":
        st.markdown("""
        1. **Manual Verification Required**: Confirm on the official city page / portal whether the program is currently accepting applications and whether rules changed.
        2. **Pending Verification**: If applications are accepted: You may submit only as "pending verification", and do not start work / pay deposits before a written approval (Zuwendungsbescheid/Bewilligung).
        3. **Contracting**: If you sign, ensure an **aufschiebende Bedingung** (subsidy approval) clause.
        """)
        
    elif status == "APPROVED" or status == "ELIGIBLE":
        st.markdown("""
        **Plan A: Direct Subsidy Pursuit**
        1. **Contracting**: Sign the installation contract **ONLY IF** it includes a conditional clause (aufschiebende Bedingung).
        2. **Applying**: Immediately submit applications to the city and/or KfW portals.
        3. **Execution**: **DO NOT** start work or make payments until portals confirm receipt (Zusage).
        4. **Auditing**: Collect final invoices (Rechnung) and Fachunternehmererklärung upon completion.
        """)
        
    elif status == "REJECTED" or status == "BLOCKED":
        st.markdown("""
        **Plan B: Alternative Tax Deduction (EStG §35c)**
        1. **Assessment**: Direct subsidies are blocked because a critical timing or compliance rule was broken (see blockers above).
        2. **Tax Action**: You may still deduct 20% of eligible labor costs over 3 years on your income tax, capped at 40,000€.
        3. **Execution**: Proceed with installation, but ensure the installer provides a valid Fachunternehmererklärung for the tax office.
        """)
        
    elif status == "NEEDS_INPUT":
        st.markdown("""
        1. **Review**: Check the RED/YELLOW warnings above to see which mandatory facts are missing.
        2. **Fix**: Return to Tab A (Case Intake) and modify the inputs.
        3. **Re-Run**: Click "Generate Audit Report" again.
        """)
