"""
street_roi_generator.py
=======================
Street-level ROI profile builder and renderer for the Global Street Ranking view.

Logic:
  1. Inspect building subtype distribution for a street (EFH/DHH/RH).
  2. Determine 1-3 dominant profiles (threshold: ≥25% of total SFH).
  3. Build case_data for each profile and run calculate_roi_mvp().
  4. Render a compact ROI summary (1-3 side-by-side cards) inside an st.expander.

Inputs from street parquet (field_08):
  sfh_detached_count, sfh_semi_count, sfh_rowhouse_count, sfh_total_count,
  cluster_id, plz, b_roof_norm (segment-level proxy for yield quality)

Segment-level inputs (from field_07 parquet):
  hp_status, heat_status → drives has_heat_pump flag

Author: D-ESS Engine
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

import pandas as pd
import streamlit as st

from core.roi_mvp import calculate_roi_mvp

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT       = pathlib.Path(__file__).parent.parent.parent
POLICY_PATH = ROOT / "policies" / "roi_hp_mvp_neuss_2026.json"

# ---------------------------------------------------------------------------
# Building profile benchmarks
# ---------------------------------------------------------------------------
# Building type → (label_de, hp_bucket, household_size, kwp_override)
PROFILE_SPECS: dict[str, tuple[str, str, str, int]] = {
    "EFH": ("EFH Detached",  "150_200", "4", 11),
    "DHH": ("DHH Semi-Det.", "100_150", "3", 8),
    "RH":  ("RH Rowhouse",   "100_150", "3", 6),
}

# Minimum share of SFH stock to be included as a profile  (0.25 = 25%)
PROFILE_THRESHOLD = 0.25

# ---------------------------------------------------------------------------
# yield_per_kwp_override from b_roof_norm
# ---------------------------------------------------------------------------
def _yield_override(b_roof_norm: float) -> int:
    """Map segment roof quality [0,1] → yield kWh/kWp ∈ [900, 1100]."""
    clamped = max(0.0, min(1.0, float(b_roof_norm)))
    return int(900 + 200 * clamped)


# ---------------------------------------------------------------------------
# Profile builder
# ---------------------------------------------------------------------------
def build_street_profiles(
    street_row: pd.Series,
    seg_meta: pd.Series | None = None,
) -> list[dict[str, Any]]:
    """
    Determine 1-3 building profiles for a street and build case_data for each.

    Returns a list of dicts:
        {"label": str, "case_data": dict, "subtype_key": str, "share": float}
    """
    n_efh  = int(street_row.get("sfh_detached_count", 0))
    n_dhh  = int(street_row.get("sfh_semi_count", 0))
    n_rh   = int(street_row.get("sfh_rowhouse_count", 0))
    n_sfh  = int(street_row.get("sfh_total_count", 0))

    if n_sfh == 0:
        return []

    # b_roof_norm: segment-level. Already in street_row (broadcasts from field_08).
    b_roof_norm = float(street_row.get("b_roof_norm", 0.5))
    yield_ovr   = _yield_override(b_roof_norm)

    plz = str(street_row.get("plz", ""))

    # ── Determine has_heat_pump from hp_status (segment-level signal) ──────
    # STRONG_HP_UPLIFT   → HP recommended, assume True
    # MODERATE_HP_UPLIFT → HP possible, assume True (with caution note)
    # LIMITED_HP_UPLIFT  → HP unlikely (Fernwärme / gas area), assume False
    #                       → ROI engine uses HOUSEHOLD_ONLY load profile
    hp_status  = str(street_row.get("hp_status", "MODERATE_HP_UPLIFT"))
    has_hp     = hp_status != "LIMITED_HP_UPLIFT"
    hp_note    = {
        "STRONG_HP_UPLIFT":    "HP+PV",
        "MODERATE_HP_UPLIFT":  "HP+PV (bedingt)",
        "LIMITED_HP_UPLIFT":   "PV only (kein HP)",
    }.get(hp_status, "HP+PV")

    # ── Scale kWp by b_roof_norm (worse roof → fewer usable panels) ─────────
    # Formula: kWp_adj = base_kWp × (0.70 + 0.30 × b_roof_norm)
    # SUBURB (1.0): base×1.00  |  NORF (0.345): base×0.80  |  GRIML (0.0): base×0.70
    roof_scale = 0.70 + 0.30 * max(0.0, min(1.0, b_roof_norm))

    candidates = [
        ("EFH", n_efh),
        ("DHH", n_dhh),
        ("RH",  n_rh),
    ]

    profiles = []
    for subtype_key, count in candidates:
        share = count / n_sfh
        if share < PROFILE_THRESHOLD:
            continue

        label, hp_bucket, household_size, kwp_base = PROFILE_SPECS[subtype_key]

        # Scale kWp by roof quality (b_roof_norm)
        kwp_adj = max(4, min(15, round(kwp_base * roof_scale)))

        case_data = {
            "case_id": (
                f"STREET_ROI_{street_row.get('cluster_id', 'unknown')}"
                f"_{subtype_key}_kwp{kwp_adj}"
            ),
            "attributes": {
                "has_heat_pump":          has_hp,
                "has_pv":                 False,
                "household_size":         household_size,
                "hp_input_mode":          "MODE_B",
                "hp_bucket":              hp_bucket,
                "kwp_override":           kwp_adj,          # roof-quality-scaled
                "yield_per_kwp_override": yield_ovr,        # 900-1100 kWh/kWp
                "financing_enabled":      True,
                "electric_vehicle":       "NONE",
                "region":                 f"{plz}",
            },
            "_dess_version": "V3.5-STREET",
        }

        profiles.append({
            "label":       f"{label} · {hp_note}",
            "subtype_key": subtype_key,
            "share":       share,
            "count":       count,
            "kwp_adj":     kwp_adj,
            "has_hp":      has_hp,
            "hp_note":     hp_note,
            "case_data":   case_data,
        })

    # Cap at 3 profiles, highest share first
    profiles.sort(key=lambda x: x["share"], reverse=True)
    return profiles[:3]


# ---------------------------------------------------------------------------
# ROI runner
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_policy(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_street_roi(
    profiles: list[dict],
    policy_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    """
    Run calculate_roi_mvp for each profile.
    Returns a parallel list of roi_result dicts.
    """
    pp = str(policy_path or POLICY_PATH)
    policy = _load_policy(pp)

    results = []
    for p in profiles:
        try:
            roi = calculate_roi_mvp(p["case_data"], policy)
        except Exception as exc:  # noqa: BLE001
            roi = {"verdict": "ERROR", "reason": str(exc)}
        results.append(roi)
    return results


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
def _eur(cents: int) -> str:
    """Format cents → '€ X,XXX'"""
    return f"€ {cents // 100:,}".replace(",", ".")


def _payback_color(years: int) -> str:
    if years <= 10: return "#1e6b3c"
    if years <= 14: return "#8b6914"
    return "#8b0000"


def _profile_header_color(subtype: str) -> str:
    return {"EFH": "#1a3c5e", "DHH": "#3a1c5e", "RH": "#1c4c2e"}.get(subtype, "#333")


# ---------------------------------------------------------------------------
# Main UI renderer
# ---------------------------------------------------------------------------
def render_street_roi_expander(
    street_row: pd.Series,
    seg_meta: pd.Series | None = None,
) -> None:
    """
    Render an ROI profile expander for one street row inside the global ranking.
    Must be called inside the street's st.container block.

    Auto-computes ROI on first render (no button required).
    Vollbericht still requires explicit click.
    Structure gate FAIL → no ROI shown.
    """
    cluster_id  = str(street_row.get("cluster_id", ""))
    street_name = str(street_row.get("street_name", ""))
    cache_key   = f"str_roi_{cluster_id}"

    # Gate: structure FAIL → no meaningful ROI can be derived
    if str(street_row.get("structure_gate", "")).upper() == "FAIL":
        with st.expander("📊 ROI-Profil (nicht verfügbar)", expanded=False):
            st.caption(
                "⛔ Struktur-Gate FAIL — keine geeigneten EFH/DHH/RH-Gebäude in dieser Straße. "
                "ROI-Profil nicht verfügbar."
            )
        return

    with st.expander("📊 ROI-Profil (PV + Wärmepumpe)", expanded=False):

        # ── Auto-compute ROI on first render (no button required) ───────────
        # Policy JSON is @st.cache_data — zero I/O per call after first load.
        # build_street_profiles() + run_street_roi() = pure Python, <5ms per street.
        if cache_key not in st.session_state:
            # Low-sample advisory (shown before results, not blocking)
            if bool(street_row.get("low_sample_flag", False)):
                n_bld = int(street_row.get("building_count_total", 0))
                st.info(
                    f"⚠️ **Kleine Stichprobe** (n = {n_bld} Gebäude) — "
                    "Profil basiert auf wenigen Gebäuden. Orientierungswert mit erhöhter Streubreite.",
                )
            with st.spinner("ROI wird berechnet …"):
                _profiles    = build_street_profiles(street_row, seg_meta)
                _roi_results = run_street_roi(_profiles)
            st.session_state[cache_key] = (_profiles, _roi_results)

        profiles, roi_results = st.session_state[cache_key]

        if not profiles:
            st.warning(
                "⚠️ Keine SFH-Profile gefunden (alle MFH oder kein ausreichendes Gebäudeprofil). "
                "ROI nicht verfügbar."
            )
            return

        # ── Info banner: roof quality + profile count ────────────────────────
        b_roof_norm   = float(street_row.get("b_roof_norm", 0.5))
        yield_ovr     = _yield_override(b_roof_norm)
        hp_conf       = float(street_row.get("hp_confidence", 1.0))
        dq_note       = str(street_row.get("data_quality_note", ""))
        truly_unc     = float(street_row.get("seg_truly_uncertain_share", 0.0))
        heat_status   = str(street_row.get("heat_status", ""))

        banner_parts = [
            f"Dachqualität (Segment): b_roof_norm = **{b_roof_norm:.2f}** "
            f"→ Ertrag-Ansatz **{yield_ovr} kWh/kWp/Jahr**",
            f"{len(profiles)} Haustypkategorie(n)",
        ]
        st.caption("  |  ".join(banner_parts))

        # ── Context warnings (data quality + heat risk) ──────────────────────
        context_parts = []
        if "Stage-2" in dq_note:
            context_parts.append("🟡 Gebäudetypen geschätzt — Feldbegehung empfohlen vor Erstgespräch")
        if hp_conf < 0.65:
            context_parts.append(
                f"⚠️ Heizquelle: Proxy-Annahme (Konfidenz {hp_conf:.0%}) — nicht vor Ort bestätigt"
            )
        if truly_unc > 0.20:
            context_parts.append(
                f"⚠️ {truly_unc:.0%} der Gebäude nicht klassifiziert — Stichprobe mit Vorsicht nutzen"
            )
        # Fernwärme risk warning (Component 3a)
        if heat_status == "NETWORK_LIKELY":
            context_parts.append(
                "🚫 Fernwärme-Netz wahrscheinlich — "
                "HP-Vorteil evtl. nicht realisierbar. Vor dem Pitch klären."
            )
        elif heat_status in ("LIMITED_OR_UNCLEAR", "LOW_NETWORK_SIGNAL"):
            context_parts.append(
                "⚠️ Fernwärme-Risiko möglich — Heizinfrastruktur vor Ort prüfen"
            )
        if context_parts:
            st.caption("  ·  ".join(context_parts))

        # ── Profile cards (1-3 columns) ─────────────────────────────────────
        cols = st.columns(len(profiles))

        for col, profile, roi in zip(cols, profiles, roi_results):
            subtype = profile["subtype_key"]
            label   = profile["label"]
            share   = profile["share"]
            count   = profile["count"]
            kwp_ovr = profile["case_data"]["attributes"]["kwp_override"]
            hdr_col = _profile_header_color(subtype)

            with col:
                st.markdown(
                    f"<div style='background:{hdr_col};color:#fff;"
                    f"border-radius:6px 6px 0 0;padding:8px 12px;"
                    f"font-weight:700;font-size:0.9em;'>"
                    f"{label} &nbsp;<span style='font-weight:400;font-size:0.8em;'>"
                    f"({count} Gebäude · {share:.0%})</span></div>",
                    unsafe_allow_html=True,
                )

                if roi.get("verdict") != "ROI_OK":
                    st.error(f"ROI Error: {roi.get('reason', 'unknown')}")
                    continue

                # Extract key metrics
                kwp_rec      = roi.get("kWp_rec", kwp_ovr)
                e_pv         = roi.get("e_pv_kwh", 0)
                e_load       = roi.get("e_load_kwh", 1)  # avoid div/0
                capex_vat0   = roi.get("capex", {}).get("vat0_cents", 0)
                co2          = roi.get("co2_saved_tons_per_year", 0)
                fin          = roi.get("financing_report", {})
                monthly_mgn  = fin.get("monthly_cashflow_margin_eur", 0)

                scenarios    = roi.get("scenarios", [])
                base_sc      = scenarios[1] if len(scenarios) > 1 else (scenarios[0] if scenarios else {})
                payback      = base_sc.get("payback_dynamic_years", 999)
                benefit_y1   = base_sc.get("annual_benefit_cents", 0)
                profit_20y   = base_sc.get("profit20_cents", 0)
                irr_bps      = base_sc.get("irr_bps", 0)
                irr_pct      = irr_bps / 100

                # Autarky: how much of household load is self-covered — align with Vollbericht
                e_self       = base_sc.get("e_self_kwh", 0)
                autarky_pct  = min(100.0, e_self / max(e_load, 1) * 100)

                # Render metrics
                pb_col = _payback_color(payback)
                icon   = "🟢" if payback <= 10 else ("🟡" if payback <= 14 else "🔴")
                irr_col = "#1e6b3c" if irr_pct >= 15 else ("#8b6914" if irr_pct >= 10 else "#8b0000")

                st.markdown(
                    f"""
