"""
build_augsburg_layer2.py
=========================
Phase 4 for Augsburg — builds parallel Layer2 structures.

Adapted from build_kaarst_layer2.py, generalized from Kaarst's single-PLZ
case to Augsburg's 14 real PLZ segments. Unlike Kaarst (whose single segment
made "the segment's B-signals" and "the whole city's B-signals" the same
thing), Augsburg needs PER-PLZ roof_norm/pv_oppty and a real cross-PLZ
global_rank — this follows the same multi-segment scoring mechanics as the
production fields/field_08_street_level_ranking.py (load_b_signals +
global_rank across all segments + rank_in_segment + priority_sort), just
without field_07's Fernwärme/HP modifiers (Augsburg has no field_07 run,
same as Kaarst — modifiers stay neutral 1.0, matching the Kaarst precedent).

GUARDRAILS (hard constraints):
  1. NO modification to Neuss layer2_mvp_input_table.parquet
  2. NO modification to Neuss/Kaarst street_ranking_v1.parquet
  3. NO modification to Neuss/Kaarst street_level_ranking_v1.parquet
  4. Only the 14 known Augsburg PLZ clusters from
     augsburg_foundation_structure_results.json (stray neighbor-municipality
     PLZs and UNKNOWN-postcode clusters dropped — not real Augsburg signal)
  5. Uses same field weights and scoring constants as field_07/field_08 (Guardrail G3)

PRE-EXISTING BUG, NOW FIXED UPSTREAM (2026-07-11): fields/field_01_roof_potential.py's
get_factor() used to expect building-type labels
'detached'/'semi'/'rowhouse'/'apartment'/'large_block'/'unknown', but
fields/field_02_building_type.py's actual output vocabulary is
'SFH_CONFIRMED'/'MFH_CONFIRMED'/'SFH_WEAK'/'MFH_SUSPECT'/'UNCERTAIN' — the
merge in field_01.run() found no matching category for ANY of these, so
utilization_factors.get(b_type, 0.20) silently defaulted to 0.20 for every
building. This made field_01's "roof_suitability_score" degenerate to
EXACTLY 0.20 (raw) for any segment computed after field_02 was upgraded to
this label scheme. field_01_roof_potential.py has since been rewritten to key
on field_02's real Stage1/2 vocabulary (with a raw-OSM-tag sub-split for
SFH_CONFIRMED), and Augsburg's 15 rows in field_01_roof_potential.parquet were
regenerated via scripts/rerun_augsburg_field01.py using the same
isolate-then-restore pattern as run_augsburg_fields.py / rerun_kaarst_field01.py.
_compute_real_roof_scores() below now reads those corrected rows directly
instead of recomputing locally — this script's own former raw-OSM-tag
workaround (_UTILIZATION_BY_RAW_TAG, an 8-tag lookup with a blunt
.fillna(0.20) for anything untagged) has been retired in favor of field_01's
richer Stage1/2 footprint×adjacency inference for untagged/ambiguous
buildings, which is expected to be more accurate, not just a duplicate.

Outputs (new files, parallel to Neuss/Kaarst):
  data/layer2/augsburg_layer2_input_table.parquet   (14 rows, one per PLZ)
  data/layer2/augsburg_street_level_ranking_v1.parquet
"""

import json
import math
import logging
import statistics
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("AUGSBURG_LAYER2_BUILDER")

BASE_DIR   = Path(__file__).resolve().parents[1]
FIELDS_DIR = BASE_DIR / "data" / "fields"
OUT_DIR    = BASE_DIR / "data" / "layer2"

AUGSBURG_FOUNDATION_JSON = BASE_DIR / "output" / "foundation" / "augsburg_foundation_structure_results.json"
AUGSBURG_BUILDINGS_PARQ  = BASE_DIR / "data" / "augsburg_buildings.parquet"
FIELD01_PARQ = FIELDS_DIR / "field_01_roof_potential.parquet"
FIELD02_PARQ = FIELDS_DIR / "field_02_building_type.parquet"
FIELD04_PARQ = FIELDS_DIR / "field_04_pv_adoption.parquet"

ALLOTMENT_BUILDING_IDS_JSON = BASE_DIR / "data" / "augsburg_allotment_building_ids.json"
ALLOTMENT_FULL_CONTAMINATION_THRESHOLD = 0.90


