"""
street_ranking_view.py
PV-Only Street Ranking — Region-First Drill-Down (v2)
======================================================
Architecture: Region Cards (collapsed) → Street List → ROI Expander

Data sources:
  - data/layer2/street_ranking_v1.parquet      (segment-level, field_07)
  - data/layer2/street_level_ranking_v1.parquet (street-level, field_08)

GUARDRAILS (UI layer):
- No household-level claims
- No engineering-level ROI certainty
- HP flag = commercial narrative only
- Fernwärme = caution label, not hard exclusion
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from ui.components.street_roi_generator import render_street_roi_expander

ROOT           = Path(__file__).resolve().parents[2]
PARQUET        = ROOT / "data" / "layer2" / "street_ranking_v1.parquet"
STREET_PARQUET = ROOT / "data" / "layer2" / "street_level_ranking_v1.parquet"

# ---------------------------------------------------------------------------
# Cached data loaders  (TTL=0 → cache lives for the lifetime of the session;
# clear with st.cache_data.clear() or app restart after data pipeline re-run)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=None)
def _load_segment_df() -> pd.DataFrame:
    """Load segment-level ranking (field_07 output). Cached for session."""
    return pd.read_parquet(PARQUET)


@st.cache_data(show_spinner=False, ttl=None)
def _load_street_df() -> pd.DataFrame:
    """Load street-level ranking (field_08 output). Cached for session."""
    return pd.read_parquet(STREET_PARQUET)


@st.cache_data(show_spinner=False, ttl=None)
def _load_merged_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load and merge segment + street data into final render-ready dataframes.
    Cached so the merge (514 rows × 30 cols) only runs once per session.
    Returns (segment_df, street_df_with_meta).
    """
    seg_df    = _load_segment_df()
    street_df = _load_street_df()
    # Pre-merge segment signals (heat_status, hp_status) into street rows
    seg_meta  = seg_df[["street_id", "heat_status", "hp_status"]].rename(
        columns={"street_id": "segment_id"}
    )
    merged = street_df.merge(seg_meta, on="segment_id", how="left")
    return seg_df, merged

# ---------------------------------------------------------------------------
# Badge / label helpers
# ---------------------------------------------------------------------------
FERNWAERME_BADGE = {
    "NO_SIGNAL":              ("✅", "No constraint",          "#2d6a4f"),
    "LIMITED_OR_UNCLEAR":     ("⚠️", "Caution ×0.90",         "#c0550a"),
    "PLANNED_DISTRICT_HEAT":  ("🟠", "Planned net ×0.60",     "#9c5000"),
    "STRONG_DISTRICT_HEAT":   ("🚫", "Strong net ×0.10",      "#8b0000"),
    "UNKNOWN":                ("—",  "Unknown",                "#666666"),
    # legacy compat
    "LOW_NETWORK_SIGNAL":     ("⚠️", "Low risk",              "#b5851b"),
    "NETWORK_LIKELY":         ("🚫", "High risk",              "#8b0000"),
    "UNCLEAR":                ("—",  "Unknown",                "#666666"),
}

HP_BADGE = {
    "STRONG_HP_UPLIFT":   ("🔥", "Strong HP fit"),
    "MODERATE_HP_UPLIFT": ("♨️", "Moderate HP fit"),
    "LIMITED_HP_UPLIFT":  ("—",  "Limited HP evidence"),
    "UNKNOWN":            ("—",  "No HP data"),
}

GATE_COLOR = {
    "PASS":      ("🟢", "#1e6b3c"),
    "QUALIFIED": ("🔵", "#1a457a"),
    "REVIEW":    ("🟡", "#8b6914"),
    "FAIL":      ("🔴", "#8b0000"),
}

TEMPLATE_COLOR = {
    "PV_HP_ENHANCED":      "#1a6b3c",
    "PV_PLUS_HP_OPTIONAL": "#1a4a6b",
    "PV_STANDARD":         "#444444",
}

RANK_ICON = {1: "🔥", 2: "📍", 3: "📋"}

