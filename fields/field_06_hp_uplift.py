"""
fields/field_06_hp_uplift.py
============================
Priority 2.5 — Heat Pump ROI Uplift Modifier
D-ESS / Neuss MVP

Reads:
  - data/layer2/layer2_prio2_heat_overlay.parquet   (Priority 2 output — read-only)
  - data/layer2/layer2_prio25_hp_input.json         (P2.5 tier assignments)

Outputs:
  - data/layer2/layer2_prio25_hp_uplift.parquet

Architecture: Multiplicative overlay — downstream of Layer 2 and Priority 2.
  final_score = prio2_adjusted_score * hp_modifier

Anti-double-counting gate:
  If fernwaerme_gate == BLOCKED: hp_modifier = 1.00 (no uplift, regardless of tier).
  BLOCKED is triggered by Priority 2 heat_status in {STRONG_DISTRICT_HEAT, PLANNED_DISTRICT_HEAT}.

UNKNOWN heating proxy rule:
  If hp_heating_proxy == UNKNOWN: maximum tier is LIMITED_HP_UPLIFT.
  UNKNOWN must NEVER silently flow into MODERATE or STRONG.
"""

from __future__ import annotations

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
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("field_06_hp_uplift")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE     = Path(__file__).resolve()
_BASE_DIR = _HERE.parent.parent           # d-ess-engine/

OVERLAY_P  = _BASE_DIR / "data" / "layer2" / "layer2_prio2_heat_overlay.parquet"
HP_INPUT_P = _BASE_DIR / "data" / "layer2" / "layer2_prio25_hp_input.json"
OUTPUT_P   = _BASE_DIR / "data" / "layer2" / "layer2_prio25_hp_uplift.parquet"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Fernwärme statuses that BLOCK HP uplift (anti-double-counting gate)
_BLOCKED_HEAT_STATUSES = {"STRONG_DISTRICT_HEAT", "PLANNED_DISTRICT_HEAT"}

# Modifier lookup per hp_status tier
_MODIFIER_MAP: dict[str, float] = {
    "STRONG_HP_UPLIFT":   1.15,
    "MODERATE_HP_UPLIFT": 1.08,
    "LIMITED_HP_UPLIFT":  1.00,
    "UNKNOWN":            1.00,
}

# Maximum achievable modifier (sanity cap)
_MAX_MODIFIER = 1.15


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _validate_hp_status_against_proxy(
    unit_id: str,
    hp_status: str,
    heating_proxy: str,
) -> str:
    """
    Enforce UNKNOWN heating proxy -> LIMITED_HP_UPLIFT rule.
    UNKNOWN must NEVER silently promote to MODERATE or STRONG.
    Returns the validated (possibly downgraded) hp_status.
    """
    if heating_proxy == "UNKNOWN" and hp_status in ("STRONG_HP_UPLIFT", "MODERATE_HP_UPLIFT"):
        log.warning(
            "[INTEGRITY VIOLATION] unit_id=%s: hp_status=%s but hp_heating_proxy=UNKNOWN. "
            "Downgrading to LIMITED_HP_UPLIFT per spec. "
            "Root cause: input JSON assigned MODERATE/STRONG without confirmed heating evidence.",
            unit_id, hp_status,
        )
        return "LIMITED_HP_UPLIFT"
    return hp_status


