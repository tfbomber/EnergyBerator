"""
test_street_explainer.py
========================
Tests for the Layer 1.5 Explanation / Sales Translation Layer.

Covers:
  - TestOutputContract     : 5 fields always present, action is valid enum
  - TestActionMapping      : gate + confidence → correct action (7 sanity cases)
  - TestDeterminism        : same inputs → same outputs (pure function check)
  - TestNoContamination    : gate/ranking/confidence fields not modified

Run with:
  pytest tracks/general/ranking/tests/test_street_explainer.py -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts")))

from foundation_explainer import generate_explanation

VALID_ACTIONS = {
    "DOOR_TO_DOOR",
    "SELECTIVE_OUTREACH",
    "INSTALLER_PARTNER_FOCUS",
    "MONITOR_ONLY",
    "DEPRIORITIZE",
}

REQUIRED_FIELDS = {
    "top_reasons", "risk_flags", "recommended_action",
    "action_rationale", "sales_story",
}

# Shared helper: build a standard call
def _explain(gate, conf, sfh=0.85, mfh=0.0, mfh_c=0, oth=0.05, tot=60):
    return generate_explanation(
        gate=gate, street_confidence=conf,
        sfh_ratio=sfh, mfh_ratio=mfh, mfh_count=mfh_c,
        other_ratio=oth, total_buildings=tot,
    )


# ---------------------------------------------------------------------------
# 1. Output contract
# ---------------------------------------------------------------------------
class TestOutputContract:
    def test_all_fields_present_for_pass(self):
        out = _explain("PASS", "HIGH")
        assert REQUIRED_FIELDS == set(out.keys())

    def test_all_fields_present_for_fail(self):
        out = _explain("FAIL", "LOW", sfh=0.0, mfh=0.70, mfh_c=50, oth=0.20)
        assert REQUIRED_FIELDS == set(out.keys())

    def test_action_is_valid_enum_always(self):
        for gate in ["PASS", "QUALIFIED", "REVIEW", "FAIL"]:
            for conf in ["HIGH", "MEDIUM", "LOW"]:
                out = _explain(gate, conf)
                assert out["recommended_action"] in VALID_ACTIONS, (
                    f"Invalid action '{out['recommended_action']}' for gate={gate} conf={conf}"
                )

    def test_top_reasons_is_list(self):
        out = _explain("PASS", "HIGH")
        assert isinstance(out["top_reasons"], list)

    def test_risk_flags_is_list(self):
        out = _explain("PASS", "HIGH")
        assert isinstance(out["risk_flags"], list)

    def test_top_reasons_max_3(self):
        for gate in ["PASS", "QUALIFIED", "REVIEW", "FAIL"]:
            out = _explain(gate, "HIGH")
            assert len(out["top_reasons"]) <= 3

    def test_risk_flags_max_3(self):
        for gate in ["PASS", "QUALIFIED", "REVIEW", "FAIL"]:
            out = _explain(gate, "LOW", mfh=0.15, mfh_c=5, oth=0.40, tot=10)
            assert len(out["risk_flags"]) <= 3

    def test_action_rationale_is_nonempty_string(self):
        out = _explain("PASS", "MEDIUM")
        assert isinstance(out["action_rationale"], str)
        assert len(out["action_rationale"]) > 10

    def test_sales_story_is_nonempty_string(self):
        out = _explain("REVIEW", "LOW")
        assert isinstance(out["sales_story"], str)
        assert len(out["sales_story"]) > 20


# ---------------------------------------------------------------------------
# 2. Action mapping sanity cases (from plan table)
# ---------------------------------------------------------------------------
class TestActionMapping:
    def test_pass_high_is_door_to_door(self):
        out = _explain("PASS", "HIGH")
        assert out["recommended_action"] == "DOOR_TO_DOOR"

    def test_pass_medium_is_selective(self):
        out = _explain("PASS", "MEDIUM")
        assert out["recommended_action"] == "SELECTIVE_OUTREACH"

    def test_pass_low_is_selective(self):
        out = _explain("PASS", "LOW")
        assert out["recommended_action"] == "SELECTIVE_OUTREACH"

    def test_qualified_high_is_installer(self):
        out = _explain("QUALIFIED", "HIGH")
        assert out["recommended_action"] == "INSTALLER_PARTNER_FOCUS"

    def test_qualified_medium_is_installer(self):
        out = _explain("QUALIFIED", "MEDIUM")
        assert out["recommended_action"] == "INSTALLER_PARTNER_FOCUS"

    def test_qualified_low_is_monitor(self):
        out = _explain("QUALIFIED", "LOW")
        assert out["recommended_action"] == "MONITOR_ONLY"

    def test_review_any_is_monitor(self):
        for conf in ["HIGH", "MEDIUM", "LOW"]:
            out = _explain("REVIEW", conf)
            assert out["recommended_action"] == "MONITOR_ONLY"

    def test_fail_any_is_deprioritize(self):
        for conf in ["HIGH", "MEDIUM", "LOW"]:
            out = _explain("FAIL", conf, sfh=0.0, mfh=0.70, mfh_c=50, oth=0.10)
            assert out["recommended_action"] == "DEPRIORITIZE"


# ---------------------------------------------------------------------------
# 3. Determinism (pure function check)
# ---------------------------------------------------------------------------
class TestDeterminism:
    def test_same_input_same_output(self):
        kwargs = dict(gate="PASS", conf="MEDIUM", sfh=0.75, mfh=0.05,
                      mfh_c=3, oth=0.20, tot=40)
        results = [_explain(**kwargs) for _ in range(10)]
        for r in results[1:]:
            assert r == results[0], "generate_explanation is not deterministic"

    def test_different_inputs_different_action(self):
        out_pass = _explain("PASS", "HIGH")
        out_fail = _explain("FAIL", "LOW", sfh=0.0, mfh=0.8, mfh_c=50, oth=0.1)
        assert out_pass["recommended_action"] != out_fail["recommended_action"]


# ---------------------------------------------------------------------------
# 4. No contamination (structural)
# ---------------------------------------------------------------------------
class TestNoContamination:
    def test_explainer_not_in_gate_logic(self):
        from foundation_explainer import explainer_rules
        forbidden = {
            "apply_structure_gate", "PASS_MAX_MFH_RATIO",
            "compute_street_confidence", "filter_universe",
        }
        exposed = set(dir(explainer_rules))
        leaked = forbidden.intersection(exposed)
        assert not leaked, f"Gate/confidence symbols leaked: {leaked}"

    def test_no_wildcard_exports(self):
        import foundation_explainer
        assert hasattr(foundation_explainer, "__all__")
        assert foundation_explainer.__all__ == ["generate_explanation"]

    def test_recommended_action_not_a_score(self):
        """Recommended action is a string label, not a numeric score."""
        out = _explain("PASS", "HIGH")
        assert isinstance(out["recommended_action"], str)
        assert not isinstance(out["recommended_action"], (int, float))

    def test_no_internal_field_names_in_user_text(self):
        """User-facing strings must not contain raw variable names or gate codes."""
        forbidden_terms = [
            "LOW_MFH_HIGH_SFH", "sfh_ratio", "mfh_ratio",
            "other_ratio", "gate_reason", "CONF_", "EXPL_",
        ]
        for gate in ["PASS", "QUALIFIED", "REVIEW", "FAIL"]:
            out = _explain(gate, "MEDIUM")
            all_text = " ".join(out["top_reasons"] + out["risk_flags"]
                                + [out["action_rationale"], out["sales_story"]])
            for term in forbidden_terms:
                assert term not in all_text, (
                    f"Internal term '{term}' found in user-facing text for gate={gate}"
                )