<div style='border:1px solid rgba(128,128,128,0.25);border-top:none;border-radius:0 0 6px 6px;
            padding:12px;font-size:0.85em;'>

  <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
    <span>☀️ Anlage</span>
    <strong>{kwp_rec} kWp &nbsp;·&nbsp; {e_pv:,} kWh/a</strong>
  </div>

  <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
    <span>🔋 Autarkie</span>
    <strong>≈ {autarky_pct:.0f} %</strong>
  </div>

  <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
    <span>💰 Invest (VAT 0%)</span>
    <strong>{_eur(capex_vat0)}</strong>
  </div>

  <div style='border-top:1px solid rgba(128,128,128,0.20);margin:8px 0;'></div>

  <div style='display:flex;justify-content:space-between;margin-bottom:6px;'>
    <span>📅 Rückfluss (Payback)</span>
    <strong style='color:{pb_col};'>{icon} {payback if payback < 999 else "?"} Jahre</strong>
  </div>

  <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
    <span>📊 ROI / IRR (20J.)</span>
    <strong style='color:{irr_col};'>{irr_pct:.1f}% p.a.</strong>
  </div>

  <div style='border-top:1px solid rgba(128,128,128,0.20);margin:8px 0;'></div>

  <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
    <span>📈 Jahr-1-Vorteil</span>
    <strong>{_eur(benefit_y1)}/Jahr</strong>
  </div>

  <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
    <span>🏦 Monatl. Cashflow</span>
    <strong style='color:{"#2ecc71" if monthly_mgn >= 0 else "#e74c3c"};'>
      {"+" if monthly_mgn >= 0 else ""}{monthly_mgn} €/Mon.</strong>
  </div>

  <div style='display:flex;justify-content:space-between;margin-bottom:8px;
              background:rgba(108,99,255,0.12);border-radius:4px;padding:4px 6px;'>
    <span>💎 Gewinn 20 Jahre</span>
    <strong style='color:#7c6ce7;'>{_eur(profit_20y)}</strong>
  </div>

  <div style='display:flex;justify-content:space-between;'>
    <span>🌱 CO₂-Ersparnis</span>
    <strong>{co2:.1f} t/Jahr</strong>
  </div>

