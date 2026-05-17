"""
build_kaarst_layer2.py
======================
Phase 4 for Kaarst — builds parallel Layer2 structures.

GUARDRAILS (hard constraints):
  1. NO modification to Neuss layer2_mvp_input_table.parquet
  2. NO modification to Neuss street_ranking_v1.parquet
  3. NO modification to Neuss street_level_ranking_v1.parquet
  4. Only PLZ 41564 clusters from kaarst_foundation_structure_results.json
  5. Uses same field weights and scoring constants as field_07/field_08 (Guardrail G3)
  6. Reads existing Kaarst field parquets (field_01..04) — no recomputation

Outputs (new files, parallel to Neuss):
  data/layer2/kaarst_layer2_input_table.parquet
  data/layer2/kaarst_street_level_ranking_v1.parquet
"""

import json
import math
import logging
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("KAARST_LAYER2_BUILDER")

BASE_DIR   = Path(__file__).resolve().parents[1]
FIELDS_DIR = BASE_DIR / "data" / "fields"
OUT_DIR    = BASE_DIR / "data" / "layer2"

KAARST_FOUNDATION_JSON = BASE_DIR / "output" / "foundation" / "kaarst_foundation_structure_results.json"
FIELD01_PARQ = FIELDS_DIR / "field_01_roof_potential.parquet"
FIELD02_PARQ = FIELDS_DIR / "field_02_building_type.parquet"
FIELD04_PARQ = FIELDS_DIR / "field_04_pv_adoption.parquet"

KAARST_SEGMENT_ID = "KAARST_OSM_41564"
KAARST_PLZ        = "41564"

# Gate thresholds — IDENTICAL to build_layer2_mvp_input_table.py
GATE_DEPLOY_THR   = 0.60
GATE_MIXED_THR    = 0.30

# Stage 1/2 label sets — IDENTICAL to build_layer2_mvp_input_table.py
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
SCALE_NORM_DENOM    = math.log1p(30)
SFH_SCALE_SATURATION = 15


# ── Step 1: Load field data ───────────────────────────────────────────────────

def load_kaarst_fields() -> dict:
    """Returns assembled kaarst field signals dict."""
    signals = {}

    # F01: roof potential
    df_f01 = pd.read_parquet(FIELD01_PARQ)
    k_f01  = df_f01[df_f01["segment_id"] == KAARST_SEGMENT_ID]
    if len(k_f01) == 1:
        r = k_f01.iloc[0]
        signals["roof_suitability_score"]       = float(r["field_value"])
        signals["roof_building_count"]          = int(r["building_count"])
        signals["roof_pool_adjusted_m2"]        = float(r["roof_pool_adjusted_m2"])
        signals["f01_confidence"]               = float(r.get("confidence", 0.85))
        # Normalize roof score to [0,1] — same method as build_layer2:
        # roof_norm = min(1.0, raw_score / 0.45)  (0.45 = detached max utilization rate)
        signals["roof_suitability_score_norm"]  = round(min(1.0, signals["roof_suitability_score"] / 0.45), 4)
    else:
        logger.warning("[F01] No Kaarst record in field_01 — using neutral defaults")
        signals["roof_suitability_score"]       = 0.20
        signals["roof_building_count"]          = 9949
        signals["roof_pool_adjusted_m2"]        = 0.0
        signals["f01_confidence"]               = 0.0
        signals["roof_suitability_score_norm"]  = 0.5

    # F02: building type classification
    df_f02 = pd.read_parquet(FIELD02_PARQ)
    k_f02  = df_f02[df_f02["segment_id"] == KAARST_SEGMENT_ID]
    if len(k_f02) > 0:
        vc = k_f02["field_value"].value_counts()
        n_classified    = len(k_f02)
        n_sfh_confirmed = int(vc.reindex(list(SFH_CONFIRMED_LABELS), fill_value=0).sum())
        n_mfh_confirmed = int(vc.reindex(list(MFH_CONFIRMED_LABELS), fill_value=0).sum())
        n_sfh_weak      = int(vc.reindex(list(SFH_WEAK_LABELS),      fill_value=0).sum())
        n_mfh_suspect   = int(vc.reindex(list(MFH_SUSPECT_LABELS),   fill_value=0).sum())
        n_uncertain     = int(vc.reindex(list(UNCERTAIN_LABELS),     fill_value=0).sum())

        universe_total  = n_classified  # for Kaarst all buildings are in F02 (our extractor)
        sfh_confirmed_share = n_sfh_confirmed / universe_total
        mfh_confirmed_share = n_mfh_confirmed / universe_total
        sfh_friendly_share  = (n_sfh_confirmed + n_sfh_weak) / universe_total
        effective_sfh_share = sfh_confirmed_share  # conservative: Stage 1 confirmed only
        uncertain_share     = n_uncertain / universe_total

        # Dominant form
        counts = {
            "SFH_CONFIRMED": n_sfh_confirmed,
            "MFH_CONFIRMED": n_mfh_confirmed,
            "SFH_WEAK":      n_sfh_weak,
            "MFH_SUSPECT":   n_mfh_suspect,
            "UNCERTAIN":     n_uncertain,
        }
        dominant_form = max(counts, key=counts.get)

        # F02 confidence
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
                f"Source: Kaarst Phase 3 F02 (kaarst_buildings.parquet)."
            ),
        })
    else:
        logger.warning("[F02] No Kaarst records — using neutral defaults")
        signals.update({
            "sfh_confirmed_share": 0.5,
            "mfh_confirmed_share": 0.0,
            "sfh_friendly_share":  0.5,
            "effective_sfh_share": 0.0,
            "uncertain_share":     0.5,
            "dominant_form":       "UNCERTAIN",
            "f02_building_count":  0.0,
            "f02_classified_count": 0.0,
            "f02_confidence":      0.0,
            "f02_classification_note": "NO_DATA",
        })

    # F04: PV adoption score
    df_f04 = pd.read_parquet(FIELD04_PARQ)
    k_f04  = df_f04[df_f04["segment_id"] == KAARST_SEGMENT_ID]
    if len(k_f04) == 1:
        r = k_f04.iloc[0]
        signals["pv_coverage_score"]       = float(r["field_value"])
        signals["pv_coverage_availability"] = "PLZ_ALLOCATION_E3"
        signals["pv_confidence"]            = float(r.get("confidence", 0.45))
        signals["pv_source"]                = str(r.get("source", "PLZ_ALLOCATION_E3"))
    else:
        logger.warning("[F04] No Kaarst PV record — using neutral")
        signals["pv_coverage_score"]       = 0.5
        signals["pv_coverage_availability"] = "MISSING"
        signals["pv_confidence"]            = 0.0
        signals["pv_source"]                = "MISSING"

    return signals


