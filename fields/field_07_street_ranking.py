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
    "NEUSS_NORF_01":   "Allerheiligen / Rosellen (PLZ 41470)",
    # PLZ 41472: Holzheim, Grefrath, Speck, Hoisten
    "NEUSS_SUBURB_01": "Holzheim / Grefrath (PLZ 41472)",
    # PLZ 41464: Pomona, Westfeld, Augustinusviertel (not "Grimlinghausen" — corrected 2026-04-11)
    "NEUSS_GRIML_01":  "Pomona / Westfeld (PLZ 41464)",
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
# ---------------------------------------------------------------------------
TEMPLATE_MAP = {
    "STRONG_HP_UPLIFT":   "PV_HP_ENHANCED",
    "MODERATE_HP_UPLIFT": "PV_PLUS_HP_OPTIONAL",
    "LIMITED_HP_UPLIFT":  "PV_STANDARD",
    "UNKNOWN":            "PV_STANDARD",
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
    hp   = row.get("hp_status", "")
    heat = row.get("heat_status", "")
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

    if hp == "STRONG_HP_UPLIFT":
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

    # --- C: Constraints / caveats ---
    if heat in ("LIMITED_OR_UNCLEAR", "NETWORK_LIKELY"):
        c_reasons.append("District-heating planning risk — qualify before pitch")

    if hp == "LIMITED_HP_UPLIFT":
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
        "NEUSS_NORF_01":    "QUALITY_A",
        "NEUSS_SUBURB_01":  "QUALITY_B",
        "NEUSS_GRIML_01":   "QUALITY_B",
    }
    l2_usable["quality_tier"] = l2_usable["unit_id"].map(QUALITY_TIER_MAP).fillna("SYNTHETIC")

    log.info(f"Usable rows: L2={len(l2_usable)}, P2={len(p2_usable)}, P25={len(p25_usable)}")

    # 2. Join on unit_id
    # P2 parquet already contains accepted base_score (with tier discount applied upstream).
    # Do NOT recompute from raw inputs — Guardrail G3: do not redesign Layer 2 scoring.
    df = (
        p2_usable[["unit_id", "base_score", "heat_status", "heat_modifier"]]
        .merge(
            p25_usable[["unit_id", "hp_status", "hp_modifier", "hp_confidence"]],
            on="unit_id", how="inner"
        )
        .merge(
            l2_usable[[c for c in [
                "unit_id",
                "effective_sfh_share",   # conservative ranking field (Stage 1 confirmed)
                "sfh_confirmed_share",   # for UI display
                "mfh_confirmed_share",   # for UI display
                "uncertain_share",       # for UI display
                "sfh_friendly_share",    # legacy (retained for audit)
                "roof_suitability_score", "roof_suitability_score_norm",
                "pv_coverage_score", "pct_l1_gate_pass",
                "l1_gate_label",         # for deployment score [Fix 3]
                "dominant_form", "quality_tier"
            ] if c in l2_usable.columns]],
            on="unit_id", how="inner"
        )
    )
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

    # 4. Constraint layer (P2)
    df["fernwaerme_modifier"] = df["heat_modifier"]
    df["constraint_score"]    = (df["base_score"] * df["fernwaerme_modifier"]).round(4)

    # 5. Uplift layer (P2.5)
    df["final_score"] = (df["constraint_score"] * df["hp_modifier"]).round(4)

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
    # risk_penalty: data uncertainty reduces confidence in both ROI and deployment
    # Capped at 0.50 so a genuinely uncertain area still gets a non-zero priority
    df["risk_penalty"]     = (df["truly_uncertain_share"] * 0.30).clip(0.0, 0.50).round(4)
    # priority_score: the single number that drives the ACTION_LABEL in the UI
    # It is NOT the same as final_score (ROI). It encodes: is this area ready to act on NOW?
    df["priority_score"]   = (
        df["final_score"] * df["deployment_score"] * (1.0 - df["risk_penalty"])
    ).round(4)
    log.info(
        "[PRIORITY_SCORES] ROI / Deployment / Risk / Priority:\n%s",
        df[["unit_id", "final_score", "deployment_score", "risk_penalty", "priority_score"]].to_string(index=False),
    )
    log.info(
        "[UNCERTAINTY_PENALTY] α=%.2f | Using truly_uncertain_share (Stage-2 = known):\n%s",
        UNCERTAINTY_PENALTY_ALPHA,
        df[["unit_id", "sfh_friendly_share", "truly_uncertain_share",
            "structural_certainty", "final_score"]].to_string(index=False)
    )

    # 6. Sanity checks
    assert (df["constraint_score"] <= df["base_score"] + 0.0002).all(), \
        "[FAIL] P2 not monotonic — constraint_score > base_score"
    # Note: final_score may be < constraint_score due to structural_certainty penalty (expected)
    assert (df["hp_modifier"] <= 1.15 + 0.0001).all(), \
        "[FAIL] hp_modifier exceeds cap"
    assert (df["structural_certainty"] >= 0.0).all() and (df["structural_certainty"] <= 1.0).all(), \
        "[FAIL] structural_certainty out of [0,1] range"
    log.info("[SANITY] P2 monotonic ✅ | hp_modifier cap ✅ | structural_certainty range ✅")


    # 7. Reason engine
    reasons = df.apply(_generate_reasons, axis=1, result_type="expand")
    reasons.columns = ["top_reason_1", "top_reason_2", "top_reason_3", "primary_caution"]
    df = pd.concat([df.reset_index(drop=True), reasons.reset_index(drop=True)], axis=1)

    # 8. Template routing
    df["roi_report_template_flag"] = df["hp_status"].map(TEMPLATE_MAP).fillna("PV_STANDARD")

    # 9. Street labels
    df["street_name"] = df["unit_id"].map(STREET_LABEL_MAP).fillna(df["unit_id"])
    df["street_id"]   = df["unit_id"]

    # 10. Rank
    df = df.sort_values("final_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # 11. Confidence
    df["confidence"] = df["hp_confidence"].round(2)

    # 12. Select output columns
    output_cols = [
        "rank", "street_id", "street_name",
        "base_score", "constraint_score", "final_score",
        "fernwaerme_modifier", "hp_modifier", "confidence",
        "heat_status", "hp_status",
        # L2 display fields (for UI signal row)
        "effective_sfh_share",     # used for ranking formula
        "sfh_confirmed_share",     # Stage-1 OSM adjacency (hard-verified)
        "sfh_proxy_only_share",    # Stage-2 footprint only [Fix 1]
        "sfh_friendly_share",      # Stage 1+2 combined (legacy, audit only)
        "mfh_confirmed_share", "uncertain_share",
        "truly_uncertain_share",   # = 1 - sfh_friendly - mfh_confirmed
        "structural_certainty",
        "pv_coverage_score", "roof_suitability_score_norm",
        "l1_gate_label",           # deployment score audit [Fix 3]
        # Priority scoring triad (Fix 3)
        "deployment_score", "risk_penalty", "priority_score",
        "top_reason_1", "top_reason_2", "top_reason_3",
        "primary_caution", "roi_report_template_flag",
    ]
    out = df[output_cols].copy()

    # 13. Log results
    log.info("=== STREET RANKING RESULTS ===")
    for _, r in out.iterrows():
        log.info(
            f"[RANK #{int(r['rank'])}] {r['street_id']}: "
            f"base={r['base_score']:.4f} × "
            f"fern×{r['fernwaerme_modifier']:.2f} × "
            f"hp×{r['hp_modifier']:.2f} × "
            f"certainty×{r['structural_certainty']:.2f} = ROI={r['final_score']:.4f} "
            f"| deploy={r['deployment_score']:.3f} risk={r['risk_penalty']:.2f} "
            f"→ priority={r['priority_score']:.4f} "
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

