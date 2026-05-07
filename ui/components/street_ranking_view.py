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
from ui.i18n import t
from ui.components.street_roi_generator import render_street_roi_expander

ROOT           = Path(__file__).resolve().parents[2]
PARQUET        = ROOT / "data" / "layer2" / "street_ranking_v1.parquet"
STREET_PARQUET = ROOT / "data" / "layer2" / "street_level_ranking_v1.parquet"

# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=120)
def _load_segment_df() -> pd.DataFrame:
    """Load segment-level ranking (field_07 output). Cached for session."""
    return pd.read_parquet(PARQUET)


@st.cache_data(show_spinner=False, ttl=120)
def _load_street_df() -> pd.DataFrame:
    """Load street-level ranking (field_08 output). Cached for session."""
    return pd.read_parquet(STREET_PARQUET)


@st.cache_data(show_spinner=False, ttl=120)
def _load_merged_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load and merge segment + street data into final render-ready dataframes.
    Cached so the merge only runs once per session.
    Returns (segment_df, street_df_with_meta).
    """
    seg_df    = _load_segment_df()
    street_df = _load_street_df()
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
# Plain-language translations for technical labels (kept as static dicts so
# they don't require t() lookup — they were originally German-only, now the
# short label is derived from i18n keys and the full dict is for badge lookup)
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
    from ui.i18n import get_lang
    if get_lang() == "de":
        return _REASON_DE.get(en.strip(), en)
    return en


def _translate_caution(en: str) -> str:
    from ui.i18n import get_lang
    if get_lang() == "de":
        return _CAUTION_DE.get(en.strip(), en)
    return en


def _priority_action(priority_score: float) -> str:
    if priority_score >= 0.70:
        return t("srk.priority_now")
    elif priority_score >= 0.50:
        return t("srk.priority_soon")
    elif priority_score >= 0.30:
        return t("srk.priority_qualify")
    return t("srk.priority_wait")


def _score_color(score: float, high: float = 0.75, mid: float = 0.50) -> str:
    if score >= high:
        return "#1e6b3c"
    if score >= mid:
        return "#8b6914"
    return "#8b0000"


# Streets rendered per page in a drill-down (keeps DOM small)
_PAGE_SIZE = 25


# ---------------------------------------------------------------------------
# Street list renderer (shared between Region Cards and Global Analysis)
# ---------------------------------------------------------------------------
def _render_street_list(
    seg_streets: pd.DataFrame,
    page: int = 0,
    page_size: int = _PAGE_SIZE,
) -> None:
    """
    Render a paginated street list for one segment.
    Only rows on the current page are rendered — critical for performance.
    seg_streets must already have heat_status / hp_status merged in.
    Sorted by adjusted_street_score DESC.
    """
    seg_streets = seg_streets.sort_values("adjusted_street_score", ascending=False)
    total       = len(seg_streets)
    start       = page * page_size
    end         = min(start + page_size, total)
    seg_page    = seg_streets.iloc[start:end]

    st.caption(t("srk.street_score_caption", a=start+1, b=end, n=total))

    # Column headers
    H = st.columns([2, 1, 8, 2, 2, 2, 4])
    H[0].markdown(t("srk.street_col_rank"))
    H[1].markdown(t("srk.street_col_gate"))
    H[2].markdown(t("srk.street_col_name"))
    H[3].markdown(t("srk.street_col_score"))
    H[4].markdown(t("srk.street_col_sfh"))
    H[5].markdown(t("srk.street_col_efh"))
    H[6].markdown(t("srk.street_col_note"))
    st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

    for rank_i, (_, s) in enumerate(seg_page.iterrows(), start=start + 1):
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
            t("srk.osm_confirmed") if "Stage-1" in dq_note
            else t("srk.proxy_type") if "Stage-2" in dq_note
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
                + t("srk.street_small_sample", n=n_total) +
                f"</div>",
                unsafe_allow_html=True,
            )

        # ROI Expander
        render_street_roi_expander(s)


# ---------------------------------------------------------------------------
# Region Card renderer
# ---------------------------------------------------------------------------
def _render_region_card(seg_row: pd.Series, street_df: pd.DataFrame) -> None:
    """Render one segment card (collapsed) with its drill-down street list."""
    rank      = int(seg_row["rank"])
    name      = seg_row["street_name"]
    final     = float(seg_row["final_score"])
    priority  = float(seg_row.get("priority_score", -1.0))
    deploy    = float(seg_row.get("deployment_score", -1.0))
    risk      = float(seg_row.get("risk_penalty", 0.0))
    tmpl      = seg_row.get("roi_report_template_flag", "PV_STANDARD")
    tmpl_color = TEMPLATE_COLOR.get(tmpl, "#444")
    rank_icon  = RANK_ICON.get(rank, "📋")
    unit_id    = str(seg_row.get("street_id", ""))

    # Structural data
    truly_unc        = float(seg_row.get("truly_uncertain_share", 0.0))
    sfh_confirmed_sh = float(seg_row.get("sfh_confirmed_share", 0.0))
    caution          = seg_row.get("primary_caution", "")

    # Segment street stats
    seg_streets_all = street_df[street_df["segment_id"] == unit_id]
    n_total_streets = len(seg_streets_all)
    n_pass    = (seg_streets_all["structure_gate"] == "PASS").sum()
    n_fail    = (seg_streets_all["structure_gate"] == "FAIL").sum()
    n_canvass = int(
        ((seg_streets_all["structure_gate"] == "PASS") &
         (~seg_streets_all["low_sample_flag"].fillna(False))).sum()
    )

    # Aggregate building counts
    total_efh = int(seg_streets_all["sfh_detached_count"].sum())
    total_rh  = int(seg_streets_all["sfh_rowhouse_count"].sum())
    total_dhh = int(seg_streets_all["sfh_semi_count"].sum())
    total_sfh = int(seg_streets_all["sfh_total_count"].sum())
    total_bld = int(seg_streets_all["building_count_total"].sum())
    sfh_pct   = total_sfh / total_bld if total_bld > 0 else 0.0

    # Roof yield estimate
    roof_norm = float(seg_row.get("roof_suitability_score_norm", 0.5) or 0.5)
    roof_label = (
        "🟢 Sehr gut" if roof_norm >= 0.80
        else "🟢 Gut"    if roof_norm >= 0.55
        else "🟡 Mittel" if roof_norm >= 0.30
        else "🔴 Gering"
    )

    # PV saturation
    pv_score = float(seg_row.get("pv_coverage_score", 0.0) or 0.0)

    # Heat / HP status
    heat_status = str(seg_row.get("heat_status", "UNKNOWN"))
    hp_status   = str(seg_row.get("hp_status", "UNKNOWN"))

    fern  = _fern_badge(heat_status)
    hp    = _hp_badge(hp_status)

    with st.container(border=True):
        # ── Card Header ──────────────────────────────────────────────────────
        h1, h2, h3 = st.columns([1, 6, 3])

        with h1:
            st.markdown(f"### {rank_icon} #{rank}")

        with h2:
            st.markdown(f"**{name}**")
            st.caption(
                f"{n_total_streets} {t('srk.card_streets_count')} &nbsp;·&nbsp; "
                f"{n_canvass} 🟢 {t('srk.card_ready')} &nbsp;·&nbsp; "
                f"{t('srk.card_score')}: {final:.3f}"
            )

        with h3:
            # Canvass Tier badge (Option A soft gate)
            tier = str(seg_row.get("canvass_tier", ""))
            if not tier:
                # backward-compat: derive from heat_constraint_label
                _hl = str(seg_row.get("heat_constraint_label", seg_row.get("heat_status", "")))
                tier = "PRIMARY" if _hl in ("LOW", "NO_SIGNAL") \
                    else "NOT_RECOMMENDED" if _hl in ("HIGH", "NETWORK_LIKELY") \
                    else "SECONDARY"
            _tier_badge = {
                "PRIMARY":          ("🟢", "Sofort aktiv",         "#1e6b3c"),
                "SECONDARY":        ("🟡", "Vor Besuch klären",    "#8b6914"),
                "NOT_RECOMMENDED":  ("🔴", "Nicht empfohlen",      "#8b0000"),
            }.get(tier, ("⚪", tier, "#555"))
            _tb_icon, _tb_label, _tb_color = _tier_badge
            st.markdown(
                f"<span style='font-size:0.75em;font-weight:700;color:{_tb_color}'>"
                f"{_tb_icon} {_tb_label}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<span style='color:{tmpl_color};font-size:0.8em'>⬡ {tmpl}</span>",
                unsafe_allow_html=True,
            )
            if priority >= 0:
                st.caption(_priority_action(priority))


        # ── Signal row ──────────────────────────────────────────────────────
        s1, s2, s3, s4, s5, s6 = st.columns(6)
        s1.markdown(
            f"**{t('srk.card_fern_label')}**  \n{fern}  \n"
            f"<small style='opacity:0.60'>{t('srk.card_fern_sub')}</small>",
            unsafe_allow_html=True,
        )
        s2.markdown(
            f"**{t('srk.card_hp_label')}**  \n{hp}  \n"
            f"<small style='opacity:0.60'>{t('srk.card_hp_sub')}</small>",
            unsafe_allow_html=True,
        )
        if priority >= 0:
            s3.markdown(
                f"**Priority**  \n"
                f"<span style='color:#6c5ce7;font-weight:600'>{priority:.3f}</span>  \n"
                f"<small style='opacity:0.60'>{t('srk.card_priority_sub')}</small>",
                unsafe_allow_html=True,
            )
            s4.markdown(
                f"**Deploy**  \n{deploy:.2f}  \n"
                f"<small style='opacity:0.60'>{t('srk.card_deploy_sub')}</small>",
                unsafe_allow_html=True,
            )
            s5.markdown(
                f"**Risk Penalty**  \n−{risk:.0%}  \n"
                f"<small style='opacity:0.60'>{t('srk.card_risk_sub')}</small>",
                unsafe_allow_html=True,
            )
        else:
            s3.markdown(f"**Gate**  \n{seg_row.get('l1_gate_label', '—')}")
            s4.markdown("**Deploy**  \n—")
            s5.markdown("**Risk**  \n—")

        # Building count line
        parts = []
        if total_efh > 0: parts.append(f"EFH {total_efh}")
        if total_rh  > 0: parts.append(f"RH {total_rh}")
        if total_dhh > 0: parts.append(f"DHH {total_dhh}")
        bld_detail = " · ".join(parts)
        conf_tag = (
            t("srk.card_conf_osm")     if sfh_confirmed_sh >= 0.70
            else t("srk.card_conf_partial") if sfh_confirmed_sh >= 0.30
            else t("srk.card_conf_proxy")
        )
        s6.markdown(
            f"**{t('srk.card_sfh_total')}**  \n{total_sfh} ({sfh_pct:.0%})  \n"
            f"<small style='opacity:0.60'>{bld_detail} · {conf_tag}</small>",
            unsafe_allow_html=True,
        )

        # Structural uncertainty banner
        if truly_unc > 0.40:
            st.warning(
                t("srk.card_uncert_banner", pct=f"{truly_unc:.0%}").replace("{pct}", f"{truly_unc:.0%}"),
                icon="🏗",
            )

        # ── Reasons + caution ───────────────────────────────────────────────
        r1 = seg_row.get("top_reason_1", "")
        r2 = seg_row.get("top_reason_2", "")
        if r1 or r2:
            reason_text = ""
            if r1: reason_text += f"↗ {_translate_reason(r1)}"
            if r2: reason_text += f"  ·  ↗ {_translate_reason(r2)}"
            st.markdown(f"<small>{reason_text}</small>", unsafe_allow_html=True)

        if caution:
            st.markdown(
                f"<small style='color:#e67e22'>⚠️ {_translate_caution(caution)}</small>",
                unsafe_allow_html=True,
            )

        # ── Street Drill-Down ────────────────────────────────────────────────
        expand_key = f"_srk_exp_{unit_id}"
        page_key   = f"_srk_pg_{unit_id}"
        is_open    = st.session_state.get(expand_key, False)

        if n_total_streets > 0:
            btn_lbl = (
                t("srk.card_hide_streets", n=n_total_streets)
                if is_open
                else t("srk.card_show_streets", n=n_total_streets, p=n_pass, f=n_fail)
            )
            if st.button(btn_lbl, key=f"_srk_btn_{unit_id}", use_container_width=True):
                st.session_state[expand_key] = not is_open
                if is_open:
                    st.session_state.pop(page_key, None)
                st.rerun()

            if is_open:
                page    = st.session_state.get(page_key, 0)
                n_pages = max(1, (n_total_streets + _PAGE_SIZE - 1) // _PAGE_SIZE)
                _render_street_list(seg_streets_all, page=page, page_size=_PAGE_SIZE)

                if n_pages > 1:
                    pc1, pc2, pc3 = st.columns([1, 3, 1])
                    with pc1:
                        if page > 0:
                            if st.button(t("srk.street_prev"), key=f"_srk_prev_{unit_id}"):
                                st.session_state[page_key] = page - 1
                                st.rerun()
                    with pc2:
                        st.caption(t("srk.street_page_info", p=page+1, t=n_pages, n=n_total_streets))
                    with pc3:
                        if page < n_pages - 1:
                            if st.button(t("srk.street_next"), key=f"_srk_next_{unit_id}"):
                                st.session_state[page_key] = page + 1
                                st.rerun()
        else:
            st.caption(t("srk.card_no_streets"))


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------
def render_street_ranking_view() -> None:
    st.markdown(t("srk.title"))
    st.caption(t("srk.subtitle"))

    # --- Load data (cached) ---
    if not PARQUET.exists():
        st.warning(t("srk.warn_no_segments"))
        return

    if not STREET_PARQUET.exists():
        st.warning(t("srk.warn_no_streets"))
        return

    df, street_df = _load_merged_data()
    if df.empty:
        st.info(t("srk.no_data"))
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
    col1.metric(t("srk.metric_regions"), n_segments)
    col2.metric(t("srk.metric_streets"), total_streets)
    col3.metric(t("srk.metric_top_score"), f"{top_score:.3f}")
    col4.metric(
        t("srk.metric_canvass"),
        ready_count,
        help=t("srk.metric_canvass_help"),
    )

    st.markdown("---")

    # ── Region Cards ────────────────────────────────────────────────────────
    for _, seg_row in df.sort_values("rank").iterrows():
        _render_region_card(seg_row, street_df)

    st.markdown("---")

    # ── Global Cross-Segment Analysis ───────────────────────────────────────
    with st.expander(t("srk.global_title"), expanded=False):
        st.caption(t("srk.global_caption"))

        gate_opts_keys = ["All gates", "PASS", "QUALIFIED", "REVIEW", "FAIL"]
        gate_opts_display = [
            t("srk.global_gate_all") if k == "All gates" else k
            for k in gate_opts_keys
        ]

        top_n = st.slider(
            t("srk.global_top_n"),
            min_value=10,
            max_value=len(street_df),
            value=30,
            step=10,
            key="global_analysis_n",
        )
        sel_gate_display = st.selectbox(
            t("srk.global_gate_filter"),
            gate_opts_display,
            key="global_analysis_gate",
        )
        # Map display back to data key
        sel_gate = gate_opts_keys[gate_opts_display.index(sel_gate_display)]

        gate_key = "_global_analysis_active"
        if st.button(t("srk.global_load_btn"), key="run_global_analysis"):
            st.session_state[gate_key] = True

        if not st.session_state.get(gate_key, False):
            st.caption(t("srk.global_load_hint"))
        else:
            global_view = street_df.copy()
            if sel_gate != "All gates":
                global_view = global_view[global_view["structure_gate"] == sel_gate]
            global_view = global_view.sort_values("global_rank").head(top_n)

            # Column headers
            G = st.columns([2, 1, 6, 2, 2, 2, 3, 3])
            G[0].markdown(t("srk.global_col_rank"))
            G[1].markdown(t("srk.global_col_gate"))
            G[2].markdown(t("srk.global_col_street"))
            G[3].markdown(t("srk.global_col_score"))
            G[4].markdown(t("srk.global_col_sfh"))
            G[5].markdown(t("srk.global_col_efh"))
            G[6].markdown(t("srk.global_col_segment"))
            G[7].markdown(t("srk.global_col_note"))
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
                    t("srk.osm_confirmed") if "Stage-1" in dq_note
                    else t("srk.proxy_type") if "Stage-2" in dq_note
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
                        + t("srk.street_small_sample", n=n_total) +
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    st.caption(t("srk.footer"))
