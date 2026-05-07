from typing import Dict, List, Any, Tuple
from core.taxonomy import DataAcquisitionTier, ScoredDataPoint, HouseholdAssessmentData

def _resolve_input(val: Any, tier: DataAcquisitionTier, source: str) -> ScoredDataPoint:
    """Helper to wrap inputs into ScoredDataPoint."""
    if isinstance(val, ScoredDataPoint):
        return val
    return ScoredDataPoint(value=val, tier=tier, source_tracker=source)

# ---------------------------------------------------------------------------
# Helper: IRR via Binary Search (pure integer, returns bps)
# ---------------------------------------------------------------------------
def _calc_irr_bps(capex_cents: int, cashflows_cents: List[int]) -> int:
    """
    Calculates Internal Rate of Return (IRR) in Basis Points (bps).
    NPV = sum(CF_t * 10000^t / (10000 + r_bps)^t) - capex = 0
    Returns -9999 if IRR cannot be found (e.g. all CF are 0 or capex is 0).
    Uses binary search between -9900 bps (-99%) and 100000 bps (1000%).
    """
    if capex_cents <= 0 or not cashflows_cents:
        return 0
        
    def npv_at_bps(r_bps: int) -> int:
        npv = -capex_cents
        for t, cf in enumerate(cashflows_cents, start=1):
            num = cf * (10000 ** t)
            den = (10000 + r_bps) ** t
            npv += num // den
        return npv

    low = -9900
    high = 100000
    best_r = 0

    if npv_at_bps(low) < 0:
        return low
    if npv_at_bps(high) > 0:
        return high

    for _ in range(60):
        mid = (low + high) // 2
        val = npv_at_bps(mid)
        if val > 0:
            low = mid + 1
            best_r = mid
        elif val < 0:
            high = mid - 1
        else:
            return mid
            
    return best_r


# ---------------------------------------------------------------------------
# Helper: Calculate Export Stack (integer-only, cents_x100 prices)
# ---------------------------------------------------------------------------
def _calc_export_stack(
    export_kwh: int,
    p_feed_cents_x100: int,
    export_params: Dict[str, Any]
) -> Dict[str, int]:
    """
    Splits remaining export_kwh into Energy Sharing and EEG feed-in.
    All incoming prices are cents_x100.
    Returns calculated incomes in cents.
    """
    enabled = export_params.get("energy_sharing_enabled", True)
    realization_bps = export_params.get("energy_sharing_realization_bps", 7000)
    sharing_price_cents_x100 = export_params.get("energy_sharing_net_price_cents_x100", 1800)

    if not enabled or export_kwh <= 0:
        eeg_income_cents = (export_kwh * p_feed_cents_x100) // 100
        return {
            "sharing_kwh": 0,
            "eeg_kwh": export_kwh,
            "sharing_income_cents": 0,
            "eeg_income_cents": eeg_income_cents,
            "uplift_vs_eeg_only_cents": 0,
        }

    sharing_kwh = (export_kwh * realization_bps) // 10000
    eeg_kwh = export_kwh - sharing_kwh

    sharing_income_cents = (sharing_kwh * sharing_price_cents_x100) // 100
    eeg_income_cents = (eeg_kwh * p_feed_cents_x100) // 100

    eeg_on_sharing_portion = (sharing_kwh * p_feed_cents_x100) // 100
    uplift_vs_eeg_only_cents = sharing_income_cents - eeg_on_sharing_portion

    return {
        "sharing_kwh": sharing_kwh,
        "eeg_kwh": eeg_kwh,
        "sharing_income_cents": sharing_income_cents,
        "eeg_income_cents": eeg_income_cents,
        "uplift_vs_eeg_only_cents": uplift_vs_eeg_only_cents,
    }


