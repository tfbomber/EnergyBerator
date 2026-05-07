"""
layer2_review_ui.py
====================
Layer 2 Internal Review UI — D-ESS / Neuss MVP
Mode: Inspection + Acceptance Decision Support

Sections:
  A. Segment Overview Table
  B. Selected Segment Detail Panel
  C. Row Quality Tier Display
  D. Caveat Panel
  E. DRAFT Ranking Preview
  F. Ranking Logic / Weights Block
  G. Acceptance Helper Checklist

Usage:
  cd d:\\Stock Analysis\\D-Energy Berater\\d-ess-engine
  streamlit run scripts/layer2_review_ui.py

Data sources (READ-ONLY):
  - data/layer2/layer2_mvp_input_table.parquet
  - output/stage6/segment_registry_neuss_v1.json
"""

import json
from pathlib import Path
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).resolve().parent.parent
PARQUET_P   = BASE_DIR / "data" / "layer2" / "layer2_mvp_input_table.parquet"
REGISTRY_P  = BASE_DIR / "output" / "stage6" / "segment_registry_neuss_v1.json"

# Draft ranking weights (explicit, visible to user)
RANKING_WEIGHTS = {
    "sfh_friendly_share":   0.30,
    "roof_suitability_score": 0.25,
    "pv_coverage_score":    0.25,
    "pct_l1_gate_pass":     0.20,
}
# Confidence discount multipliers by row quality tier
CONF_DISCOUNT = {
    "QUALITY_A": 1.00,
    "QUALITY_B": 0.85,
    "SYNTHETIC": 0.00,
}

QUALITY_TIER_MAP = {
    "NEUSS_PLZ41470":    "QUALITY_A",
    "NEUSS_PLZ41472":  "QUALITY_B",
    "NEUSS_PLZ41464":   "QUALITY_B",
    "NEUSS_CENTRAL_01": "SYNTHETIC",
    "NEUSS_OLD_TOWN_01":"SYNTHETIC",
}

TIER_COLOR = {
    "QUALITY_A": "#198754",   # green
    "QUALITY_B": "#fd7e14",   # amber
    "SYNTHETIC": "#6c757d",   # grey
}

