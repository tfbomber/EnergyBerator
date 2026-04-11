import json
import os
from collections import defaultdict

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
f3_path = os.path.join(base_dir, "output", "field_03", "FIELD_03_HEAT_GATE_NORF_PILOT.json")
f4_path = os.path.join(base_dir, "output", "field_04", "FIELD_04_PV_ADOPTION_NEUSS_SEGMENTS.json")
f5_path = os.path.join(base_dir, "output", "field_05", "FIELD_05_HEAT_PUMP_ADOPTION_NEUSS_SEGMENTS.json")
clusters_path = os.path.join(base_dir, "output", "clusters", "neuss_hybrid_clusters_v1.json")
routes_path = os.path.join(base_dir, "output", "routes", "neuss_route_sheets_v1.json")

output_dir = os.path.join(base_dir, "output", "opportunity_snapshots")
os.makedirs(output_dir, exist_ok=True)

def load_json_safe(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def run_snapshot():
    f3_data = load_json_safe(f3_path)
    f4_data = load_json_safe(f4_path)
    f5_data = load_json_safe(f5_path)
    clusters_data = load_json_safe(clusters_path)
    routes_data = load_json_safe(routes_path)
    
    # Pre-process lookups
    f3_list = f3_data.get('data', []) if isinstance(f3_data, dict) else (f3_data if isinstance(f3_data, list) else [])
    if not f3_list and isinstance(f3_data, dict) and 'evidence_id' in f3_data:
        f3_list = [f3_data]
    
    f3_map = {item.get('segment_id', 'NEUSS_NORF_01'): item for item in f3_list if isinstance(item, dict)}
    f4_map = {item['segment_id']: item for item in f4_data if isinstance(item, dict) and 'segment_id' in item}
    f5_map = {item['segment_id']: item for item in f5_data if isinstance(item, dict) and 'segment_id' in item}
    
    # Find all known segments across any system field
    all_segments = set()
    all_segments.update(f3_map.keys())
    all_segments.update(f4_map.keys())
    all_segments.update(f5_map.keys())
    for r in routes_data:
        all_segments.add(r['segment_id'])
    for c in clusters_data:
        all_segments.add(c['segment_id'])
        
    snapshots_generated = 0
    file_paths = []

    for seg in sorted(list(all_segments)):
        # Tactical Aggregation
        seg_routes = [r for r in routes_data if r.get('segment_id') == seg]
        seg_clusters = [c for c in clusters_data if c.get('segment_id') == seg]
        
        c_count = len(seg_clusters)
        avg_c_size = (sum(c['lead_count'] for c in seg_clusters) / c_count) if c_count > 0 else 0
        a_leads = sum(c['A_count'] for c in seg_clusters)
        b_leads = sum(c['B_count'] for c in seg_clusters)
        total_leads = a_leads + b_leads
        
        street_counts = defaultdict(int)
        for r in seg_routes:
            st = str(r.get('street', '')).strip()
            if st:
                street_counts[st] += 1
                
        top_streets = sorted(street_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        unique_route_ids = set()
        for r in seg_routes:
            unique_route_ids.add(r['route_id'])
        r_count = len(unique_route_ids)
        avg_route_stops = (len(seg_routes) / r_count) if r_count > 0 else 0

        # Strategic Aggregations
        f3 = f3_map.get(seg, {})
        f4 = f4_map.get(seg, {})
        f5 = f5_map.get(seg, {})
        
        f3_verdict = f3.get('verdict', 'NO_DATA')
        f3_status = f3.get('status', 'NO_DATA')
        f4_score = f4.get('adoption_score_normalized', 'NO_DATA')
        f4_strength = f4.get('signal_strength', 'NO_DATA')
        f5_band = f5.get('estimated_band', 'NO_DATA')
        f5_rate = f5.get('estimated_heat_pump_adoption', 'NO_DATA')
        
        # Determine depth composite
        depth = "LOW"
        if f5_band in ("HIGH", "VERY_HIGH"):
            depth = "HIGH"
        elif f5_band == "MEDIUM":
            depth = "MEDIUM"
            
        # Determine narratives
        narrative_opp = ""
        narrative_exec = ""
        
        if f3_verdict in ("HEAT_NETWORK_PRESENT", "REJECTED_HEAT_NETWORK"):
            narrative_opp = "Restricted electrification opportunity due to existing Fernwärme (district heating) obligations. Minimal immediate direct-to-home heating upgrade potential."
            narrative_exec = "Deployment should strictly pivot back towards PV-dominant upsells. Skip extensive heating audit questions on the doorstep."
        elif depth in ("HIGH", "MEDIUM") and a_leads > 0:
            narrative_opp = "Strong multi-vector electrification opportunity. Area clears core infrastructure hurdles and possesses solid PV footprint overlap indicators."
            narrative_exec = "Prime Canvassing Target. Highly clustered deployment enables 'door-to-door first' saturation scaling. Sales scripts should open with grid-independence narratives."
        else:
            narrative_opp = "Moderate exploratory electrification area. Market viability requires localized door-level truth filtering."
            narrative_exec = "Deploy standard balanced sales units. Focus targeting specifically on isolated properties triggering Class-A profiles prior to bulk street-sweeping."

        # Markdown payload
        lines = []
        lines.append(f"# Opportunity Snapshot")
        lines.append(f"**Segment ID:** {seg}  ")
        lines.append(f"**City:** Neuss  ")
        lines.append("\n---")
        
        lines.append(f"## 2. Opportunity Summary")
        lines.append(f"> {narrative_opp}")
        lines.append("")
        
        lines.append(f"## 3. Infrastructure Context (FIELD_03)")
        lines.append(f"- **Constraint:** {f3_verdict}")
        lines.append(f"- **Heat Planning Status:** {f3_status}")
        lines.append("")
        
        lines.append(f"## 4. PV Adoption Signal (FIELD_04)")
        lines.append(f"- **Adoption Score:** {f4_score}")
        lines.append(f"- **Signal Strength:** {f4_strength}")
        lines.append("")
        
        lines.append(f"## 5. Heat Pump Adoption Estimate (FIELD_05)")
        lines.append(f"- **Estimated Band:** {f5_band}")
        lines.append(f"- **Estimated Rate:** {f5_rate}")
        lines.append("")
        
        lines.append(f"## 6. Electrification Depth")
        lines.append(f"- **Composite Rating:** {depth} potential")
        lines.append("")
        
        lines.append(f"## 7. Market Size Estimate")
        lines.append(f"- **Estimated Residential Buildings:** {total_leads} (Target Audience)")
        lines.append(f"- **Clustered Opportunities:** {c_count} distinct field clusters")
        lines.append(f"- **A-Class Leads:** {a_leads}")
        lines.append(f"- **B-Class Leads:** {b_leads}")
        lines.append("")
        
        lines.append(f"## 8. Deployment Structure")
        lines.append(f"- **Cluster Count:** {c_count}")
        lines.append(f"- **Average Cluster Size:** {round(avg_c_size, 1)} properties")
        lines.append(f"- **Route Count:** {r_count} executable routes")
        lines.append(f"- **Average Stops per Route:** {round(avg_route_stops, 1)}")
        lines.append("")
        
        lines.append(f"## 9. Key Streets")
        for k, v in top_streets:
            lines.append(f"- {k} ({v} leads)")
        if not top_streets:
            lines.append("- No named street data locally available.")
        lines.append("")
        
        lines.append(f"## 10. Execution Narrative")
        lines.append(f"**Why targeted:** {narrative_exec}")
        
        md_content = "\n".join(lines)
        
        out_file = os.path.join(output_dir, f"opportunity_snapshot_{seg}.md")
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        snapshots_generated += 1
        file_paths.append(out_file)

    print("STAGE 17 REPORT EXECUTION:")
    print(f"Segments Processed: {len(all_segments)}")
    print(f"Snapshots Generated: {snapshots_generated}")
    print("Output File Paths:")
    for fp in file_paths:
        print(f"  - {fp}")

if __name__ == "__main__":
    run_snapshot()
