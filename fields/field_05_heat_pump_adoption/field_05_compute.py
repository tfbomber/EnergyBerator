import json
import os

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
f3_path = os.path.join(base_dir, "output", "field_03", "FIELD_03_HEAT_GATE_NORF_PILOT.json")
f4_path = os.path.join(base_dir, "output", "field_04", "FIELD_04_PV_ADOPTION_NEUSS_SEGMENTS.json")
segment_candidates_path = os.path.join(base_dir, "intelligence", "discovery", "neuss_segment_candidates_v2.json")
output_dir = os.path.join(base_dir, "output", "field_05")
output_path = os.path.join(output_dir, "FIELD_05_HEAT_PUMP_ADOPTION_NEUSS_SEGMENTS.json")
summary_path = os.path.join(output_dir, "FIELD_05_SUMMARY.json")

def load_json_safe(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def get_band(rate):
    if rate <= 0.05: return "VERY_LOW"
    elif rate <= 0.10: return "LOW"
    elif rate <= 0.15: return "MEDIUM"
    elif rate <= 0.25: return "HIGH"
    else: return "VERY_HIGH"

def compute_field_05():
    # Load upstream signals if they exist
    f3_data = load_json_safe(f3_path)
    f4_data = load_json_safe(f4_path)
    segments = load_json_safe(segment_candidates_path)
    
    f3_data_list = f3_data.get('data', []) if isinstance(f3_data, dict) else (f3_data if isinstance(f3_data, list) else [])
    f3_map = {item['segment_id']: item for item in f3_data_list if isinstance(item, dict) and 'segment_id' in item}
    if not f3_map and isinstance(f3_data, dict) and 'evidence_id' in f3_data:
        # F3 might be a single object
        f3_map = {f3_data.get('segment_id', 'NEUSS_NORF_01'): f3_data}
        
    f4_map = {item['segment_id']: item for item in f4_data if isinstance(item, dict) and 'segment_id' in item}
    
    results = []
    bands_count = {"VERY_LOW": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0, "VERY_HIGH": 0}
    total_est = 0.0
    
    for seg in segments:
        seg_id = seg['segment_id']
        baseline = 0.07
        multiplier = 1.0
        drivers = []
        
        # 1. FIELD 03 (Fernwärme Check)
        f3_sig = f3_map.get(seg_id)
        if f3_sig:
            verdict = f3_sig.get('verdict', '')
            if verdict in ('HEAT_NETWORK_PRESENT', 'REJECTED_HEAT_NETWORK'):
                multiplier *= 0.5
                drivers.append("FERNWAERME_PENALTY_APPLIED")
            elif verdict == 'CLEARED_FOR_INDIVIDUAL_HEATING':
                drivers.append("CLEARED_INDIVIDUAL_HEATING")
                
        # 2. FIELD 04 (PV Adoption)
        f4_sig = f4_map.get(seg_id)
        if f4_sig:
            band = f4_sig.get('adoption_band', '')
            if band in ('HIGH', 'VERY_HIGH'):
                multiplier *= 1.3
                drivers.append("STRONG_PV_ADOPTION_BOOST")
                
        # 3. Morphology (Detached / Density)
        urban_type = seg.get('urban_type', '')
        if 'SUBURBAN' in urban_type or 'DETACHED' in urban_type or seg_id == 'NEUSS_SUBURBAN_01':
            multiplier *= 1.6
            drivers.append("LOW_DENSITY_RESIDENTIAL_BOOST")
            
        # 4. Apply estimate and caps
        est_rate = baseline * multiplier
        if est_rate > 0.35:
            est_rate = 0.35
            drivers.append("CAPPED_AT_MAX_35_PCT")
            
        # 5. Band conversion
        band = get_band(est_rate)
        bands_count[band] += 1
        total_est += est_rate
        
        results.append({
            "field_id": "FIELD_05",
            "segment_id": seg_id,
            "estimated_heat_pump_adoption": round(est_rate, 4),
            "estimated_band": band,
            "confidence": "LOW_MEDIUM",
            "drivers": drivers
        })

    # Export
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    avg_est = (total_est / len(results)) if results else 0.0
    
    summary = {
        "segments_processed": len(results),
        "average_estimated_adoption": round(avg_est, 4),
        "segments_in_each_band": bands_count
    }
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
        
    print("FIELD_05 EXECUTION SUMMARY:")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    compute_field_05()
