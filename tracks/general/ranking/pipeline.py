"""
tracks/general/ranking/pipeline.py
====================================
General Track — Ranking Pipeline Orchestrator

SCOPE: General Track only.
- Reads General Foundation output (read-only).
- Applies scoring and banding.
- Writes General Ranking output to a SEPARATE file.
- Does NOT modify any Foundation file.

Usage:
    python tracks/general/ranking/pipeline.py
    python tracks/general/ranking/pipeline.py --universe PASS_PLUS_REVIEW
"""

from __future__ import annotations

import os
import sys
import json
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s"
)
logger = logging.getLogger("GeneralRanking")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Ensure d-ess-engine root is on sys.path so `tracks.*` package is importable
# regardless of which directory the script is called from.
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

FOUNDATION_INPUT_PATH = os.path.join(BASE_DIR, "output", "foundation", "foundation_structure_results.json")
RANKING_OUTPUT_PATH = os.path.join(BASE_DIR, "output", "ranking", "general_ranking_results.json")

# Required fields from Foundation contract
REQUIRED_FOUNDATION_FIELDS = [
    "cluster_id", "street_name", "plz", "address_range",
    "building_count_total", "sfh_total_ratio", "mfh_ratio",
    "other_ratio", "structure_profile", "structure_gate", "gate_reason"
]

# Fields that must NOT appear in foundation input (contamination guard)
FORBIDDEN_RANKING_FIELDS = ["general_rank_score", "general_rank", "general_band"]


def load_foundation(path: str) -> list[dict]:
    """Load and validate Foundation output. Fails fast on schema violation."""
    if not os.path.exists(path):
        logger.error(f"Foundation input not found: {path}")
        logger.error("Please run scripts/generate_foundation_layer.py first.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        logger.warning("Foundation file is empty. No clusters to rank.")
        return []

    # Input contract validation
    for field in REQUIRED_FOUNDATION_FIELDS:
        if field not in data[0]:
            logger.error(f"[CONTRACT VIOLATION] Required field '{field}' missing from Foundation output.")
            sys.exit(1)

    # Contamination guard
    for forbidden in FORBIDDEN_RANKING_FIELDS:
        if forbidden in data[0]:
            logger.error(f"[CONTAMINATION DETECTED] Ranking field '{forbidden}' found in Foundation output.")
            logger.error("Foundation output has been incorrectly modified. Aborting.")
            sys.exit(1)

    logger.info(f"Loaded {len(data)} Foundation records from {path}")
    return data


def filter_universe(data: list[dict], mode: str) -> tuple[list[dict], str]:
    """Filter to PASS or PASS+REVIEW clusters.

    Gate semantics:
      PASS      → ranked in PASS_ONLY and PASS_PLUS_REVIEW
      QUALIFIED → NOT in PASS_ONLY (data uncertainty too high for clean ranking)
                  Included in PASS_PLUS_REVIEW for exploratory analysis only
      REVIEW    → only in PASS_PLUS_REVIEW
      FAIL      → never included
    """
    if mode == "PASS_PLUS_REVIEW":
        filtered = [c for c in data if c["structure_gate"] in ("PASS", "QUALIFIED", "REVIEW")]
        universe_label = "PASS_PLUS_REVIEW"
    else:
        # PASS_ONLY: strict — only clean PASS streets
        filtered = [c for c in data if c["structure_gate"] == "PASS"]
        universe_label = "PASS_ONLY"

    logger.info(f"Ranking universe: {universe_label} → {len(filtered)} clusters selected.")
    if not filtered:
        logger.warning("Ranking universe is empty! Check if Foundation data contains any PASS clusters.")
    return filtered, universe_label


def strip_internal_fields(records: list[dict]) -> list[dict]:
    """Remove internal scoring fields (prefixed with _) before writing output."""
    return [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in records
    ]


def build_output_records(
    scored_ranked: list[dict],
    universe_label: str,
) -> list[dict]:
    """Assemble exact output schema records (General Ranking contract only)."""
    output = []
    for r in scored_ranked:
        output.append({
            "cluster_id": r["cluster_id"],
            "street_name": r["street_name"],
            "plz": r["plz"],
            "address_range": r["address_range"],
            "building_count_total": r["building_count_total"],
            "sfh_total_ratio": r["sfh_total_ratio"],
            "mfh_ratio": r["mfh_ratio"],
            "other_ratio": r["other_ratio"],
            "structure_profile": r["structure_profile"],
            "structure_gate": r["structure_gate"],
            "gate_reason": r["gate_reason"],
            "general_rank_score": r["general_rank_score"],
            "general_rank": r["general_rank"],
            "general_band": r["general_band"],
            "ranking_reason_primary": r["ranking_reason_primary"],
            "ranking_reason_secondary": r["ranking_reason_secondary"],
            "ranking_universe": universe_label,
        })
    return output


def main():
    parser = argparse.ArgumentParser(description="General Track Ranking Pipeline")
    parser.add_argument(
        "--universe",
        choices=["PASS_ONLY", "PASS_PLUS_REVIEW"],
        default="PASS_ONLY",
        help="Ranking universe mode. Default: PASS_ONLY.",
    )
    args = parser.parse_args()

    logger.info("=== General Track Ranking Pipeline ===")
    logger.info(f"Mode: {args.universe}")

    # 1. Load Foundation (read-only)
    foundation_data = load_foundation(FOUNDATION_INPUT_PATH)

    # 2. Filter universe
    universe, universe_label = filter_universe(foundation_data, args.universe)
    if not universe:
        logger.warning("No clusters to rank. Writing empty output.")
        os.makedirs(os.path.dirname(RANKING_OUTPUT_PATH), exist_ok=True)
        with open(RANKING_OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        return

    # 3. Compute scores (adds general_rank_score + reason strings)
    from tracks.general.ranking.scoring import compute_scores
    scored = compute_scores(universe)

    # 4. Apply banding + ranking (adds general_band + general_rank)
    from tracks.general.ranking.banding import apply_banding
    ranked = apply_banding(scored)

    # 5. Build clean output records (exact contract schema)
    output_records = build_output_records(ranked, universe_label)

    # 6. Write to SEPARATE output file (NOT the foundation file)
    os.makedirs(os.path.dirname(RANKING_OUTPUT_PATH), exist_ok=True)
    with open(RANKING_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output_records, f, ensure_ascii=False, indent=2)

    # Summary
    high_c = sum(1 for r in output_records if r["general_band"] == "HIGH")
    med_c = sum(1 for r in output_records if r["general_band"] == "MEDIUM")
    low_c = sum(1 for r in output_records if r["general_band"] == "LOW")
    scores = [r["general_rank_score"] for r in output_records]

    logger.info("=== General Ranking Summary ===")
    logger.info(f"  Universe : {universe_label}")
    logger.info(f"  Ranked   : {len(output_records)}")
    logger.info(f"  HIGH     : {high_c}")
    logger.info(f"  MEDIUM   : {med_c}")
    logger.info(f"  LOW      : {low_c}")
    logger.info(f"  Score range: [{min(scores):.4f}, {max(scores):.4f}]")
    logger.info(f"  Output   : {RANKING_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
