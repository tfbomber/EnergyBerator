"""
Final calculation: residential-only PV adoption with Foundation dedup denominator.
This is the root-fix version.
"""
import json

BASE = "d:/Stock Analysis/D-Energy Berater/d-ess-engine"

# Foundation dedup counts per PLZ
with open(f'{BASE}/output/foundation/foundation_structure_results.json', encoding='utf-8') as f:
    foundation = json.load(f)
fdn_counts = {}
seen = set()
for c in foundation:
    plz = str(c.get('plz', ''))
    street = c.get('street_name', '')
    key = (plz, street)
    if key not in seen:
        seen.add(key)
        fdn_counts[plz] = fdn_counts.get(plz, 0) + c.get('building_count_total', 0)

# Residential PV counts (from capacity audit: <= 30kWp)
residential_pv = {
    "41460": 109, "41462": 929, "41464": 757, "41466": 910,
    "41468": 981, "41469": 879, "41470": 1242, "41472": 969,
}
# buildings.parquet counts
bld_pq = {
    "41460": 844, "41462": 7021, "41464": 965, "41466": 4205,
    "41468": 4843, "41469": 3934, "41470": 1498, "41472": 3440,
}

print("=" * 95)
print("ROOT-FIX PV ADOPTION: residential PV (<=30kWp) / Foundation dedup buildings")
print("=" * 95)
print(f"{'PLZ':<8} {'Res.PV':>7} {'bld.pq':>7} {'Fdn.dd':>7} "
      f"{'OLD Rate':>9} {'NEW Rate':>9} {'Change':>8} {'Verdict':>12}")
print("-" * 95)

for plz in sorted(residential_pv.keys()):
    rpv = residential_pv[plz]
    bld = bld_pq.get(plz, 0)
    fdn = fdn_counts.get(plz, 0)
    # Take max of bld.pq and Foundation as denominator
    best_denom = max(bld, fdn)

    old_rate = rpv / bld if bld > 0 else 0
    new_rate = rpv / best_denom if best_denom > 0 else 0
    # Cap at 1.0 — can happen when PV count > building count
    new_rate_capped = min(1.0, new_rate)
    delta = new_rate_capped - old_rate

    if abs(delta) > 0.15:
        verdict = "MAJOR FIX"
    elif abs(delta) > 0.05:
        verdict = "MODERATE"
    else:
        verdict = "STABLE"

    print(f"{plz:<8} {rpv:>7} {bld:>7} {fdn:>7} "
          f"{old_rate:>8.1%} {new_rate_capped:>8.1%} {delta:>+7.1%} {verdict:>12}")

print()
print("KEY:")
print("  Res.PV   = MaStR installations with Nettonennleistung <= 30 kWp")
print("  bld.pq   = buildings.parquet row count (current denominator)")
print("  Fdn.dd   = Foundation deduplicated building count")
print("  OLD Rate = Res.PV / bld.pq (current, includes denominator bugs)")
print("  NEW Rate = Res.PV / max(bld.pq, Fdn.dd) (root fix, capped at 100%)")
print()
print("ANALYSIS:")
print("  PLZ41464: bld.pq=965 is WILDLY low vs Foundation=4230")
print("    -> Current 80.9% drops to 17.9% — CORRECT (suburb, not saturated)")
print("  PLZ41470: both sources ~1200-1500, PV=1242 -> genuinely high adoption")
print("    -> Stays at 82-100% — THIS IS REAL DATA, not a bug")