# ── Step 2: Foundation gate aggregation ──────────────────────────────────────

def agg_foundation_gate(clusters_41564: list) -> dict:
    """
    Aggregate structure gate distribution for PLZ 41564.
    Returns {l1_gate_label, pct_l1_gate_pass, sfh_total_ratio_median, l1_cluster_count}.
    Logic identical to build_layer2_mvp_input_table.py.
    """
    n_total = len(clusters_41564)
    if n_total == 0:
        return {"l1_gate_label": "BLOCKED", "pct_l1_gate_pass": 0.0,
                "sfh_total_ratio_median": 0.0, "l1_cluster_count": 0}

    n_pass   = sum(1 for c in clusters_41564 if c["structure_gate"] in ("PASS", "QUALIFIED"))
    pct_pass = n_pass / n_total

    if pct_pass >= GATE_DEPLOY_THR:
        gate_label = "DEPLOYABLE"
    elif pct_pass >= GATE_MIXED_THR:
        gate_label = "MIXED"
    else:
        gate_label = "BLOCKED"

    sfh_ratios = [c["sfh_total_ratio"] for c in clusters_41564 if "sfh_total_ratio" in c]
    sfh_median = round(statistics.median(sfh_ratios), 4) if sfh_ratios else 0.0

    return {
        "l1_gate_label":       gate_label,
        "pct_l1_gate_pass":    round(pct_pass, 4),
        "sfh_total_ratio_median": sfh_median,
        "l1_cluster_count":    n_total,
    }


# ── Step 3: Build Layer2 input table row for Kaarst ──────────────────────────

