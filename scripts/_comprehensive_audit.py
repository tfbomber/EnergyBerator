"""
Comprehensive data integrity audit across the full D-ESS pipeline.
Goal: Find issues SIMILAR to the SFH misclassification — where data processing
leads to results that an installer would immediately question.

Dimensions checked:
  1. Building count plausibility (garage/shed inflation)
  2. PV market_gap plausibility at segment level
  3. L2 vs Foundation SFH divergence
  4. Street-level anomalies (duplicate streets, extreme values)
  5. Ranking consistency (do segment labels match rankings?)
  6. ROI input sanity
"""
import json
import pandas as pd
import numpy as np

BASE = "d:/Stock Analysis/D-Energy Berater/d-ess-engine"

# Load all data sources
f8 = pd.read_parquet(f'{BASE}/data/layer2/street_level_ranking_v1.parquet')
l2 = pd.read_parquet(f'{BASE}/data/layer2/layer2_mvp_input_table.parquet')
f7 = pd.read_parquet(f'{BASE}/data/layer2/street_ranking_v1.parquet')

with open(f'{BASE}/output/foundation/foundation_structure_results.json', encoding='utf-8') as f:
    foundation = json.load(f)

print("=" * 70)
print("DIMENSION 1: Building Count Plausibility")
print("=" * 70)
# Check for streets with suspiciously high building counts that could indicate
# garage/shed inflation (building=yes without subtype gets rescued as SFH)
high_count = f8[f8['building_count_total'] >= 50].sort_values('building_count_total', ascending=False)
print(f"Streets with >= 50 buildings: {len(high_count)}")
print(f"\nTop 10 highest building count streets:")
for _, s in high_count.head(10).iterrows():
    print(f"  {s['street_name']} ({s['segment_id']}): "
          f"total={s['building_count_total']} "
          f"sfh={s['sfh_total_count']} mfh={s['mfh_count']} "
          f"other={s['building_count_total']-s['sfh_total_count']-s['mfh_count']} "
          f"sfh_ratio={s['sfh_total_ratio']:.0%}")

# Check for streets where "other" (unclassified) buildings are very high
# These are buildings that couldn't be classified — if they dominate, the SFH ratio is unreliable
print(f"\n--- Streets with high 'other' (unclassified) ratio ---")
f8['other_count'] = f8['building_count_total'] - f8['sfh_total_count'] - f8['mfh_count']
f8['other_ratio'] = f8['other_count'] / f8['building_count_total'].clip(lower=1)
high_other = f8[(f8['other_ratio'] > 0.50) & (f8['building_count_total'] >= 10)]
print(f"Streets with >50% unclassified AND >=10 buildings: {len(high_other)}")
for _, s in high_other.head(5).iterrows():
    print(f"  {s['street_name']} ({s['segment_id']}): total={s['building_count_total']} "
          f"other={s['other_count']} ({s['other_ratio']:.0%})")

print("\n" + "=" * 70)
print("DIMENSION 2: PV Market Gap Plausibility")
print("=" * 70)
# PV data is at PLZ level. Check if all streets in a segment share the exact same pv_oppty
# AND whether the values seem plausible
l2_usable = l2[l2['row_usable_for_ranking']==True]
print("Segment PV data:")
for _, r in l2_usable.iterrows():
    pv = r.get('pv_coverage_score', np.nan)
    gap = 1 - pv if pd.notna(pv) else np.nan
    print(f"  {r['unit_id']}: pv_coverage={pv:.4f} market_gap={gap:.4f}" if pd.notna(pv) else
          f"  {r['unit_id']}: pv_coverage=NaN")

# Check if PV data varies meaningfully across segments or is too uniform
pv_vals = l2_usable['pv_coverage_score'].dropna()
pv_range = pv_vals.max() - pv_vals.min()
print(f"\nPV coverage range: {pv_vals.min():.4f} to {pv_vals.max():.4f} (spread={pv_range:.4f})")
if pv_range < 0.10:
    print("  WARNING: PV data has very low variance — may not differentiate segments meaningfully")

