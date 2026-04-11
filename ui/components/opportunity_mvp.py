import streamlit as st
import pandas as pd
import json
import os

from core.boundary_filter import (
    filter_clusters_to_neuss,
    STATUS_OK,
    STATUS_FAIL_CLOSED,
)
from core.purity_gate_loader import (
    load_purity_config,
    apply_purity_gate_overlay,
    get_purity_audit_df,
)
from core.top10_hardener import (
    apply_top10_hardening,
    get_narrative,
)

# ─────────────────────────────────────────────
# UI-ONLY DIMENSION DERIVATION (NO SCORE CHANGE)
# ─────────────────────────────────────────────

def _derive_structure_label(sfh_abs):
    """Derive Structure label from sfh_absolute_count."""
    try:
        n = int(sfh_abs or 0)
        if n >= 80: return "Strong"
        if n >= 30: return "Medium"
        return "Weak"
    except Exception:
        return "Unknown"

def _derive_purity_label(purity_flag, purity_score_final=None):
    """Derive Purity label from purity_flag and purity_score_final."""
    flag = str(purity_flag or "")
    if flag == "DOWNGRADED":
        return "Downgraded"
    try:
        ps = float(purity_score_final) if purity_score_final is not None else None
        if ps is not None and ps >= 0.75:
            return "Clean"
        if ps is not None and ps >= 0.55:
            return "Mixed"
    except Exception:
        pass
    if flag in ("UNCHANGED", "RETAINED"):
        return "Clean"
    if flag == "NOT_APPLICABLE":
        return "Mixed"
    return "Unknown"

def _derive_scale_label(volume_band):
    """Derive Scale label from deployable_volume_band."""
    vb = str(volume_band or "")
    if vb == "XL": return "Large"
    if vb == "L":  return "Medium-Large"
    if vb == "M":  return "Medium"
    return "Small"

def _derive_general_status(score, purity_flag, volume_band):
    """Derive General Status tag from score + purity + scale."""
    s = float(score or 0)
    flag = str(purity_flag or "")
    vb = str(volume_band or "")
    if s >= 0.60 and flag != "DOWNGRADED" and vb in ("L", "XL"):
        return "STRONG_GENERAL_CANDIDATE"
    if s >= 0.40:
        return "REVIEW_GENERAL_CANDIDATE"
    return "WEAK_GENERAL_CANDIDATE"

def _derive_main_friction(purity_flag, sfh_abs, volume_band, purity_score_final=None):
    """Derive the single most significant constraint for each cluster."""
    flag = str(purity_flag or "")
    n = int(sfh_abs or 0)
    vb = str(volume_band or "")
    # Priority order of friction signals
    if flag == "DOWNGRADED":
        return "Mixed-density surroundings reduce field efficiency"
    try:
        ps = float(purity_score_final) if purity_score_final is not None else None
        if ps is not None and ps < 0.55:
            return "High MFH pressure in surrounding context"
    except Exception:
        pass
    if n < 25:
        return "Weak residential structure — limited SFH footprint"
    if vb == "S":
        return "Small cluster size limits deployment priority"
    return "No major structural constraints identified"

def _derive_structured_reasons(structure_label, purity_label, sfh_abs, volume_band, lead_count):
    """Return 3-line structured reasons (Structure / Purity / Scale)."""
    n = int(sfh_abs or 0)
    lc = int(lead_count or 0)
    vb = str(volume_band or "")

    if structure_label == "Strong":
        r1 = f"Strong single-family housing presence — {n} SFH-dominant properties across the cluster"
    elif structure_label == "Medium":
        r1 = f"Moderate residential structure with {n} SFH-type properties identified"
    else:
        r1 = f"Limited single-family housing signal — {n} SFH units detected, structural risk elevated"

    if purity_label == "Clean":
        r2 = "Clean surrounding context with low MFH interference — door-to-door efficiency preserved"
    elif purity_label == "Downgraded":
        r2 = "Mixed-density surroundings introduce outreach friction — experienced reps preferred"
    else:
        r2 = "Mixed-density context — partial MFH pressure present, conversion rates may vary"

    if vb in ("XL", "L"):
        r2_scale = "large"
    elif vb == "M":
        r2_scale = "medium"
    else:
        r2_scale = "small"
    r3 = f"{lc} deployable target properties in a {r2_scale}-scale cluster — field deployment {('highly efficient' if vb in ('XL','L') else 'viable' if vb == 'M' else 'selective')}"

    return r1, r2, r3

