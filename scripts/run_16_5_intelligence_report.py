import json
import os
from collections import defaultdict

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
f3_path = os.path.join(base_dir, "output", "field_03", "FIELD_03_HEAT_GATE_NORF_PILOT.json")
f4_path = os.path.join(base_dir, "output", "field_04", "FIELD_04_PV_ADOPTION_NEUSS_SEGMENTS.json")
f5_path = os.path.join(base_dir, "output", "field_05", "FIELD_05_HEAT_PUMP_ADOPTION_NEUSS_SEGMENTS.json")
clusters_path = os.path.join(base_dir, "output", "clusters", "neuss_hybrid_clusters_v1.json")
routes_path = os.path.join(base_dir, "output", "routes", "neuss_route_sheets_v1.json")

output_dir = os.path.join(base_dir, "output", "segment_reports")
os.makedirs(output_dir, exist_ok=True)

def load_json_safe(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def run_report():
    f3_data = load_json_safe(f3_path)
    f4_data = load_json_safe(f4_path)
    f5_data = load_json_safe(f5_path)
    clusters_data = load_json_safe(clusters_path)
    routes_data = load_json_safe(routes_path)
    
    # Pre-process lookups
    f3_list = f3_data.get('data', []) if isinstance(f3_data, dict) else (f3_data if isinstance(f3_data, list) else [])
    # F3 fallback for single object output mapping
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
        
    reports_generated = 0
    file_paths = []

    for seg in sorted(list(all_segments)):
        # Route Aggregation
        seg_routes = [r for r in routes_data if r.get('segment_id') == seg]
        seg_clusters = [c for c in clusters_data if c.get('segment_id') == seg]
        
        c_count = len(seg_clusters)
        avg_c_size = sum(c['lead_count'] for c in seg_clusters) / c_count if c_count > 0 else 0
        a_leads_c = sum(c['A_count'] for c in seg_clusters)
        b_leads_c = sum(c['B_count'] for c in seg_clusters)
        
        street_counts = defaultdict(int)
        for r in seg_routes:
            st = str(r.get('street', '')).strip()
            if st:
                street_counts[st] += 1
                
        top_streets = sorted(street_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        unique_route_ids = set()
        a_stops = 0
        b_stops = 0
        for r in seg_routes:
            unique_route_ids.add(r['route_id'])
            if r['lead_class'] == 'A':
                a_stops += 1
            if r['lead_class'] == 'B':
                b_stops += 1

        # Field Aggregations
        f3 = f3_map.get(seg, {})
        f4 = f4_map.get(seg, {})
        f5 = f5_map.get(seg, {})
        
        f3_verdict = f3.get('verdict', 'NO_DATA')
        f3_status = f3.get('status', 'NO_DATA')
        f4_score = f4.get('adoption_score_normalized', 'NO_DATA')
        f4_strength = f4.get('signal_strength', 'NO_DATA')
        
        f5_band = f5.get('estimated_band', 'NO_DATA')
        f5_rate = f5.get('estimated_heat_pump_adoption', 'NO_DATA')
        
        # Derive Narrative (Electrification Depth)
        depth = "LOW"
        if f5_band in ("HIGH", "VERY_HIGH"):
            depth = "HIGH"
        elif f5_band == "MEDIUM":
            depth = "MEDIUM"
            
        drivers_text = []
        if f3_verdict in ("HEAT_NETWORK_PRESENT", "REJECTED_HEAT_NETWORK"):
            drivers_text.append("Hard limitation due to existing Fernwärme infrastructure.")
        if f4_score != "NO_DATA" and float(f4_score) > 0.05:
            drivers_text.append("Early PV adoption indicators present, suggesting electrification readiness.")
        if f5.get('drivers'):
            drivers_text.extend(f5['drivers'])
            
        if not drivers_text:
            drivers_text.append("Insufficient signals; awaiting deeper infrastructure clarity.")
            
        # Write Output
        lines = []
        lines.append(f"# Segment Intelligence Report")
        lines.append(f"**Segment ID:** {seg}  ")
        lines.append(f"**City:** Neuss  ")
        lines.append("\n---")
        
        lines.append(f"## Heat Infrastructure (FIELD_03)")
        lines.append(f"- **Verdict / Constraint:** {f3_verdict}")
        lines.append(f"- **Status:** {f3_status}")
        lines.append("")
        
        lines.append(f"## PV Adoption (FIELD_04)")
        lines.append(f"- **Adoption Score:** {f4_score}")
        lines.append(f"- **Signal Strength:** {f4_strength}")
        lines.append("")
        
        lines.append(f"## Heat Pump Adoption Estimate (FIELD_05)")
        lines.append(f"- **Estimated Band:** {f5_band}")
        lines.append(f"- **Estimated Rate:** {f5_rate}")
        lines.append("")
        
        lines.append(f"## Electrification Depth")
        lines.append(f"- **Potential:** {depth}")
        lines.append(f"- **Drivers:** ")
        for dt in set(drivers_text):
            lines.append(f"  - {dt}")
        lines.append("")
        
        lines.append(f"## Cluster Summary")
        lines.append(f"- **Total Clusters:** {c_count}")
        lines.append(f"- **Average Cluster Size:** {round(avg_c_size, 1)}")
        lines.append(f"- **Lead Distribution:** {a_leads_c} A-Leads, {b_leads_c} B-Leads")
        lines.append("")
        
        lines.append(f"## Key Streets Identified")
        for k, v in top_streets:
            lines.append(f"- {k} ({v} leads)")
        if not top_streets:
            lines.append("- No named street extraction performed.")
        lines.append("")
        
        lines.append(f"## Field Deployment Summary")
        lines.append(f"- **Total Routes:** {len(unique_route_ids)}")
        lines.append(f"- **Total Stops:** {len(seg_routes)}")
        lines.append(f"- **A Leads:** {a_stops}")
        lines.append(f"- **B Leads:** {b_stops}")
        
        md_content = "\n".join(lines)
        
        out_file = os.path.join(output_dir, f"segment_intelligence_{seg}.md")
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        reports_generated += 1
        file_paths.append(out_file)

    print("STAGE 16.5 REPORT EXECUTION:")
    print(f"Segments Processed: {len(all_segments)}")
    print(f"Reports Generated: {reports_generated}")
    print("Output File Paths:")
    for fp in file_paths:
        print(f"  - {fp}")

if __name__ == "__main__":
    run_report()
