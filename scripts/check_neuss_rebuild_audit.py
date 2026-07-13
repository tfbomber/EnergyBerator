"""
check_neuss_rebuild_audit.py
============================
Validation gate for the Neuss building rebuild. Parametrized (Phase 2) so it can
audit either the Phase-1 7-PLZ rebuilt file (default, backward compatible) or the
Phase-2 Stage A final 8-PLZ combined file via --input / --report / --label.

Validates the input parquet against:
  1. Integrity: 0 duplicate building_id, 0 postcode outside the 8 real Neuss PLZ,
     schema parity vs current data/buildings.parquet.
  2. GATE: building-weighted street-match rate vs the territoryai ranking table
     (street_level_ranking_v1.parquet), using the EXACT norm_l2 rule from the
     WBS#1 audit (scratch/street_match_audit.py) so it is apples-to-apples with
     the 58.7% baseline. Must clear >=88%.
  3. field_04 denominator before/after per segment (report only; recompute is Phase 2).

Read-only except for writing the markdown report. Does NOT modify buildings.parquet.
Reads (but never writes) the sibling territoryai repo's ranking parquet.
Default --report path is unchanged (Phase-1 report) for backward compatibility;
Phase-2 callers MUST pass an explicit --report path outside the territoryai repo.
"""
import argparse
import os
import re
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REBUILT = os.path.join(BASE, "data", "buildings_neuss_rebuilt.parquet")
CURRENT = os.path.join(BASE, "data", "buildings.parquet")
RANKING = r"D:\Stock Analysis\territoryai\data\layer2\street_level_ranking_v1.parquet"
REPORT = r"D:\Stock Analysis\territoryai\scratch\neuss_rebuild_phase1.md"

KNOWN_NEUSS_PLZ = ["41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472"]

_parser = argparse.ArgumentParser()
_parser.add_argument("--input", default=REBUILT, help="parquet file to audit (default: Phase-1 rebuilt 7-PLZ file)")
_parser.add_argument("--report", default=REPORT, help="markdown report output path (default: Phase-1 report path)")
_parser.add_argument("--label", default="Phase 1", help="label used in the report heading")
_args = _parser.parse_args()


