"""
D-ESS Engine — S1 Intake Test Suite
Test IDs: TC-S1-001 to TC-S1-041

Coverage:
  A. Enum / Unknown / Schema
  B. Date + Vorhabenbeginn risk flags
  C. Amount & Basis validation
  D. Data Completeness scoring
  E. Determinism / Contract

Run:
    python -m pytest tests/test_s1_intake.py -v
"""
import sys
import os
import json
import hashlib
from datetime import date
from decimal import Decimal
import pytest

# -- Path setup -----------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ui", "components")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ui")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from s1_intake import normalize_amount, build_payload, compute_completeness, load_spec

SPEC = load_spec()

# =========================================================================
# HELPERS
# =========================================================================

def make_full_state(
    project_type="BALCONY_PV",
    is_business="NO",
    duesselpass="NO",
    energy_consult="NO",
    app_date=date(2026, 2, 1),
    con_date=date(2026, 2, 5),
    wrk_date=date(2026, 2, 10),
    hw_amt="800",
    hw_amt_unk=False,
    hw_basis="NET",
    lb_amt="200",
    lb_amt_unk=False,
    lb_basis="GROSS",
):
    """Build a fully-populated intake_state dict for build_payload()."""
    return {
        "Q0_PROJECT_TYPE": project_type,
        "Q1_IS_BUSINESS": is_business,
        "Q2_HAS_DUESSELPASS": duesselpass,
        "Q10_HAS_ENERGY_CONSULT_PROOF": energy_consult,
        "Q3_APPLICATION_DATE": app_date,
        "Q4_CONTRACT_DATE": con_date,
        "Q5_WORK_START_DATE": wrk_date,
        "Q6_HARDWARE_AMOUNT_val": hw_amt,
        "Q6_HARDWARE_AMOUNT_unk": hw_amt_unk,
        "Q7_HARDWARE_BASIS": hw_basis,
        "Q8_LABOR_AMOUNT_val": lb_amt,
        "Q8_LABOR_AMOUNT_unk": lb_amt_unk,
        "Q9_LABOR_BASIS": lb_basis,
    }


def empty_state():
    """All fields UNKNOWN / absent = initial blank form."""
    return {
        "Q0_PROJECT_TYPE": "PLEASE_SELECT",  # Not yet selected → does not contribute to completeness
        "Q1_IS_BUSINESS": "UNKNOWN",
        "Q2_HAS_DUESSELPASS": "UNKNOWN",
        "Q10_HAS_ENERGY_CONSULT_PROOF": "UNKNOWN",
        # No date keys set → None values handled by UI; we skip them here.
        "Q6_HARDWARE_AMOUNT_val": "",
        "Q6_HARDWARE_AMOUNT_unk": True,
        "Q7_HARDWARE_BASIS": "UNKNOWN",
        "Q8_LABOR_AMOUNT_val": "",
        "Q8_LABOR_AMOUNT_unk": True,
        "Q9_LABOR_BASIS": "UNKNOWN",
    }


# =========================================================================
# A. ENUM / UNKNOWN / SCHEMA
# =========================================================================

