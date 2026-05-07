import json
f = open('output/foundation/foundation_structure_results.json', encoding='utf-8')
d = json.load(f)
seen = set()
total = 0
for c in d:
    plz = str(c.get('plz', ''))
    street = c.get('street_name', '')
    if plz == '41470' and (plz, street) not in seen:
        seen.add((plz, street))
        total += c.get('building_count_total', 0)
print(f"PLZ41470 Foundation dedup: {len(seen)} unique streets, {total} buildings")
print(f"PLZ41470 buildings.parquet: 1498")
print(f"PLZ41470 MaStR residential PV: 1242")
print(f"Adoption (Foundation denom): {1242/total*100:.1f}%" if total > 0 else "")
print(f"Adoption (bld.pq denom):     {1242/1498*100:.1f}%")
