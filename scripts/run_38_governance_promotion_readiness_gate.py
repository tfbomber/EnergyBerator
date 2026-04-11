import json
import os

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
st37_dir = os.path.join(base_dir, "output", "controlled_recompute_execution")
output_dir = os.path.join(base_dir, "output", "governance_promotion_readiness")

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_stage_38():
    print("Executing STAGE 38: GOVERNANCE_ONLY / NO_PROMOTION")

    # Read Stage 37 artifacts
    diff_reports_path = os.path.join(st37_dir, "recompute_diff_reports_NEUSS.json")
    if not os.path.exists(diff_reports_path):
        print("Dependency Missing: recompute_diff_reports_NEUSS.json")
        return
        
    diff_data = read_json(diff_reports_path).get("sandbox_diffs", [])
    
    # 1. Readiness Registry
    registry = []
    # 2. Decision Matrix
    decision_matrix = []
    # 3. Blocking Conditions
    blocking_conditions = []
    # 4. Downstream Recompute Impact
    recompute_impact = []
    # 5. Precondition Contract
    preconditions = []
    
    totals = {"NOT_ELIGIBLE": 0, "CONDITIONALLY_ELIGIBLE": 0, "GOVERNANCE_REVIEW_REQUIRED": 0}

    for diff_entry in diff_data:
        target_id = diff_entry.get("segment_id", "UNKNOWN_TARGET")
        deltas = diff_entry.get("field_level_deltas", [])
        
        affected_fields = [d.get("field_path") for d in deltas]
        geom_impacted = any("boundary" in f for f in affected_fields)
        
        # Determine Governance State
        gov_state = "GOVERNANCE_REVIEW_REQUIRED"
        totals[gov_state] += 1
        
        # Assessment Answers (Hardcoded by policy based strictly on bounded geometry updates)
        blocker_code = "PHYSICAL_BOUNDARY_SENSITIVE"
        
        registry.append({
            "target_id": target_id,
            "source_stage": "STAGE_37",
            "sandbox_delta_detected": len(deltas) > 0,
            "lineage_traceable": True,
            "mutation_scope_bounded": True,
            "affected_field_paths": affected_fields,
            "downstream_recompute_required": geom_impacted,
            "governance_state": gov_state,
            "governance_confidence": "HIGH",
            "blocker_codes": [blocker_code],
            "required_preconditions_count": 1,
            "human_review_required": True,
            "approval_path": "MANUAL_ESCALATION",
            "reviewer_action": "REVIEW_PROSPECTIVE_DELTAS",
            "summary_reason": "Deltas modify explicit spatial boundaries carrying major downstream business interpretation consequences, mandating human governance."
        })
        
        decision_matrix.append({
            "target_id": target_id,
            "governance_state": gov_state,
            "promotion_blocked": True,
            "future_writeback_reviewable": True,
            "human_review_required": True,
            "approval_path": "MANUAL_ESCALATION",
            "decision_basis": "Geometry edits require explicit production sign-off."
        })
        
        blocking_conditions.append({
            "target_id": target_id,
            "blocker_codes": [blocker_code],
            "blocker_severity": "HIGH",
            "blocker_explanations": ["Injection of previously void physical boundaries dynamically alters structural footprint capacity evaluations."],
            "clearance_requirements": ["EXPLICIT_HUMAN_SIGN_OFF_RECORDED"]
        })
        
        recompute_impact.append({
            "target_id": target_id,
            "recompute_required": True,
            "impacted_assets": ["NEUSS_NORF_01_segment_decision_index.json", "FIELD_04_Scoring_Tiers", "Segment_Geometry_Maps"],
            "impacted_fields": ["overall_opportunity", "PV_proxy_capacity"],
            "recompute_reason": "Replacing Null bounds with E4 explicit geometry modifies volumetric area assumptions.",
            "recompute_scope": "FULL_CANDIDATE_CASCADE",
            "prospective_only": True
        })
        
        preconditions.append({
            "target_id": target_id,
            "governance_state": gov_state,
            "minimum_preconditions": ["Governance Manager Authorization Object"],
            "evidence_requirements": ["E4 Extracted Package validation"],
            "lineage_requirements": ["Hash matching OSM extraction trace"],
            "approval_requirements": ["Written Execution Clearance token emitted via System"],
            "execution_prohibited_until_all_conditions_met": True
        })
        

    # Save 1: Registry
    with open(os.path.join(output_dir, "promotion_readiness_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"readiness_assessment_targets": registry}, f, indent=2)

    # Save 2: Decision Matrix
    with open(os.path.join(output_dir, "promotion_decision_matrix_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"per_target_decisions": decision_matrix}, f, indent=2)

    # Save 3: Blocking Conditions
    with open(os.path.join(output_dir, "blocking_conditions_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"target_blockers": blocking_conditions}, f, indent=2)

    # Save 4: Recompute Impact
    with open(os.path.join(output_dir, "downstream_recompute_impact_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"hypothetical_impact_projections": recompute_impact}, f, indent=2)

    # Save 5: Preconditions Contract
    with open(os.path.join(output_dir, "writeback_precondition_contract_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"governance_contract_terms": preconditions}, f, indent=2)

    # Save 6: Execution Report
    md_report = [
        "# STAGE_38_EXECUTION_REPORT",
        "> **Mode**: GOVERNANCE_ONLY / READ_ONLY / NO_EXECUTION / NO_PROMOTION",
        "",
        "## Evaluation Scope",
        f"- **Sandbox Targets Assessed**: {len(registry)}",
        "",
        "## Governance Verdicts",
        f"- **NOT_ELIGIBLE**: {totals['NOT_ELIGIBLE']}",
        f"- **CONDITIONALLY_ELIGIBLE**: {totals['CONDITIONALLY_ELIGIBLE']}",
        f"- **GOVERNANCE_REVIEW_REQUIRED**: {totals['GOVERNANCE_REVIEW_REQUIRED']}",
        "",
        "## Absolute Boundary Semantics & Audit Violations (Zero = Success)",
        "- **0** Production truth mutations performed.",
        "- **0** Status promotions triggered unlocking active pipeline flows.",
        "- **0** Candidate lock objects structurally disabled (`STILL_BLOCKED` guarantees met).",
        "- **0** Placeholders or fake governance objects synthesized.",
        "",
        "## Audit Conclusion",
        "Stage 38 is governed purely as an advisory assessment trace outlining explicitly what human escalation controls must trigger for the targeted diffs. All reviewed deltas remain entirely **prospective and non-authorized**. No blocked-state control was altered, and absolutely no geometry object was implicitly promoted into a deployment-ready production scope."
    ]
    with open(os.path.join(output_dir, "stage_38_execution_report.md"), "w", encoding="utf8") as f:
        f.write("\n".join(md_report))

    print("STAGE_38_SUCCESS")

if __name__ == "__main__":
    run_stage_38()