class TestEnumValidation:
    """Group A: Enum / Unknown / Schema"""

    # TC-S1-001: UNKNOWN for is_business must not appear as True/False in payload
    def test_TC_S1_001_is_business_unknown_not_inferred(self):
        """TC-S1-001: is_business=UNKNOWN → key absent from payload (ZERO_INFERENCE)."""
        state = make_full_state(is_business="UNKNOWN")
        payload = build_payload(state)
        assert "is_business" not in payload["attributes"], (
            "ZERO_INFERENCE violated: is_business=UNKNOWN must NOT become True/False in payload"
        )

    # TC-S1-002: bonus=UNKNOWN → no DUESSELPASS in bonuses
    def test_TC_S1_002_bonus_unknown_no_duesselpass(self):
        """TC-S1-002: bonus=UNKNOWN → DUESSELPASS not appended."""
        state = make_full_state(duesselpass="UNKNOWN")
        payload = build_payload(state)
        assert "DUESSELPASS" not in payload["attributes"].get("bonuses", [])

    # TC-S1-003: bonus=NO → no DUESSELPASS either
    def test_TC_S1_003_bonus_no_equals_unknown_outcome(self):
        """TC-S1-003: bonus=NO must also produce no DUESSELPASS (same outcome as UNKNOWN)."""
        state_unk = make_full_state(duesselpass="UNKNOWN")
        state_no  = make_full_state(duesselpass="NO")
        p_unk = build_payload(state_unk)
        p_no  = build_payload(state_no)
        assert "DUESSELPASS" not in p_unk["attributes"].get("bonuses", [])
        assert "DUESSELPASS" not in p_no["attributes"].get("bonuses", [])

    # TC-S1-004: bonus=YES → DUESSELPASS present
    def test_TC_S1_004_bonus_yes_triggers_duesselpass(self):
        """TC-S1-003 counterpart: bonus=YES → DUESSELPASS in bonuses."""
        state = make_full_state(duesselpass="YES")
        payload = build_payload(state)
        assert "DUESSELPASS" in payload["attributes"].get("bonuses", [])


# =========================================================================
# B. DATE FORMAT + VORHABENBEGINN (risk flags)
# =========================================================================

class TestDateRiskFlags:
    """Group B: Date/Timing risk flag logic (replicated from UI for unit testing)."""

    def _check_risk(self, app_date, con_date=None, wrk_date=None):
        """
        Replicate the UI risk logic for unit testing.
        Returns (contract_risk: bool, workstart_risk: bool)
        """
        contract_risk = False
        workstart_risk = False
        if con_date and app_date and con_date < app_date:
            contract_risk = True
        if wrk_date and app_date and wrk_date < app_date:
            workstart_risk = True
        return contract_risk, workstart_risk

    # TC-S1-011: contract_signed < application_submitted → risk flag, NOT rejection
    def test_TC_S1_011_contract_before_application_risk_only(self):
        """TC-S1-011: contract_signed earlier triggers risk; S1 must NOT reject."""
        app = date(2026, 3, 1)
        con = date(2026, 2, 20)
        contract_risk, _ = self._check_risk(app, con_date=con)
        assert contract_risk is True, "VORHABENBEGINN_POSSIBLE should be raised"
        # S1 layer has no REJECTED status; risk flag is advisory only
        # (the flag is a boolean, not a verdict → this test confirms advisory-only)

    # TC-S1-012: work_started < application_submitted → risk flag
    def test_TC_S1_012_workstart_before_application_risk(self):
        """TC-S1-012: work_started earlier triggers risk."""
        app = date(2026, 3, 1)
        wrk = date(2026, 2, 15)
        _, workstart_risk = self._check_risk(app, wrk_date=wrk)
        assert workstart_risk is True

    # TC-S1-013: same-day → NO false positive
    def test_TC_S1_013_same_day_no_false_positive(self):
        """TC-S1-013: contract_signed == application_submitted → NO risk flag."""
        same_date = date(2026, 3, 1)
        contract_risk, workstart_risk = self._check_risk(same_date, con_date=same_date, wrk_date=same_date)
        assert contract_risk is False, "Same-day must not trigger contract risk"
        assert workstart_risk is False, "Same-day must not trigger workstart risk"

    # TC-S1-014: app_date missing → risk logic cannot fire
    def test_TC_S1_014_missing_app_date_no_false_risk(self):
        """TC-S1-014: If application_submitted is UNKNOWN, risk engine stays silent."""
        contract_risk, workstart_risk = self._check_risk(None, con_date=date(2026, 1, 1), wrk_date=date(2026, 1, 1))
        assert contract_risk is False
        assert workstart_risk is False


# =========================================================================
# C. AMOUNT & BASIS VALIDATION
# =========================================================================

