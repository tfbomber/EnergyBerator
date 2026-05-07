"""
street_ranking_client.py  —  Client View v3
==========================================
Clean client-facing PV Street Ranking.  No technical scores.

Architecture  : 2-layer, session-state routing
  Layer 1     — Region cards (always fully expanded, no toggle needed)
  Layer 2     — Street drill-down (session-state page switch)

Language      : follows global i18n switcher (EN / DE)
FAIL streets  : shown grayed-out, brief note, no dismissal
"""

from __future__ import annotations

import re
import streamlit as st
import pandas as pd
from ui.i18n import get_lang

# Re-use the cached data loaders (no double parquet reads)
from ui.components.street_ranking_view import (
    _load_merged_data,
    _load_segment_df,
    _load_street_df,
)

# Street-level ROI expander (reused from analyst view)
from ui.components.street_roi_generator import render_street_roi_expander

# ── Session-state keys ────────────────────────────────────────────────────────
_S_VIEW   = "cli_view"     # "overview" | "street_detail"
_S_SEG_ID = "cli_seg_id"   # active segment_id in street_detail mode

# ── PLZ → Stadtteil mapping (user-verified) ───────────────────────────────────
PLZ_STADTTEIL: dict[str, str] = {
    "41460": "Innenstadt / Hammfeld / Hafen",
    "41462": "Vogelsang / Weißenberg / Neuss-Nord",
    "41464": "Pomona / Westfeld",
    "41466": "Weckhoven / Reuschenberg / Neuss-Süd",
    "41468": "Uedesheim / Grimlinghausen",
    "41469": "Norf / Helpenstein",
    "41470": "Allerheiligen / Rosellen",
    "41472": "Holzheim / Grefrath",
}


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────

def _plz(seg_id: str) -> str:
    m = re.search(r"(\d{5})", seg_id)
    return m.group(1) if m else seg_id


def _stadtteil(seg_id: str, seg_row: pd.Series) -> str:
    """Return human area name, falling back to Stadtteil map or raw PLZ."""
    plz_str = _plz(seg_id)
    # Use Stadtteil map first; fall back to street_name if it already has a
    # readable label (e.g. "Holzheim / Grefrath (PLZ 41472)")
    if plz_str in PLZ_STADTTEIL:
        return PLZ_STADTTEIL[plz_str]
    name = str(seg_row.get("street_name", ""))
    if name and not name.startswith("NEUSS_PLZ"):
        # strip trailing "(PLZ xxxxx)" if present
        return re.sub(r"\s*\(PLZ\s*\d+\)\s*$", "", name).strip()
    return f"PLZ {plz_str}"


def _pct(n: float) -> str:
    return f"{n:.0%}"


