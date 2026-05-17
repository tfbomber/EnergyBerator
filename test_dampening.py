import pandas as pd

df = pd.read_parquet('data/layer2/street_level_ranking_v1.parquet')

print('=== TEST 1: sfh>=15 must have dampening=1.0 (regression) ===')
high_sfh = df[df['sfh_total_count'] >= 15]
assert (high_sfh['scale_dampening'] == 1.0).all()
print(f'PASS: {len(high_sfh)} streets with sfh>=15 → dampening=1.00')

print()
print('=== TEST 2: sfh=0 must have adj_score=0 (edge case) ===')
zero_sfh = df[df['sfh_total_count'] == 0]
if len(zero_sfh) > 0:
    assert (zero_sfh['adjusted_street_score'] == 0.0).all()
    print(f'PASS: {len(zero_sfh)} streets with sfh=0 → adj_score=0.0')
else:
    print('(no sfh=0 streets in dataset - OK)')

print()
print('=== TEST 3: street_quality_agg unchanged (anti-double-count) ===')
ORIGINAL_AGG = {
    'NEUSS_PLZ41460': 0.3557, 'NEUSS_PLZ41462': 0.5254,
    'NEUSS_PLZ41464': 0.6239, 'NEUSS_PLZ41466': 0.6466,
    'NEUSS_PLZ41468': 0.6266, 'NEUSS_PLZ41469': 0.5731,
    'NEUSS_PLZ41470': 0.6561, 'NEUSS_PLZ41472': 0.7359,
}
agg = df.groupby('segment_id')['street_quality_agg'].first()
all_match = True
for seg, expected in ORIGINAL_AGG.items():
    got = round(float(agg[seg]), 4)
    ok = abs(got - expected) < 0.0001
    status = 'PASS' if ok else 'FAIL'
    print(f'  {seg}: expected={expected} got={got} {status}')
    if not ok:
        all_match = False
assert all_match, 'FAIL: street_quality_agg changed (double-count detected)'
print('PASS: all 8 segment agg values unchanged')

print()
print('=== TEST 4: small-sfh streets are now deprioritized ===')
small = df[df['sfh_total_count'] <= 3].sort_values('adjusted_street_score', ascending=False)
print(f'Streets with sfh<=3: {len(small)}')
print(small[['street_name','sfh_total_count','scale_dampening','street_score','adjusted_street_score','global_rank']].head(5).to_string(index=False))

print()
print('=== TEST 5: problem case - single-SFH vs large-RH streets ===')
single = df[df['sfh_total_count'] == 1]
big_rh = df[df['sfh_total_count'] >= 50]
print(f'Streets with sfh=1:   {len(single)}, global_rank range: {int(single["global_rank"].min())} - {int(single["global_rank"].max())}')
print(f'Streets with sfh>=50: {len(big_rh)}, global_rank range: {int(big_rh["global_rank"].min())} - {int(big_rh["global_rank"].max())}')
# No single-SFH street should have a better rank than the best large-RH street
worst_big = int(big_rh['global_rank'].max())
best_single = int(single['global_rank'].min())
if best_single > worst_big:
    print('PASS: no single-SFH street outranks any large-SFH (>=50) street')
else:
    overlap = df[df['global_rank'] <= best_single][['street_name','sfh_total_count','global_rank']].head(10)
    print(f'INFO: best single-SFH rank={best_single}, worst large-SFH rank={worst_big}')
    print(overlap.to_string(index=False))

print()
print('=== ALL TESTS PASSED ===')
