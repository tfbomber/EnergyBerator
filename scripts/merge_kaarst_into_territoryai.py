"""
merge_kaarst_into_territoryai.py
====================================
Kaarst D3: re-syncs Kaarst's segment row (street_ranking_v1.parquet) and
413 street rows (street_level_ranking_v1.parquet) using field_01_roof_potential.py's
now-fixed utilization_factors (Stage1/2 label vocabulary instead of raw OSM
tags — the same fix D2 applied to Augsburg). Also carries forward the
already-in-progress "Grosser/Großer Mühlenweg" cluster consolidation found
sitting uncommitted in this repo's foundation JSON (3 duplicate/spelling-
variant clusters -> 1 clean 37-building QUALIFIED cluster) — confirmed via
residual analysis to be the ONLY other change versus the shipped baseline
(411/413 other streets match a pure dampened field_01-shift formula to
within 0.0001 rounding noise).

Source: scripts/build_kaarst_layer2.py's fresh output
  (data/layer2/kaarst_layer2_input_table.parquet, kaarst_street_level_ranking_v1.parquet)

APPROXIMATION NOTE (read before trusting these 3 fields — same caveat as
merge_augsburg_into_territoryai.py, and the same reasoning applies verbatim
since Kaarst's shipped row was ALSO hand-assembled once with no persisted
field_07 run): final_score/structural_certainty/risk_penalty ARE exactly
reproducible via field_07_street_ranking.py's real formula (verified by
dry-run against this file's current inputs). deployment_score/priority_score
are NOT — field_07's formula computed against Kaarst's CURRENT dominant_form
("SFH_WEAK") does not reproduce the shipped values, implying the original
hand-assembly used a different/stale dominant_form weight. Rather than
preserve that unreproducible discrepancy, this script uses the SAME
transparent monotonic approximation already user-approved for Augsburg:
    deployment_score = 0.5 * final_score + 0.5 * pv_coverage_score
    risk_penalty      = uncertain_share * 0.3
    priority_score    = max(0, deployment_score - risk_penalty)

SCHEMA NOTE: build_kaarst_layer2.py's raw output (37 cols) is missing 13
columns present in territoryai's street_level_ranking_v1.parquet schema
(sfh_detached_ratio, sfh_rowhouse_ratio, sfh_semi_ratio,
structure_gate_original, coherence_capped, sales_story, low_sample_flag,
pv_data_saturated, sfh_stage1_share, sfh_stage2_share, data_quality_note,
hp_confidence, seg_truly_uncertain_share) — these were added to Augsburg
during its own 2026-07-07/08 QA passes (allotment-garden exclusion,
per-street Stage1/2 confidence via _compute_per_street_data_quality(),
segment-BLOCKED coherence-guard). Kaarst has NEVER had that work done.
This script fills the 13 columns MECHANICALLY ONLY (ratios, direct
cluster-dict lookups, segment-level fallback for stage1/2 share) — it does
NOT attempt Augsburg's per-street data-quality refinement or allotment-
garden detection for Kaarst. That would be new, separate scope (a Kaarst
data-quality pass, not part of D3) if wanted later.

GUARDRAILS:
  - Neuss and Augsburg rows in both target parquets: untouched (old rows
    preserved, only KAARST_ rows are replaced via concat).
  - Output schema: exact column-set match asserted before writing.
  - Assertions abort the write entirely if NaN or duplicate KAARST_ rows
    would result — no partial/corrupt writes.
"""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("MERGE_KAARST")

DESS_BASE_DIR = Path(__file__).resolve().parents[1]
TERRITORYAI_DIR = Path(r"D:\Stock Analysis\territoryai\data\layer2")

KAARST_L2_PARQ  = DESS_BASE_DIR / "data" / "layer2" / "kaarst_layer2_input_table.parquet"
KAARST_SLR_PARQ = DESS_BASE_DIR / "data" / "layer2" / "kaarst_street_level_ranking_v1.parquet"

TARGET_SEG_PARQ = TERRITORYAI_DIR / "street_ranking_v1.parquet"
TARGET_SLR_PARQ = TERRITORYAI_DIR / "street_level_ranking_v1.parquet"