# ---------------------------------------------------------------------------
# Plain-language translations for technical labels
# ---------------------------------------------------------------------------
_FERN_PLAIN = {
    "NO_SIGNAL":             ("✅", "Kein Fernwärme-Netz",        "Freie Technologiewahl — PV+WP ohne Einschränkung"),
    "LIMITED_OR_UNCLEAR":    ("⚠️", "Fernwärme möglicherweise",  "Situation vor Ort klären — Risiko vorhanden"),
    "PLANNED_DISTRICT_HEAT": ("🟠", "Fernwärme geplant",         "Netzausbau geplant — vor Pitch unbedingt klären"),
    "STRONG_DISTRICT_HEAT":  ("🚫", "Fernwärme vorhanden",       "Starkes Netz — PV-Only empfohlen, kein WP-Vorteil"),
    "UNKNOWN":               ("—",  "Heizung unbekannt",         "Keine verlässlichen Daten — Feldcheck nötig"),
    "LOW_NETWORK_SIGNAL":    ("⚠️", "Schwaches Netz-Signal",     "Geringes Risiko, aber zur Sicherheit klären"),
    "NETWORK_LIKELY":        ("🚫", "Fernwärme wahrscheinlich",  "Hohe Wahrscheinlichkeit — PV-Only empfohlen"),
    "UNCLEAR":               ("—",  "Heizung unklar",            "Keine verlässlichen Daten — Feldcheck nötig"),
}

_HP_PLAIN = {
    "STRONG_HP_UPLIFT":   ("🔥", "Starkes WP+PV-Potenzial",    "Viele Haushalte ideal für PV+Wärmepumpe-Kombination"),
    "MODERATE_HP_UPLIFT": ("♨️", "WP+PV-Kombination möglich",  "Gute Ergänzung — PV + Wärmepumpe als Paket anbietbar"),
    "LIMITED_HP_UPLIFT":  ("☀️", "PV-Only empfohlen",           "Wärmepumpen-Vorteil begrenzt — auf PV fokussieren"),
    "UNKNOWN":            ("—",  "Keine WP-Daten",              "Heizungstyp unbekannt — im Erstgespräch erfragen"),
}

_REASON_DE = {
    "Above-average roof suitability in this area":             "Überdurchschnittliche Dachqualität",
    "Detached / rowhouse homes — installation-friendly":       "Viele Einzel-/Reihenhäuser — einfache Montage",
    "Good SFH share — solid PV opportunity base":              "Hoher Einfamilienhausanteil — solide PV-Basis",
    "Solid data foundation — partial Stage-1 confirmation":    "Gute Datenbasis — teilweise durch OSM bestätigt",
    "SFH-dominated area — strong installation base":           "EFH-dominiertes Gebiet — starke Installationsbasis",
    "High EFH density — strong canvassing target":             "Hohe EFH-Dichte — ideales Canvassing-Ziel",
}

_CAUTION_DE = {
    "SFH classification via proxy — recommend field confirmation":
        "Gebäudetypen per Schätzung — Feldbegehung vor Erstgespräch empfohlen",
    "District-heating planning risk — qualify before pitch":
        "Fernwärme-Planungsrisiko — Heizungssituation vor dem Pitch klären",
    "Low confidence — validate heating data before pitch":
        "Geringe Datensicherheit — Heizungstyp im Erstgespräch erfragen",
}


def _fern_badge(status: str) -> str:
    """Used in street-level rows (compact icon+label only)."""
    icon, label, _ = FERNWAERME_BADGE.get(status, ("—", status, "#666666"))
    return f"{icon} {label}"


def _hp_badge(status: str) -> str:
    icon, label = HP_BADGE.get(status, ("—", ""))
    return f"{icon} {label}"


def _fern_plain(status: str) -> tuple[str, str, str]:
    """Returns (icon, short_label, description) for Region Card display."""
    return _FERN_PLAIN.get(status, ("—", "Unbekannt", "Keine Daten verfügbar"))


def _hp_plain(status: str) -> tuple[str, str, str]:
    """Returns (icon, short_label, description) for Region Card display."""
    return _HP_PLAIN.get(status, ("—", "Keine Daten", "Heizungstyp unbekannt"))