def _find_fully_allotment_streets() -> set[tuple[str, str]]:
    """Return the set of (street_name, plz) keys where >=90% of the street's
    own buildings fall inside an OSM landuse=allotments polygon — i.e. the
    "street" is actually a Kleingartenanlage (allotment garden colony), not
    real single-family homes, and should not be canvassed at all.

    Found during a 2026-07-08 reliability spot-check: satellite imagery of
    "Am Wertachdamm" (86199, then-rank #13) showed a garden-shed colony along
    the Wertach river, not houses — confirmed by an independent Overpass
    query for landuse=allotments polygons (281 found in the Augsburg bbox)
    and a precise point-in-polygon join (54 of 35,923 real buildings,
    i.e. 0.2% citywide, fall inside one). Most affected streets have only a
    small minority of allotment buildings mixed with real houses (1-45%) —
    left as-is, not worth the risk of re-deriving Foundation-stage counts for
    a <1% effect. Only the ONE fully-contaminated case (Am Wertachdamm,
    100%) is excluded here — a real street shouldn't be recommended to a
    salesperson as a PV canvassing target when it doesn't have real houses.
    Building ID set persisted in data/augsburg_allotment_building_ids.json
    (from a live Overpass spatial join) so this doesn't need re-fetching.
    """
    if not ALLOTMENT_BUILDING_IDS_JSON.exists():
        logger.warning("[ALLOTMENT] No cached allotment building_id list found — skipping this check.")
        return set()

    allotment_ids = set(json.loads(ALLOTMENT_BUILDING_IDS_JSON.read_text()))
    buildings = pd.read_parquet(AUGSBURG_BUILDINGS_PARQ)
    buildings = buildings[buildings["segment_id"].str.startswith("AUGSBURG_OSM_") &
                           (buildings["segment_id"] != "AUGSBURG_OSM_GENERAL")]
    buildings["is_allotment"] = buildings["building_id"].isin(allotment_ids)

    fully_contaminated: set[tuple[str, str]] = set()
    for (street, plz), grp in buildings.groupby(["street", "postal_code"]):
        frac = grp["is_allotment"].mean()
        if frac >= ALLOTMENT_FULL_CONTAMINATION_THRESHOLD:
            fully_contaminated.add((street, str(plz)))
            logger.info(f"[ALLOTMENT] Excluding '{street}' ({plz}) — "
                        f"{grp['is_allotment'].sum()}/{len(grp)} buildings ({frac:.0%}) "
                        f"are inside a landuse=allotments polygon, not real houses.")
    return fully_contaminated


def _compute_per_street_data_quality() -> dict[tuple[str, str], dict]:
    """Compute sfh_confirmed_share/sfh_proxy_share/data_quality PER STREET
    (street_name, plz), instead of inheriting the whole-PLZ aggregate.

    BUG FOUND during a 2026-07-07 reliability audit: the per-street rows were
    displaying data_quality_note/sfh_stage1_share/sfh_stage2_share copied from
    the segment-level b_signals dict (one value per PLZ, applied to every one
    of that PLZ's ~100+ streets). Spot-check: Dornröschenweg (PLZ 86199,
    global_rank #1) is 100% SFH_CONFIRMED at the building level (verified
    against a live Overpass re-query — every one of its 29 buildings is
    explicitly OSM-tagged "detached"), yet was displaying PLZ 86199's overall
    aggregate (only 29.5% SFH_CONFIRMED citywide across all 5056 buildings in
    that PLZ) — a real understatement of that street's actual confidence.
    This matters far more for Augsburg than it did for Neuss/Kaarst: each
    Augsburg PLZ covers roughly 2-3x the area of a single named Stadtbezirk
    (verified against Zensus/Stadt Augsburg district data), so PLZ-level
    averages mask far more street-to-street variance here.

    roof_norm/pv_oppty are NOT changed by this fix — those are legitimately
    PLZ-level signals (roof score aggregates the whole PLZ's buildings by
    design; PV adoption is a MaStR PLZ-allocation, physically un-splittable
    below that granularity) — only the SFH classification confidence, which
    we DO have real per-building data for, gets recomputed at street grain.
    """
    buildings = pd.read_parquet(AUGSBURG_BUILDINGS_PARQ)
    f02 = pd.read_parquet(FIELD02_PARQ)[["building_id", "field_value"]]
    merged = buildings.merge(f02, on="building_id", how="left")

    out: dict[tuple[str, str], dict] = {}
    for (street, plz), grp in merged.groupby(["street", "postal_code"]):
        vc = grp["field_value"].value_counts()
        n = len(grp)
        n_sfh_confirmed = int(vc.get("SFH_CONFIRMED", 0))
        n_sfh_weak      = int(vc.get("SFH_WEAK", 0))
        n_mfh_confirmed = int(vc.get("MFH_CONFIRMED", 0))
        n_mfh_suspect   = int(vc.get("MFH_SUSPECT", 0))

        sfh_confirmed_share = n_sfh_confirmed / n if n else 0.0
        sfh_friendly_share  = (n_sfh_confirmed + n_sfh_weak) / n if n else 0.0
        sfh_proxy_share     = max(0.0, sfh_friendly_share - sfh_confirmed_share)

        if sfh_confirmed_share >= SFH_HIGH_CONFIRMED_THRESHOLD:
            data_quality = "HIGH"
        elif sfh_confirmed_share < SFH_PROXY_CONFIRMED_THRESHOLD and sfh_proxy_share > SFH_PROXY_SHARE_THRESHOLD:
            data_quality = "PROXY"
        else:
            data_quality = "MIXED"

        out[(street, str(plz))] = {
            "sfh_confirmed_share": round(sfh_confirmed_share, 4),
            "sfh_proxy_share":     round(sfh_proxy_share, 4),
            "data_quality":        data_quality,
            "n_buildings_matched": n,
        }
    return out


