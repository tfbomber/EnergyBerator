import os
import datetime
from typing import Dict, Any
from fpdf import FPDF

# helper to format numbers for the PDF (German style: 1.500)
def pfmt(val: float) -> str:
    return f"{abs(val):,.0f}".replace(",", ".")

class D_ESS_SalesPDF(FPDF):
    def header(self): pass
    def footer(self): pass

def generate_sales_pdf_bytes(report: Dict[str, Any]) -> bytes:
    roi = report.get("roi_result", {})
    scenarios = roi.get("scenarios", [])
    baseline = scenarios[1] if len(scenarios) > 1 else (scenarios[0] if scenarios else {})
    
    hs = roi.get("household_snapshot", {})
    breakdown = roi.get("breakdown_base", {})
    ea = roi.get("export_analysis", {})
    fr = roi.get("financing_report", {})
    ci = roi.get("carbon_impact", {})
    we = roi.get("wealth_effect", {})
    dt = roi.get("data_taxonomy", {})

    # ── Derived display variables ─────────────────────────────────────────────
    # hp_str: "Ja" if has_heat_pump=True, else "Nein (PV-Only)"
    # BUG-01 FIX (2026-04-02): was reading dt["building_footprint"]["value"] which is a
    # geometry key, NOT the HP flag — caused PDF to always show "Wärmepumpe: Ja".
    # Correct source: data_taxonomy["has_heat_pump"]["value"], fallback to hp_potential.
    _has_hp = dt.get("has_heat_pump", {}).get("value")
    if _has_hp is None:
        _has_hp = dt.get("hp_potential", {}).get("value", False)
    hp_str  = "Ja" if _has_hp else "Nein (PV-Only)"

    # e_load_total: total household demand (base + HP + EV) in kWh/year
    e_load_total = (
        hs.get("e_load_total_kwh")
        or roi.get("e_load_kwh", 0)
        or hs.get("e_base_kwh", 0) + hs.get("e_hp_kwh", 0)
    )
    
    # Setup PDF
    pdf = D_ESS_SalesPDF(orientation='P', unit='mm', format='A4')
    
    
    # -----------------------------------------------------------------------
    # FONT / UNICODE SETUP
    # -----------------------------------------------------------------------
    font_added = False
    sys_font_path = "C:\\Windows\\Fonts\\arial.ttf"
    if os.path.exists(sys_font_path):
        try:
            pdf.add_font("Sans", "", sys_font_path)
            pdf.add_font("Sans", "B", "C:\\Windows\\Fonts\\arialbd.ttf")
            pdf.add_font("Sans", "I", "C:\\Windows\\Fonts\\ariali.ttf")
            font_name = "Sans"
            font_added = True
        except Exception as exc:  # MEDIUM-01 FIX (2026-04-02): was bare except: — swallowed KeyboardInterrupt
            import logging as _log
            _log.getLogger(__name__).warning("[PDF] Font load failed (%s) — fallback to helvetica", exc)
            font_name = "helvetica"
    else:
        font_name = "helvetica"

    euro = "€" if font_added else "EUR"
    
    pdf.add_page()
    pdf.set_auto_page_break(False)
    
    # -----------------------------------------------------------------------
    # COLORS
    # -----------------------------------------------------------------------
    C_BLUE = (0, 48, 96)       # Dark Navy
    C_ACCENT = (0, 120, 200)   # Action Blue
    C_GRAY = (80, 80, 80)      # Labels
    C_TEXT = (20, 20, 20)      # Body
    C_LIGHT_GRAY = (245, 245, 245) # Card Back
    C_GREEN = (46, 204, 113)   # Positive
    C_RED = (231, 76, 60)     # Negative

    # -----------------------------------------------------------------------
    # TOP ZONE (y: 0 -> 95mm)
    # -----------------------------------------------------------------------
    
    # 1A. Header Bar
    pdf.set_font(font_name, "B", 18)
    pdf.set_text_color(*C_BLUE)
    pdf.text(15, 20, "Ihre Dach-Energieinvestition")
    
    pdf.set_font(font_name, "", 9)
    pdf.set_text_color(*C_GRAY)
    subtitle = "Orientierungshilfe auf Basis Ihrer aktuellen Verbrauchs- und Haushaltsdaten"
    pdf.text(15, 26, subtitle)
    
    pdf.set_font(font_name, "I", 7)
    pdf.set_text_color(*C_GRAY)
    pdf.text(125, 26, "Vorläufige Wirtschaftlichkeitseinschätzung / vorbehaltlich Detailprüfung")

    # 1B. Case Input Snapshot Card
    y_input = 34
    pdf.set_fill_color(*C_LIGHT_GRAY)
    pdf.rect(15, y_input, 180, 18, 'F')
    
    pdf.set_font(font_name, "B", 9)
    pdf.set_text_color(*C_BLUE)
    pdf.text(20, y_input + 6, "Grundlage dieser Einschätzung")
    
    pdf.set_font(font_name, "", 8)
    pdf.set_text_color(*C_TEXT)
    
    # Grid layout for inputs with Tier Markers
    def get_tier_char(key):
        tier = dt.get(key, {}).get("tier")
        if tier == "DIRECT_TRUTH": return "[A]"
        if tier == "PROXY_INFERRED": return "[B]"
        if tier == "MANUAL_REQUIRED": return "[C]"
        return ""

    pdf.text(20, y_input + 12, f"Haushalt: {hs.get('household_size', 'k.A.')} P. {get_tier_char('household_size')}")
    pdf.text(65, y_input + 12, f"E-Auto: {hs.get('ev_status', 'Nein')} {get_tier_char('ev_status')}")
    pdf.text(110, y_input + 12, f"Wärmepumpe: {hp_str} {get_tier_char('hp_potential')}")
    pdf.text(150, y_input + 12, f"Bedarf: {pfmt(e_load_total)} kWh")

    # 1C. Hero KPI Strip (The Visual Center of Gravity)
    y_kpi = 62
    pdf.set_font(font_name, "B", 11)
    pdf.set_text_color(*C_BLUE)
    pdf.text(15, y_kpi - 2, "Kernkennzahlen Ihrer Anlage")

    # Derived Metrics
    kwp = roi.get("kWp_rec", 0)
    e_self = baseline.get("e_self_kwh", 0)
    autarky = (e_self / e_load_total * 100) if e_load_total > 0 else 0
    dp = baseline.get("payback_dynamic_years", 0)
    dp_str = f"≈ {dp} Jahre" if dp < 99 else ">20 Jahre"
    benefit = baseline.get("annual_benefit_cents", 0) / 100
    mo_benefit = benefit / 12
    profit20 = baseline.get("profit20_cents", 0) / 100

    def draw_kpi_card(x, y, w, h, label, value, subtext="", size="normal"):
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(x, y, w, h)
        
        # Label
        pdf.set_font(font_name, "", 8)
        pdf.set_text_color(*C_GRAY)
        pdf.text(x + 4, y + 6, label)
        
        # Value
        if size == "hero":
            pdf.set_font(font_name, "B", 20)
            v_off = 16
        else:
            pdf.set_font(font_name, "B", 14)
            v_off = 14
            
        pdf.set_text_color(*C_BLUE)
        pdf.text(x + 4, y + v_off, value)
        
        # Subtext
        if subtext:
            pdf.set_font(font_name, "", 7)
            pdf.set_text_color(*C_GRAY)
            pdf.text(x + 4, y + v_off + 6, subtext)

    # Row 1: The Heavy Hitters
    k_gap = 3
    w_hero = 88
    w_std = (180 - w_hero - k_gap*2) / 2 # ~43mm
    
    draw_kpi_card(15, y_kpi, w_hero, 28, "Netto-Energievorteil 1. Jahr", f"≈ {pfmt(benefit)} {euro}", f"entspricht ≈ {pfmt(mo_benefit)} {euro} / Monat", "hero")
    draw_kpi_card(15 + w_hero + k_gap, y_kpi, w_std, 28, "Autarkiegrad", f"≈ {autarky:.0f} %")
    draw_kpi_card(15 + w_hero + w_std + k_gap*2, y_kpi, w_std, 28, "Amortisation", dp_str)
    
    # Row 2: Supporting Facts (Secondary)
    y_kpi2 = y_kpi + 28 + k_gap
    draw_kpi_card(15, y_kpi2, 88, 14, "Systemgröße", f"{pfmt(kwp)} kWp")
    draw_kpi_card(15 + 88 + k_gap, y_kpi2, (180 - 88 - k_gap), 14, "Gesamtertrag über 20 Jahre", f"≈ {pfmt(profit20)} {euro}")

    # -----------------------------------------------------------------------
    # MIDDLE ZONE (y: 115 -> 195mm)
    # -----------------------------------------------------------------------
    y_mid = 120
    
    # 2A. "Warum dieses System passt" (Left)
    pdf.set_font(font_name, "B", 11)
    pdf.set_text_color(*C_BLUE)
    pdf.text(15, y_mid, "Warum dieses System zu Ihrem Haushalt passt")
    
    pdf.set_font(font_name, "", 9)
    pdf.set_text_color(*C_TEXT)
    pdf.set_xy(15, y_mid + 3)
    txt_fits = (f"Der Strombedarf Ihres Haushalts ({pfmt(e_load_total)} kWh/J) in Kombination mit der Wärmepumpe spricht "
                f"für eine PV-Anlage in dieser Größenordnung. Ein großer Teil des Stromverbrauchs kann direkt "
                "auf dem eigenen Dach erzeugt werden. Dies verbessert die Wirtschaftlichkeit und erhöht Ihre Unabhängigkeit.")
    pdf.multi_cell(90, 4.5, txt_fits)

    # 2B. "So entsteht der wirtschaftliche Vorteil" (Right)
    pdf.set_font(font_name, "B", 11)
    pdf.set_text_color(*C_BLUE)
    pdf.text(115, y_mid, "So entsteht der wirtschaftliche Vorteil")
    
    self_cons_eur = breakdown.get("self_saving_cents", 0) / 100
    eeg_eur = ea.get("eeg_income_eur", 0)
    opex_eur = breakdown.get("opex_cents", 0) / 100
    
    def draw_calc_row(x, y, label, val, color):
        pdf.set_font(font_name, "", 9)
        pdf.set_text_color(*C_TEXT)
        pdf.text(x, y, label)
        pdf.set_font(font_name, "B", 9)
        pdf.set_text_color(*color)
        pdf.text(x + 55, y, f"≈ {pfmt(val)} {euro} / J.")

    draw_calc_row(115, y_mid + 8, "Eigenverbrauchsersparnis", self_cons_eur, C_GREEN)
    draw_calc_row(115, y_mid + 14, "EEG Einspeisevergütung", eeg_eur, C_GREEN)
    draw_calc_row(115, y_mid + 20, "- Betriebskosten (OPEX)", opex_eur, C_RED)
    
    pdf.set_font(font_name, "I", 7)
    pdf.set_text_color(*C_GRAY)
    pdf.text(115, y_mid + 24, "inkl. Wartungsreserve und Rücklage für Wechselrichter-Ersatz")

    # 2C. Financing Block (Full Width Card with Accent)
    y_fin = 155
    pdf.set_fill_color(*C_LIGHT_GRAY)
    pdf.rect(15, y_fin, 180, 24, 'F')
    
    pdf.set_font(font_name, "B", 11)
    pdf.set_text_color(*C_BLUE)
    pdf.text(20, y_fin + 7, "Beispiel Finanzierung")
    
    if fr.get("enabled", False):
        pmt = fr.get("loan_monthly_payment_eur", 0)
        sav = fr.get("monthly_savings_eur", 0)
        cf = fr.get("monthly_cashflow_margin_eur", 0)
        
        pdf.set_font(font_name, "", 9)
        pdf.set_text_color(*C_TEXT)
        pdf.text(25, y_fin + 13, f"Monatliche Kreditrate: {pfmt(pmt)} {euro}")
        pdf.text(85, y_fin + 13, f"Stromkostenersparnis: {pfmt(sav)} {euro}")
        
        # Highlighted Result Row
        pdf.set_fill_color(*C_BLUE)
        pdf.rect(20, y_fin + 16, 2, 5, 'F') # Blue left accent border
        pdf.set_font(font_name, "B", 10)
        pdf.set_text_color(*C_BLUE)
        pdf.text(25, y_fin + 20, f"Netto-Cashflow nach Finanzierung: {'+' if cf>=0 else ''}{pfmt(cf)} {euro} / Monat")
        
        pdf.set_font(font_name, "I", 7)
        pdf.set_text_color(*C_GRAY)
        pdf.text(20, y_fin + 28, "Beispielrechnung auf Basis eines angenommenen Kredits (Laufzeit 10 Jahre, Zinssatz ca. 4 %). Finanzierungskonditionen können je nach Bank variieren.")
    else:
        pdf.set_font(font_name, "I", 9)
        pdf.set_text_color(*C_GRAY)
        pdf.text(25, y_fin + 14, "Die Finanzierungsanalyse war für diesen Durchlauf deaktiviert. Wir bieten verschiedene Kredite (z.B. KfW) an.")

    # -----------------------------------------------------------------------
    # BOTTOM ZONE (y: 195 -> 297mm)
    # -----------------------------------------------------------------------
    y_bottom = 205
    
    # 3A. Zusätzlicher Nutzen (2-column layout)
    pdf.set_font(font_name, "B", 11)
    pdf.set_text_color(*C_BLUE)
    pdf.text(15, y_bottom, "Zusätzlicher Nutzen")
    
    # Left: CO2
    pdf.set_font(font_name, "B", 8)
    pdf.set_text_color(*C_GRAY)
    pdf.text(15, y_bottom + 6, "CO2-BILANZ")
    pdf.set_font(font_name, "", 9)
    pdf.set_text_color(*C_TEXT)
    pdf.text(15, y_bottom + 11, f"Reduktion: ≈ {pfmt(ci.get('annual_co2_reduction_tons', 0))} t / Jahr")
    pdf.text(15, y_bottom + 16, f"Vermeidung (20 J.): ≈ {pfmt(ci.get('co2_20y_total_tons', 0))} t")

    # Right: Immobilie
    pdf.set_font(font_name, "B", 8)
    pdf.set_text_color(*C_GRAY)
    pdf.text(105, y_bottom + 6, "IMMOBILIENWIRKUNG")
    pdf.set_font(font_name, "", 9)
    pdf.set_text_color(*C_TEXT)
    pdf.set_xy(105, y_bottom + 8)
    txt_imm = "Eine PV-Anlage kann das energetische Profil der Immobilie stärken und die Marktattraktivität erhöhen."
    pdf.multi_cell(90, 4.5, txt_imm)

    # 3B. EEG Timing Note (Slim Highlight Card)
    y_eeg = 238
    pdf.set_fill_color(*C_LIGHT_GRAY)
    pdf.rect(15, y_eeg, 180, 14, 'F')
    pdf.set_fill_color(*C_BLUE)
    pdf.rect(15, y_eeg, 180, 0.5, 'F') # Top blue line 1pt equivalent
    
    pdf.set_xy(20, y_eeg + 3)
    pdf.set_font(font_name, "", 8.5)
    pdf.set_text_color(*C_TEXT)
    txt_eeg = "Die EEG-Vergütung für neue Anlagen richtet sich nach dem Inbetriebnahmedatum. Eine frühzeitige Projektplanung kann helfen, die aktuelle Vergütungsstufe zu sichern."
    pdf.multi_cell(170, 4, txt_eeg)

    # 3C. Footer Continuation Line
    pdf.set_font(font_name, "", 8)
    pdf.set_text_color(*C_GRAY)
    footer_text = "Diese Übersicht dient als erste Wirtschaftlichkeitseinschätzung. Eine Detailprüfung kann zusätzliche Optimierungspotenziale sichtbar machen."
    pdf.text(15, 275, footer_text)
    
    ts = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    pdf.text(170, 280, f"Stand: {ts} (D-ESS Engine)")

    # -----------------------------------------------------------------------
    # EXPORT
    # -----------------------------------------------------------------------
    return bytes(pdf.output())
