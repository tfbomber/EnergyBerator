import pytest
import os
import json
from core.roi_mvp import calculate_roi_mvp, _calc_export_stack, _calc_financing, _calc_wealth_effect


def load_v3_policy():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "policies", "roi_hp_mvp_neuss_2026.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# REGRESSION: Existing v2 tests (adapted for 100_150 format)
# ---------------------------------------------------------------------------

def test_roi_target_audience():
    policy = load_v3_policy()
    case_no_hp = {"attributes": {"has_heat_pump": False, "has_pv": False}}
    res = calculate_roi_mvp(case_no_hp, policy)
    assert res["verdict"] == "ROI_NOT_TARGET"

    case_has_pv = {"attributes": {"has_heat_pump": True, "has_pv": True}}
    res = calculate_roi_mvp(case_has_pv, policy)
    assert res["verdict"] == "ROI_NOT_TARGET"


def test_roi_v2_calculation_features():
    policy = load_v3_policy()
    case = {
        "attributes": {
            "has_heat_pump": True,
            "has_pv": False,
            "household_size": "3",
            "hp_input_mode": "MODE_B",
            "hp_bucket": "100_150",
            "electric_vehicle": "NONE"
        }
    }

    res = calculate_roi_mvp(case, policy)
    assert res["verdict"] == "ROI_OK"

    # 1. kWp Recommendation
    assert 6 <= res["kWp_rec"] <= 12

    # 2. VAT Calculation
    capex = res["capex"]
    assert capex["vat19_cents"] > capex["vat0_cents"]
    assert capex["vat_saving_cents"] == capex["vat19_cents"] - capex["vat0_cents"]

    # 3. Scenarios & Monotonicity
    scenarios = res["scenarios"]
    assert len(scenarios) == 3

    pb_con = scenarios[0]["payback_static_years_x100"]
    pb_base = scenarios[1]["payback_static_years_x100"]
    pb_opt = scenarios[2]["payback_static_years_x100"]
    assert pb_con >= pb_base >= pb_opt

    # 4. Dynamic Payback vs Static
    for s in scenarios:
        pb_static_full = (s["payback_static_years_x100"] + 99) // 100
        pb_dynamic = s["payback_dynamic_years"]
        if pb_dynamic != 999: # Only verify if it actually paid back
            assert pb_dynamic <= pb_static_full or pb_dynamic == 999

    # 5. Type Consistency
    assert isinstance(res["kWp_rec"], int)
    assert isinstance(res["e_pv_kwh"], int)
    assert isinstance(res["lcoe_ct_per_kwh"], int)
    assert isinstance(res["co2_saved_tons_per_year"], (int, float))
    
    for s in scenarios:
        assert isinstance(s["annual_benefit_cents"], int)
        assert isinstance(s["payback_dynamic_years"], int)
        assert isinstance(s["profit20_cents"], int)
        assert isinstance(s["lcoe_ct_per_kwh"], int)

    # 6. Basic Logic Checks
    base = scenarios[1]
    assert base["lcoe_ct_per_kwh"] > 0
    assert res["co2_saved_tons_per_year"] > 0
    if base["payback_dynamic_years"] <= 20:
        assert base["post_payback_profit_20y"] >= 0


# ---------------------------------------------------------------------------
# NEW: v3 Module Tests
# ---------------------------------------------------------------------------

def test_roi_v3_all_new_fields_present():
    policy = load_v3_policy()
    case = {
        "attributes": {
            "has_heat_pump": True,
            "has_pv": False,
            "household_size": "3",
            "hp_input_mode": "MODE_B",
            "hp_bucket": "100_150",
            "financing_enabled": True
        }
    }
    res = calculate_roi_mvp(case, policy)

    assert "export_analysis" in res
    assert "financing_report" in res
    assert "wealth_effect" in res

    ea = res["export_analysis"]
    for field in ("sharing_kwh", "eeg_kwh", "sharing_income_eur", "eeg_income_eur"):
        assert field in ea

    fr = res["financing_report"]
    assert fr.get("enabled") is True
    for field in ("loan_principal_eur", "loan_monthly_payment_eur", "monthly_savings_eur",
                  "monthly_cashflow_margin_eur", "is_cashflow_positive"):
        assert field in fr