def _compute_real_roof_scores() -> dict[str, dict]:
    """Load roof_suitability_score per Augsburg segment from the (now-fixed)
    shared field_01_roof_potential.parquet — see the module docstring's
    "PRE-EXISTING BUG, NOW FIXED UPSTREAM" note. field_01 itself computes
    this via per-building footprint area (UTM32N) x utilization factor,
    aggregated as roof_pool_adjusted / roof_pool_area per segment, using
    field_02's Stage1/2 classification (with a raw-OSM-tag sub-split for
    SFH_CONFIRMED) — richer than this script's former standalone raw-tag
    lookup."""
    df = pd.read_parquet(FIELD01_PARQ)
    df = df[df["segment_id"].str.startswith("AUGSBURG_")]

    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        out[row["segment_id"]] = {
            "roof_suitability_score": round(float(row["field_value"]), 4),
            "roof_building_count":    int(row["building_count"]),
            "roof_pool_adjusted_m2":  round(float(row["roof_pool_adjusted_m2"]), 2),
        }
    return out

# Real PLZ set, confirmed from actual tagged buildings (see
# generate_augsburg_osm_clusters.py run log). Anything outside this set in
# the foundation JSON is either UNKNOWN-postcode noise or a stray
# neighboring-municipality PLZ that leaked through the boundary polygon edge.
AUGSBURG_PLZ_SEGMENTS: dict[str, str] = {
    plz: f"AUGSBURG_OSM_{plz}"
    for plz in [
        "86150", "86152", "86153", "86154", "86156", "86157", "86159",
        "86161", "86163", "86165", "86167", "86169", "86179", "86199",
    ]
}

# Gate thresholds — IDENTICAL to build_layer2_mvp_input_table.py / field_08
GATE_DEPLOY_THR   = 0.60
GATE_MIXED_THR    = 0.30

SFH_CONFIRMED_LABELS = frozenset({"SFH_CONFIRMED"})
MFH_CONFIRMED_LABELS = frozenset({"MFH_CONFIRMED"})
SFH_WEAK_LABELS      = frozenset({"SFH_WEAK"})
MFH_SUSPECT_LABELS   = frozenset({"MFH_SUSPECT"})
UNCERTAIN_LABELS     = frozenset({"UNCERTAIN"})

# Scoring weights — IDENTICAL to field_08_street_level_ranking.py
GATE_SCORE = {"PASS": 1.00, "QUALIFIED": 0.80, "REVIEW": 0.40, "FAIL": 0.00}
W_SFH_QUALITY  = 0.30
W_GATE         = 0.20
W_MFH_CLEAN    = 0.10
W_SCALE        = 0.10
W_ROOF_NORM    = 0.20
W_PV_OPPTY     = 0.10
W_DETACHED     = 1.00
W_SEMI         = 0.65
W_ROWHOUSE     = 0.50
SCALE_NORM_DENOM     = math.log1p(30)
SFH_SCALE_SATURATION = 15
LOW_SAMPLE_THRESHOLD = 10     # matches field_08_street_level_ranking.py
PV_SCORE_CAP         = 0.50   # E3 cap (field_04's E3_MAX_FIELD_VALUE) — matches field_08's saturation check
SFH_HIGH_CONFIRMED_THRESHOLD  = 0.50   # matches field_08 data_quality thresholds
SFH_PROXY_CONFIRMED_THRESHOLD = 0.10
SFH_PROXY_SHARE_THRESHOLD     = 0.40


# ── Step 1: Load field data for ONE PLZ segment ──────────────────────────────

