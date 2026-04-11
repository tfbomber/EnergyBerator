"""
confidence_rules.py
====================
Street Confidence Layer — Enhancement C
Date   : 2026-03-21
Version: Enhancement C (v5 Foundation)

PURPOSE
-------
Compute a descriptive reliability indicator (`street_confidence`) for each
street-level gate verdict produced by the Foundation Layer.

THIS MODULE IS METADATA-ONLY.
DO NOT USE `street_confidence` FOR:
  - gate decisions (PASS / QUALIFIED / REVIEW / FAIL)
  - ranking or score computation
  - sorting or filtering leads
  - any downstream prioritization

ANY CHANGE TO THRESHOLDS OR SEMANTICS MUST BE EXPLICITLY AUDITED.
Changes here may affect user-facing reliability labels across all streets.

DESIGN CONTRACT
---------------
- Pure function: compute_street_confidence() has no side effects.
- No imports from pipeline modules — this module is self-contained.
- Constants are prefixed CONF_* to distinguish from gate thresholds.
- Exports only compute_street_confidence() via __init__.py.
"""

# ---------------------------------------------------------------------------
# Threshold constants (confidence layer only — no gate coupling)
# ---------------------------------------------------------------------------
CONF_SIZE_HIGH    = 50    # total_buildings >= this → size signal = HIGH
CONF_SIZE_MEDIUM  = 20    # total_buildings >= this → size signal = MEDIUM (else LOW)
CONF_CONTAM_LIGHT = 0.10  # 0 < mfh_ratio <= this  → contamination = LIGHT (else MIXED)
CONF_AMB_LOW      = 0.20  # other_ratio < this      → ambiguity = LOW
CONF_AMB_HIGH     = 0.50  # other_ratio >= this     → ambiguity = HIGH


def compute_street_confidence(
    total_buildings: int,
    mfh_count: int,
    mfh_ratio: float,
    other_ratio: float,
) -> str:
    """
    Return a descriptive reliability label for a street-level gate verdict.

    Parameters
    ----------
    total_buildings : int   — total buildings on the street (all types)
    mfh_count       : int   — raw count of MFH-classified buildings
    mfh_ratio       : float — mfh_count / total_buildings
    other_ratio     : float — other_count / total_buildings (ambiguous buildings)

    Returns
    -------
    "HIGH" | "MEDIUM" | "LOW"

    Signal definitions
    ------------------
    Signal 1 — Sample size
      HIGH   : total_buildings >= 50
      MEDIUM : 20 <= total_buildings < 50
      LOW    : total_buildings < 20

    Signal 2 — MFH contamination
      CLEAN  : mfh_count == 0
      LIGHT  : 0 < mfh_ratio <= 0.10
      MIXED  : mfh_ratio > 0.10

    Signal 3 — Ambiguity (other_ratio)
      LOW    : other_ratio < 0.20
      MEDIUM : 0.20 <= other_ratio < 0.50
      HIGH   : other_ratio >= 0.50

    Final rule (priority order)
    ---------------------------
    HIGH   : size=HIGH  AND  amb=LOW   AND  contam=CLEAN
    LOW    : size=LOW   OR   amb=HIGH  OR   contam=MIXED
    MEDIUM : all remaining combinations
    """
    # Signal 1: Sample size
    if total_buildings >= CONF_SIZE_HIGH:
        size = "HIGH"
    elif total_buildings >= CONF_SIZE_MEDIUM:
        size = "MEDIUM"
    else:
        size = "LOW"

    # Signal 2: MFH contamination
    if mfh_count == 0:
        contam = "CLEAN"
    elif mfh_ratio <= CONF_CONTAM_LIGHT:
        contam = "LIGHT"
    else:
        contam = "MIXED"

    # Signal 3: Ambiguity
    if other_ratio < CONF_AMB_LOW:
        amb = "LOW"
    elif other_ratio < CONF_AMB_HIGH:
        amb = "MEDIUM"
    else:
        amb = "HIGH"

    # Final rule
    if size == "HIGH" and amb == "LOW" and contam == "CLEAN":
        return "HIGH"
    if size == "LOW" or amb == "HIGH" or contam == "MIXED":
        return "LOW"
    return "MEDIUM"