def test_roi_v3_export_stack_conservation_demo_case():
    """Demo case requested by user: load < pv so export > 0"""
    policy = load_v3_policy()
    case = {
        "attributes": {
            "has_heat_pump": True,
            "has_pv": False,
            "household_size": "2",     # 3200 base
            "hp_input_mode": "MODE_A",
            "hp_bucket": "<3000",      # 2000 hp
            "electric_vehicle": "NONE"
        }
    }
    # load = 5200. PV recommendation will likely be ~6kwp -> ~5160kWh or bounded to min 6 kWp -> 5160 kWh.
    # To force larger PV, pretend it has an EV plan to pump up kWp, then calculate. Or just trust engine min kwp=6.
    
    res = calculate_roi_mvp(case, policy)
    ea = res["export_analysis"]
    baseline_export = res["scenarios"][1]["e_export_kwh"]

    assert ea["sharing_kwh"] + ea["eeg_kwh"] == baseline_export
    # All integers
    assert isinstance(ea["sharing_kwh"], int)
    assert isinstance(ea["eeg_kwh"], int)
    assert isinstance(ea["sharing_income_eur"], int)
    assert isinstance(ea["eeg_income_eur"], int)


def test_roi_v3_export_stack_zero_export():
    export_params = {
        "energy_sharing_enabled": True,
        "energy_sharing_realization_bps": 7000,
        "energy_sharing_net_price_cents_x100": 1800,
    }
    result = _calc_export_stack(0, 778, export_params)
    assert result["sharing_kwh"] == 0
    assert result["sharing_income_cents"] == 0
    assert result["eeg_income_cents"] == 0


def test_roi_v3_export_stack_sharing_split():
    result = _calc_export_stack(
        export_kwh=1000,
        p_feed_cents_x100=778,
        export_params={
            "energy_sharing_enabled": True,
            "energy_sharing_realization_bps": 7000,
            "energy_sharing_net_price_cents_x100": 1800,
        }
    )
    assert result["sharing_kwh"] == 700
    assert result["eeg_kwh"] == 300
    assert result["sharing_income_cents"] == 700 * 1800 // 100   # 12600 cents
    assert result["eeg_income_cents"] == (300 * 778) // 100


def test_roi_v3_financing_pmt_correctness():
    """PMT precision check with pure numerator/denominator math."""
    fin_params = {
        "loan_principal_pct_bps": 10000,
        "loan_term_years": 10,
        "loan_apr_bps": 450,
    }
    capex_cents = 1_235_000  # 12350 EUR
    result = _calc_financing(capex_cents, 1980_00, fin_params)

    pmt = result["loan_monthly_payment_cents"]
    principal = result["loan_principal_cents"]
    months = 120

    assert pmt > 0
    assert isinstance(pmt, int)

    total_repaid = pmt * months
    assert total_repaid >= principal
    assert total_repaid <= (principal * 15000) // 10000


def test_roi_v3_financing_cashflow_flag():
    fin_params = {
        "loan_principal_pct_bps": 10000,
        "loan_term_years": 10,
        "loan_apr_bps": 450,
    }
    capex_cents = 1_235_000
    # Pos cashflow: benefit 200/mo -> 2400 EUR/y
    result = _calc_financing(capex_cents, 2400 * 100, fin_params)
    assert result["is_cashflow_positive"] is True

    # Neg cashflow: benefit 1/mo -> 12 EUR/y
    result2 = _calc_financing(capex_cents, 12 * 100, fin_params)
    assert result2["is_cashflow_positive"] is False


def test_roi_v3_does_not_break_v2_payback():
    policy = load_v3_policy()
    case = {
        "attributes": {
            "has_heat_pump": True,
            "has_pv": False,
            "household_size": "4",
            "hp_input_mode": "MODE_B",
            "hp_bucket": "100_150",
            "electric_vehicle": "PLAN",
            "financing_enabled": False
        }
    }
    res = calculate_roi_mvp(case, policy)
    base = res["scenarios"][1]

    assert 0 < base["payback_dynamic_years"] <= 999
    assert base["annual_benefit_cents"] > 0
    assert res["financing_report"]["enabled"] is False

