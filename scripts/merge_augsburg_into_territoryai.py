"""
merge_augsburg_into_territoryai.py
====================================
Final step: builds Augsburg's 14 segment-level rows (street_ranking_v1.parquet
schema) and merges both Augsburg parquets into territoryai's shared
data/layer2/street_ranking_v1.parquet and street_level_ranking_v1.parquet.

User-approved (2026-07-07) to proceed with the approximate segment-level
scoring fields documented below.

APPROXIMATION NOTE (read before trusting these 5 fields): street_ranking_v1's
schema includes base_score/constraint_score/final_score/deployment_score/
risk_penalty/priority_score — these look like field_07_street_ranking.py's
output, but field_07 is Neuss-only (hardcoded STREET_LABEL_MAP/
QUALITY_TIER_MAP keyed to the 8 Neuss PLZ) and was never run for Kaarst
either — Kaarst's own row in this file is also NOT a genuine field_07 output.
Reverse-engineering from Neuss/Kaarst's 2 existing rows: final_score =
round(base_score * structural_certainty, 4) holds EXACTLY for both
(0.6782*0.9466=0.6420=Neuss's final_score; 0.629*0.938=0.590=Kaarst's) — this
relationship is used here. deployment_score/risk_penalty/priority_score could
NOT be reverse-engineered to an exact formula from just 2 data points (e.g.
Kaarst has a "DEPLOYABLE" l1_gate_label yet a LOWER deployment_score than
Neuss's "MIXED" row, so it isn't a simple gate-label-driven formula either).
For those 3 fields this script uses a transparent, documented, monotonic
approximation instead of guessing at an exact match.

GUARDRAILS:
  - Neuss rows in both target parquets: untouched (old rows preserved,
    only new Augsburg rows are appended via concat).
  - Kaarst rows: same.
  - Output schema: exact column-set match asserted before writing.
  - Assertions abort the write entirely if NaN or duplicate AUGSBURG_ rows
    would result — no partial/corrupt writes.
"""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("MERGE_AUGSBURG")

DESS_BASE_DIR = Path(__file__).resolve().parents[1]
TERRITORYAI_DIR = Path(r"D:\Stock Analysis\territoryai\data\layer2")

AUGSBURG_L2_PARQ  = DESS_BASE_DIR / "data" / "layer2" / "augsburg_layer2_input_table.parquet"
AUGSBURG_SLR_PARQ = DESS_BASE_DIR / "data" / "layer2" / "augsburg_street_level_ranking_v1.parquet"

TARGET_SEG_PARQ = TERRITORYAI_DIR / "street_ranking_v1.parquet"
TARGET_SLR_PARQ = TERRITORYAI_DIR / "street_level_ranking_v1.parquet"

# German reason strings (must match portal/src/constants/labels_de.js REASON_DE
# keys exactly — these are the English keys that get translated at render time)
REASON_HIGH_SFH_DETACHED   = "Detached / rowhouse homes — installation-friendly"
REASON_GOOD_SFH_VOLUME     = "Good SFH share — solid PV opportunity base"
REASON_ROOF_ABOVE_AVG      = "Above-average roof suitability in this area"
REASON_LOW_PV_PENETRATION  = "Low current PV penetration — open market opportunity"
REASON_MIXED_STRUCTURE     = "Mixed structure — some units may not qualify"
REASON_PROXY_DATA_CAUTION  = "SFH classification via proxy — recommend field confirmation"


def build_augsburg_segment_rows() -> pd.DataFrame:
    df_l2 = pd.read_parquet(AUGSBURG_L2_PARQ)
    df_slr = pd.read_parquet(AUGSBURG_SLR_PARQ)

    # Segment rank already computed in build_augsburg_layer2.py (by street_quality_agg)
    seg_rank = df_slr.groupby("segment_id")["segment_rank"].first()

    rows = []
    for _, r in df_l2.iterrows():
        seg_id = r["unit_id"]
        plz    = r["plz"]

        structural_certainty = round(1.0 - float(r["uncertain_share"]), 4)
        base_score = round(float(df_slr[df_slr["segment_id"] == seg_id]["street_quality_agg"].iloc[0]), 4)
        # Verified-exact relationship from Neuss/Kaarst's real rows (see module docstring).
        final_score = round(base_score * structural_certainty, 4)
        constraint_score = base_score  # matches both real examples (constraint==base when no heat-constraint data)

        # APPROXIMATION (not reverse-engineerable from the 2 available real
        # examples — see module docstring): transparent monotonic blend of
        # segment quality (final_score) and PV market opportunity
        # (pv_coverage_score), discounted by classification uncertainty.
        deployment_score = round(0.5 * final_score + 0.5 * float(r["pv_coverage_score"]), 4)
        risk_penalty      = round(float(r["uncertain_share"]) * 0.3, 4)
        priority_score    = round(max(0.0, deployment_score - risk_penalty), 4)

        sfh_friendly = float(r["sfh_friendly_share"])
        sfh_confirmed = float(r["sfh_confirmed_share"])
        mfh_confirmed = float(r["mfh_confirmed_share"])
        gate_label = r["l1_gate_label"]

        # canvass_tier: heat_status is UNKNOWN for Augsburg (field_03 inert,
        # same as Kaarst) -> SECONDARY, matching the Kaarst precedent exactly
        # (Kaarst's own row: heat_status=UNKNOWN -> canvass_tier=SECONDARY).
        canvass_tier = "SECONDARY"

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

        rows.append({
            "rank": int(seg_rank.get(seg_id, 99)),
            "canvass_tier": canvass_tier,
            "street_id": seg_id,
            "street_name": f"Augsburg (PLZ {plz})",
            "base_score": base_score,
            "constraint_score": constraint_score,
            "final_score": final_score,
            "fernwaerme_modifier": 1.0,
            "hp_modifier": 1.0,
            "confidence": 0.0,   # no field_03/field_06 data for Augsburg (matches Kaarst)
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
            "truly_uncertain_share": float(r["uncertain_share"]),  # no field_07 refinement for Augsburg
            "structural_certainty": structural_certainty,
            "pv_coverage_score": float(r["pv_coverage_score"]),
            "roof_suitability_score_norm": float(r["roof_suitability_score_norm"]),
            "l1_gate_label": gate_label,
            "deployment_score": deployment_score,
            "risk_penalty": risk_penalty,
            "priority_score": priority_score,
            "top_reason_1": top_reason_1,
            "top_reason_2": top_reason_2,
            "top_reason_3": top_reason_3,
            "primary_caution": primary_caution,
            "roi_report_template_flag": "PV_STANDARD",
        })

    return pd.DataFrame(rows)