def _apply_modifier(
    unit_id: str,
    hp_status: str,
    fernwaerme_gate: str,
    prio2_adjusted_score: float,
) -> tuple[float, float, str]:
    """
    Apply multiplicative HP modifier with anti-double-counting gate.

    Returns:
      (hp_modifier, final_score_after_hp, decision_reason)
    """
    if fernwaerme_gate == "BLOCKED":
        modifier = 1.00
        reason = (
            f"BLOCKED by Fernwärme gate — prio2 heat_status indicates district heat. "
            f"Anti-double-counting: hp_modifier capped at 1.00 regardless of hp_status={hp_status}."
        )
        log.info("[GATE_BLOCKED] unit_id=%s: hp_modifier=1.00 (fernwaerme_gate=BLOCKED)", unit_id)
    else:
        modifier = _MODIFIER_MAP.get(hp_status, 1.00)
        if modifier > _MAX_MODIFIER:
            log.warning(
                "[CAP] unit_id=%s: modifier %s exceeds max %s — capping.",
                unit_id, modifier, _MAX_MODIFIER,
            )
            modifier = _MAX_MODIFIER
        reason = (
            f"fernwaerme_gate=COMPATIBLE, hp_status={hp_status} → hp_modifier={modifier:.2f}"
        )
        log.info(
            "[MODIFIER_APPLIED] unit_id=%s: gate=COMPATIBLE, status=%s, modifier=×%.2f",
            unit_id, hp_status, modifier,
        )

    final_score = round(prio2_adjusted_score * modifier, 6)
    return modifier, final_score, reason


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> None:
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info("=== field_06_hp_uplift START · %s ===", run_ts)

    # ── Guard: input files ────────────────────────────────────────────────
    if not OVERLAY_P.exists():
        log.error(
            "Priority 2 overlay not found at %s. "
            "Run scripts/field_05_heat_modifier.py first.",
            OVERLAY_P,
        )
        sys.exit(1)

    if not HP_INPUT_P.exists():
        log.error(
            "HP input JSON not found at %s. "
            "Create data/layer2/layer2_prio25_hp_input.json first.",
            HP_INPUT_P,
        )
        sys.exit(1)

    # ── Load P2 overlay (read-only) ───────────────────────────────────────
    log.info("Loading P2 overlay: %s", OVERLAY_P)
    p2_df = pd.read_parquet(OVERLAY_P)
    log.info(
        "P2 overlay loaded: %d rows, columns=%s",
        len(p2_df), list(p2_df.columns),
    )

    # Confirm required column exists
    required_cols = {"unit_id", "adjusted_score", "heat_status", "row_usable_for_ranking"}
    missing = required_cols - set(p2_df.columns)
    if missing:
        log.error(
            "P2 overlay missing required columns: %s. "
            "Cannot proceed — P2 schema may have changed.",
            missing,
        )
        sys.exit(1)

    # ── Load HP input JSON ────────────────────────────────────────────────
    log.info("Loading HP input JSON: %s", HP_INPUT_P)
    with open(HP_INPUT_P, encoding="utf-8") as f:
        hp_raw = json.load(f)

    schema_ver = hp_raw.get("_meta", {}).get("schema_version", "unknown")
    log.info("HP input schema_version: %s", schema_ver)

    hp_segments: dict[str, dict] = {
        seg["unit_id"]: seg for seg in hp_raw.get("segments", [])
    }
    log.info("HP input segments loaded: %s", list(hp_segments.keys()))

    # ── Build output rows ─────────────────────────────────────────────────
    output_rows: list[dict] = []

    for _, p2_row in p2_df.iterrows():
        unit_id   = str(p2_row["unit_id"])
        usable    = bool(p2_row["row_usable_for_ranking"])
        adj_score = float(p2_row["adjusted_score"])
        heat_stat = str(p2_row["heat_status"])

        if unit_id not in hp_segments:
            log.warning(
                "[NO_HP_INPUT] unit_id=%s not found in HP input JSON — "
                "assigning UNKNOWN tier, modifier=1.00",
                unit_id,
            )
            output_rows.append({
                "unit_id":               unit_id,
                "row_usable_for_ranking": usable,
                "prio2_adjusted_score":  adj_score,
                "hp_status":             "UNKNOWN",
                "hp_sfh_share":          None,
                "hp_fernwaerme_gate":    "UNKNOWN",
                "hp_heating_proxy":      "UNKNOWN",
                "hp_confidence":         0.0,
                "hp_modifier":           1.00,
                "final_score_after_hp":  adj_score,
                "hp_caveat":             "No HP input data provided for this segment.",
                "hp_sales_interpretation": "HP uplift unknown — no input data.",
                "hp_modifier_reason":    "No HP input — default 1.00",
                "build_timestamp_utc":   run_ts,
                "schema_version":        schema_ver,
            })
            continue

        hp_seg = hp_segments[unit_id]

        # Derive fernwaerme gate from P2 heat_status (NOT from json — single source of truth)
        fernwaerme_gate = (
            "BLOCKED" if heat_stat in _BLOCKED_HEAT_STATUSES else "COMPATIBLE"
        )
        if fernwaerme_gate != hp_seg.get("fernwaerme_gate", "COMPATIBLE"):
            log.warning(
                "[GATE_MISMATCH] unit_id=%s: JSON says fernwaerme_gate=%s but P2 heat_status=%s "
                "→ derived gate=%s takes precedence (P2 is authoritative).",
                unit_id,
                hp_seg.get("fernwaerme_gate"),
                heat_stat,
                fernwaerme_gate,
            )

        # Validate hp_status against heating proxy (ZERO_INFERENCE guard)
        raw_hp_status  = str(hp_seg.get("hp_status", "UNKNOWN"))
        heating_proxy  = str(hp_seg.get("hp_heating_proxy", "UNKNOWN"))
        hp_status      = _validate_hp_status_against_proxy(unit_id, raw_hp_status, heating_proxy)

        # Apply modifier with gate
        modifier, final_score, reason = _apply_modifier(
            unit_id, hp_status, fernwaerme_gate, adj_score
        )

        sfh_share = hp_seg.get("sfh_friendly_share")
        if sfh_share is not None:
            sfh_share = float(sfh_share)

        output_rows.append({
            "unit_id":                unit_id,
            "row_usable_for_ranking": usable,
            "prio2_adjusted_score":   adj_score,
            "hp_status":              hp_status,
            "hp_sfh_share":           sfh_share,
            "hp_fernwaerme_gate":     fernwaerme_gate,
            "hp_heating_proxy":       heating_proxy,
            "hp_confidence":          float(hp_seg.get("hp_confidence", 0.0)),
            "hp_modifier":            modifier,
            "final_score_after_hp":   final_score,
            "hp_caveat":              str(hp_seg.get("hp_caveat", "")),
            "hp_sales_interpretation": str(hp_seg.get("hp_sales_interpretation", "")),
            "hp_modifier_reason":     reason,
            "build_timestamp_utc":    run_ts,
            "schema_version":         schema_ver,
        })

    # ── Output dataframe ──────────────────────────────────────────────────
    out_df = pd.DataFrame(output_rows)

    # Sanity checks
    for _, row in out_df[out_df["row_usable_for_ranking"].astype(bool)].iterrows():  # LOW-04 FIX: avoid == True
        if row["hp_modifier"] > _MAX_MODIFIER:
            log.error(
                "[SANITY FAIL] unit_id=%s: hp_modifier=%s exceeds _MAX_MODIFIER=%s",
                row["unit_id"], row["hp_modifier"], _MAX_MODIFIER,
            )
            sys.exit(1)
        # BUG-03 FIX (2026-04-02): add 1e-9 tolerance — round(..., 6) can produce
        # final_score = prio2_score - ε (ε ≈ 1e-10) for modifier=1.00 (BLOCKED/LIMITED).
        # Strict < comparison caused false-positive sys.exit(1). Tolerance = 1e-9 >> ε.
        if row["final_score_after_hp"] < row["prio2_adjusted_score"] - 1e-9:
            log.error(
                "[SANITY FAIL] unit_id=%s: final_score_after_hp < prio2_adjusted_score "
                "(uplift modifier must never reduce score). "
                "final=%.6f, p2=%.6f",
                row["unit_id"], row["final_score_after_hp"], row["prio2_adjusted_score"],
            )
            sys.exit(1)
        log.info(
            "[SCORE_CHAIN] unit_id=%s: P2=%.4f × HP=%.2f = final=%.4f (status=%s, gate=%s)",
            row["unit_id"],
            row["prio2_adjusted_score"],
            row["hp_modifier"],
            row["final_score_after_hp"],
            row["hp_status"],
            row["hp_fernwaerme_gate"],
        )

    # ── Rank order check (NORF must stay #1) ─────────────────────────────
    usable_out = (
        out_df[out_df["row_usable_for_ranking"] == True]
        .sort_values("final_score_after_hp", ascending=False)
        .reset_index(drop=True)
    )
    if len(usable_out) > 0:
        top = usable_out.iloc[0]
        log.info(
            "[RANK_ORDER] Top segment after HP uplift: %s (final=%.4f, hp_status=%s, hp_modifier=%.2f)",
            top["unit_id"], top["final_score_after_hp"],
            top["hp_status"], top["hp_modifier"],
        )

    # ── Write output ──────────────────────────────────────────────────────
    OUTPUT_P.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(OUTPUT_P, index=False)
    log.info("Output written: %s (%d rows)", OUTPUT_P, len(out_df))
    log.info("=== field_06_hp_uplift COMPLETE ===")

    # Print summary table
    print("\n--- Priority 2.5 HP Uplift Summary ---")
    summary_cols = [
        "unit_id", "prio2_adjusted_score", "hp_status",
        "hp_fernwaerme_gate", "hp_modifier", "final_score_after_hp", "hp_confidence",
    ]
    available_cols = [c for c in summary_cols if c in out_df.columns]
    print(out_df[available_cols].to_string(index=False))
    print("--------------------------------------\n")


if __name__ == "__main__":
    run()
