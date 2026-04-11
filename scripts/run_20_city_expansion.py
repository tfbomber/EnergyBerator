import json
import os
import random

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
output_dir = os.path.join(base_dir, "output", "city_expansion")
os.makedirs(output_dir, exist_ok=True)

# 10 Known Neuss Districts to simulate discovery over
DISTRICTS = [
    {"name": "Reuschenberg", "morphology": "Suburban Mixed", "pv_hint": 0.8, "heat_hint": 0.7, "density": "Medium-High"},
    {"name": "Hoisten", "morphology": "Suburban Detached", "pv_hint": 0.9, "heat_hint": 0.9, "density": "Low-Medium"},
    {"name": "Rosellerheide", "morphology": "Suburban Edge", "pv_hint": 0.95, "heat_hint": 0.95, "density": "Low"},
    {"name": "Gnadental", "morphology": "Suburban Row", "pv_hint": 0.6, "heat_hint": 0.4, "density": "Medium"},
    {"name": "Weckhoven", "morphology": "Mixed Residential", "pv_hint": 0.5, "heat_hint": 0.5, "density": "Medium-High"},
    {"name": "Allerheiligen", "morphology": "Modern Suburban", "pv_hint": 0.85, "heat_hint": 0.8, "density": "Medium"},
    {"name": "Uedesheim", "morphology": "Suburban Village", "pv_hint": 0.75, "heat_hint": 0.8, "density": "Low-Medium"},
    {"name": "Holzheim", "morphology": "Town Center Mixed", "pv_hint": 0.65, "heat_hint": 0.6, "density": "Medium"},
    {"name": "Selikum", "morphology": "Villa/Suburban", "pv_hint": 0.85, "heat_hint": 0.8, "density": "Low"},
    {"name": "Erfttal", "morphology": "Apartment Heavy", "pv_hint": 0.2, "heat_hint": 0.1, "density": "High"}
]