KAARST_SEGMENT_ID = "KAARST_OSM_41564"
KAARST_PLZ        = "41564"

LOW_SAMPLE_THRESHOLD = 10     # matches field_08_street_level_ranking.py / build_augsburg_layer2.py
PV_SCORE_CAP         = 0.50   # E3 cap (field_04's E3_MAX_FIELD_VALUE)

# German reason strings (must match portal/src/constants/labels_de.js REASON_DE
# keys exactly — reused verbatim from merge_augsburg_into_territoryai.py)
REASON_HIGH_SFH_DETACHED   = "Detached / rowhouse homes — installation-friendly"
REASON_GOOD_SFH_VOLUME     = "Good SFH share — solid PV opportunity base"
REASON_ROOF_ABOVE_AVG      = "Above-average roof suitability in this area"
REASON_LOW_PV_PENETRATION  = "Low current PV penetration — open market opportunity"
REASON_MIXED_STRUCTURE     = "Mixed structure — some units may not qualify"
REASON_PROXY_DATA_CAUTION  = "SFH classification via proxy — recommend field confirmation"


def build_kaarst_segment_row(df_l2: pd.DataFrame, df_slr: pd.DataFrame) -> pd.DataFrame:
    r = df_l2.iloc[0]

    structural_certainty = round(1.0 - float(r["uncertain_share"]), 4)
    base_score = round(float(df_slr["street_quality_agg"].iloc[0]), 4)
    # Verified-exact relationship (see module docstring / merge_augsburg precedent).
    final_score = round(base_score * structural_certainty, 4)
    constraint_score = base_score  # no heat-constraint data for Kaarst (matches shipped row)

    # APPROXIMATION — see module docstring.
    deployment_score = round(0.5 * final_score + 0.5 * float(r["pv_coverage_score"]), 4)
    risk_penalty      = round(float(r["uncertain_share"]) * 0.3, 4)
    priority_score    = round(max(0.0, deployment_score - risk_penalty), 4)

    sfh_friendly  = float(r["sfh_friendly_share"])
    sfh_confirmed = float(r["sfh_confirmed_share"])
    mfh_confirmed = float(r["mfh_confirmed_share"])

    if sfh_confirmed >= 0.5:
        top_reason_1 = REASON_HIGH_SFH_DETACHED
    elif sfh_friendly >= 0.5:
        top_reason_1 = REASON_GOOD_SFH_VOLUME
    else:
        top_reason_1 = REASON_LOW_PV_PENETRATION

    top_reason_2 = REASON_ROOF_ABOVE_AVG if r["roof_suitability_score_norm"] >= 0.45 else ""
    top_reason_3 = ""

    primary_caution = REASON_MIXED_STRUCTURE if mfh_confirmed >= 0.15 else (
        REASON_PROXY_DATA_CAUTION if (sfh_friendly - sfh_confirmed) > 0.4 else ""
    )

    row = {
        "rank": 1,  # single segment, matches shipped
        "canvass_tier": "SECONDARY",  # heat_status UNKNOWN -> SECONDARY (matches shipped)
        "street_id": KAARST_SEGMENT_ID,
        "street_name": f"Kaarst (PLZ {KAARST_PLZ})",
        "base_score": base_score,
        "constraint_score": constraint_score,
        "final_score": final_score,
        "fernwaerme_modifier": 1.0,
        "hp_modifier": 1.0,
        "confidence": 0.0,
        "heat_constraint_label": "UNKNOWN",
        "heat_constraint_score": 0.0,
        "heat_constraint_confidence": 0.0,
        "hp_opportunity_label": "UNKNOWN",
        "hp_opportunity_score": 0.0,
        "heat_status": "UNKNOWN",
        "hp_status": "UNKNOWN",
        "effective_sfh_share": float(r["effective_sfh_share"]),
        "sfh_confirmed_share": sfh_confirmed,
        "sfh_proxy_only_share": round(max(0.0, sfh_friendly - sfh_confirmed), 4),
        "sfh_friendly_share": sfh_friendly,
        "mfh_confirmed_share": mfh_confirmed,
        "uncertain_share": float(r["uncertain_share"]),
        "truly_uncertain_share": float(r["uncertain_share"]),  # no field_07 refinement (matches shipped)
        "structural_certainty": structural_certainty,
        "pv_coverage_score": float(r["pv_coverage_score"]),
        "roof_suitability_score_norm": float(r["roof_suitability_score_norm"]),
        "l1_gate_label": str(r["l1_gate_label"]),
        "deployment_score": deployment_score,
        "risk_penalty": risk_penalty,
        "priority_score": priority_score,
        "top_reason_1": top_reason_1,
        "top_reason_2": top_reason_2,
        "top_reason_3": top_reason_3,
        "primary_caution": primary_caution,
        "roi_report_template_flag": "PV_STANDARD",
    }
    return pd.DataFrame([row])


