"""
tests/test_ranking_universe.py
================================
General Ranking — Universe Filter Test

Verifies:
1. Default PASS_ONLY excludes REVIEW and FAIL clusters.
2. PASS_PLUS_REVIEW includes REVIEW, excludes FAIL.
3. ranking_universe field matches the active mode.
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, BASE_DIR)

from tracks.general.ranking.pipeline import filter_universe


def _make_rec(cluster_id, gate):
    return {
        "cluster_id": cluster_id,
        "street_name": f"Street-{cluster_id}",
        "plz": "41464",
        "address_range": "1-10",
        "building_count_total": 30,
        "sfh_total_ratio": 0.60,
        "mfh_ratio": 0.20,
        "other_ratio": 0.20,
        "structure_profile": "MIXED_RESIDENTIAL",
        "structure_gate": gate,
        "gate_reason": "TEST",
    }


ALL_RECORDS = [
    _make_rec("P1", "PASS"),
    _make_rec("P2", "PASS"),
    _make_rec("R1", "REVIEW"),
    _make_rec("F1", "FAIL"),
]


def test_pass_only_default():
    """PASS_ONLY mode must include only PASS clusters."""
    filtered, label = filter_universe(ALL_RECORDS, "PASS_ONLY")
    ids = {r["cluster_id"] for r in filtered}
    assert ids == {"P1", "P2"}
    assert label == "PASS_ONLY"


def test_pass_plus_review():
    """PASS_PLUS_REVIEW must include PASS and REVIEW, excluding FAIL."""
    filtered, label = filter_universe(ALL_RECORDS, "PASS_PLUS_REVIEW")
    ids = {r["cluster_id"] for r in filtered}
    assert ids == {"P1", "P2", "R1"}
    assert "F1" not in ids
    assert label == "PASS_PLUS_REVIEW"


def test_fail_always_excluded():
    """FAIL clusters must never appear in any ranking universe."""
    for mode in ("PASS_ONLY", "PASS_PLUS_REVIEW"):
        filtered, _ = filter_universe(ALL_RECORDS, mode)
        ids = {r["cluster_id"] for r in filtered}
        assert "F1" not in ids, f"FAIL cluster found in {mode} universe"


def test_empty_universe_no_error():
    """All FAIL records should produce empty universe without crash."""
    all_fail = [_make_rec(f"F{i}", "FAIL") for i in range(5)]
    filtered, label = filter_universe(all_fail, "PASS_ONLY")
    assert filtered == []
    assert label == "PASS_ONLY"