def load_augsburg_segment_fields(segment_id: str, real_roof_scores: dict,
                                  df_f02: pd.DataFrame, df_f04: pd.DataFrame) -> dict:
    """Same logic as build_kaarst_layer2.load_kaarst_fields(), parameterized
    per segment instead of hardcoded to one Kaarst segment_id. Roof score
    comes from _compute_real_roof_scores(), NOT field_01_roof_potential.parquet
    directly (see module docstring — that parquet's Augsburg rows are all a
    degenerate flat 0.20 due to a pre-existing field_01/field_02 label
    mismatch bug)."""
    signals: dict = {}

    r = real_roof_scores.get(segment_id)
    if r:
        signals["roof_suitability_score"]      = r["roof_suitability_score"]
        signals["roof_building_count"]         = r["roof_building_count"]
        signals["roof_pool_adjusted_m2"]       = r["roof_pool_adjusted_m2"]
        signals["f01_confidence"]              = 0.85  # same as field_01's stated confidence
        signals["roof_suitability_score_norm"] = round(min(1.0, signals["roof_suitability_score"] / 0.45), 4)
    else:
        logger.warning(f"[ROOF] No buildings for {segment_id} — using neutral defaults")
        signals["roof_suitability_score"]      = 0.20
        signals["roof_building_count"]         = 0
        signals["roof_pool_adjusted_m2"]       = 0.0
        signals["f01_confidence"]              = 0.0
        signals["roof_suitability_score_norm"] = 0.5

    f02 = df_f02[df_f02["segment_id"] == segment_id]
    if len(f02) > 0:
        vc = f02["field_value"].value_counts()
        n_classified    = len(f02)
        n_sfh_confirmed = int(vc.reindex(list(SFH_CONFIRMED_LABELS), fill_value=0).sum())
        n_mfh_confirmed = int(vc.reindex(list(MFH_CONFIRMED_LABELS), fill_value=0).sum())
        n_sfh_weak      = int(vc.reindex(list(SFH_WEAK_LABELS),      fill_value=0).sum())
        n_mfh_suspect   = int(vc.reindex(list(MFH_SUSPECT_LABELS),   fill_value=0).sum())
        n_uncertain     = int(vc.reindex(list(UNCERTAIN_LABELS),     fill_value=0).sum())

        universe_total       = n_classified
        sfh_confirmed_share  = n_sfh_confirmed / universe_total
        mfh_confirmed_share  = n_mfh_confirmed / universe_total
        sfh_friendly_share   = (n_sfh_confirmed + n_sfh_weak) / universe_total
        effective_sfh_share  = sfh_confirmed_share
        uncertain_share      = n_uncertain / universe_total

        counts = {
            "SFH_CONFIRMED": n_sfh_confirmed, "MFH_CONFIRMED": n_mfh_confirmed,
            "SFH_WEAK": n_sfh_weak, "MFH_SUSPECT": n_mfh_suspect, "UNCERTAIN": n_uncertain,
        }
        dominant_form = max(counts, key=counts.get)

        if sfh_confirmed_share >= 0.50:
            f02_conf = 0.9
        elif sfh_friendly_share >= 0.50:
            f02_conf = 0.7
        else:
            f02_conf = 0.5

        signals.update({
            "sfh_confirmed_share": round(sfh_confirmed_share, 4),
            "mfh_confirmed_share": round(mfh_confirmed_share, 4),
            "sfh_friendly_share":  round(sfh_friendly_share, 4),
            "effective_sfh_share": round(effective_sfh_share, 4),
            "uncertain_share":     round(uncertain_share, 4),
            "dominant_form":       dominant_form,
            "f02_building_count":  universe_total,
            "f02_classified_count": n_classified,
            "f02_confidence":      f02_conf,
            "f02_classification_note": (
                f"Stage 1/2 label counts: SFH_CONFIRMED={n_sfh_confirmed} "
                f"MFH_CONFIRMED={n_mfh_confirmed} SFH_WEAK={n_sfh_weak} "
                f"MFH_SUSPECT={n_mfh_suspect} UNCERTAIN={n_uncertain}. "
                f"Denominator: universe_total={universe_total}. "
                f"Source: Augsburg Phase 3 F02 (augsburg_buildings.parquet)."
            ),
        })
    else:
        logger.warning(f"[F02] No records for {segment_id} — using neutral defaults")
        signals.update({
            "sfh_confirmed_share": 0.5, "mfh_confirmed_share": 0.0,
            "sfh_friendly_share": 0.5, "effective_sfh_share": 0.0,
            "uncertain_share": 0.5, "dominant_form": "UNCERTAIN",
            "f02_building_count": 0.0, "f02_classified_count": 0.0,
            "f02_confidence": 0.0, "f02_classification_note": "NO_DATA",
        })

    f04 = df_f04[df_f04["segment_id"] == segment_id]
    if len(f04) == 1:
        r = f04.iloc[0]
        signals["pv_coverage_score"]        = float(r["field_value"])
        signals["pv_coverage_availability"] = "PLZ_ALLOCATION_E3"
        signals["pv_confidence"]            = float(r.get("confidence", 0.45))
        signals["pv_source"]                = str(r.get("source", "PLZ_ALLOCATION_E3"))
    else:
        logger.warning(f"[F04] No PV record for {segment_id} — using neutral")
        signals["pv_coverage_score"]        = 0.5
        signals["pv_coverage_availability"] = "MISSING"
        signals["pv_confidence"]            = 0.0
        signals["pv_source"]                = "MISSING"

    return signals


