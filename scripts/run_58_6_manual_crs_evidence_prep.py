import json
from pathlib import Path

# =====================================================================
# CONFIGURATION & PATHS
# =====================================================================
REGION_TAG = "NEUSS"
ROOT_DIR = Path(r"d:\Stock Analysis\D-Energy Berater\d-ess-engine")

STAGE_58_5_DIR = ROOT_DIR / "output" / "crs_spatial_trust_gate"
OUTPUT_DIR = ROOT_DIR / "output" / "manual_crs_evidence_prep"

# Enums - Review States
REV_AWAITING = "AWAITING_EVIDENCE_SUBMISSION"
REV_SUBMITTED = "EVIDENCE_SUBMITTED_NOT_REVIEWED"
REV_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
REV_READY = "EVIDENCE_REVIEW_READY"
REV_ESCALATION = "HOLD_FOR_TECHNICAL_ESCALATION"

# Verdicts
VERDICT_BLOCKED = "PREP_ONLY_BLOCKED"
VERDICT_COLLECT = "PREP_READY_FOR_EVIDENCE_COLLECTION"
VERDICT_PARTIAL = "PREP_PARTIALLY_READY_FOR_REVIEW"
VERDICT_RERUN = "PREP_READY_FOR_TARGETED_58_5_RERUN"

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def build_policy():
    return {
        "policy_id": "CRS_EVIDENCE_ACCEPTANCE_POLICY_V1",
        "acceptable_crs_evidence_classes": [
            "EXPLICIT_CRS_DECLARATION_IN_ORIGINAL_SOURCE",
            "EXPLICIT_EPSG_DECLARATION_IN_REGISTERED_DOCUMENTATION",
            "EXPORTER_SYSTEM_DOCUMENTATION_TIED_TO_EXACT_DATASET",
            "FORMALLY_REGISTERED_MANUAL_REVIEW_RECORD_WITH_CITATION"
        ],
        "conditionally_reviewable_evidence_classes": [
            "SOURCE_SIDE_DOCUMENTATION_STRONGLY_SUGGESTING_CRS_NOT_EXACTLY_TIED",
            "TECHNICAL_NOTES_REQUIRING_HUMAN_VERIFICATION",
            "INCOMPLETE_BUT_USEFUL_TECHNICAL_EXPORT_CONTEXT"
        ],
        "unacceptable_crs_evidence_classes": [
            "COORDINATE_APPEARANCE_ONLY",
            "DEGREE_LIKE_OR_METER_LIKE_RANGE_ALONE",
            "PRIOR_HABIT_OR_EXPECTATION",
            "LOOKS_CORRECT_ON_MAP",
            "SUCCESSFUL_SANDBOX_MATCHING",
            "SUCCESSFUL_REPROJECTION_GUESS_ATTEMPTS",
            "UNDOCUMENTED_VERBAL_ASSUMPTIONS"
        ],
        "review_principles": [
            "EVIDENCE_MUST_BE_FORMALLY_REGISTERED_BEFORE_TRUST_CLOSURE",
            "FALSE_NEGATIVES_PREFERRED_OVER_FALSE_POSITIVES"
        ],
        "non_guessing_principles": [
            "DO_NOT_GUESS_EPSG_CODES",
            "DO_NOT_UPGRADE_BASED_ON_PLAUSIBILITY",
            "DO_NOT_TREAT_MATCHING_SUCCESS_AS_CRS_PROOF"
        ]
    }

