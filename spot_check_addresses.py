"""
spot_check_addresses.py
=======================
Deep quality check: for each sampled cluster, verify that
cluster_building_count is plausible given the address range.

Logic: a house range "A - B" spans (B - A + 1) potential numbers.
For German streets with sub-addresses (1a/1b, etc.), the actual
building count can exceed the numeric span. The check flags cases
where cluster_building_count > 3x the numeric range span (likely
range misalignment) or where count is 0 despite a parseable range.
"""
import json, re, sys
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\Stock Analysis\D-Energy Berater\d-ess-engine"

with open(BASE + r"\output\foundation\foundation_structure_results.json", encoding="utf-8") as f:
    fnd = json.load(f)

def parse_range(s):
    nums = re.findall(r"\d+", str(s))
    if len(nums) >= 2:
        return int(nums[0]), int(nums[-1])
    return None, None

def span(lo, hi):
    if lo is None or hi is None:
        return None
    return hi - lo + 1

def flag(r):
    """Return a flag string if something looks suspicious."""
    rng = r.get("address_range", "")
    lo, hi = parse_range(rng)
    cc = r.get("cluster_building_count")
    tot = r.get("building_count_total", 0)
    s = span(lo, hi)

    flags = []
    if cc is not None and s is not None:
        # German streets typically have <=3 sub-units per number
        # so cluster_count > 4 * span is suspicious
        if cc > 4 * s:
            flags.append(f"COUNT_TOO_HIGH_FOR_RANGE (cc={cc} > 4×span={4*s})")
        if cc == 0 and s > 0:
            flags.append("COUNT_ZERO_WITH_VALID_RANGE")
    if cc is not None and tot > 0 and cc > tot:
        flags.append(f"CLUSTER_EXCEEDS_TOTAL ({cc}>{tot})")
    return flags

# ── Sample selection: diverse categories ────────────────────────────────────
# 1. Full-street (ratio=1.0)
full_street = [r for r in fnd
               if r.get("cluster_building_count") == r.get("building_count_total")
               and r["building_count_total"] > 10][:5]

# 2. Multi-cluster streets (ratio < 0.7)
partial = [r for r in fnd
           if r.get("cluster_building_count") is not None
           and r["building_count_total"] > 0
           and r["cluster_building_count"] / r["building_count_total"] < 0.7
           and r["building_count_total"] > 20][:8]

# 3. Narrow address range (span <= 10 house numbers)
narrow = []
for r in fnd:
    rng = r.get("address_range", "")
    lo, hi = parse_range(rng)
    s = span(lo, hi)
    if s is not None and s <= 10 and r.get("cluster_building_count", 0) > 0:
        narrow.append(r)
narrow = narrow[:8]

# 4. Suspicious cases (any flag triggered)
suspicious = [r for r in fnd if flag(r)]

# ── Print report ─────────────────────────────────────────────────────────────
def print_table(title, rows):
    print(f"\n{'='*70}")
    print(f"  {title}  ({len(rows)} records)")
    print(f"{'='*70}")
    print(f"  {'Street':<30} {'Range':<22} {'Span':>5} {'Cluster':>8} {'Total':>7} {'EFH':>4} {'DHH':>4} {'RH':>4}  Flags")
    print(f"  {'-'*66}")
    for r in rows:
        rng = r.get("address_range", "")
        lo, hi = parse_range(rng)
        s = span(lo, hi)
        cc = r.get("cluster_building_count", "?")
        tot = r["building_count_total"]
        efh = r.get("cluster_sfh_detached_count", r.get("sfh_detached_count", "?"))
        dh  = r.get("cluster_sfh_semi_count",     r.get("sfh_semi_detached_count", "?"))
        rh  = r.get("cluster_sfh_rowhouse_count",  r.get("sfh_rowhouse_count", "?"))
        flg = flag(r)
        flg_str = " ⚠️ " + ", ".join(flg) if flg else ""
        span_str = str(s) if s is not None else "?"
        print(f"  {r['street_name']:<30} {rng:<22} {span_str:>5} {str(cc):>8} {str(tot):>7}"
              f" {str(efh):>4} {str(dh):>4} {str(rh):>4}  {flg_str}")

print_table("CATEGORY 1: Full-street clusters (ratio=1.0, n>10)", full_street)
print_table("CATEGORY 2: Multi-cluster streets (ratio<0.7, total>20)", partial)
print_table("CATEGORY 3: Narrow address range (span<=10 house numbers)", narrow)

print(f"\n{'='*70}")
print(f"  CATEGORY 4: Suspicious flags  ({len(suspicious)} total)")
print(f"{'='*70}")
if suspicious:
    for r in suspicious[:20]:
        flg = flag(r)
        print(f"  ⚠️  {r['street_name']:<35} range={r['address_range']:<18}"
              f"  cluster={r['cluster_building_count']}  total={r['building_count_total']}")
        for f_ in flg:
            print(f"      └─ {f_}")
else:
    print("  ✅ No suspicious cases found.")

# ── Overall health summary ───────────────────────────────────────────────────
zero_count = sum(1 for r in fnd if r.get("cluster_building_count") == 0)
none_count = sum(1 for r in fnd if r.get("cluster_building_count") is None)
exceed_count = sum(1 for r in fnd
                   if (r.get("cluster_building_count") or 0) > r.get("building_count_total", 0))

print(f"\n{'='*70}")
print(f"  HEALTH SUMMARY")
print(f"{'='*70}")
print(f"  Total records           : {len(fnd)}")
print(f"  cluster_count == 0      : {zero_count}")
print(f"  cluster_count == None   : {none_count}")
print(f"  cluster_count > total   : {exceed_count}  ← must be 0")
print(f"  Suspicious (any flag)   : {len(suspicious)}")
print(f"  Status                  : {'✅ CLEAN' if len(suspicious) == 0 and exceed_count == 0 else '⚠️  REVIEW NEEDED'}")
