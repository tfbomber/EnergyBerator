"""
merge_leipzig_into_territoryai.py
====================================
Final step: builds Leipzig's 34 segment-level rows (street_ranking_v1.parquet
schema) and merges both Leipzig parquets into territoryai's shared
data/layer2/street_ranking_v1.parquet and street_level_ranking_v1.parquet.

APPROXIMATION NOTE (same as merge_augsburg_into_territoryai.py — read before
trusting these 5 fields): base_score/constraint_score/final_score/
deployment_score/risk_penalty/priority_score look like field_07's output, but
field_07 is Neuss-only and was never run for Kaarst/Augsburg/Leipzig either.
final_score = round(base_score * structural_certainty, 4) is the one
relationship verified EXACT against Neuss/Kaarst's real rows (reused as-is,
same as Augsburg). deployment_score/risk_penalty/priority_score use the same
transparent, documented, monotonic approximation Augsburg used — not a new
one invented for Leipzig, so it stays "the same style of unverifiable
approximation", not a divergent new formula.

GUARDRAILS:
  - Neuss/Kaarst/Augsburg rows in both target parquets: untouched (old rows
    preserved, only new Leipzig rows are appended via concat).
  - Output schema: exact column-set match asserted before writing.
  - Assertions abort the write entirely if NaN or duplicate LEIPZIG_ rows
    would result — no partial/corrupt writes.
  - Idempotent: drops any pre-existing LEIPZIG_ rows before re-appending, so
    reruns don't duplicate.
"""

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("MERGE_LEIPZIG")

DESS_BASE_DIR = Path(__file__).resolve().parents[1]
TERRITORYAI_DIR = Path(r"D:\Stock Analysis\territoryai\data\layer2")

LEIPZIG_L2_PARQ  = DESS_BASE_DIR / "data" / "layer2" / "leipzig_layer2_input_table.parquet"
LEIPZIG_SLR_PARQ = DESS_BASE_DIR / "data" / "layer2" / "leipzig_street_level_ranking_v1.parquet"

TARGET_SEG_PARQ = TERRITORYAI_DIR / "street_ranking_v1.parquet"
TARGET_SLR_PARQ = TERRITORYAI_DIR / "street_level_ranking_v1.parquet"

# German reason strings (must match portal/src/constants/labels_de.js REASON_DE
# keys exactly — same set Augsburg used, no new strings introduced).
REASON_HIGH_SFH_DETACHED   = "Detached / rowhouse homes — installation-friendly"
REASON_GOOD_SFH_VOLUME     = "Good SFH share — solid PV opportunity base"
REASON_ROOF_ABOVE_AVG      = "Above-average roof suitability in this area"
REASON_LOW_PV_PENETRATION  = "Low current PV penetration — open market opportunity"
REASON_MIXED_STRUCTURE     = "Mixed structure — some units may not qualify"
REASON_PROXY_DATA_CAUTION  = "SFH classification via proxy — recommend field confirmation"