def build_kaarst_street_rows(df_slr: pd.DataFrame) -> pd.DataFrame:
    """Adds the 13 columns present in territoryai's schema but not produced by
    build_kaarst_layer2.py — mechanical derivations only (see module docstring)."""
    df = df_slr.copy()
    n_total = df["building_count_total"].clip(lower=1)

    df["sfh_detached_ratio"] = (df["sfh_detached_count"] / n_total).round(3)
    df["sfh_rowhouse_ratio"] = (df["sfh_rowhouse_count"] / n_total).round(3)
    df["sfh_semi_ratio"]     = (df["sfh_semi_count"] / n_total).round(3)

    # Kaarst's single segment is DEPLOYABLE, never BLOCKED -> the Augsburg
    # segment-coherence guard never fires; gate is never overridden.
    df["structure_gate_original"] = df["structure_gate"]
    df["coherence_capped"] = False

    df["low_sample_flag"] = df["building_count_total"] < LOW_SAMPLE_THRESHOLD
    # Kaarst's single-segment pv_coverage_score (0.5) sits exactly at the E3
    # cap -> saturated for every street (matches Augsburg's mechanical check).
    pv_score = float(df_slr.attrs.get("_pv_coverage_score", 0.5))
    df["pv_data_saturated"] = bool(pv_score >= PV_SCORE_CAP)

    # No per-street Stage1/2 confidence work has been done for Kaarst (unlike
    # Augsburg's 2026-07-08 fix) — fall back to the segment-level aggregate,
    # repeated per street. This matches Kaarst's existing/shipped methodology
    # tier; it is NOT a regression, just schema-parity for the new columns.
    seg_sfh_confirmed = float(df_slr.attrs.get("_sfh_confirmed_share", 0.0))
    seg_sfh_proxy      = float(df_slr.attrs.get("_sfh_proxy_share", 0.0))
    seg_data_quality    = str(df_slr.attrs.get("_data_quality", "MIXED"))
    df["sfh_stage1_share"] = seg_sfh_confirmed
    df["sfh_stage2_share"] = seg_sfh_proxy
    df["data_quality_note"] = (
        "Stage-1 confirmed (OSM adjacency)" if seg_data_quality == "HIGH"
        else "Stage-2 proxy (footprint heuristic)" if seg_data_quality == "PROXY"
        else "Stage-1 + Stage-2 composite"
    )

    df["sales_story"] = ""  # build_kaarst_layer2.py's foundation-cluster read doesn't carry this through
    df["hp_confidence"] = 1.0             # no field_07 HP data for Kaarst (matches shipped)
    df["seg_truly_uncertain_share"] = 0.0  # no field_07 data for Kaarst (matches shipped)

    return df


