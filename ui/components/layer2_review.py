"""
ui/components/layer2_review.py
================================
Layer 2 Internal Review Component — D-ESS / Neuss MVP
Embedded inside the main app.py under City Insights.

Call render_layer2_review() from workspace.py when
workspace_view == "LAYER2_REVIEW".

Data sources (READ-ONLY):
  - data/layer2/layer2_mvp_input_table.parquet
  - output/stage6/segment_registry_neuss_v1.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Paths — resolved relative to this file's parent (d-ess-engine/)
# ---------------------------------------------------------------------------
_HERE     = Path(__file__).resolve()
_BASE_DIR = _HERE.parent.parent.parent          # d-ess-engine/
PARQUET_P  = _BASE_DIR / "data"   / "layer2" / "layer2_mvp_input_table.parquet"
REGISTRY_P = _BASE_DIR / "output" / "stage6" / "segment_registry_neuss_v1.json"
HP_UPLIFT_P = _BASE_DIR / "data"   / "layer2" / "layer2_prio25_hp_uplift.parquet"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# RANKING_WEIGHTS: LEGACY — used only for the weight bar-chart display in Section F.
# Actual scoring is now bottom-up: field_08 (street scores) → field_05
# (street_quality_agg × tier_disc) → field_07 (heat + HP modifiers).
# Do NOT use these weights to recompute scores independently.
RANKING_WEIGHTS = {
    "street_quality_agg (A+B)":    0.70,   # field_08 street-level composite (SFH quality + gate + scale + mfh_clean + roof + PV-oppty)
    "fernwaerme_modifier":          0.15,   # field_03 heat constraint (×0.90 or ×1.00)
    "hp_modifier":                  0.15,   # field_06 HP narrative uplift
}
CONF_DISCOUNT = {
    "QUALITY_A": 1.00,
    "QUALITY_B": 0.85,
    "SYNTHETIC": 0.00,
}
QUALITY_TIER_MAP = {
    "NEUSS_NORF_01":    "QUALITY_A",
    "NEUSS_SUBURB_01":  "QUALITY_B",
    "NEUSS_GRIML_01":   "QUALITY_B",
    "NEUSS_CENTRAL_01": "SYNTHETIC",
    "NEUSS_OLD_TOWN_01":"SYNTHETIC",
}

# ---------------------------------------------------------------------------
# Styles (injected once per render — light-theme compatible)
# ---------------------------------------------------------------------------
_CSS = """
<style>
/* ── D-ESS Layer 2 Review — Dark-mode compatible styles ─────────────────── */

/* Root tokens: light defaults */
:root {
    --l2-bg:           #ffffff;
    --l2-bg-alt:       #f8f9fa;
    --l2-bg-row-real:  #e8f5e9;
    --l2-bg-row-grey:  #f5f5f5;
    --l2-bg-row-synth: #eeeeee;
    --l2-border:       #dee2e6;
    --l2-text:         #212529;
    --l2-text-muted:   #666666;
    --l2-text-sub:     #888888;
    --l2-text-aaa:     #aaaaaa;
}

/* Dark-mode overrides (Streamlit sets data-theme="dark" on <body>) */
[data-theme="dark"],
@media (prefers-color-scheme: dark) {
    :root {
        --l2-bg:           #1a1a2e;
        --l2-bg-alt:       #16213e;
        --l2-bg-row-real:  #1a3a2a;
        --l2-bg-row-grey:  #1e1e2e;
        --l2-bg-row-synth: #18182a;
        --l2-border:       #3a3a5c;
        --l2-text:         #e0e0e0;
        --l2-text-muted:   #a0a0b0;
        --l2-text-sub:     #8888a0;
        --l2-text-aaa:     #666680;
    }
}

