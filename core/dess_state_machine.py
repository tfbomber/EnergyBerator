from datetime import datetime
from typing import Dict, List, Tuple

def parse_date(date_str: str) -> datetime:
    date_str = date_str.strip()
    if "T" in date_str:
        clean_str = date_str.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(clean_str)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(date_str[:10], fmt)
        except ValueError:
            continue
    raise ValueError(f"not a valid date: {date_str}")

def check_timing(policy: Dict, case: Dict) -> Tuple[str, List[Dict], List[Dict]]:
    findings = []
    audit_trail = []
    
    # Version Detection from shared state (Top of scope)
    version = case.get("_dess_version", "V1.1")

    app_date_str = None
    for event in case.get("timeline_events", []):
        if event["event_type"] == "APPLICATION_SUBMITTED":
            app_date_str = event["date"]
            break
            
    if not app_date_str:
        # Check if timeline dict has the field (fallback for business JSON)
        timeline = case.get("timeline", {})
        app_date_str = timeline.get("application_submitted_date")
        
    if not app_date_str:
        if version == "V1.1" and not case.get("timeline_events"):
            # Perfectly empty timeline in V1.1 (ROBUST cases) -> APPROVED
            findings.append({"severity": "INFO", "reason_code_raw": "TIMING_OK", "message": "No timeline provided. Assuming OK for Plan mode."})
            return "APPROVED", findings, []
        
        # Incomplete timeline or V1.2 -> NEEDS_INFO
        verdict = "NEEDS_INFO" if version == "V1.2" else "NEEDS_INPUT"
        findings.append({
            "severity": "NEEDS_INFO",
            "reason_code_raw": "MISSING_APPLICATION_EVENT",
            "message": "missing_fields: application_submitted_date",
            "missing_facts": ["application_submitted_date"],
            "trace": {"missing": ["application_submitted_date"]}
        })
        return verdict, findings, []

    try:
        app_date = parse_date(app_date_str)
    except ValueError as e:
        verdict = "NEEDS_INFO" if version == "V1.2" else "NEEDS_INPUT"
        findings.append({
            "severity": "NEEDS_INFO",
            "reason_code_raw": "DATE_PARSE_ERROR",
            "message": str(e),
            "parse_error": True,
            "trace": {"field": "application_submitted_date", "value": app_date_str}
        })
        return verdict, findings, []

    # Overlay Check for precedence language
    has_overlay = policy.get("_runtime_status", {}).get("status") == "PAUSED"

    limit_days = policy.get("rules", {}).get("vorhabenbeginn_limit_days", 0)

    blocking_actions = set(policy.get("timing_rules", {}).get("blocking_actions", []))
    any_legacy_violation = False

    for event in case.get("timeline_events", []):
        etype = event["event_type"]
        if etype in blocking_actions:
            try:
                event_date = parse_date(event["date"])
            except ValueError as e:
                findings.append({"severity": "NEEDS_INFO", "reason_code_raw": "DATE_PARSE_ERROR", "message": str(e), "parse_error": True})
                continue
            
            is_cond = event.get("is_conditional", False)
            if etype == "CONTRACT_SIGNED":
                if is_cond == "UNKNOWN":
                    findings.append({"severity": "NEEDS_INFO", "reason_code_raw": "MISSING_ATTRIBUTES", "message": "UNKNOWN conditionality."})
                    continue
                if is_cond is True and event_date < app_date:
                    findings.append({"severity": "INFO", "reason_code_raw": "CONDITIONAL_CLAUSE_OK", "message": "Conditional clause valid."})
                    continue
                if event_date.date() == app_date.date() and is_cond is False:
                    findings.append({"severity": "NEEDS_INFO", "reason_code_raw": "AMBIGUOUS_SAME_DAY_ORDER", "message": "Same day order."})
                    continue

            # Grace Period Logic: event_date < (app_date - limit_days)
            diff = (app_date - event_date).days
            if diff > limit_days:
                any_legacy_violation = True
                
                raw_code = "VORHABENBEGINN_VIOLATION"
                if etype == "CONTRACT_SIGNED": raw_code = "VORHABENBEGINN_BEFORE_APPLICATION"
                elif etype == "WORK_STARTED": raw_code = "WORK_STARTED_BINDING"
                elif etype in ("FIRST_PAYMENT_MADE", "PAYMENT_MADE"): raw_code = "PAYMENT_BINDING"
                
                msg = f"Vorhabenbeginn violation: {etype} on {event_date.strftime('%Y-%m-%d')} (parsed) is {diff} days before Application {app_date.strftime('%Y-%m-%d')} (parsed). Limit: {limit_days}."
                if has_overlay:
                    msg += " This rejection takes precedence over the overlay status."

                findings.append({
                    "severity": "REJECTED",
                    "reason_code_raw": raw_code,
                    "message": msg,
                    "gate": "VORHABENBEGINN",
                    "cutoff_date": policy.get("rules", {}).get("cutoff_date"),
                    "trace": {"event": etype, "date": event["date"], "app_date": app_date.strftime("%Y-%m-%d"), "note": "overlay ignored for core eligibility"}
                })

    # Conflict Engine
    work_started_fact = any(e["event_type"] == "WORK_STARTED" for e in case.get("timeline_events", []))
    cost_items = case.get("costs", {}).get("items", [])
    conflicts = []
    for i, item in enumerate(cost_items):
        edate_str = item.get("execution_date")
        if edate_str:
            try:
                edate = parse_date(edate_str)
                if not work_started_fact and edate < app_date:
                    conflicts.append({"field": "timeline.work_started", "conflict_source_path": f"costs.items[{i}].execution_date"})
            except: pass
    if conflicts:
        findings.append({"severity": "NEEDS_INFO", "reason_code_raw": "CONFLICT_DETECTED", "message": "Conflict detected between work_started and cost item execution_date.", "trace": {"conflicts": conflicts}})

    has_rejected = any(f["severity"] == "REJECTED" for f in findings)
    has_needs_info = any(f["severity"] == "NEEDS_INFO" for f in findings)
    
    status = "REJECTED" if has_rejected else ("NEEDS_INPUT" if has_needs_info else "APPROVED")
    if status == "APPROVED":
        findings.append({"severity": "INFO", "reason_code_raw": "VORHABENBEGINN_PASS", "message": "Vorhabenbeginn pass."})

    audit_trail.append({"step_id": "TIMING_CHECK", "description": f"Vorhabenbeginn: {status}", "amount_cents": 0, "evidence_anchor": "19.303 Punkt 4.1"})
    return status, findings, audit_trail
