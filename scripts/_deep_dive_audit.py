"""
Deep-dive into the most concerning findings from the comprehensive audit.
"""
import pandas as pd
import numpy as np

BASE = "d:/Stock Analysis/D-Energy Berater/d-ess-engine"
f8 = pd.read_parquet(f'{BASE}/data/layer2/street_level_ranking_v1.parquet')
l2 = pd.read_parquet(f'{BASE}/data/layer2/layer2_mvp_input_table.parquet')

print("=" * 70)
print("DEEP DIVE A: Duplicate Streets — Are They Identical or Different Clusters?")
print("=" * 70)
# Check if duplicates have same data or different address ranges
dupes_names = f8.groupby(['segment_id','street_name']).filter(lambda x: len(x) > 1)
sample_streets = dupes_names.groupby(['segment_id','street_name']).first().head(5).reset_index()
for _, row in sample_streets.iterrows():
    st = row['street_name']
    seg = row['segment_id']
    entries = f8[(f8['street_name']==st) & (f8['segment_id']==seg)]
    print(f"\n  {st} in {seg}: {len(entries)} entries")
    for _, e in entries.iterrows():
        addr = e.get('address_range', '')
        cid = e.get('cluster_id', '')
        print(f"    cluster={cid} addr_range='{addr}' n={e['building_count_total']} "
              f"sfh={e['sfh_total_ratio']:.0%} gate={e['structure_gate']}")

print("\n" + "=" * 70)
print("DEEP DIVE B: PV Market Gap — PLZ41470 vs PLZ41464 anomaly")
print("=" * 70)
# PLZ41470: pv_coverage=0.1595 (very low — 84% market gap)
# PLZ41464: pv_coverage=0.1907 (very low — 81% market gap)
# These are suburban areas. Is 16-19% PV coverage realistic?
# Compare with urban PLZ41460: pv_coverage=0.8140 (81% covered)
# This means: Innenstadt has 4x more PV coverage than suburbs??
# That's counter-intuitive. Suburban houses are MORE likely to have solar.
print("PV coverage comparison:")
for _, r in l2[l2['row_usable_for_ranking']==True].sort_values('pv_coverage_score').iterrows():
    pv = r.get('pv_coverage_score', np.nan)
    sfh = r.get('sfh_friendly_share', np.nan)
    print(f"  {r['unit_id']}: pv_coverage={pv:.4f} sfh={sfh:.2f}")
print()
print("QUESTION: Is it plausible that PLZ41460 (Innenstadt) has 81% PV coverage")
print("          while PLZ41470 (Allerheiligen/suburb) has only 16%?")
print("          This seems INVERTED — suburbs should have MORE solar, not less.")
print()
# Check: what is pv_coverage_score actually measuring?
# From knowledge: field_04 = market_gap = 1 - pv_adoption_rate
# So pv_coverage_score = market_gap
# PLZ41460: market_gap=0.814 means only 18.6% adoption — LOTS of room
# PLZ41470: market_gap=0.1595 means 84% adoption — nearly saturated
# Wait, that's the OPPOSITE of what I thought!
print("CORRECTION: pv_coverage_score IS market_gap (not coverage).")
print("  PLZ41460: gap=0.81 -> 19% PV adoption (makes sense for city center)")
print("  PLZ41470: gap=0.16 -> 84% PV adoption (this is suspicious for suburb!)")
print("  PLZ41462: gap=0.87 -> 13% PV adoption")
print()
print("POTENTIAL ISSUE: PLZ41470 shows 84% PV adoption — is this realistic?")
print("If MaStR has large commercial installations in this PLZ, it would inflate the rate.")

print("\n" + "=" * 70)
print("DEEP DIVE C: L2 sfh_friendly_share vs Foundation — PLZ41470/41464")
print("=" * 70)
# These two segments show massive L2 vs Foundation divergence
# L2 says 15% SFH, Foundation says 59% mean SFH
# What drives L2's sfh_friendly_share?
print("L2 sfh_friendly_share source check:")
for seg in ['NEUSS_PLZ41470', 'NEUSS_PLZ41464']:
    r = l2[l2['unit_id']==seg]
    if len(r) > 0:
        r = r.iloc[0]
        print(f"\n  {seg}:")
        print(f"    sfh_friendly_share = {r.get('sfh_friendly_share', 'N/A')}")
        # sfh_friendly_share comes from buildings.parquet (field_02)
        # Let's check if buildings.parquet exists and what it says
        try:
            bld = pd.read_parquet(f'{BASE}/data/buildings.parquet')
            seg_bld = bld[bld['segment_id']==seg]
            print(f"    buildings.parquet count: {len(seg_bld)}")
            if len(seg_bld) > 0:
                print(f"    building_type distribution:")
                print(seg_bld['building_type'].value_counts().to_string())
        except Exception as e:
            print(f"    buildings.parquet error: {e}")

print("\n" + "=" * 70)
print("DEEP DIVE D: Segment Modifier Impact on PLZ41470/41464")
print("=" * 70)
# These segments lose 43% of their score from modifiers
# Check what's driving the penalty
for seg in ['NEUSS_PLZ41470', 'NEUSS_PLZ41464']:
    seg_streets = f8[f8['segment_id']==seg]
    if len(seg_streets) > 0:
        s = seg_streets.iloc[0]
        print(f"\n  {seg}:")
        print(f"    fern_modifier   = {s['segment_fern_modifier']:.3f}")
        print(f"    hp_modifier     = {s['segment_hp_modifier']:.3f}")
        print(f"    certainty       = {s['segment_certainty']:.3f}")
        print(f"    combined        = {s['segment_combined_modifier']:.3f}")
        print(f"    -> Score reduced by {(1-s['segment_combined_modifier'])*100:.0f}%")
        print(f"    truly_uncertain = {s['seg_truly_uncertain_share']:.0%}")

print("\n" + "=" * 70)
print("DEEP DIVE E: How pv_oppty is used in field_08 scoring")
print("=" * 70)
# Check if the PV anomaly actually matters for the ranking
# pv_oppty weight is only 0.10 — might not move the needle much
for seg in f8['segment_id'].unique():
    seg_df = f8[f8['segment_id']==seg]
    s = seg_df.iloc[0]
    pv_contrib = s['pv_oppty_score']  # already weighted by W_PV_OPPTY=0.10
    avg_score = seg_df['street_score'].mean()
    print(f"  {seg}: pv_contrib={pv_contrib:.4f} avg_street_score={avg_score:.4f} "
          f"pv_as_%_of_score={pv_contrib/avg_score*100:.1f}%")