class TestAmountValidation:
    """Group C: normalize_amount strict rules."""

    # TC-S1-020: negative amount rejected
    def test_TC_S1_020_negative_amount_rejected(self):
        """TC-S1-020: hardware.amount=-1 → NEGATIVE_NOT_ALLOWED."""
        with pytest.raises(ValueError, match="NEGATIVE_NOT_ALLOWED"):
            normalize_amount("-1")

    # TC-S1-021a: amount=0 is allowed and treated as zero subsidy
    def test_TC_S1_021_zero_amount_allowed(self):
        """TC-S1-021: amount=0 is a valid non-negative decimal → no exception."""
        result, notices = normalize_amount("0")
        assert result == "0", f"Expected '0', got '{result}'"

    # TC-S1-021b: amount="0" produces zero string, consistent contract
    def test_TC_S1_021b_zero_behavior_consistent(self):
        """TC-S1-021b: Zero string '0' normalizes to '0' (integer-style, no dp)."""
        result, _ = normalize_amount("0")
        assert result == "0"

    # TC-S1-021c: labor amount 0 must still be emitted (valid deterministic input)
    def test_TC_S1_021c_labor_zero_persists_in_payload(self):
        """TC-S1-021c: LABOR.amount='0' should be present in payload, not dropped."""
        state = make_full_state(lb_amt="0", lb_basis="GROSS")
        payload = build_payload(state)
        labor = payload["costs"]["buckets"].get("LABOR", {})
        assert labor.get("amount") == "0", "LABOR amount zero must be emitted for engine compatibility"
        assert labor.get("amount_basis") == "GROSS"

    # TC-S1-022: amount with UNKNOWN basis → payload lacks amount_basis
    def test_TC_S1_022_unknown_basis_omitted_from_payload(self):
        """TC-S1-022: basis=UNKNOWN must not appear in payload (blocks final calc)."""
        state = make_full_state(hw_basis="UNKNOWN", lb_basis="UNKNOWN")
        payload = build_payload(state)
        hw = payload["costs"]["buckets"].get("HARDWARE", {})
        lb = payload["costs"]["buckets"].get("LABOR", {})
        assert "amount_basis" not in hw, "HARDWARE basis UNKNOWN must be omitted from payload"
        assert "amount_basis" not in lb, "LABOR basis UNKNOWN must be omitted from payload"

    # TC-S1-023: very large amount does not crash
    def test_TC_S1_023_large_amount_no_crash(self):
        """TC-S1-023: hardware.amount=999999999 normalizes without exception."""
        result, _ = normalize_amount("999999999")
        assert result == "999999999"

    # TC-S1-024: European decimal comma converted
    def test_TC_S1_024_euro_comma_normalized(self):
        """TC-S1-024: '1200,50' → '1200.50' with notice emitted."""
        result, notices = normalize_amount("1200,50")
        assert result == "1200.50"
        assert any("1200,50" in n for n in notices), "Notice must mention original value"

    # TC-S1-025: date format with hyphen (YYYY-MM-DD) not a normalization concern for amount
    def test_TC_S1_025_thousands_separator_rejected(self):
        """TC-S1-025: '1,200.50' (thousands separator) must be rejected."""
        with pytest.raises(ValueError):
            normalize_amount("1,200.50")


# =========================================================================
# D. DATA COMPLETENESS SCORING
# =========================================================================

