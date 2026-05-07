"""
ui/i18n.py
==========
D-ESS Internationalization (i18n) — English / German

Usage:
    from ui.i18n import t, get_lang, LANGS

    # In any Streamlit component:
    st.markdown(f"## {t('street_ranking.title')}")

Language is stored in st.session_state["lang"].
Default: "en".  Supported: "en", "de".

Language switcher widget:
    from ui.i18n import render_lang_switcher
    render_lang_switcher()   # call from sidebar
"""
from __future__ import annotations

import streamlit as st

LANGS = {"en": "🇬🇧 English", "de": "🇩🇪 Deutsch"}
DEFAULT_LANG = "en"

# ---------------------------------------------------------------------------
# Translation table
# key → {lang: string}
# ---------------------------------------------------------------------------
_T: dict[str, dict[str, str]] = {

    # ── App / global ─────────────────────────────────────────────────────────
    "app.title":                    {"en": "D-ESS MVP v1.1 Workspace",     "de": "D-ESS MVP v1.1 Arbeitsbereich"},
    "app.nav_title":                {"en": "D-ESS Navigator 🧭",           "de": "D-ESS Navigator 🧭"},
    "app.lang_label":               {"en": "Language",                     "de": "Sprache"},
    "app.back_scan":                {"en": "👈 Back to Quick Scan",        "de": "👈 Zurück zum Quick Scan"},

    # ── Navigator — Section 1: Data Intake ───────────────────────────────────
    "nav.section_intake":           {"en": "#### 📥 Data Intake",          "de": "#### 📥 Datenerfassung"},
    "nav.overview":                 {"en": "📄 1. Project Overview",       "de": "📄 1. Projektübersicht"},
    "nav.input_facts":              {"en": "📝 2. Input Facts",            "de": "📝 2. Dateneingabe"},
    "nav.house_info":               {"en": "- 🏠 Property details",        "de": "- 🏠 Gebäudedaten"},
    "nav.project_type":             {"en": "- ⚡ Project type (PV/HP)",    "de": "- ⚡ Projekttyp (PV/WP)"},
    "nav.quote":                    {"en": "- 💶 Quote / Contract",        "de": "- 💶 Angebot / Vertrag"},
    "nav.subsidy_path":             {"en": "**Subsidy path (auto-derived)**", "de": "**Förderweg (automatisch)**"},
    "nav.kfw":                      {"en": "KfW 458 Federal programme",    "de": "KfW 458 Bundesförderung"},
    "nav.bafa":                     {"en": "BAFA Federal programme (opt.)", "de": "BAFA Bundesförderung (optional)"},
    "nav.city_programme":           {"en": "Düsseldorf city programme",    "de": "Düsseldorfer Stadtprogramm"},
    "nav.output_modules":           {"en": "**Output modules**",           "de": "**Ausgabemodule**"},
    "nav.timeline":                 {"en": "⏳ Compliance Timeline",       "de": "⏳ Förder-Zeitplan"},
    "nav.report":                   {"en": "📊 Report & Export",           "de": "📊 Bericht & Export"},

    # ── Navigator — Section 2: Core Analysis ─────────────────────────────────
    "nav.section_analysis":         {"en": "#### 🔬 Core Analysis",        "de": "#### 🔬 Kernanalyse"},
    "nav.neuss_mvp":                {"en": "📍 Neuss MVP Target",          "de": "📍 Neuss MVP Zielgebiet"},
    "nav.foundation_filter":        {"en": "🏗️ Foundation Filter",         "de": "🏗️ Strukturfilter"},
    "nav.layer2_review":            {"en": "🔍 Layer 2 Review",            "de": "🔍 Ebene-2-Vorschau"},
    "nav.general_workspace":        {"en": "📊 General Track Workspace",   "de": "📊 Allgemeiner Arbeitsbereich"},
    "nav.street_ranking_internal":  {"en": "🏘 PV Street Ranking (Internal)", "de": "🏘 PV Straßenranking (Intern)"},

    # ── Navigator — Section 3: Customer View ─────────────────────────────────
    "nav.section_customer":         {"en": "#### 👤 Customer View",        "de": "#### 👤 Kundenansicht"},
    "nav.street_ranking_customer":  {"en": "🏘 PV Street Ranking (Client)", "de": "🏘 PV Straßenranking (Kunde)"},
    "nav.roi_report_customer":      {"en": "📄 ROI Report (Client)",       "de": "📄 ROI-Bericht (Kunde)"},

    # ── Street Ranking View ───────────────────────────────────────────────────
    "srk.title":                    {"en": "## 🏘 PV Opportunity — Street Ranking", "de": "## 🏘 PV-Potenzial — Straßenranking"},
    "srk.subtitle":                 {
        "en": "Region cards ranked by segment opportunity score (ROI × deployment × risk). "
              "Click a region to view its streets ranked by building quality. "
              "No household-level claims implied.",
        "de": "Regionskarten nach Segmentpotenzial sortiert (ROI × Einsatz × Risiko). "
              "Klicken Sie eine Region, um die Straßen nach Gebäudequalität anzuzeigen. "
              "Keine haushaltsbezogenen Aussagen.",
    },
    "srk.warn_no_segments":         {
        "en": "⚠️ Segment ranking data not found. Run `python fields/field_07_street_ranking.py` first.",
        "de": "⚠️ Segment-Rankingdaten nicht gefunden. Bitte zuerst `python fields/field_07_street_ranking.py` ausführen.",
    },
    "srk.warn_no_streets":          {
        "en": "⚠️ Street-level data not found. Run `python fields/field_08_street_level_ranking.py` first.",
        "de": "⚠️ Straßendaten nicht gefunden. Bitte zuerst `python fields/field_08_street_level_ranking.py` ausführen.",
    },
    "srk.no_data":                  {"en": "No segment data available.",   "de": "Keine Segmentdaten verfügbar."},

    # Metrics
    "srk.metric_regions":           {"en": "Regions",                      "de": "Regionen"},
    "srk.metric_streets":           {"en": "Streets total",                "de": "Straßen gesamt"},
    "srk.metric_top_score":         {"en": "Top Score",                    "de": "Top-Score"},
    "srk.metric_canvass":           {"en": "🟢 Canvass-ready",            "de": "🟢 Canvass-bereit"},
    "srk.metric_canvass_help":      {
        "en": "Streets with Gate=PASS and sufficient building data. Ready for outreach.",
        "de": "Straßen mit Gate=PASS und ausreichend Gebäudedaten. Sofort ansprechbar.",
    },

    # Region card
    "srk.card_streets_count":       {"en": "streets",                      "de": "Straßen"},
    "srk.card_ready":               {"en": "ready now",                    "de": "sofort ansprechbar"},
    "srk.card_score":               {"en": "Score",                        "de": "Score"},
    "srk.card_fern_label":          {"en": "District Heat",                "de": "Fernwärme"},
    "srk.card_fern_sub":            {"en": "Network risk",                 "de": "Netz-Risiko"},
    "srk.card_hp_label":            {"en": "HP Signal",                    "de": "WP-Signal"},
    "srk.card_hp_sub":              {"en": "Heat pump",                    "de": "Wärmepumpe"},
    "srk.card_priority_sub":        {"en": "ROI×Deploy×Risk",              "de": "ROI×Einsatz×Risiko"},
    "srk.card_deploy_sub":          {"en": "Ready",                        "de": "Einsatzbereit"},
    "srk.card_risk_sub":            {"en": "Risk deduction",               "de": "Risiko-Abzug"},
    "srk.card_sfh_total":           {"en": "SFH total",                    "de": "EFH gesamt"},
    "srk.card_uncert_banner":       {
        "en": "⚠️ **Structural data incomplete**: {pct}% unclassified — field survey recommended.",
        "de": "⚠️ **Strukturdaten unvollständig**: {pct}% nicht klassifiziert — Feldbegehung empfohlen.",
    },
    "srk.card_show_streets":        {"en": "▼ {n} streets  ·  {p} ✅ PASS  ·  {f} ❌ FAIL", "de": "▼ {n} Straßen  ·  {p} ✅ PASS  ·  {f} ❌ FAIL"},
    "srk.card_hide_streets":        {"en": "▲ Hide streets ({n})",         "de": "▲ Straßen ausblenden ({n})"},
    "srk.card_no_streets":          {"en": "No street data available for this segment.", "de": "Keine Straßendaten für dieses Segment verfügbar."},
    "srk.card_conf_osm":            {"en": "OSM-verified",                 "de": "OSM-bestätigt"},
    "srk.card_conf_partial":        {"en": "partly estimated",             "de": "tlw. geschätzt"},
    "srk.card_conf_proxy":          {"en": "Proxy",                        "de": "Proxy"},

    # Street list
    "srk.street_col_rank":          {"en": "**Rank**",                     "de": "**Rang**"},
    "srk.street_col_gate":          {"en": "**Gate**",                     "de": "**Gate**"},
    "srk.street_col_name":          {"en": "**Street / PLZ / Nr.**",       "de": "**Straße / PLZ / Nr.**"},
    "srk.street_col_score":         {"en": "**Score**",                    "de": "**Score**"},
    "srk.street_col_sfh":           {"en": "**SFH%**",                     "de": "**EFH%**"},
    "srk.street_col_efh":           {"en": "**EFH / n**",                  "de": "**EFH / n**"},
    "srk.street_col_note":          {"en": "**Note**",                     "de": "**Hinweis**"},
    "srk.street_score_caption":     {
        "en": "Score = A-signals (building quality ×0.70) + B-signals (roof ×0.20 + PV-oppty ×0.10) "
              "× segment modifiers. Sorted by adjusted score. | Showing {a}–{b} of {n} streets.",
        "de": "Score = A-Signale (Gebäudequalität ×0.70) + B-Signale (Dach ×0.20 + PV-Potenzial ×0.10) "
              "× Segmentmodifikatoren. Sortiert nach Score. | Zeige {a}–{b} von {n} Straßen.",
    },
    "srk.street_small_sample":      {
        "en": "⚠️ **Small sample** — {n} buildings. Score accuracy limited.",
        "de": "⚠️ **Kleine Stichprobe** — {n} Gebäude. Score-Genauigkeit eingeschränkt.",
    },
    "srk.street_page_info":         {"en": "Page {p} / {t}  ·  {n} streets total", "de": "Seite {p} / {t}  ·  {n} Straßen gesamt"},
    "srk.street_prev":              {"en": "← Prev",                       "de": "← Zurück"},
    "srk.street_next":              {"en": "Next →",                       "de": "Weiter →"},
    "srk.osm_confirmed":            {"en": "✅ OSM confirmed",              "de": "✅ OSM bestätigt"},
    "srk.proxy_type":               {"en": "🟡 Type estimated",            "de": "🟡 Typ geschätzt"},

    # Global analysis
    "srk.global_title":             {"en": "🔬 Global Cross-Segment Analysis (advanced)", "de": "🔬 Globale Segmentübergreifende Analyse (Experten)"},
    "srk.global_caption":           {
        "en": "All streets ranked by adjusted score across all segments. "
              "Use for analyst-level cross-region comparison only.",
        "de": "Alle Straßen nach bereinigtem Score segmentübergreifend gerankt. "
              "Nur für Analyst-Vergleiche geeignet.",
    },
    "srk.global_top_n":             {"en": "Show top N streets",           "de": "Top N Straßen anzeigen"},
    "srk.global_gate_filter":       {"en": "Filter by gate",               "de": "Gate-Filter"},
    "srk.global_gate_all":          {"en": "All gates",                    "de": "Alle Gates"},
    "srk.global_load_btn":          {"en": "🔍 Load analysis",             "de": "🔍 Analyse laden"},
    "srk.global_load_hint":         {"en": "Click 'Load analysis' to render the table.", "de": "Klicke 'Analyse laden', um die Tabelle zu rendern."},
    "srk.global_col_rank":          {"en": "**Global #**",                 "de": "**Global #**"},
    "srk.global_col_gate":          {"en": "**Gate**",                     "de": "**Gate**"},
    "srk.global_col_street":        {"en": "**Street**",                   "de": "**Straße**"},
    "srk.global_col_score":         {"en": "**Score**",                    "de": "**Score**"},
    "srk.global_col_sfh":           {"en": "**SFH%**",                     "de": "**EFH%**"},
    "srk.global_col_efh":           {"en": "**EFH/n**",                    "de": "**EFH/n**"},
    "srk.global_col_segment":       {"en": "**Segment**",                  "de": "**Segment**"},
    "srk.global_col_note":          {"en": "**Note**",                     "de": "**Hinweis**"},
    "srk.footer":                   {
        "en": "2 synthetic units excluded by default (SYNTHETIC / row_usable_for_ranking = False).",
        "de": "2 synthetische Einheiten standardmäßig ausgeschlossen (SYNTHETIC / row_usable_for_ranking = False).",
    },

    # Priority action labels
    "srk.priority_now":             {"en": "🔥 Start now — high priority",  "de": "🔥 Jetzt starten — hohe Priorität"},
    "srk.priority_soon":            {"en": "📍 Next slot — schedule soon",  "de": "📍 Bald angehen — nächster freier Slot"},
    "srk.priority_qualify":         {"en": "🔎 Pre-qualify — check data",   "de": "🔎 Vorqualifizieren — Daten prüfen"},
    "srk.priority_wait":            {"en": "📋 Wait — not ready yet",       "de": "📋 Warten — noch nicht kontaktbereit"},

    # ── Customer / Client view ────────────────────────────────────────────────
    "client.srk_title":             {"en": "## 🏘 PV Opportunity — Your Area", "de": "## 🏘 PV-Potenzial — Ihr Wohngebiet"},
    "client.srk_caption":           {"en": "Customer view  ·  Powered by D-ESS Engine", "de": "Kundenansicht  ·  Powered by D-ESS Engine"},
    "client.srk_preview_info":      {
        "en": "**Preliminary view** — Data loaded directly from the core system. "
              "This view will be refined before client presentation.",
        "de": "**Vorläufige Ansicht** — Daten werden direkt aus dem Kernsystem geladen. "
              "Diese Ansicht wird vor der Kundenpräsentation noch verfeinert.",
    },

    # ── Workspace ─────────────────────────────────────────────────────────────
    "ws.back_btn":                  {"en": "← Back to Ranking",            "de": "← Zurück zur Rangfolge"},
    "ws.full_report_for":           {"en": "Full report for:",             "de": "Vollbericht für:"},
    "ws.copilot_expander":          {"en": "🤖 D-ESS Copilot (Guard Assistant)", "de": "🤖 D-ESS Copilot (Projektassistent)"},
    "ws.test_gen_expander":         {"en": "🧪 Test Case Generator",       "de": "🧪 Testfall-Generator"},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_lang() -> str:
    """Return the current active language code ('en' or 'de')."""
    return st.session_state.get("lang", DEFAULT_LANG)


def t(key: str, **kwargs) -> str:
    """
    Look up translation for `key` in the current language.
    Falls back to English, then to the raw key if not found.
    Supports format kwargs: t("srk.card_show_streets", n=5, p=3, f=1)
    """
    lang = get_lang()
    entry = _T.get(key)
    if entry is None:
        return key  # key not registered — return as-is for safety
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass  # partial format — return unformatted rather than crash
    return text


def render_lang_switcher() -> None:
    """
    Render a compact EN / DE toggle in the sidebar (or wherever called).
    Stores selection in st.session_state["lang"].
    Triggers st.rerun() on change so all t() calls refresh immediately.
    """
    if "lang" not in st.session_state:
        st.session_state["lang"] = DEFAULT_LANG

    st.markdown(f"**{t('app.lang_label')}**")
    cols = st.columns(2)
    for i, (code, label) in enumerate(LANGS.items()):
        is_active = st.session_state["lang"] == code
        btn_type  = "primary" if is_active else "secondary"
        if cols[i].button(label, key=f"_lang_{code}", type=btn_type, use_container_width=True):
            if not is_active:
                st.session_state["lang"] = code
                st.rerun()