def _readiness_plain(deploy: float, risk: float) -> tuple[str, str]:
    """Returns (icon+label, detail_in_parentheses) for deploy+risk combined."""
    if deploy >= 0.80 and risk <= 0.05:
        label = "🟢 Sofort einsatzbereit"
    elif deploy >= 0.60 and risk <= 0.12:
        label = "🟡 Gut vorbereitet"
    elif deploy >= 0.40:
        label = "🟠 Mit Vorbereitung machbar"
    else:
        label = "🔴 Datenvalidierung nötig"
    detail = f"Einsatz: {deploy:.0%} · Risiko: −{risk:.0%}"
    return label, detail


def _translate_reason(en: str) -> str:
    return _REASON_DE.get(en.strip(), en)


def _translate_caution(en: str) -> str:
    return _CAUTION_DE.get(en.strip(), en)


def _priority_action(priority_score: float) -> str:
    if priority_score >= 0.70:
        return "🔥 Jetzt starten — hohe Priorität"
    elif priority_score >= 0.50:
        return "📍 Bald angehen — nächster freier Slot"
    elif priority_score >= 0.30:
        return "🔎 Vorqualifizieren — Daten prüfen"
    return "📋 Warten — noch nicht kontaktbereit"


def _score_color(score: float, high: float = 0.75, mid: float = 0.50) -> str:
    if score >= high:
        return "#1e6b3c"
    if score >= mid:
        return "#8b6914"
    return "#8b0000"


# ---------------------------------------------------------------------------
# Street list renderer (shared between Region Cards and Global Analysis)
# ---------------------------------------------------------------------------
def _render_street_list(seg_streets: pd.DataFrame) -> None:
    """
    Render a sorted street list for one segment.
    seg_streets must already have heat_status / hp_status merged in.
    Sorted by adjusted_street_score DESC.
    """
    seg_streets = seg_streets.sort_values("adjusted_street_score", ascending=False)

    st.caption(
        "Score = A-signals (building quality ×0.70) + B-signals (roof ×0.20 + PV-oppty ×0.10) "
        "× segment modifiers (Fernwärme × HP × certainty). "
        "Sorted by adjusted score — highest building quality first."
    )

    # Column headers
    H = st.columns([2, 1, 8, 2, 2, 2, 4])
    H[0].markdown("**Rank**")
    H[1].markdown("**Gate**")
    H[2].markdown("**Straße / PLZ / Nr.**")
    H[3].markdown("**Score**")
    H[4].markdown("**SFH%**")
    H[5].markdown("**EFH / n**")
    H[6].markdown("**Hinweis**")
    st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

    for rank_i, (_, s) in enumerate(seg_streets.iterrows(), start=1):
        gate_str  = str(s.get("structure_gate", "?"))
        gate_icon = GATE_COLOR.get(gate_str, ("⚪", "#666"))[0]

        score_v   = float(s.get("adjusted_street_score", s["street_score"]))
        score_col = _score_color(score_v, high=0.75, mid=0.50)

        fern_icon = FERNWAERME_BADGE.get(
            str(s.get("heat_status", "UNCLEAR")), ("—", "—", "#666")
        )[0]

        # PLZ + address sub-line
        plz_str  = str(s.get("plz", ""))
        addr_str = str(s.get("address_range", "")).strip()
        addr_sub = (
            f"<small style='opacity:0.65;font-size:0.72em'>"
            f"PLZ {plz_str}" + (f" &nbsp;·&nbsp; Nr. {addr_str}" if addr_str else "") +
            "</small>"
        )

        # Data-quality label
        dq_note  = str(s.get("data_quality_note", ""))
        dq_label = (
            "✅ OSM bestätigt"     if "Stage-1" in dq_note
            else "🟡 Typ geschätzt" if "Stage-2" in dq_note
            else ""
        )
        dq_color = (
            "#2ecc71" if "Stage-1" in dq_note
            else "#f39c12" if "Stage-2" in dq_note
            else "inherit"
        )
        dq_html = (
            f"<br><span style='color:{dq_color};font-size:0.68em'>{dq_label}</span>"
            if dq_label else ""
        )

        low_sample = bool(s.get("low_sample_flag", False))
        n_total    = int(s.get("building_count_total", 0))
        efh_pct    = float(s["sfh_detached_ratio"])

        C = st.columns([2, 1, 8, 2, 2, 2, 4])
        C[0].markdown(f"**#{rank_i}**")
        C[1].markdown(gate_icon)
        C[2].markdown(
            f"{s['street_name']}<br>{addr_sub}",
            unsafe_allow_html=True,
        )
        C[3].markdown(
            f"<span style='color:{score_col};font-weight:600'>{score_v:.3f}</span>",
            unsafe_allow_html=True,
        )
        C[4].markdown(f"{float(s['sfh_total_ratio']):.0%}")
        C[5].markdown(f"{efh_pct:.0%} /{n_total}")
        C[6].markdown(
            f"<small>{s['top_reason']}</small>  {fern_icon}{dq_html}",
            unsafe_allow_html=True,
        )

        # Small-sample warning row (dedicated, more visible)
        if low_sample:
            st.markdown(
                f"<div style='margin:-6px 0 4px 0;padding:3px 8px;"
                f"background:rgba(230,160,32,0.12);border-left:3px solid #e0a020;"
                f"border-radius:0 4px 4px 0;font-size:0.73em;'>"
                f"⚠️ <strong>Kleine Stichprobe</strong> — {n_total} Gebäude. "
                f"Score-Genauigkeit eingeschränkt."
                f"</div>",
                unsafe_allow_html=True,
            )

        # ROI Expander (reused, no changes needed)
        render_street_roi_expander(s)


