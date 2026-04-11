"""
tracks/general/ranking/banding.py
===================================
General Track — Banding Logic

Fixed threshold design (not percentile-based) for reproducibility.

Thresholds (from specification):
    HIGH   : general_rank_score >= 0.65
    MEDIUM : 0.35 <= general_rank_score < 0.65
    LOW    : general_rank_score < 0.35

No external dependencies.
"""

from __future__ import annotations

BAND_HIGH_THRESHOLD = 0.65
BAND_MEDIUM_THRESHOLD = 0.35


def assign_band(score: float) -> str:
    """
    Assign a band label based on general_rank_score.

    Args:
        score: float in [0.0, 1.0]

    Returns:
        "HIGH" | "MEDIUM" | "LOW"
    """
    if score >= BAND_HIGH_THRESHOLD:
        return "HIGH"
    if score >= BAND_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def apply_banding(clusters: list[dict]) -> list[dict]:
    """
    Add 'general_band' field to each cluster record.
    Also assigns 'general_rank' (1-indexed, 1 = highest score).
    Sorts by score descending before assigning rank.

    Args:
        clusters: List of records with 'general_rank_score' field.

    Returns:
        Sorted list with 'general_band' and 'general_rank' added.
    """
    sorted_clusters = sorted(clusters, key=lambda c: c["general_rank_score"], reverse=True)
    for rank_idx, c in enumerate(sorted_clusters, start=1):
        c["general_band"] = assign_band(c["general_rank_score"])
        c["general_rank"] = rank_idx
    return sorted_clusters
