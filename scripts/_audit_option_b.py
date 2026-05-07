"""
Deep audit of Option B coherence guard implementation.
Checks:
  A. B_NEUTRAL fallback — is l1_gate_label missing from the neutral dict? (edge case for segments without L2 data)
  B. Score consistency — do capped streets have gate_score == 0.40 (REVIEW value)?
  C. PLZ41460 street_quality_agg — did it drop correctly vs previous run?
  D. Am Alten Weiher (the other PASS street) — is it also capped?
  E. Rank integrity — PLZ41460 is still #8 (no ranking reversal side-effect)?
  F. No new columns broke existing column consumers (parquet schema check)
"""
import pandas as pd

PARQUET = 'data/layer2/street_level_ranking_v1.parquet'
f8 = pd.read_parquet(PARQUET)

print("=" * 65)
print("AUDIT A: B_NEUTRAL fallback — segments missing from L2 data")
print("=" * 65)
# If a segment falls back to B_NEUTRAL (no L2 data), l1_gate_label key is absent from B_NEUTRAL.
# b.get("l1_gate_label") returns None → seg_blocked = (None == "BLOCKED") = False → gate_override=None
# This is CORRECT — no B_NEUTRAL segment should be blocked. Verify no unexpected capping.
unknown_segs = f8[f8['segment_id']=='UNKNOWN']
print(f"Rows with segment_id=UNKNOWN: {len(unknown_segs)}  (should be 0)")
capped_non_41460 = f8[(f8['coherence_capped']==True) & (f8['segment_id']!='NEUSS_PLZ41460')]
print(f"Capped rows outside PLZ41460: {len(capped_non_41460)}  (should be 0)")

print("\n" + "=" * 65)
print("AUDIT B: gate_score consistency for capped streets")
print("=" * 65)
capped = f8[f8['coherence_capped']==True]
print(f"Total capped streets: {len(capped)}")
# REVIEW gate_score = 0.40 (from GATE_SCORE dict)
for _, s in capped.iterrows():
    gate_s_ok = abs(s['gate_score'] - 0.40) < 0.001
    print(f"  {s['street_name']}: gate_score={s['gate_score']:.2f} (expect 0.40) -> {'OK' if gate_s_ok else 'FAIL'}")

print("\n" + "=" * 65)
print("AUDIT C: PLZ41460 street_quality_agg change")
print("=" * 65)
# Before: 0.3566 (all 3 streets PASS)
# After: should be lower (capped streets get gate_score=0.40 vs 1.00)
seg41460 = f8[f8['segment_id']=='NEUSS_PLZ41460']
agg_val = seg41460['street_quality_agg'].iloc[0] if len(seg41460) > 0 else None
print(f"PLZ41460 street_quality_agg: {agg_val:.4f}  (was 0.3566 before, should be lower now)")
print(f"Direction: {'LOWER -> CORRECT' if agg_val is not None and agg_val < 0.3566 else 'NOT LOWER -> CHECK'}")

print("\n" + "=" * 65)
print("AUDIT D: Am Alten Weiher — also capped?")
print("=" * 65)
weiher = f8[f8['street_name'].str.contains('Alten Weiher', na=False)]
for _, s in weiher.iterrows():
    print(f"  {s['street_name']}: gate={s['structure_gate']} original={s['structure_gate_original']} capped={s['coherence_capped']}")

print("\n" + "=" * 65)
print("AUDIT E: Segment ranking integrity (PLZ41460 still last)")
print("=" * 65)
seg_ranks = f8.groupby('segment_id')['segment_rank'].first().sort_values()
for seg, rank in seg_ranks.items():
    marker = " <- expect #8 (last)" if seg == 'NEUSS_PLZ41460' else ""
    print(f"  #{rank}  {seg}{marker}")

print("\n" + "=" * 65)
print("AUDIT F: Parquet schema — all expected columns present")
print("=" * 65)
required_cols = [
    'structure_gate', 'structure_gate_original', 'coherence_capped',
    'gate_score', 'street_score', 'adjusted_street_score',
    'segment_rank', 'global_rank', 'rank_in_segment',
    'sfh_total_ratio', 'building_count_total', 'top_reason',
]
for col in required_cols:
    present = col in f8.columns
    print(f"  {col}: {'OK' if present else 'MISSING'}")

print(f"\nTotal columns in parquet: {len(f8.columns)}")
print(f"Total rows: {len(f8)}")