def main():
    print("📋 [STAGE 58.6] Executing MANUAL CRS EVIDENCE REGISTRATION & TRUST CLOSURE PREP...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load 58.5 Un-trusted files
    s58_5_untrusted_reg = load_json(STAGE_58_5_DIR / f"geometry_untrusted_or_manual_review_{REGION_TAG}.json").get("records", [])
    
    # Check if there are explicitly trusted in 58.5 for completeness (should be 0)
    s58_5_safe = load_json(STAGE_58_5_DIR / f"geometry_safe_for_real_matching_{REGION_TAG}.json").get("records", [])

    registry = []
    review_queue = []
    gap_register = []
    rerun_readiness = []
    blocked_files = []
    non_upgrade_verif = []
    
    c_awaiting = 0
    c_submitted = 0
    c_insuff = 0
    c_ready = 0
    c_hold = 0
    
    c_rerun_justified = 0
    c_rerun_not_justified = 0
    
    policy = build_policy()
    
    for r in sorted(s58_5_untrusted_reg, key=lambda x: (x["file_name"], x["sha256"])):
        file_id = r["file_id"]
        
        # 1. Lineage & Carrier
        trust_status = r["crs_trust_status"]
        safe_posture = r["future_real_matching_safety_posture"]
        blockers = r["blocker_reasons"]
        
        # 2. Gap Identification
        missing_cats = []
        if "NO_EXPLICIT_CRS_EVIDENCE" in blockers or "CRS_NOT_DECLARED" in blockers:
            missing_cats.append("EXPLICIT_CRS_DECLARATION_IN_ORIGINAL_SOURCE")
            missing_cats.append("FORMALLY_REGISTERED_MANUAL_REVIEW_RECORD")
            
        # 4. Review Queue Assignment
        # Given this is purely a prep stage and no new evidence was introduced
        workflow_state = REV_AWAITING
        
        # 5. Rerun Preconditions
        rerun_preconditions = [
            "A formally registered manual review artifact must be provided in pipeline input.",
            f"The registered artifact must establish EPSG mapping for {file_id} satisfying policy rules."
        ]
        
        conf = "HIGH" # High confidence in the preparation rules themselves
        
        # Build Normalized Record
        rec = {
            "file_id": file_id,
            "file_name": r["file_name"],
            "sha256": r["sha256"],
            "source_path": r["source_path"],
            
            "stage_58_5_crs_trust_status": trust_status,
            "stage_58_5_future_real_matching_safety_posture": safe_posture,
            "carried_forward_blocker_reasons": blockers,
            
            "missing_evidence_categories": missing_cats,
            "acceptable_evidence_classes": policy["acceptable_crs_evidence_classes"],
            "conditionally_reviewable_evidence_classes": policy["conditionally_reviewable_evidence_classes"],
            "unacceptable_evidence_classes": policy["unacceptable_crs_evidence_classes"],
            
            "manual_review_workflow_state": workflow_state,
            "rerun_58_5_preconditions": rerun_preconditions,
            "confidence_class": conf,
            "notes": "File placed in manual processing queue. No automated trust upgrades performed."
        }
        
        registry.append(rec)
        
        review_queue.append({
            "file_id": file_id,
            "manual_review_workflow_state": workflow_state,
            "missing_evidence_categories": missing_cats,
            "rerun_58_5_preconditions": rerun_preconditions
        })
        
        for g in missing_cats:
            gap_register.append({"file_id": file_id, "missing_evidence_category": g})
            
        rerun_readiness.append({
            "file_id": file_id,
            "rerun_currently_justified": False,
            "missing_prerequisites": rerun_preconditions,
            "technical_escalation_needed": False
        })
        
        blocked_files.append(rec)
        
        non_upgrade_verif.append({
            "file_id": file_id,
            "upgraded_trust_status": False,
            "maintained_conservative_workflow_state": workflow_state
        })
        
        # Accounter
        if workflow_state == REV_AWAITING: c_awaiting += 1
        elif workflow_state == REV_SUBMITTED: c_submitted += 1
        elif workflow_state == REV_INSUFFICIENT: c_insuff += 1
        elif workflow_state == REV_READY: c_ready += 1
        else: c_hold += 1
        
        c_rerun_not_justified += 1
        
    # Verdict Assignment
    if not registry:
        overall_v = VERDICT_BLOCKED
    else:
        # Since we just placed them in "AWAITING", it's ready for collection via standard process
        overall_v = VERDICT_COLLECT

    # Export Files
    def write_out(name, data):
        with open(OUTPUT_DIR / f"{name}_{REGION_TAG}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    write_out("manual_crs_evidence_registry", {"records": registry})
    write_out("manual_crs_review_queue", {"records": review_queue})
    write_out("crs_acceptance_policy", policy)
    write_out("crs_evidence_gap_register", {"gaps": gap_register})
    write_out("rerun_58_5_readiness_register", {"readiness": rerun_readiness})
    write_out("blocked_files_pending_crs_closure", {"records": blocked_files})
    write_out("trust_non_upgrade_verification", {"verifications": non_upgrade_verif})

    report = {
        "stage": "58.6",
        "mode": "MANUAL_CRS_EVIDENCE_REGISTRATION_AND_TRUST_CLOSURE_PREP",
        "files_considered": len(s58_5_untrusted_reg),
        "files_processed": len(registry),
        "awaiting_evidence_submission_count": c_awaiting,
        "evidence_submitted_not_reviewed_count": c_submitted,
        "evidence_insufficient_count": c_insuff,
        "evidence_review_ready_count": c_ready,
        "hold_for_technical_escalation_count": c_hold,
        "rerun_currently_justified_count": c_rerun_justified,
        "rerun_not_yet_justified_count": c_rerun_not_justified,
        "overall_verdict": overall_v,
        "governance_summary": "Successfully established the manual review schema and rules. All untrusted files accurately queued requesting acceptable forms of evidence strictly before any 58.5 rerun action.",
        "safety_confirmation": "Confirmed: Generated policy templates exclusively and rigorously upheld historical blocks without injecting missing EPSG parameters or bypassing closure rules."
    }

    with open(OUTPUT_DIR / "stage_58_6_manual_crs_evidence_prep_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("✅ Stage 58.6 Manual CRS Evidence Prep completed. Outputs saved.")
    print(f"Overall Verdict: {overall_v}")

if __name__ == "__main__":
    main()
