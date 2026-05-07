import pandas as pd
f8 = pd.read_parquet('data/layer2/street_level_ranking_v1.parquet')

print('=== Test 1: PLZ41460 ===')
seg = f8[f8['segment_id']=='NEUSS_PLZ41460']
pass_streets = seg[seg['structure_gate'].isin(['PASS','QUALIFIED'])]
capped = seg[seg['coherence_capped']==True]
print(f'PASS/QUALIFIED streets: {len(pass_streets)}')
print(f'coherence-capped streets: {len(capped)}')

print('\n=== Test 2: Other segments ===')
for seg_id in ['NEUSS_PLZ41472','NEUSS_PLZ41468','NEUSS_PLZ41466','NEUSS_PLZ41470','NEUSS_PLZ41464']:
    seg = f8[f8['segment_id']==seg_id]
    capped_count = (seg['coherence_capped']==True).sum()
    print(f'{seg_id}: capped={capped_count}')

print('\n=== Test 3: Sternstrasse Audit ===')
stern = f8[f8['street_name'].str.contains('Stern', na=False) & (f8['segment_id']=='NEUSS_PLZ41460')]
for _, s in stern.iterrows():
    print(f"{s['street_name']}: gate={s['structure_gate']} original={s['structure_gate_original']} capped={s['coherence_capped']} reason='{s['top_reason']}'")