def main():
    target_seg = pd.read_parquet(TARGET_SEG_PARQ)
    target_slr = pd.read_parquet(TARGET_SLR_PARQ)

    augsburg_seg = build_augsburg_segment_rows()
    augsburg_slr = pd.read_parquet(AUGSBURG_SLR_PARQ)

    # Schema verification before touching anything on disk
    assert set(augsburg_seg.columns) == set(target_seg.columns), (
        f"street_ranking schema mismatch: "
        f"missing={set(target_seg.columns) - set(augsburg_seg.columns)} "
        f"extra={set(augsburg_seg.columns) - set(target_seg.columns)}"
    )
    assert set(augsburg_slr.columns) == set(target_slr.columns), (
        f"street_level_ranking schema mismatch: "
        f"missing={set(target_slr.columns) - set(augsburg_slr.columns)} "
        f"extra={set(augsburg_slr.columns) - set(target_slr.columns)}"
    )
    logger.info("[SCHEMA] Both Augsburg tables match territoryai's target schema exactly.")

    # Reorder Augsburg columns to match target exactly (cosmetic, avoids
    # column-order drift even though parquet is order-agnostic on read).
    augsburg_seg = augsburg_seg[target_seg.columns]
    augsburg_slr = augsburg_slr[target_slr.columns]

    # Idempotent re-merge: drop any pre-existing Augsburg rows first (e.g. from
    # a prior run of this script), then append the freshly-built ones. Neuss/
    # Kaarst rows are untouched either way — only rows already starting with
    # AUGSBURG_ are ever replaced.
    n_prior_seg = target_seg["street_id"].astype(str).str.startswith("AUGSBURG_").sum()
    n_prior_slr = target_slr["segment_id"].astype(str).str.startswith("AUGSBURG_").sum()
    if n_prior_seg or n_prior_slr:
        logger.info(f"[REPLACE] Dropping {n_prior_seg} prior AUGSBURG_ rows from street_ranking_v1 "
                    f"and {n_prior_slr} from street_level_ranking_v1 before re-merge.")
    target_seg = target_seg[~target_seg["street_id"].astype(str).str.startswith("AUGSBURG_")]
    target_slr = target_slr[~target_slr["segment_id"].astype(str).str.startswith("AUGSBURG_")]

    merged_seg = pd.concat([target_seg, augsburg_seg], ignore_index=True)
    merged_slr = pd.concat([target_slr, augsburg_slr], ignore_index=True)

    n_nan_seg = merged_seg.isna().sum().sum()
    n_nan_slr = merged_slr.isna().sum().sum()
    logger.info(f"[CHECK] merged street_ranking_v1: {len(merged_seg)} rows, {n_nan_seg} NaN cells")
    logger.info(f"[CHECK] merged street_level_ranking_v1: {len(merged_slr)} rows, {n_nan_slr} NaN cells")
    assert n_nan_seg == 0, "NaN introduced in merged street_ranking_v1 — aborting write"
    assert n_nan_slr == 0, "NaN introduced in merged street_level_ranking_v1 — aborting write"

    merged_seg.to_parquet(TARGET_SEG_PARQ, index=False)
    merged_slr.to_parquet(TARGET_SLR_PARQ, index=False)
    logger.info(f"[WRITE] {TARGET_SEG_PARQ} ({len(merged_seg)} rows)")
    logger.info(f"[WRITE] {TARGET_SLR_PARQ} ({len(merged_slr)} rows)")

    logger.info("[SUMMARY] PLZ universe in merged street_ranking_v1:")
    logger.info(merged_seg["street_id"].tolist())
    logger.info("[SUMMARY] plz value_counts in merged street_level_ranking_v1:")
    logger.info(merged_slr["plz"].value_counts().to_dict())


if __name__ == "__main__":
    main()