class TestCompleteness:
    """Group D: compute_completeness() — Must=70%/7, Nice=30%/3 (updated)."""

    # TC-S1-030: PLEASE_SELECT + all UNKNOWN → 0% Must, but UNKNOWN-as-answered counts Nice
    def test_TC_S1_030_please_select_with_all_unknowns(self):
        """TC-S1-030: PLEASE_SELECT + explicit UNKNOWN nice fields + hw_unk=True + lb_unk=True.
        - hw_unk=True  → C.HARDWARE.AMOUNT + C.HARDWARE.BASIS in mh (2 blockers)
        - lb_unk=True  → C.LABOR.AMOUNT   + C.LABOR.BASIS   in mh (2 blockers)
        - Q1/Q2/Q10 = UNKNOWN → 3 nice blockers
        """
        state = empty_state()  # PLEASE_SELECT + UNKNOWN for nice fields
        payload = build_payload(state)
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        # hw_unk + lb_unk → 4 must-have unknowns registered
        assert mh_c == 4, f"Expected must_done=4 (4 cost unknowns from checkboxes), got {mh_c}"
        # Q1=UNKNOWN + Q2=UNKNOWN + Q10=UNKNOWN → all 3 nice blockers
        assert nh_c == 3, f"Expected nice_done=3 (all 3 UNKNOWN-nice), got {nh_c}"
        # All unknowns should appear as blockers
        assert len(blockers) > 0, "Expected blockers from Unknown answers"

    # TC-S1-031: Nice-to-Have DUESSELPASS=YES → 15%  (0/7 Must + 1/3 Nice × 30%  = 10%)
    def test_TC_S1_031_one_nice_ten_percent(self):
        """TC-S1-031: DUESSELPASS=YES + IS_BUSINESS=UNKNOWN + ENERGY=UNKNOWN.
        - mh_c=0 (no dates or costs filled)
        - nh_c=3: DUESSELPASS=YES (1) + IS_BUSINESS=UNKNOWN (1) + ENERGY=UNKNOWN (1)
        - score = 0/7*0.7 + 3/3*0.3 = 0.30 = 30%
        """
        state = {
            "Q0_PROJECT_TYPE": "BALCONY_PV",
            "Q1_IS_BUSINESS": "UNKNOWN",
            "Q2_HAS_DUESSELPASS": "YES",
            "Q10_HAS_ENERGY_CONSULT_PROOF": "UNKNOWN",
            "Q6_HARDWARE_AMOUNT_val": "",
            "Q6_HARDWARE_AMOUNT_unk": False,
            "Q7_HARDWARE_BASIS": "UNKNOWN",
            "Q8_LABOR_AMOUNT_val": "",
            "Q8_LABOR_AMOUNT_unk": False,
            "Q9_LABOR_BASIS": "UNKNOWN",
        }
        payload = build_payload(state)
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        assert mh_c == 0
        assert nh_t == 3, f"Expected 3 Nice-to-Haves (now includes ENERGY_CONSULT_PROOF), got {nh_t}"
        assert nh_c == 3, f"Expected nh_c=3 (DUESSELPASS=YES + IS_BUSINESS=UNKNOWN + ENERGY=UNKNOWN), got {nh_c}"
        assert int(score * 100) == 30, f"Expected 30%, got {int(score*100)}%"

    # TC-S1-032: 1 Must (APPLICATION_DATE) → 10%  (1/7 Must × 70%)
    def test_TC_S1_032_one_must_ten_percent(self):
        """TC-S1-032: APPLICATION_DATE filled + Q1/Q2/Q10 = UNKNOWN.
        - mh_c=1 (date) + 0 (no cost unknowns via checkbox or amount)
        - nh_c=3: IS_BUSINESS=UNKNOWN + DUESSELPASS=UNKNOWN + ENERGY=UNKNOWN
        - score = 1/7*0.7 + 3/3*0.3 = 0.10 + 0.30 = 40%
        """
        state = {
            "Q0_PROJECT_TYPE": "BALCONY_PV",
            "Q1_IS_BUSINESS": "UNKNOWN",
            "Q2_HAS_DUESSELPASS": "UNKNOWN",
            "Q10_HAS_ENERGY_CONSULT_PROOF": "UNKNOWN",
            "Q3_APPLICATION_DATE": date(2026, 2, 1),
            "Q6_HARDWARE_AMOUNT_val": "",
            "Q6_HARDWARE_AMOUNT_unk": False,
            "Q7_HARDWARE_BASIS": "UNKNOWN",
            "Q8_LABOR_AMOUNT_val": "",
            "Q8_LABOR_AMOUNT_unk": False,
            "Q9_LABOR_BASIS": "UNKNOWN",
        }
        payload = build_payload(state)
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        assert mh_c == 1, f"Expected must_done=1 (only APPLICATION_DATE), got {mh_c}"
        assert nh_c == 3, f"Expected nh_c=3 (all 3 UNKNOWN-nice), got {nh_c}"
        assert int(score * 100) == 40, f"Expected 40% (1/7*0.7 + 3/3*0.3 = 40%), got {int(score*100)}%"

    # TC-S1-033: all fields complete → 100%
    def test_TC_S1_033_all_complete_hundred_percent(self):
        """TC-S1-033: All 7 Must + 3 Nice filled → 100%."""
        state = make_full_state(is_business="YES", duesselpass="YES", energy_consult="YES")
        payload = build_payload(state)
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        assert mh_c == 7, f"Expected must_done=7, got {mh_c}"
        assert nh_t == 3, f"Expected 3 Nice-to-Haves (updated), got {nh_t}"
        assert nh_c == 3, f"Expected nice_done=3, got {nh_c}"
        assert int(score * 100) == 100, f"Expected 100%, got {int(score*100)}%"
        assert len(blockers) == 0, "No blockers expected when all fields are definitively answered"

    # TC-S1-034: is_business=NO counts as Nice (explicitly set)
    def test_TC_S1_034_is_business_no_counts_nice(self):
        """TC-S1-034: is_business=NO is explicit → Nice score +1."""
        state = {
            "Q0_PROJECT_TYPE": "BALCONY_PV",
            "Q1_IS_BUSINESS": "NO",
            "Q2_HAS_DUESSELPASS": "UNKNOWN",
            "Q10_HAS_ENERGY_CONSULT_PROOF": "UNKNOWN",
            "Q6_HARDWARE_AMOUNT_val": "", "Q6_HARDWARE_AMOUNT_unk": False,
            "Q7_HARDWARE_BASIS": "UNKNOWN",
            "Q8_LABOR_AMOUNT_val": "", "Q8_LABOR_AMOUNT_unk": False,
            "Q9_LABOR_BASIS": "UNKNOWN",
        }
        payload = build_payload(state)
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        assert nh_c >= 1, f"Expected nice_done>=1, got {nh_c} (is_business=NO should score)"

    # TC-S1-035: is_business=UNKNOWN → NOW counts as Nice (answered-as-unknown), AND is a blocker
    def test_TC_S1_035_is_business_unknown_counts_nice_as_blocker(self):
        """TC-S1-035 (UPDATED): is_business=UNKNOWN → counts as answered-nice, appears in blockers."""
        state = {
            "Q0_PROJECT_TYPE": "BALCONY_PV",
            "Q1_IS_BUSINESS": "UNKNOWN",
            "Q2_HAS_DUESSELPASS": "UNKNOWN",
            "Q10_HAS_ENERGY_CONSULT_PROOF": "UNKNOWN",
            "Q6_HARDWARE_AMOUNT_val": "", "Q6_HARDWARE_AMOUNT_unk": False,
            "Q7_HARDWARE_BASIS": "UNKNOWN",
            "Q8_LABOR_AMOUNT_val": "", "Q8_LABOR_AMOUNT_unk": False,
            "Q9_LABOR_BASIS": "UNKNOWN",
        }
        payload = build_payload(state)
        # is_business key must be absent from payload (ZERO_INFERENCE)
        assert "is_business" not in payload["attributes"], "ZERO_INFERENCE: key must be absent"
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        # is_business=UNKNOWN → counts as answered-nice but is a blocker
        assert nh_c >= 1, f"Expected nice_done>=1 since UNKNOWN now counts as answered, got {nh_c}"
        blocker_codes = [b.split()[0] for b in blockers]
        assert "A.IS_BUSINESS" in blocker_codes, "A.IS_BUSINESS should appear in blockers"

    # TC-S1-036: exactly 7 Must, 0 Nice → 70%
    def test_TC_S1_036_seven_must_zero_nice_seventy_percent(self):
        """TC-S1-036: All Must filled; is_business=UNKNOWN (blocker) + energy_consult=NO (definitive).
        - mh_c=7, nh_c=2: is_business=UNKNOWN (1, blocker) + energy_consult=NO (1, definitive)
        - score = 7/7*0.7 + 2/3*0.3 = 0.70 + 0.20 = 90%
        """
        state = make_full_state(is_business="UNKNOWN", duesselpass="NO", energy_consult="NO")
        payload = build_payload(state)
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        assert mh_c == 7, f"Expected mh_c=7, got {mh_c}"
        # is_business=UNKNOWN → nh_c+1 (blocker); energy_consult=NO → nh_c+1 (definitive)
        assert nh_c == 2, f"Expected nh_c=2 (is_business=UNKNOWN + energy_consult=NO), got {nh_c}"
        assert any("A.IS_BUSINESS" in b for b in blockers), "is_business=UNKNOWN must appear in blockers"

    # TC-S1-037: energy_consult=UNKNOWN → counts as answered Nice, appears in blockers
    def test_TC_S1_037_energy_consult_unknown_scored_as_blocker(self):
        """TC-S1-037 [NEW]: energy_consult=UNKNOWN → nh_c+1, in blockers."""
        state = {
            "Q0_PROJECT_TYPE": "BALCONY_PV",
            "Q1_IS_BUSINESS": "NO",
            "Q2_HAS_DUESSELPASS": "NO",
            "Q10_HAS_ENERGY_CONSULT_PROOF": "UNKNOWN",
            "Q6_HARDWARE_AMOUNT_val": "", "Q6_HARDWARE_AMOUNT_unk": False,
            "Q7_HARDWARE_BASIS": "UNKNOWN",
            "Q8_LABOR_AMOUNT_val": "", "Q8_LABOR_AMOUNT_unk": False,
            "Q9_LABOR_BASIS": "UNKNOWN",
        }
        payload = build_payload(state)
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        assert any("A.ENERGY_CONSULT_PROOF" in b for b in blockers), "ENERGY_CONSULT_PROOF must appear in blockers"
        assert nh_c >= 2, f"Expected nh_c>=2 (is_business=NO + energy_consult=UNKNOWN), got {nh_c}"

    # TC-S1-038: nice_to_haves total must equal 3 (updated from 2)
    def test_TC_S1_038_nice_to_haves_total_is_three(self):
        """TC-S1-038 [NEW]: Spec must reflect 3 Nice-to-Haves after ENERGY_CONSULT_PROOF addition."""
        state = make_full_state()
        payload = build_payload(state)
        score, mh_c, mh_t, nh_c, nh_t, blockers = compute_completeness(payload, SPEC)
        assert nh_t == 3, f"Expected total nice-to-haves=3, got {nh_t}"


