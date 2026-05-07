"""
field_07_street_ranking.py
PV-Only Street Ranking Engine — Neuss MVP
==========================================
Reads accepted Layer 2 / P2 / P2.5 parquets and produces:
  data/layer2/street_ranking_v1.parquet

Scoring: base_score × fernwaerme_modifier × hp_modifier
Formula: identical to accepted Layer 2 (Guardrail G3).

GUARDRAILS:
- No new data sources
- No ML / training
- No household-level claims
- HP signal = narrative routing only
- Synthetic / unusable units always excluded
- Rank order must match Layer 2 accepted baseline
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [STREET_RANK] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "layer2"

L2_PATH  = DATA / "layer2_mvp_input_table.parquet"
P2_PATH  = DATA / "layer2_prio2_heat_overlay.parquet"
P25_PATH = DATA / "layer2_prio25_hp_uplift.parquet"
OUT_PATH = DATA / "street_ranking_v1.parquet"

# ---------------------------------------------------------------------------
# Street name labels (Neuss MVP hardcoded map)
# ---------------------------------------------------------------------------
STREET_LABEL_MAP = {
    # PLZ 41470: Allerheiligen, Rosellen (not "Norf" — corrected 2026-04-11)
    "NEUSS_PLZ41470":   "Allerheiligen / Rosellen (PLZ 41470)",
    # PLZ 41472: Holzheim, Grefrath, Speck, Hoisten
    "NEUSS_PLZ41472": "Holzheim / Grefrath (PLZ 41472)",
    # PLZ 41464: Pomona, Westfeld, Augustinusviertel (not "Grimlinghausen" — corrected 2026-04-11)
    "NEUSS_PLZ41464":  "Pomona / Westfeld (PLZ 41464)",
}

# ---------------------------------------------------------------------------
# Scoring reference (documentation only — NOT used for calculation here)
# NOTE: base_score is read directly from P2 parquet (already tier-discounted).
# Guardrail G3: do not redesign Layer 2 scoring in this engine.
# Accepted Layer 2 weights for audit trail:
#   sfh_friendly_share=30%  roof_suitability_score_norm=25%
#   pv_coverage_score=25%   pct_l1_gate_pass=20%
# Source of truth: layer2_review.py / RANKING_WEIGHTS
# ---------------------------------------------------------------------------

TIER_DISCOUNT = {
    "QUALITY_A": 1.00,
    "QUALITY_B": 0.85,
    "SYNTHETIC": 0.00,
}

# ---------------------------------------------------------------------------
# ROI report template mapping
# Updated for field_06 v2 labels (hp_opportunity_label)
# ---------------------------------------------------------------------------
TEMPLATE_MAP = {
    "STRONG":   "PV_HP_ENHANCED",
    "MODERATE": "PV_PLUS_HP_OPTIONAL",
    "LIMITED":  "PV_STANDARD",
    "WEAK":     "PV_STANDARD",
    "UNKNOWN":  "PV_STANDARD",
    # Legacy v1 labels (fallback for any cached parquets)
    "STRONG_HP_UPLIFT":   "PV_HP_ENHANCED",
    "MODERATE_HP_UPLIFT": "PV_PLUS_HP_OPTIONAL",
    "LIMITED_HP_UPLIFT":  "PV_STANDARD",
}

# ---------------------------------------------------------------------------
# Uncertainty penalty
# ---------------------------------------------------------------------------
# structural_certainty = 1 - (uncertain_share × α)
# α=0.50: 100% uncertain → score halved; 0% uncertain → no impact
# Guardrail: unknown ≠ good; fail-closed principle (user-approved 2026-03-30)
UNCERTAINTY_PENALTY_ALPHA = 0.50


# ---------------------------------------------------------------------------
# Reason engine
# ---------------------------------------------------------------------------
def _generate_reasons(row: pd.Series):
    """
    Returns (top_reason_1, top_reason_2, top_reason_3, primary_caution).
    Reasons are sales-usable, no technical jargon, no household claims.
    """
    a_reasons = []  # ROI drivers
    b_reasons = []  # Deployment drivers
    c_reasons = []  # Constraints / caveats

    sfh  = row.get("effective_sfh_share", 0.0)  # conservative: Stage 1 confirmed only
    pv   = row.get("pv_coverage_score", 0.0)
    hp   = row.get("hp_opportunity_label", row.get("hp_status", ""))   # v2 primary, v1 fallback
    heat = row.get("heat_constraint_label", row.get("heat_status", ""))  # v2 primary, v1 fallback
    form = str(row.get("dominant_form", "")).upper()
    gate = row.get("pct_l1_gate_pass", 0.0)
    tier = str(row.get("quality_tier", "")).upper()

    # Prefer normalized roof score [0,1] for differentiated threshold;
    # fallback to raw utilization rate; if BOTH missing = data gap (not a bad roof).
    # FIX 2 (2026-04-02): roof=0 confirmed to mean data missing, NOT bad suitability.
    _roof_norm = row.get("roof_suitability_score_norm")
    _roof_raw  = row.get("roof_suitability_score")
    if _roof_norm is not None and not pd.isna(_roof_norm):
        roof = float(_roof_norm)          # [0,1] scale
        _roof_above_avg = roof > 0.30     # above-average threshold on norm scale
    elif _roof_raw is not None and not pd.isna(_roof_raw) and float(_roof_raw) > 0:
        roof = float(_roof_raw)
        _roof_above_avg = roof > 0.08     # legacy raw utilization rate threshold
    else:
        # Data gap: neutral assumption — no positive claim, no penalty
        roof = 0.50
        _roof_above_avg = False           # fail-closed: no signal without data

    # --- A: ROI drivers ---
    if sfh >= 0.80:
        a_reasons.append("High single-family home density — strong PV fit")
    elif sfh >= 0.65:
        a_reasons.append("Good SFH share — solid PV opportunity base")

    if _roof_above_avg:
        a_reasons.append("Above-average roof suitability in this area")

    if pv < 0.35:
        a_reasons.append("Low current PV penetration — open market opportunity")

    # HP reason: use v2 label (STRONG) or v1 legacy (STRONG_HP_UPLIFT)
    if hp in ("STRONG", "STRONG_HP_UPLIFT"):
        a_reasons.append("Area profile matches fossil-replacement window")

    # --- B: Deployment drivers ---
    sfh_form_keywords = {"SFH", "ROWHOUSE", "SEMI", "DETACHED"}
    if any(k in form for k in sfh_form_keywords):
        b_reasons.append("Detached / rowhouse homes — installation-friendly")

    if gate >= 0.80:
        b_reasons.append("High structural deployability — low friction")

    # Data confidence: based on Stage-1 confirmed share, NOT geometry tier.
    # QUALITY_A/B reflects data SOURCE type (point vs polygon), not building
    # classification quality. Use sfh_confirmed_share for honest confidence signals.
    sfh_conf = float(row.get("sfh_confirmed_share", 0.0))
    if sfh_conf >= 0.60:
        b_reasons.append("High-confidence segment — Stage-1 OSM data backing")
    elif sfh_conf >= 0.20:
        b_reasons.append("Solid data foundation — partial Stage-1 confirmation")
    # sfh_conf < 0.20: no positive confidence claim generated

    # Heat constraint caution: v2 label (MEDIUM/HIGH) or v1 legacy
    if heat in ("MEDIUM", "HIGH", "LIMITED_OR_UNCLEAR", "NETWORK_LIKELY"):
        c_reasons.append("District-heating planning risk — qualify before pitch")

    # HP caution: limited opportunity
    if hp in ("LIMITED", "WEAK", "LIMITED_HP_UPLIFT"):
        c_reasons.append("HP narrative not yet substantiated for this area")

    # Proxy caution: fire when Stage-1 confirmed share is genuinely low,
    # regardless of geometry tier. SUBURB (confirmed=79%) should NOT get this.
    if sfh_conf < 0.20 and float(row.get("sfh_friendly_share", 0.0)) > 0.10:
        c_reasons.append("SFH classification via proxy — recommend field confirmation")

    if gate < 0.60:
        c_reasons.append("Mixed structure — some units may not qualify")

    unc = row.get("truly_uncertain_share", row.get("uncertain_share", 0.0))
    if unc > 0.50:
        c_reasons.append(
            f"Building type unconfirmed ({unc:.0%} truly uncertain) "
            "— field scan required before outreach"
        )


    # --- Select top reasons (max 3 total) ---
    selected = []

    # Up to 2 from A or B (A first)
    for r in a_reasons + b_reasons:
        if len(selected) < 2:
            selected.append(r)

    # 1 from C if any (caution returned separately — NOT added to positive reasons list)
    primary_caution = c_reasons[0] if c_reasons else ""

    while len(selected) < 3:
        selected.append("")

    return selected[0], selected[1], selected[2], primary_caution


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------
def build_street_ranking() -> pd.DataFrame:
    log.info("=== PV-Only Street Ranking Engine START ===")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Load and filter usable rows
    log.info("Loading Layer 2 parquets...")
    l2  = pd.read_parquet(L2_PATH)
    p2  = pd.read_parquet(P2_PATH)
    p25 = pd.read_parquet(P25_PATH)

    l2_usable  = l2[l2["row_usable_for_ranking"].astype(bool)].copy()   # LOW-04 FIX: avoid == True (fragile for int/str typed parquet cols)
    p2_usable  = p2[p2["row_usable_for_ranking"].astype(bool)].copy()
    p25_usable = p25[p25["row_usable_for_ranking"].astype(bool)].copy()

    # quality_tier is a UI-side lookup (not persisted in L2 parquet) — inject here
    QUALITY_TIER_MAP = {
        "NEUSS_PLZ41470":    "QUALITY_A",
        "NEUSS_PLZ41472":  "QUALITY_B",
        "NEUSS_PLZ41464":   "QUALITY_B",
        "NEUSS_PLZ41460":   "QUALITY_C",
        "NEUSS_PLZ41462":   "QUALITY_C",
        "NEUSS_PLZ41466":   "QUALITY_C",
        "NEUSS_PLZ41468":   "QUALITY_C",
        "NEUSS_PLZ41469":   "QUALITY_C",
    }
    l2_usable["quality_tier"] = l2_usable["unit_id"].map(QUALITY_TIER_MAP).fillna("SYNTHETIC")

    log.info(f"Usable rows: L2={len(l2_usable)}, P2={len(p2_usable)}, P25={len(p25_usable)}")

    # 2. Join on unit_id
    # P2 parquet (v2): base_score, heat_constraint_label, heat_modifier (=1-0.15*score)
    # P25 parquet (v2): hp_opportunity_label, hp_opportunity_score, hp_modifier(=1.00), hp_confidence
    #
    # Backward-compat: field_07 adds shim columns heat_status / hp_status
    # so UI components (street_ranking_view, street_roi_generator) need zero changes.
    p2_cols  = [c for c in ["unit_id", "base_score",
                             "heat_constraint_label", "heat_constraint_score",
                             "heat_constraint_confidence", "heat_modifier",
                             "heat_caveat"] if c in p2_usable.columns]
    p25_cols = [c for c in ["unit_id",
                             "hp_opportunity_label", "hp_opportunity_score",
                             "hp_modifier", "hp_confidence",
                             "hp_narrative"] if c in p25_usable.columns]

    df = (
        p2_usable[p2_cols]
        .merge(
            p25_usable[p25_cols],
            on="unit_id", how="inner"
        )
        .merge(
            l2_usable[[c for c in [
                "unit_id",
                "effective_sfh_share",
                "sfh_confirmed_share",
                "mfh_confirmed_share",
                "uncertain_share",
                "sfh_friendly_share",
                "roof_suitability_score", "roof_suitability_score_norm",
                "pv_coverage_score", "pct_l1_gate_pass",
                "l1_gate_label",
                "dominant_form", "quality_tier"
            ] if c in l2_usable.columns]],
            on="unit_id", how="inner"
        )
    )

    # Backward-compat shim: UI components still read heat_status / hp_status
    # Derive from v2 labels so no UI code changes needed.
    _HEAT_LABEL_TO_STATUS = {
        "HIGH":    "NETWORK_LIKELY",
        "MEDIUM":  "LIMITED_OR_UNCLEAR",
        "LOW":     "NO_SIGNAL",
        "UNKNOWN": "UNKNOWN",
    }
    _HP_LABEL_TO_STATUS = {
        "STRONG":   "STRONG_HP_UPLIFT",
        "MODERATE": "MODERATE_HP_UPLIFT",
        "LIMITED":  "LIMITED_HP_UPLIFT",
        "WEAK":     "LIMITED_HP_UPLIFT",
        "UNKNOWN":  "UNKNOWN",
    }
    df["heat_status"] = df["heat_constraint_label"].map(_HEAT_LABEL_TO_STATUS).fillna("UNKNOWN")
    df["hp_status"]   = df["hp_opportunity_label"].map(_HP_LABEL_TO_STATUS).fillna("UNKNOWN")
    log.info("[SHIM] heat_status / hp_status derived from v2 labels for UI backward-compat.")
    # Ensure optional fields exist with safe defaults
    for col, default in [
        ("dominant_form",  "UNKNOWN"),
        ("quality_tier",   "UNKNOWN"),
        ("l1_gate_label",  "NOT_AVAILABLE"),  # Fix 3 — deployment score input
    ]:
        if col not in df.columns:
            df[col] = default
            log.warning(f"[FIELD MISSING] '{col}' not in L2 parquet — defaulted to '{default}'")
    log.info(f"Joined rows: {len(df)}")

    # 3. base_score is taken directly from P2 parquet (already tier-discounted)
    log.info("[BASE_SCORE] Using accepted base_score from P2 parquet (includes tier discount)")

    # 4. field_05 is now a pure label layer (v3) — heat_modifier = 1.00 for all rows.
    # fernwaerme_modifier retained as informational column (UI badge, caveat text).
    df["fernwaerme_modifier"] = df.get("heat_modifier", pd.Series(1.00, index=df.index)).fillna(1.00)
    # constraint_score is now informational only, not used in scoring:
    df["constraint_score"]    = df["base_score"].round(4)  # == base_score (no suppression)

    # 5. ROI adjustment via hp_roi_multiplier from field_06 (Option C)
    # hp_roi_multiplier encodes: Fernwarme -> HP likelihood -> self-consumption -> PV ROI
    # final_score = base_score x hp_roi_multiplier x structural_certainty
    hp_mult = df.get("hp_roi_multiplier", df.get("hp_modifier", pd.Series(1.0, index=df.index)))
    df["hp_modifier"] = hp_mult.fillna(0.93)   # UNKNOWN fallback
    df["final_score"] = (df["base_score"] * df["hp_modifier"]).round(4)

    # 5b. Structural certainty penalty
    # Use truly_uncertain_share = 1 - sfh_friendly_share - mfh_confirmed_share
    # This treats Stage-2 (SFH_WEAK) as KNOWN, not uncertain.
    # NORF: 1 - 0.745 - 0.000 = 0.255 (was 1.00 when using raw uncertain_share)
    # SUBURB: 1 - 0.826 - 0.067 = 0.107
    # GRIML: 1 - 0.707 - 0.025 = 0.268
    df["truly_uncertain_share"] = (
        (1.0 - df["sfh_friendly_share"].clip(0.0, 1.0)
             - df["mfh_confirmed_share"].clip(0.0, 1.0)
        ).clip(0.0, 1.0)
    ).round(4)
    df["structural_certainty"] = (
        1.0 - df["truly_uncertain_share"] * UNCERTAINTY_PENALTY_ALPHA
    ).round(4)
    df["final_score"] = (df["final_score"] * df["structural_certainty"]).round(4)

    # 5c. SFH proxy-only share (Fix 1 — display transparency split)
    # sfh_confirmed_share  = Stage-1 OSM adjacency (hard-verified)
    # sfh_proxy_only_share = Stage-2 footprint only (inferred, not confirmed)
    # effective_sfh_share  = used for ranking formula (= sfh_confirmed_share)
    df["sfh_proxy_only_share"] = (
        df["sfh_friendly_share"].fillna(0.0) - df["sfh_confirmed_share"].fillna(0.0)
    ).clip(0.0, 1.0).round(4)

    # 5d. Deployment Score + Priority Score (Fix 3)
    # Deployment Score: how accessible / ready-to-convert is this area?
    # Formula: gate×0.50 + sfh_confirm×0.30 + dominant_form×0.20
    # No new data sources — all inputs already in df (Guardrail G1).
    _DEPLOY_GATE = {
        "DEPLOYABLE":    1.00,
        "MIXED":         0.55,
        "BLOCKED":       0.10,
        "NOT_AVAILABLE": 0.50,   # data missing → neutral
    }
    _DEPLOY_FORM = {
        "SFH_CONFIRMED": 1.00, "DETACHED": 1.00,
        "SFH_WEAK":      0.70, "SEMI":     0.60, "ROWHOUSE": 0.50,
        "UNCERTAIN":     0.40,
        "MFH_SUSPECT":   0.20, "MFH_CONFIRMED": 0.10,
    }

    def _deploy_score(row: pd.Series) -> float:
        gate_s = _DEPLOY_GATE.get(str(row.get("l1_gate_label", "NOT_AVAILABLE")).upper(), 0.50)
        conf_s = float(row.get("sfh_confirmed_share", 0.0) or 0.0)
        form_s = _DEPLOY_FORM.get(str(row.get("dominant_form", "UNCERTAIN")).upper(), 0.40)
        return round(gate_s * 0.50 + conf_s * 0.30 + form_s * 0.20, 4)

    df["deployment_score"] = df.apply(_deploy_score, axis=1)
    # risk_penalty: retained as an AUDIT/DISPLAY column only.
    # FIX C (2026-04-15): risk_penalty is NO LONGER multiplied into priority_score.
    # Root cause of removal: truly_uncertain_share already appears in final_score via
    # structural_certainty = 1 - truly_uncertain_share * 0.50.
    # Multiplying by (1 - risk_penalty) again compounds the same signal twice,
    # which suppressed ALL segments to 'Erst qualifizieren' even for high-ROI areas.
    # risk_penalty remains in the output parquet for UI display transparency.
    df["risk_penalty"]     = (df["truly_uncertain_share"] * 0.30).clip(0.0, 0.50).round(4)
    # priority_score: final_score (ROI quality, uncertainty-adjusted) × deployment_score
    # (operational readiness: gate, SFH confirmation, building form).
    # High priority = high ROI AND area is field-ready. Does NOT re-penalise uncertainty.
    df["priority_score"]   = (
        df["final_score"] * df["deployment_score"]
    ).round(4)
    log.info(
        "[PRIORITY_SCORES] ROI / Deployment / Risk(audit) / Priority:\n%s",
        df[["unit_id", "final_score", "deployment_score", "risk_penalty", "priority_score"]].to_string(index=False),
    )
    log.info(
        "[UNCERTAINTY_PENALTY] α=%.2f | Using truly_uncertain_share (Stage-2 = known):\n%s",
        UNCERTAINTY_PENALTY_ALPHA,
        df[["unit_id", "sfh_friendly_share", "truly_uncertain_share",
            "structural_certainty", "final_score"]].to_string(index=False)
    )

    # 6. Sanity checks (Option C architecture)
    # constraint_score == base_score (field_05 is label-only, no suppression)
    # hp_modifier: STRONG=1.10 max, WEAK=0.77 min
    assert (df["hp_modifier"] <= 1.15 + 0.0001).all(), \
        "[FAIL] hp_modifier exceeds cap (Option A: all values must be 1.00)"
    assert (df["hp_modifier"] >= 0.99 - 0.0001).all(), \
        "[FAIL] hp_modifier below 1.00 (Option A: no penalties allowed — check field_06)"
    assert (df["structural_certainty"] >= 0.0).all() and (df["structural_certainty"] <= 1.0).all(), \
        "[FAIL] structural_certainty out of [0,1] range"
    log.info("[SANITY] Option A confirmed: hp_modifier=1.00 for all rows | structural_certainty range OK")


    # 7. Reason engine
    reasons = df.apply(_generate_reasons, axis=1, result_type="expand")
    reasons.columns = ["top_reason_1", "top_reason_2", "top_reason_3", "primary_caution"]
    df = pd.concat([df.reset_index(drop=True), reasons.reset_index(drop=True)], axis=1)

    # 8. Template routing — use v2 label (hp_opportunity_label) primary
    df["roi_report_template_flag"] = (
        df["hp_opportunity_label"]
        .map(TEMPLATE_MAP)
        .fillna(df["hp_status"].map(TEMPLATE_MAP))  # legacy fallback
        .fillna("PV_STANDARD")
    )

    # 9. Street labels
    df["street_name"] = df["unit_id"].map(STREET_LABEL_MAP).fillna(df["unit_id"])
    df["street_id"]   = df["unit_id"]

    # 10. Rank
    df = df.sort_values("final_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # 10b. Canvass Tier — Soft Gate (no score change)
    # Splits segments by Fernwaerme feasibility WITHOUT touching any score.
    # Tiers drive the UI display order; internal rank is preserved within each tier.
    #   PRIMARY:          NO / LOW Fernwaerme signal — canvass directly
    #   SECONDARY:        MEDIUM / UNKNOWN — confirm Fernwaerme situation first
    #   NOT_RECOMMENDED:  HIGH / NETWORK_LIKELY — HP not viable, PV feasibility limited
    _HEAT_TO_TIER = {
        "LOW":            "PRIMARY",
        "NO_SIGNAL":      "PRIMARY",        # v1 legacy shim label
        "MEDIUM":         "SECONDARY",
        "UNKNOWN":        "SECONDARY",
        "HIGH":           "NOT_RECOMMENDED",
        "NETWORK_LIKELY": "NOT_RECOMMENDED",  # v1 legacy shim label
    }
    df["canvass_tier"] = (
        df["heat_constraint_label"]
        .map(_HEAT_TO_TIER)
        .fillna(df["heat_status"].map(_HEAT_TO_TIER))   # v1 shim fallback
        .fillna("SECONDARY")                             # fail-safe: unknown = confirm first
    )
    log.info(
        "[CANVASS_TIER] Tier distribution:\n%s",
        df.groupby("canvass_tier")["street_id"].apply(list).to_string(),
    )

    # 11. Confidence
    df["confidence"] = df["hp_confidence"].round(2)

    # 12. Select output columns
    output_cols = [
        "rank", "canvass_tier", "street_id", "street_name",
        "base_score", "constraint_score", "final_score",
        "fernwaerme_modifier", "hp_modifier", "confidence",
        # v2 signal columns
        "heat_constraint_label", "heat_constraint_score", "heat_constraint_confidence",
        "hp_opportunity_label", "hp_opportunity_score",
        # Backward-compat shim columns (UI reads these)
        "heat_status", "hp_status",
        # L2 display fields (for UI signal row)
        "effective_sfh_share",
        "sfh_confirmed_share",
        "sfh_proxy_only_share",
        "sfh_friendly_share",
        "mfh_confirmed_share", "uncertain_share",
        "truly_uncertain_share",
        "structural_certainty",
        "pv_coverage_score", "roof_suitability_score_norm",
        "l1_gate_label",
        "deployment_score", "risk_penalty", "priority_score",
        "top_reason_1", "top_reason_2", "top_reason_3",
        "primary_caution", "roi_report_template_flag",
    ]
    out = df[[c for c in output_cols if c in df.columns]].copy()

    # 13. Log results
    log.info("=== STREET RANKING RESULTS ===")
    for _, r in out.iterrows():
        log.info(
            f"[RANK #{int(r['rank'])}] {r['street_id']}: "
            f"base={r['base_score']:.4f} x "
            f"hp_mult={r['hp_modifier']:.2f} [{r.get('hp_opportunity_label','?')}] x "
            f"certainty={r['structural_certainty']:.2f} = ROI={r['final_score']:.4f} "
            f"| fern={r.get('heat_constraint_label','?')} "
            f"| deploy={r['deployment_score']:.3f} risk={r['risk_penalty']:.2f} "
            f"-> priority={r['priority_score']:.4f} "
            f"| template={r['roi_report_template_flag']}"
        )
        if r["top_reason_1"]:
            log.info(f"  Reason 1: {r['top_reason_1']}")
        if r["primary_caution"]:
            log.info(f"  Caution:  {r['primary_caution']}")

    # 14. Write output
    out.to_parquet(OUT_PATH, index=False)
    log.info(f"Output written: {OUT_PATH} ({len(out)} rows)")
    log.info("=== PV-Only Street Ranking Engine END ===")

    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    result = build_street_ranking()
    print(result[["rank", "street_id", "base_score", "final_score", "structural_certainty",
                  "roi_report_template_flag", "top_reason_1", "primary_caution"]].to_string())

