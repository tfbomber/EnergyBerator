"""
tests/test_foundation_gate_phase15.py
=======================================
Phase 15 Finding A — Gate Calibration Tests

Verifies the separation of structural eligibility and execution scale.

Key behavioral change from Phase 15:
    - Small cluster + structurally good  -> PASS + APPEND_TO_AREA  (was FAIL before)
    - Large cluster + structurally good  -> PASS + STANDALONE
    - Small cluster + MFH-heavy          -> FAIL (structural, not size-driven)
    - Boundary mixed cluster             -> REVIEW (unchanged)
"""

import sys
import os
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, BASE_DIR)

from scripts.generate_foundation_layer import (
    apply_structure_gate,
    compute_execution_scale_flag,
    PASS_MAX_MFH_RATIO,
    PASS_MIN_SFH_RATIO,
    REVIEW_MAX_MFH_RATIO,
    STANDALONE_MIN_SIZE,
)


# ===========================
# STRUCTURAL GATE TESTS
# ===========================

class TestApplyStructureGate:

    def test_good_structure_passes(self):
        """Strong SFH, low MFH → PASS."""
        gate, reason = apply_structure_gate(mfh_ratio=0.10, sfh_total_ratio=0.75)
        assert gate == "PASS"
        assert reason == "LOW_MFH_HIGH_SFH"

    def test_high_mfh_fails(self):
        """MFH ratio too high → FAIL regardless of size."""
        gate, reason = apply_structure_gate(mfh_ratio=0.50, sfh_total_ratio=0.30)
        assert gate == "FAIL"
        assert reason == "MFH_RATIO_TOO_HIGH"

    def test_borderline_mixed_is_review(self):
        """Borderline cluster → REVIEW."""
        gate, reason = apply_structure_gate(mfh_ratio=0.30, sfh_total_ratio=0.45)
        assert gate == "REVIEW"
        assert reason == "BORDERLINE_MIXED_STREET"

    def test_exact_pass_boundary(self):
        """Exactly at PASS thresholds → PASS."""
        gate, reason = apply_structure_gate(
            mfh_ratio=PASS_MAX_MFH_RATIO,
            sfh_total_ratio=PASS_MIN_SFH_RATIO,
        )
        assert gate == "PASS"

    def test_exact_fail_boundary(self):
        """Exactly at REVIEW_MAX_MFH_RATIO + 0.001 → FAIL."""
        gate, reason = apply_structure_gate(
            mfh_ratio=REVIEW_MAX_MFH_RATIO + 0.001,
            sfh_total_ratio=0.20,
        )
        assert gate == "FAIL"

    def test_size_does_not_affect_gate(self):
        """
        CRITICAL Phase 15 test:
        Gate function signature no longer accepts building_count_total.
        Calling with only 2 args must succeed.
        """
        # This MUST not raise TypeError
        gate, reason = apply_structure_gate(mfh_ratio=0.10, sfh_total_ratio=0.80)
        assert gate == "PASS"


# ====================================
# EXECUTION SCALE FLAG TESTS
# ====================================

class TestComputeExecutionScaleFlag:

    def test_large_cluster_is_standalone(self):
        """Building count >= STANDALONE_MIN_SIZE → STANDALONE."""
        flag = compute_execution_scale_flag(STANDALONE_MIN_SIZE)
        assert flag == "STANDALONE"

    def test_large_cluster_above_threshold(self):
        flag = compute_execution_scale_flag(STANDALONE_MIN_SIZE + 50)
        assert flag == "STANDALONE"

    def test_small_cluster_is_append(self):
        """Building count < STANDALONE_MIN_SIZE → APPEND_TO_AREA."""
        flag = compute_execution_scale_flag(STANDALONE_MIN_SIZE - 1)
        assert flag == "APPEND_TO_AREA"

    def test_zero_buildings_is_append(self):
        """Edge case: zero buildings → APPEND_TO_AREA (not an error)."""
        flag = compute_execution_scale_flag(0)
        assert flag == "APPEND_TO_AREA"


# ====================================
# INTEGRATION: GATE + SCALE COMBINED
# ====================================

class TestGatePlusScaleIntegration:

    def test_small_structurally_strong_is_pass_append(self):
        """
        Phase 15 KEY TEST:
        Small cluster + good structure → PASS + APPEND_TO_AREA
        (Previously: FAIL + CLUSTER_TOO_SMALL — WRONG)
        """
        gate, reason = apply_structure_gate(mfh_ratio=0.05, sfh_total_ratio=0.85)
        scale = compute_execution_scale_flag(building_count_total=5)  # small!
        assert gate == "PASS", f"Expected PASS, got {gate}"
        assert scale == "APPEND_TO_AREA", f"Expected APPEND_TO_AREA, got {scale}"

    def test_large_structurally_strong_is_pass_standalone(self):
        """Large cluster + good structure → PASS + STANDALONE."""
        gate, _ = apply_structure_gate(mfh_ratio=0.10, sfh_total_ratio=0.70)
        scale = compute_execution_scale_flag(building_count_total=50)
        assert gate == "PASS"
        assert scale == "STANDALONE"

    def test_small_mfh_heavy_is_fail_append(self):
        """
        Small cluster + MFH-heavy → FAIL (structural) + APPEND_TO_AREA (scale).
        The FAIL must come from the structure, not from the size.
        """
        gate, reason = apply_structure_gate(mfh_ratio=0.55, sfh_total_ratio=0.20)
        scale = compute_execution_scale_flag(building_count_total=5)
        assert gate == "FAIL"
        assert reason == "MFH_RATIO_TOO_HIGH"  # NOT CLUSTER_TOO_SMALL
        assert scale == "APPEND_TO_AREA"

    def test_large_mfh_heavy_is_fail_standalone(self):
        """Large cluster + MFH-heavy → FAIL + STANDALONE (scale ok, structure bad)."""
        gate, reason = apply_structure_gate(mfh_ratio=0.55, sfh_total_ratio=0.20)
        scale = compute_execution_scale_flag(building_count_total=80)
        assert gate == "FAIL"
        assert scale == "STANDALONE"
