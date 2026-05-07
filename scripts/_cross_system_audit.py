import pandas as pd

l2 = pd.read_parquet('data/layer2/layer2_mvp_input_table.parquet')
f8 = pd.read_parquet('data/layer2/street_level_ranking_v1.parquet')

print("=== Cross-system SFH ratio comparison ===")
print("L2 = layer2_mvp_input_table (effective_sfh_share, denominator from building_universe)")
print("F8 = street_level_ranking (sfh_total_count / building_count_total from foundation JSON)")
print()

for _, row in l2[l2['row_usable_for_ranking']==True].iterrows():
    seg = row['unit_id']
    l2_sfh = float(row.get('effective_sfh_share', 0))
    
    seg_streets = f8[f8['segment_id'] == seg]
    if seg_streets.empty:
        print(f"  {seg:25s} | L2={l2_sfh:.2%} | F8=N/A | MISSING")
        continue
    
    total_bld = seg_streets['building_count_total'].sum()
    total_sfh = seg_streets['sfh_total_count'].sum()
    f8_ratio = total_sfh / total_bld if total_bld > 0 else 0
    
    delta = abs(l2_sfh - f8_ratio)
    status = 'OK' if delta < 0.05 else 'DRIFT' if delta < 0.15 else 'DIVERGENT'
    print(f"  {seg:25s} | L2={l2_sfh:.2%} | F8={f8_ratio:.2%} | delta={delta:.2%} | {status}")

# Also check: do the building_count_total values in F8 match the building_universe?
print()
print("=== Building count source comparison ===")
print("L2 = f02_building_count (from building_universe)")
print("F8 = sum(building_count_total) (from foundation JSON)")
print()

for _, row in l2[l2['row_usable_for_ranking']==True].iterrows():
    seg = row['unit_id']
    l2_total = int(row.get('f02_building_count', 0) or 0)
    
    seg_streets = f8[f8['segment_id'] == seg]
    f8_total = int(seg_streets['building_count_total'].sum()) if not seg_streets.empty else 0
    
    match = "MATCH" if l2_total == f8_total else "MISMATCH"
    print(f"  {seg:25s} | L2_universe={l2_total:,} | F8_foundation={f8_total:,} | {match}")