def agg_foundation_gate(clusters: list) -> dict:
    """Identical to build_kaarst_layer2.agg_foundation_gate()."""
    n_total = len(clusters)
    if n_total == 0:
        return {"l1_gate_label": "BLOCKED", "pct_l1_gate_pass": 0.0,
                "sfh_total_ratio_median": 0.0, "l1_cluster_count": 0}

    n_pass   = sum(1 for c in clusters if c["structure_gate"] in ("PASS", "QUALIFIED"))
    pct_pass = n_pass / n_total

    if pct_pass >= GATE_DEPLOY_THR:
        gate_label = "DEPLOYABLE"
    elif pct_pass >= GATE_MIXED_THR:
        gate_label = "MIXED"
    else:
        gate_label = "BLOCKED"

    sfh_ratios = [c["sfh_total_ratio"] for c in clusters if "sfh_total_ratio" in c]
    sfh_median = round(statistics.median(sfh_ratios), 4) if sfh_ratios else 0.0

    return {
        "l1_gate_label": gate_label,
        "pct_l1_gate_pass": round(pct_pass, 4),
        "sfh_total_ratio_median": sfh_median,
        "l1_cluster_count": n_total,
    }


def _sfh_quality_score(c: dict) -> float:
    sfh_total = c.get("sfh_total_count", 0) or 0
    sfh_ratio = float(c.get("sfh_total_ratio", 0.0) or 0.0)
    if sfh_total == 0 or sfh_ratio == 0:
        return 0.0
    weighted = (
        float(c.get("sfh_detached_count", 0) or 0) * W_DETACHED
        + float(c.get("sfh_semi_detached_count", 0) or 0) * W_SEMI
        + float(c.get("sfh_rowhouse_count", 0) or 0) * W_ROWHOUSE
    )
    return round(sfh_ratio * (weighted / sfh_total), 4)


def _gate_score(c: dict) -> float:
    return GATE_SCORE.get(str(c.get("structure_gate", "FAIL")).upper(), 0.0)


def _scale_score(c: dict) -> float:
    n = int(c.get("building_count_total", 0) or 0)
    return round(min(1.0, math.log1p(n) / SCALE_NORM_DENOM), 4)


def _mfh_clean_score(c: dict) -> float:
    return round(1.0 - float(c.get("mfh_ratio", 0.0) or 0.0), 4)


def _top_reason(c: dict, coherence_capped: bool = False) -> str:
    if coherence_capped:
        return "Segment data quality low — verify building types on site"
    sfh_ratio = float(c.get("sfh_total_ratio", 0.0) or 0.0)
    mfh_ratio = float(c.get("mfh_ratio", 0.0) or 0.0)
    g_label   = str(c.get("structure_gate", "")).upper()
    n         = int(c.get("building_count_total", 1) or 1)
    det_count = int(c.get("sfh_detached_count", 0) or 0)

    if g_label == "FAIL":
        return "MFH-heavy — skip unless data improves"
    if mfh_ratio > 0.40:
        return f"High MFH mix ({mfh_ratio:.0%}) — qualify on site"
    if sfh_ratio >= 0.90 and det_count / max(n, 1) >= 0.60:
        return "Detached-dominant — max roof area per household"
    if sfh_ratio >= 0.90:
        return "Very high SFH density — strong deployment base"
    if sfh_ratio >= 0.70:
        return "Good SFH share — solid volume target"
    if sfh_ratio >= 0.50:
        return "Mixed SFH/MFH — pre-qualify before batch approach"
    return "Low SFH ratio — review structure before investing"