GATE_COLOR = {
    "DEPLOYABLE":     "#198754",
    "MIXED":          "#fd7e14",
    "BLOCKED":        "#dc3545",
    "NOT_AVAILABLE":  "#6c757d",
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    df = pd.read_parquet(PARQUET_P)
    with open(REGISTRY_P, encoding="utf-8") as f:
        registry = json.load(f)

    # Build a dict of segment_id -> expansion_caveats
    caveats_map = {}
    for seg in registry.get("segments", []):
        sid = seg.get("segment_id", "")
        caveats_map[sid] = seg.get("expansion_caveats", [])

    return df, caveats_map


def compute_draft_score(row: pd.Series, tier: str) -> float | None:
    if not row.get("row_usable_for_ranking", False):
        return None
    discount = CONF_DISCOUNT.get(tier, 1.0)
    score = 0.0
    for field, weight in RANKING_WEIGHTS.items():
        val = row.get(field)
        if pd.isna(val):
            # FIX 2 (2026-04-02): NULL roof means DATA MISSING, not bad suitability.
            # Use neutral 0.5 so Grimlinghausen is not penalised for a data gap.
            # All other NULL fields remain fail-closed (0.0).
            val = 0.5 if field == "roof_suitability_score" else 0.0
        score += float(val) * weight
    return round(score * discount, 4)


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Layer 2 Review — D-ESS Neuss MVP",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0f1117; color: #e0e0e0; }
[data-testid="stHeader"] { background: #0f1117; }
.review-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.05em;
}
.badge-A  { background: #0d3b23; color: #75e09e; border: 1px solid #198754; }
.badge-B  { background: #3b2000; color: #ffd08a; border: 1px solid #fd7e14; }
.badge-S  { background: #1e1e2e; color: #9b9bbb; border: 1px solid #6c757d; }
.badge-D  { background: #0d3b23; color: #75e09e; border: 1px solid #198754; }
.badge-M  { background: #3b2000; color: #ffd08a; border: 1px solid #fd7e14; }
.badge-B2 { background: #3b0000; color: #ff9999; border: 1px solid #dc3545; }
.badge-N  { background: #1e1e2e; color: #9b9bbb; border: 1px solid #6c757d; }
.section-header {
    font-size: 0.85rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: #888;
    text-transform: uppercase;
    border-bottom: 1px solid #2a2a3e;
    padding-bottom: 4px;
    margin-bottom: 10px;
}
.caveat-box {
    background: #1a1a2e;
    border-left: 3px solid #fd7e14;
    padding: 8px 12px;
    border-radius: 0 6px 6px 0;
    margin-bottom: 6px;
    font-size: 0.83rem;
    color: #ffd08a;
}
.metric-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 8px;
}
.metric-card {
    background: #1a1a2e;
    border-radius: 6px;
    padding: 10px 14px;
    min-width: 140px;
    flex: 1;
}
.metric-label { font-size: 0.72rem; color: #888; text-transform: uppercase; letter-spacing: 0.08em; }
.metric-value { font-size: 1.15rem; font-weight: 700; color: #e0e0e0; }
.metric-sub   { font-size: 0.72rem; color: #666; }
.not-available { color: #555; font-style: italic; }
.draft-banner {
    background: #1e1a00;
    border: 1px solid #fd7e14;
    border-radius: 6px;
    padding: 8px 14px;
    color: #ffd08a;
    font-size: 0.82rem;
    margin-bottom: 12px;
}
.rank-row {
    display: flex;
    align-items: center;
    gap: 14px;
    background: #13131f;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 6px;
    border-left: 4px solid #333;
}
.rank-num { font-size: 1.5rem; font-weight: 800; width: 34px; color: #888; }
.rank-seg { font-size: 1rem; font-weight: 700; flex: 1; }
.rank-score { font-size: 1.1rem; font-weight: 700; min-width: 70px; text-align: right; }
.checklist-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 8px;
    font-size: 0.88rem;
}
.check-icon { font-size: 1.1rem; min-width: 22px; }
div[data-testid="stDataFrame"] { font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
df, caveats_map = load_data()

# Add computed columns
df["quality_tier"] = df["unit_id"].map(QUALITY_TIER_MAP).fillna("SYNTHETIC")
df["draft_score"] = df.apply(
    lambda r: compute_draft_score(r, df.loc[df["unit_id"]==r["unit_id"], "quality_tier"].iloc[0]),
    axis=1
)

# Rank usable rows
usable = df[df["row_usable_for_ranking"] == True].copy()
usable = usable.sort_values("draft_score", ascending=False).reset_index(drop=True)
usable["draft_rank"] = usable.index + 1
df = df.merge(usable[["unit_id","draft_rank"]], on="unit_id", how="left")

# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.markdown("""
<div style="background:#13131f;border-radius:8px;padding:14px 20px;margin-bottom:18px;border-left:4px solid #6c5ce7;">
  <span style="font-size:1.2rem;font-weight:800;letter-spacing:0.05em;color:#e0e0e0;">
    🔍 Layer 2 Review Console
  </span>
  <span style="margin-left:14px;font-size:0.8rem;background:#2d1b69;color:#c8b8ff;padding:3px 10px;border-radius:4px;font-weight:700;">
    EARLY_COMPARATIVE_REVIEW_READY
  </span>
  <span style="margin-left:8px;font-size:0.8rem;background:#3b0000;color:#ff9999;padding:3px 10px;border-radius:4px;font-weight:700;">
    NOT YET ACCEPTED
  </span>
  <div style="margin-top:6px;font-size:0.78rem;color:#666;">
    D-ESS Neuss MVP · Layer 2 PV-only ROI · 2026-03-22 · READ-ONLY
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SECTION A — Segment Overview Table
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">A · Segment Overview</div>', unsafe_allow_html=True)

tier_badge = {
    "QUALITY_A": '<span class="review-badge badge-A">QUALITY_A</span>',
    "QUALITY_B": '<span class="review-badge badge-B">QUALITY_B</span>',
    "SYNTHETIC": '<span class="review-badge badge-S">SYNTHETIC</span>',
}
gate_badge = {
    "DEPLOYABLE":    '<span class="review-badge badge-D">DEPLOYABLE</span>',
    "MIXED":         '<span class="review-badge badge-M">MIXED</span>',
    "BLOCKED":       '<span class="review-badge badge-B2">BLOCKED</span>',
    "NOT_AVAILABLE": '<span class="review-badge badge-N">—</span>',
}
usable_badge = {
    True:  "✅ Yes",
    False: "❌ No",
}

headers = ["Segment", "Status", "Tier", "Usable", "SFH %", "Gate", "PV Score", "Draft Rank"]
rows_html = "".join([
    f"""<tr style="{'background:#0d1a0d' if row.row_usable_for_ranking else 'background:#131320'}">
      <td style="padding:7px 10px;font-weight:700;color:#e0e0e0;">{row.unit_id}</td>
      <td style="padding:7px 10px;font-size:0.8rem;color:#aaa;">{row.unit_status}</td>
      <td style="padding:7px 10px;">{tier_badge.get(row.quality_tier,'')}</td>
      <td style="padding:7px 10px;text-align:center;">{usable_badge.get(bool(row.row_usable_for_ranking),'—')}</td>
      <td style="padding:7px 10px;text-align:right;color:#c8f7c5;">{f'{row.sfh_friendly_share*100:.1f}%' if pd.notna(row.sfh_friendly_share) else '<span class=not-available>—</span>'}</td>
      <td style="padding:7px 10px;">{gate_badge.get(str(row.l1_gate_label),'')}</td>
      <td style="padding:7px 10px;text-align:right;color:#c8f7c5;">{f'{row.pv_coverage_score:.4f}' if pd.notna(row.pv_coverage_score) else '<span class=not-available>—</span>'}</td>
      <td style="padding:7px 10px;text-align:center;font-weight:800;color:#6c5ce7;">{f'#{int(row.draft_rank)}' if pd.notna(row.draft_rank) else '—'}</td>
    </tr>"""
    for _, row in df.iterrows()
])
st.markdown(f"""
<table style="width:100%;border-collapse:collapse;border-radius:6px;overflow:hidden;font-size:0.85rem;">
  <thead>
    <tr style="background:#1a1a2e;">
      {''.join(f'<th style="padding:8px 10px;text-align:left;color:#888;font-weight:600;font-size:0.75rem;letter-spacing:0.08em;text-transform:uppercase;">{h}</th>' for h in headers)}
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SECTION B — Selected Segment Detail Panel + C Caveat Panel
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">B · Segment Detail Panel &nbsp;+&nbsp; C · Quality Tier &nbsp;+&nbsp; D · Caveats</div>', unsafe_allow_html=True)

selected_id = st.selectbox(
    "Select a segment to inspect:",
    options=df["unit_id"].tolist(),
    index=0,
    key="seg_select",
)
sel = df[df["unit_id"] == selected_id].iloc[0]
tier = sel["quality_tier"]
tier_caveats = caveats_map.get(selected_id, [])

col_tier, col_main = st.columns([1, 3], gap="large")

with col_tier:
    st.markdown(f"""
    <div style="background:#13131f;border-radius:8px;padding:14px;text-align:center;border:2px solid {TIER_COLOR.get(tier,'#333')};">
      <div style="font-size:0.72rem;color:#888;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">Row Quality Tier</div>
      <div style="font-size:1.5rem;font-weight:900;color:{TIER_COLOR.get(tier,'#666')};">{tier}</div>
      <div style="margin-top:10px;font-size:0.78rem;color:#888;">
        {'✅ Usable for ranking' if sel.row_usable_for_ranking else '❌ Not usable for ranking'}
      </div>
      <div style="margin-top:6px;font-size:0.78rem;color:#888;">
        Confidence discount: <strong style="color:#e0e0e0;">{CONF_DISCOUNT.get(tier,0)*100:.0f}%</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")
    st.markdown(f"""
    <div style="background:#13131f;border-radius:8px;padding:12px;border:1px solid #2a2a3e;">
      <div style="font-size:0.72rem;color:#888;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">Gate Status</div>
      <div>{gate_badge.get(str(sel.l1_gate_label),'')}</div>
      <div style="margin-top:6px;font-size:0.8rem;color:#aaa;">
        PLZ {sel.plz if pd.notna(sel.plz) else '—'} &nbsp;|&nbsp;
        {f"{sel.l1_cluster_count:.0f} clusters" if pd.notna(sel.l1_cluster_count) else '—'}
      </div>
      <div style="margin-top:4px;font-size:0.8rem;color:#aacc88;">
        {f"{sel.pct_l1_gate_pass*100:.1f}% PASS" if pd.notna(sel.pct_l1_gate_pass) else '—'}
      </div>
    </div>
    """, unsafe_allow_html=True)

    if sel.draft_rank and pd.notna(sel.draft_rank):
        st.markdown(f"""
        <div style="background:#13131f;border-radius:8px;padding:12px;border:1px solid #2a2a3e;margin-top:8px;text-align:center;">
          <div style="font-size:0.72rem;color:#888;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Draft Rank</div>
          <div style="font-size:2rem;font-weight:900;color:#6c5ce7;">#{int(sel.draft_rank)}</div>
          <div style="font-size:0.8rem;color:#888;">Score: <strong>{sel.draft_score:.4f}</strong></div>
        </div>
        """, unsafe_allow_html=True)

with col_main:
    # --- Field values ---
    st.markdown("**Field Input Values**")

    def fmt(val, decimals=4, pct=False):
        if pd.isna(val): return '<span class="not-available">NULL</span>'
        if pct: return f"{float(val)*100:.1f}%"
        return f"{float(val):.{decimals}f}"

    def conf_tag(conf):
        if pd.isna(conf): return ""
        c = float(conf)
        color = "#75e09e" if c >= 0.80 else "#ffd08a" if c >= 0.60 else "#ff9999"
        return f'<span style="font-size:0.72rem;color:{color};margin-left:6px;">conf={c:.2f}</span>'

    st.markdown(f"""
    <div style="background:#13131f;border-radius:8px;padding:14px;border:1px solid #2a2a3e;margin-bottom:10px;">
      <table style="width:100%;border-collapse:collapse;font-size:0.83rem;">
        <thead>
          <tr style="color:#666;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;">
            <th style="padding:4px 8px;text-align:left;">Field</th>
            <th style="padding:4px 8px;text-align:left;">Value</th>
            <th style="padding:4px 8px;text-align:left;">Source</th>
            <th style="padding:4px 8px;text-align:left;">Confidence</th>
          </tr>
        </thead>
        <tbody>
          <tr style="border-top:1px solid #2a2a3e;">
            <td style="padding:6px 8px;color:#aaa;">field_01 · Roof Score</td>
            <td style="padding:6px 8px;font-weight:700;color:#c8f7c5;">{fmt(sel.roof_suitability_score)}</td>
            <td style="padding:6px 8px;color:#888;font-size:0.78rem;">{'osm_point_footprint_proxy_v1' if sel.quality_tier!='QUALITY_A' else 'statistical_proxy_v1'}</td>
            <td style="padding:6px 8px;">{conf_tag(sel.f01_confidence)}</td>
          </tr>
          <tr style="border-top:1px solid #2a2a3e;">
            <td style="padding:6px 8px;color:#aaa;">field_02 · SFH Share</td>
            <td style="padding:6px 8px;font-weight:700;color:#c8f7c5;">{fmt(sel.sfh_friendly_share, pct=True)}</td>
            <td style="padding:6px 8px;color:#888;font-size:0.78rem;">{'osm_building_tag_proxy_v1' if sel.quality_tier!='QUALITY_A' else 'spatial_adjacency_v2'}</td>
            <td style="padding:6px 8px;">{conf_tag(sel.f02_confidence)}</td>
          </tr>
          <tr style="border-top:1px solid #2a2a3e;">
            <td style="padding:6px 8px;color:#aaa;">field_02 · Dominant Form</td>
            <td style="padding:6px 8px;font-weight:700;color:#c8f7c5;">{sel.dominant_form if sel.dominant_form else '<span class="not-available">—</span>'}</td>
            <td style="padding:6px 8px;color:#888;font-size:0.78rem;">same as SFH share</td>
            <td style="padding:6px 8px;">—</td>
          </tr>
          <tr style="border-top:1px solid #2a2a3e;">
            <td style="padding:6px 8px;color:#aaa;">Foundation Gate</td>
            <td style="padding:6px 8px;font-weight:700;">{gate_badge.get(str(sel.l1_gate_label),'—')}</td>
            <td style="padding:6px 8px;color:#888;font-size:0.78rem;">PLZ proxy bridge → foundation JSON</td>
            <td style="padding:6px 8px;"><span style="font-size:0.72rem;color:#ffd08a;">⚠️ PLZ-level only</span></td>
          </tr>
          <tr style="border-top:1px solid #2a2a3e;">
            <td style="padding:6px 8px;color:#aaa;">field_04 · PV Coverage</td>
            <td style="padding:6px 8px;font-weight:700;color:#c8f7c5;">{fmt(sel.pv_coverage_score)}</td>
            <td style="padding:6px 8px;color:#888;font-size:0.78rem;">{sel.pv_source if pd.notna(sel.pv_source) else '—'}</td>
            <td style="padding:6px 8px;">{conf_tag(sel.pv_confidence)}</td>
          </tr>
          <tr style="border-top:1px solid #2a2a3e;">
            <td style="padding:6px 8px;color:#aaa;">Build Time</td>
            <td colspan="3" style="padding:6px 8px;color:#555;font-size:0.75rem;">{sel.build_timestamp_utc}</td>
          </tr>
        </tbody>
      </table>
    </div>
    """, unsafe_allow_html=True)

    # --- CAVEATS ---
    st.markdown("**Caveats for this segment**")
    if tier_caveats:
        for cv in tier_caveats:
            st.markdown(f'<div class="caveat-box">⚠ {cv}</div>', unsafe_allow_html=True)
    elif tier == "QUALITY_A":
        st.markdown('<div style="background:#0d1a0d;border-left:3px solid #198754;padding:8px 12px;border-radius:0 6px 6px 0;font-size:0.83rem;color:#75e09e;">✓ No proxy patches. Polygon OSM geometry used for field_01 and field_02 spatial adjacency.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="caveat-box">No expansion caveats loaded — verify segment_registry_neuss_v1.json.</div>', unsafe_allow_html=True)

    # Foundation gate note
    if pd.notna(sel.l1_gate_note) and sel.l1_gate_note:
        with st.expander("Foundation gate detail note"):
            st.markdown(f'<div style="font-size:0.8rem;color:#aaa;">{sel.l1_gate_note}</div>', unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# SECTION E + F — DRAFT Ranking Preview + Weights Block
# ---------------------------------------------------------------------------
left_col, right_col = st.columns([2, 1], gap="large")

with left_col:
    st.markdown('<div class="section-header">E · DRAFT Ranking Preview</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="draft-banner">
      ⚠️ &nbsp;<strong>DRAFT RANKING — FOR REVIEW ONLY.</strong>
      Not accepted. Not final. Confidence discounting applied per quality tier.
      Do not use downstream without formal acceptance.
    </div>
    """, unsafe_allow_html=True)

    rank_colors = ["#6c5ce7", "#0984e3", "#00b894"]
    for _, rrow in usable.iterrows():
        r = df[df["unit_id"] == rrow["unit_id"]].iloc[0]
        t = r["quality_tier"]
        rc = rank_colors[min(int(r["draft_rank"])-1, 2)]
        pv_str    = f"{r.pv_coverage_score:.3f}" if pd.notna(r.pv_coverage_score) else "—"
        sfh_str   = f"{r.sfh_friendly_share*100:.0f}%" if pd.notna(r.sfh_friendly_share) else "—"
        gate_str  = str(r.l1_gate_label)
        score_str = f"{r.draft_score:.4f}" if pd.notna(r.draft_score) else "—"
        key_reason = f"SFH={sfh_str}, Gate={gate_str}, PV={pv_str}"
        badge = tier_badge.get(t, "")

        st.markdown(f"""
        <div class="rank-row" style="border-left-color:{rc};">
          <div class="rank-num" style="color:{rc};">#{int(r.draft_rank)}</div>
          <div style="flex:1;">
            <div class="rank-seg">{r.unit_id}</div>
            <div style="font-size:0.77rem;color:#888;margin-top:2px;">{key_reason}</div>
          </div>
          <div>{badge}</div>
          <div class="rank-score" style="color:{rc};">{score_str}</div>
        </div>
        """, unsafe_allow_html=True)

with right_col:
    st.markdown('<div class="section-header">F · Ranking Logic</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="background:#13131f;border-radius:8px;padding:14px;border:1px solid #2a2a3e;font-size:0.82rem;">
      <div style="color:#888;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">Score Formula</div>
    """, unsafe_allow_html=True)

    for field, weight in RANKING_WEIGHTS.items():
        bar_w = int(weight * 100)
        st.markdown(f"""
      <div style="margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
          <span style="color:#aaa;">{field}</span>
          <span style="color:#e0e0e0;font-weight:700;">{weight*100:.0f}%</span>
        </div>
        <div style="background:#2a2a3e;border-radius:4px;height:5px;">
          <div style="background:#6c5ce7;border-radius:4px;height:5px;width:{bar_w}%;"></div>
        </div>
      </div>
        """, unsafe_allow_html=True)

    st.markdown("""
      <div style="border-top:1px solid #2a2a3e;margin-top:10px;padding-top:10px;">
        <div style="color:#888;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Confidence Discounting</div>
    """, unsafe_allow_html=True)

    for tier_name, discount in CONF_DISCOUNT.items():
        color = TIER_COLOR.get(tier_name, "#666")
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;margin-bottom:5px;">
          <span style="color:{color};">{tier_name}</span>
          <span style="color:#e0e0e0;font-weight:700;">× {discount:.2f}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
        <div style="margin-top:8px;font-size:0.72rem;color:#555;">
          Score = weighted_sum × tier_discount<br>
          Normalization: none (raw field values)<br>
          Status: DRAFT — weights not formally accepted
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# SECTION G — Acceptance Helper
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">G · Acceptance Helper</div>', unsafe_allow_html=True)

col_status, col_check = st.columns([1, 2], gap="large")

with col_status:
    st.markdown("""
    <div style="background:#1a0000;border:2px solid #dc3545;border-radius:8px;padding:16px;text-align:center;">
      <div style="font-size:0.72rem;color:#888;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">Current Layer 2 Status</div>
      <div style="font-size:1.2rem;font-weight:900;color:#ff6b6b;">NOT YET ACCEPTED</div>
      <div style="margin-top:10px;font-size:0.8rem;color:#888;">
        3 real rows usable<br>
        2 synthetic rows blocked<br>
        Ranking: DRAFT only<br>
        Priority 2 inputs: not yet integrated
      </div>
    </div>
    """, unsafe_allow_html=True)

with col_check:
    checklist = [
        ("🔍", "Inspect each REAL_GROUNDED row individually (use panel above)", "#aaa"),
        ("📊", "Confirm quality tier assignment (A vs B) reflects your confidence in the data sources", "#aaa"),
        ("⚠️", "Review all caveats for NEUSS_PLZ41472 and NEUSS_PLZ41464 (proxy-patched rows)", "#ffd08a"),
        ("🎯", "Inspect confidence values — field_01 / field_02 for QUALITY_B rows are 0.65–0.70, not 0.85", "#ffd08a"),
        ("🏷️",  "Inspect Gate labels — NEUSS_PLZ41464 is MIXED (51%), not DEPLOYABLE", "#ffd08a"),
        ("📈", "Review the DRAFT ranking — does the result feel directionally reasonable?", "#aaa"),
        ("⚖️", "Decide whether QUALITY_B rows need additional confidence discounting before acceptance", "#aaa"),
        ("✅", "Formally accept or reject Layer 2 — then Priority 2 inputs can enter", "#75e09e"),
    ]
    st.markdown("""
    <div style="background:#13131f;border-radius:8px;padding:14px;border:1px solid #2a2a3e;">
      <div style="font-size:0.72rem;color:#888;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px;">Review checklist before acceptance</div>
    """, unsafe_allow_html=True)
    for icon, text, color in checklist:
        st.markdown(f"""
      <div class="checklist-item">
        <span class="check-icon">{icon}</span>
        <span style="color:{color};">{text}</span>
      </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# Footer
st.markdown("""
<div style="margin-top:24px;padding:10px 14px;background:#0a0a12;border-radius:6px;font-size:0.72rem;color:#444;text-align:center;">
  D-ESS Layer 2 Review UI · READ-ONLY · Data: data/layer2/layer2_mvp_input_table.parquet · 
  Registry: output/stage6/segment_registry_neuss_v1.json · Not for external use.
</div>
""", unsafe_allow_html=True)
