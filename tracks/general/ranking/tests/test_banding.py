"""
tests/test_banding.py
======================
General Ranking — Banding Logic Test

Verifies fixed-threshold band assignment including exact boundary values.
"""

import sys
import os
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, BASE_DIR)

from tracks.general.ranking.banding import assign_band, apply_banding


def test_high_band():
    assert assign_band(0.70) == "HIGH"
    assert assign_band(1.00) == "HIGH"


def test_medium_band():
    assert assign_band(0.50) == "MEDIUM"
    assert assign_band(0.40) == "MEDIUM"


def test_low_band():
    assert assign_band(0.20) == "LOW"
    assert assign_band(0.00) == "LOW"


def test_exact_high_boundary():
    """Score of exactly 0.65 must map to HIGH."""
    assert assign_band(0.65) == "HIGH"


def test_exact_medium_boundary():
    """Score of exactly 0.35 must map to MEDIUM."""
    assert assign_band(0.35) == "MEDIUM"


def test_just_below_high():
    """Score of 0.6499 must map to MEDIUM."""
    assert assign_band(0.6499) == "MEDIUM"


def test_just_below_medium():
    """Score of 0.3499 must map to LOW."""
    assert assign_band(0.3499) == "LOW"


def test_apply_banding_assigns_rank():
    """apply_banding must assign general_rank starting from 1 (highest score)."""
    records = [
        {"cluster_id": "A", "general_rank_score": 0.80, "ranking_reason_primary": "X", "ranking_reason_secondary": "Y"},
        {"cluster_id": "B", "general_rank_score": 0.50, "ranking_reason_primary": "X", "ranking_reason_secondary": "Y"},
        {"cluster_id": "C", "general_rank_score": 0.20, "ranking_reason_primary": "X", "ranking_reason_secondary": "Y"},
    ]
    result = apply_banding(records)
    by_id = {r["cluster_id"]: r for r in result}
    assert by_id["A"]["general_rank"] == 1
    assert by_id["B"]["general_rank"] == 2
    assert by_id["C"]["general_rank"] == 3
    assert by_id["A"]["general_band"] == "HIGH"
    assert by_id["B"]["general_band"] == "MEDIUM"
    assert by_id["C"]["general_band"] == "LOW"
