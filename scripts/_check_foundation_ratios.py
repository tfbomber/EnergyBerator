import json

with open('output/foundation/foundation_structure_results.json', encoding='utf-8') as f:
    data = json.load(f)

clusters = []
if isinstance(data, dict):
    for v in data.values():
        if isinstance(v, list):
            clusters.extend(v)
elif isinstance(data, list):
    clusters = data

print("=== Foundation JSON: sfh_total_ratio denominator check ===")
print(f"Total clusters: {len(clusters)}")
print()

for c in clusters[:10]:
    name = c.get('street_name', '?')
    plz = c.get('plz', '?')
    sfh_total = int(c.get('sfh_total_count', 0) or 0)
    bldg_total = int(c.get('building_count_total', 0) or 0)
    sfh_ratio = float(c.get('sfh_total_ratio', 0) or 0)
    mfh_count = int(c.get('mfh_count', 0) or 0)
    mfh_ratio = float(c.get('mfh_ratio', 0) or 0)
    
    if bldg_total > 0:
        computed_sfh = sfh_total / bldg_total
        computed_mfh = mfh_count / bldg_total
        sfh_match = abs(computed_sfh - sfh_ratio) < 0.02
        mfh_match = abs(computed_mfh - mfh_ratio) < 0.02
    else:
        computed_sfh = 0
        computed_mfh = 0
        sfh_match = True
        mfh_match = True

    unaccounted = bldg_total - sfh_total - mfh_count
    flag = "OK" if sfh_match and mfh_match else "MISMATCH"
    print(f"[{flag}] {name} ({plz})")
    print(f"  sfh={sfh_total}/{bldg_total} stored_ratio={sfh_ratio:.3f} computed={computed_sfh:.3f}")
    print(f"  mfh={mfh_count}/{bldg_total} stored_ratio={mfh_ratio:.3f} computed={computed_mfh:.3f}")
    print(f"  unaccounted={unaccounted} ({unaccounted/max(bldg_total,1):.0%})")
    print()

# Summary: aggregate by PLZ
print("=== PLZ-level aggregate check ===")
from collections import defaultdict
plz_agg = defaultdict(lambda: {'sfh': 0, 'mfh': 0, 'total': 0})
for c in clusters:
    plz = str(c.get('plz', ''))
    plz_agg[plz]['sfh'] += int(c.get('sfh_total_count', 0) or 0)
    plz_agg[plz]['mfh'] += int(c.get('mfh_count', 0) or 0)
    plz_agg[plz]['total'] += int(c.get('building_count_total', 0) or 0)

for plz in sorted(plz_agg):
    a = plz_agg[plz]
    unaccounted = a['total'] - a['sfh'] - a['mfh']
    print(f"PLZ {plz}: sfh={a['sfh']:,} mfh={a['mfh']:,} total={a['total']:,} unaccounted={unaccounted:,} ({unaccounted/max(a['total'],1):.0%})")