def main():
    logger.info("=" * 65)
    logger.info("  Augsburg Phase 4 — Layer2 Builder (14 PLZ segments)")
    logger.info("=" * 65)

    with open(AUGSBURG_FOUNDATION_JSON, encoding="utf-8") as f:
        all_clusters = json.load(f)
    logger.info(f"[LOAD] {len(all_clusters)} total clusters in foundation JSON")

    # Keep only the 14 real Augsburg PLZ (drop UNKNOWN + stray neighbor-PLZ noise)
    clusters_by_plz: dict[str, list] = {plz: [] for plz in AUGSBURG_PLZ_SEGMENTS}
    n_dropped = 0
    for c in all_clusters:
        plz = str(c.get("plz", ""))
        if plz in clusters_by_plz:
            clusters_by_plz[plz].append(c)
        else:
            n_dropped += 1
    logger.info(f"[FILTER] Dropped {n_dropped} clusters outside the 14 known Augsburg PLZ "
                f"(UNKNOWN postcode / neighboring-municipality noise)")
    for plz, cl in clusters_by_plz.items():
        logger.info(f"  PLZ {plz}: {len(cl)} clusters")

    real_roof_scores = _compute_real_roof_scores()
    logger.info("[ROOF] Recomputed real per-segment roof_suitability_score "
                "(bypassing degenerate field_01 output):")
    for seg_id, r in sorted(real_roof_scores.items()):
        logger.info(f"  {seg_id:<22} raw={r['roof_suitability_score']:.4f} "
                    f"(n={r['roof_building_count']})")

    per_street_quality = _compute_per_street_data_quality()
    logger.info(f"[DATA_QUALITY] Computed per-street classification confidence "
                f"for {len(per_street_quality)} (street, plz) keys "
                f"(replaces PLZ-aggregate data_quality_note — see docstring)")

    df_f02 = pd.read_parquet(FIELD02_PARQ)
    df_f04 = pd.read_parquet(FIELD04_PARQ)

    # ── Build Layer2 input table: one row per PLZ segment ───────────────────
    l2_rows = []
    b_signals: dict[str, dict] = {}
    for plz, segment_id in AUGSBURG_PLZ_SEGMENTS.items():
        clusters = clusters_by_plz[plz]
        signals  = load_augsburg_segment_fields(segment_id, real_roof_scores, df_f02, df_f04)
        gate_agg = agg_foundation_gate(clusters)

        sfh_confirmed = signals["sfh_confirmed_share"]
        sfh_friendly  = signals["sfh_friendly_share"]
        sfh_proxy     = max(0.0, sfh_friendly - sfh_confirmed)   # matches field_08 load_b_signals
        if sfh_confirmed >= SFH_HIGH_CONFIRMED_THRESHOLD:
            data_quality = "HIGH"
        elif sfh_confirmed < SFH_PROXY_CONFIRMED_THRESHOLD and sfh_proxy > SFH_PROXY_SHARE_THRESHOLD:
            data_quality = "PROXY"
        else:
            data_quality = "MIXED"

        b_signals[segment_id] = {
            "roof_norm": signals["roof_suitability_score_norm"],
            "pv_oppty":  round(min(1.0, max(0.0, signals["pv_coverage_score"])), 4),
            "l1_gate_label": gate_agg["l1_gate_label"],
            # PV E3 saturation check — matches field_08's load_b_signals exactly:
            # field_04 (PLZ_ALLOCATION_E3) hard-caps field_value at PV_SCORE_CAP (0.50).
            # A segment hitting the cap means the signal is unreliable (data-cap
            # artifact), not genuine "zero market opportunity" — must be flagged.
            "pv_data_saturated": bool(signals["pv_coverage_score"] >= PV_SCORE_CAP),
            "sfh_confirmed_share": round(sfh_confirmed, 4),
            "sfh_proxy_share":     round(sfh_proxy, 4),
            "data_quality":        data_quality,
        }

        lats = [c.get("cluster_centroid_lat", 0) for c in clusters if c.get("cluster_centroid_lat")]
        lons = [c.get("cluster_centroid_lon", 0) for c in clusters if c.get("cluster_centroid_lon")]

        l2_rows.append({
            "unit_id":                  segment_id,
            "unit_type":                "residential_urban",
            "unit_status":              "REAL_GROUNDED",
            "district_name":            f"Augsburg (PLZ {plz})",
            "plz":                      plz,
            "centroid_lat":             round(sum(lats)/len(lats), 4) if lats else 48.37,
            "centroid_lon":             round(sum(lons)/len(lons), 4) if lons else 10.90,
            "roof_suitability_score":   signals["roof_suitability_score"],
            "roof_building_count":      signals["roof_building_count"],
            "roof_pool_adjusted_m2":    signals["roof_pool_adjusted_m2"],
            "f01_confidence":           signals["f01_confidence"],
            "sfh_confirmed_share":      signals["sfh_confirmed_share"],
            "mfh_confirmed_share":      signals["mfh_confirmed_share"],
            "uncertain_share":          signals["uncertain_share"],
            "effective_sfh_share":      signals["effective_sfh_share"],
            "sfh_friendly_share":       signals["sfh_friendly_share"],
            "dominant_form":            signals["dominant_form"],
            "f02_building_count":       signals["f02_building_count"],
            "f02_classified_count":     signals["f02_classified_count"],
            "f02_confidence":           signals["f02_confidence"],
            "f02_classification_note":  signals["f02_classification_note"],
            "l1_gate_label":            gate_agg["l1_gate_label"],
            "pct_l1_gate_pass":         gate_agg["pct_l1_gate_pass"],
            "sfh_total_ratio_median":   gate_agg["sfh_total_ratio_median"],
            "l1_cluster_count":         gate_agg["l1_cluster_count"],
            "pv_coverage_score":        signals["pv_coverage_score"],
            "pv_coverage_availability": signals["pv_coverage_availability"],
            "pv_confidence":            signals["pv_confidence"],
            "pv_source":                signals["pv_source"],
            "row_usable_for_ranking":   True,
            "build_timestamp_utc":      datetime.now(timezone.utc).isoformat(),
            "roof_suitability_score_norm": signals["roof_suitability_score_norm"],
            "roof_data_available":      True,
            "roof_norm_or_neutral":     signals["roof_suitability_score_norm"],
        })

    df_l2 = pd.DataFrame(l2_rows)
    l2_path = OUT_DIR / "augsburg_layer2_input_table.parquet"
    df_l2.to_parquet(l2_path, index=False)
    logger.info(f"[SAVE] Layer2 input table -> {l2_path} ({len(df_l2)} PLZ rows)")

    # ── Street-level ranking across ALL 14 segments together ────────────────
    # Dedup by (plz, street_name), same as field_08/Kaarst.
    fully_allotment_streets = _find_fully_allotment_streets()
    seen = set()
    dedup: list[dict] = []
    n_excluded = 0
    for plz, segment_id in AUGSBURG_PLZ_SEGMENTS.items():
        for c in clusters_by_plz[plz]:
            street_name = c.get("street_name", "")
            key = (plz, street_name)
            if key in seen:
                continue
            seen.add(key)
            if (street_name, plz) in fully_allotment_streets:
                n_excluded += 1
                continue
            c = dict(c)
            c["_segment_id"] = segment_id
            dedup.append(c)
    logger.info(f"[F08] {sum(len(v) for v in clusters_by_plz.values())} clusters -> "
                f"{len(dedup)} unique streets after dedup "
                f"({n_excluded} excluded as fully-allotment-garden colonies)")

    rows = []
    for c in dedup:
        segment_id = c["_segment_id"]
        b = b_signals[segment_id]
        roof_norm = b["roof_norm"]
        pv_oppty  = b["pv_oppty"]

        # Coherence guard — IDENTICAL to field_08_street_level_ranking.py:
        # if the segment is BLOCKED (<30% Foundation PASS rate), cap street
        # gates to REVIEW so individual streets can't show misleading PASS
        # in a segment whose overall structure data is unreliable.
        seg_blocked = (b.get("l1_gate_label") == "BLOCKED")
        orig_gate = str(c.get("structure_gate", "")).upper()
        gate_override = "REVIEW" if (seg_blocked and orig_gate in ("PASS", "QUALIFIED")) else None

        if gate_override:
            c_scored = dict(c)
            c_scored["structure_gate"] = gate_override
        else:
            c_scored = c

        sfh_q  = _sfh_quality_score(c_scored)
        gate_s = _gate_score(c_scored)
        scale  = _scale_score(c_scored)
        mfh_c  = _mfh_clean_score(c_scored)

        score = round(
            sfh_q * W_SFH_QUALITY + gate_s * W_GATE + mfh_c * W_MFH_CLEAN
            + scale * W_SCALE + roof_norm * W_ROOF_NORM + pv_oppty * W_PV_OPPTY,
            4,
        )

        sfh_n = int(c.get("sfh_total_count", 0) or 0)
        scale_dampening = round(min(1.0, sfh_n / SFH_SCALE_SATURATION), 4)
        # No field_07 Fernwärme/HP modifiers for Augsburg (same as Kaarst) -> neutral 1.0
        adj_score = round(score * scale_dampening * 1.0, 4)
        n_total = int(c.get("building_count_total", 0) or 0)

        rows.append({
            "cluster_id":            c.get("cluster_id"),
            "street_name":           c.get("street_name"),
            "plz":                   c.get("plz"),
            "address_range":         c.get("address_range", ""),
            "segment_id":            segment_id,
            "street_score":          score,
            "scale_dampening":       scale_dampening,
            "adjusted_street_score": adj_score,
            "segment_fern_modifier": 1.0,
            "segment_hp_modifier":   1.0,
            "segment_certainty":     1.0,
            "segment_combined_modifier": 1.0,
            "sfh_quality_score":     sfh_q,
            "gate_score":            gate_s,
            "mfh_clean_score":       mfh_c,
            "scale_score":           scale,
            "roof_norm_score":       round(roof_norm * W_ROOF_NORM, 4),
            "pv_oppty_score":        round(pv_oppty  * W_PV_OPPTY, 4),
            "b_roof_norm":           round(roof_norm, 3),
            "b_pv_oppty":            round(pv_oppty, 3),
            "structure_gate":        gate_override if gate_override else c.get("structure_gate"),
            "structure_gate_original": c.get("structure_gate"),
            "coherence_capped":      bool(gate_override),
            "structure_profile":     c.get("structure_profile"),
            "sfh_total_ratio":       float(c.get("sfh_total_ratio", 0.0) or 0.0),
            "sfh_detached_count":    int(c.get("sfh_detached_count", 0) or 0),
            "sfh_rowhouse_count":    int(c.get("sfh_rowhouse_count", 0) or 0),
            "sfh_semi_count":        int(c.get("sfh_semi_detached_count", 0) or 0),
            "sfh_total_count":       sfh_n,
            "mfh_count":             int(c.get("mfh_count", 0) or 0),
            "mfh_ratio":             float(c.get("mfh_ratio", 0.0) or 0.0),
            "building_count_total":  n_total,
            "sfh_detached_ratio":    round(int(c.get("sfh_detached_count", 0) or 0) / max(n_total, 1), 3),
            "sfh_rowhouse_ratio":    round(int(c.get("sfh_rowhouse_count", 0) or 0) / max(n_total, 1), 3),
            "sfh_semi_ratio":        round(int(c.get("sfh_semi_detached_count", 0) or 0) / max(n_total, 1), 3),
            "top_reason":            _top_reason(c, coherence_capped=bool(gate_override)),
            "execution_scale_flag":  c.get("execution_scale_flag"),
            "street_confidence":     c.get("street_confidence"),
            "sales_story":           c.get("sales_story", ""),
            "low_sample_flag":       bool(n_total < LOW_SAMPLE_THRESHOLD),
            "pv_data_saturated":     b.get("pv_data_saturated", False),
            **(lambda sq: {
                "sfh_stage1_share":  sq["sfh_confirmed_share"],
                "sfh_stage2_share":  sq["sfh_proxy_share"],
                "data_quality_note": (
                    "Stage-1 confirmed (OSM adjacency)" if sq["data_quality"] == "HIGH"
                    else "Stage-2 proxy (footprint heuristic)" if sq["data_quality"] == "PROXY"
                    else "Stage-1 + Stage-2 composite"
                ),
            })(
                # Per-street confidence (real fix, 2026-07-07) — falls back to
                # the PLZ-level b_signals aggregate only if this exact street
                # had zero buildings join successfully (shouldn't happen in
                # practice; defensive only).
                per_street_quality.get(
                    (c.get("street_name", ""), str(c.get("plz", ""))),
                    {
                        "sfh_confirmed_share": b.get("sfh_confirmed_share", 0.0),
                        "sfh_proxy_share": b.get("sfh_proxy_share", 0.0),
                        "data_quality": b.get("data_quality", "MIXED"),
                    },
                )
            ),
            "hp_confidence":            1.0,   # no field_07 HP data for Augsburg (same as Kaarst)
            "seg_truly_uncertain_share": 0.0,  # no field_07 data for Augsburg (same as Kaarst)
        })

    df = pd.DataFrame(rows)

    # Global rank across ALL 14 Augsburg segments together (matches field_08's
    # real multi-segment behavior, not Kaarst's trivial single-segment case).
    df["global_rank"] = df["adjusted_street_score"].rank(method="first", ascending=False).astype(int)
    df["rank_in_segment"] = (
        df.groupby("segment_id")["street_score"].rank(method="first", ascending=False).astype(int)
    )

    # street_quality_agg per segment (building-count-weighted mean of RAW street_score)
    df["_n_x_score"] = df["street_score"] * df["building_count_total"]
    agg = df.groupby("segment_id").agg(
        street_quality_agg=("_n_x_score", "sum"),
        _n_total=("building_count_total", "sum"),
    )
    agg["street_quality_agg"] = (agg["street_quality_agg"] / agg["_n_total"]).round(4)
    agg = agg.drop(columns="_n_total").reset_index()
    df = df.merge(agg, on="segment_id", how="left").drop(columns="_n_x_score")

    # Real segment_rank: rank the 14 PLZ segments by their own street_quality_agg
    # (best building-quality segment = rank 1). There is no field_07 output for
    # Augsburg to source this from (same as Kaarst), so this is derived directly
    # from Augsburg's own computed data rather than left as an arbitrary constant.
    agg_sorted = agg.sort_values("street_quality_agg", ascending=False).reset_index(drop=True)
    segment_rank_map = {row["segment_id"]: i + 1 for i, row in agg_sorted.iterrows()}
    df["segment_rank"] = df["segment_id"].map(segment_rank_map)
    df["priority_sort"] = ((df["segment_rank"] - 1) * 1000 + df["rank_in_segment"]).astype(int)

    df = df.sort_values("global_rank").reset_index(drop=True)

    slr_path = OUT_DIR / "augsburg_street_level_ranking_v1.parquet"
    df.to_parquet(slr_path, index=False)
    logger.info(f"[SAVE] Street-level ranking -> {slr_path} ({len(df)} streets)")

    logger.info("[SEGMENT RANK] (by street_quality_agg, best first):")
    for _, r in agg_sorted.iterrows():
        logger.info(f"  #{segment_rank_map[r['segment_id']]:<3} {r['segment_id']:<22} "
                    f"street_quality_agg={r['street_quality_agg']:.4f}")

    logger.info("[GLOBAL] Top-10 Augsburg streets:")
    for _, r in df.head(10).iterrows():
        logger.info(
            f"  #{int(r['global_rank']):<4} {r['street_name']:<35} ({r['segment_id']}) "
            f"score={r['street_score']:.3f} adj={r['adjusted_street_score']:.3f} "
            f"gate={r['structure_gate']}"
        )

    logger.info("=" * 65)
    logger.info("  Augsburg Phase 4 DONE")
    logger.info("=" * 65)
    return df_l2, df


if __name__ == "__main__":
    df_l2, df_slr = main()
    print(f"\nLayer2 rows ({len(df_l2)}):")
    print(df_l2[["unit_id", "l1_gate_label", "pct_l1_gate_pass", "pv_coverage_score",
                 "sfh_friendly_share", "roof_suitability_score_norm"]].to_string(index=False))
    print(f"\nTop-15 Augsburg streets:")
    print(df_slr[["global_rank", "street_name", "segment_id", "street_score",
                  "adjusted_street_score", "structure_gate"]].head(15).to_string(index=False))
