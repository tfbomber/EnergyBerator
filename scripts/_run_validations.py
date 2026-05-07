import json
import pandas as pd

print("=== Test 1: Foundation Output Sanity Check (Sternstraße) ===")
with open('output/foundation/foundation_structure_results.json', encoding='utf-8') as f:
    data = json.load(f)
clusters = data if isinstance(data, list) else []

for c in clusters:
    if str(c.get('plz','')) == '41460' and 'Stern' in c.get('street_name',''):
        print(f"Sternstraße: sfh={c['sfh_total_count']}/{c['building_count_total']} ratio={c['sfh_total_ratio']:.0%}")
        print(f"  detached={c['sfh_detached_count']} semi={c['sfh_semi_detached_count']} rh={c['sfh_rowhouse_count']} mfh={c['mfh_count']}")
        print(f"  gate={c['structure_gate']}")

print("\n=== Test 4: Street-Level UI Spot Check (PLZ41460) ===")
f8 = pd.read_parquet('data/layer2/street_level_ranking_v1.parquet')
seg = f8[f8['segment_id']=='NEUSS_PLZ41460']
pass_streets = seg[seg['structure_gate'].isin(['PASS','QUALIFIED'])]
print(f"PLZ41460 PASS/QUALIFIED streets: {len(pass_streets)}")
for _, s in pass_streets.head(5).iterrows():
    print(f"  {s['street_name']}: EFH={s.get('sfh_detached_count',0)} RH={s.get('sfh_rowhouse_count',0)} MFH={s.get('mfh_count',0)} total={s['building_count_total']} sfh_ratio={s['sfh_total_ratio']:.0%}")

print("\n=== Test 5: Suburban Segment Regression Check (PLZ41472) ===")
sr = pd.read_parquet('data/layer2/street_ranking_v1.parquet')
r41472 = sr[sr['street_id']=='NEUSS_PLZ41472']
print(f"PLZ41472 rank: {int(r41472['rank'].iloc[0])}")
print(f"PLZ41472 final_score: {float(r41472['final_score'].iloc[0]):.4f}")

seg_streets = f8[f8['segment_id']=='NEUSS_PLZ41472']
total_sfh = seg_streets['sfh_total_count'].sum()
total_bld = seg_streets['building_count_total'].sum()
print(f"PLZ41472 street-level SFH ratio: {total_sfh}/{total_bld} = {total_sfh/total_bld:.0%}")