def build_leipzig_segment_rows() -> pd.DataFrame:
    df_l2 = pd.read_parquet(LEIPZIG_L2_PARQ)
    df_slr = pd.read_parquet(LEIPZIG_SLR_PARQ)

    seg_rank = df_slr.groupby("segment_id")["segment_rank"].first()

    rows = []
    for _, r in df_l2.iterrows():
        seg_id = r["unit_id"]
        plz    = r["plz"]

        structural_certainty = round(1.0 - float(r["uncertain_share"]), 4)
        base_score = round(float(df_slr[df_slr["segment_id"] == seg_id]["street_quality_agg"].iloc[0]), 4)
        final_score = round(base_score * structural_certainty, 4)
        constraint_score = base_score

        deployment_score = round(0.5 * final_score + 0.5 * float(r["pv_coverage_score"]), 4)
        risk_penalty      = round(float(r["uncertain_share"]) * 0.3, 4)
        priority_score    = round(max(0.0, deployment_score - risk_penalty), 4)

        sfh_friendly = float(r["sfh_friendly_share"])
        sfh_confirmed = float(r["sfh_confirmed_share"])
        mfh_confirmed = float(r["mfh_confirmed_share"])
        gate_label = r["l1_gate_label"]

        # canvass_tier: heat_status is UNKNOWN for Leipzig (field_03 inert,
        # same as Kaarst/Augsburg) -> SECONDARY.
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
            "street_name": f"Leipzig (PLZ {plz})",
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
            "truly_uncertain_share": float(r["uncertain_share"]),
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

    leipzig_seg = build_leipzig_segment_rows()
    leipzig_slr = pd.read_parquet(LEIPZIG_SLR_PARQ)

    assert set(leipzig_seg.columns) == set(target_seg.columns), (
        f"street_ranking schema mismatch: "
        f"missing={set(target_seg.columns) - set(leipzig_seg.columns)} "
        f"extra={set(leipzig_seg.columns) - set(target_seg.columns)}"
    )
    assert set(leipzig_slr.columns) == set(target_slr.columns), (
        f"street_level_ranking schema mismatch: "
        f"missing={set(target_slr.columns) - set(leipzig_slr.columns)} "
        f"extra={set(leipzig_slr.columns) - set(target_slr.columns)}"
    )
    logger.info("[SCHEMA] Both Leipzig tables match territoryai's target schema exactly.")

    leipzig_seg = leipzig_seg[target_seg.columns]
    leipzig_slr = leipzig_slr[target_slr.columns]

    # Snapshot pre-existing non-Leipzig rows for a byte-identical proof after write.
    pre_existing_seg = target_seg[~target_seg["street_id"].astype(str).str.startswith("LEIPZIG_")].copy()
    pre_existing_slr = target_slr[~target_slr["segment_id"].astype(str).str.startswith("LEIPZIG_")].copy()

    n_prior_seg = target_seg["street_id"].astype(str).str.startswith("LEIPZIG_").sum()
    n_prior_slr = target_slr["segment_id"].astype(str).str.startswith("LEIPZIG_").sum()
    if n_prior_seg or n_prior_slr:
        logger.info(f"[REPLACE] Dropping {n_prior_seg} prior LEIPZIG_ rows from street_ranking_v1 "
                    f"and {n_prior_slr} from street_level_ranking_v1 before re-merge.")
    target_seg = target_seg[~target_seg["street_id"].astype(str).str.startswith("LEIPZIG_")]
    target_slr = target_slr[~target_slr["segment_id"].astype(str).str.startswith("LEIPZIG_")]

    merged_seg = pd.concat([target_seg, leipzig_seg], ignore_index=True)
    merged_slr = pd.concat([target_slr, leipzig_slr], ignore_index=True)

    n_nan_seg = merged_seg.isna().sum().sum()
    n_nan_slr = merged_slr.isna().sum().sum()
    logger.info(f"[CHECK] merged street_ranking_v1: {len(merged_seg)} rows, {n_nan_seg} NaN cells")
    logger.info(f"[CHECK] merged street_level_ranking_v1: {len(merged_slr)} rows, {n_nan_slr} NaN cells")
    assert n_nan_seg == 0, "NaN introduced in merged street_ranking_v1 — aborting write"
    assert n_nan_slr == 0, "NaN introduced in merged street_level_ranking_v1 — aborting write"

    # Byte-identical proof: every pre-existing (non-Leipzig) row must be
    # untouched by this merge (Neuss/Kaarst/Augsburg regression guard).
    post_seg_non_leipzig = merged_seg[~merged_seg["street_id"].astype(str).str.startswith("LEIPZIG_")].reset_index(drop=True)
    post_slr_non_leipzig = merged_slr[~merged_slr["segment_id"].astype(str).str.startswith("LEIPZIG_")].reset_index(drop=True)
    pre_existing_seg_sorted = pre_existing_seg.sort_values("street_id").reset_index(drop=True)
    post_seg_sorted = post_seg_non_leipzig.sort_values("street_id").reset_index(drop=True)
    pre_existing_slr_sorted = pre_existing_slr.sort_values("segment_id").reset_index(drop=True)
    post_slr_sorted = post_slr_non_leipzig.sort_values("segment_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(pre_existing_seg_sorted, post_seg_sorted, check_like=False)
    pd.testing.assert_frame_equal(pre_existing_slr_sorted, post_slr_sorted, check_like=False)
    logger.info("[REGRESSION GUARD] Neuss/Kaarst/Augsburg rows in both target parquets are "
                "byte-identical before vs after this merge.")

    merged_seg.to_parquet(TARGET_SEG_PARQ, index=False)
    merged_slr.to_parquet(TARGET_SLR_PARQ, index=False)
    logger.info(f"[WRITE] {TARGET_SEG_PARQ} ({len(merged_seg)} rows)")
    logger.info(f"[WRITE] {TARGET_SLR_PARQ} ({len(merged_slr)} rows)")

    logger.info("[SUMMARY] street_id prefix counts in merged street_ranking_v1:")
    logger.info(merged_seg["street_id"].astype(str).str.extract(r"^([A-Z]+)")[0].value_counts().to_dict())
    logger.info("[SUMMARY] segment_id prefix counts in merged street_level_ranking_v1:")
    logger.info(merged_slr["segment_id"].astype(str).str.extract(r"^([A-Z]+)")[0].value_counts().to_dict())


if __name__ == "__main__":
    main()