def build_layer2_table(clusters: list, signals: dict, gate_agg: dict) -> pd.DataFrame:
    """Build a 1-row Layer2 input table for KAARST_OSM_41564."""
    ts = datetime.now(timezone.utc).isoformat()

    lats = [c.get("cluster_centroid_lat", 0) for c in clusters if c.get("cluster_centroid_lat")]
    lons = [c.get("cluster_centroid_lon", 0) for c in clusters if c.get("cluster_centroid_lon")]

    row = {
        "unit_id":                    KAARST_SEGMENT_ID,
        "unit_type":                  "residential_suburban",
        "unit_status":                "REAL_GROUNDED",
        "district_name":              "Kaarst (PLZ 41564)",
        "plz":                        KAARST_PLZ,
        "centroid_lat":               round(sum(lats)/len(lats), 4) if lats else 51.2303,
        "centroid_lon":               round(sum(lons)/len(lons), 4) if lons else 6.6194,
        # Field 01
        "roof_suitability_score":     signals["roof_suitability_score"],
        "roof_building_count":        signals["roof_building_count"],
        "roof_pool_adjusted_m2":      signals["roof_pool_adjusted_m2"],
        "f01_confidence":             signals["f01_confidence"],
        # Field 02
        "sfh_confirmed_share":        signals["sfh_confirmed_share"],
        "mfh_confirmed_share":        signals["mfh_confirmed_share"],
        "uncertain_share":            signals["uncertain_share"],
        "effective_sfh_share":        signals["effective_sfh_share"],
        "sfh_friendly_share":         signals["sfh_friendly_share"],
        "dominant_form":              signals["dominant_form"],
        "f02_building_count":         signals["f02_building_count"],
        "f02_classified_count":       signals["f02_classified_count"],
        "f02_confidence":             signals["f02_confidence"],
        "f02_classification_note":    signals["f02_classification_note"],
        # Foundation gate
        "l1_gate_label":              gate_agg["l1_gate_label"],
        "pct_l1_gate_pass":           gate_agg["pct_l1_gate_pass"],
        "sfh_total_ratio_median":     gate_agg["sfh_total_ratio_median"],
        "l1_cluster_count":           gate_agg["l1_cluster_count"],
        # Field 04
        "pv_coverage_score":          signals["pv_coverage_score"],
        "pv_coverage_availability":   signals["pv_coverage_availability"],
        "pv_confidence":              signals["pv_confidence"],
        "pv_source":                  signals["pv_source"],
        # Usability
        "row_usable_for_ranking":     True,
        "build_timestamp_utc":        ts,
        # Normalized roof
        "roof_suitability_score_norm": signals["roof_suitability_score_norm"],
        "roof_data_available":        True,
        "roof_norm_or_neutral":       signals["roof_suitability_score_norm"],
    }

    return pd.DataFrame([row])


# ── Step 4: Street-level ranking for Kaarst (field_08 logic) ─────────────────

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


def _top_reason(c: dict, sfh_q: float, gate_s: float) -> str:
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