def main():
    target_seg = pd.read_parquet(TARGET_SEG_PARQ)
    target_slr = pd.read_parquet(TARGET_SLR_PARQ)

    df_l2  = pd.read_parquet(KAARST_L2_PARQ)
    df_slr = pd.read_parquet(KAARST_SLR_PARQ)

    r0 = df_l2.iloc[0]
    df_slr.attrs["_pv_coverage_score"]  = float(r0["pv_coverage_score"])
    df_slr.attrs["_sfh_confirmed_share"] = float(r0["sfh_confirmed_share"])
    sfh_proxy = max(0.0, float(r0["sfh_friendly_share"]) - float(r0["sfh_confirmed_share"]))
    df_slr.attrs["_sfh_proxy_share"] = sfh_proxy
    sfh_confirmed = float(r0["sfh_confirmed_share"])
    if sfh_confirmed >= 0.5:
        data_quality = "HIGH"
    elif sfh_confirmed < 0.3 and sfh_proxy > 0.3:
        data_quality = "PROXY"
    else:
        data_quality = "MIXED"
    df_slr.attrs["_data_quality"] = data_quality

    kaarst_seg = build_kaarst_segment_row(df_l2, df_slr)
    kaarst_slr = build_kaarst_street_rows(df_slr)

    # Schema verification before touching anything on disk
    assert set(kaarst_seg.columns) == set(target_seg.columns), (
        f"street_ranking schema mismatch: "
        f"missing={set(target_seg.columns) - set(kaarst_seg.columns)} "
        f"extra={set(kaarst_seg.columns) - set(target_seg.columns)}"
    )
    assert set(kaarst_slr.columns) == set(target_slr.columns), (
        f"street_level_ranking schema mismatch: "
        f"missing={set(target_slr.columns) - set(kaarst_slr.columns)} "
        f"extra={set(kaarst_slr.columns) - set(target_slr.columns)}"
    )
    logger.info("[SCHEMA] Both Kaarst tables match territoryai's target schema exactly.")

    kaarst_seg = kaarst_seg[target_seg.columns]
    kaarst_slr = kaarst_slr[target_slr.columns]

    n_prior_seg = target_seg["street_id"].astype(str).str.startswith("KAARST_").sum()
    n_prior_slr = target_slr["segment_id"].astype(str).str.startswith("KAARST_").sum()
    logger.info(f"[REPLACE] Dropping {n_prior_seg} prior KAARST_ rows from street_ranking_v1 "
                f"and {n_prior_slr} from street_level_ranking_v1 before re-merge.")
    target_seg = target_seg[~target_seg["street_id"].astype(str).str.startswith("KAARST_")]
    target_slr = target_slr[~target_slr["segment_id"].astype(str).str.startswith("KAARST_")]

    merged_seg = pd.concat([target_seg, kaarst_seg], ignore_index=True)
    merged_slr = pd.concat([target_slr, kaarst_slr], ignore_index=True)

    n_nan_seg = merged_seg.isna().sum().sum()
    n_nan_slr = merged_slr.isna().sum().sum()
    logger.info(f"[CHECK] merged street_ranking_v1: {len(merged_seg)} rows, {n_nan_seg} NaN cells")
    logger.info(f"[CHECK] merged street_level_ranking_v1: {len(merged_slr)} rows, {n_nan_slr} NaN cells")
    assert n_nan_seg == 0, "NaN introduced in merged street_ranking_v1 — aborting write"
    assert n_nan_slr == 0, "NaN introduced in merged street_level_ranking_v1 — aborting write"

    dup_slr = merged_slr[merged_slr["segment_id"].astype(str).str.startswith("KAARST_")]
    dup_check = dup_slr.duplicated(subset=["plz", "street_name"]).sum()
    assert dup_check == 0, f"{dup_check} duplicate (plz, street_name) rows in KAARST_ streets — aborting write"

    merged_seg.to_parquet(TARGET_SEG_PARQ, index=False)
    merged_slr.to_parquet(TARGET_SLR_PARQ, index=False)
    logger.info(f"[WRITE] {TARGET_SEG_PARQ} ({len(merged_seg)} rows)")
    logger.info(f"[WRITE] {TARGET_SLR_PARQ} ({len(merged_slr)} rows)")

    logger.info("[SUMMARY] Kaarst segment row:")
    logger.info(kaarst_seg.iloc[0][["street_id", "base_score", "final_score", "deployment_score",
                                      "priority_score", "roof_suitability_score_norm"]].to_dict())
    logger.info(f"[SUMMARY] {len(kaarst_slr)} Kaarst street rows written.")


if __name__ == "__main__":
    main()
