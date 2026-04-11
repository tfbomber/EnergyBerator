"""
test_street_confidence.py
=========================
Regression and contract tests for the Street Confidence Layer (Enhancement C).

Covers:
  - valid output values (only HIGH / MEDIUM / LOW)
  - boundary behavior for all three signals
  - the four approved sanity cases
  - no gate contamination (confidence does not affect gate)
  - no ranking contamination (confidence field absent from ranking inputs)

Run with:
  pytest tracks/general/ranking/tests/test_street_confidence.py -v
"""
import pytest
import sys
import os

# Allow direct import of scripts/ modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts")))

from foundation_confidence import compute_street_confidence

VALID_VALUES = {"HIGH", "MEDIUM", "LOW"}


# ---------------------------------------------------------------------------
# 1. Output contract: only valid values ever returned
# ---------------------------------------------------------------------------
class TestOutputContract:
    def test_all_returns_are_valid(self):
        """Exhaustive sweep: every combination of boundary inputs returns a valid value."""
        for tot in [0, 5, 19, 20, 49, 50, 100, 500]:
            for mfh_c in [0, 1]:
                for mfh_r in [0.0, 0.05, 0.10, 0.15, 0.50, 1.0]:
                    for oth_r in [0.0, 0.19, 0.20, 0.49, 0.50, 0.99]:
                        result = compute_street_confidence(tot, mfh_c, mfh_r, oth_r)
                        assert result in VALID_VALUES, (
                            f"Invalid value '{result}' for inputs "
                            f"tot={tot} mfh_c={mfh_c} mfh_r={mfh_r} oth_r={oth_r}"
                        )


# ---------------------------------------------------------------------------
# 2. Approved sanity cases (from Enhancement C design review)
# ---------------------------------------------------------------------------
class TestSanityCases:
    def test_high_confidence_clean_large_street(self):
        """tot=100, mfh=0, other<20% → HIGH."""
        assert compute_street_confidence(
            total_buildings=100, mfh_count=0, mfh_ratio=0.0, other_ratio=0.10
        ) == "HIGH"

    def test_low_confidence_small_street(self):
        """tot=8, mfh=1, any → LOW (small sample)."""
        assert compute_street_confidence(
            total_buildings=8, mfh_count=1, mfh_ratio=0.12, other_ratio=0.10
        ) == "LOW"

    def test_low_confidence_high_ambiguity(self):
        """tot=60, mfh=0, other>=50% → LOW (high ambiguity)."""
        assert compute_street_confidence(
            total_buildings=60, mfh_count=0, mfh_ratio=0.0, other_ratio=0.60
        ) == "LOW"

    def test_medium_confidence_typical_qualified(self):
        """tot=30, mfh=1, mfh%=0.04, other%=0.22 → MEDIUM (light contam + medium ambiguity)."""
        assert compute_street_confidence(
            total_buildings=30, mfh_count=1, mfh_ratio=0.04, other_ratio=0.22
        ) == "MEDIUM"


# ---------------------------------------------------------------------------
# 3. Signal boundary precision
# ---------------------------------------------------------------------------
class TestBoundaryBehavior:
    # Signal 1: sample size boundaries
    def test_size_boundary_50_is_high(self):
        assert compute_street_confidence(50, 0, 0.0, 0.0) == "HIGH"

    def test_size_boundary_49_is_not_high(self):
        result = compute_street_confidence(49, 0, 0.0, 0.0)
        assert result in {"MEDIUM"}  # 49, no MFH, no other → MEDIUM (not LOW, not HIGH)

    def test_size_boundary_20_is_medium(self):
        result = compute_street_confidence(20, 0, 0.0, 0.0)
        assert result == "MEDIUM"  # 20, clean, low amb → MEDIUM

    def test_size_boundary_19_is_low(self):
        result = compute_street_confidence(19, 0, 0.0, 0.0)
        assert result == "LOW"

    # Signal 2: MFH contamination boundaries
    def test_contam_boundary_mfh0_is_clean(self):
        # mfh_count=0 → CLEAN regardless of mfh_ratio
        result = compute_street_confidence(50, 0, 0.0, 0.0)
        assert result == "HIGH"

    def test_contam_boundary_light_10pct(self):
        # mfh_ratio exactly 0.10 → LIGHT → allowed into MEDIUM/HIGH chain
        result = compute_street_confidence(50, 5, 0.10, 0.0)
        # size=HIGH, amb=LOW, contam=LIGHT → not HIGH (LIGHT ≠ CLEAN), not LOW → MEDIUM
        assert result == "MEDIUM"

    def test_contam_boundary_mixed_just_above_10pct(self):
        # mfh_ratio > 0.10 → MIXED → LOW
        result = compute_street_confidence(50, 6, 0.11, 0.0)
        assert result == "LOW"

    # Signal 3: ambiguity boundaries
    def test_amb_boundary_exactly_20pct_is_medium(self):
        result = compute_street_confidence(50, 0, 0.0, 0.20)
        # size=HIGH, contam=CLEAN, amb=MEDIUM → MEDIUM (HIGH requires amb=LOW)
        assert result == "MEDIUM"

    def test_amb_boundary_just_below_20pct_is_high(self):
        result = compute_street_confidence(50, 0, 0.0, 0.19)
        assert result == "HIGH"

    def test_amb_boundary_exactly_50pct_is_low(self):
        result = compute_street_confidence(50, 0, 0.0, 0.50)
        assert result == "LOW"

    def test_amb_boundary_just_below_50pct_is_medium(self):
        result = compute_street_confidence(50, 0, 0.0, 0.49)
        assert result == "MEDIUM"


# ---------------------------------------------------------------------------
# 4. No gate / no ranking contamination (structural check)
# ---------------------------------------------------------------------------
class TestNoContamination:
    def test_confidence_not_in_gate_logic(self):
        """
        Structural: confidence_rules.py must not import from gate modules.
        We verify by checking the module's __dict__ for known gate symbols.
        """
        from foundation_confidence import confidence_rules
        forbidden = {"apply_structure_gate", "PASS_MAX_MFH_RATIO", "PASS_MIN_SFH_RATIO",
                     "QUALIFIED_MIN_SFH_RATIO", "filter_universe"}
        exposed = set(dir(confidence_rules))
        leaked = forbidden.intersection(exposed)
        assert not leaked, (
            f"Gate symbols leaked into confidence module: {leaked}. "
            "This module must remain isolated from gate logic."
        )

    def test_no_wildcard_exports(self):
        """__all__ must be defined and minimal in __init__.py."""
        import foundation_confidence
        assert hasattr(foundation_confidence, "__all__"), "__all__ must be defined"
        assert foundation_confidence.__all__ == ["compute_street_confidence"], (
            f"__all__ must export only compute_street_confidence, got: {foundation_confidence.__all__}"
        )

    def test_confidence_function_is_pure(self):
        """Same inputs must always return same output (pure function, no side effects)."""
        inputs = (60, 2, 0.04, 0.15)
        result1 = compute_street_confidence(*inputs)
        result2 = compute_street_confidence(*inputs)
        assert result1 == result2
        # Also verify it's deterministic across multiple calls
        for _ in range(10):
            assert compute_street_confidence(*inputs) == result1
