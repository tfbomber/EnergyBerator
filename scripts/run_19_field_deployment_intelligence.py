import json
import os
import re

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
output_dir = os.path.join(base_dir, "output", "field_deployment")

os.makedirs(output_dir, exist_ok=True)

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def safe_float(v, default=0.0):
    try:
        return float(v)
    except:
        return default

def extract_street_name(label):
    # 'Himmelgeister Straße (Part 1)' -> 'Himmelgeister Straße'
    return re.sub(r'\s*\(Part \d+\)\s*', '', label).strip()

def run_stage_19():
    clusters = load_json(os.path.join(base_dir, "output", "clusters", "neuss_hybrid_clusters_v1.json"))
    f4_data = load_json(os.path.join(base_dir, "output", "field_04", "FIELD_04_PV_ADOPTION_NEUSS_SEGMENTS.json"))
    
    f4_map = {item['segment_id']: safe_float(item.get('adoption_score_normalized', 0.15)) for item in f4_data if isinstance(item, dict) and 'segment_id' in item}
    
    seg_map = {}
    for c in clusters:
        seg = c['segment_id']
        if seg not in seg_map:
            seg_map[seg] = []
        seg_map[seg].append(c)
        
    execution_report = {
        "segments_processed": 0,
        "clusters_analyzed": 0,
        "top_streets_identified": set(),
        "total_revenue_potential": 0.0
    }

    report_lines = ["# Stage 19 Execution Report\n"]

    for seg, seg_clusters in seg_map.items():
        execution_report["segments_processed"] += 1
        
        # Load Stage 18 Ground truth for this segment
        gt_path = os.path.join(base_dir, "output", "ground_truth_validation", f"cluster_validation_{seg}.json")
        gt_data = load_json(gt_path)
        gt_vals = gt_data.get("cluster_validations", []) if isinstance(gt_data, dict) else []
        gt_map = {v['cluster_id']: v for v in gt_vals}
        
        pv_adoption_score = f4_map.get(seg, 0.15)
        
        priority_list = []
        
        for c in seg_clusters:
            execution_report["clusters_analyzed"] += 1
            cid = c['cluster_id']
            lead_count = c.get('lead_count', 1)
            a_count = c.get('A_count', 0)
            
            # Module 19A Logic
            gt = gt_map.get(cid, {})
            val_score = gt.get('validation_score', 0.5)
            
            a_density = a_count / lead_count if lead_count > 0 else 0.0
            c_size_norm = min(lead_count / 50.0, 1.0)
            
            rq_str = gt.get('ground_truth', {}).get('roof_quality', 'mixed_roof')
            if rq_str == 'good_roof': rq_score = 1.0
            elif rq_str == 'mixed_roof': rq_score = 0.5
            else: rq_score = 0.0
            
            priority_score = (0.40 * val_score) + (0.25 * a_density) + (0.15 * pv_adoption_score) + (0.10 * c_size_norm) + (0.10 * rq_score)
            priority_score = round(priority_score, 3)
            
            if priority_score >= 0.80: tier = "TIER_1"
            elif priority_score >= 0.65: tier = "TIER_2"
            else: tier = "TIER_3"
            
            c_info = {
                "cluster_id": cid,
                "cluster_label": c.get('cluster_label', ''),
                "priority_score": priority_score,
                "tier": tier,
                "lead_count": lead_count,
                "val_score": val_score
            }
            priority_list.append(c_info)
            
        priority_list.sort(key=lambda x: x['priority_score'], reverse=True)
        
        # Export 19A
        with open(os.path.join(output_dir, f"installer_priority_{seg}.json"), 'w', encoding='utf-8') as f:
            json.dump(priority_list, f, indent=2)
            
        # Module 19B Street Leaderboard
        street_agg = {}
        for p in priority_list:
            st = extract_street_name(p['cluster_label'])
            if not st: st = "Unnamed Local"
            if st not in street_agg:
                street_agg[st] = {'total_houses': 0, 'cluster_count': 0, 'val_scores': [], 'pri_scores': []}
            street_agg[st]['total_houses'] += p['lead_count']
            street_agg[st]['cluster_count'] += 1
            street_agg[st]['val_scores'].append(p['val_score'])
            street_agg[st]['pri_scores'].append(p['priority_score'])
            
        street_list = []
        for st, data in street_agg.items():
            avg_v = sum(data['val_scores']) / data['cluster_count']
            avg_p = sum(data['pri_scores']) / data['cluster_count']
            street_list.append({
                "street": st,
                "total_houses": data['total_houses'],
                "cluster_count": data['cluster_count'],
                "avg_validation_score": round(avg_v, 2),
                "priority_score": round(avg_p, 2)
            })
            
        street_list.sort(key=lambda x: x['priority_score'], reverse=True)
        top_20 = street_list[:20]
        
        md_b = [f"# Street Opportunity Leaderboard: {seg}\n"]
        for idx, t in enumerate(top_20):
            md_b.append(f"### {idx+1}. {t['street']}")
            md_b.append(f"- **Priority Score**: {t['priority_score']}")
            md_b.append(f"- **Houses**: {t['total_houses']}")
            md_b.append(f"- **Clusters**: {t['cluster_count']}")
            md_b.append(f"- **Avg Reality Validation**: {t['avg_validation_score']}\n")
            execution_report["top_streets_identified"].add(t['street'])
            
        with open(os.path.join(output_dir, f"street_leaderboard_{seg}.md"), 'w', encoding='utf-8') as f:
            f.write("\n".join(md_b))
            
        # Module 19C Field Route Optimization
        md_c = [f"# Field Routes: {seg}\n"]
        day_idx = 1
        current_day_count = 0
        current_day_clusters = []
        
        for p in priority_list:
            if current_day_count + p['lead_count'] > 40 and current_day_count >= 20:
                md_c.append(f"### Day {day_idx}")
                md_c.append(f"**Clusters**: {', '.join(current_day_clusters)}")
                md_c.append(f"**Total Estimated Stops**: {current_day_count}\n")
                day_idx += 1
                current_day_count = 0
                current_day_clusters = []
                
            current_day_clusters.append(p['cluster_id'])
            current_day_count += p['lead_count']
            
        if current_day_clusters:
            md_c.append(f"### Day {day_idx}")
            md_c.append(f"**Clusters**: {', '.join(current_day_clusters)}")
            md_c.append(f"**Total Estimated Stops**: {current_day_count}\n")
            
        with open(os.path.join(output_dir, f"deployment_routes_{seg}.md"), 'w', encoding='utf-8') as f:
            f.write("\n".join(md_c))
            
        # Module 19D Revenue Potential
        d2d_rate = 0.085 # 8.5%
        event_rate = 0.055
        digi_rate = 0.02
        rev_data = []
        for p in priority_list:
            lc = p['lead_count']
            e_installs = lc * d2d_rate
            revenue_pv = e_installs * 12000
            revenue_pvb = e_installs * 18000
            revenue_hp = e_installs * 25000
            
            execution_report["total_revenue_potential"] += revenue_pvb # Baseline sum for report
            
            rev_data.append({
                "cluster_id": p['cluster_id'],
                "estimated_installs_d2d": round(e_installs, 2),
                "estimated_revenue_PV": round(revenue_pv, 2),
                "estimated_revenue_PV_Battery": round(revenue_pvb, 2),
                "estimated_revenue_HeatPump": round(revenue_hp, 2)
            })
            
        with open(os.path.join(output_dir, f"revenue_projection_{seg}.json"), 'w', encoding='utf-8') as f:
            json.dump(rev_data, f, indent=2)
            
        # Module 19E Campaign Playbook
        md_e = [f"# Campaign Playbook: {seg}\n"]
        t1_streets = [s for s in street_list if s['priority_score'] >= 0.80]
        if not t1_streets and top_20:
            md_e.append("> No pure Tier 1 streets met the threshold; substituting highest priority streets for immediate playbook generation.\n")
            t1_streets = top_20[:3]
            
        for st in t1_streets:
            md_e.append(f"## Target Street: {st['street']}")
            md_e.append(f"- **Housing Density**: {st['total_houses']} localized targets")
            md_e.append(f"- **Recommended Sales Approach**: Direct Door-to-Door Canvassing supplemented by prior Direct Mail.")
            md_e.append(f"- **Door Knocking Script**: 'Hello! Your neighbor is planning an energy upgrade and we noticed your roof has exceptional geometry for PV. Would you like a free assessment while our engineers are on the street?'")
            md_e.append(f"- **Flyer Campaign**: Distribute 'Group Buying Discount' flyers 48 hours before physical visit.")
            md_e.append(f"- **Installer Visit**: Assign to A-Team due to high probability density.\n")
            
        with open(os.path.join(output_dir, f"campaign_playbook_{seg}.md"), 'w', encoding='utf-8') as f:
            f.write("\n".join(md_e))

        report_lines.append(f"## Segment: {seg}")
        report_lines.append(f"- Clusters Analyzed: {len(priority_list)}")
        report_lines.append(f"- Top Tier Streets Extracted: {len(t1_streets)}")

    # Central Execution Report
    report_lines.insert(1, f"- **Total Segments Processed**: {execution_report['segments_processed']}")
    report_lines.insert(2, f"- **Total Clusters Analyzed**: {execution_report['clusters_analyzed']}")
    report_lines.insert(3, f"- **Top Unique Streets Targeted**: {len(execution_report['top_streets_identified'])}")
    report_lines.insert(4, f"- **Projected Baseline Pipeline Value**: €{round(execution_report['total_revenue_potential'], 2):,}\n")
    
    with open(os.path.join(output_dir, "stage_19_execution_report.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print("STAGE_19_SUCCESS")

if __name__ == "__main__":
    run_stage_19()