def _summary_line(structure_label, purity_label, scale_label):
    return f"{structure_label} structure · {purity_label} context · {scale_label} scale"

# ─────────────────────────────────────────────


def render_opportunity_mvp():
    st.title("📍 Territory Opportunity Radar (Neuss)")
    st.info("💡 **Note:** This radar evaluates territory suitability at the street-cluster level across 3 dimensions: **Structure · Purity · Scale**. It is designed for **territory prioritization**, not deterministic individual household qualification.")
    st.caption("Aggregated street-level deployment intelligence. Structurally independent from single-case pipelines.")
    st.divider()

    # --- Data Paths ---
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cluster_file = os.path.join(base_dir, "output", "clusters", "neuss_hybrid_clusters_v1.json")
    explainer_file = os.path.join(base_dir, "output", "stage6", "stage6_segment_explainer.csv")

    if not os.path.exists(cluster_file) or not os.path.exists(explainer_file):
        st.error("Missing required offline data artifacts in /output/")
        st.code(f"Expected:\n- {cluster_file}\n- {explainer_file}")
        return

    # --- 1. Load Cluster JSON ---
    try:
        with open(cluster_file, 'r', encoding='utf-8') as f:
            clusters_raw = json.load(f)
        if isinstance(clusters_raw, list):
            cluster_list = clusters_raw
        elif isinstance(clusters_raw, dict):
            cluster_list = clusters_raw.get("clusters", [])
        else:
            st.error(f"Unexpected JSON root type: {type(clusters_raw)}")
            return
    except Exception as e:
        st.error(f"Failed to load clusters JSON: {e}")
        return

    # --- 1b. BOUNDARY FILTER ---
    filter_result = filter_clusters_to_neuss(
        cluster_list,
        source_file=cluster_file,
    )
    if filter_result["boundary_status"] != STATUS_OK:
        st.error(
            "⛔ **Boundary integrity check FAILED.** "
            "The Neuss admin polygon could not be loaded. "
            "No territory radar output will be shown to prevent unverified data from reaching the UI."
        )
        st.info(
            f"Missing file: `config/boundaries/neuss_admin_boundary.geojson`\n\n"
            "Place the Neuss GeoJSON boundary file in the path above and restart the app."
        )
        return

    cluster_list = filter_result["kept"]
    _rejected_count   = filter_result["meta"]["rejected_count"]
    _total_input      = filter_result["meta"]["total_input"]
    _boundary_method  = filter_result["meta"]["boundary_method"]

    with st.expander("🛡️ Territory Integrity Audit", expanded=False):
        st.markdown("**Data Provenance Pipeline: LIVE**")
        st.markdown(f"- **Raw Input Clusters:** `{_total_input}`")
        st.markdown(f"- **Mathematical Boundary Enforced:** `{_boundary_method}`")
        st.markdown(f"- **Out-of-Bounds Rejections:** `{_rejected_count}`")
        st.markdown(f"- **Final Verified Neuss Clusters:** `{len(cluster_list)}`")
        if _rejected_count > 0:
            st.success("Spatial guardrail active: Neighboring city boundaries successfully intercepted.")
        else:
            st.success("100% Geometry Compliance. 0 leakage detected.")

    if not cluster_list:
        st.warning(
            f"⚠️ All {_total_input} clusters were outside the Neuss boundary after filtering. "
            "Nothing to display — check the boundary polygon and source data."
        )
        return

    df_clusters = pd.DataFrame(cluster_list)

    # --- 2. Load Explainer CSV ---
    try:
        df_exp = pd.read_csv(explainer_file)
    except Exception as e:
        st.error(f"Failed to load stage6 CSV: {e}")
        return

    # --- 3. Validate required cluster columns ---
    required_cols = {"cluster_id", "segment_id", "primary_street", "house_range", "lead_count"}
    missing = required_cols - set(df_clusters.columns)
    if missing:
        st.error(f"Cluster JSON missing expected columns: {missing}")
        st.write("Actual columns found:", list(df_clusters.columns))
        return

    # --- 4. Rename to display-friendly labels ---
    df_clusters = df_clusters.rename(columns={
        "cluster_id":     "Cluster ID",
        "primary_street": "Street",
        "house_range":    "House Range",
        "lead_count":     "Lead Count",
    })

    # --- 5. Join Explainer on segment_id ---
    df_joined = pd.merge(
        df_clusters,
        df_exp,
        on="segment_id",
        how="left"
    )

    # --- 5b. Purity Gate Overlay (non-destructive) ---
    _purity_cfg = load_purity_config(base_dir)
    df_joined = apply_purity_gate_overlay(df_joined, base_dir, cfg=_purity_cfg)

    # --- 6. Opportunity Score (unchanged from original) ---
    if "opportunity_score" in df_joined.columns:
        df_joined["_seg_score"] = pd.to_numeric(df_joined["opportunity_score"], errors="coerce").fillna(0.0)
    else:
        df_joined["_seg_score"] = 0.0

    if "A_count" in df_joined.columns:
        a_count = pd.to_numeric(df_joined["A_count"], errors="coerce").fillna(0)
    else:
        a_count = pd.Series(0.0, index=df_joined.index)

    if "Lead Count" in df_joined.columns:
        lead_count_raw = pd.to_numeric(df_joined["Lead Count"], errors="coerce").fillna(1)
        lead_count_safe = lead_count_raw.clip(lower=1)
    else:
        lead_count_safe = pd.Series(1.0, index=df_joined.index)

    lead_quality_ratio = (a_count / lead_count_safe).clip(0.0, 1.0)
    df_joined["Opportunity Score"] = (
        df_joined["_seg_score"] * 0.5 + lead_quality_ratio * 0.5
    ).round(4)

    if "social_proof_level" in df_joined.columns:
        df_joined["Confidence"] = df_joined["social_proof_level"]
    else:
        df_joined["Confidence"] = "N/A"

    if "primary_driver" in df_joined.columns:
        df_joined["Top Reasons"] = df_joined["primary_driver"]
    else:
        df_joined["Top Reasons"] = "N/A"

    # --- 7. Recommended Action (unchanged) ---
    def get_action(score):
        try:
            s = float(score)
            if s >= 0.6:  return "🔥 Fast-Track Field Sales"
            elif s >= 0.4: return "✉️ Targeted Mail Campaign"
            else:          return "⏸️ Hold for D-ESS Qualification"
        except Exception:
            return "Needs Evaluation"

    df_joined["Recommended Action"] = df_joined["Opportunity Score"].apply(get_action)

    # --- 7b. Top 10 Hardening Overlay ---
    df_joined = apply_top10_hardening(df_joined, base_dir)

    # -----------------------------------------------------------
    # UI PATCH: Derive 3-Dimension Labels (display only, no score)
    # -----------------------------------------------------------
    df_joined["Structure"] = df_joined["sfh_absolute_count"].apply(_derive_structure_label)
    df_joined["Purity"]    = df_joined.apply(
        lambda r: _derive_purity_label(r.get("purity_flag"), r.get("purity_score_final")), axis=1
    )
    df_joined["Scale"]     = df_joined["deployable_volume_band"].apply(_derive_scale_label)
    df_joined["Status"]    = df_joined.apply(
        lambda r: _derive_general_status(r.get("Opportunity Score", 0), r.get("purity_flag"), r.get("deployable_volume_band")), axis=1
    )
    df_joined["Main Friction"] = df_joined.apply(
        lambda r: _derive_main_friction(r.get("purity_flag"), r.get("sfh_absolute_count"), r.get("deployable_volume_band"), r.get("purity_score_final")), axis=1
    )
    df_joined["Summary"] = df_joined.apply(
        lambda r: _summary_line(r["Structure"], r["Purity"], r["Scale"]), axis=1
    )
    # -----------------------------------------------------------

    # --- 8. Summary Metrics Row ---
    st.markdown("### 🗺️ Territory Suitability Matrix")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Evaluated Clusters", len(df_joined))
    c2.metric("Total Target Properties", int(df_joined["Lead Count"].sum()) if "Lead Count" in df_joined else 0)
    strong_count = int((df_joined["Status"] == "STRONG_GENERAL_CANDIDATE").sum())
    c3.metric("⭐ Strong Candidates", strong_count)
    avg_score = df_joined["Opportunity Score"].mean()
    c4.metric("Avg Territory Score", f"{avg_score:.2f}" if pd.notna(avg_score) else "N/A")

    st.divider()

    # --- 9. Filtering ---
    st.markdown("### 🎛️ Territory Filters")
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        action_filter = st.multiselect("Filter by Action", df_joined["Recommended Action"].unique())
    with f_col2:
        structure_filter = st.multiselect("Filter by Structure", ["Strong", "Medium", "Weak"])
    with f_col3:
        purity_filter = st.multiselect("Filter by Purity", ["Clean", "Mixed", "Downgraded"])

    # Table columns (decision-oriented, A_count demoted)
    view_cols = [
        "rank_position", "Cluster ID", "Street", "PLZ", "House Range",
        "Lead Count", "Scale", "Structure", "Purity", "Status",
        "Summary", "Main Friction", "display_score_precise", "Recommended Action"
    ]
    final_cols = [c for c in view_cols if c in df_joined.columns]

    df_filtered = df_joined.copy()
    if action_filter:
        df_filtered = df_filtered[df_filtered["Recommended Action"].isin(action_filter)]
    if structure_filter:
        df_filtered = df_filtered[df_filtered["Structure"].isin(structure_filter)]
    if purity_filter:
        df_filtered = df_filtered[df_filtered["Purity"].isin(purity_filter)]

    _sort_cols = [c for c in ["display_score_precise", "tie_break_score"] if c in df_filtered.columns]
    if _sort_cols:
        df_sorted = df_filtered.sort_values(_sort_cols, ascending=[False] * len(_sort_cols), na_position="last")
    else:
        df_sorted = df_filtered.sort_values("Opportunity Score", ascending=False, na_position="last")
    df_display = df_sorted[[c for c in final_cols if c in df_sorted.columns]]

    # --- 10. Top 10 Table ---
    st.markdown("### 🎯 Top 10 Priority Areas")
    st.caption("Ranked by combined structural suitability, purity, and scale.")

    def _status_style(val):
        if "STRONG" in str(val): return "color:#155724; background-color:#d4edda; font-weight:bold"
        if "REVIEW" in str(val): return "color:#856404; background-color:#fff3cd"
        if "WEAK"   in str(val): return "color:#721c24; background-color:#f8d7da"
        return ""

    def _structure_style(val):
        if val == "Strong": return "color:#155724; font-weight:bold"
        if val == "Weak":   return "color:#721c24"
        return ""

    def _purity_style(val):
        if val == "Clean":      return "color:#155724"
        if val == "Downgraded": return "color:#721c24; font-style:italic"
        return ""

    top_10_df = df_display.head(10)
    styled = top_10_df.style \
        .map(_status_style, subset=["Status"] if "Status" in top_10_df.columns else []) \
        .map(_structure_style, subset=["Structure"] if "Structure" in top_10_df.columns else []) \
        .map(_purity_style, subset=["Purity"] if "Purity" in top_10_df.columns else [])

    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.divider()

    # --- 11. Full Backlog ---
    with st.expander("📂 View Full Territory Backlog"):
        st.dataframe(df_display.style.map(_status_style, subset=["Status"] if "Status" in df_display.columns else []),
                     use_container_width=True, hide_index=True)

        if _purity_cfg.get("enable_purity_gate", True):
            _audit_df = get_purity_audit_df(df_joined)
            if not _audit_df.empty:
                _n_down = (_audit_df["purity_flag"] == "DOWNGRADED").sum() if "purity_flag" in _audit_df.columns else 0
                with st.expander(f"🔬 Purity Gate Audit View — {_n_down} clusters downgraded (T={_purity_cfg.get('purity_threshold', 0.55)})", expanded=False):
                    st.caption("Non-destructive contextual overlay. Original labels and ranking are unchanged.")
                    st.dataframe(_audit_df.reset_index(drop=True), use_container_width=True, hide_index=True)

    st.divider()

    # --- 12. Cluster Detail Cards (decision-oriented) ---
    st.markdown("### 🔍 Area Intelligence Cards")
    st.caption("Deep-dive into each top candidate's suitability profile.")

    for _, row in df_joined.sort_values(
        [c for c in ["display_score_precise", "tie_break_score"] if c in df_joined.columns],
        ascending=False, na_position="last"
    ).head(10).iterrows():

        cluster_id  = row.get("Cluster ID",            "Unknown")
        street      = row.get("Street",                "Unknown")
        score       = row.get("display_score_precise", row.get("Opportunity Score", 0.0))
        action      = row.get("Recommended Action",    "N/A")
        lead_count  = row.get("Lead Count",            0)
        rank_pos    = row.get("rank_position",         "?")
        a_count     = int(row.get("A_count", 0) or 0)
        vband       = row.get("deployable_volume_band","?")
        plz         = row.get("PLZ",                   "UNKNOWN")
        sfh_abs     = row.get("sfh_absolute_count",    0)
        purity_flag = row.get("purity_flag",           "N/A")
        purity_score= row.get("purity_score_final",    None)

        structure_lbl = row.get("Structure", _derive_structure_label(sfh_abs))
        purity_lbl    = row.get("Purity",    _derive_purity_label(purity_flag, purity_score))
        scale_lbl     = row.get("Scale",     _derive_scale_label(vband))
        status_tag    = row.get("Status",    "REVIEW_GENERAL_CANDIDATE")
        main_friction = row.get("Main Friction", "")
        summary       = row.get("Summary",   "")
        audit_flag    = row.get("consistency_audit_flag", "OK")
        tie_expl      = row.get("tie_break_explanation", "")

        r1, r2, r3 = _derive_structured_reasons(structure_lbl, purity_lbl, sfh_abs, vband, lead_count)

        # Status badge color
        if "STRONG" in status_tag:   badge = "🟢"
        elif "REVIEW" in status_tag: badge = "🟡"
        else:                        badge = "🔴"

        with st.expander(f"#{rank_pos}  {badge}  **{cluster_id}** — {street} | Score: {score:.4f} | {scale_lbl}"):

            # ── Status + 3 Dimension Tiles ──
            st.markdown(f"#### Territory Status: `{status_tag}`")
            col_s, col_p, col_sc = st.columns(3)
            col_s.metric("🏗️ Structure",  structure_lbl)
            col_p.metric("🧭 Purity",     purity_lbl)
            col_sc.metric("📦 Scale",     scale_lbl)

            st.divider()

            # ── Why this area ──
            st.markdown("#### ✅ Why This Area Is Good")
            st.markdown(f"1. {r1}")
            st.markdown(f"2. {r2}")
            st.markdown(f"3. {r3}")

            # ── Main Friction ──
            if main_friction and "No major" not in main_friction:
                st.warning(f"⚠️ **Main Constraint:** {main_friction}")

            st.divider()

            # ── Execution Frame ──
            st.markdown("#### ⚡ Deployment Decision")
            ec1, ec2, ec3, ec4 = st.columns(4)
            clean_action = action.split(" ", 1)[-1] if " " in action else action
            ec1.metric("Action",    clean_action)
            ec2.metric("Leads",     lead_count)
            ec3.metric("PLZ",       plz)
            ec4.metric("Summary",   summary)

            if "Fast-Track" in str(action):
                st.success("**P0 — Immediate field dispatch recommended.** Route-optimise reps to cover this cluster first.")
            elif "Mail" in str(action):
                st.info("**P1 — Direct mail + digital retargeting.** Follow up with field visit if response rate exceeds 15%.")
            else:
                st.error("**P2 — Hold.** Await additional qualification before deploying field resources.")

            # ── Purity Badge ──
            if _purity_cfg.get("enable_purity_gate", True) and _purity_cfg.get("purity_show_explainer_note", True):
                if purity_flag == "DOWNGRADED":
                    st.warning(
                        "⚠️ **Purity Context Note:** "
                        + str(row.get("purity_reason_short",
                            "Mixed-density surroundings detected. Door-to-door efficiency may be reduced."))
                    )

            # ── Secondary / Debug Section (A_count demoted here) ──
            with st.expander("🔍 Signal Details & Ranking Debug", expanded=False):
                st.caption(f"A-grade leads: {a_count} / {lead_count}  |  A-rate: {a_count/max(int(lead_count),1):.0%}")
                st.caption(f"Volume Band: {vband}  |  SFH Count: {sfh_abs}")
                if purity_score is not None:
                    st.caption(f"Purity Score: {purity_score:.4f}  |  Purity Flag: {purity_flag}")
                st.caption(tie_expl)
                if audit_flag not in ("OK", ""):
                    st.warning(f"⚠️ Consistency Flag: `{audit_flag}`")