def build_street_ranking(clusters_41564: list, signals: dict) -> pd.DataFrame:
    """
    Applies field_08 scoring logic to Kaarst foundation clusters.
    B-signals sourced from the Kaarst signals dict (same pipeline).
    """
    roof_norm = signals["roof_suitability_score_norm"]
    pv_oppty  = round(min(1.0, max(0.0, signals["pv_coverage_score"])), 4)

    logger.info(f"[F08] B-signals: roof_norm={roof_norm:.3f} pv_oppty={pv_oppty:.3f}")

    # Deduplicate by (plz, street_name) — same as field_08
    seen = set()
    dedup = []
    for c in clusters_41564:
        key = (str(c.get("plz", "")), c.get("street_name", ""))
        if key not in seen:
            seen.add(key)
            dedup.append(c)
    logger.info(f"[F08] {len(clusters_41564)} clusters -> {len(dedup)} unique streets after dedup")

    rows = []
    for c in dedup:
        sfh_q  = _sfh_quality_score(c)
        gate_s = _gate_score(c)
        scale  = _scale_score(c)
        mfh_c  = _mfh_clean_score(c)

        score = round(
            sfh_q  * W_SFH_QUALITY
            + gate_s * W_GATE
            + mfh_c  * W_MFH_CLEAN
            + scale  * W_SCALE
            + roof_norm * W_ROOF_NORM
            + pv_oppty  * W_PV_OPPTY,
            4,
        )

        sfh_n          = int(c.get("sfh_total_count", 0) or 0)
        scale_dampening = round(min(1.0, sfh_n / SFH_SCALE_SATURATION), 4)
        adj_score       = round(score * scale_dampening, 4)  # no segment modifier for single-seg

        rows.append({
            "cluster_id":              c.get("cluster_id"),
            "street_name":             c.get("street_name"),
            "plz":                     c.get("plz"),
            "address_range":           c.get("address_range", ""),
            "segment_id":              KAARST_SEGMENT_ID,
            "segment_rank":            1,  # Only 1 Kaarst segment
            "street_score":            score,
            "scale_dampening":         scale_dampening,
            "adjusted_street_score":   adj_score,
            "segment_fern_modifier":   1.0,   # No Fernwärme data for Kaarst → neutral
            "segment_hp_modifier":     1.0,   # No HP data for Kaarst → neutral
            "segment_certainty":       1.0,
            "segment_combined_modifier": 1.0,
            "sfh_quality_score":       sfh_q,
            "gate_score":              gate_s,
            "mfh_clean_score":         mfh_c,
            "scale_score":             scale,
            "roof_norm_score":         round(roof_norm * W_ROOF_NORM, 4),
            "pv_oppty_score":          round(pv_oppty  * W_PV_OPPTY, 4),
            "b_roof_norm":             round(roof_norm, 3),
            "b_pv_oppty":              round(pv_oppty, 3),
            "structure_gate":          c.get("structure_gate"),
            "structure_profile":       c.get("structure_profile"),
            "sfh_total_ratio":         float(c.get("sfh_total_ratio", 0.0) or 0.0),
            "sfh_detached_count":      int(c.get("sfh_detached_count", 0) or 0),
            "sfh_rowhouse_count":      int(c.get("sfh_rowhouse_count", 0) or 0),
            "sfh_semi_count":          int(c.get("sfh_semi_detached_count", 0) or 0),
            "sfh_total_count":         sfh_n,
            "mfh_count":               int(c.get("mfh_count", 0) or 0),
            "mfh_ratio":               float(c.get("mfh_ratio", 0.0) or 0.0),
            "building_count_total":    int(c.get("building_count_total", 0) or 0),
            "top_reason":              _top_reason(c, sfh_q, gate_s),
            "execution_scale_flag":    c.get("execution_scale_flag"),
            "street_confidence":       c.get("street_confidence"),
        })

    df = pd.DataFrame(rows)

    # Rank within Kaarst (global_rank = rank within this segment only)
    df["global_rank"]     = df["adjusted_street_score"].rank(method="first", ascending=False).astype(int)
    df["rank_in_segment"] = df["street_score"].rank(method="first", ascending=False).astype(int)
    df["priority_sort"]   = df["rank_in_segment"].astype(int)

    # Street quality aggregate (feeds potential future field_07 Kaarst variant)
    df["_n_x_score"] = df["street_score"] * df["building_count_total"]
    street_quality_agg = (
        df["_n_x_score"].sum() / df["building_count_total"].sum()
        if df["building_count_total"].sum() > 0 else 0.0
    )
    df["street_quality_agg"] = round(street_quality_agg, 4)
    df = df.drop(columns="_n_x_score")

    df = df.sort_values("global_rank").reset_index(drop=True)

    logger.info(f"[F08] {len(df)} Kaarst streets ranked. Top 5:")
    for _, r in df.head(5).iterrows():
        logger.info(
            f"  #{int(r['global_rank']):<4} {r['street_name']:<35} "
            f"score={r['street_score']:.3f} adj={r['adjusted_street_score']:.3f} "
            f"gate={r['structure_gate']}"
        )
    logger.info(f"  street_quality_agg (feeds ranking): {street_quality_agg:.4f}")

    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 65)
    logger.info("  Kaarst Phase 4 — Layer2 Builder")
    logger.info("=" * 65)

    # Load foundation
    with open(KAARST_FOUNDATION_JSON, encoding="utf-8") as f:
        all_clusters = json.load(f)

    # Filter to PLZ 41564 only (the canonical Kaarst PLZ)
    clusters_41564 = [c for c in all_clusters if str(c.get("plz", "")) == KAARST_PLZ]
    logger.info(f"[LOAD] {len(all_clusters)} total clusters, {len(clusters_41564)} in PLZ {KAARST_PLZ}")

    # Step 1: Load field signals
    signals = load_kaarst_fields()
    logger.info(f"[SIGNALS] roof_norm={signals['roof_suitability_score_norm']:.3f} "
                f"sfh_friendly={signals['sfh_friendly_share']:.1%} "
                f"pv_score={signals['pv_coverage_score']:.3f}")

    # Step 2: Foundation gate aggregation
    gate_agg = agg_foundation_gate(clusters_41564)
    logger.info(f"[GATE] {gate_agg['l1_gate_label']} | PASS+QUAL={gate_agg['pct_l1_gate_pass']:.1%} "
                f"| clusters={gate_agg['l1_cluster_count']}")

    # Step 3: Build Layer2 input table
    df_l2 = build_layer2_table(clusters_41564, signals, gate_agg)
    l2_path = OUT_DIR / "kaarst_layer2_input_table.parquet"
    df_l2.to_parquet(l2_path, index=False)
    logger.info(f"[SAVE] Layer2 input table -> {l2_path}")

    # Step 4: Street-level ranking
    df_slr = build_street_ranking(clusters_41564, signals)
    slr_path = OUT_DIR / "kaarst_street_level_ranking_v1.parquet"
    df_slr.to_parquet(slr_path, index=False)
    logger.info(f"[SAVE] Street-level ranking -> {slr_path} ({len(df_slr)} streets)")

    logger.info("=" * 65)
    logger.info("  Kaarst Phase 4 DONE")
    logger.info("=" * 65)
    return df_l2, df_slr


if __name__ == "__main__":
    df_l2, df_slr = main()
    print(f"\nLayer2 row: {df_l2[['unit_id','l1_gate_label','pct_l1_gate_pass','pv_coverage_score','sfh_friendly_share']].to_string(index=False)}")
    print(f"\nTop-10 Kaarst streets:")
    print(df_slr[["global_rank","street_name","street_score","adjusted_street_score","structure_gate"]].head(10).to_string(index=False))