def norm_l2(s):
    """German-aware normalization — copied verbatim from scratch/street_match_audit.py."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    if s == "":
        return s
    s = s.replace("ß", "ss")
    s = re.sub(r"[‐‑‒–—−]", "-", s)
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s*str\.$", "strasse", s)
    s = re.sub(r"\s*str$", "strasse", s)
    s = re.sub(r"\s+strasse$", "strasse", s)
    s = re.sub(r"[.,;:]+$", "", s)
    return s.strip()


out = []
def p(msg=""):
    print(msg)
    out.append(msg)


p(f"# Neuss rebuild — {_args.label} validation\n")
p(f"(input: `{_args.input}`)\n")

reb = pd.read_parquet(_args.input)
reb["postal_code"] = reb["postal_code"].astype(str).str.strip()

# --- 1. Integrity ---
p("## 1. Integrity")
n = len(reb)
uniq = reb["building_id"].nunique()
p(f"- rows: {n}, unique building_id: {uniq}, duplicates: {n - uniq}")
outside = reb[~reb["postal_code"].isin(KNOWN_NEUSS_PLZ)]
p(f"- rows with postcode outside the 8 real Neuss PLZ: {len(outside)} (boundary/PLZ filter {'OK' if len(outside) == 0 else 'FAIL'})")
fab = reb["postal_code"].isna().sum() + (reb["postal_code"] == "").sum()
p(f"- rows with empty/fabricated postcode: {fab}")
p(f"- PLZ distribution:")
for plz, c in reb["postal_code"].value_counts().sort_index().items():
    p(f"    {plz}: {c}")

cur = pd.read_parquet(CURRENT)
schema_ok = list(reb.columns) == list(cur.columns)
p(f"- schema parity vs current buildings.parquet: {'OK' if schema_ok else 'DIFFERS'}")
if not schema_ok:
    p(f"    current: {list(cur.columns)}")
    p(f"    rebuilt: {list(reb.columns)}")

# --- 2. GATE: match rate ---
p("\n## 2. Match rate vs ranking (GATE >=88% building-weighted)")
rank = pd.read_parquet(RANKING, columns=["street_name", "plz", "segment_id"])
rank["plz"] = rank["plz"].astype(str).str.strip()
rank_neuss = rank[rank["segment_id"].astype(str).str.startswith("NEUSS")].copy()
rank_neuss["sn"] = rank_neuss["street_name"].map(norm_l2)

# exact (plz, street) keys, and cross-PLZ set (street under ANY Neuss plz)
rkey_exact = set(zip(rank_neuss["plz"], rank_neuss["sn"]))
rstreet_any = set(rank_neuss["sn"])

bstreets = reb.groupby(["postal_code", "street"]).size().reset_index(name="bc")
bstreets["sn"] = bstreets["street"].map(norm_l2)
total_b = bstreets["bc"].sum()
total_pairs = len(bstreets)

exact_mask = [(plz, sn) in rkey_exact for plz, sn in zip(bstreets["postal_code"], bstreets["sn"])]
exact_mask = pd.Series(exact_mask, index=bstreets.index)
fallback_mask = exact_mask | pd.Series([sn in rstreet_any for sn in bstreets["sn"]], index=bstreets.index)

def pct(mask):
    mb = bstreets.loc[mask, "bc"].sum()
    return 100.0 * mb / total_b, int(mb), 100.0 * mask.sum() / total_pairs, int(mask.sum())

bw_e, mb_e, sw_e, sp_e = pct(exact_mask)
bw_f, mb_f, sw_f, sp_f = pct(fallback_mask)
p(f"- total buildings: {total_b}, distinct (plz,street) pairs: {total_pairs}")
p(f"- EXACT (plz, street): building-weighted **{bw_e:.2f}%** ({mb_e}/{total_b}), street-weighted {sw_e:.2f}% ({sp_e}/{total_pairs})")
p(f"- + intra-city cross-PLZ fallback: building-weighted **{bw_f:.2f}%** ({mb_f}/{total_b}), street-weighted {sw_f:.2f}% ({sp_f}/{total_pairs})")
p(f"- baseline (old data): 58.74% building-weighted")
p(f"- GATE >=88%: EXACT {'PASS' if bw_e >= 88 else 'FAIL'} / with-fallback {'PASS' if bw_f >= 88 else 'FAIL'}")

# --- top-15 unmatched (exact) ---
p("\n## 3. Top-15 residual unmatched streets (exact join, by building count)")
un = bstreets[~exact_mask].sort_values("bc", ascending=False).head(15)
for _, r in un.iterrows():
    other = "cross-PLZ-recoverable" if r["sn"] in rstreet_any else "absent from ranking"
    p(f"    {r['postal_code']}  {r['street'][:34]:34s}  bc={int(r['bc']):4d}  ({other})")

# --- 4. field_04 denominator before/after ---
p("\n## 4. field_04 denominator per segment (before = current NON-deduped, after = rebuilt)")
cur["segment_id"] = cur["segment_id"].astype(str)
cur_neuss = cur[cur["segment_id"].str.startswith("NEUSS")]
old_by_seg = cur_neuss.groupby("segment_id").size()
new_by_seg = reb.groupby("segment_id").size()
segs = sorted(set(old_by_seg.index) | set(new_by_seg.index))
p(f"    {'segment':20s} {'old(field_04 now)':>18s} {'new(rebuilt)':>14s} {'delta':>8s}")
for s in segs:
    o = int(old_by_seg.get(s, 0)); ne = int(new_by_seg.get(s, 0))
    p(f"    {s:20s} {o:>18d} {ne:>14d} {ne - o:>+8d}")
p(f"    {'TOTAL':20s} {int(old_by_seg.sum()):>18d} {int(new_by_seg.sum()):>14d} {int(new_by_seg.sum() - old_by_seg.sum()):>+8d}")

with open(_args.report, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
p(f"\n[report] {_args.report}")