# ---------------------------------------------------------------------------
# Helper: PMT via Binary Search Amortization (precise fraction)
# ---------------------------------------------------------------------------
def _calc_financing(
    capex_cents: int,
    benefit_y1_cents: int,
    fin_params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculates monthly loan payment using Binary Search Amortization.
    Uses num/den for APR down to month to avoid truncation bias.
    """
    principal_pct_bps = fin_params.get("loan_principal_pct_bps", 10000)
    term_years = fin_params.get("loan_term_years", 10)
    apr_bps = fin_params.get("loan_apr_bps", 450)

    principal_cents = (capex_cents * principal_pct_bps) // 10000
    months = term_years * 12

    # Monthly rate as fraction: apr_bps / (12 * 10000)
    monthly_rate_num = apr_bps
    monthly_rate_den = 12 * 10000

    low = principal_cents // months
    max_interest = (principal_cents * monthly_rate_num * months) // monthly_rate_den
    high = (principal_cents + max_interest) // months + 1

    pmt_cents = high
    for _ in range(64):
        mid = (low + high) // 2
        balance = principal_cents
        for _ in range(months):
            interest = (balance * monthly_rate_num) // monthly_rate_den
            balance = balance + interest - mid

        if balance > 0:
            low = mid + 1
        else:
            pmt_cents = mid
            high = mid

        if low >= high:
            break

    monthly_savings_cents = benefit_y1_cents // 12
    monthly_margin_cents = monthly_savings_cents - pmt_cents
    year1_net_cashflow_cents = benefit_y1_cents - (pmt_cents * 12)

    return {
        "loan_principal_cents": principal_cents,
        "loan_term_years": term_years,
        "loan_apr_bps": apr_bps,
        "loan_monthly_payment_cents": pmt_cents,
        "monthly_savings_cents": monthly_savings_cents,
        "monthly_cashflow_margin_cents": monthly_margin_cents,
        "year1_net_cashflow_after_loan_cents": year1_net_cashflow_cents,
        "is_cashflow_positive": monthly_margin_cents >= 0,
    }


# ---------------------------------------------------------------------------
# Helper: Property Wealth Effect (integer-only, cents)
# ---------------------------------------------------------------------------
def _calc_wealth_effect(
    profit20_cents: int,
    uplift_params: Dict[str, Any]
) -> Dict[str, Any]:
    area_min = uplift_params.get("area_sqm_min", 100)
    area_max = uplift_params.get("area_sqm_max", 150)
    price_min = uplift_params.get("price_eur_per_sqm_min", 4000)
    price_max = uplift_params.get("price_eur_per_sqm_max", 4200)
    
    # Overriden for narrower, more credible display range (2.5% - 3.5%) if not provided
    uplift_min_bps = uplift_params.get("property_uplift_display_pct_min_bps", 250)
    uplift_max_bps = uplift_params.get("property_uplift_display_pct_max_bps", 350)

    value_min_eur = area_min * price_min
    value_max_eur = area_max * price_max

    uplift_min_eur = (value_min_eur * uplift_min_bps) // 10000
    uplift_max_eur = (value_max_eur * uplift_max_bps) // 10000

    profit20_eur = profit20_cents // 100
    total_wealth_min_eur = profit20_eur + uplift_min_eur
    total_wealth_max_eur = profit20_eur + uplift_max_eur

    return {
        "property_value_range_eur": [value_min_eur, value_max_eur],
        "property_uplift_range_eur": [uplift_min_eur, uplift_max_eur],
        "cash_profit_20y_eur": profit20_eur,
        "total_wealth_increment_range_eur": [total_wealth_min_eur, total_wealth_max_eur],
    }


# ---------------------------------------------------------------------------
# Main: calculate_roi_mvp (v3.1)
# ---------------------------------------------------------------------------
def calculate_roi_mvp(case: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    """
    ROI MVP calculation v3.1 for Heat Pump owners (PV only).
    Applies pure limits vs scenario rates and export stack in loops.
    Now uses Level A/B/C taxonomy for data provenance and zero-inference safety.
    """
    attributes = case.get("attributes", {})
    
    # Tier C: Individual household data from manual input/Intake
    has_hp_dp = _resolve_input(attributes.get("has_heat_pump", True), DataAcquisitionTier.LEVEL_C, "Manual Input / Intake S1")
    has_pv_dp = _resolve_input(attributes.get("has_pv", False), DataAcquisitionTier.LEVEL_C, "Manual Input / Intake S1")

    # [ZERO_INFERENCE] Guardrail: Reject if already has PV (not a target customer)
    if has_pv_dp.value:
        return {
            "verdict": "ROI_NOT_TARGET",
            "reason": "Customer already has PV system — ROI MVP is for new installations only."
        }

    # HP flag determines load profile:
    #   has_heat_pump=True  → HEAT_PUMP    (60% self-consumption)
    #   has_heat_pump=False → HOUSEHOLD_ONLY (45% self-consumption, PV-only pitch)

    hp_mode_dp = _resolve_input(attributes.get("hp_input_mode", "MODE_B"), DataAcquisitionTier.LEVEL_C, "Manual Selection")
    ev_mode_dp = _resolve_input(attributes.get("electric_vehicle", "NONE"), DataAcquisitionTier.LEVEL_C, "Manual Selection")
    household_size_dp = _resolve_input(attributes.get("household_size", "3"), DataAcquisitionTier.LEVEL_C, "Manual Selection")
    
    # Tier B: Inferred / Mapped data
    hp_bucket = attributes.get("hp_bucket", "UNKNOWN")
    hp_bucket_dp = _resolve_input(hp_bucket, DataAcquisitionTier.LEVEL_B, f"Mapped from {hp_mode_dp.value} bucket '{hp_bucket}'")

    params = policy["parameters"]

    # 2. Base Load Calculation (kWh)
    e_base = params["e_base_table"].get(household_size_dp.value, params["e_base_table"]["3"])
    e_hp = params["hp_bucket_mapping"].get(hp_mode_dp.value, {}).get(hp_bucket_dp.value, 4500)

    e_load = e_base + e_hp

    # EV Load
    ev_load_mapping = params.get("ev_load_mapping", {"NONE": 0, "PLAN": 1500, "YES": 2500})
    ev_annual_kwh = ev_load_mapping.get(ev_mode_dp.value, 0)
    ev_pv_kwh = (ev_annual_kwh * params.get("pv_ev_share_bps", 4000)) // 10000

    e_load_total_potential = e_load + ev_pv_kwh

    ev_enabled = (ev_mode_dp.value != "NONE")
    if not has_hp_dp.value:
        # No heat pump → PV-only pitch → lower self-consumption
        load_profile_mode = "HOUSEHOLD_ONLY"
    elif ev_enabled:
        load_profile_mode = "HEAT_PUMP_EV"
    else:
        load_profile_mode = "HEAT_PUMP"

    # 3. Yield parameters (always computed — fix: must precede kwp_override path)
    # yield_per_kwp_override: optional street-level GIS signal (b_roof_norm based).
    # Formula: 900 + 200 * b_roof_norm  → maps [0,1] → [900, 1100] kWh/kWp/year
    _yield_override = attributes.get("yield_per_kwp_override", None)
    if _yield_override is not None:
        yield_per_kwp = int(_yield_override)
    else:
        yield_per_kwp = params["yield_per_kwp"]

    loss_bps = params["loss_bps"]
    net_yield_per_kwp_bps = yield_per_kwp * (10000 - loss_bps)

    # 4. Recommendation (kWp)
    # Check for GIS-driven override (Pilot requirement)
    kwp_override_dp = _resolve_input(attributes.get("kwp_override", None), DataAcquisitionTier.LEVEL_B, "GIS Segment Aggregation")

    if kwp_override_dp.value is not None:
        kwp_rec = int(round(float(kwp_override_dp.value)))
    else:
        kwp_rec = (e_load * 9000 + (net_yield_per_kwp_bps // 2)) // net_yield_per_kwp_bps

    if kwp_rec < 4: kwp_rec = 4   # min for small rowhouses
    if kwp_rec > 15: kwp_rec = 15  # max for large detached villas

    # 5. Annual Generation Year 1 (kWh)
    e_pv = (kwp_rec * net_yield_per_kwp_bps) // 10000


    # 5. Financial Params
    # Fallback support for old logic where p_grid_cents was provided
    if "p_grid_cents_x100" in params:
        p_grid_cents_x100_base = params["p_grid_cents_x100"]
    else:
        p_grid_cents_x100_base = params.get("p_grid_cents", 38) * 100
        
    p_feed_cents_x100 = params["p_feed_cents_x100"]
    
    opex_cfg = params.get("opex")
    if opex_cfg:
        opex_annual_cents = (opex_cfg.get("insurance_cents", 0) + 
                             opex_cfg.get("monitoring_cents", 0) + 
                             opex_cfg.get("maintenance_reserve_cents", 0))
    else:
        opex_annual_cents = params.get("opex_annual_cents", 20000)
    
    vat_rate_bps = params["vat_rate_bps"]


    degradation_bps = params.get("degradation_rate_bps_per_year", 50)
    incl_inverter = params.get("include_inverter_replacement", False)
    inv_year = params.get("inverter_replace_year", 13)
    inv_cost_cents = params.get("inverter_replace_cost_eur", 1500) * 100

    base_match_bps = params.get("load_profile_match_factors", {}).get(load_profile_mode, 6000)

    # 5b. Carbon Impact (Precise Reporting Layer)
    grid_co2_factor = params.get("co2_factor_g_per_kwh", 363)
    car_co2_factor = params.get("car_co2_g_per_km", 106)

    # Annual metrics
    annual_co2_reduction_kg = (e_pv * grid_co2_factor) // 1000
    annual_co2_reduction_tons = round(annual_co2_reduction_kg / 1000, 1)
    
    car_km_equivalent = int(round((annual_co2_reduction_kg * 1000) / car_co2_factor))
    grid_kwh_equivalent = int(round((annual_co2_reduction_kg * 1000) / grid_co2_factor))
    
    # Trees (Tier 3)
    trees_low = int(round(annual_co2_reduction_kg / 25))
    trees_high = int(round(annual_co2_reduction_kg / 10))
    trees_equivalent_range_per_year = [trees_low, trees_high]

    capex_vat0 = kwp_rec * params["capex_per_kwp_cents"] + params["install_fixed_cents"]
    capex_vat19 = (capex_vat0 * (10000 + vat_rate_bps)) // 10000
    vat_saving_cents = capex_vat19 - capex_vat0

    export_stack_params = params.get("export_stack", {})
    apply_years_mode = export_stack_params.get("apply_years_mode", "ALL_YEARS")
    sharing_mode = export_stack_params.get("energy_sharing_mode", "assumed")

    # 6. Scenarios
    scenarios = []
    for s_cfg in policy["scenarios"]:
        match_offset_bps = s_cfg.get("match_factor_offset_bps", 0)
        match_bps = base_match_bps + match_offset_bps
        g_bps = s_cfg["grid_escalation_bps"]
        
        scenario_export_params = dict(export_stack_params)
        if "energy_sharing_net_price_cents_x100" in s_cfg:
            scenario_export_params["energy_sharing_net_price_cents_x100"] = s_cfg["energy_sharing_net_price_cents_x100"]

        # Self consumption strict limit: min(pv * scenario_match, absolute_load)
        e_self_raw = (e_pv * match_bps) // 10000
        e_self_y1 = e_self_raw if e_self_raw < e_load_total_potential else e_load_total_potential
        e_export_y1 = e_pv - e_self_y1

        # Year 1 benefit
        y1_export_res = _calc_export_stack(e_export_y1, p_feed_cents_x100, scenario_export_params)
        benefit_y1 = (e_self_y1 * p_grid_cents_x100_base // 100) + y1_export_res["sharing_income_cents"] + y1_export_res["eeg_income_cents"] - opex_annual_cents

        payback_static_x100 = 999900
        if benefit_y1 > 0:
            payback_static_x100 = (capex_vat0 * 100) // benefit_y1

        # Dynamic Payback
        accumulated_cf = 0
        total_opex_20y = opex_annual_cents * 20
        total_pv_gen_20y = 0
        total_co2_reduction_kg_20y = 0
        dynamic_payback_year = 999
        p_grid_t_x100 = p_grid_cents_x100_base

        cashflows = []
        for t in range(1, 21):
            e_pv_t = (e_pv * (10000 - degradation_bps * (t - 1))) // 10000
            total_pv_gen_20y += e_pv_t
            
            # Yearly carbon contribution based on degraded generation
            total_co2_reduction_kg_20y += (e_pv_t * grid_co2_factor) // 1000

            e_self_raw_t = (e_pv_t * match_bps) // 10000
            e_self_t = e_self_raw_t if e_self_raw_t < e_load_total_potential else e_load_total_potential
            e_export_t = e_pv_t - e_self_t

            if apply_years_mode == "ALL_YEARS":
                t_export_res = _calc_export_stack(e_export_t, p_feed_cents_x100, scenario_export_params)
                export_income_t = t_export_res["sharing_income_cents"] + t_export_res["eeg_income_cents"]
            else:
                # YEAR1_ONLY fallback (EEG only in outer years)
                if t == 1:
                    t_export_res = _calc_export_stack(e_export_t, p_feed_cents_x100, scenario_export_params)
                    export_income_t = t_export_res["sharing_income_cents"] + t_export_res["eeg_income_cents"]
                else:
                    export_income_t = (e_export_t * p_feed_cents_x100) // 100

            cf_t = (e_self_t * p_grid_t_x100 // 100) + export_income_t - opex_annual_cents
            if incl_inverter and t == inv_year:
                cf_t -= inv_cost_cents

            accumulated_cf += cf_t
            cashflows.append(cf_t)

            if dynamic_payback_year == 999 and accumulated_cf >= capex_vat0:
                dynamic_payback_year = t

            p_grid_t_x100 = (p_grid_t_x100 * (10000 + g_bps)) // 10000

        irr_bps = _calc_irr_bps(capex_vat0, cashflows)

        profit20 = accumulated_cf - capex_vat0
        post_payback_profit = 0
        post_payback_avg = 0
        if dynamic_payback_year <= 20:
            post_payback_profit = profit20
            if dynamic_payback_year < 20:
                post_payback_avg = post_payback_profit // (20 - dynamic_payback_year)

        total_cost_20y = capex_vat0 + total_opex_20y
        if incl_inverter:
            total_cost_20y += inv_cost_cents
        lcoe_ct = total_cost_20y // total_pv_gen_20y if total_pv_gen_20y > 0 else 999

        scenarios.append({
            "name": s_cfg["name"],
            "match_factor_bps": match_bps,
            "grid_escalation_bps": g_bps,
            "e_self_kwh": e_self_y1,
            "e_export_kwh": e_export_y1,
            "annual_benefit_cents": benefit_y1,
            "payback_static_years_x100": payback_static_x100,
            "payback_dynamic_years": dynamic_payback_year,
            "profit20_cents": profit20,
            "post_payback_profit_20y": post_payback_profit,
            "post_payback_avg_annual_profit": post_payback_avg,
            "lcoe_ct_per_kwh": lcoe_ct,
            "irr_bps": irr_bps,
            "sharing_revenue_cents_y1": y1_export_res["sharing_income_cents"],
            "export_total_revenue_cents_y1": y1_export_res["sharing_income_cents"] + y1_export_res["eeg_income_cents"],
            "co2_20y_total_tons": round(total_co2_reduction_kg_20y / 1000, 1)
        })

    confidence = "MED"
    if hp_bucket == "UNKNOWN":
        confidence = "LOW"

    baseline = scenarios[1] if len(scenarios) > 1 else scenarios[0]
    
    baseline_export_params = dict(export_stack_params)
    s_baseline_cfg = policy["scenarios"][1] if len(policy["scenarios"]) > 1 else policy["scenarios"][0]
    if "energy_sharing_net_price_cents_x100" in s_baseline_cfg:
        baseline_export_params["energy_sharing_net_price_cents_x100"] = s_baseline_cfg["energy_sharing_net_price_cents_x100"]
        
    baseline_export_kwh = baseline["e_export_kwh"]
    baseline_benefit_y1 = baseline["annual_benefit_cents"]
    baseline_profit20 = baseline["profit20_cents"]

    # Export analysis
    export_analysis_raw = _calc_export_stack(baseline_export_kwh, p_feed_cents_x100, baseline_export_params)
    export_analysis = {
        "sharing_kwh": export_analysis_raw["sharing_kwh"],
        "eeg_kwh": export_analysis_raw["eeg_kwh"],
        "export_total_kwh": baseline_export_kwh,
        "sharing_revenue_cents": export_analysis_raw["sharing_income_cents"],
        "eeg_revenue_cents": export_analysis_raw["eeg_income_cents"],
        "export_total_revenue_cents": export_analysis_raw["sharing_income_cents"] + export_analysis_raw["eeg_income_cents"],
        "sharing_income_eur": export_analysis_raw["sharing_income_cents"] // 100,
        "eeg_income_eur": export_analysis_raw["eeg_income_cents"] // 100,
        "export_total_revenue_eur": (export_analysis_raw["sharing_income_cents"] + export_analysis_raw["eeg_income_cents"]) // 100,
        "uplift_vs_eeg_only_eur": export_analysis_raw["uplift_vs_eeg_only_cents"] // 100,
        "note": f"Export Stack modes: {apply_years_mode}. Income is applied dynamically into ROI scenarios.",
    }

    # Financing report
    fin_params_cfg = params.get("financing", {})
    
    # Overridable by UI payload
    if "financing_enabled" in attributes:
        financing_enabled = attributes["financing_enabled"]
    else:
        financing_enabled = fin_params_cfg.get("enabled", True)
        
    financing_report: Dict[str, Any] = {"enabled": False}

    if financing_enabled:
        fin_raw = _calc_financing(capex_vat0, baseline_benefit_y1, fin_params_cfg)
        financing_report = {
            "enabled": True,
            "loan_principal_eur": fin_raw["loan_principal_cents"] // 100,
            "loan_term_years": fin_raw["loan_term_years"],
            "loan_apr_bps": fin_raw["loan_apr_bps"],
            "loan_monthly_payment_eur": fin_raw["loan_monthly_payment_cents"] // 100,
            "monthly_savings_eur": fin_raw["monthly_savings_cents"] // 100,
            "monthly_cashflow_margin_eur": fin_raw["monthly_cashflow_margin_cents"] // 100,
            "year1_net_cashflow_after_loan_eur": fin_raw["year1_net_cashflow_after_loan_cents"] // 100,
            "is_cashflow_positive": fin_raw["is_cashflow_positive"],
            "note": "100% Loan / 10Y / 4.5% APR. Monthly savings based on BASELINE Year 1 benefit.",
        }

    # Wealth effect
    uplift_params_cfg = params.get("property_uplift", {})
    wealth_raw = _calc_wealth_effect(baseline_profit20, uplift_params_cfg)
    wealth_effect = {
        "property_value_range_eur": wealth_raw["property_value_range_eur"],
        "property_uplift_range_eur": wealth_raw["property_uplift_range_eur"],
        "cash_profit_20y_eur": wealth_raw["cash_profit_20y_eur"],
        "total_wealth_increment_range_eur": wealth_raw["total_wealth_increment_range_eur"],
        "note": "Property uplift is display-only. Does NOT affect payback_years or ROI metrics.",
    }

    # Format assumptions logic safely extracting values
    assump_grid = f"{p_grid_cents_x100_base/100:.2f}"
    assump_sharing_price = baseline_export_params.get("energy_sharing_net_price_cents_x100", 1800)
    assump_feedin = f"{p_feed_cents_x100/100:.2f}"
    
    sharing_disclaimer = ""
    if sharing_mode == "assumed":
        sharing_disclaimer = " (Assumed: Illustrative mode, pricing depends on local agreements)"
    elif sharing_mode == "contract_confirmed":
        sharing_disclaimer = " (Contract Confirmed)"

    result = {
        "verdict": "ROI_OK",
        "confidence": confidence,
        "kWp_rec": kwp_rec,
        "recommended_kwp": kwp_rec,
        "e_pv_kwh": e_pv,
        "e_load_kwh": e_load,
        "lcoe_ct_per_kwh": baseline["lcoe_ct_per_kwh"],
        "co2_saved_tons_per_year": annual_co2_reduction_tons,
        "carbon_impact": {
            "annual_co2_reduction_tons": annual_co2_reduction_tons,
            "annual_co2_reduction_kg": annual_co2_reduction_kg,
            "co2_20y_total_tons": baseline["co2_20y_total_tons"],
            "car_km_equivalent": car_km_equivalent,
            "grid_electricity_kwh_equivalent": grid_kwh_equivalent
        },
        "optional_illustrative_equivalents": {
            "trees_equivalent_range": trees_equivalent_range_per_year,
            "note": "Highly illustrative only; depends strongly on species, age, survival, and location."
        },
        "data_taxonomy": {
            "building_footprint": has_hp_dp.model_dump(),
            "household_size": household_size_dp.model_dump(),
            "hp_potential": hp_bucket_dp.model_dump(),
            "ev_status": ev_mode_dp.model_dump()
        },
        "trees_equivalent_range_per_year": trees_equivalent_range_per_year,
        "capex": {
            "vat0_cents": capex_vat0,
            "vat19_cents": capex_vat19,
            "vat_saving_cents": vat_saving_cents,
            "basis_eur_per_kwp": params["capex_per_kwp_cents"] // 100,
            "basis_fixed_eur": params["install_fixed_cents"] // 100,
        },
        "household_snapshot": {
            "household_size": household_size_dp.value,
            "e_base_kwh": e_base,
            "e_hp_kwh": e_hp,
            "ev_annual_kwh": ev_annual_kwh,
            "e_load_total_kwh": e_load + ev_annual_kwh,
            "hp_mode": hp_mode_dp.value
        },
        "scenarios": scenarios,
        "breakdown_base": {
            "self_saving_cents": (baseline["e_self_kwh"] * p_grid_cents_x100_base) // 100,
            # feed_income_cents explicitly means EXPORT REVENUE (combining Sharing + EEG)
            "feed_income_cents": export_analysis_raw["sharing_income_cents"] + export_analysis_raw["eeg_income_cents"],
            "opex_cents": opex_annual_cents,
            "opex_breakdown": opex_cfg if opex_cfg else {"opex_annual_cents": opex_annual_cents}
        },
        "energy_sharing_mode": sharing_mode,
        "export_analysis": export_analysis,
        "financing_report": financing_report,
        "wealth_effect": wealth_effect,
        "assumptions": [
            f"DEFAULT (assumed): Grid Electricity Price @ {assump_grid} cents/kWh",
            f"DEFAULT (assumed): Grid Escalation @ {baseline['grid_escalation_bps']/100:.1f}% per year (based on last 10Y)",
            f"[v3.5] Feed-in Tariff @ {assump_feedin} ct/kWh \\n(BNetzA EEG Vergütungssätze – reference value for 2026 installations, subject to confirmation at commissioning date)",
            f"DEFAULT (assumed): PV Yield Neuss @ {yield_per_kwp} kWh/kWp",
            f"DEFAULT (assumed): PV Degradation @ {degradation_bps/100:.1f}% per year",
            f"DEFAULT (assumed): System Loss @ {loss_bps/100:.1f}% (combined)",
            f"DEFAULT (assumed): CAPEX @ {params['capex_per_kwp_cents']//100} EUR/kWp + {params['install_fixed_cents']//100} EUR fix (VAT 0%)",
            f"DEFAULT (assumed): VAT @ {vat_rate_bps/100:.0f}% (calculated for audit display only)",
            f"[v3.5] Household base load @ {e_base} kWh/a \\nTypical consumption range for a {household_size_dp.value}-person household in Germany. (DEFAULT_ASSUMED_LOAD)",
            f"[v3.5] Heat pump load ({hp_mode_dp.value}) @ {e_hp} kWh/a",
            f"[v3.1] EV Engine mode '{ev_mode_dp.value}' @ +{ev_pv_kwh} kWh PV consumption",
            f"DEFAULT (assumed): Inverter Replacement @ {inv_year}Y: {'Yes' if incl_inverter else 'No'}",
            f"[v3.5] Export Stack loop: {apply_years_mode} | Sharing Mode ({sharing_mode}): {sharing_disclaimer} | {export_stack_params.get('energy_sharing_realization_bps', 7000)/100:.0f}% @ {assump_sharing_price/100:.2f} ct/kWh",
            f"[v3.1] Financing: {'Enabled' if financing_enabled else 'Disabled'} | 100% Loan / {fin_params_cfg.get('loan_term_years', 10)}Y / {fin_params_cfg.get('loan_apr_bps', 450)/100:.1f}% APR",
            f"[v3.5] Note: breakdown_base.feed_income_cents represents all export revenue (Sharing + EEG).",
            "Note: Dynamic Payback includes grid price escalation; Static does not.",
            f"[v3.5] Advanced: 20-Year Baseline IRR ({baseline.get('irr_bps', 0)/100:.1f}%) is an auxiliary orientation metric and must not affect core payback conclusions.",
            "Environmental equivalents are illustrative comparisons based on stated reference emission factors.",
            f"CO₂ avoidance is estimated using an average German grid-emission factor ({grid_co2_factor} g/kWh) and is intended for orientation only.",
            "Tree comparison is highly illustrative and depends strongly on species, growth conditions, and time horizon."
        ],
    }

    return result


# ---------------------------------------------------------------------------
# Dual-Scenario Wrapper: calculate_roi_dual (KI C12 — Locked 2026-04-20)
# ---------------------------------------------------------------------------
def calculate_roi_dual(base_case: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    """
    ROI Dual-Scenario Wrapper — computes HOUSEHOLD_ONLY and HIGH_LOAD simultaneously.

    DESIGN CONTRACT (KI C12, additive — does NOT modify calculate_roi_mvp):
        HOUSEHOLD_ONLY: has_heat_pump=False, hp_input_mode=HOUSEHOLD_ONLY, hp_bucket=NONE
                        → e_hp = 0 (policy HOUSEHOLD_ONLY/NONE key), load_profile=HOUSEHOLD_ONLY
                        → annual load ≈ e_base only (~3,500 kWh for 3-person), self-consumption 45%
        HIGH_LOAD:      has_heat_pump=True,  hp_input_mode=MODE_B,         hp_bucket=100_150
                        → e_hp ≈ 4,500 kWh, load_profile=HEAT_PUMP, self-consumption 60%

    Returns:
        {
            "household":      <roi_result for HOUSEHOLD_ONLY scenario>,
            "high_load":      <roi_result for HIGH_LOAD / HEAT_PUMP scenario>,
            "delta_annual_eur": float (high_load Y1 benefit − household Y1 benefit),
            "hp_uplift_class": "STRONG_HP_UPLIFT" | "MODERATE_HP_UPLIFT" | "LIMITED_HP_UPLIFT"
        }
    """
    import copy

    # ── HOUSEHOLD_ONLY case ───────────────────────────────────────────────────
    case_hh = copy.deepcopy(base_case)
    case_hh.setdefault("attributes", {})
    case_hh["attributes"]["has_heat_pump"]  = False
    case_hh["attributes"]["hp_input_mode"]  = "HOUSEHOLD_ONLY"  # maps to e_hp=0 via policy
    case_hh["attributes"]["hp_bucket"]      = "NONE"
    case_hh["attributes"]["electric_vehicle"] = "NONE"           # conservative: no EV
    case_hh["case_id"] = str(base_case.get("case_id", "DUAL")) + "_HOUSEHOLD_ONLY"

    # ── HIGH_LOAD case ────────────────────────────────────────────────────────
    case_hl = copy.deepcopy(base_case)
    case_hl.setdefault("attributes", {})
    case_hl["attributes"]["has_heat_pump"]  = True
    case_hl["attributes"]["hp_input_mode"]  = "MODE_B"
    # Preserve caller's hp_bucket if present; fallback to 100_150 (moderate HP)
    if not case_hl["attributes"].get("hp_bucket") or case_hl["attributes"]["hp_bucket"] == "NONE":
        case_hl["attributes"]["hp_bucket"]  = "100_150"
    case_hl["case_id"] = str(base_case.get("case_id", "DUAL")) + "_HIGH_LOAD"

    # ── Run both scenarios ────────────────────────────────────────────────────
    result_hh = calculate_roi_mvp(case_hh, policy)
    result_hl = calculate_roi_mvp(case_hl, policy)

    # ── Extract Y1 BASELINE benefit for delta calculation ─────────────────────
    def _y1_benefit_eur(roi: Dict[str, Any]) -> float:
        """Return Y1 annual_benefit in EUR from BASELINE scenario (index 1), or 0."""
        if roi.get("verdict") != "ROI_OK":
            return 0.0
        scens = roi.get("scenarios", [])
        baseline = scens[1] if len(scens) > 1 else (scens[0] if scens else {})
        return baseline.get("annual_benefit_cents", 0) / 100.0

    hh_benefit = _y1_benefit_eur(result_hh)
    hl_benefit  = _y1_benefit_eur(result_hl)
    delta       = round(hl_benefit - hh_benefit, 2)

    # ── HP uplift classification (mirrors KI C12 UWG framing rules) ──────────
    # delta >= 400 EUR/year → STRONG   (headline: high_load savings)
    # delta >= 150 EUR/year → MODERATE (headline: high_load savings, moderate footnote)
    # delta <  150 EUR/year → LIMITED  (headline: household savings only)
    if delta >= 400:
        hp_uplift_class = "STRONG_HP_UPLIFT"
    elif delta >= 150:
        hp_uplift_class = "MODERATE_HP_UPLIFT"
    else:
        hp_uplift_class = "LIMITED_HP_UPLIFT"

    return {
        "household":       result_hh,
        "high_load":       result_hl,
        "delta_annual_eur": delta,
        "hp_uplift_class":  hp_uplift_class,
    }
