"""
tests/test_scoring.py
======================
General Ranking — Scoring Logic Test

Verifies:
1. Deterministic score computation.
2. Score is within [0.0, 1.0].
3. Exact values match expected for known inputs.
"""

import sys
import os
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, BASE_DIR)

from tracks.general.ranking.scoring import compute_scores


def _make_cluster(cluster_id, sfh, mfh, other, building_count):
    """Helper: create a minimal Foundation-compatible record."""
    return {
        "cluster_id": cluster_id,
        "street_name": f"Street {cluster_id}",
        "plz": "41464",
        "address_range": "1 - 10",
        "building_count_total": building_count,
        "sfh_total_ratio": sfh,
        "mfh_ratio": mfh,
        "other_ratio": other,
        "structure_profile": "SFH_DOMINANT",
        "structure_gate": "PASS",
        "gate_reason": "LOW_MFH_HIGH_SFH",
    }


SAMPLE_CLUSTERS = [
    _make_cluster("A", sfh=0.90, mfh=0.05, other=0.05, building_count=100),  # Strong SFH, large
    _make_cluster("B", sfh=0.70, mfh=0.15, other=0.15, building_count=60),
    _make_cluster("C", sfh=0.55, mfh=0.20, other=0.25, building_count=40),
    _make_cluster("D", sfh=0.55, mfh=0.24, other=0.21, building_count=20),
    _make_cluster("E", sfh=0.50, mfh=0.24, other=0.26, building_count=15),  # Marginal
]


def test_scores_within_range():
    """All scores must be in [0.0, 1.0]."""
    results = compute_scores(SAMPLE_CLUSTERS)
    for r in results:
        score = r["general_rank_score"]
        assert 0.0 <= score <= 1.0, f"Score {score} out of range for cluster {r['cluster_id']}"


def test_score_determinism():
    """Same input always produces same output."""
    results_1 = compute_scores(SAMPLE_CLUSTERS)
    results_2 = compute_scores(SAMPLE_CLUSTERS)
    for r1, r2 in zip(results_1, results_2):
        assert r1["general_rank_score"] == r2["general_rank_score"], (
            f"Non-deterministic score for cluster {r1['cluster_id']}"
        )


def test_ordering_is_sensible():
    """Cluster A (best SFH, largest) should score higher than Cluster E (marginal)."""
    results = {r["cluster_id"]: r["general_rank_score"] for r in compute_scores(SAMPLE_CLUSTERS)}
    assert results["A"] > results["E"], "Expected A (strong) to score above E (marginal)"


def test_empty_input():
    """Empty input should return empty list without error."""
    result = compute_scores([])
    assert result == []


def test_single_cluster_variance_collapse():
    """Single cluster: all normalized values should be 0.5 (zero variance)."""
    single = [_make_cluster("X", sfh=0.75, mfh=0.10, other=0.15, building_count=50)]
    results = compute_scores(single)
    assert len(results) == 1
    score = results[0]["general_rank_score"]
    # With all dims at 0.5: 0.50*0.5 + 0.30*0.5 + 0.20*0.5 = 0.5
    assert abs(score - 0.5) < 0.001, f"Expected 0.5 for single-cluster universe, got {score}"