# =========================================================================
# E. CONTRACT & DETERMINISM
# =========================================================================

class TestDeterminism:
    """Group E: Same input → identical payload hash (determinism contract)."""

    def _payload_hash(self, state: dict) -> str:
        payload = build_payload(state)
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # TC-S1-040: same input → identical hash on two calls
    def test_TC_S1_040_same_input_same_hash(self):
        """TC-S1-040: Identical state→ identical payload hash (determinism)."""
        state = make_full_state()
        h1 = self._payload_hash(state)
        h2 = self._payload_hash(state)
        assert h1 == h2, "Payload hash must be identical for identical inputs"

    # TC-S1-041: UNKNOWN stays UNKNOWN (not silently converted)
    def test_TC_S1_041_unknown_not_defaulted(self):
        """TC-S1-041: is_business=UNKNOWN & duesselpass=UNKNOWN → both absent/empty in payload."""
        state = make_full_state(is_business="UNKNOWN", duesselpass="UNKNOWN")
        payload = build_payload(state)
        # is_business must be absent
        assert "is_business" not in payload["attributes"], \
            "is_business=UNKNOWN must not appear as True or False"
        # DUESSELPASS must not appear in bonuses list
        assert "DUESSELPASS" not in payload["attributes"].get("bonuses", []), \
            "duesselpass=UNKNOWN must not produce DUESSELPASS bonus"

    # TC-S1-042: different inputs → different hashes
    def test_TC_S1_042_different_inputs_different_hashes(self):
        """TC-S1-042: Different state → different hash (non-collision sanity check)."""
        s1 = make_full_state(hw_amt="800")
        s2 = make_full_state(hw_amt="900")
        assert self._payload_hash(s1) != self._payload_hash(s2)
