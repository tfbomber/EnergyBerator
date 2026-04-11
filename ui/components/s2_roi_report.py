import streamlit as st
import pandas as pd
from typing import Dict, Any
from ui.components.s2_pdf_generator import generate_sales_pdf_bytes

def fmt(val: float) -> str:
    """Format European number string: 1.500 instead of 1,500."""
    return f"{val:,.0f}".replace(",", ".")

def render_tier_badge(tier_data: Dict[str, Any]):
    """Renders a small badge based on DataAcquisitionTier."""
    if not tier_data:
        return
    tier = tier_data.get("tier")
    if tier == "DIRECT_TRUTH":
        st.caption("✅ **Gesichert** (Level A)")
    elif tier == "PROXY_INFERRED":
        st.caption("📊 **Hergeleitet** (Level B Proxy)")
    elif tier == "MANUAL_REQUIRED":
        st.caption("📝 **Manuelle Angabe** (Level C)")

def render_roi_report(report: Dict[str, Any]):
    roi = report.get("roi_result")
    if not roi:
        st.error("Keine ROI-Daten im Bericht gefunden.")
        return

    if roi.get("verdict") == "ROI_NOT_TARGET":
        st.error(f"❌ {roi.get('reason', 'Nicht für ROI-Berechnung geeignet')}")
        return

    # ── Street ranking context banner (only for street-level reports) ───────────
    street_ctx = report.get("street_context", {})
    if street_ctx:
        seg_rank    = street_ctx.get("segment_rank", "?")
        rank_in_seg = street_ctx.get("rank_in_segment", "?")
        dq_note     = street_ctx.get("data_quality_note", "")
        low_s       = street_ctx.get("low_sample_flag", False)
        adj_score   = street_ctx.get("adjusted_street_score", 0.0)
        street_name = street_ctx.get("street_name", "")
        segment_id  = str(street_ctx.get("segment_id", "")).replace("NEUSS_", "").replace("_01", "")

        ctx_md = (
            f"📍 **{street_name}**  |  "
            f"Segment **#{seg_rank}** ({segment_id})  |  "
            f"Rang in Segment: **#{rank_in_seg}**  |  "
            f"Score: **{adj_score:.3f}**"
        )
        if low_s:
            ctx_md += "    ⚠️ *Kleine Stichprobe*"
        st.info(ctx_md)
        if dq_note:
            dq_color = "#2d7a4f" if "Stage-1" in dq_note else "#8b5e00"
            st.markdown(
                f"<small style='color:{dq_color};'>🔍 Datenqualität: {dq_note}</small>",
                unsafe_allow_html=True,
            )
        st.markdown("---")

    c_head, c_btn = st.columns([3, 1])
    with c_head:
        st.header("📊 Ihre Dach-Energieinvestition")
        st.caption("Orientierungshilfe / vorbehaltlich Detailprüfung")
    
    with c_btn:
        try:
            case_id = report.get("case_id", "Draft")
            cache_key = f"pdf_bytes_{case_id}"
            
            # Use st.session_state as the stable source of truth
            if cache_key not in st.session_state:
                st.session_state[cache_key] = generate_sales_pdf_bytes(report)
                
            st.download_button(
                label="📥 PDF herunterladen",
                data=st.session_state[cache_key],
                file_name=f"D-ESS_Sales_Report_{case_id}.pdf",
                mime="application/pdf",
                key=f"btn_dl_{case_id}",
                type="primary",
                help="Kompakte 1-Seiten-Zusammenfassung als PDF herunterladen"
            )
        except Exception as e:
            import traceback
            st.error(f"Error: {e}\n{traceback.format_exc()}")
            st.button("📥 PDF herunterladen", disabled=True)


    scenarios = roi.get("scenarios", [])
    baseline = scenarios[1] if len(scenarios) > 1 else scenarios[0]

    kwp_rec = roi.get("kWp_rec", 0)
    dp = baseline.get("payback_dynamic_years", 0)
    dp_str = f"≈ {dp} Jahre" if dp < 999 else ">20 Jahre"
    benefit_eur = baseline.get("annual_benefit_cents", 0) / 100
    monthly_benefit_eur = benefit_eur / 12
    profit20_eur = baseline.get("profit20_cents", 0) / 100
    
    e_self_kwh = baseline.get("e_self_kwh", 0)
    e_load_kwh_base = roi.get("e_load_kwh", 0)
    hs = roi.get("household_snapshot", {})
    e_load_total = hs.get("e_load_total_kwh", e_load_kwh_base)
    
    if e_load_total == 0: e_load_total = e_self_kwh if e_self_kwh > 0 else 1
    autarky_pct = (e_self_kwh / e_load_total) * 100
    if autarky_pct > 100: autarky_pct = 100

    # -----------------------------------------------------------------------
    # SECTION 1 — KERNKENNZAHLEN (HERO SUMMARY)
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🚀 Ihre Dach-Energieinvestition")

    # Row 1: Key operational & temporal metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Systemgröße", f"{fmt(kwp_rec)} kWp")
    with c2:
        st.metric("Autarkiegrad", f"≈ {autarky_pct:.0f} %")
    with c3:
        st.metric("Amortisationszeit", dp_str)
    with c4:
        irr_bps = baseline.get("irr_bps", 0)
        irr_pct = irr_bps / 100
        irr_col = "normal" if irr_pct >= 10 else "off"
        st.metric("ROI / IRR (20J.)", f"{irr_pct:.1f}% p.a.", delta=None)

    # Row 2: Financial impact
    c4, c5 = st.columns(2)
    with c4:
        st.metric("Netto-Energievorteil im ersten Jahr", f"≈ {fmt(benefit_eur)} €", 
                  delta=f"entspricht ≈ {fmt(monthly_benefit_eur)} € / Monat", delta_color="normal")
    with c5:
        st.metric("Gesamtertrag über 20 Jahre", f"≈ {fmt(profit20_eur)} €")

    # -----------------------------------------------------------------------
    # SECTION 2 — INVESTITIONSGRUNDLAGE & DATENQUALITÄT
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🏠 Investitionsgrundlage & Datenqualität")
    dt = roi.get("data_taxonomy", {})
    
    if hs:
        c_snap1, c_snap2 = st.columns(2)
        with c_snap1:
            st.write(f"**Haushaltsgröße:** {hs.get('household_size', 'k.A.')} Personen")
            render_tier_badge(dt.get("household_size"))
            
            st.write(f"**Haushaltsstrombedarf:** {fmt(hs.get('e_base_kwh', 0))} kWh / Jahr")
            st.caption("📊 Basierend auf Haushaltsgröße (Standardprofil)")
            
            st.write(f"**Wärmepumpe:** {fmt(hs.get('e_hp_kwh', 0))} kWh / Jahr")
            render_tier_badge(dt.get("hp_potential"))

        with c_snap2:
            st.write(f"**Gesamtstrombedarf:** {fmt(hs.get('e_load_total_kwh', 0))} kWh / Jahr")
            st.caption("Summe aus Haushaltsstrom, Wärme und Mobilität")
            
            st.write(f"**Empfohlene PV-Größe:** {fmt(kwp_rec)} kWp")
            st.caption("✅ Dimensioniert für maximale Eigenabdeckung")
            
            st.write(f"**E-Mobilität (EV):** {hs.get('ev_status', 'k.A.')}")
            render_tier_badge(dt.get("ev_status"))
            
        st.caption("*Die Datenqualität wird unterteilt in: Gesichert (Level A), Hergeleitet (Level B) und Manuelle Angabe (Level C).*")

    # -----------------------------------------------------------------------
    # SECTION 3 — HERKUNFT DER EINSPARUNGEN (BASELINE)
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("💶 Herkunft der Einsparungen (Baseline)")
    breakdown = roi.get("breakdown_base", {})
    ea = roi.get("export_analysis", {})
    sharing_mode = roi.get("energy_sharing_mode", "none")
    
    self_cons_eur = breakdown.get("self_saving_cents", 0) / 100
    eeg_eur = ea.get("eeg_income_eur", 0)
    sharing_eur = ea.get("sharing_income_eur", 0)
    opex_eur = breakdown.get("opex_cents", 0) / 100
    
    col_split, _ = st.columns([2, 1])
    with col_split:
        st.success(f"**+ Eigenverbrauchsersparnis:** ≈ {fmt(self_cons_eur)} € / Jahr")
        if eeg_eur > 0:
            st.info(f"**+ EEG Einspeisevergütung:** ≈ {fmt(eeg_eur)} € / Jahr")
        st.error(f"**- Betriebskosten (OPEX):** ≈ {fmt(opex_eur)} € / Jahr", 
                 icon="ℹ️")
        st.caption("OPEX beinhaltet eine Wartungsreserve sowie eine mögliche Rücklage für einen zukünftigen Wechselrichter-Ersatz.")
        
    st.markdown("*Die Baseline-Berechnung berücksichtigt ausschließlich gesicherte Faktoren wie Eigenverbrauch und gesetzliche Einspeisevergütung (EEG).*")

    # -----------------------------------------------------------------------
    # SECTION 4 — INVESTITIONS- UND FINANZIERUNGSÜBERSICHT
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Investitions- und Finanzierungsübersicht")
    capex = roi.get("capex", {})
    vat_saving = capex.get("vat_saving_cents", 0) / 100
    vat0_eur = capex.get("vat0_cents", 0) / 100
    opex_y = breakdown.get("opex_cents", 0) / 100
    
    fr = roi.get("financing_report", {})
    
    c_inv, c_fin = st.columns(2)
    with c_inv:
        st.markdown("**4A. Investitionsdetails**")
        st.write(f"- **Geschätzte Systemkosten (CAPEX netto):** {fmt(vat0_eur)} €")
        st.write(f"- **0% MwSt.-Vorteil (bereits berücksichtigt):** ~{fmt(vat_saving)} €")
        st.write(f"- **Jährliche Betriebskosten (OPEX):** {fmt(opex_y)} € / Jahr")
        if "basis_eur_per_kwp" in capex:
            st.caption(f"Basis: {fmt(capex['basis_eur_per_kwp'])} €/kWp + {fmt(capex['basis_fixed_eur'])} € fix (0% MwSt.)")
            
    with c_fin:
        if fr.get("enabled", False):
            pmt = fr.get("loan_monthly_payment_eur", 0)
            savings_mo = fr.get("monthly_savings_eur", 0)
            margin = fr.get("monthly_cashflow_margin_eur", 0)
            st.markdown("**4B. Finanzierungsbeispiel**")
            st.write("Anstatt monatlich nur für Netzstrom zu bezahlen, kann ein Teil dieses Budgets in das eigene Energie-Asset umgeschichtet werden.")
            st.info(f"- **Monatliche Kreditrate:** ≈ {fmt(pmt)} €\n"
                    f"- **Monatliche Stromkostenersparnis:** ≈ {fmt(savings_mo)} €\n"
                    f"- **Netto-Cashflow nach Finanzierung:** ≈ {'+' if margin>=0 else ''}{fmt(margin)} € / Monat")
            st.caption("Beispielrechnung auf Basis eines angenommenen Kredits (Laufzeit 10 Jahre, Zinssatz ca. 4 %). Finanzierungskonditionen können je nach Bank variieren.")
        else:
            st.markdown("**4B. Finanzierungsoptionen**")
            st.info("Die Finanzierungsanalyse war für diesen Durchlauf deaktiviert. Wir bieten verschiedene strukturelle Darlehensoptionen an.")

    # -----------------------------------------------------------------------
    # SECTION 5 — CO₂-WIRKUNG
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🌍 CO₂-Wirkung")
    ci = roi.get("carbon_impact", {})
    annual_tons = ci.get("annual_co2_reduction_tons", 0)
    total_20y_tons = ci.get("co2_20y_total_tons", 0)
    car_km = ci.get("car_km_equivalent", 0)
    grid_kwh = ci.get("grid_electricity_kwh_equivalent", 0)
    
    ci_c1, ci_c2 = st.columns(2)
    with ci_c1:
        st.metric("CO₂-Reduktion", f"≈ {fmt(annual_tons)} Tonnen / Jahr")
    with ci_c2:
        st.metric("über 20 Jahre", f"≈ {fmt(total_20y_tons)} Tonnen vermieden")
        
    st.info(f"**Vergleichswerte:**\n"
            f"- Vermeidung von ca. {fmt(car_km)} PKW-Kilometern\n"
            f"- Ersatz von ca. {fmt(grid_kwh)} kWh konventionellem Netzstrom")
    
    st.caption("Diese Umweltäquivalente dienen der Orientierung und basieren auf durchschnittlichen deutschen Strommix-Emissionsfaktoren.")

    # -----------------------------------------------------------------------
    # SECTION 6 — AUSWIRKUNG AUF DIE IMMOBILIE
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🏘️ Auswirkung auf die Immobilie")
    we = roi.get("wealth_effect", {})
    
    c_prop, c_pol = st.columns(2)
    with c_prop:
        val_range = we.get("property_value_range_eur", [0, 0])
        uplift_range = we.get("property_uplift_range_eur", [0, 0])
        st.markdown("**6A. Auswirkung auf die Marktattraktivität der Immobilie**")
        st.write("Eine PV-Anlage kann das energetische Profil der Immobilie stärken und die Marktattraktivität erhöhen.")
        st.success(f"**Geschätzter Mehrwert:** {fmt(uplift_range[0])} € – {fmt(uplift_range[1])} €\n"
                   f"*(Basis-Immobilienwert: {fmt(val_range[0])} € – {fmt(val_range[1])} €)*")
        st.caption("**Dieser Wert ist NICHT enthalten in:** Amortisationszeit, Netto-Energievorteil im ersten Jahr oder Gesamtertrag über 20 Jahre.")
        st.caption("Die tatsächliche Wirkung hängt unter anderem von Gebäudetyp, Energieausweis, Käufernachfrage und lokaler Marktsituation ab.")

    with c_pol:
        st.markdown("**6B. Hinweis zur Einspeisevergütung**")
        st.info("Die EEG-Vergütung für neue Anlagen richtet sich nach dem Inbetriebnahmedatum. Eine frühzeitige Projektplanung kann helfen, die aktuelle Vergütungsstufe zu sichern.")
        st.markdown("**Bereits in der ROI-Berechnung berücksichtigt:**")
        st.markdown(f"- **0% MwSt. (UStG §12 Abs.3)** — Reduziert die Anfangsinvestition um ~{fmt(vat_saving)} €")
        st.markdown("- **EEG-Einspeisevergütung** — Sichert die Vergütung für überschüssigen Strom über 20 Jahre")

    # -----------------------------------------------------------------------
    # SECTION 7 — WEITERE WIRTSCHAFTLICHKEITS-OPTIMIERUNGEN
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("💡 Weitere Wirtschaftlichkeits-Optimierungen")
    st.caption("Nicht in der Baseline-Berechnung enthalten")
    
    upside_c1, upside_c2 = st.columns(2)
    with upside_c1:
        st.markdown("##### Dynamische Stromtarife")
        st.write("Mit intelligentem Messsystem (Smart Meter) und flexiblen Verbrauchern kann der Haushaltsstrombezug zusätzlich optimiert werden.")
        if sharing_mode != "none" and sharing_eur > 0:
            st.info(f"Mögliche Einnahmen durch Energy Sharing: **≈ {fmt(sharing_eur)} € / Jahr**")

    with upside_c2:
        st.markdown("##### § 14a EnWG Netzentgelt-Reduzierung")
        st.write("Bei steuerbaren Verbrauchseinrichtungen wie Wärmepumpen oder Wallboxen können reduzierte Netzentgelte möglich sein.")

    # -----------------------------------------------------------------------
    # SECTION 8 — SZENARIENVERGLEICH
    # -----------------------------------------------------------------------
    if scenarios:
        st.markdown("---")
        st.subheader("📈 Szenarienvergleich")
        
        table_data = []
        for s in scenarios:
            pb_dynamic = s.get("payback_dynamic_years", 0)
            profit20 = s.get("profit20_cents", 0) / 100
            benefit = s.get("annual_benefit_cents", 0) / 100
            
            # Autarky for scenario
            e_self_s = s.get("e_self_kwh", 0)
            autarky_s = (e_self_s / e_load_total) * 100 if e_load_total > 0 else 0
            
            # Map default english names to German
            s_name = s["name"]
            if "CONSERVATIVE" in s_name.upper(): s_name = "Konservativ"
            elif "BASELINE" in s_name.upper(): s_name = "Basis (Empfehlung)"
            elif "AGGRESSIVE" in s_name.upper() or "OPTIMISTIC" in s_name.upper(): s_name = "Optimiert"

            table_data.append({
                "Szenario": s_name,
                "Autarkiegrad": f"{autarky_s:.0f} %",
                "Strompreiserhöhung": f"{s['grid_escalation_bps']/100:.1f} % / Jahr",
                "Netto-Energievorteil im ersten Jahr": f"{fmt(benefit)} €",
                "Amortisationszeit": f"{pb_dynamic if pb_dynamic < 999 else '>20'}",
                "Gesamtertrag über 20 Jahre": f"{fmt(profit20)} €",
            })
        df_scenarios = pd.DataFrame(table_data)
        
        def highlight_baseline(row):
            return ['background-color: rgba(46, 204, 113, 0.2)'] * len(row) if 'Basis' in row['Szenario'] else [''] * len(row)
        
        st.dataframe(df_scenarios.style.apply(highlight_baseline, axis=1), use_container_width=True)

    # -----------------------------------------------------------------------
    # SECTION 9 — TECHNISCHE DETAILANSICHT (INSPECTOR)
    # -----------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🛠️ Technische Detailansicht anzeigen"):
        st.subheader("⚖️ Berechnungs- und Annahmegrundlagen")
        st.markdown("Zur vollständigen Transparenz der oben genannten Berechnungen sind hier die Systemgrenzen und Verhaltensannahmen katalogisiert.")
        
        tb1, tb2, tb3 = st.tabs(["1. In Baseline ROI enthalten", "2. Technische Annahmen", "3. Nicht enthaltene Förderungen"])
        with tb1:
            st.markdown("**Diese Faktoren fließen aktiv in die Kernberechnung ein:**")
            st.write("- Eigenverbrauchsersparnis basierend auf hinterlegten Stromtarifen.")
            st.write("- Residuale Einspeisevergütung gemäß aktuellem EEG.")
            st.write("- Jährlich geschätzte OPEX-Kosten (Betrieb & Wartung).")
            st.write("- 0% MwSt.-Befreiung für förderfähige Photovoltaikanlagen.")
            
        with tb2:
            st.markdown("**Diese Inputs steuern die Systemauslegung:**")
            st.write("- Haushaltsstrombedarf & geschätztes Profil für elektrifizierte Wärme/E-Mobilität.")
            st.write("- Dachproduktionsschätzung & räumliche Begrenzungen.")
            st.write("- Dynamische Amortisation berücksichtigt eine jährliche Strompreiserhöhung.")
            
        with tb3:
            st.markdown("**Optionale Upsides (Ausgeschlossen aus der ROI-Baseline):**")
            st.write("- Förderkredite (z.B. KfW 270) oder Zuschüsse zur Heizungserneuerung (KfW 458).")
            st.write("- Lokale kommunale Förderprogramme oder Energy-Sharing Einnahmen (soweit nicht aktiviert).")
            st.write("- Wertsteigerung der Immobilie.")

    # Timestamp Footer
    ts = report.get('generated_at_CET', report.get('generated_at_utc', 'N/A'))
    if ts != 'N/A':
        st.caption(f"\n*Bericht generiert: {ts}*")
    else:
        st.caption("\n*Bericht generiert: k.A.*")
