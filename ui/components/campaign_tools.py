"""
ui/components/campaign_tools.py
================================
TerritoryAI Campaign PDF Generator — Installer Leave-Behind & B2C Flyer.

Functions:
    generate_vollbericht_pdf(dual_roi, street_ctx, policy_meta) -> bytes
        A4 format, 1-page. Installer-only leave-behind after first consultation.
        Shows BOTH scenarios (Household vs. High Load) side-by-side.
        Does NOT include Gesprächsleitfaden (not for direct homeowner use).

    generate_flyer_pdf(dual_roi, street_ctx, installer_brand) -> bytes
        DIN-lang (210 × 99 mm) B2C flyer. White-label (installer brand only).
        UWG §5 compliant: hp_status → AGGRESSIVE | CONSERVATIVE template selection.
        Headline + mandatory footnote always on same page/medium.

UWG §5 Compliance Contract (KI C12 — Locked):
    AGGRESSIVE (STRONG/MODERATE_HP_UPLIFT):
        Headline: "Bis zu {high_load_savings} € Stromkostenersparnis pro Jahr*"
        Footnote:  "* Maximalwert bei hohem Stromverbrauch, z. B. Wärmepumpe..."
    CONSERVATIVE (LIMITED_HP_UPLIFT):
        Headline: "Ca. {household_savings} € Stromkostenersparnis pro Jahr*"
        Footnote:  "* Orientierungswert basierend auf Haushaltsverbrauch..."

Author: TerritoryAI Engine
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict

from fpdf import FPDF

# ── Copy Registry ─────────────────────────────────────────────────────────────
try:
    from ui.copy_de import COPY
except ImportError:
    # Fallback if running standalone
    COPY = {
        "uwg_footnote_high_load":
            "* Maximalwert bei hohem Stromverbrauch, z. B. vorhandener Wärmepumpe "
            "(ca. 8.000 kWh/Jahr). Ohne Wärmepumpe: Ersparnis geringer.",
        "uwg_footnote_household":
            "* Orientierungswert basierend auf typischem Haushaltsverbrauch (ca. 3.500 kWh/Jahr).",
        "roi_assumptions":
            "Annahmen: Strompreis 38 ct/kWh · 4,5 % APR · 10J. Finanzierung · "
            "MwSt. 0 % (EEG) · Einspeisevergütung 7,78 ct/kWh · Degradation 0,5 %/J.",
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _fmt(val: float) -> str:
    """German number format: 1.500"""
    return f"{abs(val):,.0f}".replace(",", ".")


def _setup_font(pdf: FPDF) -> tuple[str, str]:
    """Load Arial if available on Windows; fallback to Helvetica. Returns (font_name, euro_sym)."""
    arial_regular = "C:\\Windows\\Fonts\\arial.ttf"
    arial_bold    = "C:\\Windows\\Fonts\\arialbd.ttf"
    if os.path.exists(arial_regular) and os.path.exists(arial_bold):
        try:
            pdf.add_font("Sans", "",  arial_regular)
            pdf.add_font("Sans", "B", arial_bold)
            return "Sans", "€"
        except Exception:
            pass
    return "helvetica", "EUR"


def _extract_baseline(roi_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract BASELINE scenario (index 1) from roi_result."""
    scens = roi_result.get("scenarios", [])
    return scens[1] if len(scens) > 1 else (scens[0] if scens else {})


def _y1_savings_eur(roi_result: Dict[str, Any]) -> int:
    """Return Y1 annual_benefit in whole EUR."""
    return _extract_baseline(roi_result).get("annual_benefit_cents", 0) // 100


# ── Color Palette ─────────────────────────────────────────────────────────────
C_NAVY   = (10,  45,  90)
C_BLUE   = (0,  110, 190)
C_GREEN  = (39, 174,  96)
C_AMBER  = (211,  84,   0)
C_GRAY   = (90,  90,  90)
C_TEXT   = (25,  25,  25)
C_BGLT   = (248, 248, 248)