# ---------------------------------------------------------------------------
# Region Card renderer
# ---------------------------------------------------------------------------
def _render_region_card(seg_row: pd.Series, street_df: pd.DataFrame) -> None:
    """Render one segment card (collapsed) with its drill-down street list."""
    rank      = int(seg_row["rank"])
    name      = seg_row["street_name"]
    base      = float(seg_row["base_score"])
    final     = float(seg_row["final_score"])
    conf      = float(seg_row["confidence"])
    fern      = _fern_badge(seg_row.get("heat_status", "UNCLEAR"))
    hp        = _hp_badge(seg_row.get("hp_status", "UNKNOWN"))
    priority  = float(seg_row.get("priority_score", -1.0))
    deploy    = float(seg_row.get("deployment_score", -1.0))
    risk      = float(seg_row.get("risk_penalty", 0.0))
    tmpl      = seg_row.get("roi_report_template_flag", "PV_STANDARD")
    tmpl_color = TEMPLATE_COLOR.get(tmpl, "#444")
    rank_icon  = RANK_ICON.get(rank, "📋")
    unit_id    = str(seg_row.get("street_id", ""))

    # Truly uncertain share for structural warning
    truly_unc    = float(seg_row.get("truly_uncertain_share", 0.0))
    sfh_confirmed_sh = float(seg_row.get("sfh_confirmed_share", 0.0))
    caution      = seg_row.get("primary_caution", "")

    # Segment street stats
    seg_streets_all = street_df[street_df["segment_id"] == unit_id]
    n_total_streets = len(seg_streets_all)
    n_pass    = (seg_streets_all["structure_gate"] == "PASS").sum()
    n_fail    = (seg_streets_all["structure_gate"] == "FAIL").sum()
    n_canvass = int(
        ((seg_streets_all["structure_gate"] == "PASS") &
         (~seg_streets_all["low_sample_flag"].fillna(False))).sum()
    )

    # ── Aggregate actual building counts from street-level data ─────────────
    total_efh = int(seg_streets_all["sfh_detached_count"].sum())
    total_rh  = int(seg_streets_all["sfh_rowhouse_count"].sum())
    total_dhh = int(seg_streets_all["sfh_semi_count"].sum())
    total_sfh = int(seg_streets_all["sfh_total_count"].sum())
    total_bld = int(seg_streets_all["building_count_total"].sum())
    sfh_pct   = total_sfh / total_bld if total_bld > 0 else 0.0

    # Roof yield estimate (same formula as street_roi_generator)
    roof_norm = float(seg_row.get("roof_suitability_score_norm", 0.5) or 0.5)
    yield_kwh = int(900 + 200 * max(0.0, min(1.0, roof_norm)))
    roof_label = (
        "🟢 Sehr gut" if roof_norm >= 0.80
        else "🟢 Gut"    if roof_norm >= 0.55
        else "🟡 Mittel" if roof_norm >= 0.30
        else "🔴 Gering"
    )

    # PV market saturation / potential signal
    pv_score = float(seg_row.get("pv_coverage_score", 0.0) or 0.0)
    pv_market_label = (
        "🟢 Hohe PV-Nachfrage"   if pv_score >= 0.60
        else "🟡 Mittlere Nachfrage" if pv_score >= 0.35
        else "🔴 Niedrige Nachfrage"
    )

    # WP pitch potential from heat_status
    heat_status = str(seg_row.get("heat_status", "UNKNOWN"))
    hp_status   = str(seg_row.get("hp_status", "UNKNOWN"))
    _WP_CARD = {
        "NO_SIGNAL":             ("✅", "WP+PV-Paket pitchbar",        "Kein Netz — Wärmepumpe ideal kombinierbar"),
        "LIMITED_OR_UNCLEAR":    ("⚠️", "WP erst abklären",           "Fernwärme mögl. — vor WP-Pitch prüfen"),
        "PLANNED_DISTRICT_HEAT": ("🟠", "WP kritisch — PV-Focus",     "Netzausbau geplant — WP zurückstellen"),
        "STRONG_DISTRICT_HEAT":  ("🚫", "PV-Only",                    "Fernwärme vorhanden — kein WP-Paket"),
        "UNKNOWN":               ("—",  "Heizung klären",              "Situation vor Ort erfragen"),
        "LOW_NETWORK_SIGNAL":    ("⚠️", "WP möglich, klären",         "Schwaches Signal — kurze Abklärung"),
        "NETWORK_LIKELY":        ("🚫", "PV-Only",                    "Netz wahrscheinlich — kein WP"),
        "UNCLEAR":               ("—",  "Heizung klären",              "Situation vor Ort erfragen"),
    }
    wp_icon, wp_label, wp_desc = _WP_CARD.get(heat_status, ("—", "Unbekannt", "Keine Daten"))

    with st.container(border=True):
        # ── Card Header ──────────────────────────────────────────────────────
        h1, h2, h3 = st.columns([1, 6, 3])

        with h1:
            st.markdown(f"### {rank_icon} #{rank}")

        with h2:
            st.markdown(f"**{name}**")
            st.caption(
                f"{n_total_streets} Straßen &nbsp;·&nbsp; "
                f"{n_canvass} 🟢 sofort ansprechbar &nbsp;·&nbsp; "
                f"Score: {final:.3f}"
            )

        with h3:
            st.markdown(
                f"<span style='color:{tmpl_color};font-size:0.8em'>⬡ {tmpl}</span>",
                unsafe_allow_html=True,
            )
            if priority >= 0:
                st.caption(_priority_action(priority))

        # ── Signal row — raw data, 6 columns ──────────────────────────────────────
        fern  = _fern_badge(heat_status)
        hp    = _hp_badge(hp_status)

        s1, s2, s3, s4, s5, s6 = st.columns(6)
        s1.markdown(
            f"**Fernwärme**  \n{fern}  \n"
            f"<small style='opacity:0.60'>Netz-Risiko</small>",
            unsafe_allow_html=True,
        )
        s2.markdown(
            f"**HP Signal**  \n{hp}  \n"
            f"<small style='opacity:0.60'>Wärmepumpe</small>",
            unsafe_allow_html=True,
        )
        if priority >= 0:
            s3.markdown(
                f"**Priority**  \n"
                f"<span style='color:#6c5ce7;font-weight:600'>{priority:.3f}</span>  \n"
                f"<small style='opacity:0.60'>ROI×Deploy×Risk</small>",
                unsafe_allow_html=True,
            )
            s4.markdown(
                f"**Deploy**  \n{deploy:.2f}  \n"
                f"<small style='opacity:0.60'>Einsatzbereit</small>"
            )
            s5.markdown(
                f"**Risk Penalty**  \n−{risk:.0%}  \n"
                f"<small style='opacity:0.60'>Risiko-Abzug</small>"
            )
        else:
            s3.markdown(f"**Gate**  \n{seg_row.get('l1_gate_label', '—')}")
            s4.markdown(f"**Deploy**  \n—")
            s5.markdown(f"**Risk**  \n—")

        # Building count line (raw numbers)
        parts = []
        if total_efh > 0: parts.append(f"EFH {total_efh}")
        if total_rh  > 0: parts.append(f"RH {total_rh}")
        if total_dhh > 0: parts.append(f"DHH {total_dhh}")
        bld_detail = " · ".join(parts)
        conf_tag = (
            "OSM-bestätigt" if sfh_confirmed_sh >= 0.70
            else "tlw. geschätzt" if sfh_confirmed_sh >= 0.30
            else "Proxy"
        )
        s6.markdown(
            f"**SFH gesamt**  \n{total_sfh} ({sfh_pct:.0%})  \n"
            f"<small style='opacity:0.60'>{bld_detail} · {conf_tag}</small>",
            unsafe_allow_html=True,
        )

        # Structural uncertainty banner
        if truly_unc > 0.40:
            st.warning(
                f"⚠️ **Strukturdaten unvollständig**: {truly_unc:.0%} nicht klassifiziert — "
                f"Feldbegehung empfohlen.",
                icon="🏗",
            )

        # ── Reasons + caution (original format, raw) ───────────────────────────
        r1 = seg_row.get("top_reason_1", "")
        r2 = seg_row.get("top_reason_2", "")
        if r1 or r2:
            reason_text = ""
            if r1: reason_text += f"↗ {r1}"
            if r2: reason_text += f"  ·  ↗ {r2}"
            st.markdown(f"<small>{reason_text}</small>", unsafe_allow_html=True)

        if caution:
            st.markdown(
                f"<small style='color:#e67e22'>⚠️ {caution}</small>",
                unsafe_allow_html=True,
            )

        # ── Street Drill-Down (collapsed) ─────────────────────────────────
        if n_total_streets > 0:
            with st.expander(
                f"🗺 {n_total_streets} Straßen anzeigen "
                f"· {n_pass} ✅ PASS · {n_fail} ❌ FAIL",
                expanded=False,
            ):
                _render_street_list(seg_streets_all)
        else:
            st.caption("No street data available for this segment.")


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------
def render_street_ranking_view() -> None:
    st.markdown("## 🏘 PV Opportunity Street Ranking")
    st.caption(
        "Region cards ranked by segment opportunity score (ROI × deployment × risk). "
        "Click a region to view its streets ranked by building quality. "
        "No household-level claims implied."
    )

    # --- Load data (cached) ---
    if not PARQUET.exists():
        st.warning(
            "⚠️ Segment ranking data not found. "
            "Run `python fields/field_07_street_ranking.py` first."
        )
        return

    if not STREET_PARQUET.exists():
        st.warning(
            "⚠️ Street-level data not found. "
            "Run `python fields/field_08_street_level_ranking.py` first."
        )
        return

    df, street_df = _load_merged_data()
    if df.empty:
        st.info("No segment data available.")
        return

    # --- Summary metrics ---
    total_streets = len(street_df)
    top_score     = float(street_df["adjusted_street_score"].max())
    ready_count   = int(
        (
            (street_df["structure_gate"] == "PASS") &
            (~street_df["low_sample_flag"].fillna(False))
        ).sum()
    )
    n_segments = len(df)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Regionen", n_segments)
    col2.metric("Straßen gesamt", total_streets)
    col3.metric("Top Score", f"{top_score:.3f}")
    col4.metric(
        "🟢 Canvass-bereit",
        ready_count,
        help=(
            "Straßen mit Gate=PASS und ausreichend Gebäudedaten (kein n-small-sample). "
            "Sofort ansprechbar."
        ),
    )

    st.markdown("---")

    # ── Region Cards (all collapsed by default) ──────────────────────────────
    for _, seg_row in df.sort_values("rank").iterrows():
        _render_region_card(seg_row, street_df)

    st.markdown("---")

    # ── Global Cross-Segment Analysis (collapsed, for analysts) ──────────────
    with st.expander("🔬 Global Cross-Segment Analysis (advanced)", expanded=False):
        st.caption(
            "All streets ranked by adjusted_street_score across all segments. "
            "Use this for analyst-level cross-region comparison only. "
            "For canvassing route planning, use the region cards above."
        )

        top_n = st.slider(
            "Show top N streets",
            min_value=10,
            max_value=len(street_df),
            value=30,
            step=10,
            key="global_analysis_n",
        )
        gate_opts = ["All gates", "PASS", "QUALIFIED", "REVIEW", "FAIL"]
        sel_gate  = st.selectbox("Filter by gate", gate_opts, key="global_analysis_gate")

        global_view = street_df.copy()
        if sel_gate != "All gates":
            global_view = global_view[global_view["structure_gate"] == sel_gate]
        global_view = global_view.sort_values("global_rank").head(top_n)

        # Column headers
        G = st.columns([2, 1, 6, 2, 2, 2, 3, 3])
        G[0].markdown("**Global #**")
        G[1].markdown("**Gate**")
        G[2].markdown("**Straße**")
        G[3].markdown("**Score**")
        G[4].markdown("**SFH%**")
        G[5].markdown("**EFH/n**")
        G[6].markdown("**Segment**")
        G[7].markdown("**Hinweis**")
        st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

        for _, s in global_view.iterrows():
            gate_str  = str(s.get("structure_gate", "?"))
            gate_icon = GATE_COLOR.get(gate_str, ("⚪", "#666"))[0]
            score_v   = float(s.get("adjusted_street_score", s["street_score"]))
            score_col = _score_color(score_v)
            fern_icon = FERNWAERME_BADGE.get(
                str(s.get("heat_status", "UNCLEAR")), ("—", "—", "#666")
            )[0]
            plz_str   = str(s.get("plz", ""))
            addr_str  = str(s.get("address_range", "")).strip()
            addr_sub  = (
                f"<small style='opacity:0.65;font-size:0.72em'>"
                f"PLZ {plz_str}" + (f" &nbsp;·&nbsp; Nr. {addr_str}" if addr_str else "") +
                "</small>"
            )
            n_total   = int(s.get("building_count_total", 0))
            efh_pct   = float(s["sfh_detached_ratio"])
            seg_short = s["segment_id"].replace("NEUSS_", "").replace("_01", "")
            seg_r     = int(s.get("segment_rank", 99))
            dq_note   = str(s.get("data_quality_note", ""))
            dq_label  = (
                "✅ OSM"         if "Stage-1" in dq_note
                else "🟡 Proxy" if "Stage-2" in dq_note
                else ""
            )
            dq_color  = (
                "#2ecc71" if "Stage-1" in dq_note
                else "#f39c12" if "Stage-2" in dq_note
                else "inherit"
            )
            dq_html   = (
                f"<br><span style='color:{dq_color};font-size:0.68em'>{dq_label}</span>"
                if dq_label else ""
            )
            low_sample = bool(s.get("low_sample_flag", False))

            G2 = st.columns([2, 1, 6, 2, 2, 2, 3, 3])
            G2[0].markdown(f"**#{int(s['global_rank'])}**")
            G2[1].markdown(gate_icon)
            G2[2].markdown(f"{s['street_name']}<br>{addr_sub}", unsafe_allow_html=True)
            G2[3].markdown(
                f"<span style='color:{score_col};font-weight:600'>{score_v:.3f}</span>",
                unsafe_allow_html=True,
            )
            G2[4].markdown(f"{float(s['sfh_total_ratio']):.0%}")
            G2[5].markdown(f"{efh_pct:.0%} /{n_total}")
            G2[6].markdown(
                f"<small><b>#{seg_r}</b> {seg_short}</small>",
                unsafe_allow_html=True,
            )
            G2[7].markdown(
                f"<small>{s['top_reason']}</small>  {fern_icon}{dq_html}",
                unsafe_allow_html=True,
            )

            if low_sample:
                st.markdown(
                    f"<div style='margin:-6px 0 4px 0;padding:3px 8px;"
                    f"background:rgba(230,160,32,0.12);border-left:3px solid #e0a020;"
                    f"border-radius:0 4px 4px 0;font-size:0.73em;'>"
                    f"⚠️ <strong>Kleine Stichprobe</strong> — {n_total} Gebäude.</div>",
                    unsafe_allow_html=True,
                )

    st.caption(
        "2 synthetic units excluded by default (SYNTHETIC / row_usable_for_ranking = False)."
    )