/* ── Badges ─────────────────────────────────────────────────────────────── */
.l2r-badge {
    display: inline-block; padding: 2px 9px; border-radius: 4px;
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em;
}
/* QUALITY_A — green */
.l2r-qa  { background: rgba(25,135,84,0.20); color: #2ecc71; border: 1px solid rgba(25,135,84,0.40); }
/* QUALITY_B — amber */
.l2r-qb  { background: rgba(255,193,7,0.18); color: #f39c12; border: 1px solid rgba(255,193,7,0.35); }
/* SYNTHETIC — grey */
.l2r-syn { background: rgba(108,117,125,0.18); color: #a0a0b0; border: 1px solid rgba(108,117,125,0.35); }
/* Gate: DEPLOYABLE */
.l2r-dep { background: rgba(25,135,84,0.20); color: #2ecc71; border: 1px solid rgba(25,135,84,0.40); }
/* Gate: MIXED */
.l2r-mix { background: rgba(255,193,7,0.18); color: #f39c12; border: 1px solid rgba(255,193,7,0.35); }
/* Gate: BLOCKED */
.l2r-blk { background: rgba(220,53,69,0.18); color: #e74c3c; border: 1px solid rgba(220,53,69,0.35); }
/* NOT_AVAILABLE */
.l2r-na  { background: rgba(108,117,125,0.15); color: #a0a0b0; border: 1px solid rgba(108,117,125,0.30); }

/* ── Banners & callouts ──────────────────────────────────────────────────── */
.l2r-draft-banner {
    background: rgba(255,193,7,0.12); border: 1px solid rgba(255,193,7,0.45);
    border-radius: 6px; padding: 8px 14px;
    color: #f0c040; font-size: 0.82rem; margin-bottom: 10px;
}
.l2r-caveat {
    background: rgba(255,140,0,0.10); border-left: 3px solid #e67e22;
    padding: 7px 11px; border-radius: 0 5px 5px 0;
    margin-bottom: 5px; font-size: 0.82rem; color: #e0a060;
}
.l2r-ok {
    background: rgba(25,135,84,0.12); border-left: 3px solid #2ecc71;
    padding: 7px 11px; border-radius: 0 5px 5px 0;
    font-size: 0.82rem; color: #2ecc71;
}
.l2r-not-accepted {
    background: rgba(220,53,69,0.15); border: 2px solid #e74c3c;
    border-radius: 6px; padding: 12px 16px;
    text-align: center; color: #e74c3c;
}

/* ── Section heading ─────────────────────────────────────────────────────── */
.l2r-section {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em;
    color: var(--l2-text-muted); text-transform: uppercase;
    border-bottom: 1px solid var(--l2-border);
    padding-bottom: 3px; margin-bottom: 10px;
}

/* ── Field table ─────────────────────────────────────────────────────────── */
.l2r-field-table { width: 100%; border-collapse: collapse; font-size: 0.83rem; color: var(--l2-text); }
.l2r-field-table th {
    padding: 5px 8px; text-align: left;
    background: var(--l2-bg-alt); color: var(--l2-text-muted);
    font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.06em; border-bottom: 2px solid var(--l2-border);
}
.l2r-field-table td { padding: 6px 8px; border-bottom: 1px solid var(--l2-border); color: var(--l2-text); }

/* ── Rank row ────────────────────────────────────────────────────────────── */
.l2r-rank-row {
    display: flex; align-items: center; gap: 12px;
    background: var(--l2-bg-alt); border-radius: 6px;
    padding: 9px 12px; margin-bottom: 6px;
    border-left: 4px solid var(--l2-border);
}

/* ── Checklist ─────────────────────────────────────────────────────────── */
.l2r-checklist-item {
    display: flex; align-items: flex-start; gap: 8px;
    margin-bottom: 7px; font-size: 0.86rem;
}
</style>
"""



# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_data() -> tuple[pd.DataFrame, dict]:
    df = pd.read_parquet(PARQUET_P)
    with open(REGISTRY_P, encoding="utf-8") as f:
        registry = json.load(f)
    caveats: dict[str, list[str]] = {}
    for seg in registry.get("segments", []):
        sid = seg.get("segment_id", "")
        caveats[sid] = seg.get("expansion_caveats", [])

    # Merge pre-computed final scores from field_07 pipeline.
    # This ensures layer2_review.py shows scores consistent with
    # the operational ranking in street_ranking_view.py.
    street_rank_p = _BASE_DIR / "data" / "layer2" / "street_ranking_v1.parquet"
    if street_rank_p.exists():
        f7 = pd.read_parquet(street_rank_p)[
            ["street_id", "final_score", "base_score", "rank", "confidence"]
        ].rename(columns={
            "street_id":   "unit_id",
            "final_score": "_f7_final_score",
            "base_score":  "_f7_base_score",
            "rank":        "_f7_rank",
            "confidence":  "_f7_confidence",
        })
        df = df.merge(f7, on="unit_id", how="left")

    return df, caveats



def _draft_score(row: pd.Series, tier: str) -> float | None:
    """Return the operational final score from field_07 (preferred),
    or fall back to the legacy RANKING_WEIGHTS formula if not yet computed."""
    if not row.get("row_usable_for_ranking", False):
        return None
    # Prefer pre-computed score from field_07 pipeline (Logic 1, street-aggregated)
    if pd.notna(row.get("_f7_final_score")):
        return float(row["_f7_final_score"])
    # Legacy fallback (RANKING_WEIGHTS — may differ from pipeline)
    disc = CONF_DISCOUNT.get(tier, 1.0)
    s = 0.0
    for field, w in {"effective_sfh_share": 0.30, "roof_suitability_score_norm": 0.25,
                     "pv_coverage_score": 0.25, "pct_l1_gate_pass": 0.20}.items():
        v = row.get(field)
        s += float(v) * w if pd.notna(v) else 0.0
    return round(s * disc, 4)



def _tier_badge(tier: str) -> str:
    cls = {"QUALITY_A": "l2r-qa", "QUALITY_B": "l2r-qb", "SYNTHETIC": "l2r-syn"}.get(tier, "l2r-syn")
    return f'<span class="l2r-badge {cls}">{tier}</span>'


def _gate_badge(gate: str) -> str:
    cls = {
        "DEPLOYABLE":    "l2r-dep",
        "MIXED":         "l2r-mix",
        "BLOCKED":       "l2r-blk",
        "NOT_AVAILABLE": "l2r-na",
    }.get(gate, "l2r-na")
    label = gate if gate != "NOT_AVAILABLE" else "—"
    return f'<span class="l2r-badge {cls}">{label}</span>'


def _conf_tag(conf) -> str:
    if pd.isna(conf):
        return "—"
    c = float(conf)
    color = "#0f5132" if c >= 0.80 else "#664d03" if c >= 0.60 else "#842029"
    return f'<span style="color:{color};font-weight:700;">conf = {c:.2f}</span>'


def _fmt(val, pct: bool = False, dec: int = 4) -> str:
    if pd.isna(val) or val is None:
        return '<span style="color:#aaa;">—</span>'
    if pct:
        return f"{float(val)*100:.1f}%"
    return f"{float(val):.{dec}f}"


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------
def render_layer2_review() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Guard: check parquet exists ──────────────────────────────────────
    if not PARQUET_P.exists():
        st.error(
            f"Layer 2 parquet not found at `{PARQUET_P}`.\n\n"
            "Run `scripts/build_layer2_mvp_input_table.py` first."
        )
        return

    df, caveats_map = _load_data()

    # Add derived columns
    df = df.copy()
    df["quality_tier"] = df["unit_id"].map(QUALITY_TIER_MAP).fillna("SYNTHETIC")
    df["draft_score"]  = df.apply(
        lambda r: _draft_score(r, QUALITY_TIER_MAP.get(r["unit_id"], "SYNTHETIC")),
        axis=1,
    )
    usable = (
        df[df["row_usable_for_ranking"] == True]
        .sort_values("draft_score", ascending=False)
        .reset_index(drop=True)
    )
    usable["draft_rank"] = usable.index + 1
    df = df.merge(usable[["unit_id", "draft_rank"]], on="unit_id", how="left")

    # ── Header ────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([6, 2, 2])
    with c1:
        st.markdown("### 🔍 Layer 2 Review Console")
        st.caption("D-ESS · Neuss MVP · PV-only ROI · READ-ONLY internal review")
    with c2:
        st.markdown(
            '<span class="l2r-badge l2r-mix" style="font-size:0.8rem;">EARLY_COMPARATIVE_REVIEW_READY</span>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<span class="l2r-badge l2r-blk" style="font-size:0.8rem;">NOT YET ACCEPTED</span>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ════════════════════════════════════════════════════════════════════
    # A · Segment Overview Table
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="l2r-section">A · Segment Overview</div>', unsafe_allow_html=True)

    header_cols = ["Segment", "Status", "Tier", "Usable", "Buildings", "SFH %", "Gate", "PV Score", "Draft Rank"]
    rows_html = ""
    for _, row in df.iterrows():
        if row.row_usable_for_ranking:
            bg = "rgba(25,135,84,0.12)"   # subtle green — real & usable
        elif row.unit_status == "REAL_GROUNDED":
            bg = "rgba(108,117,125,0.10)"  # subtle grey — real but not usable
        else:
            bg = "rgba(108,117,125,0.07)"  # faint — synthetic
        sfh_str  = f"{row.sfh_friendly_share*100:.1f}%" if pd.notna(row.sfh_friendly_share) else "—"
        pv_str   = f"{row.pv_coverage_score:.4f}"       if pd.notna(row.pv_coverage_score)  else "—"
        rank_str = f"#{int(row.draft_rank)}"             if pd.notna(row.draft_rank)          else "—"
        bldg_str = f"{int(row.f02_building_count):,}"   if pd.notna(row.f02_building_count)  else "—"
        usable_str = "✅ Yes" if row.row_usable_for_ranking else "❌ No"
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:6px 10px;font-weight:700;color:var(--l2-text)">{row.unit_id}</td>
          <td style="padding:6px 10px;font-size:0.8rem;color:var(--l2-text-muted)">{row.unit_status}</td>
          <td style="padding:6px 10px;">{_tier_badge(row.quality_tier)}</td>
          <td style="padding:6px 10px;text-align:center;">{usable_str}</td>
          <td style="padding:6px 10px;text-align:right;font-weight:700;color:#0984e3;">{bldg_str}</td>
          <td style="padding:6px 10px;text-align:right;">{sfh_str}</td>
          <td style="padding:6px 10px;">{_gate_badge(str(row.l1_gate_label))}</td>
          <td style="padding:6px 10px;text-align:right;">{pv_str}</td>
          <td style="padding:6px 10px;text-align:center;font-weight:800;color:#6c5ce7;">{rank_str}</td>
        </tr>"""

    st.markdown(f"""
    <table style="width:100%;border-collapse:collapse;border-radius:6px;overflow:hidden;
                  font-size:0.85rem;border:1px solid var(--l2-border);">
      <thead>
        <tr style="background:var(--l2-bg-alt);">
          {''.join(f'<th style="padding:7px 10px;text-align:left;color:var(--l2-text-muted);font-size:0.72rem;'
                   f'text-transform:uppercase;letter-spacing:0.07em;">{h}</th>'
                   for h in header_cols)}
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # B + C + D · Detail Panel + Quality Tier + Caveats
    # ════════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="l2r-section">B · Segment Detail &nbsp;·&nbsp; C · Quality Tier &nbsp;·&nbsp; D · Caveats</div>',
        unsafe_allow_html=True,
    )

    selected_id = st.selectbox(
        "Select segment to inspect:",
        options=df["unit_id"].tolist(),
        key="l2r_seg_select",
    )
    sel = df[df["unit_id"] == selected_id].iloc[0]
    tier = sel["quality_tier"]
    tier_caveats = caveats_map.get(selected_id, [])

    col_tier, col_detail = st.columns([1, 3], gap="large")

    # ── C · Quality Tier card ────────────────────────────
    with col_tier:
        tier_colors = {"QUALITY_A": "#0f5132", "QUALITY_B": "#664d03", "SYNTHETIC": "#383d41"}
        tier_bgs    = {"QUALITY_A": "#d1e7dd", "QUALITY_B": "#fff3cd", "SYNTHETIC": "#e2e3e5"}
        tc = tier_colors.get(tier, "#333")
        tb = tier_bgs.get(tier, "#eee")
        disc_pct = int(CONF_DISCOUNT.get(tier, 0) * 100)

        st.markdown(f"""
        <div style="background:rgba({','.join(['0,0,0' if tier=='SYNTHETIC' else ('25,135,84' if tier=='QUALITY_A' else '255,193,7')].pop().split(',') + [''])};background:{tb};border:1px solid {tc}33;border-radius:8px;
                    padding:14px;text-align:center;margin-bottom:10px;">
          <div style="font-size:0.72rem;color:{tc};text-transform:uppercase;
                      letter-spacing:0.1em;margin-bottom:6px;">Row Quality Tier</div>
          <div style="font-size:1.4rem;font-weight:900;color:{tc};">{tier}</div>
          <div style="margin-top:8px;font-size:0.78rem;color:{tc};">
            {'✅ Usable for ranking' if sel.row_usable_for_ranking else '❌ Not usable'}
          </div>
          <div style="margin-top:4px;font-size:0.78rem;color:{tc};">
            Confidence discount: <strong>{disc_pct}%</strong>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Gate card
        gate_str = str(sel.l1_gate_label) if pd.notna(sel.l1_gate_label) else "NOT_AVAILABLE"
        plz_str  = str(sel.plz) if pd.notna(sel.plz) else "—"
        pass_str = f"{sel.pct_l1_gate_pass*100:.1f}%" if pd.notna(sel.pct_l1_gate_pass) else "—"
        clust    = f"{int(sel.l1_cluster_count)} clusters" if pd.notna(sel.l1_cluster_count) else "—"
        st.markdown(f"""
        <div style="background:var(--l2-bg-alt);border:1px solid var(--l2-border);border-radius:8px;padding:12px;margin-bottom:10px;">
          <div style="font-size:0.72rem;color:var(--l2-text-sub);text-transform:uppercase;
                      letter-spacing:0.08em;margin-bottom:6px;">Foundation Gate</div>
          {_gate_badge(gate_str)}
          <div style="margin-top:6px;font-size:0.8rem;color:var(--l2-text-muted);">
            PLZ {plz_str} &nbsp;|&nbsp; {clust}<br>
            <strong>{pass_str}</strong> PASS
          </div>
        </div>
        """, unsafe_allow_html=True)

        if pd.notna(sel.get("draft_rank")):
            rank_c = ["#6c5ce7","#0984e3","#00b894"]
            rc = rank_c[min(int(sel.draft_rank)-1, 2)]
            st.markdown(f"""
            <div style="background:var(--l2-bg-alt);border:1px solid var(--l2-border);border-radius:8px;
                        padding:12px;text-align:center;">
              <div style="font-size:0.72rem;color:var(--l2-text-sub);text-transform:uppercase;
                          letter-spacing:0.08em;margin-bottom:4px;">Draft Rank</div>
              <div style="font-size:1.8rem;font-weight:900;color:{rc};">#{int(sel.draft_rank)}</div>
              <div style="font-size:0.8rem;color:var(--l2-text-muted);">Score: <strong>{sel.draft_score:.4f}</strong></div>
            </div>
            """, unsafe_allow_html=True)

    # ── B · Field Detail ─────────────────────────────────
    with col_detail:
        f01_src = "osm_point_footprint_proxy_v2_utilization_rate" if tier != "QUALITY_A" else "statistical_proxy_v2_utilization_rate"
        f02_src = "osm_building_tag_proxy_v1"    if tier != "QUALITY_A" else "spatial_adjacency_v2"

        st.markdown(f"""
        <table class="l2r-field-table">
          <thead>
            <tr><th>Field</th><th>Value</th><th>Source</th><th>Confidence</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>field_01 · Roof Score (raw)</td>
              <td><strong>{_fmt(sel.roof_suitability_score)}</strong></td>
              <td style="color:#888;font-size:0.78rem;">{f01_src}</td>
              <td>{_conf_tag(sel.f01_confidence)}</td>
            </tr>
            <tr style="background:rgba(30,100,210,0.08);">
              <td>field_01 · Roof Score <span style="background:#d1e7dd;color:#0f5132;padding:1px 5px;border-radius:3px;font-size:0.72rem;font-weight:700;">NORM</span></td>
              <td><strong>{_fmt(sel.get('roof_suitability_score_norm'))}</strong>
                <span style="font-size:0.72rem;color:#888;"> [0–1]</span></td>
              <td style="color:#888;font-size:0.78rem;">min-max · REAL_GROUNDED only</td>
              <td><span style="color:#0f5132;font-size:0.75rem;">✓ used in ranking</span></td>
            </tr>
            <tr>
              <td>field_02 · SFH Share</td>
              <td><strong>{_fmt(sel.sfh_friendly_share, pct=True)}</strong></td>
              <td style="color:#888;font-size:0.78rem;">{f02_src}</td>
              <td>{_conf_tag(sel.f02_confidence)}</td>
            </tr>
            <tr>
              <td>field_02 · Dominant Form</td>
              <td><strong>{sel.dominant_form if sel.dominant_form else "—"}</strong></td>
              <td style="color:#888;font-size:0.78rem;">same as SFH share</td>
              <td>—</td>
            </tr>
            <tr>
              <td>Foundation Gate</td>
              <td>{_gate_badge(str(sel.l1_gate_label))}</td>
              <td style="color:#888;font-size:0.78rem;">PLZ proxy bridge → foundation JSON</td>
              <td><span style="color:#664d03;font-size:0.78rem;">⚠️ PLZ-level only</span></td>
            </tr>
            <tr>
              <td>field_04 · PV Coverage</td>
              <td><strong>{_fmt(sel.pv_coverage_score)}</strong></td>
              <td style="color:#888;font-size:0.78rem;">{sel.pv_source if pd.notna(sel.pv_source) else "—"}</td>
              <td>{_conf_tag(sel.pv_confidence)}</td>
            </tr>
            <tr>
              <td style="color:#aaa;font-size:0.75rem;">Build Time</td>
              <td colspan="3" style="color:#aaa;font-size:0.75rem;">{sel.build_timestamp_utc}</td>
            </tr>
          </tbody>
        </table>
        """, unsafe_allow_html=True)

        # ── D · Caveats ─────────────────────────────────
        st.markdown("<br>**Caveats**", unsafe_allow_html=True)
        if tier_caveats:
            for cv in tier_caveats:
                st.markdown(f'<div class="l2r-caveat">⚠ {cv}</div>', unsafe_allow_html=True)
        elif tier == "QUALITY_A":
            st.markdown(
                '<div class="l2r-ok">✓ No proxy patches. Polygon OSM geometry used for field_01 and field_02.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="l2r-caveat">No expansion_caveats loaded — verify segment_registry_neuss_v1.json.</div>',
                unsafe_allow_html=True,
            )

        if pd.notna(sel.l1_gate_note) and sel.l1_gate_note:
            with st.expander("Foundation gate details"):
                st.markdown(
                    f'<div style="font-size:0.8rem;color:var(--l2-text-muted);">{sel.l1_gate_note}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # ════════════════════════════════════════════════════════════════════
    # E · DRAFT Ranking Preview  +  F · Weights
    # ════════════════════════════════════════════════════════════════════
    col_rank, col_weights = st.columns([2, 1], gap="large")

    with col_rank:
        st.markdown('<div class="l2r-section">E · DRAFT Ranking Preview</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="l2r-draft-banner">⚠️ <strong>DRAFT RANKING — FOR REVIEW ONLY.</strong> '
            'Not accepted. Not final. Confidence discounting applied per quality tier. '
            'Do not use downstream without formal acceptance.</div>',
            unsafe_allow_html=True,
        )
        rank_colors = ["#6c5ce7", "#0984e3", "#00b894"]
        for _, rrow in usable.iterrows():
            r   = df[df["unit_id"] == rrow["unit_id"]].iloc[0]
            t   = r["quality_tier"]
            rc  = rank_colors[min(int(r["draft_rank"]) - 1, 2)]
            bldg_count = int(r.f02_building_count) if pd.notna(r.f02_building_count) else 0
            key_reason = (
                f"{bldg_count:,} buildings · "
                f"SFH={_fmt(r.sfh_friendly_share, pct=True)} · "
                f"Gate={r.l1_gate_label} · "
                f"PV={_fmt(r.pv_coverage_score, dec=3)}"
            )
            st.markdown(f"""
            <div class="l2r-rank-row" style="border-left-color:{rc};">
              <div style="font-size:1.4rem;font-weight:900;color:{rc};width:30px;">
                #{int(r.draft_rank)}
              </div>
              <div style="flex:1;">
                <div style="font-weight:700;">{r.unit_id}</div>
                <div style="font-size:0.76rem;color:var(--l2-text-sub);margin-top:2px;">{key_reason}</div>
              </div>
              <div>{_tier_badge(t)}</div>
              <div style="font-size:1.05rem;font-weight:700;color:{rc};min-width:60px;text-align:right;">
                {r.draft_score:.4f}
              </div>
            </div>
            """, unsafe_allow_html=True)

    with col_weights:
        st.markdown('<div class="l2r-section">F · Ranking Logic</div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="background:var(--l2-bg-alt);border:1px solid var(--l2-border);border-radius:8px;
                    padding:14px;font-size:0.82rem;">
          <div style="color:var(--l2-text-sub);font-size:0.72rem;text-transform:uppercase;
                      letter-spacing:0.08em;margin-bottom:10px;">Score = Σ (field × weight) × tier_discount</div>
        """, unsafe_allow_html=True)
        for field, weight in RANKING_WEIGHTS.items():
            pct = int(weight * 100)
            st.markdown(f"""
          <div style="margin-bottom:9px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
              <span style="color:var(--l2-text);">{field}</span>
              <strong>{pct}%</strong>
            </div>
            <div style="background:var(--l2-border);border-radius:4px;height:4px;">
              <div style="background:#6c5ce7;border-radius:4px;height:4px;width:{pct}%;"></div>
            </div>
          </div>
            """, unsafe_allow_html=True)

        st.markdown("""
          <div style="border-top:1px solid var(--l2-border);margin-top:10px;padding-top:10px;">
            <div style="color:var(--l2-text-sub);font-size:0.72rem;text-transform:uppercase;
                        letter-spacing:0.08em;margin-bottom:7px;">Tier Discount</div>
        """, unsafe_allow_html=True)
        for t_name, disc in CONF_DISCOUNT.items():
            t_colors = {"QUALITY_A":"#0f5132","QUALITY_B":"#664d03","SYNTHETIC":"#383d41"}
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
              <span style="color:{t_colors.get(t_name,'#333')};">{t_name}</span>
              <strong>× {disc:.2f}</strong>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("""
            <div style="margin-top:8px;font-size:0.72rem;color:var(--l2-text-aaa);">
              Normalization: roof_suitability_score_norm is min-max [0,1].<br>
              Status: PRODUCTION — heat modifier sign-off accepted 2026-04-10.
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ════════════════════════════════════════════════════════════════════
    # H · Priority 2 — Fernwärme / Heat Overlay (DRAFT)
    # ════════════════════════════════════════════════════════════════════
    _OVERLAY_P = _BASE_DIR / "data" / "layer2" / "layer2_prio2_heat_overlay.parquet"

    with st.expander("🔥 H · Priority 2 — Fernwärme Heat Overlay (DRAFT)", expanded=False):
        st.markdown(
            '<div class="l2r-draft-banner">⚠️ <strong>PRIORITY 2 OVERLAY — DRAFT.</strong> '
            'Negative reality-adjustment only. Not included in the formally accepted Layer 2 ranking. '
            'Modifier ×1.00 = no adjustment. Heat pump intentionally excluded from v1.</div>',
            unsafe_allow_html=True,
        )
        if not _OVERLAY_P.exists():
            st.warning(
                "Priority 2 heat overlay not found. "
                "Run `scripts/field_05_heat_modifier.py` first."
            )
        else:
            @st.cache_data(show_spinner=False)
            def _load_overlay(p: str) -> pd.DataFrame:
                return pd.read_parquet(p)

            hdf     = _load_overlay(str(_OVERLAY_P))
            usable_h = (
                hdf[hdf["row_usable_for_ranking"] == True]
                .sort_values("adjusted_score", ascending=False)
                .reset_index(drop=True)
            )

            # Data quality warning if all confidence < 0.55
            if (usable_h["heat_confidence"] < 0.55).all():
                st.markdown(
                    '<div class="l2r-caveat">⚠️ All heat assignments are desk-research grade '
                    '(confidence ≤ 0.45). No confirmed district-heat network data was '
                    'available for these PLZs. Treat adjusted scores with caution.</div>',
                    unsafe_allow_html=True,
                )

            # Heat status badge colors
            _hs_styles = {
                "STRONG_DISTRICT_HEAT":  ("#842029", "#f8d7da"),
                "PLANNED_DISTRICT_HEAT": ("#664d03", "#fff3cd"),
                "LIMITED_OR_UNCLEAR":    ("#664d03", "#fff3cd"),
                "NO_SIGNAL":             ("#0f5132", "#d1e7dd"),
                "UNKNOWN":               ("#383d41", "#e2e3e5"),
            }
            _rank_colors = ["#6c5ce7", "#0984e3", "#00b894"]
            rows_h = ""
            for i, r in usable_h.iterrows():
                hs = str(r.heat_status)
                hc, hbg = _hs_styles.get(hs, ("#333", "#f8f9fa"))
                rc = _rank_colors[min(i, 2)]
                rows_h += f"""
                <tr>
                  <td style="padding:7px 10px;font-weight:700;">
                    <span style="color:{rc};font-weight:900;">#{i+1}</span>&nbsp;{r.unit_id}
                  </td>
                  <td style="padding:7px 10px;text-align:right;">{r.base_score:.4f}</td>
                  <td style="padding:7px 10px;">
                    <span style="background:{hbg};color:{hc};padding:2px 8px;border-radius:4px;
                                 font-size:0.75rem;font-weight:700;">{hs}</span>
                  </td>
                  <td style="padding:7px 10px;text-align:center;font-weight:700;">×{r.heat_modifier:.2f}</td>
                  <td style="padding:7px 10px;text-align:right;font-weight:800;color:{rc};">{r.adjusted_score:.4f}</td>
                  <td style="padding:7px 10px;font-size:0.76rem;color:#777;">{r.prio2_interpretation}</td>
                </tr>"""

            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-size:0.84rem;
                          border:1px solid var(--l2-border);border-radius:6px;margin-bottom:10px;">
              <thead>
                <tr style="background:var(--l2-bg-alt);">
                  <th style="padding:6px 10px;text-align:left;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">Segment</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">Base Score</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">Heat Status</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;text-align:center;">Modifier</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">Adj. Score</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">Interpretation</th>
                </tr>
              </thead>
              <tbody>{rows_h}</tbody>
            </table>
            """, unsafe_allow_html=True)

            # Per-segment caveats (only for non-NO_SIGNAL rows)
            for _, r in usable_h.iterrows():
                if r.heat_status != "NO_SIGNAL":
                    st.markdown(
                        f'<div class="l2r-caveat"><strong>{r.unit_id}:</strong> {r.heat_caveat}</div>',
                        unsafe_allow_html=True,
                    )

            # Footer
            conf_val = float(usable_h["heat_confidence"].iloc[0]) if len(usable_h) > 0 else 0.0
            st.markdown(
                f'<div style="margin-top:8px;font-size:0.72rem;color:#aaa;">'
                f'Source: manual_desk_research_neuss_v1 · Confidence: {conf_val:.2f} · '
                f'Heat pump: excluded from v1 (→ Priority 2.5 / Layer 3)</div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ════════════════════════════════════════════════════════════════════
    # I · Priority 2.5 — Heat Pump ROI Uplift (DRAFT)
    # ════════════════════════════════════════════════════════════════════
    _hp_status_styles = {
        "STRONG_HP_UPLIFT":   ("#0f5132", "#d1e7dd"),
        "MODERATE_HP_UPLIFT": ("#664d03", "#fff3cd"),
        "LIMITED_HP_UPLIFT":  ("#383d41", "#e2e3e5"),
        "UNKNOWN":            ("#383d41", "#e2e3e5"),
    }

    with st.expander("🌡️ I · Priority 2.5 — Heat Pump ROI Uplift (DRAFT)", expanded=False):
        st.markdown(
            '<div class="l2r-draft-banner">⚠️ <strong>PRIORITY 2.5 — DRAFT.</strong> '
            'Positive ROI uplift modifier for PV + Heat Pump bundle narrative. '
            'Applied downstream of Layer 2 base score and Priority 2 heat overlay. '
            'Max uplift ×1.15 · Anti-double-counting gate enforced · '
            'UNKNOWN heating proxy → LIMITED tier (no uplift).</div>',
            unsafe_allow_html=True,
        )

        if not HP_UPLIFT_P.exists():
            st.warning(
                "HP uplift data not yet loaded. "
                "Run `fields/field_06_hp_uplift.py` first."
            )
        else:
            @st.cache_data(show_spinner=False)
            def _load_hp_uplift(p: str) -> pd.DataFrame:
                return pd.read_parquet(p)

            hp_df = _load_hp_uplift(str(HP_UPLIFT_P))
            usable_hp = (
                hp_df[hp_df["row_usable_for_ranking"] == True]
                .sort_values("final_score_after_hp", ascending=False)
                .reset_index(drop=True)
            )

            _rank_colors_hp = ["#6c5ce7", "#0984e3", "#00b894"]

            # ── Summary table ─────────────────────────────────────────
            rows_hp = ""
            for i, r in usable_hp.iterrows():
                hs = str(r.hp_status)
                hc, hbg = _hp_status_styles.get(hs, ("#383d41", "#e2e3e5"))
                rc = _rank_colors_hp[min(i, 2)]
                sfh_str = f"{float(r.hp_sfh_share)*100:.1f}%" if pd.notna(r.hp_sfh_share) else "—"
                proxy_str = str(r.hp_heating_proxy)
                conf_str = f"{float(r.hp_confidence):.2f}"
                rows_hp += f"""
                <tr>
                  <td style="padding:7px 10px;font-weight:700;">
                    <span style="color:{rc};font-weight:900;">#{i+1}</span>&nbsp;{r.unit_id}
                  </td>
                  <td style="padding:7px 10px;text-align:right;">{r.prio2_adjusted_score:.4f}</td>
                  <td style="padding:7px 10px;">
                    <span style="background:{hbg};color:{hc};padding:2px 8px;border-radius:4px;
                                 font-size:0.75rem;font-weight:700;">{hs}</span>
                  </td>
                  <td style="padding:7px 10px;text-align:center;font-weight:700;">×{r.hp_modifier:.2f}</td>
                  <td style="padding:7px 10px;text-align:right;font-weight:800;color:{rc};">{r.final_score_after_hp:.4f}</td>
                  <td style="padding:7px 10px;font-size:0.76rem;color:#777;">{r.hp_sales_interpretation}</td>
                </tr>"""

            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-size:0.84rem;
                          border:1px solid var(--l2-border);border-radius:6px;margin-bottom:10px;">
              <thead>
                <tr style="background:var(--l2-bg-alt);">
                  <th style="padding:6px 10px;text-align:left;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">Segment</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">P2 Score</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">HP Status</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;text-align:center;">Modifier</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">Final Score</th>
                  <th style="padding:6px 10px;color:var(--l2-text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">Interpretation</th>
                </tr>
              </thead>
              <tbody>{rows_hp}</tbody>
            </table>
            """, unsafe_allow_html=True)

            # ── Score chain per segment ───────────────────────────────
            st.markdown(
                '<div style="font-size:0.72rem;color:#888;text-transform:uppercase;'
                'letter-spacing:0.08em;margin-top:12px;margin-bottom:8px;">'
                'Score Chain  ·  Layer 2 base × P2 heat × P2.5 HP = final</div>',
                unsafe_allow_html=True,
            )
            for _, r in usable_hp.iterrows():
                hs = str(r.hp_status)
                hc, hbg = _hp_status_styles.get(hs, ("#383d41", "#e2e3e5"))
                # base_score from P2 overlay = prio2_adjusted_score / heat_modifier (approx)
                # We display prio2_adjusted_score as the P2 output and pp final
                chain_html = f"""
                <div style="background:var(--l2-bg-alt);border:1px solid var(--l2-border);border-radius:6px;
                            padding:10px 14px;margin-bottom:6px;font-size:0.82rem;">
                  <div style="font-weight:700;margin-bottom:4px;color:var(--l2-text);">{r.unit_id}</div>
                  <div style="font-family:monospace;font-size:0.80rem;color:var(--l2-text-muted);">
                    P2 adj &nbsp;&nbsp;×&nbsp; HP mod &nbsp;= final
                    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                    <strong>{r.prio2_adjusted_score:.4f}</strong>
                    &nbsp;&nbsp;×&nbsp;&nbsp;
                    <span style="background:{hbg};color:{hc};padding:1px 6px;border-radius:3px;font-weight:700;">×{r.hp_modifier:.2f}</span>
                    &nbsp;&nbsp;=&nbsp;&nbsp;
                    <strong style="color:#6c5ce7;">{r.final_score_after_hp:.4f}</strong>
                  </div>
                  <div style="margin-top:5px;font-size:0.76rem;color:#888;">gate: {r.hp_fernwaerme_gate} · proxy: {r.hp_heating_proxy} · conf: {float(r.hp_confidence):.2f}</div>"""
                if float(r.hp_confidence) < 0.55:
                    chain_html += (
                        f'<div class="l2r-caveat" style="margin-top:6px;">'
                        f'⚠️ {r.hp_caveat}</div>'
                    )
                chain_html += "</div>"
                st.markdown(chain_html, unsafe_allow_html=True)

            # Footer
            st.markdown(
                '<div style="margin-top:8px;font-size:0.72rem;color:#aaa;">'
                'Source: prio25_hp_input_v1 · Max uplift ×1.15 · '
                'Fernwärme gate derived from Priority 2 heat_status (authoritative) · '
                'UNKNOWN heating proxy → LIMITED_HP_UPLIFT (enforced in field_06_hp_uplift.py)'
                '</div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ════════════════════════════════════════════════════════════════════
    # G · Acceptance Helper
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="l2r-section">G · Acceptance Helper</div>', unsafe_allow_html=True)

    col_status, col_check = st.columns([1, 2], gap="large")

    with col_status:
        st.markdown("""
        <div style="background:#d1e7dd;border:2px solid #198754;border-radius:6px;
                    padding:12px 16px;text-align:center;color:#0f5132;">
          <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1em;
                      margin-bottom:6px;">Layer 2 Status</div>
          <div style="font-size:1.2rem;font-weight:900;">✅ ACCEPTED</div>
          <div style="margin-top:10px;font-size:0.8rem;line-height:1.6;">
            Accepted by: <strong>Di Wu</strong><br>
            Date: 2026-03-22<br>
            Scope: Controlled internal use<br>
            Ranking: PV-only DRAFT
          </div>
          <div style="margin-top:8px;font-size:0.72rem;color:#155724;">
            SUBURB &amp; GRIML: caution for external use
          </div>
        </div>
        """, unsafe_allow_html=True)

    with col_check:
        checklist = [
            ("🔍", "Inspect each REAL_GROUNDED row using the detail panel above", "#333"),
            ("📊", "Confirm quality tier assignment (A vs B) matches your confidence in the data", "#333"),
            ("⚠️", "Review all caveats for NEUSS_SUBURB_01 and NEUSS_GRIML_01 (proxy-patched rows)", "#664d03"),
            ("🎯", "Check confidence values — field_01/02 for QUALITY_B rows are 0.65–0.70 (not 0.85)", "#664d03"),
            ("🏷️",  "Check gate labels — NEUSS_GRIML_01 is MIXED (51.4%), not DEPLOYABLE", "#664d03"),
            ("📈", "Review DRAFT ranking — does the order feel directionally reasonable?", "#333"),
            ("⚖️",  "Decide whether QUALITY_B rows need additional discounting before acceptance", "#333"),
            ("✅", "Formally accept or reject Layer 2 → then Priority 2 inputs can enter", "#0f5132"),
        ]
        st.markdown("""
        <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:14px;">
          <div style="font-size:0.72rem;color:#888;text-transform:uppercase;
                      letter-spacing:0.08em;margin-bottom:10px;">Review checklist before acceptance</div>
        """, unsafe_allow_html=True)
        for icon, text, color in checklist:
            st.markdown(f"""
          <div class="l2r-checklist-item">
            <span style="font-size:1.05rem;min-width:22px;">{icon}</span>
            <span style="color:{color};">{text}</span>
          </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div style="margin-top:20px;font-size:0.72rem;color:#aaa;text-align:center;">'
        'Layer 2 Review Console · READ-ONLY · '
        'data/layer2/layer2_mvp_input_table.parquet · '
        'output/stage6/segment_registry_neuss_v1.json'
        '</div>',
        unsafe_allow_html=True,
    )