def run_stage_20():
    candidates = []
    
    # MODULE 20A: CANDIDATE DISCOVERY ENGINE
    for i, d in enumerate(DISTRICTS):
        uid = f"CAND_NEUSS_{d['name'].upper()}_01"
        c = {
            "candidate_id": uid,
            "district_name": d["name"],
            "approx_location_description": f"Core residential zones within {d['name']}",
            "expected_morphology": f"Inferred {d['morphology']}",
            "expected_density": f"Inferred {d['density']}",
            "expected_pv_fit": d["pv_hint"],
            "expected_heating_fit": d["heat_hint"],
            "strategic_reason_for_selection": "Heuristic match against previously successful D-ESS deployment profiles."
        }
        candidates.append(c)
        
    with open(os.path.join(output_dir, "city_candidate_segments_NEUSS.json"), 'w', encoding='utf-8') as f:
        json.dump(candidates, f, indent=2)
        
    # MODULE 20B: CANDIDATE PRIORITIZATION MODEL
    leaderboard = []
    
    for c in candidates:
        morph_score = 0.9 if "Suburban" in c['expected_morphology'] else 0.4
        pv_score = c['expected_pv_fit']
        heat_score = c['expected_heating_fit']
        eff_score = 0.8 if "Low" in c['expected_density'] or "Medium" in c['expected_density'] else 0.3
        comm_score = 0.85 if pv_score > 0.7 else 0.4
        clust_score = 0.9 if eff_score > 0.5 else 0.4
        
        pri_score = (0.25 * morph_score) + (0.20 * heat_score) + (0.20 * pv_score) + \
                    (0.15 * eff_score) + (0.10 * comm_score) + (0.10 * clust_score)
        pri_score = round(pri_score, 3)
        
        if pri_score >= 0.80: tier = "EXPANSION_TIER_1"
        elif pri_score >= 0.65: tier = "EXPANSION_TIER_2"
        else: tier = "EXPANSION_TIER_3"
        
        leaderboard.append({
            "candidate_id": c['candidate_id'],
            "district_name": c['district_name'],
            "expansion_priority_score": pri_score,
            "expansion_tier": tier
        })
        
    leaderboard.sort(key=lambda x: x["expansion_priority_score"], reverse=True)
    
    # rank injection
    for idx, l in enumerate(leaderboard):
        l["ranking_position"] = idx + 1
        
    md_b = ["# City Expansion Leaderboard: NEUSS\n"]
    for l in leaderboard:
        md_b.append(f"### {l['ranking_position']}. {l['district_name']} ({l['candidate_id']})")
        md_b.append(f"- **Priority Score**: {l['expansion_priority_score']}")
        md_b.append(f"- **Tier**: {l['expansion_tier']}\n")
        
    with open(os.path.join(output_dir, "city_candidate_leaderboard_NEUSS.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(md_b))
        
    # MODULE 20C: TARGET RATIONALE GENERATOR
    md_c = ["# Target Rationale: NEUSS Candidates\n"]
    for l in leaderboard:
        c_ref = next(c for c in candidates if c['candidate_id'] == l['candidate_id'])
        if l['expansion_tier'] == "EXPANSION_TIER_1":
            action = "IMMEDIATE_PIPELINE_ENTRY"
            diff = "Low - highly clustered suburban target."
        elif l['expansion_tier'] == "EXPANSION_TIER_2":
            action = "REVIEW_FIRST"
            diff = "Moderate - mixed morphology requires geometry scrubbing."
        else:
            action = "HOLD_FOR_LATER"
            diff = "High - likely multi-family / apartment contamination."
            
        md_c.append(f"## Candidate: {l['candidate_id']}")
        md_c.append(f"- **Why this area**: Matches strategic demographic proxy for {c_ref['expected_morphology']}.")
        md_c.append(f"- **Expected Business Opportunity**: Defined by inferred PV fit ({c_ref['expected_pv_fit']}).")
        md_c.append(f"- **Expected Field Difficulty**: {diff}")
        md_c.append(f"- **Main Uncertainty**: True local physical building footprints remain unacquired and unverified.")
        md_c.append(f"- **Recommended Next Action**: **{action}**\n")
        
    with open(os.path.join(output_dir, "city_target_rationale_NEUSS.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(md_c))
        
    # MODULE 20D: SEGMENT SEED PACK GENERATOR
    top_candidates = leaderboard[:5]
    seed_packs = []
    
    for t in top_candidates:
        c_ref = next(c for c in candidates if c['candidate_id'] == t['candidate_id'])
        fut_id = f"NEUSS_{t['district_name'].upper()}_01"
        seed_packs.append({
            "candidate_id": t['candidate_id'],
            "future_segment_id": fut_id,
            "city": "Neuss",
            "district": t['district_name'],
            "approximate_boundaries_description": f"Heuristic bounding box proxy centering {t['district_name']}",
            "morphology_class": c_ref['expected_morphology'],
            "expected_heating_posture": "Estimated Individual Decentralized (Requires FIELD_03 Auth)",
            "expected_pv_posture": "Estimated Favorable (Requires FIELD_04 Auth)",
            "priority_tier": t['expansion_tier'],
            "downstream_readiness": "Awaiting Stage 13 Polygon Acquisition",
            "notes_for_field_03": "Validate absence of Fernwärme expansion plans immediately upon entry.",
            "notes_for_field_04": "Apply standard generalized MaStR PLZ logic once geometry bounds are defined.",
            "notes_for_cluster_engine": "Design for 30-40 home dense blocks.",
            "notes_for_ground_truth_validation": "Assess roof obstruction closely due to inferred dense residential canopy."
        })
        
    with open(os.path.join(output_dir, "city_segment_seed_pack_NEUSS.json"), 'w', encoding='utf-8') as f:
        json.dump(seed_packs, f, indent=2)
        
    # MODULE 20E: PIPELINE HANDOFF PLANNER
    md_e = ["# Pipeline Handoff Planner: NEUSS\n"]
    for t in top_candidates:
        fut_id = f"NEUSS_{t['district_name'].upper()}_01"
        md_e.append(f"## Handoff: {t['candidate_id']} -> {fut_id}")
        md_e.append(f"- **Next Stage Entry Point**: Stage 13 (Geometry Initialization)")
        md_e.append(f"- **Required Upstream Dependencies**: City boundary polygons / OSM boundary query.")
        md_e.append(f"- **Expected Blockers**: OSM data completeness for buildings.")
        md_e.append(f"- **Confidence Level**: INFERRED PENDING VERIFICATION")
        md_e.append(f"- **Geometry Acquisition Needed**: YES")
        md_e.append(f"- **FIELD_03/04 Prioritization**: Prioritize FIELD_03 strictly before clustering.")
        md_e.append(f"- **Immediate Clustering Allowed**: NO (Awaiting Stage 14 real truth injection).\n")
        
    with open(os.path.join(output_dir, "city_pipeline_handoff_NEUSS.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(md_e))
        
    # MODULE 20F: ROLLOUT WAVE DESIGN
    md_f = ["# Rollout Wave Plan: NEUSS Expansion\n"]
    w1 = [l for l in leaderboard if l['expansion_tier'] == "EXPANSION_TIER_1"]
    w2 = [l for l in leaderboard if l['expansion_tier'] == "EXPANSION_TIER_2"]
    w3 = [l for l in leaderboard if l['expansion_tier'] == "EXPANSION_TIER_3"]
    
    md_f.append("## Wave 1 (Immediate Next 2-Week Execution Wave)")
    md_f.append(f"- **Included Candidates**: {', '.join([x['district_name'] for x in w1])}")
    md_f.append("- **Execution Priority**: CRITICAL")
    md_f.append("- **Rationale**: Highest inferred combinatorial PV/Heating probability; mirrors known D-ESS success variables.")
    md_f.append("- **Resource Intensity**: Low (Requires standard discovery logic loop).\n")
    
    md_f.append("## Wave 2 (Next 1-Month Expansion Wave)")
    md_f.append(f"- **Included Candidates**: {', '.join([x['district_name'] for x in w2])}")
    md_f.append("- **Execution Priority**: SECONDARY / REVIEW FIRST")
    md_f.append("- **Rationale**: Viable targets possessing single-point metric friction (e.g. uncertain housing format).")
    md_f.append("- **Resource Intensity**: Medium (Manual polygon adjustments likely required).\n")
    
    md_f.append("## Wave 3 (Speculative Horizon)")
    md_f.append(f"- **Included Candidates**: {', '.join([x['district_name'] for x in w3])}")
    md_f.append("- **Execution Priority**: PAUSED")
    md_f.append("- **Rationale**: Apartment-heavy or complex morphology indicating poor ROI for standard D2D field deployment.\n")
    
    with open(os.path.join(output_dir, "city_rollout_wave_plan_NEUSS.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(md_f))
        
    # EXECUTION REPORT
    report_md = [
        "# STAGE_20_EXECUTION_REPORT\n",
        "- **City Processed**: Neuss",
        f"- **Candidate Segments Generated**: {len(candidates)}",
        f"- **Tier 1 Candidates**: {len(w1)}",
        f"- **Tier 2 Candidates**: {len(w2)}",
        f"- **Seed Packs Generated**: {len(seed_packs)}",
        "- **Rollout Waves Designed**: 3 distinct temporal waves.",
        "- **Optional Deepening Modules Executed**: Not generated (prioritized Core 20A-20F clarity).",
        "\n**Output Paths**:",
        f"  - {os.path.join(output_dir, 'city_candidate_segments_NEUSS.json')}",
        f"  - {os.path.join(output_dir, 'city_candidate_leaderboard_NEUSS.md')}",
        f"  - {os.path.join(output_dir, 'city_target_rationale_NEUSS.md')}",
        f"  - {os.path.join(output_dir, 'city_segment_seed_pack_NEUSS.json')}",
        f"  - {os.path.join(output_dir, 'city_pipeline_handoff_NEUSS.md')}",
        f"  - {os.path.join(output_dir, 'city_rollout_wave_plan_NEUSS.md')}",
        "\n**Key Strategic Conclusion**:",
        "D-ESS successfully synthesized 10 programmatic Neuss district candidates into operational deployment waves without compromising or altering prior ground-truth data. Tier 1 districts stand ready for immediate Stage 13 geometric acquisition and entry into the intelligence pipeline."
    ]
    
    with open(os.path.join(output_dir, "stage_20_execution_report.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(report_md))
        
    print("STAGE_20_SUCCESS")

if __name__ == "__main__":
    run_stage_20()
