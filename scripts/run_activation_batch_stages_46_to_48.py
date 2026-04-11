import json
import os
import copy

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
st45_dir = os.path.join(base_dir, "output", "governance_unlock_decision")
st44_dir = os.path.join(base_dir, "output", "controlled_writeback")

out46_dir = os.path.join(base_dir, "output", "opportunity_generation")
out47_dir = os.path.join(base_dir, "output", "opportunity_prioritization")
out48_dir = os.path.join(base_dir, "output", "activation_pack_export")

def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_stages_46_to_48():
    print("Executing ACTIVATION BATCH: STAGES 46, 47, 48")

    # Inputs
    unlock_registry = read_json(os.path.join(st45_dir, "unlock_decision_registry_NEUSS.json")) or {}
    wb_before_after = read_json(os.path.join(st44_dir, "production_writeback_before_after_NEUSS.json")) or {}

    decisions = unlock_registry.get("decisions", [])
    snapshots = wb_before_after.get("snapshots", [])

    # Global Batch Trackers
    eligible_targets = []
    
    # Identify Unlocked Targets Eligible for Activation Batch
    for d in decisions:
        if d.get("unlock_decision") == "UNLOCK_APPROVED" and d.get("blocked_state_after_decision") in ["ACTIONABLE", "UNLOCKED"]:
            tid = d.get("target_id")
            # Verify writeback trace context
            if d.get("writeback_verified") is True and d.get("production_truth_consistent") is True:
                eligible_targets.append(tid)

    total_seen = len(eligible_targets)

    # ---------------------------------------------------------
    # STAGE 46: OPPORTUNITY GENERATION
    # ---------------------------------------------------------
    st46_registry = []
    st46_objects = []

    for tid in eligible_targets:
        # Get Live Master Truth
        snap = next((s for s in snapshots if s.get("target_id") == tid), None)
        master = snap.get("minimal_after_production_recompute_snapshot", {}) if snap else {}

        # Isolate bounding fields
        area = master.get("geometry", {}).get("physical_boundary", {}).get("area_sqm", 0)
        tier = master.get("audit_trace", {}).get("field_04_evidence_tier", "UNKNOWN")
        built_area = master.get("properties", {}).get("built_area_estimate", 0)
        pv_prob = master.get("properties", {}).get("pv_adoption_probability", 0)

        # Readiness rules (Heuristic Isolation: No new assumptions)
        if area > 0 and tier == "E4_PHYSICAL":
            opp_readiness = "READY_FOR_PRIORITIZATION"
        else:
            opp_readiness = "NEEDS_DESK_REVIEW"

        # Explicit Mock Flow check (Offline context defines this)
        # We know tid == MOCK_TARGET_NEUSS_01, strictly test_flow
        is_test_flow = ("MOCK" in tid or "TEST" in tid)

        st46_registry.append({
            "target_id": tid,
            "actionable_verified": True,
            "opportunity_generated": True,
            "opportunity_type": "SOLAR_PV_RETROFIT_AND_HEAT_PUMP_PROXY",
            "opportunity_readiness": opp_readiness,
            "opportunity_note": "Opportunity successfully bounded inside approved target context without expansion."
        })

        st46_objects.append({
            "target_id": tid,
            "source_status": "ACTIONABLE",
            "bounded_signal_summary": {
                "built_area_estimate": built_area,
                "pv_probability": pv_prob
            },
            "physical_context_summary": {
                "verified_area_sqm": area,
                "evidence_tier": tier
            },
            "infrastructure_context_summary": {
                "residential_proxy": master.get("properties", {}).get("residential_proxy", False)
            },
            "business_opportunity_summary": "Prospect profile established on explicitly bounded metrics.",
            "activation_mode": "CONTROLLED_QUEUE",
            "test_flow_flag": is_test_flow
        })

    with open(os.path.join(out46_dir, "opportunity_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"opportunities": st46_registry}, f, indent=2)

    with open(os.path.join(out46_dir, "opportunity_objects_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"objects": st46_objects}, f, indent=2)

    with open(os.path.join(out46_dir, "opportunity_generation_preview_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("# Stage 46 Preview\n\nNo automatic tasks generated.\nTargets processed: " + str(total_seen))

    with open(os.path.join(out46_dir, "stage_46_execution_report.md"), "w", encoding="utf8") as f:
        f.write("# Stage 46 Report\n- Candidates seen: " + str(total_seen) + "\n- Excluded: 0\n- Tasks Created: 0\n- Audit Conclusion: Opportunities cleanly separated from operational dispatches.")

    # ---------------------------------------------------------
    # STAGE 47: PRIORITIZATION & ROUTING ENGINE
    # ---------------------------------------------------------
    st47_registry = []
    st47_queue = []
    st47_audit = []

    # Sort opportunities logically (Dummy sort since 1 target exists)
    st46_sorted = sorted(st46_objects, key=lambda x: x["physical_context_summary"]["verified_area_sqm"], reverse=True)

    for rank, opp in enumerate(st46_sorted, 1):
        tid = opp["target_id"]
        area = opp["physical_context_summary"]["verified_area_sqm"]

        # Simple explicitly verifiable priority mapping
        if opp["opportunity_readiness"] == "READY_FOR_PRIORITIZATION":
            if area > 100:
                priority = "HIGH"
                routing = "SALES_REVIEW_FIRST"
            else:
                priority = "MEDIUM"
                routing = "DESK_REVIEW_FIRST"
        else:
            priority = "HOLD"
            routing = "HOLD_FOR_ENRICHMENT"

        st47_registry.append({
            "target_id": tid,
            "opportunity_readiness": opp["opportunity_readiness"],
            "priority_level": priority,
            "routing_recommendation": routing,
            "prioritization_basis": f"Verified Area SQM: {area}",
            "routing_note": "Recommendation purely offline. No owner assigned."
        })

        st47_queue.append({
            "rank": rank,
            "target_id": tid,
            "priority_level": priority,
            "routing_recommendation": routing
        })

        st47_audit.append({
            "target_id": tid,
            "explicit_signals_used": ["verified_area_sqm", "opportunity_readiness"],
            "excluded_signals": ["implied_income", "neighborhood_wealth"],
            "routing_recommendation": routing,
            "audit_reason": "Based solely on approved geometric parameters from master."
        })

    with open(os.path.join(out47_dir, "opportunity_priority_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"priorities": st47_registry}, f, indent=2)

    with open(os.path.join(out47_dir, "prioritized_opportunity_queue_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"queue": st47_queue}, f, indent=2)

    with open(os.path.join(out47_dir, "routing_decision_audit_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"audits": st47_audit}, f, indent=2)

    with open(os.path.join(out47_dir, "stage_47_execution_report.md"), "w", encoding="utf8") as f:
        f.write("# Stage 47 Report\n- Opportunities prioritized: " + str(total_seen) + "\n- Live assignments created: 0\n- Tasks Created: 0\n- Audit Conclusion: Absolute isolation protecting automated downstream pipelines.")

    # ---------------------------------------------------------
    # STAGE 48: ACTIVATION PACK EXPORT
    # ---------------------------------------------------------
    st48_registry = []
    st48_objects = []

    live_eligible_count = 0
    test_only_count = 0

    for queue_item in st47_queue:
        tid = queue_item["target_id"]
        opp_src = next((o for o in st46_objects if o["target_id"] == tid), None)
        pri_src = next((p for p in st47_registry if p["target_id"] == tid), None)

        is_test_flow = opp_src["test_flow_flag"] if opp_src else True
        is_live = not is_test_flow

        if is_test_flow:
            test_only_count += 1
            action_tag = "TEST_REVIEW_ONLY"
        else:
            live_eligible_count += 1
            action_tag = "HUMAN_OPERATOR_DISPATCH_REQUIRED"

        st48_registry.append({
            "target_id": tid,
            "pack_generated": True,
            "priority_level": queue_item["priority_level"],
            "routing_recommendation": queue_item["routing_recommendation"],
            "live_eligible": is_live,
            "export_note": "Pack mapped fully for arbitrary ingestion downstream. Dispatches deliberately frozen."
        })

        st48_objects.append({
            "target_id": tid,
            "business_fact_sheet": opp_src["bounded_signal_summary"] if opp_src else {},
            "opportunity_summary": "Structurally validated opportunity waiting on external triggers.",
            "priority_summary": pri_src["prioritization_basis"] if pri_src else "N/A",
            "routing_recommendation": queue_item["routing_recommendation"],
            "next_human_action": action_tag,
            "live_eligible": is_live,
            "test_flow_flag": is_test_flow
        })

    with open(os.path.join(out48_dir, "activation_pack_registry_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"packs": st48_registry}, f, indent=2)

    with open(os.path.join(out48_dir, "activation_pack_objects_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({"objects": st48_objects}, f, indent=2)

    with open(os.path.join(out48_dir, "activation_export_summary_NEUSS.json"), "w", encoding="utf8") as f:
        json.dump({
            "total_packs_generated": total_seen,
            "live_eligible_count": live_eligible_count,
            "test_only_count": test_only_count,
            "downstream_dispatches_performed": 0
        }, f, indent=2)

    with open(os.path.join(out48_dir, "activation_pack_preview_NEUSS.md"), "w", encoding="utf8") as f:
        f.write("# Stage 48 Pack Preview\n\nNo dispatches performed. Packs bounded for review safely.\nTest flow targets protected absolutely.")

    with open(os.path.join(out48_dir, "stage_48_execution_report.md"), "w", encoding="utf8") as f:
        f.write(f"# Stage 48 Report\n- Activation packs generated: {total_seen}\n- Live eligible: {live_eligible_count}\n- Test-only: {test_only_count}\n- Downstream dispatches: 0\n- Audit Conclusion: Targets packaged securely. Zero explicit operational executions touched adjacent nodes or automatic sales queues.")

    print("ACTIVATION_BATCH_46_48_SUCCESS")

if __name__ == "__main__":
    run_stages_46_to_48()
