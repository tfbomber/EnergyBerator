"""
explainer_rules.py
===================
Layer 1.5 — Explanation / Sales Translation Layer
Date   : 2026-03-21
Version: Layer 1.5 (v5 Foundation)

PURPOSE
-------
Translate existing Layer 1 structured signals into business-friendly
explanation fields for each street cluster. Used by Stadtwerk / installer
teams to understand why a street was classified as it was.

THIS MODULE IS METADATA-ONLY.
DO NOT USE ANY OUTPUT FIELD FROM THIS MODULE FOR:
  - gate decisions (PASS / QUALIFIED / REVIEW / FAIL)
  - ranking, scoring, or prioritization
  - sorting or filtering leads
  - any automated decision pipeline

ALL TEXT IS GENERATED FROM DETERMINISTIC RULE TEMPLATES.
No freeform/LLM-generated prose. All outputs are traceable to explicit rules.

DESIGN CONTRACT
---------------
- generate_explanation() is a pure function with no side effects.
- No imports from gate, ranking, or scoring modules.
- Exports only generate_explanation() via __init__.py.
- Constants prefixed EXPL_* to distinguish from gate/confidence constants.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Valid enum values for recommended_action
# ---------------------------------------------------------------------------
VALID_ACTIONS = {
    "DOOR_TO_DOOR",
    "SELECTIVE_OUTREACH",
    "INSTALLER_PARTNER_FOCUS",
    "MONITOR_ONLY",
    "DEPRIORITIZE",
}

# ---------------------------------------------------------------------------
# Thresholds (explainer-layer only — no gate coupling)
# ---------------------------------------------------------------------------
EXPL_SFH_STRONG    = 0.80   # sfh_ratio >= this → "strong" pattern
EXPL_SFH_MAJORITY  = 0.60   # sfh_ratio >= this → "majority" pattern
EXPL_MFH_VERY_LOW  = 0.10   # mfh_ratio <= this (>0) → "very low" label
EXPL_OTHER_CLEAR   = 0.20   # other_ratio < this → "clear composition"
EXPL_OTHER_ELEVATED = 0.30  # other_ratio >= this → elevated ambiguity flag
EXPL_MIN_BUILDINGS  = 50    # total_buildings >= → "well-represented"
EXPL_LARGE_STREET   = 80    # total_buildings >= → "large street"
EXPL_SMALL_STREET   = 20    # total_buildings < → "small street" risk flag


# ---------------------------------------------------------------------------
# A. Positive reason rules
# ---------------------------------------------------------------------------
def _build_top_reasons(
    sfh_ratio: float,
    mfh_ratio: float,
    other_ratio: float,
    total_buildings: int,
    street_confidence: str,
) -> list:
    reasons = []

    # SFH dominance
    if sfh_ratio >= EXPL_SFH_STRONG:
        reasons.append("Strong single-family housing pattern")
    elif sfh_ratio >= EXPL_SFH_MAJORITY:
        reasons.append("Majority single-family residential composition")

    # MFH absence / very low presence
    if mfh_ratio == 0.0:
        reasons.append("No multi-family buildings detected")
    elif mfh_ratio <= EXPL_MFH_VERY_LOW:
        reasons.append("Very low apartment presence")

    # Low ambiguity
    if other_ratio < EXPL_OTHER_CLEAR:
        reasons.append("Clear and consistent building composition")

    # Signal stability
    if total_buildings >= EXPL_MIN_BUILDINGS and street_confidence in {"HIGH", "MEDIUM"}:
        if "Well-represented" not in " ".join(reasons):  # avoid redundancy
            reasons.append("Well-represented street with stable signal")
    if total_buildings >= EXPL_LARGE_STREET:
        reasons.append("Large street area with broad coverage")

    # Cap at 3 bullets
    return reasons[:3]


# ---------------------------------------------------------------------------
# B. Risk flag rules
# ---------------------------------------------------------------------------
def _build_risk_flags(
    sfh_ratio: float,
    mfh_ratio: float,
    mfh_count: int,
    other_ratio: float,
    total_buildings: int,
    street_confidence: str,
    gate: str,
) -> list:
    flags = []

    if street_confidence == "LOW":
        flags.append("Low reliability — small sample or mixed signals")
    if mfh_ratio > EXPL_MFH_VERY_LOW:
        flags.append("Presence of multi-family buildings reduces fit")
    if other_ratio >= EXPL_OTHER_ELEVATED:
        flags.append("Elevated ambiguity — building classification unclear")
    if total_buildings < EXPL_SMALL_STREET:
        flags.append("Small street — pattern may not be representative")
    if gate == "QUALIFIED":
        flags.append("Pattern data is partially uncertain")

    return flags[:3]


# ---------------------------------------------------------------------------
# C. Recommended action + rationale
# ---------------------------------------------------------------------------
def _build_action(gate: str, street_confidence: str) -> tuple:
    """Returns (recommended_action, action_rationale)."""
    if gate == "PASS":
        if street_confidence == "HIGH":
            return (
                "DOOR_TO_DOOR",
                "Strong, verified SFH street — direct outreach is appropriate.",
            )
        else:  # MEDIUM or LOW
            return (
                "SELECTIVE_OUTREACH",
                "Good SFH pattern with moderate confidence — target selectively.",
            )

    if gate == "QUALIFIED":
        if street_confidence in {"HIGH", "MEDIUM"}:
            return (
                "INSTALLER_PARTNER_FOCUS",
                "Promising but uncertain — coordinate via installer partner.",
            )
        else:  # LOW
            return (
                "MONITOR_ONLY",
                "Pattern is unclear — monitor before committing resources.",
            )

    if gate == "REVIEW":
        return (
            "MONITOR_ONLY",
            "Mixed signals — not suitable for direct outreach at this stage.",
        )

    # FAIL
    return (
        "DEPRIORITIZE",
        "Apartment-dominated area — not aligned with SFH product.",
    )


# ---------------------------------------------------------------------------
# D. Sales story — gate-level fixed templates
# ---------------------------------------------------------------------------
_SALES_STORY_TEMPLATES = {
    "PASS": (
        "This street shows a strong single-family residential pattern "
        "and appears suitable for SFH-focused outreach."
    ),
    "QUALIFIED": (
        "This street appears primarily residential but contains some data "
        "uncertainty — a selective approach is advisable."
    ),
    "REVIEW": (
        "This street shows a mixed or unclear residential composition "
        "and should be approached with caution."
    ),
    "FAIL": (
        "This street is predominantly multi-family and is not well-suited "
        "for single-family product campaigns."
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_explanation(
    gate: str,
    street_confidence: str,
    sfh_ratio: float,
    mfh_ratio: float,
    mfh_count: int,
    other_ratio: float,
    total_buildings: int,
) -> dict:
    """
    Layer 1.5: generate business-friendly explanation for a street cluster.

    Parameters
    ----------
    gate              : "PASS" | "QUALIFIED" | "REVIEW" | "FAIL"
    street_confidence : "HIGH" | "MEDIUM" | "LOW"
    sfh_ratio         : sfh_total_count / total_buildings
    mfh_ratio         : mfh_count / total_buildings
    mfh_count         : raw MFH building count
    other_ratio       : other_count / total_buildings
    total_buildings   : total building count on street

    Returns
    -------
    dict with keys:
      top_reasons       : list[str]   — 0-3 positive bullets
      risk_flags        : list[str]   — 0-3 risk bullets
      recommended_action: str         — one of VALID_ACTIONS
      action_rationale  : str         — 1-sentence rationale
      sales_story       : str         — 1-sentence business narrative
    """
    top_reasons = _build_top_reasons(
        sfh_ratio, mfh_ratio, other_ratio, total_buildings, street_confidence
    )
    risk_flags = _build_risk_flags(
        sfh_ratio, mfh_ratio, mfh_count, other_ratio,
        total_buildings, street_confidence, gate
    )
    recommended_action, action_rationale = _build_action(gate, street_confidence)
    sales_story = _SALES_STORY_TEMPLATES.get(
        gate,
        "This street has an unclear residential pattern — further review is recommended.",
    )

    return {
        "top_reasons":        top_reasons,
        "risk_flags":         risk_flags,
        "recommended_action": recommended_action,
        "action_rationale":   action_rationale,
        "sales_story":        sales_story,
    }
