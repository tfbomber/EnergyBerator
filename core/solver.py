from typing import Dict, Tuple, List
from decimal import Decimal
from datetime import datetime
# from .cost_engine import parse_date # Helper needed? No, separate logic.


def _parse_date_flexible(date_str: str):
    if not date_str:
        return None
    s = str(date_str).strip()
    if not s:
        return None

    if "T" in s:
        clean = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(clean)
        except ValueError:
            pass

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue

    return None


def _get_timeline_event_date(case: Dict, event_type: str):
    for event in case.get("timeline_events", []):
        if event.get("event_type") == event_type:
            return _parse_date_flexible(event.get("date", ""))
    return None

def solve(policy: Dict, case: Dict, eligible_cents: int) -> Tuple[int, List[Dict], bool]:
    """
    Determines the final subsidy amount by applying grant rates, bonuses, and caps.
    Returns: (FinalSubsidyCents, AuditTrail, FinalLocked)
    """
    audit_trail = []
    
    # Identify if the final calculation is "locked" based on cost basis
    final_locked = True
    case_costs = case.get("costs", {})
    case_buckets = case_costs.get("buckets", {})
    if not case_buckets:
        final_locked = False
    else:
        for bucket_name, bucket in case.get("costs", {}).get("buckets", {}).items():
            certainty = bucket.get("certainty", "ESTIMATE")
            # Only FIRM_QUOTE or CONTRACT are considered "locked"
            if certainty not in ["CONTRACT", "FIRM_QUOTE"]:
                final_locked = False
                break
    calc_rules = policy["calculation"]
    
    # 1. Base Parameters
    grant_rate = Decimal(str(calc_rules.get("grant_rate", 1.0))) # Default 100% if missing
    cap_cents = calc_rules["cap_cents"]
    cap_anchor = calc_rules["evidence_anchor"]
    
    fixed_bonus_cents = 0
    active_bonuses = []
    
    # 2. Apply Bonuses
    case_attributes = case.get("attributes", {})
    
    if "bonuses" in calc_rules:
        for bonus in calc_rules["bonuses"]:
            code = bonus["code"]
            trigger = bonus["trigger"]
            effect = bonus["effect"]
            is_triggered = False
            trigger_reason = ""
            
            # Trigger Logic
            if trigger == "USER_ATTRIBUTE":
                # Primary form: attributes[code] == trigger_value
                req_val = bonus.get("trigger_value", True)
                if case_attributes.get(code) == req_val:
                    is_triggered = True
                # Compatibility form: attributes.bonuses contains bonus code
                # (used by S1 intake payload for YES selections)
                elif req_val is True:
                    bonuses = case_attributes.get("bonuses", [])
                    if isinstance(bonuses, list) and code in bonuses:
                        is_triggered = True
                    else:
                        trigger_reason = "User did not select this bonus."
                else:
                    trigger_reason = "Required user attribute value not met."
            elif trigger == "HARDWARE_LABEL":
                # Check hardware specs (Mock logic for now: assume attribute also holds this)
                # In real engine, we'd check cost buckets for 'specs'
                req_val = bonus.get("trigger_value")
                if case_attributes.get(code) == req_val:
                     is_triggered = True
                else:
                     trigger_reason = "Required hardware label was not found."

            if not is_triggered:
                audit_trail.append({
                    "step_id": f"BONUS_NOT_REQUESTED_{code}",
                    "description": f"Bonus {code} not applied. {trigger_reason or 'Trigger conditions were not met.'}",
                    "amount_cents": 0,
                    "amount_eur": "0.00",
                    "evidence_anchor": bonus["evidence_anchor"],
                    "source_url": policy["citations"]["source_url"],
                    "doc_version": policy["citations"]["doc_version"]
                })
                continue

            eligibility_failed = False
            for check in bonus.get("eligibility_checks", []):
                check_type = check.get("type")
                reason_code = check.get("reason_code", "CHECK_FAILED")
                evidence_anchor = check.get("evidence_anchor", bonus["evidence_anchor"])

                if check_type == "DATE_ON_OR_BEFORE":
                    event_type = check.get("event_type", "APPLICATION_SUBMITTED")
                    latest_date = _parse_date_flexible(check.get("latest_date", ""))
                    actual_date = _get_timeline_event_date(case, event_type)

                    if actual_date is None:
                        eligibility_failed = True
                        audit_trail.append({
                            "step_id": f"BONUS_SKIPPED_{code}_{reason_code}",
                            "description": (
                                f"Bonus {code} skipped: required date {event_type} is missing. "
                                f"Fallback to standard rate/cap."
                            ),
                            "amount_cents": 0,
                            "amount_eur": "0.00",
                            "evidence_anchor": evidence_anchor,
                            "source_url": policy["citations"]["source_url"],
                            "doc_version": policy["citations"]["doc_version"]
                        })
                    elif latest_date is not None and actual_date > latest_date:
                        eligibility_failed = True
                        audit_trail.append({
                            "step_id": f"BONUS_SKIPPED_{code}_{reason_code}",
                            "description": (
                                f"Bonus {code} skipped: {event_type}={actual_date.strftime('%Y-%m-%d')} "
                                f"is after cutoff {latest_date.strftime('%Y-%m-%d')}. "
                                f"Fallback to standard rate/cap."
                            ),
                            "amount_cents": 0,
                            "amount_eur": "0.00",
                            "evidence_anchor": evidence_anchor,
                            "source_url": policy["citations"]["source_url"],
                            "doc_version": policy["citations"]["doc_version"]
                        })

                elif check_type == "USER_ATTRIBUTE":
                    attr_name = check.get("attribute")
                    expected = check.get("expected", True)
                    
                    if attr_name not in case_attributes:
                        # ZERO INFERENCE BLOCK: Hard stop
                        print(f"DEBUG SOLVER.PY: Missing {attr_name}. Full case_attributes: {case_attributes}")
                        raise ValueError(f"Missing required attribute for bonus '{code}': {attr_name}. Please provide whether {attr_name} is true or false.")
                        
                    actual = case_attributes.get(attr_name)
                    if actual != expected:
                        eligibility_failed = True
                        audit_trail.append({
                            "step_id": f"BONUS_SKIPPED_{code}_{reason_code}",
                            "description": (
                                f"Bonus {code} skipped: required attribute {attr_name}={expected} not satisfied "
                                f"(actual={actual}). Fallback to standard rate/cap."
                            ),
                            "amount_cents": 0,
                            "amount_eur": "0.00",
                            "evidence_anchor": evidence_anchor,
                            "source_url": policy["citations"]["source_url"],
                            "doc_version": policy["citations"]["doc_version"]
                        })

            if eligibility_failed:
                continue
            
            active_bonuses.append(code)
            # Apply Effects
            if "set_grant_rate" in effect:
                grant_rate = Decimal(str(effect["set_grant_rate"]))
            if "set_cap_cents" in effect:
                cap_cents = effect["set_cap_cents"]
                cap_anchor = bonus["evidence_anchor"] # Update anchor to bonus rule
            if "add_fixed_cents" in effect:
                fixed_bonus_cents += effect["add_fixed_cents"]
                
            audit_trail.append({
                "step_id": f"BONUS_APPLIED_{code}",
                "description": f"Bonus {code} triggered. Effects: {effect}",
                "amount_cents": 0,
                "amount_eur": "0.00",
                "evidence_anchor": bonus["evidence_anchor"],
                "source_url": policy["citations"]["source_url"],
                "doc_version": policy["citations"]["doc_version"]
            })

    # 3. Calculation
    calc_type = calc_rules.get("type", "GRANT_ON_ELIGIBLE_COST")
    
    eligible_decimal = Decimal(eligible_cents)
    
    if calc_type == "FIXED_AMOUNT_TIERS":
        if "system_kw" not in case_attributes:
            raise ValueError("Missing required attribute: system_kw. ZERO_INFERENCE enforced.")
        system_kw = Decimal(str(case_attributes.get("system_kw")))
        tier_amount_cents = 0
        for tier in calc_rules.get("tiers", []):
            min_kw = Decimal(str(tier.get("min_kw", 0)))
            max_kw = Decimal(str(tier.get("max_kw", 999999)))
            if system_kw > min_kw and system_kw <= max_kw:
                tier_amount_cents = tier["amount_cents"]
                break
        sub_base_cents = Decimal(tier_amount_cents)
    else:
        sub_base_cents = eligible_decimal * grant_rate

    sub_total_cents = sub_base_cents + Decimal(fixed_bonus_cents)

    # 4. Apply Stacking Limit (Kumulierungsgrenze)
    # Total Subsidies <= Total Costs * stacking_limit
    stacking_limit = Decimal(str(calc_rules.get("stacking_limit", 1.0)))
    if stacking_limit < Decimal("1.0"):
        other_subsidies_cents = Decimal(str(case_attributes.get("other_subsidies_cents", 0)))
        max_allowed_total = eligible_decimal * stacking_limit
        max_city_share = max(Decimal("0.0"), max_allowed_total - other_subsidies_cents)
        
        cutoff_applied = min(sub_total_cents, max_city_share)
        
        audit_trail.append({
            "step_id": "STACKING_VALIDATION",
            "description": f"Kumulierungsgrenze (叠加上限扣减) Applied: Max {int(stacking_limit*100)}% of eligible costs ({max_allowed_total/100:.2f}€). Provided existing subsidies: {other_subsidies_cents/100:.2f}€.",
            "amount_cents": int(cutoff_applied),
            "amount_eur": f"{cutoff_applied/100:.2f}",
            "evidence_anchor": cap_anchor,
            "source_url": policy["citations"]["source_url"],
            "doc_version": policy["citations"]["doc_version"]
        })
        
        sub_total_cents = cutoff_applied
    else:
        audit_trail.append({
            "step_id": "STACKING_VALIDATION",
            "description": "Stacking limit conceptually evaluated as 100%. User must externally verify no overriding federal law blocks this. [WARNING: Stacking not fully verified, please confirm].",
            "amount_cents": 0,
            "amount_eur": "0.00",
            "evidence_anchor": cap_anchor,
            "source_url": policy["citations"]["source_url"],
            "doc_version": policy["citations"]["doc_version"]
        })

    
    # Rounding and Base Cap
    sub_total_cents = sub_total_cents.quantize(Decimal("1"), rounding='ROUND_HALF_UP')
    final_subsidy_cents = min(int(sub_total_cents), cap_cents)
    
    # Audit Trail
    audit_trail.append({
        "step_id": "SUBSIDY_CALCULATION",
        "description": f"Eligible: {eligible_cents/100:.2f}€. Rate: {grant_rate*100:.0f}%. Fixed Bonus: {fixed_bonus_cents/100:.2f}€. Cap: {cap_cents/100:.2f}€. Final: {final_subsidy_cents/100:.2f}€.",
        "amount_cents": final_subsidy_cents,
        "amount_eur": f"{final_subsidy_cents/100:.2f}",
        "evidence_anchor": cap_anchor,
        "source_url": policy["citations"]["source_url"],
        "doc_version": policy["citations"]["doc_version"]
    })
    
    return final_subsidy_cents, audit_trail, final_locked
