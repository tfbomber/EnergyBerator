"""
tracks/general/ranking/scoring.py
===================================
General Track — Ranking Score Computation

SCOPE: General Track only.
No PV logic. No heat-pump logic. No bundle logic. No probability claims.
No modification of General Foundation data.

Formula:
    general_rank_score =
        0.50 * normalized_structure_strength
      + 0.30 * normalized_scale
      + 0.20 * normalized_purity

Normalization: min-max within the active ranking universe (PASS or PASS+REVIEW).

If max == min for any dimension (zero variance), all values default to 0.5.
"""

from __future__ import annotations
from typing import List, Dict, Any

# --- Scoring Weights (from specification) ---
W_STRUCTURE = 0.50
W_SCALE = 0.30
W_PURITY = 0.20

# --- Primary Reason Thresholds ---
HIGH_SFH_THRESHOLD = 0.70
HIGH_SFH_MFH_CEILING = 0.15
TOP_QUARTILE_LABEL = "STRONG_SCALE"
LOW_OTHER_THRESHOLD = 0.10

# --- Secondary Reason Thresholds ---
MFH_DRAG_THRESHOLD = 0.20
HIGH_OTHER_THRESHOLD = 0.25


def _minmax_normalize(values: List[float]) -> List[float]:
    """Min-max normalize a list of floats to [0.0, 1.0].
    If zero-variance (max == min), returns 0.5 for all entries."""
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def compute_scores(clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Compute general_rank_score for each cluster in the ranking universe.

    Args:
        clusters: List of Foundation output records (already filtered by universe).

    Returns:
        Same list with added scoring fields:
            norm_structure, norm_scale, norm_purity, general_rank_score.
    """
    if not clusters:
        return []

    # Compute raw dimension values
    raw_structure = [
        max(0.0, float(c["sfh_total_ratio"]) - float(c["mfh_ratio"]))
        for c in clusters
    ]
    # Scale: use cluster_building_count (range-scoped, corrected in v2) when available.
    # Falls back to building_count_total for backward compatibility with pre-v2 data.
    raw_scale = [
        float(c.get("cluster_building_count") or c["building_count_total"])
        for c in clusters
    ]
    raw_purity = [1.0 - float(c["other_ratio"]) for c in clusters]

    # Normalize each dimension independently within the universe
    norm_structure = _minmax_normalize(raw_structure)
    norm_scale = _minmax_normalize(raw_scale)
    norm_purity = _minmax_normalize(raw_purity)

    # Quartile thresholds for reason strings
    sorted_scale = sorted(raw_scale)
    q25_scale = sorted_scale[max(0, int(len(sorted_scale) * 0.25) - 1)]
    q75_scale = sorted_scale[min(len(sorted_scale) - 1, int(len(sorted_scale) * 0.75))]

    enriched = []
    for i, c in enumerate(clusters):
        score = round(
            W_STRUCTURE * norm_structure[i]
            + W_SCALE * norm_scale[i]
            + W_PURITY * norm_purity[i],
            4
        )

        # Deterministic reason strings
        primary = _resolve_primary_reason(
            sfh_ratio=float(c["sfh_total_ratio"]),
            mfh_ratio=float(c["mfh_ratio"]),
            other_ratio=float(c["other_ratio"]),
            scale=float(c.get("cluster_building_count") or c["building_count_total"]),
            q75_scale=q75_scale,
        )
        secondary = _resolve_secondary_reason(
            mfh_ratio=float(c["mfh_ratio"]),
            other_ratio=float(c["other_ratio"]),
            scale=float(c.get("cluster_building_count") or c["building_count_total"]),
            q25_scale=q25_scale,
        )

        enriched.append({
            **c,
            "_norm_structure": round(norm_structure[i], 4),
            "_norm_scale": round(norm_scale[i], 4),
            "_norm_purity": round(norm_purity[i], 4),
            "general_rank_score": score,
            "ranking_reason_primary": primary,
            "ranking_reason_secondary": secondary,
        })

    return enriched


def _resolve_primary_reason(
    sfh_ratio: float,
    mfh_ratio: float,
    other_ratio: float,
    scale: float,
    q75_scale: float,
) -> str:
    """Return the single dominant positive driver for this cluster's rank."""
    if sfh_ratio >= HIGH_SFH_THRESHOLD and mfh_ratio <= HIGH_SFH_MFH_CEILING:
        return "HIGH_SFH_RATIO"
    if scale >= q75_scale:
        return "STRONG_SCALE"
    if other_ratio < LOW_OTHER_THRESHOLD:
        return "LOW_OTHER_RATIO"
    return "BALANCED_STRUCTURE"


def _resolve_secondary_reason(
    mfh_ratio: float,
    other_ratio: float,
    scale: float,
    q25_scale: float,
) -> str:
    """Return the single most notable limiting factor (or NONE)."""
    if mfh_ratio > MFH_DRAG_THRESHOLD:
        return "MFH_DRAG"
    if scale <= q25_scale:
        return "SMALL_CLUSTER"
    if other_ratio > HIGH_OTHER_THRESHOLD:
        return "HIGH_OTHER_SHARE"
    return "NONE"