def test_roi_v3_integer_only_guaranteed():
    policy = load_v3_policy()
    case = {
        "attributes": {
            "has_heat_pump": True,
            "has_pv": False,
            "household_size": "2",
            "hp_input_mode": "MODE_B",
            "hp_bucket": "100_150",
        }
    }
    res = calculate_roi_mvp(case, policy)

    ea = res["export_analysis"]
    assert isinstance(ea["sharing_kwh"], int)
    assert isinstance(ea["eeg_kwh"], int)
    
    fr = res["financing_report"]
    assert isinstance(fr["loan_principal_eur"], int)
    assert isinstance(fr["loan_monthly_payment_eur"], int)
    assert isinstance(fr["monthly_cashflow_margin_eur"], int)


def test_roi_v3_backward_compat_opex_annual_cents():
    policy = load_v3_policy()
    # Verify fallback logic by removing the v3.5 opex block
    if "opex" in policy["parameters"]:
        del policy["parameters"]["opex"]
    policy["parameters"]["opex_annual_cents"] = 12345
    
    case = {
        "attributes": {
            "has_heat_pump": True,
            "has_pv": False,
            "household_size": "2",
            "hp_input_mode": "MODE_B",
            "hp_bucket": "100_150",
        }
    }
    res = calculate_roi_mvp(case, policy)
    assert res["verdict"] == "ROI_OK"
    assert res["breakdown_base"]["opex_cents"] == 12345


def test_roi_v3_scenario_specific_sharing():
    policy = load_v3_policy()
    
    # Force scenarios to have different sharing nets
    for s in policy["scenarios"]:
        s["match_factor_offset_bps"] = 0
        if "CONSERVATIVE" in s["name"]:
            s["energy_sharing_net_price_cents_x100"] = 1000
        elif "BASELINE" in s["name"]:
            s["energy_sharing_net_price_cents_x100"] = 1400
        elif "OPTIMISTIC" in s["name"]:
            s["energy_sharing_net_price_cents_x100"] = 1800
            
    case = {
        "attributes": {
            "has_heat_pump": True,
            "has_pv": False,
            "household_size": "2",
            "hp_input_mode": "MODE_B",
            "hp_bucket": "100_150",
        }
    }
    
    res = calculate_roi_mvp(case, policy)
    scenarios = res["scenarios"]
    
    y1_rev_conservative = scenarios[0]["sharing_revenue_cents_y1"]
    y1_rev_baseline = scenarios[1]["sharing_revenue_cents_y1"]
    y1_rev_optimistic = scenarios[2]["sharing_revenue_cents_y1"]
    
    assert y1_rev_conservative < y1_rev_baseline < y1_rev_optimistic


def test_roi_v3_carbon_impact_metrics():
    policy = load_v3_policy()
    # Explicitly set factors for testing stability
    policy["parameters"]["co2_factor_g_per_kwh"] = 400
    policy["parameters"]["car_co2_g_per_km"] = 100
    
    case = {
        "attributes": {
            "has_heat_pump": True,
            "has_pv": False,
            "household_size": "3",
            "hp_input_mode": "MODE_B",
            "hp_bucket": "100_150",
        }
    }
    res = calculate_roi_mvp(case, policy)
    
    assert "carbon_impact" in res
    ci = res["carbon_impact"]
    
    # PV gen for 100_150 (4500) + 3800 house = 8300 load. kwp_rec ~ 9. e_pv ~ 7740.
    e_pv = res["e_pv_kwh"]
    expected_kg = (e_pv * 400) // 1000
    assert ci["annual_co2_reduction_kg"] == expected_kg
    
    # 20y check
    baseline = res["scenarios"][1]
    assert "co2_20y_total_tons" in ci
    assert ci["co2_20y_total_tons"] == baseline["co2_20y_total_tons"]
    
    # Car km: kg * 1000 / 100
    assert ci["car_km_equivalent"] == (expected_kg * 1000) // 100
    
    # Structure of optional block
    assert "optional_illustrative_equivalents" in res
    assert "trees_equivalent_range" in res["optional_illustrative_equivalents"]
    
    # 20y tons should be less than 20 * annual tons due to degradation
    assert ci["co2_20y_total_tons"] < 20 * ci["annual_co2_reduction_tons"]
