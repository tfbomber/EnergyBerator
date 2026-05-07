"""
Pre-plan diagnostic: What would PV adoption rates look like
if we use Foundation's building counts as denominator?
"""
import json
import pandas as pd

BASE = "d:/Stock Analysis/D-Energy Berater/d-ess-engine"

# Foundation building counts per PLZ
with open(f'{BASE}/output/foundation/foundation_structure_results.json', encoding='utf-8') as f:
    foundation = json.load(f)

plz_foundation_counts = {}
for c in foundation:
    plz = str(c.get('plz', ''))
    n = c.get('building_count_total', 0)
    if plz not in plz_foundation_counts:
        plz_foundation_counts[plz] = {'total_buildings': 0, 'clusters': 0}
    plz_foundation_counts[plz]['total_buildings'] += n
    plz_foundation_counts[plz]['clusters'] += 1

# Deduplicated Foundation counts (street-level, not cluster-level)
# Since duplicates share the same count, we need to dedup first
plz_dedup_counts = {}
seen = set()
for c in foundation:
    plz = str(c.get('plz', ''))
    street = c.get('street_name', '')
    key = (plz, street)
    if key in seen:
        continue
    seen.add(key)
    n = c.get('building_count_total', 0)
    plz_dedup_counts[plz] = plz_dedup_counts.get(plz, 0) + n

# Current buildings.parquet counts
bld = pd.read_parquet(f'{BASE}/data/buildings.parquet', columns=['segment_id'])
bld_counts = bld['segment_id'].value_counts().to_dict()
plz_bld = {}
for seg, cnt in bld_counts.items():
    plz = str(seg).replace('NEUSS_PLZ', '')
    plz_bld[plz] = cnt

# MaStR PV counts
try:
    mastr = pd.read_parquet(f'{BASE}/data/sources/mastr/mastr_pv_adoption_neuss.parquet')
    pv_counts = dict(zip(mastr['plz'].astype(str), mastr['pv_installation_count']))
except:
    pv_counts = {}

# Compare
print("=" * 90)
print("PV ADOPTION RATE: Current vs Proposed (Foundation denominator)")
print("=" * 90)
print(f"{'PLZ':<8} {'MaStR':>6} {'bld.pq':>7} {'Fdn(raw)':>9} {'Fdn(dd)':>8} "
      f"{'Rate_NOW':>9} {'Rate_NEW':>9} {'Delta':>7}")
print("-" * 90)

for plz in sorted(['41460','41462','41464','41466','41468','41469','41470','41472']):
    pv = pv_counts.get(plz, 0)
    bld_n = plz_bld.get(plz, 0)
    fdn_raw = plz_foundation_counts.get(plz, {}).get('total_buildings', 0)
    fdn_dd = plz_dedup_counts.get(plz, 0)

    rate_now = pv / bld_n if bld_n > 0 else 0
    rate_new = pv / fdn_dd if fdn_dd > 0 else 0

    delta = rate_new - rate_now
    flag = " !!!" if abs(delta) > 0.15 else ""

    print(f"{plz:<8} {pv:>6} {bld_n:>7} {fdn_raw:>9} {fdn_dd:>8} "
          f"{rate_now:>8.1%} {rate_new:>8.1%} {delta:>+6.1%}{flag}")

print()
print("Legend:")
print("  bld.pq    = buildings.parquet row count (current denominator)")
print("  Fdn(raw)  = Foundation total (sum of all clusters, includes duplicates)")
print("  Fdn(dd)   = Foundation total (deduplicated by street name)")
print("  Rate_NOW  = current adoption rate using bld.pq")
print("  Rate_NEW  = proposed adoption rate using Fdn(dd)")

# Also check: how many duplicate clusters exist per PLZ?
print("\n" + "=" * 90)
print("DUPLICATE CLUSTER ANALYSIS")
print("=" * 90)
dup_analysis = {}
for c in foundation:
    plz = str(c.get('plz', ''))
    street = c.get('street_name', '')
    key = (plz, street)
    dup_analysis.setdefault(plz, {'total_clusters': 0, 'unique_streets': set()})
    dup_analysis[plz]['total_clusters'] += 1
    dup_analysis[plz]['unique_streets'].add(street)

for plz in sorted(dup_analysis.keys()):
    d = dup_analysis[plz]
    total = d['total_clusters']
    unique = len(d['unique_streets'])
    dups = total - unique
    print(f"  PLZ {plz}: {total} clusters, {unique} unique streets, {dups} duplicates ({dups/total*100:.0f}%)")
