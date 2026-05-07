"""
ui/copy_de.py
=============
Central German Copy Registry for TerritoryAI Installer View.

ALL client-visible strings MUST originate here via LABELS["key"] or COPY["key"].
No inline German string literals allowed for whitelisted terms.

Authority: KI territoryai_skills / de_copy_guard.md (2026-04-17)
LABELS: 31 keys (action labels, market labels, data quality labels, canvass tiers)
COPY:    8 keys (caveat & disclaimer strings — mandatory, do NOT paraphrase)
"""

# ---------------------------------------------------------------------------
# LABELS — Action Labels, Terminology Whitelist, UI Chips
# ---------------------------------------------------------------------------
LABELS: dict[str, str] = {
    # ── Aktions-Priorität (priority_score thresholds) ──────────────────────
    "prio_sofort":         "🔥 Sofort ansprechen",
    "prio_bald":           "📍 Bald einplanen",
    "prio_qualifizieren":  "🔎 Erst vorqualifizieren",
    "prio_zurueck":        "📋 Zurückstellen",

    # ── Marktpotenzial (pv_coverage_score → adoption conversion) ───────────
    "markt_offen":         "🟢 Hohes Restpotenzial",
    "markt_mittel":        "🟡 Teilweise erschlossen",
    "markt_gesaettigt":    "🔴 Bereits stark besetzt",

    # ── Dachertrag (roof_suitability_score_norm) ───────────────────────────
    "dach_premium":        "☀️ Hervorragende Dachausrichtung",
    "dach_standard":       "☀️ Gute Dachlage",
    "dach_eingeschraenkt": "☀️ Solarpotenzial vorhanden",
    "dach_heterogen":      "☀️ Dachsituation heterogen",

    # ── PV+WP-Potenzial (hp_status) ────────────────────────────────────────
    "wp_hoch":             "🔋 PV+WP-Potenzial: Hoch",
    "wp_mittel":           "🔋 PV+WP-Potenzial: Mittel",
    "wp_gering":           "🔋 PV+WP-Potenzial: Gering",

    # ── Wärmeinfrastruktur (heat_status) ───────────────────────────────────
    "heat_kein_risiko":    "✅ Kein bekanntes Fernwärmenetz",
    "heat_unklar":         "⚠️ Fernwärme-Situation unklar",
    "heat_risiko":         "🚫 Fernwärme-Risiko hoch",

    # ── Datenkonfidenz (structural_certainty) ──────────────────────────────
    "dq_verifiziert":      "✅ Verifiziert",
    "dq_plausibel":        "🟡 Plausibel",
    "dq_vorsicht":         "⚠️ Vorsicht",

    # ── Canvass-Tier ───────────────────────────────────────────────────────
    "tier_primary":        "🟢 Sofort aktiv — kein Fernwärme-Risiko",
    "tier_secondary":      "🟡 Vor Besuch bestätigen — Fernwärme-Situation klären",
    "tier_not_rec":        "🔴 Nicht empfohlen — hohes Fernwärme-Risiko",

    # ── Gebäudetypen ───────────────────────────────────────────────────────
    "typ_efh":             "Freistehend",
    "typ_dhh":             "Doppelhaus",
    "typ_rh":              "Reihenhaus",

    # ── ROI / PDF Labels ───────────────────────────────────────────────────
    "roi_invest_label":    "Invest (MwSt. 0%)",
    "roi_autarkie":        "Autarkiegrad",
    "roi_amortisation":    "Amortisationszeit",
    "roi_vorteil_y1":      "Netto-Energievorteil (Jahr 1)",
    "roi_gewinn_20y":      "Gesamtertrag über 20 Jahre",
    "roi_cashflow":        "Monatl. Cashflow",
    "roi_fehler":          "ROI-Fehler",
    "roi_nicht_verfuegbar": "ROI-Profil (nicht verfügbar)",
}


# ---------------------------------------------------------------------------
# COPY — Mandatory Disclaimer & Caveat Strings
# These MUST be rendered as-is. Never paraphrase or shorten.
# Authority: de_copy_guard.md Rule 4 (COPY keys locked 2026-04-17)
# ---------------------------------------------------------------------------
COPY: dict[str, str] = {
    # Segment-level Empfehlung — ALWAYS show (even when high confidence)
    "caveat_segment_level":
        "Gilt als Gebietssignal — keine gebäudegenaue Einzelbewertung.",

    # structural_certainty < 0.50
    "dq_caution_note":
        "Überwiegend Proxy-Daten — Empfehlung mit Vorsicht nutzen.",

    # Building types estimated via proxy
    "caveat_proxy_data":
        "Gebäudetypen tlw. geschätzt — Ortsbegehung vor Erstgespräch empfohlen.",

    # Low sample flag
    "caveat_low_sample":
        "Kleine Datenbasis — Einschätzung vorläufig, Streubreite erhöht.",

    # Heating infrastructure unclear
    "caveat_heat_uncertain":
        "Heizinfrastruktur nicht vollständig erfasst — vor Pitch klären.",

    # ROI output — ALWAYS show
    "roi_assumptions":
        (
            "Annahmen: Strompreis 38 ct/kWh · Einspeisevergütung 7,78 ct/kWh · "
            "Finanzierung 4,5 % APR / 10 Jahre · MwSt. 0 % (EEG) · "
            "Degradation 0,5 %/J. — Orientierungswert, individuelle Abweichungen möglich."
        ),

    # UWG §5 compliant footnote for HIGH_LOAD headine (AGGRESSIVE template)
    "uwg_footnote_high_load":
        (
            "* Maximalwert bei hohem Stromverbrauch, z. B. vorhandener Wärmepumpe "
            "(ca. 8.000 kWh/Jahr). Ohne Wärmepumpe: Ersparnis geringer."
        ),

    # Conservative template footnote (CONSERVATIVE template — no WP headline)
    "uwg_footnote_household":
        "* Orientierungswert basierend auf typischem Haushaltsverbrauch (ca. 3.500 kWh/Jahr).",
}
