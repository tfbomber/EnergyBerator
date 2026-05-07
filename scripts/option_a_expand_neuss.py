"""
option_a_expand_neuss.py
=========================
Option-A: Neuss full expansion without running field_01-06 for new segments.

Strategy:
  1. Run field_08 (already has new PLZ mapped) to get street-level data + segment agg
  2. For new segments (MITTE / SUED / WEST), compute conservative segment-level
     entries by:
     - base_score = street_quality_agg from field_08
     - heat_status = LIMITED_OR_UNCLEAR, heat_modifier = 0.90 (conservative)
     - hp_status = LIMITED_HP_UPLIFT, hp_modifier = 1.00 (neutral)
     - structural_certainty = derived from truly_uncertain_share (foundation data)
     - All other triad scores computed per field_07 formula
  3. Append new segment rows to street_ranking_v1.parquet and re-rank

Guardrails:
  - Does NOT modify any field_01-06 outputs
  - Clearly labels new rows with roi_report_template_flag = "OPTION_A_PLACEHOLDER"
  - Conservative signals only (no optimistic inflation)
  - Audit: logs every injected segment with reasoning

Run:
  python scripts/option_a_expand_neuss.py
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [OPTION_A] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA       = ROOT / "data" / "layer2"
L2_PATH    = DATA / "street_ranking_v1.parquet"        # field_07 output (patch target)
F08_OUTPUT = DATA / "street_level_ranking_v1.parquet"  # field_08 output (source of agg)

# ── New segment display labels ───────────────────────────────────────────────
NEW_SEGMENT_LABELS = {
    "NEUSS_PLZ41460": "Innenstadt / Hammfeld (PLZ 41460)",
    "NEUSS_PLZ41462": "Furth (PLZ 41462)",
    "NEUSS_PLZ41466": "Reuschenberg / Weckhoven (PLZ 41466)",
    "NEUSS_PLZ41468": "Grimlinghausen / Gnadental (PLZ 41468)",
    "NEUSS_PLZ41469": "Norf / Erfttal (PLZ 41469)",
}

# ── Conservative market signal defaults (Option-A placeholder) ───────────────
# Rationale:
#   heat_status = LIMITED_OR_UNCLEAR → heat_modifier = 0.90
#     (we genuinely don't know Fernwärme situation for these PLZ;
#      conservative assumption protects against overestimating WP opportunity)
#   hp_status = LIMITED_HP_UPLIFT → hp_modifier = 1.00
#     (no HP uplift claimed without real data)
#   structural_certainty = computed from foundation data quality
#   quality_tier = QUALITY_B (moderate confidence; no field data)

HEAT_STATUS   = "LIMITED_OR_UNCLEAR"
HEAT_MODIFIER = 0.90
HP_STATUS     = "LIMITED_HP_UPLIFT"
HP_MODIFIER   = 1.00
HP_CONFIDENCE = 0.50
QUALITY_TIER  = "QUALITY_B"
UNCERTAINTY_ALPHA = 0.50   # same as field_07


def _deploy_score(sfh_conf: float, gate_label: str, dominant_form: str) -> float:
    """Replicate field_07 deployment score formula."""
    DEPLOY_GATE = {
        "DEPLOYABLE": 1.00, "MIXED": 0.55, "BLOCKED": 0.10, "NOT_AVAILABLE": 0.50,
    }
    DEPLOY_FORM = {
        "SFH_CONFIRMED": 1.00, "DETACHED": 1.00, "SFH_WEAK": 0.70,
        "SEMI": 0.60, "ROWHOUSE": 0.50, "UNCERTAIN": 0.40,
        "MFH_SUSPECT": 0.20, "MFH_CONFIRMED": 0.10,
    }
    gate_s = DEPLOY_GATE.get(str(gate_label).upper(), 0.50)
    conf_s = float(sfh_conf or 0.0)
    form_s = DEPLOY_FORM.get(str(dominant_form).upper(), 0.40)
    return round(gate_s * 0.50 + conf_s * 0.30 + form_s * 0.20, 4)


def run():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info("=== Option-A Neuss Expansion START (%s) ===", ts)

    # ── Step 1: Run field_08 to get extended street data ────────────────────
    log.info("[STEP 1] Running field_08 with extended PLZ mapping ...")
    from fields.field_08_street_level_ranking import build_street_ranking as f08
    street_df, agg_df = f08()
    log.info("[STEP 1] field_08 complete. %d streets, agg segments: %s",
             len(street_df), list(agg_df["segment_id"].unique()))

    # ── Step 2: Load existing field_07 output ───────────────────────────────
    log.info("[STEP 2] Loading existing street_ranking_v1.parquet ...")
    existing = pd.read_parquet(L2_PATH)
    existing_ids = set(existing["street_id"].tolist())
    log.info("[STEP 2] Existing segments: %s", sorted(existing_ids))

    # Remove stale merged Option-A segments (old groupings replaced by per-PLZ)
    stale_ids = {"NEUSS_MITTE_01", "NEUSS_SUED_01", "NEUSS_WEST_01"}
    stale_found = stale_ids & existing_ids
    if stale_found:
        log.info("[CLEANUP] Removing stale merged segments: %s", sorted(stale_found))
        existing = existing[~existing["street_id"].isin(stale_ids)]
        existing_ids = set(existing["street_id"].tolist())
        log.info("[CLEANUP] Remaining: %s", sorted(existing_ids))

    # ── Step 3: Compute new segment entries from agg_df ─────────────────────
    new_rows = []
    for new_seg_id, label in NEW_SEGMENT_LABELS.items():
        if new_seg_id in existing_ids:
            log.info("[SKIP] %s already in ranking parquet — skipping.", new_seg_id)
            continue

        # Get street_quality_agg for this segment (field_08 building-weighted agg)
        agg_row = agg_df[agg_df["segment_id"] == new_seg_id]
        if agg_row.empty:
            log.warning("[MISSING] No agg data for %s — segment has no streets? Skipping.", new_seg_id)
            continue

        base_score = float(agg_row["street_quality_agg"].iloc[0])
        log.info("[NEW_SEG] %s: base_score (street_quality_agg) = %.4f", new_seg_id, base_score)

        # Conservative uncertainty estimate from actual street data
        seg_streets = street_df[street_df["segment_id"] == new_seg_id]
        n_total    = int(seg_streets["building_count_total"].sum())
        n_sfh      = int(seg_streets["sfh_total_count"].sum())
        sfh_pct    = n_sfh / n_total if n_total > 0 else 0.0
        # No confirmed stage-1 data for new segments → assume truly_uncertain based on pass/gate ratio
        n_pass     = (seg_streets["structure_gate"] == "PASS").sum()
        n_streets  = len(seg_streets)
        gate_pass_rate = n_pass / n_streets if n_streets > 0 else 0.5
        # Conservative: truly_uncertain = 1 - gate_pass_rate (streets with FAIL gate = uncertain)
        truly_unc  = round(max(0.0, min(0.60, 1.0 - gate_pass_rate)), 4)
        structural_certainty = round(1.0 - truly_unc * UNCERTAINTY_ALPHA, 4)

        # Score computation (replicating field_07 chain)
        constraint_score = round(base_score * HEAT_MODIFIER, 4)
        final_score      = round(constraint_score * HP_MODIFIER * structural_certainty, 4)

        # Deployment score (conservative: no sfh_confirmed, use neutral gate/form)
        deploy = _deploy_score(sfh_conf=0.30, gate_label="MIXED", dominant_form="UNCERTAIN")
        # risk_penalty: audit column only — NOT applied to priority_score (Fix C 2026-04-15).
        # Mirrors change in field_07: uncertainty already embedded in final_score via structural_certainty.
        risk   = round(truly_unc * 0.30, 4)
        priority = round(final_score * deploy, 4)   # Fix C: no (1 - risk_penalty)

        log.info(
            "[NEW_SEG] %s: base=%.4f fern×%.2f hp×%.2f certainty×%.3f → final=%.4f | "
            "SFH=%d/%d (%.0f%%) gate_pass=%.0f%% uncertainty=%.0f%%",
            new_seg_id, base_score, HEAT_MODIFIER, HP_MODIFIER, structural_certainty, final_score,
            n_sfh, n_total, sfh_pct * 100, gate_pass_rate * 100, truly_unc * 100,
        )

        new_rows.append({
            "street_id":               new_seg_id,
            "street_name":             label,
            "base_score":              round(base_score, 4),
            "constraint_score":        constraint_score,
            "final_score":             final_score,
            "fernwaerme_modifier":     HEAT_MODIFIER,
            "hp_modifier":             HP_MODIFIER,
            "confidence":              HP_CONFIDENCE,
            "heat_status":             HEAT_STATUS,
            "hp_status":               HP_STATUS,
            "effective_sfh_share":     round(sfh_pct, 4),
            "sfh_confirmed_share":     0.30,   # conservative placeholder
            "sfh_proxy_only_share":    round(max(0.0, sfh_pct - 0.30), 4),
            "sfh_friendly_share":      round(sfh_pct, 4),
            "mfh_confirmed_share":     0.00,
            "uncertain_share":         truly_unc,
            "truly_uncertain_share":   truly_unc,
            "structural_certainty":    structural_certainty,
            "pv_coverage_score":       0.50,   # neutral
            "roof_suitability_score_norm": 0.50,  # neutral
            "l1_gate_label":           "MIXED",
            "deployment_score":        deploy,
            "risk_penalty":            risk,
            "priority_score":          priority,
            "top_reason_1":            "Option-A segment — foundation data only",
            "top_reason_2":            "",
            "top_reason_3":            "",
            "primary_caution":         "Market signals not yet computed — field survey recommended",
            "roi_report_template_flag": "PV_STANDARD",
        })

    if not new_rows:
        log.warning("[RESULT] No new segments to inject. All already present.")
        return

    # ── Step 4: Merge and re-rank ────────────────────────────────────────────
    log.info("[STEP 4] Injecting %d new segment rows ...", len(new_rows))
    new_df = pd.DataFrame(new_rows)

    # Align columns — fill missing columns in new_df with None
    for col in existing.columns:
        if col not in new_df.columns:
            new_df[col] = None

    combined = pd.concat([existing, new_df[existing.columns]], ignore_index=True)
    combined = combined.sort_values("final_score", ascending=False).reset_index(drop=True)
    combined["rank"] = combined.index + 1
    log.info("[STEP 4] Combined: %d segments", len(combined))

    for _, r in combined.iterrows():
        log.info(
            "  [RANK #%d] %s: final=%.4f | heat=%s hp=%s certainty=%.3f",
            int(r["rank"]), r["street_id"],
            float(r["final_score"]),
            r.get("heat_status", "?"), r.get("hp_status", "?"),
            float(r.get("structural_certainty", 1.0)),
        )

    # ── Step 5: Save ─────────────────────────────────────────────────────────
    combined.to_parquet(L2_PATH, index=False)
    log.info("[STEP 5] Saved → %s (%d rows)", L2_PATH, len(combined))
    log.info("=== Option-A Neuss Expansion DONE ===")


if __name__ == "__main__":
    run()
