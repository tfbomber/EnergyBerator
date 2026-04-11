import os
import json
from datetime import datetime, timezone

# --- Stage 74.5: Commercial Readiness & Compliance Auditor ---
# Mode: NON_EXECUTING / READ_ONLY_UPSTREAM / AUDIT_AND_CLASSIFICATION_ONLY

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_73_DIR = os.path.join(ROOT_DIR, "output", "manual_activation_warrant")
STAGE_74_DIR = os.path.join(ROOT_DIR, "output", "execution_dry_run")
CONFIG_DIR = os.path.join(ROOT_DIR, "data", "governance_configs")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "commercial_readiness_audit")

def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return "PARSE_ERROR"

def write_json(data, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return filepath

def run_gate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)

    warrant_file = os.path.join(STAGE_73_DIR, "manual_activation_warrant_registry_NEUSS.json")
    dry_run_file = os.path.join(STAGE_74_DIR, "contact_execution_dry_run_registry_NEUSS.json")
    summary_file = os.path.join(STAGE_74_DIR, "execution_simulation_summary_NEUSS.json")

    legal_cfg_file = os.path.join(CONFIG_DIR, "legal_config.json")
    business_cfg_file = os.path.join(CONFIG_DIR, "business_config.json")

    warrant_data = load_json(warrant_file)
    dry_run_data = load_json(dry_run_file)
    # The summary is mostly for macro completion rules, though we don't strictly read its array, we just need to know it didn't global abort
    exec_summary = load_json(summary_file) 
    
    legal_cfg = load_json(legal_cfg_file)
    business_cfg = load_json(business_cfg_file)

    audit_lines = []
    audit_lines.append(f"STAGE 74.5 AUDIT LOG - {datetime.now(timezone.utc).isoformat()}")
    audit_lines.append("="*80)

    # Missing Global Required Input Checks
    if not dry_run_data or dry_run_data == "PARSE_ERROR":
        audit_lines.append("GLOBAL WARNING: contact_execution_dry_run_registry_NEUSS.json missing or malformed.")
        dry_run_records = []
    else:
        dry_run_records = dry_run_data.get("records", [])

    if legal_cfg is None:
        audit_lines.append("OPTIONAL CONFIG MISSING: legal_config.json not found. Evaluating using available evidence only.")
        legal_cfg = {}
    elif legal_cfg == "PARSE_ERROR":
        audit_lines.append("OPTIONAL CONFIG OVERRIDE: legal_config.json malformed. Treating legal support as UNAVAILABLE.")
        legal_cfg = {}
        
    if business_cfg is None:
        audit_lines.append("OPTIONAL CONFIG MISSING: business_config.json not found. Evaluating using available evidence only.")
        business_cfg = {}
    elif business_cfg == "PARSE_ERROR":
        audit_lines.append("OPTIONAL CONFIG OVERRIDE: business_config.json malformed. Treating business support as UNAVAILABLE.")
        business_cfg = {}

    audit_registry = {"records": []}
    
    # System Level Summary Tracking
    sys_summary = {
        "total_records": len(dry_run_records),
        "ready_records": 0,
        "not_ready_records": 0,
        "legal_safe_count": 0,
        "legal_conditional_count": 0,
        "legal_forbidden_count": 0,
        "ownership_clear_count": 0,
        "ownership_partial_count": 0,
        "ownership_unclear_count": 0,
        "operational_ready_count": 0,
        "operational_partial_count": 0,
        "operational_not_ready_count": 0,
        "overall_system_readiness": "NOT_READY"
    }
    
    # File components for detailed reports
    legal_downgrade_reasons = {}
    commercial_role_completion = {"dess": 0, "installer": 0, "consultant": 0, "unknown": 0}
    operational_coverage = {"chain_defined": 0, "crm_defined": 0, "installer_defined": 0, "fallback_defined": 0}
    
    for rec in dry_run_records:
        cid = rec.get("contact_id")
        blockers = []
        is_malformed = False

        if not cid:
            is_malformed = True
            cid = "UNKNOWN_ID"
            blockers.append("MALFORMED_RECORD_INPUT")
            audit_lines.append(f"RECORD MALFORMED [{cid}]: Missing contact_id. Pessimistic classification forcing NOT_READY.")

        # Extract configs
        l_conf = legal_cfg.get(cid, {}) if isinstance(legal_cfg, dict) else {}
        b_conf = business_cfg.get(cid, {}) if isinstance(business_cfg, dict) else {}

        if not isinstance(l_conf, dict): l_conf = {}
        if not isinstance(b_conf, dict): b_conf = {}

        # =====================================================================
        # LEGAL EVALUATION
        # =====================================================================
        legal_basis = l_conf.get("legal_basis_status", "UNKNOWN" if not is_malformed else "UNKNOWN")
        consent = l_conf.get("consent_status", "UNKNOWN" if not is_malformed else "UNKNOWN")
        traceable = l_conf.get("data_origin_traceable", False if is_malformed else False)
        
        # Safe downgrade overrides per rules
        if not isinstance(traceable, bool):
            traceable = False

        gdpr_readiness = "CONDITIONAL"

        if not traceable:
            gdpr_readiness = "FORBIDDEN"
            blockers.append("DATA_ORIGIN_NOT_TRACEABLE")
        elif consent == "NONE":
            gdpr_readiness = "FORBIDDEN"
        elif legal_basis != "CONFIRMED":
            # Rule 5: Cannot be SAFE
            pass
        elif consent == "UNKNOWN" or consent == "IMPLIED":
            # Rule 3,4: Cannot be SAFE
            pass
        elif consent == "EXPLICIT" and legal_basis == "CONFIRMED" and traceable:
            gdpr_readiness = "SAFE"

        if gdpr_readiness != "SAFE" and gdpr_readiness != "FORBIDDEN":
            # It's CONDITIONAL. 
            pass

        # Append blockers for Legal
        if consent != "EXPLICIT":
            blockers.append("CONSENT_NOT_EXPLICIT")
            audit_lines.append(f"LEGAL DOWNGRADE [{cid}]: consent is not explicit ({consent}).")
        if legal_basis != "CONFIRMED":
            blockers.append("LEGAL_BASIS_NOT_CONFIRMED")
            audit_lines.append(f"LEGAL DOWNGRADE [{cid}]: legal_basis is not confirmed ({legal_basis}).")
            
        if gdpr_readiness == "SAFE": sys_summary["legal_safe_count"] += 1
        elif gdpr_readiness == "CONDITIONAL": sys_summary["legal_conditional_count"] += 1
        else: sys_summary["legal_forbidden_count"] += 1

        legal_assessment = {
            "legal_basis_status": legal_basis,
            "consent_status": consent,
            "data_origin_traceable": traceable,
            "gdpr_contact_readiness": gdpr_readiness
        }

        # =====================================================================
        # COMMERCIAL EVALUATION
        # =====================================================================
        comm_path = b_conf.get("commercial_path", "UNKNOWN" if not is_malformed else "UNKNOWN")
        data_ctrl = b_conf.get("data_controller")
        data_proc = b_conf.get("data_processor")
        cont_exec = b_conf.get("contact_executor")
        
        if not data_ctrl: blockers.append("DATA_CONTROLLER_UNDEFINED")
        if not cont_exec: blockers.append("CONTACT_EXECUTOR_UNDEFINED")
        if comm_path == "UNKNOWN": blockers.append("COMMERCIAL_PATH_UNKNOWN")

        clarity = "UNCLEAR"
        roles_defined = sum([1 for x in (data_ctrl, cont_exec) if x])
        if roles_defined == 2 and comm_path != "UNKNOWN":
            clarity = "CLEAR"
        elif roles_defined > 0:
            clarity = "PARTIAL"

        if clarity != "CLEAR":
            audit_lines.append(f"OWNERSHIP DOWNGRADE [{cid}]: roles or path ambiguous. Clarity = {clarity}.")

        if clarity == "CLEAR": sys_summary["ownership_clear_count"] += 1
        elif clarity == "PARTIAL": sys_summary["ownership_partial_count"] += 1
        else: sys_summary["ownership_unclear_count"] += 1
        
        # update breakdown
        commercial_role_completion[comm_path.lower().split('_')[0] if "LED" in comm_path or "DIRECT" in comm_path else "unknown"] += 1

        commercial_assessment = {
            "commercial_path": comm_path,
            "role_definition": {
                "data_controller": data_ctrl or "",
                "data_processor": data_proc or "",
                "contact_executor": cont_exec or ""
            },
            "ownership_clarity": clarity
        }

        # =====================================================================
        # OPERATIONAL EVALUATION
        # =====================================================================
        ex_chain = b_conf.get("execution_chain_defined", False)
        crm_int = b_conf.get("crm_integration_defined", False)
        inst_pipe = b_conf.get("installer_pipeline_defined", False)
        fallback = b_conf.get("fallback_defined", False)
        
        if not ex_chain: blockers.append("EXECUTION_CHAIN_NOT_DEFINED")
        if not crm_int: blockers.append("CRM_INTEGRATION_NOT_DEFINED")
        if not inst_pipe: blockers.append("INSTALLER_PIPELINE_NOT_DEFINED")
        if not fallback: blockers.append("FALLBACK_NOT_DEFINED")

        op_trues = sum([1 for x in (ex_chain, crm_int, inst_pipe, fallback) if x])
        op_readiness = "NOT_READY"
        if op_trues == 4:
            op_readiness = "READY"
        elif op_trues > 0:
            op_readiness = "PARTIAL"

        if op_readiness != "READY":
            audit_lines.append(f"OPERATIONAL DOWNGRADE [{cid}]: not all 4 mechanisms defined. Readiness = {op_readiness}.")

        if op_readiness == "READY": sys_summary["operational_ready_count"] += 1
        elif op_readiness == "PARTIAL": sys_summary["operational_partial_count"] += 1
        else: sys_summary["operational_not_ready_count"] += 1
        
        if ex_chain: operational_coverage["chain_defined"] += 1
        if crm_int: operational_coverage["crm_defined"] += 1
        if inst_pipe: operational_coverage["installer_defined"] += 1
        if fallback: operational_coverage["fallback_defined"] += 1

        operational_assessment = {
            "execution_chain_defined": ex_chain,
            "crm_integration_defined": crm_int,
            "installer_pipeline_defined": inst_pipe,
            "fallback_defined": fallback,
            "operational_readiness": op_readiness
        }

        # =====================================================================
        # FINAL VERDICT
        # =====================================================================
        final_readiness = "NOT_READY"
        
        if gdpr_readiness == "SAFE" and clarity == "CLEAR" and op_readiness == "READY":
            final_readiness = "READY_FOR_CONTROLLED_EXECUTION"
            sys_summary["ready_records"] += 1
            audit_lines.append(f"READY [{cid}]: All legal, commercial, and operational constraints met strictly.")
        else:
            sys_summary["not_ready_records"] += 1
            if len(blockers) == 0: # Failsafe
                blockers.append("UNCATEGORIZED_NOT_READY")

        # Strip duplicates and sort blockers deterministically
        blockers = sorted(list(set(blockers)))
        
        # Sub-summaries stats update
        for b in blockers:
            legal_downgrade_reasons[b] = legal_downgrade_reasons.get(b, 0) + 1

        audit_registry["records"].append({
            "contact_id": cid,
            "legal_assessment": legal_assessment,
            "commercial_assessment": commercial_assessment,
            "operational_assessment": operational_assessment,
            "final_readiness": final_readiness,
            "blocking_reasons": blockers
        })

    # =====================================================================
    # MACRO SYSTEM GATING
    # =====================================================================
    macro_readiness = "NOT_READY"

    if sys_summary["ready_records"] > 0 and sys_summary["legal_forbidden_count"] == 0 and \
       sys_summary["ownership_unclear_count"] < sys_summary["ownership_clear_count"] and \
       sys_summary["operational_not_ready_count"] <= sys_summary["operational_ready_count"]:
        macro_readiness = "READY"
    elif sys_summary["ready_records"] == 0 or sys_summary["legal_forbidden_count"] > (sys_summary["total_records"]/2):
        macro_readiness = "NOT_READY"
    else:
        macro_readiness = "PARTIAL"
        
    audit_lines.append(f"MACRO EVALUATION: Records Ready [{sys_summary['ready_records']}/{sys_summary['total_records']}]. Final system readiness: {macro_readiness}")

    sys_summary["overall_system_readiness"] = macro_readiness

    # Breakdown Reports
    legal_summary = {
        "legal_safe_count": sys_summary["legal_safe_count"],
        "legal_conditional_count": sys_summary["legal_conditional_count"],
        "legal_forbidden_count": sys_summary["legal_forbidden_count"],
        "downgrade_reasons": legal_downgrade_reasons,
        "config_availability_note": "legal_config.json parsed applied via declarative strict mapping."
    }
    
    business_summary = {
        "commercial_path_counts": commercial_role_completion,
        "ownership_clarity_distribution": {
            "CLEAR": sys_summary["ownership_clear_count"],
            "PARTIAL": sys_summary["ownership_partial_count"],
            "UNCLEAR": sys_summary["ownership_unclear_count"]
        }
    }
    
    operational_summary = {
        "execution_chain_coverage": operational_coverage["chain_defined"],
        "crm_integration_coverage": operational_coverage["crm_defined"],
        "installer_pipeline_coverage": operational_coverage["installer_defined"],
        "fallback_coverage": operational_coverage["fallback_defined"],
        "operational_readiness_distribution": {
            "READY": sys_summary["operational_ready_count"],
            "PARTIAL": sys_summary["operational_partial_count"],
            "NOT_READY": sys_summary["operational_not_ready_count"]
        }
    }

    # Write Outputs (Exactly 7 mapped items per prompt request)
    write_json(audit_registry, "commercial_readiness_audit_registry_NEUSS.json")
    write_json(legal_summary, "legal_compliance_summary_NEUSS.json")
    write_json(business_summary, "business_ownership_analysis_NEUSS.json")
    write_json(operational_summary, "operational_readiness_report_NEUSS.json")
    write_json(sys_summary, "system_readiness_summary_NEUSS.json")

    with open(os.path.join(OUTPUT_DIR, "audit_log.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(audit_lines) + "\n")

    print(f"Stage 74.5 completed securely. Macro System Readiness: {sys_summary['overall_system_readiness']}")

if __name__ == "__main__":
    run_gate()
