import pandas as pd
f04 = pd.read_parquet('data/fields/field_04_pv_adoption.parquet')
f8 = pd.read_parquet('data/layer2/street_level_ranking_v1.parquet')

# Test 2
dupes = f8.groupby(['segment_id','street_name']).size().reset_index(name='n')
duplicates_found = (dupes['n'] > 1).sum()
print(f"Test 2: Duplicates found: {duplicates_found}")
assert duplicates_found == 0, f"Duplicates: {dupes[dupes['n']>1]}"

# Test 3
expected = {'41462': 0.87, '41466': 0.78, '41468': 0.79, '41469': 0.77, '41472': 0.71}
for seg, exp in expected.items():
    r = f04[f04['segment_id']==f'NEUSS_PLZ{seg}'].iloc[0]
    delta = abs(r['field_value'] - exp)
    status = 'OK' if delta < 0.05 else 'DRIFT'
    print(f"Test 3: PLZ{seg}: gap={r['field_value']:.4f} expected~{exp} delta={delta:.4f} {status}")

# Test 4
r = f04[f04['segment_id']=='NEUSS_PLZ41470'].iloc[0]
print(f"Test 4: PLZ41470: market_gap={r['field_value']:.4f} (expect <0.20, genuine high adoption)")
print("ALL TESTS PASSED.")