def _round50(n: int) -> int:
    return max(50, (n // 50) * 50)


# ─────────────────────────────────────────────────────────────────────────────
# Region-level insight builder
# ─────────────────────────────────────────────────────────────────────────────

def _house_type_line(
    efh: int, dh: int, rh: int, total_bld: int, lang: str
) -> str | None:
    """Generate a plain-language house-type composition line.
    Individual type counts are rounded to nearest 50 (avoid false precision from OSM data).
    """
    sfh_total = efh + dh + rh
    if sfh_total == 0 or total_bld == 0:
        return None
    sfh_pct = sfh_total / total_bld

    parts: list[str] = []
    if efh > 0:
        label = "Freistehend" if lang == "de" else "Detached"
        parts.append(f"~{_round50(efh):,} {label}".replace(",", "."))
    if dh > 0:
        label = "Doppelhaus" if lang == "de" else "Semi-detached"
        parts.append(f"~{_round50(dh):,} {label}".replace(",", "."))
    if rh > 0:
        label = "Reihenhaus" if lang == "de" else "Terraced"
        parts.append(f"~{_round50(rh):,} {label}".replace(",", "."))

    breakdown   = " · ".join(parts)
    total_label = "Gebäude gesamt" if lang == "de" else "buildings total"
    sfh_label   = "Einfamilienhäuser" if lang == "de" else "single-family homes"

    return (
        f"🏠 **{_pct(sfh_pct)} {sfh_label}** — {breakdown}"
        f"  *(von ~{_round50(total_bld):,} {total_label})*".replace(",", ".")
    )


def _pv_market_line(pv_cov: float, lang: str) -> str:
    """Market-openness framing based on PV adoption rate.

    SEMANTIC NOTE: pv_coverage_score in parquet = market_gap (field_04 value).
      market_gap = 1 - adoption_rate
      HIGH market_gap (e.g. 0.87) = LOW adoption (~13%) = large open market
      LOW  market_gap (e.g. 0.19) = HIGH adoption (~81%) = saturated market
    We convert to adoption_rate before applying thresholds so a high value
    means 'many households already have PV' — matching intuitive language.
    """
    adoption_rate = 1.0 - pv_cov  # market_gap → adoption_rate
    if adoption_rate >= 0.65:
        # >=65% already have PV → market largely saturated
        return (
            "📡 " + ("PV bereits weit verbreitet im Gebiet — verbleibende Haushalte gezielt qualifizieren"
                     if lang == "de"
                     else "PV already widely adopted — qualify remaining households selectively")
        )
    if adoption_rate >= 0.35:
        return (
            "📈 " + ("PV in der Region im Aufbau — noch viele Haushalte ohne Anlage"
                     if lang == "de"
                     else "PV adoption growing — many households still without a system")
        )
    return (
        "📈 " + ("Solarenergie noch wenig verbreitet — großes unerschlossenes Potenzial"
                 if lang == "de"
                 else "Solar still rare here — large untapped market potential")
    )


def _roof_line(roof_norm: float, lang: str) -> str:
    """Roof quality → PV yield potential framing (sales-oriented, action-guiding)."""
    if roof_norm >= 0.80:
        return (
            "☀️ " + ("Hervorragende Dachausrichtung — maximaler Solarertrag zu erwarten"
                     if lang == "de"
                     else "Excellent roof orientation — maximum solar yield expected")
        )
    if roof_norm >= 0.55:
        return (
            "☀️ " + ("Gute Dachlage — solider PV-Ertrag, Anlage rechnet sich gut"
                     if lang == "de"
                     else "Good roof orientation — solid PV output, system pays off well")
        )
    if roof_norm >= 0.25:
        return (
            "☀️ " + ("Solarpotenzial vorhanden — individuelle Dachprüfung vor Angebotserstellung empfohlen"
                     if lang == "de"
                     else "Solar potential present — individual roof check recommended before quote")
        )
    return (
        "☀️ " + ("Dachsituation heterogen — Vor-Ort-Check empfohlen (Verschattung und Ausrichtung)"
                 if lang == "de"
                 else "Roof situation mixed — on-site check recommended (shading and orientation)")
    )


def _heat_hp_line(heat: str, hp: str, tmpl: str, lang: str) -> str | None:
    """Fernwärme + Wärmepumpe framing.
    Uses epistemic qualifiers (bekannt/aktuell) — avoids overclaiming absence of planned networks.
    """
    no_fern   = heat in ("NO_SIGNAL", "LOW_NETWORK_SIGNAL")
    strong_hp = hp == "STRONG_HP_UPLIFT"
    mod_hp    = hp == "MODERATE_HP_UPLIFT"
    enhanced  = tmpl == "PV_HP_ENHANCED"

    if no_fern and (strong_hp or enhanced):
        return (
            "🔋 " + ("Kein bekanntes Fernwärmenetz — PV+Wärmepumpe aktuell gut integrierbar"
                     if lang == "de"
                     else "No known district heating — PV+heat pump currently well-feasible")
        )
    if no_fern and mod_hp:
        return (
            "🔋 " + ("Kein bekanntes Fernwärmenetz — Wärmepumpe gut kombinierbar mit PV"
                     if lang == "de"
                     else "No known district heating — heat pump combines well with PV")
        )
    if no_fern:
        return (
            "✅ " + ("Kein bekanntes Fernwärmenetz — freie Wahl der Heizungstechnologie"
                     if lang == "de"
                     else "No known district heating — free choice of heating technology")
        )
    if heat in ("LIMITED_OR_UNCLEAR", "PLANNED_DISTRICT_HEAT"):
        return (
            "⚠️ " + ("Fernwärme möglicherweise in Planung — Heizungssituation im Erstgespräch klären"
                     if lang == "de"
                     else "District heating possibly planned — confirm heating setup in first conversation")
        )
    if heat == "STRONG_DISTRICT_HEAT":
        return (
            "⚠️ " + ("Fernwärme vorhanden — PV-Only empfohlen, Wärmepumpe derzeit weniger geeignet"
                     if lang == "de"
                     else "District heating present — PV-only recommended, heat pump less viable currently")
        )
    return None


def _build_region_insights(
    seg_row: pd.Series,
    seg_streets: pd.DataFrame,
    lang: str,
) -> list[str]:
    """Build ordered list of plain-language insight lines for a region card."""
    lines: list[str] = []

    # 1. House-type composition (strongest signal)
    efh = int(seg_streets["sfh_detached_count"].sum()) if "sfh_detached_count" in seg_streets.columns else 0
    dh  = int(seg_streets["sfh_semi_count"].sum())     if "sfh_semi_count"     in seg_streets.columns else 0
    rh  = int(seg_streets["sfh_rowhouse_count"].sum()) if "sfh_rowhouse_count" in seg_streets.columns else 0
    total_bld = int(seg_streets["building_count_total"].sum()) if "building_count_total" in seg_streets.columns else 0
    ht_line = _house_type_line(efh, dh, rh, total_bld, lang)
    if ht_line:
        lines.append(ht_line)

    # 2. Roof quality → PV yield
    roof_norm = float(seg_row.get("roof_suitability_score_norm", 0.5) or 0.5)
    lines.append(_roof_line(roof_norm, lang))

    # 3. Fernwärme + Wärmepumpe
    heat = str(seg_row.get("heat_status", "UNKNOWN"))
    hp   = str(seg_row.get("hp_status",   "UNKNOWN"))
    tmpl = str(seg_row.get("roi_report_template_flag", ""))
    hp_line = _heat_hp_line(heat, hp, tmpl, lang)
    if hp_line:
        lines.append(hp_line)

    # 4. Market openness (PV coverage)
    pv_cov = float(seg_row.get("pv_coverage_score", 0.5) or 0.5)
    lines.append(_pv_market_line(pv_cov, lang))

    # 4b. Field capacity — key ranking driver (moved to narrative so it’s visible)
    _active_gates   = {"PASS", "QUALIFIED"}
    n_suitable      = len(seg_streets[seg_streets["structure_gate"].isin(_active_gates)])
    n_total_streets = len(seg_streets)
    if n_suitable > 0:
        if n_suitable >= 30:
            cap_lbl = "Große Feldkapazität" if lang == "de" else "High field capacity"
        elif n_suitable >= 15:
            cap_lbl = "Solide Feldkapazität" if lang == "de" else "Solid field capacity"
        else:
            cap_lbl = "Fokussierter Einsatz" if lang == "de" else "Focused deployment"
        streets_lbl = "Straßen" if lang == "de" else "streets"
        total_lbl   = "gesamt" if lang == "de" else "total"
        lines.append(
            f"📍 {n_suitable} einsatzbereite {streets_lbl} "
            f"(von {n_total_streets} {total_lbl}) — {cap_lbl}"
        )

    # 5. Caution (ethical: never suppress — but deduplicate heat warnings)
    caution = str(seg_row.get("primary_caution", "")).strip()
    _heat_caution_keys = {
        "District-heating planning risk — qualify before pitch",
        "Low confidence — validate heating data before pitch",
    }
    # If the heat/HP line already displayed a Fernwaerme warning (starts with ⚠️),
    # skip the district-heating caution from primary_caution to avoid duplication.
    _heat_already_shown = hp_line is not None and hp_line.startswith("⚠️")
    _is_heat_caution    = caution in _heat_caution_keys

    if caution and not (_heat_already_shown and _is_heat_caution):
        _CAUTION_DE = {
            "SFH classification via proxy — recommend field confirmation":
                "⚠️ Gebäudetypen teilweise geschätzt — Ortsbegehung empfohlen",
            "District-heating planning risk — qualify before pitch":
                "⚠️ Fernwärme möglicherweise geplant — Heizungssituation im Erstgespräch klären",
            "Low confidence — validate heating data before pitch":
                "⚠️ Heizungstyp nicht vollständig erfasst — bitte im Erstgespräch erfragen",
            "Mixed structure — some units may not qualify":
                "⚠️ Gemischte Bebauung — erhöhte Streuverluste im Vertrieb · Straßen vorab filtern",
        }
        _CAUTION_EN = {
            "SFH classification via proxy — recommend field confirmation":
                "⚠️ Building types partly estimated — on-site check recommended",
            "District-heating planning risk — qualify before pitch":
                "⚠️ District heating possibly planned — clarify heating situation first",
            "Low confidence — validate heating data before pitch":
                "⚠️ Heating type not fully captured — please confirm in first conversation",
            "Mixed structure — some units may not qualify":
                "⚠️ Mixed housing types — higher sales scatter · pre-filter streets before canvassing",
        }
        c_map = _CAUTION_DE if lang == "de" else _CAUTION_EN
        lines.append(c_map.get(caution, f"⚠️ {caution}"))

    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Street-level narrative builder
# ─────────────────────────────────────────────────────────────────────────────

def _street_narrative(s: pd.Series, lang: str) -> str:
    """
    Construct a plain-language one-liner explaining why this street ranks well.
    Uses actual house counts, not the template sales_story field.
    """
    efh = int(s.get("sfh_detached_count", 0))
    dh  = int(s.get("sfh_semi_count",     0))
    rh  = int(s.get("sfh_rowhouse_count", 0))
    sfh_total = efh + dh + rh
    total_bld = int(s.get("building_count_total", 0))

    if sfh_total == 0 or total_bld == 0:
        return ""

    sfh_pct = sfh_total / total_bld

    # Dominant type
    dominant = max([(efh, "efh"), (dh, "dh"), (rh, "rh")], key=lambda x: x[0])[1]

    parts: list[str] = []
    if efh > 0:
        lbl = "Freistehend" if lang == "de" else "Detached"
        parts.append(f"{efh}× {lbl}")
    if dh > 0:
        lbl = "Doppelhaus" if lang == "de" else "Semi-det."
        parts.append(f"{dh}× {lbl}")
    if rh > 0:
        lbl = "Reihenhaus" if lang == "de" else "Terraced"
        parts.append(f"{rh}× {lbl}")

    bld_summary = " · ".join(parts)

    if lang == "de":
        if dominant == "efh" and sfh_pct >= 0.85:
            narrative = "Fast ausschließlich Einfamilienhäuser — große Dachflächen, beste Voraussetzungen"
        elif dominant == "efh":
            narrative = "Überwiegend Einfamilienhäuser — gute Montage­bedingungen"
        elif dominant == "dh":
            narrative = "Viele Doppelhäuser — kompakte Bebauung, PV gut realisierbar"
        elif dominant == "rh":
            narrative = "Reihenhäuser dominieren — Sammelinstallation möglich, Kosten teilbar"
        else:
            narrative = "Gemischte Bebauung — Einfamilienhäuser im Fokus"
    else:
        if dominant == "efh" and sfh_pct >= 0.85:
            narrative = "Almost exclusively detached homes — large roofs, ideal conditions"
        elif dominant == "efh":
            narrative = "Mostly detached homes — good installation conditions"
        elif dominant == "dh":
            narrative = "Many semi-detached homes — PV well-achievable"
        elif dominant == "rh":
            narrative = "Terraced houses dominate — collective installation possible, costs shareable"
        else:
            narrative = "Mixed housing — single-family homes are the focus"

    return f"{bld_summary}  ·  {narrative}"


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — Street Drill-Down
# ─────────────────────────────────────────────────────────────────────────────

def _render_street_detail(
    seg_id: str,
    seg_row: pd.Series,
    street_df: pd.DataFrame,
) -> None:
    lang      = get_lang()
    plz_str   = _plz(seg_id)
    area_name = _stadtteil(seg_id, seg_row)

    # ── Back + header ───────────────────────────────────────────────────────
    col_back, col_title = st.columns([2, 9])
    with col_back:
        back_lbl = "← Zurück" if lang == "de" else "← Back"
        if st.button(back_lbl, key="cli_back_btn"):
            st.session_state[_S_VIEW]   = "overview"
            st.session_state[_S_SEG_ID] = None
            st.rerun()
    with col_title:
        st.markdown(
            f"#### 🏘 {area_name}"
            f"<span style='font-size:0.78em;opacity:0.55;margin-left:8px'>PLZ {plz_str}</span>",
            unsafe_allow_html=True,
        )

    # ── PV saturation chip (PLZ-level MaStR data) ───────────────────────────────
    # pv_coverage_score = market_gap (field_04). Convert to adoption_rate for display.
    # HIGH market_gap = LOW adoption = open market (green chip)
    # LOW  market_gap = HIGH adoption = saturated market (red chip)
    pv_cov = float(seg_row.get("pv_coverage_score", 0.5) or 0.5)
    adoption_rate = 1.0 - pv_cov  # market_gap → PV adoption rate
    if adoption_rate < 0.35:
        _pv_icon, _pv_border = "☀️", "#2e8b57"
        _pv_bg  = "rgba(46,139,87,0.10)"
        _pv_txt = (
            "Niedriger PV-Anteil im PLZ — Markt weitgehend offen"
            if lang == "de" else
            "Low PV adoption in PLZ — market largely untapped"
        )
    elif adoption_rate < 0.65:
        _pv_icon, _pv_border = "📈", "#b8860b"
        _pv_bg  = "rgba(184,134,11,0.10)"
        _pv_txt = (
            "Mittlerer PV-Anteil — Markt im Aufbau"
            if lang == "de" else
            "Moderate PV adoption — market growing"
        )
    else:
        _pv_icon, _pv_border = "📡", "#8b0000"
        _pv_bg  = "rgba(139,0,0,0.07)"
        _pv_txt = (
            "Hoher PV-Anteil im PLZ — verbleibende Haushalte selektiv ansprechen"
            if lang == "de" else
            "High PV adoption in PLZ — target remaining households selectively"
        )
    st.markdown(
        f"<div style='display:inline-block;padding:4px 12px;margin:4px 0 8px;"
        f"background:{_pv_bg};border-left:3px solid {_pv_border};"
        f"border-radius:2px 4px 4px 2px;font-size:0.82em'>"
        f"{_pv_icon} {_pv_txt} &ensp;<b>({adoption_rate:.0%} PLZ-Ø)</b></div>",
        unsafe_allow_html=True,
    )

    # ── Caption + divider ──────────────────────────────────────────────────
    st.caption(
        "Straßen nach Eignung sortiert. Alle SFH-geeigneten Straßen enthalten ein ROI-Profil."
        if lang == "de" else
        "Streets sorted by suitability. All SFH-suitable streets include a ROI profile."
    )
    st.markdown("---")

    # ── Load streets + split active vs FAIL ─────────────────────────────────
    seg_streets = (
        street_df[street_df["segment_id"] == seg_id]
        .sort_values("adjusted_street_score", ascending=False)
    )
    if seg_streets.empty:
        msg = "Keine Straßendaten verfügbar." if lang == "de" else "No street data available."
        st.info(msg)
        return

    _active_gates = {"PASS", "QUALIFIED", "REVIEW"}
    active = seg_streets[seg_streets["structure_gate"].isin(_active_gates)]
    fails  = seg_streets[~seg_streets["structure_gate"].isin(_active_gates)]

    # ── Active street cards (bordered) ───────────────────────────────────
    for rank_i, (_, s) in enumerate(active.iterrows(), start=1):
        gate       = str(s.get("structure_gate", "?"))
        addr_range = str(s.get("address_range", "")).strip()
        low_sample = bool(s.get("low_sample_flag", False))
        narrative  = _street_narrative(s, lang)

        if gate == "PASS":
            gate_lbl = "✅ " + ("Sehr geeignet" if lang == "de" else "Very suitable")
        elif gate == "QUALIFIED":
            gate_lbl = "🟢 " + ("Geeignet" if lang == "de" else "Suitable")
        else:
            gate_lbl = "🔍 " + ("Prüfung nötig" if lang == "de" else "Needs review")

        addr_line = (
            (f"Nr. {addr_range}  ·  " if addr_range else "") + f"PLZ {plz_str}"
        )

        with st.container(border=True):
            c_rank, c_info, c_gate_col = st.columns([1, 8, 3])

            with c_rank:
                st.markdown(
                    f"<div style='font-size:1.20em;font-weight:700;"
                    f"padding-top:6px;text-align:center'>#{rank_i}</div>",
                    unsafe_allow_html=True,
                )
            with c_info:
                st.markdown(
                    f"<div style='font-weight:700;font-size:1.02em;margin-bottom:2px'>"
                    f"{s['street_name']}</div>"
                    f"<div style='font-size:0.78em;opacity:0.50'>{addr_line}</div>",
                    unsafe_allow_html=True,
                )
                if narrative:
                    st.markdown(
                        f"<div style='font-size:0.85em;opacity:0.72;"
                        f"margin-top:4px;line-height:1.4'>{narrative}</div>",
                        unsafe_allow_html=True,
                    )
            with c_gate_col:
                st.markdown(
                    f"<div style='text-align:right;padding-top:6px;"
                    f"font-size:0.88em'>{gate_lbl}</div>",
                    unsafe_allow_html=True,
                )

            if low_sample:
                warn = (
                    "⚠️ Kleine Datenbasis — Einschätzung vorläufig"
                    if lang == "de" else
                    "⚠️ Small data sample — assessment provisional"
                )
                st.markdown(
                    f"<div style='padding:3px 10px;margin-top:4px;"
                    f"background:rgba(230,160,32,0.10);"
                    f"border-left:3px solid #e0a020;"
                    f"border-radius:2px 4px 4px 2px;font-size:0.78em'>{warn}</div>",
                    unsafe_allow_html=True,
                )

            # Q2 fix: ROI entry point at street level
            render_street_roi_expander(s)

    # ── FAIL streets — collapsed at bottom ──────────────────────────────────────
    if not fails.empty:
        n_fail   = len(fails)
        fail_hdr = (
            f"Nicht im Fokus ({n_fail} Straßen)"
            if lang == "de" else
            f"Not in focus ({n_fail} streets)"
        )
        with st.expander(fail_hdr, expanded=False):
            st.caption(
                "Diese Straßen haben einen höheren Mehrfamilienhausanteil "
                "und werden derzeit nicht priorisiert."
                if lang == "de" else
                "These streets have a higher multi-family share "
                "and are not currently prioritised."
            )
            for _, s in fails.iterrows():
                mfh = int(s.get("mfh_count", 0))
                sfh = int(s.get("sfh_total_count", 0))
                bld_note = ""
                if mfh > 0 or sfh > 0:
                    bld_note = f" — {mfh} MFH" + (f" / {sfh} SFH" if sfh > 0 else "")
                st.markdown(
                    f"**{s['street_name']}**"
                    f"<span style='opacity:0.45;font-size:0.84em'>{bld_note}</span>",
                    unsafe_allow_html=True,
                )




# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — Region Overview Cards (always fully expanded)
# ─────────────────────────────────────────────────────────────────────────────

def _render_segment_card(
    seg_row: pd.Series,
    street_df: pd.DataFrame,
    rank: int,
    lang: str,
) -> None:
    """Render one region card. Called by _render_overview for each tier group."""
    rank_icon = {1: "🔥", 2: "📍", 3: "📋"}
    seg_id    = str(seg_row.get("street_id", ""))
    plz_str   = _plz(seg_id)
    area_name = _stadtteil(seg_id, seg_row)
    icon      = rank_icon.get(rank, "📋")

    seg_streets = street_df[street_df["segment_id"] == seg_id]
    n_streets   = len(seg_streets)
    n_pass      = int((seg_streets["structure_gate"].isin(["PASS", "QUALIFIED"])).sum()) \
                  if "structure_gate" in seg_streets.columns else 0

    with st.container(border=True):
        c_left, c_right = st.columns([8, 3])

        # ── Left: title + compact insight block ───────────────────────────
        with c_left:
            st.markdown(
                f"<div style='font-size:1.05em;font-weight:700;margin-bottom:6px'>"
                f"{icon} #{rank}&nbsp;&nbsp;{area_name}"
                f"<span style='font-size:0.72em;opacity:0.50;margin-left:10px'>"
                f"PLZ {plz_str}</span></div>",
                unsafe_allow_html=True,
            )
            insights = _build_region_insights(seg_row, seg_streets, lang)
            insight_html = "".join(
                f"<div style='margin:2px 0;font-size:0.88em;line-height:1.5'>{ln}</div>"
                for ln in insights
            )
            st.markdown(insight_html, unsafe_allow_html=True)

        # ── Right: stats + CTA button ─────────────────────────────────────
        with c_right:
            streets_lbl  = "Straßen" if lang == "de" else "streets"
            suitable_lbl = "geeignet" if lang == "de" else "suitable"
            stats_html = (
                f"<div style='font-size:0.82em;opacity:0.60;"
                f"text-align:right;line-height:1.8;margin-bottom:6px'>"
                f"<b>{n_streets}</b> {streets_lbl}"
                + (f"<br><b>{n_pass}</b> {suitable_lbl}" if n_pass > 0 else "")
                + "</div>"
            )
            st.markdown(stats_html, unsafe_allow_html=True)

            cta_label = "🏘 Straßen →" if lang == "de" else "🏘 Streets →"
            if st.button(
                cta_label,
                key=f"cli_street_btn_{seg_id}",
                type="primary",
                use_container_width=True,
            ):
                st.session_state[_S_VIEW]   = "street_detail"
                st.session_state[_S_SEG_ID] = seg_id
                st.rerun()


def _render_overview(seg_df: pd.DataFrame, street_df: pd.DataFrame) -> None:
    lang = get_lang()

    # ── Split by canvass_tier (fail-safe: missing col → all PRIMARY) ──────────
    if "canvass_tier" in seg_df.columns:
        primary   = seg_df[seg_df["canvass_tier"] == "PRIMARY"].sort_values("rank")
        secondary = seg_df[seg_df["canvass_tier"] == "SECONDARY"].sort_values("rank")
        not_rec   = seg_df[seg_df["canvass_tier"] == "NOT_RECOMMENDED"].sort_values("rank")
    else:
        primary, secondary, not_rec = seg_df.sort_values("rank"), pd.DataFrame(), pd.DataFrame()

    # ── 🟢 Primary tier ───────────────────────────────────────────────────────
    if not primary.empty:
        hdr = "🟢 Sofort aktiv — kein Fernwärme-Risiko" if lang == "de" \
              else "🟢 Ready to Canvass — no district heating risk"
        st.markdown(
            f"<div style='font-size:0.80em;font-weight:700;letter-spacing:0.06em;"
            f"opacity:0.65;margin:8px 0 6px 2px;text-transform:uppercase'>{hdr}</div>",
            unsafe_allow_html=True,
        )
        for rank_idx, (_, seg_row) in enumerate(primary.iterrows(), start=1):
            _render_segment_card(seg_row, street_df, rank_idx, lang)

    # ── 🟡 Secondary tier ─────────────────────────────────────────────────────
    if not secondary.empty:
        hdr = "🟡 Vor Besuch bestätigen — Fernwärme-Situation klären" if lang == "de" \
              else "🟡 Confirm First — clarify district heating situation"
        st.markdown(
            f"<div style='font-size:0.80em;font-weight:700;letter-spacing:0.06em;"
            f"opacity:0.65;margin:18px 0 4px 2px;text-transform:uppercase'>{hdr}</div>",
            unsafe_allow_html=True,
        )
        note = (
            "Diese Gebiete haben ein gutes PV-Potenzial, aber ein mittleres Fernwärme-Signal. "
            "Bitte vorab telefonisch klären, bevor Ressourcen eingesetzt werden."
        ) if lang == "de" else (
            "These areas have good PV potential, but a medium district-heating signal. "
            "Please confirm by phone before deploying canvassing resources."
        )
        st.caption(note)
        for sec_idx, (_, seg_row) in enumerate(secondary.iterrows(), start=1):
            _render_segment_card(seg_row, street_df, sec_idx, lang)

    # ── 🔴 Not recommended (rare — shown collapsed) ───────────────────────────
    if not not_rec.empty:
        hdr = "🔴 Nicht empfohlen — hohes Fernwärme-Risiko" if lang == "de" \
              else "🔴 Not Recommended — high district heating risk"
        with st.expander(hdr, expanded=False):
            for nr_idx, (_, seg_row) in enumerate(not_rec.iterrows(), start=1):
                _render_segment_card(seg_row, street_df, nr_idx, lang)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (no title / caption / info banner — clean slate for clients)
# ─────────────────────────────────────────────────────────────────────────────

def render_street_ranking_client() -> None:
    """Render the client-facing PV Street Ranking. No technical scores exposed."""
    lang = get_lang()

    # ── Cache-clear shortcut (sidebar, developer use only) ────────────────────
    with st.sidebar:
        if st.button("🔄 Daten neu laden", key="cli_cache_clear",
                     help="Parquet-Cache leeren und Daten neu einlesen"):
            _load_segment_df.clear()
            _load_street_df.clear()
            _load_merged_data.clear()
            st.rerun()

    seg_df, street_df = _load_merged_data()
    if seg_df.empty:
        st.info("Keine Daten verfügbar." if lang == "de" else "No data available.")
        return

    view = st.session_state.get(_S_VIEW, "overview")

    if view == "street_detail":
        seg_id = st.session_state.get(_S_SEG_ID)
        if seg_id:
            match = seg_df[seg_df["street_id"] == seg_id]
            if not match.empty:
                _render_street_detail(seg_id, match.iloc[0], street_df)
                return
        # Fallback: segment not found → back to overview
        st.session_state[_S_VIEW] = "overview"
        st.rerun()

    _render_overview(seg_df, street_df)