# ===========================================================================
# generate_vollbericht_pdf  (A4, Installer Leave-Behind)
# ===========================================================================
def generate_vollbericht_pdf(
    dual_roi: Dict[str, Any],
    street_ctx: Dict[str, Any] | None = None,
    policy_meta: Dict[str, Any] | None = None,
) -> bytes:
    """
    Generate A4 Vollbericht PDF with side-by-side dual-scenario ROI comparison.

    Args:
        dual_roi:    Output of calculate_roi_dual() — contains "household", "high_load",
                     "delta_annual_eur", "hp_uplift_class".
        street_ctx:  Optional dict with street_name, segment_id, plz etc.
        policy_meta: Optional dict for assumptions footer override.

    Returns:
        PDF bytes (latin-1 safe, fpdf2).
    """
    roi_hh  = dual_roi.get("household", {})
    roi_hl  = dual_roi.get("high_load", {})
    delta   = dual_roi.get("delta_annual_eur", 0)
    uplift  = dual_roi.get("hp_uplift_class", "MODERATE_HP_UPLIFT")

    hh_savings = _y1_savings_eur(roi_hh)
    hl_savings  = _y1_savings_eur(roi_hl)
    hh_base    = _extract_baseline(roi_hh)
    hl_base    = _extract_baseline(roi_hl)

    ctx = street_ctx or {}
    street_name = ctx.get("street_name", "")
    plz         = ctx.get("plz", "")
    seg_id      = ctx.get("segment_id", "")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    fn, euro = _setup_font(pdf)

    ts = datetime.datetime.now().strftime("%d.%m.%Y")

    # ── Header ───────────────────────────────────────────────────────────────
    pdf.set_fill_color(*C_NAVY)
    pdf.rect(0, 0, 210, 22, "F")

    pdf.set_font(fn, "B", 16)
    pdf.set_text_color(255, 255, 255)
    pdf.text(12, 13, "Ihre PV-Investition auf einen Blick")

    pdf.set_font(fn, "", 8)
    pdf.set_text_color(200, 215, 235)
    ctx_line = f"{street_name}  |  PLZ {plz}  |  {seg_id}" if street_name else f"PLZ {plz}  |  {seg_id}"
    pdf.text(12, 19, ctx_line)

    pdf.set_font(fn, "", 7)
    pdf.text(150, 19, f"Stand: {ts}  |  TerritoryAI")

    # ── Subtitle bar ─────────────────────────────────────────────────────────
    pdf.set_fill_color(*C_BGLT)
    pdf.rect(0, 22, 210, 8, "F")
    pdf.set_font(fn, "", 8)
    pdf.set_text_color(*C_GRAY)
    pdf.text(12, 27.5,
             "Orientierungshilfe fuer Ihre Beratung | Keine Anlageberatung | Vorbehaltlich Detailpruefung")

    # ── Two-column scenario comparison ───────────────────────────────────────
    y0   = 36
    colw = 90   # each scenario column width
    gap  = 8    # gap between columns
    lx   = 10   # left col x
    rx   = lx + colw + gap  # right col x

    def _draw_scenario_col(x: float, roi_result: Dict, label: str, color: tuple) -> None:
        """Draw one scenario column at x position."""
        base_sc   = _extract_baseline(roi_result)
        savings   = base_sc.get("annual_benefit_cents", 0) // 100
        payback   = base_sc.get("payback_dynamic_years", 999)
        profit20  = base_sc.get("profit20_cents", 0) // 100
        capex     = roi_result.get("capex", {}).get("vat0_cents", 0) // 100
        kwp       = roi_result.get("kWp_rec", 0)
        fin       = roi_result.get("financing_report", {})
        pmt       = fin.get("loan_monthly_payment_eur", 0)
        co2       = roi_result.get("co2_saved_tons_per_year", 0)

        # Header strip
        pdf.set_fill_color(*color)
        pdf.rect(x, y0, colw, 10, "F")
        pdf.set_font(fn, "B", 10)
        pdf.set_text_color(255, 255, 255)
        pdf.text(x + 4, y0 + 7, label)

        # KPI rows
        y_kpi = y0 + 14
        kpis = [
            ("Netto-Energievorteil (Jahr 1)", f"ca. {_fmt(savings)} {euro}/Jahr"),
            ("Amortisationszeit",             f"ca. {payback if payback < 999 else '>20'} Jahre"),
            ("Systemgroesse",                 f"{kwp} kWp"),
            ("Invest (MwSt. 0%)",             f"ca. {_fmt(capex)} {euro}"),
            ("Gesamtertrag 20 Jahre",          f"ca. {_fmt(profit20)} {euro}"),
            ("Kreditrate (10J/4,5%)",          f"ca. {_fmt(pmt)} {euro}/Mon."),
            ("CO2-Ersparnis",                  f"ca. {co2:.1f} t/Jahr"),
        ]
        pdf.set_text_color(*C_TEXT)
        for i, (lbl, val) in enumerate(kpis):
            y_row = y_kpi + i * 9
            # Alternating row background
            if i % 2 == 0:
                pdf.set_fill_color(*C_BGLT)
                pdf.rect(x, y_row - 5, colw, 9, "F")
            pdf.set_font(fn, "", 7.5)
            pdf.set_text_color(*C_GRAY)
            pdf.text(x + 4, y_row, lbl)
            pdf.set_font(fn, "B", 8)
            pdf.set_text_color(*C_TEXT)
            pdf.text(x + 4, y_row + 4.5, val)

    _draw_scenario_col(lx, roi_hh, "Standard-Haushalt (kein WP-Aufschlag)", C_BLUE)
    _draw_scenario_col(rx, roi_hl, "Hohe Last: Waermepumpe / E-Auto",       C_GREEN)

    # ── Delta highlight bar ───────────────────────────────────────────────────
    y_delta = y0 + 14 + 7 * 9 + 6
    pdf.set_fill_color(*C_AMBER)
    pdf.rect(10, y_delta, 190, 10, "F")
    pdf.set_font(fn, "B", 9)
    pdf.set_text_color(255, 255, 255)
    delta_lbl = (
        f"Moeglicher Mehrwert durch Waermepumpe/E-Auto: ca. +{_fmt(delta)} {euro}/Jahr"
        f"  |  HP-Uplift-Klasse: {uplift.replace('_', ' ')}"
    )
    pdf.text(14, y_delta + 7, delta_lbl)

    # ── Assumptions footer ────────────────────────────────────────────────────
    y_foot = 265
    pdf.set_fill_color(*C_BGLT)
    pdf.rect(0, y_foot, 210, 32, "F")

    pdf.set_font(fn, "B", 7.5)
    pdf.set_text_color(*C_NAVY)
    pdf.text(12, y_foot + 6, "Grundlegende Annahmen (alle Werte sind Orientierungswerte):")

    pdf.set_font(fn, "", 6.5)
    pdf.set_text_color(*C_GRAY)
    assumptions = COPY.get("roi_assumptions",
        "Strompreis 38 ct/kWh | Einspeisevergütung 7,78 ct/kWh | 4,5% APR / 10J. | MwSt. 0% (EEG)")
    pdf.set_xy(12, y_foot + 9)
    pdf.multi_cell(186, 3.5, assumptions)

    pdf.set_font(fn, "I", 6)
    pdf.set_text_color(*C_GRAY)
    pdf.text(12, y_foot + 23,
             "Dieses Dokument ist ausschliesslich fuer den internen Gebrauch des Installateurs bestimmt "
             "und nicht fuer die direkte Weitergabe an den Endkunden.")

    return bytes(pdf.output())


