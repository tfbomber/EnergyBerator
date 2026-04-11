"""
tests/test_input_contract.py
=============================
General Ranking — Input Contract Test

Verifies:
1. All required Foundation fields exist in the real Foundation output.
2. Foundation output has NOT been contaminated with ranking fields.
3. structure_gate values are valid.
"""

import os
import sys
import json
import pytest

# Adjust path for standalone test runner
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
FOUNDATION_PATH = os.path.join(BASE_DIR, "output", "foundation", "foundation_structure_results.json")

REQUIRED_FIELDS = [
    "cluster_id", "street_name", "plz", "address_range",
    "building_count_total", "sfh_total_ratio", "mfh_ratio",
    "other_ratio", "structure_profile", "structure_gate", "gate_reason",
    "execution_scale_flag",  # Phase 15 Finding A
    # Layer 1.5: explanation metadata fields
    "top_reasons", "risk_flags", "recommended_action",
    "action_rationale", "sales_story",
]

VALID_SCALE_VALUES = {"STANDALONE", "APPEND_TO_AREA"}  # Phase 15 Finding A

FORBIDDEN_RANKING_FIELDS = ["general_rank_score", "general_rank", "general_band"]

VALID_GATE_VALUES = {"PASS", "QUALIFIED", "REVIEW", "FAIL"}

# Enhancement C: street_confidence valid values
VALID_CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW"}

# Layer 1.5: recommended_action valid values
VALID_ACTION_VALUES = {
    "DOOR_TO_DOOR", "SELECTIVE_OUTREACH",
    "INSTALLER_PARTNER_FOCUS", "MONITOR_ONLY", "DEPRIORITIZE",
}


@pytest.fixture
def foundation_data():
    if not os.path.exists(FOUNDATION_PATH):
        pytest.skip(f"Foundation data not found: {FOUNDATION_PATH}. Run generate_foundation_layer.py first.")
    with open(FOUNDATION_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_required_fields_exist(foundation_data):
    """All required input fields must be present in every record."""
    assert len(foundation_data) > 0, "Foundation data is empty."
    for rec in foundation_data:
        for field in REQUIRED_FIELDS:
            assert field in rec, f"[CONTRACT VIOLATION] Required field '{field}' missing in cluster {rec.get('cluster_id')}"


def test_no_ranking_field_contamination(foundation_data):
    """Ranking fields must NOT appear in Foundation output file."""
    for rec in foundation_data:
        for forbidden in FORBIDDEN_RANKING_FIELDS:
            assert forbidden not in rec, (
                f"[CONTAMINATION DETECTED] Ranking field '{forbidden}' found in Foundation output "
                f"for cluster {rec.get('cluster_id')}. Foundation has been incorrectly modified."
            )


def test_gate_values_valid(foundation_data):
    """structure_gate values must only be PASS, QUALIFIED, REVIEW, or FAIL."""
    for rec in foundation_data:
        gate = rec.get("structure_gate")
        assert gate in VALID_GATE_VALUES, (
            f"Invalid structure_gate '{gate}' for cluster {rec.get('cluster_id')}. "
            f"Expected one of {VALID_GATE_VALUES}."
        )


def test_street_confidence_valid(foundation_data):
    """Enhancement C: street_confidence must be present and valid for every record."""
    for rec in foundation_data:
        conf = rec.get("street_confidence")
        assert conf is not None, (
            f"[CONTRACT VIOLATION] 'street_confidence' missing in cluster {rec.get('cluster_id')}."
        )
        assert conf in VALID_CONFIDENCE_VALUES, (
            f"Invalid street_confidence '{conf}' for cluster {rec.get('cluster_id')}. "
            f"Expected one of {VALID_CONFIDENCE_VALUES}."
        )


def test_recommended_action_valid(foundation_data):
    """Layer 1.5: recommended_action must be present and a valid enum value."""
    for rec in foundation_data:
        action = rec.get("recommended_action")
        assert action is not None, (
            f"[CONTRACT VIOLATION] 'recommended_action' missing in cluster {rec.get('cluster_id')}."
        )
        assert action in VALID_ACTION_VALUES, (
            f"Invalid recommended_action '{action}' for cluster {rec.get('cluster_id')}. "
            f"Expected one of {VALID_ACTION_VALUES}."
        )