print("\n" + "=" * 70)
print("DIMENSION 3: L2 vs Foundation SFH Divergence")
print("=" * 70)
# Compare L2's sfh_friendly_share with Foundation's aggregate SFH ratio
# Large divergence = one of the classifiers is wrong
for _, r in l2_usable.iterrows():
    seg = r['unit_id']
    l2_sfh = r.get('sfh_friendly_share', np.nan)
    # Get Foundation's aggregate for this segment
    plz = seg.replace('NEUSS_PLZ', '')
    seg_clusters = [c for c in foundation if str(c.get('plz','')) == plz]
    if seg_clusters:
        f_sfh_ratios = [c.get('sfh_total_ratio', 0) for c in seg_clusters]
        f_mean = np.mean(f_sfh_ratios)
        f_pass = sum(1 for c in seg_clusters if c.get('structure_gate')=='PASS') / len(seg_clusters)
        delta = abs(l2_sfh - f_mean) if pd.notna(l2_sfh) else np.nan
        flag = "DIVERGENT" if pd.notna(delta) and delta > 0.30 else ""
        print(f"  {seg}: L2_sfh={l2_sfh:.2f} Foundation_mean_sfh={f_mean:.2f} "
              f"delta={delta:.2f} PASS_rate={f_pass:.0%} {flag}")
    else:
        print(f"  {seg}: L2_sfh={l2_sfh:.2f} Foundation=NO_DATA")

print("\n" + "=" * 70)
print("DIMENSION 4: Street-Level Anomalies")
print("=" * 70)

# 4a. Duplicate street names within same segment (user confusion)
dupes = f8.groupby(['segment_id', 'street_name']).size().reset_index(name='count')
dupes = dupes[dupes['count'] > 1]
print(f"Duplicate street names within same segment: {len(dupes)}")
if len(dupes) > 0:
    for _, d in dupes.head(10).iterrows():
        print(f"  {d['street_name']} in {d['segment_id']}: appears {d['count']}x")

# 4b. Streets with 100% SFH in urban segments (suspicious after fix)
print(f"\n--- Streets with 100% SFH in low-ranking segments (rank >= 6) ---")
suspect = f8[(f8['sfh_total_ratio'] >= 0.99) & (f8['segment_rank'] >= 6) & (f8['building_count_total'] >= 10)]
print(f"Count: {len(suspect)}")
for _, s in suspect.head(5).iterrows():
    print(f"  {s['street_name']} ({s['segment_id']} rank#{s['segment_rank']}): "
          f"sfh={s['sfh_total_ratio']:.0%} n={s['building_count_total']} gate={s['structure_gate']}")

# 4c. Very small streets (< 5 buildings) that got PASS
tiny_pass = f8[(f8['building_count_total'] < 5) & (f8['structure_gate'] == 'PASS')]
print(f"\n--- PASS streets with < 5 buildings: {len(tiny_pass)} ---")
for _, s in tiny_pass.head(5).iterrows():
    print(f"  {s['street_name']} ({s['segment_id']}): n={s['building_count_total']} sfh_ratio={s['sfh_total_ratio']:.0%}")

print("\n" + "=" * 70)
print("DIMENSION 5: Ranking vs Label Consistency")
print("=" * 70)
# Check that segment labels match their actual characteristics
# E.g., a segment labeled "DEPLOYABLE" should rank reasonably high
for _, r in f7.iterrows():
    seg = r['street_id']
    rank = int(r['rank'])
    l2_row = l2[l2['unit_id']==seg]
    if len(l2_row) > 0:
        gate = l2_row.iloc[0].get('l1_gate_label', 'N/A')
        sfh = l2_row.iloc[0].get('sfh_friendly_share', np.nan)
        seg_streets = f8[f8['segment_id']==seg]
        pass_pct = (seg_streets['structure_gate']=='PASS').mean() * 100
        print(f"  Rank #{rank} {seg}: gate={gate} l2_sfh={sfh:.2f} street_PASS={pass_pct:.0f}%")

print("\n" + "=" * 70)
print("DIMENSION 6: Extreme Score Gaps")
print("=" * 70)
# Check if any street has a very high raw score but very low adjusted score (or vice versa)
# This would indicate the segment modifier is dominating in a way that might surprise users
f8['modifier_impact'] = f8['adjusted_street_score'] / f8['street_score'].clip(lower=0.001)
extreme_mod = f8[(f8['modifier_impact'] < 0.50) | (f8['modifier_impact'] > 1.50)]
print(f"Streets where segment modifier changes score by >50%: {len(extreme_mod)}")
# Check by segment
for seg in f8['segment_id'].unique():
    seg_df = f8[f8['segment_id']==seg]
    avg_impact = seg_df['modifier_impact'].mean()
    if abs(avg_impact - 1.0) > 0.15:
        print(f"  {seg}: avg modifier impact = {avg_impact:.3f} (>{'+' if avg_impact>1 else ''}{(avg_impact-1)*100:.0f}%)")
