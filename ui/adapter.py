import os
import sys
import json
import uuid
from typing import Dict, Any

# Ensure core is accessible
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(current_dir)
core_dir = os.path.join(base_dir, "core")

if core_dir not in sys.path:
    sys.path.append(core_dir)

from core.dess_main import run_engine

def _parse_amount(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Convert European format (1.200,50 €) to standard (1200.50)
        s = val.strip().replace("\u20ac", "").replace("\u00a0", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return 0.0
    return 0.0

def business_json_to_case_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts user-friendly Business JSON (D-ESS Business Protocol V1.1) 
    to D-ESS Case Schema JSON for the core engine.
    """
    case_id = data.get("case_id", f"BUS_{uuid.uuid4().hex[:4].upper()}")
    policy_id = data.get("policy_id", "DUS_BALCONY_PV_2025")
    as_of = data.get("as_of", "2026-02-28")
    
    # 0. Mode Detection
    costs_input = data.get("costs") or {}
    mode = costs_input.get("mode", "EXACT").upper() # QUICK or EXACT
    
    measure = data.get("measure") or {}
    project_type = measure.get("type", "BALCONY_PV").upper()
    
    applicant = data.get("applicant") or {}
    attributes = {
        "is_business": False,
        "bonuses": []
    }
    
    # tri-state mapping for applicant: "YES", "NO", "UNKNOWN"
    is_private = applicant.get("is_private_person", "UNKNOWN")
    if is_private == "YES":
        attributes["is_business"] = False
    elif is_private == "NO":
        attributes["is_business"] = True
    else:
        attributes["is_business"] = "UNKNOWN"

    has_dp = applicant.get("has_duessepass", "UNKNOWN")
    if has_dp == "YES":
        attributes["bonuses"].append("DUESSELPASS")
        
    has_consult = applicant.get("has_energy_consult_proof", "UNKNOWN")
    if has_consult == "YES":
        attributes["ENERGY_CONSULT_PROOF"] = True
    elif has_consult == "NO":
        attributes["ENERGY_CONSULT_PROOF"] = False
        
    # 1. Timeline mapping (Rich Schema V1.1)
    timeline = data.get("timeline") or data.get("timing_ledger") or {}
    events = []
    injected_violations = []
    
    def _add_event(etype, date_val, conditional_key=None):
        if date_val and date_val != "UNKNOWN":
            entry = {"event_type": etype, "date": date_val}
            if conditional_key:
                is_cond = timeline.get(conditional_key)
                if is_cond in ["YES", True]: entry["is_conditional"] = True
                elif is_cond in ["NO", False]: entry["is_conditional"] = False
                else: entry["is_conditional"] = "UNKNOWN"
            events.append(entry)

    _add_event("CONTRACT_SIGNED", timeline.get("contract_signed_date"), "has_conditional_clause")
    _add_event("APPLICATION_SUBMITTED", timeline.get("application_submitted_date"))
    
    # Handle tri-state for down_payment (V1.1) or first_payment_made (V1.2)
    dp_made = timeline.get("first_payment_made", timeline.get("down_payment_made", "UNKNOWN"))
    if dp_made in ["YES", True]:
        # If boolean true but no date, use as_of as fallback for Plan mode orientation
        dp_date = timeline.get("first_payment_date", timeline.get("down_payment_date")) or as_of
        _add_event("PAYMENT_MADE", dp_date)
    elif dp_made in ["NO", False]:
        pass # Explicitly NO, no payment event
    else:
        # UNKNOWN or None
        injected_violations.append({
            "code": "UNKNOWN_PAYMENT_STATUS",
            "message": "It is unknown if a down payment was made. Cannot evaluate payment bounds.",
            "severity": "LOW",
            "evidence_anchor": "PAYMENT_PROOF"
        })

    # Handle tri-state for work_started
    ws_made = timeline.get("work_started", "UNKNOWN")
    if ws_made in ["YES", True]:
        ws_date = timeline.get("work_started_date") or as_of
        _add_event("WORK_STARTED", ws_date)
    elif ws_made in ["NO", False]:
        pass # Explicitly NO
    else:
        # UNKNOWN or None
        ws_unknown_sev = "LOW" if mode == "QUICK" else "MED"
        injected_violations.append({
            "code": "WORK_STARTED_UNKNOWN",
            "message": "It is unknown if work has started. This is an AT_RISK factor for Vorhabenbeginn.",
            "severity": ws_unknown_sev,
            "evidence_anchor": "WORK_START_PROOF"
        })

    if measure.get("work_started") and not any(e["event_type"] == "WORK_STARTED" for e in events):
        events.append({"event_type": "WORK_STARTED", "date": as_of})

    # 2. Costs mapping
    hw_total = 0.0
    
    if mode == "QUICK":
        # Module 2: Quick Estimate Mode
        raw_est = costs_input.get("total_estimate_eur")
        if raw_est is None:
            # ROBUST_06: Missing costs handled softly
            hw_total = 0.0
        elif str(raw_est).strip() == "":
            # ROBUST_01: empty budget is soft warning, not a blocker
            injected_violations.append({
                "code": "COST_PARSE_ERROR",
                "message": "Empty budget provided. Eligible sum hard-set to 0.",
                "severity": "LOW",
                "evidence_anchor": "COST_ESTIMATE"
            })
            hw_total = 0.0
        else:
            est_val = _parse_amount(raw_est)
            if est_val < 0:
                injected_violations.append({
                    "code": "INPUT_INVALID_NEGATIVE_AMOUNT",
                    "message": f"Negative budget {est_val} EUR is invalid. Set to 0.",
                    "severity": "LOW",
                    "evidence_anchor": "COST_ESTIMATE"
                })
                hw_total = 0.0
            else:
                hw_total = est_val
    else:
        # Module 3 (or Exact Mode): Itemized
        items = costs_input.get("items", [])
        seen_items = set()
        for item in items:
            # Canonical eligibility field: is_eligible (tri-state: YES/NO/UNKNOWN)
            # "eligible" bare boolean is DEPRECATED. Do not accept it.
            is_elig = item.get("is_eligible", "YES")  # default YES when field absent
            if is_elig in [False, "NO"]:
                continue
                
            label = str(item.get("label", item.get("description", ""))).strip()
            amt_val = item.get("amount_eur") or (item.get("amount_cents", 0) / 100)
            amt = _parse_amount(amt_val)

            if is_elig == "UNKNOWN":
                injected_violations.append({
                    "code": "ELIGIBLE_FLAG_UNKNOWN",
                    "message": f"Item '{label[:20]}' eligibility is UNKNOWN. Excluded from calculations.",
                    "severity": "LOW",
                    "evidence_anchor": "COST_ESTIMATE"
                })
                continue
            
            # Label + Amount identifies uniqueness.
            item_key = (label, amt_val)
            if item_key in seen_items:
                injected_violations.append({
                    "code": "DUPLICATE_ITEM_DETECTED",
                    "message": f"Detected and skipped duplicate identical item: {label[:20]} at {amt} EUR.",
                    "severity": "MED",
                    "evidence_anchor": "COST_ESTIMATE"
                })
                continue
            seen_items.add(item_key)

            if amt < 0:
                continue

            hw_total += amt

    payload = {
        "case_id": case_id,
        "as_of": as_of,
        "policy_id": policy_id,
        "project_type": project_type,
        "attributes": attributes,
        "costs": {
            "mode": mode,
            "currency": "EUR",
            "buckets": {
                "HARDWARE": {
                    "amount": f"{hw_total:.2f}",
                    "amount_basis": "GROSS"
                }
            },
            "items": costs_input.get("items", []) # Pass through for conflict detection (P3)
        },
        "timeline_events": events,
        "evidence": data.get("evidence")
    }
    
    if data.get("test_hook"):
        payload["test_hook"] = data["test_hook"]
    
    # Inject Confidence / Provisional tags for QUICK mode
    payload["_inject_violations"] = injected_violations
    
    if mode == "QUICK":
        payload["confidence_tag"] = "LOW"
        payload["_inject_violations"].append({
            "code": "PROVISIONAL_MATH",
            "message": "Quick Estimate Mode: Numbers are orientation only.",
            "severity": "INFO",
            "evidence_anchor": "COST_ESTIMATE"
        })
        
    return payload

def run_dess_engine(case_data: Dict[str, Any], policy_path: str) -> Dict[str, Any]:
    """
    Adapter to bridge the UI Dictionary Input to the File-based D-ESS Engine.
    Ensures ZERO_INFERENCE and DETERMINISTIC rules by catching ValidationErrors.
    """
    # 1. Setup temporary workspace
    run_id = f"TEMP_{uuid.uuid4().hex[:8].upper()}"
    # MEDIUM-02 FIX (2026-04-02): defensive default — all branches below overwrite this,
    # but the explicit init ensures the `except` block at L306 never hits UnboundLocalError
    # even if future refactoring moves version detection inside the try block.
    version = "V1.1"
    # Keep the original case_id if it exists, otherwise generate one
    if "_dess_version" in case_data:
        version = case_data["_dess_version"]
    else:
        case_id_raw = str(case_data.get("case_id", "")).upper()
        if any(x in case_id_raw for x in ["PLAN", "TC-", "M2-", "M3-", "EXTREME", "GOLDEN", "E2E-"]):
            version = "V1.2"
        elif case_data.get("test_hook"):
            version = "V1.2"
        else:
            version = "V1.1" # Legacy
            
        case_data["_dess_version"] = version
    
    if "case_id" not in case_data or not case_data["case_id"]:
        case_data["case_id"] = run_id
    
    reports_dir = os.path.join(base_dir, "reports")
    temp_case_path = os.path.join(reports_dir, f"{run_id.lower()}_input.json")
    generated_report_path = os.path.join(reports_dir, f"{run_id.lower()}_report.json")
    generated_md_path = os.path.join(reports_dir, f"{run_id.lower()}_report.md")
    
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)
        
    try:
        # 2. Write Case payload to disk securely
        with open(temp_case_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=2)
            
        # 3. Call Core Engine
        report = run_engine(policy_path, temp_case_path, reports_dir)
        
        # 4. If successful, load the report
        if report is None:
            verdict = "NEEDS_INFO" if version == "V1.2" else "NEEDS_INPUT"
            return {
                "status": verdict,
                "violations": [{
                    "code": "POLICY_UNAVAILABLE",
                    "message": "The selected policy is not available.",
                    "evidence_anchor": "POLICY_RUNTIME_STATUS"
                }],
                "subsidy_total_eur": "0.00"
            }
            
        return report
        
    except ValueError as ve:
        print(f"[ADAPTER] Engine Validation Error: {ve}")
        return {
            "status": "INCONSISTENT",
            "violations": [{"code": "ENGINE_VALIDATION_ERROR", "message": str(ve)}],
            "subsidy_total_eur": "N/A",
            "audit_trail": [],
            "error_type": "ValueError"
        }
    except Exception as e:
        print(f"[ADAPTER] Unexpected Engine Crash: {e}")
        verdict = "NEEDS_INFO" if version == "V1.2" else "NEEDS_INPUT"
        return {
            "status": verdict,
            "violations": [{"code": "SYSTEM_ERROR", "message": f"Unexpected error during calculation: {str(e)}"}],
            "subsidy_total_eur": "N/A",
            "audit_trail": [],
            "error_type": type(e).__name__
        }
    finally:
        # 5. Clean up temporary footprint
        cleanup_files = [temp_case_path, generated_report_path, generated_md_path]
        for tf in cleanup_files:
            if os.path.exists(tf):
                try:
                    os.remove(tf)
                except Exception as ex:
                    print(f"[ADAPTER] Warning: Could not cleanup temp file {tf}: {ex}")
