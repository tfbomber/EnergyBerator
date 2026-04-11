from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Tuple, List

def to_cents(amount: Decimal) -> int:
    """Converts Decimal EUR to Integer Cents."""
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def compute_eligible_cost_cents(policy: Dict, case: Dict) -> Tuple[int, List[Dict]]:
    """
    Calculates the total eligible cost basis in cents.
    """
    total_eligible_cents = 0
    audit_trail = []
    
    policy_buckets = policy["cost_rules"]["buckets"]
    case_buckets = case["costs"]["buckets"]
    
    # Determine default basis from policy
    default_basis = policy["cost_rules"]["input_amount_basis"]
    
    for bucket_name, bucket_data in case_buckets.items():
        # Skip if not eligible in policy
        if bucket_name not in policy_buckets or not policy_buckets[bucket_name]["eligible"]:
            continue
            
        policy_bucket_rule = policy_buckets[bucket_name]
        
        # 1. Get raw amount (Decimal)
        raw_amount_str = bucket_data.get("amount")
        if raw_amount_str is None or str(raw_amount_str).strip() == "":
            raise ValueError(
                f"Missing required cost amount for bucket '{bucket_name}'. ZERO_INFERENCE enforced."
            )

        try:
            raw_amount = Decimal(str(raw_amount_str))
        except InvalidOperation as exc:
            raise ValueError(
                f"Invalid decimal amount for bucket '{bucket_name}': {raw_amount_str}"
            ) from exc
        
        # 2. Determine Basis (Net vs Gross)
        input_basis = bucket_data.get("amount_basis") or default_basis
        target_basis = policy["calculation"]["eligible_basis"] # Gross or Net
        raw_vat = str(policy_bucket_rule["vat_rate"]).strip()
        if raw_vat.endswith("%"):
            vat_rate = Decimal(raw_vat[:-1]) / Decimal("100")
        else:
            vat_rate = Decimal(raw_vat)
        eligible_amount = Decimal("0.00")
        
        if input_basis == "NET" and target_basis == "GROSS":
             # Add VAT
             eligible_amount = raw_amount * (Decimal("1.00") + vat_rate)
        elif input_basis == "GROSS" and target_basis == "NET":
             # Remove VAT
             eligible_amount = raw_amount / (Decimal("1.00") + vat_rate)
        else:
             # Match or unknown basis - take as is
             eligible_amount = raw_amount
             
        # Round to 2 decimals first
        eligible_amount = eligible_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cents = to_cents(eligible_amount)
        
        total_eligible_cents += cents
        
        # Audit Trail
        audit_trail.append({
            "step_id": f"COST_CALC_{bucket_name}",
            "description": f"Eligible Cost for {bucket_name}: {eligible_amount} EUR ({target_basis})",
            "amount_cents": cents,
            "amount_eur": str(eligible_amount),
            "evidence_anchor": policy_bucket_rule.get("evidence_anchor", policy.get("calculation", {}).get("evidence_anchor", "")),
            "source_url": policy["citations"]["source_url"],
            "doc_version": policy["citations"]["doc_version"]
        })
        
    return total_eligible_cents, audit_trail