</div>
                    """,
                    unsafe_allow_html=True,
                )


                # ── "Vollbericht" button per profile card ────────────────────
                if st.button(
                    f"📄 Vollbericht — {profile['label']}",
                    key=f"fullroi_{cluster_id}_{profile['subtype_key']}",
                    use_container_width=True,
                    help="Vollständiger ROI-Report wie im ROI MVP (alle Szenarien, Finanzierung, CO₂)",
                ):
                    # R3 fix: inject full street ranking context into report session_state
                    st.session_state["street_roi_report"] = {
                        "roi_result": roi,
                        "case_id":    profile["case_data"]["case_id"],
                        "street_context": {
                            "street_name":             street_name,
                            "segment_id":              str(street_row.get("segment_id", "")),
                            "segment_rank":            int(street_row.get("segment_rank", 99)),
                            "rank_in_segment":         int(street_row.get("rank_in_segment", 0)),
                            "global_rank":             int(street_row.get("global_rank", 9999)),
                            "adjusted_street_score":   float(street_row.get("adjusted_street_score", 0.0)),
                            "data_quality_note":       str(street_row.get("data_quality_note", "")),
                            "low_sample_flag":         bool(street_row.get("low_sample_flag", False)),
                            "hp_confidence":           float(street_row.get("hp_confidence", 1.0)),
                            "seg_truly_uncertain":     float(street_row.get("seg_truly_uncertain_share", 0.0)),
                        },
                    }
                    st.session_state["street_roi_context"] = (
                        f"{street_name} · {profile['label']}"
                    )
                    st.session_state["workspace_view"] = "STREET_ROI_FULL"
                    st.rerun()

        # Reset button + footer
        st.markdown("")
        if st.button(
            "↺ Neu berechnen",
            key=f"roi_reset_{cluster_id}",
            use_container_width=False,
        ):
            if cache_key in st.session_state:
                del st.session_state[cache_key]
            st.rerun()

        st.caption(
            "ℹ️ Annahmen: 4.5% APR · 10J. Finanzierung · VAT 0% (EEG) · "
            "Degradation 0.5%/J. · Neuss Einspeisevergütung 7.78 ct/kWh. "
            "Daten: Typ-A-Signal (Gebäudestruktur OSM) + Typ-B-Signal (Dachqualität Segment-Proxy). Orientierungswert."
        )