# ===========================================================================
# generate_flyer_pdf  (DIN-lang 210x99mm, B2C White-Label)
# ===========================================================================
def generate_flyer_pdf(
    dual_roi: Dict[str, Any],
    street_ctx: Dict[str, Any] | None = None,
    installer_brand: str = "Ihr lokaler PV-Spezialist",
    qr_code_url: str | None = None,
) -> bytes:
    """
    Generate DIN-lang (210 x 99 mm) B2C flyer. White-label — installer brand only.
    UWG §5 compliant: template selected automatically via hp_uplift_class.

    Args:
        dual_roi:        Output of calculate_roi_dual().
        street_ctx:      Optional dict with plz, street, batch for QR code context.
        installer_brand: Name shown on flyer (no TerritoryAI branding on B2C material).
        qr_code_url:     Optional URL to encode as QR (fallback: no QR shown).

    Returns:
        PDF bytes.
    """
    uplift      = dual_roi.get("hp_uplift_class", "MODERATE_HP_UPLIFT")
    roi_hh      = dual_roi.get("household", {})
    roi_hl      = dual_roi.get("high_load", {})

    hh_savings  = _y1_savings_eur(roi_hh)
    hl_savings  = _y1_savings_eur(roi_hl)
    fin         = roi_hl.get("financing_report", {}) if uplift != "LIMITED_HP_UPLIFT" else roi_hh.get("financing_report", {})
    pmt         = fin.get("loan_monthly_payment_eur", 0)
    kwp         = roi_hl.get("kWp_rec", roi_hh.get("kWp_rec", 10))
    capex       = roi_hl.get("capex", {}).get("vat0_cents", roi_hh.get("capex", {}).get("vat0_cents", 0)) // 100

    ctx         = street_ctx or {}
    plz         = ctx.get("plz", "")

    # ── UWG §5 Template selection ─────────────────────────────────────────────
    is_aggressive = uplift in ("STRONG_HP_UPLIFT", "MODERATE_HP_UPLIFT")
    if is_aggressive:
        headline_eur = rl_savings  = hl_savings
        footnote     = COPY["uwg_footnote_high_load"]
    else:
        headline_eur = hh_savings
        footnote     = COPY["uwg_footnote_household"]

    # Round down to nearest 50 for credible "Bis zu X" claim
    headline_eur_display = (headline_eur // 50) * 50

    # ── PDF Setup ─────────────────────────────────────────────────────────────
    pdf = FPDF(orientation="L", unit="mm", format=(99, 210))
    pdf.set_auto_page_break(False)
    pdf.add_page()
    fn, euro = _setup_font(pdf)

    W, H = 210, 99   # DIN-lang landscape (width=210, height=99)

    # ── Background ────────────────────────────────────────────────────────────
    pdf.set_fill_color(*C_NAVY)
    pdf.rect(0, 0, W, H, "F")

    # Right accent strip
    pdf.set_fill_color(*C_GREEN)
    pdf.rect(W - 55, 0, 55, H, "F")

    # ── MAIN HEADLINE (left zone) ─────────────────────────────────────────────
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(fn, "B", 11)
    pdf.text(8, 14, "Ihre Solaranlage.")

    pdf.set_font(fn, "B", 24)
    pdf.set_text_color(255, 230, 80)   # Gold
    if is_aggressive:
        pdf.text(8, 32, f"Bis zu {_fmt(headline_eur_display)} {euro}*")
    else:
        pdf.text(8, 32, f"Ca. {_fmt(headline_eur_display)} {euro}*")

    pdf.set_font(fn, "", 10)
    pdf.set_text_color(200, 220, 255)
    pdf.text(8, 42, "Stromkostenersparnis pro Jahr")

    # Financing line
    if pmt > 0:
        pdf.set_font(fn, "B", 9)
        pdf.set_text_color(255, 255, 255)
        pdf.text(8, 56, f"Ihre PV-Anlage ab {_fmt(pmt)} {euro}/Monat")
        pdf.set_font(fn, "", 7.5)
        pdf.set_text_color(180, 200, 230)
        pdf.text(8, 62, "(0 {euro} Anzahlung | 100% Finanzierung | MwSt. 0%)".format(euro=euro))

    # System size
    pdf.set_font(fn, "", 8)
    pdf.set_text_color(150, 180, 220)
    pdf.text(8, 74, f"Anlage ca. {kwp} kWp  |  Systemkosten ab {_fmt(capex)} {euro} (MwSt. 0%)")

    # ── FOOTNOTE (mandatory, same page — UWG §5) ──────────────────────────────
    pdf.set_font(fn, "", 6)
    pdf.set_text_color(150, 170, 210)
    pdf.set_xy(8, H - 14)
    pdf.multi_cell(W - 70, 3, footnote)

    # ── RIGHT ZONE (CTA + QR + Brand) ─────────────────────────────────────────
    rx = W - 52

    pdf.set_font(fn, "B", 9)
    pdf.set_text_color(*C_NAVY)
    pdf.text(rx, 15, "Jetzt pruefen")
    pdf.set_font(fn, "", 7.5)
    pdf.text(rx, 21, "wie viel Sie sparen:")

    # QR code placeholder (or real QR if qrcode lib available)
    if qr_code_url:
        try:
            import qrcode
            import io
            qr = qrcode.make(qr_code_url)
            buf = io.BytesIO()
            qr.save(buf, format="PNG")
            buf.seek(0)
            pdf.image(buf, x=rx, y=26, w=38, h=38)
        except ImportError:
            # qrcode not installed — draw placeholder box
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(rx, 26, 38, 38, "F")
            pdf.set_font(fn, "", 6)
            pdf.set_text_color(*C_GRAY)
            pdf.text(rx + 4, 47, "QR-Code")
    else:
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(rx, 26, 38, 38, "F")
        pdf.set_font(fn, "", 6)
        pdf.set_text_color(*C_GRAY)
        pdf.text(rx + 4, 47, "QR-Code")

    # Brand / CTA
    pdf.set_font(fn, "B", 8)
    pdf.set_text_color(*C_NAVY)
    pdf.text(rx, 70, installer_brand[:28])   # truncate to fit

    if plz:
        pdf.set_font(fn, "", 6.5)
        pdf.set_text_color(60, 80, 110)
        pdf.text(rx, 76, f"Ihr Angebot fuer PLZ {plz}")

    return bytes(pdf.output())
