"""
field_08_street_level_ranking.py  — v2 (Logic 1: Global Ranking)
=================================================================
FIELD_08: Global Street-Level PV Opportunity Ranking
D-ESS · Neuss MVP · PV-only

Implements Logic 1: all streets ranked in a SINGLE global list.
Each street receives a composite score combining:
  A-type signals (street-level, high confidence) × 0.70
  B-type signals (segment-level proxy)           × 0.30

Scoring Formula (user-approved 2026-03-29):
  street_score =
    sfh_quality_score  × 0.30   (SFH ratio × subtype quality weight)
    + gate_score       × 0.20   (PASS=1.0 / QUALIFIED=0.8 / REVIEW=0.4 / FAIL=0.0)
    + mfh_clean_score  × 0.10   (1 − mfh_ratio)
    + scale_score      × 0.10   (log-normalised building count)
    + roof_norm_score  × 0.20   (B: roof polygon quality, conf=0.85)
    + pv_oppty_score   × 0.10   (B: 1 − normalised PV penetration, conf=0.45)

Subtype Quality Weights:
  detached (EFH)       → 1.00
  semi-detached (DHH)  → 0.65
  rowhouse (RH)        → 0.50

B-signal sourcing:
  roof_norm_score → layer2_mvp_input_table.parquet :: roof_suitability_score_norm
  pv_oppty_score  → 1 − (pv_coverage_score / PV_SCORE_CAP)
                    low adoption = high opportunity
  B signals are segment-level; Fernwärme + HP applied at segment layer only.

Outputs:
  data/layer2/street_level_ranking_v1.parquet
    · global_rank    : int (1 = best across all segments)
    · rank_in_segment: int (rank within own segment)
    · street_quality_agg_by_segment: float (building-weighted mean per segment → feeds field_05)
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("FIELD_08_STREET_RANK_V2")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR        = Path(__file__).resolve().parents[1]
FOUNDATION_JSON = BASE_DIR / "output" / "foundation" / "foundation_structure_results.json"
LAYER2_TABLE    = BASE_DIR / "data" / "layer2" / "layer2_mvp_input_table.parquet"
SEG_RANK_PARQUET = BASE_DIR / "data" / "layer2" / "street_ranking_v1.parquet"  # field_07 output
OUTPUT_PARQUET  = BASE_DIR / "data" / "layer2" / "street_level_ranking_v1.parquet"

# ---------------------------------------------------------------------------
# Segment ↔ PLZ mapping (source: fields/field_04_pv_adoption.py)
# ---------------------------------------------------------------------------
PLZ_TO_SEGMENT: dict[str, str] = {
    "41470": "NEUSS_NORF_01",
    "41472": "NEUSS_SUBURB_01",
    "41464": "NEUSS_GRIML_01",
}

# PV coverage score cap (E3 max, from field_04)
PV_SCORE_CAP = 0.50   # field_04 E3_MAX_FIELD_VALUE

# Minimum building count for reliable street-level inference
# Streets below this threshold receive a low_sample_flag in the output
LOW_SAMPLE_THRESHOLD = 10

# SFH classification quality thresholds
# A segment is HIGH quality if >50% of buildings have Stage-1 OSM confirmation
# A segment is PROXY  quality if <10% confirmed AND >40% Stage-2 proxy
SFH_HIGH_CONFIRMED_THRESHOLD  = 0.50
SFH_PROXY_CONFIRMED_THRESHOLD = 0.10
SFH_PROXY_SHARE_THRESHOLD     = 0.40

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------
GATE_SCORE: dict[str, float] = {
    "PASS":      1.00,
    "QUALIFIED": 0.80,
    "REVIEW":    0.40,
    "FAIL":      0.00,
}

# Subtype quality weights (user-approved 2026-03-29)
W_DETACHED  = 1.00
W_SEMI      = 0.65
W_ROWHOUSE  = 0.50

# Score composition weights (A=0.70, B=0.30 — user-approved 2026-03-29)
W_SFH_QUALITY  = 0.30   # A
W_GATE         = 0.20   # A
W_MFH_CLEAN    = 0.10   # A
W_SCALE        = 0.10   # A
W_ROOF_NORM    = 0.20   # B  (conf=0.85 polygon geometry)
W_PV_OPPTY     = 0.10   # B  (conf=0.45 MaStR PLZ allocation)

# Scale normalisation: building count ≥ 30 → score 1.0
SCALE_NORM_DENOM = math.log1p(30)

# Neutral B defaults (used when a segment lacks L2 data, or when a signal is
# saturated/unreliable and cannot be used directionally)
B_NEUTRAL: dict = {
    "roof_norm":           0.50,
    "pv_oppty":            0.50,
    "pv_data_saturated":   False,
    "sfh_confirmed_share": 0.50,   # Stage-1 share (OSM adjacency)
    "sfh_proxy_share":     0.00,   # Stage-2 share (footprint heuristic)
    "data_quality":        "MIXED",  # HIGH | PROXY | MIXED
}


# ---------------------------------------------------------------------------
# B-signal loader
# ---------------------------------------------------------------------------

def load_b_signals(l2_path: Path) -> dict[str, dict]:
    """
    Load segment-level B signals from the Layer 2 MVP input table.

    Returns {segment_id: {roof_norm, pv_oppty, pv_data_saturated,
                           sfh_confirmed_share, sfh_proxy_share, data_quality}}.

    pv_oppty = 1 − (pv_coverage_score / PV_SCORE_CAP).
    PV SATURATION RULE: if pv_coverage_score ≥ PV_SCORE_CAP, the signal is
      unreliable (PLZ-level allocation has hit a hard cap, not real saturation).
      In that case pv_oppty is set to B_NEUTRAL['pv_oppty'] (0.50) and
      pv_data_saturated=True is flagged. This prevents a false signal of
      'zero market opportunity' when the root cause is a data cap, not reality.

    DATA QUALITY LABELS:
      HIGH  → sfh_confirmed_share > SFH_HIGH_CONFIRMED_THRESHOLD (Stage-1 OSM)
      PROXY → sfh_confirmed_share < SFH_PROXY_CONFIRMED_THRESHOLD
              AND sfh_proxy_share > SFH_PROXY_SHARE_THRESHOLD (Stage-2 dominant)
      MIXED → everything else
    """
    if not l2_path.exists():
        logger.warning("[B-SIGNALS] Layer 2 table not found: %s. Using neutral defaults.", l2_path)
        return {}

    df = pd.read_parquet(l2_path)
    b: dict[str, dict] = {}
    for _, row in df.iterrows():
        seg = row["unit_id"]
        if not row.get("row_usable_for_ranking", False):
            continue

        # Roof quality (B-signal, polygon geometry)
        roof_raw  = row.get("roof_suitability_score_norm")
        roof_norm = float(roof_raw) if pd.notna(roof_raw) else B_NEUTRAL["roof_norm"]

        # PV opportunity with saturation guard
        pv_raw         = row.get("pv_coverage_score")
        pv_saturated   = False
        if pd.notna(pv_raw) and float(pv_raw) > 0:
            pv_val = float(pv_raw)
            if pv_val >= PV_SCORE_CAP:
                # PLZ allocation hit the hard cap — signal is not directional
                pv_oppty   = B_NEUTRAL["pv_oppty"]  # neutral 0.50
                pv_saturated = True
                logger.warning(
                    "[PV_DATA_SATURATED] %s: pv_coverage_score=%.3f >= cap=%.2f. "
                    "Using neutral pv_oppty=%.2f instead of %.3f to avoid false zero-opportunity signal.",
                    seg, pv_val, PV_SCORE_CAP, B_NEUTRAL["pv_oppty"],
                    1.0 - pv_val / PV_SCORE_CAP,
                )
            else:
                pv_oppty = max(0.0, 1.0 - pv_val / PV_SCORE_CAP)
        else:
            pv_oppty = B_NEUTRAL["pv_oppty"]

        # SFH stage quality (data source transparency)
        sfh_confirmed = float(row.get("sfh_confirmed_share", 0.0))
        sfh_friendly  = float(row.get("sfh_friendly_share", sfh_confirmed))
        sfh_proxy     = max(0.0, sfh_friendly - sfh_confirmed)   # Stage-2 only

        if sfh_confirmed >= SFH_HIGH_CONFIRMED_THRESHOLD:
            data_quality = "HIGH"   # majority Stage-1 OSM confirmed
        elif (sfh_confirmed < SFH_PROXY_CONFIRMED_THRESHOLD
              and sfh_proxy  > SFH_PROXY_SHARE_THRESHOLD):
            data_quality = "PROXY"  # Stage-2 footprint dominant
        else:
            data_quality = "MIXED"

        b[seg] = {
            "roof_norm":           roof_norm,
            "pv_oppty":            pv_oppty,
            "pv_data_saturated":   pv_saturated,
            "sfh_confirmed_share": round(sfh_confirmed, 4),
            "sfh_proxy_share":     round(sfh_proxy, 4),
            "data_quality":        data_quality,
        }
        logger.info(
            "[B-SIGNALS] %s: roof=%.3f pv_oppty=%.3f%s sfh_confirmed=%.0f%% sfh_proxy=%.0f%% quality=%s",
            seg, roof_norm, pv_oppty,
            " [PV_SATURATED]" if pv_saturated else "",
            sfh_confirmed * 100, sfh_proxy * 100, data_quality,
        )
    return b


# ---------------------------------------------------------------------------
# Segment modifier loader (field_07 output)
# ---------------------------------------------------------------------------

NEUTRAL_MODIFIER = {"fern": 1.0, "hp": 1.0, "certainty": 1.0, "combined": 1.0,
                    "hp_confidence": 1.0, "truly_uncertain_share": 0.0}

def load_segment_modifiers(seg_rank_path: Path) -> dict[str, dict]:
    """
    Load fernwaerme_modifier, hp_modifier, structural_certainty, hp_confidence,
    and truly_uncertain_share from field_07 output.
    Applied as a combined multiplier to street_score to produce adjusted_street_score.

    Returns {segment_id: {fern, hp, certainty, combined, hp_confidence,
                           truly_uncertain_share}}.

    ANTI-DOUBLE-COUNT GUARDRAIL:
      street_quality_agg (feeds field_05 base_score) MUST use raw street_score,
      NOT adjusted_street_score. If agg used adjusted scores, field_07 would
      re-apply the same modifiers, causing double-counting.
    """
    if not seg_rank_path.exists():
        logger.warning(
            "[SEG_MODIFIERS] street_ranking_v1.parquet not found at %s. "
            "Segment modifiers defaulting to 1.0 (neutral). "
            "Run field_07_street_ranking.py first.",
            seg_rank_path,
        )
        return {}

    df = pd.read_parquet(seg_rank_path)
    mods: dict[str, dict] = {}
    for _, row in df.iterrows():
        seg_id          = str(row["street_id"])
        fern            = float(row.get("fernwaerme_modifier",  1.0))
        hp              = float(row.get("hp_modifier",          1.0))
        certainty       = float(row.get("structural_certainty", 1.0))
        combined        = round(fern * hp * certainty, 4)
        hp_conf         = float(row.get("confidence",           1.0))  # hp_confidence from field_07
        truly_unc       = float(row.get("truly_uncertain_share", 0.0))
        mods[seg_id] = {
            "fern":                 fern,
            "hp":                   hp,
            "certainty":            certainty,
            "combined":             combined,
            "hp_confidence":        hp_conf,
            "truly_uncertain_share": truly_unc,
        }
        logger.info(
            "[SEG_MODIFIERS] %s: fern=%.2f × hp=%.2f × certainty=%.3f = combined=%.4f "
            "| hp_conf=%.2f truly_unc=%.0f%%",
            seg_id, fern, hp, certainty, combined, hp_conf, truly_unc * 100,
        )
    return mods


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _sfh_quality_score(row: dict) -> float:
    """sfh_total_ratio × quality_within_sfh_subtypes.  Range [0, 1]."""
    sfh_total = row.get("sfh_total_count", 0) or 0
    sfh_ratio = float(row.get("sfh_total_ratio", 0.0) or 0.0)
    if sfh_total == 0 or sfh_ratio == 0:
        return 0.0
    weighted = (
        float(row.get("sfh_detached_count",      0) or 0) * W_DETACHED
        + float(row.get("sfh_semi_detached_count", 0) or 0) * W_SEMI
        + float(row.get("sfh_rowhouse_count",      0) or 0) * W_ROWHOUSE
    )
    return round(sfh_ratio * (weighted / sfh_total), 4)


def _gate_score(row: dict) -> float:
    return GATE_SCORE.get(str(row.get("structure_gate", "FAIL")).upper(), 0.0)


def _scale_score(row: dict) -> float:
    n = int(row.get("building_count_total", 0) or 0)
    return round(min(1.0, math.log1p(n) / SCALE_NORM_DENOM), 4)


def _mfh_clean_score(row: dict) -> float:
    return round(1.0 - float(row.get("mfh_ratio", 0.0) or 0.0), 4)


def _street_score(
    row: dict, roof_norm: float, pv_oppty: float
) -> tuple[float, float, float, float, float]:
    """Returns (total, sfh_q, gate_s, scale_s, mfh_c) for audit."""
    sfh_q  = _sfh_quality_score(row)
    gate_s = _gate_score(row)
    scale  = _scale_score(row)
    mfh_c  = _mfh_clean_score(row)

    total = round(
        sfh_q  * W_SFH_QUALITY
        + gate_s * W_GATE
        + mfh_c  * W_MFH_CLEAN
        + scale  * W_SCALE
        + roof_norm * W_ROOF_NORM
        + pv_oppty  * W_PV_OPPTY,
        4,
    )
    return total, sfh_q, gate_s, scale, mfh_c


def _top_reason(row: dict, sfh_q: float, gate_s: float) -> str:
    sfh_ratio = float(row.get("sfh_total_ratio", 0.0) or 0.0)
    det_count = int(row.get("sfh_detached_count", 0) or 0)
    n         = int(row.get("building_count_total", 1) or 1)
    mfh_ratio = float(row.get("mfh_ratio", 0.0) or 0.0)
    g_label   = str(row.get("structure_gate", "")).upper()

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


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def build_street_ranking() -> tuple[pd.DataFrame, pd.DataFrame]:  # LOW-02 FIX (2026-04-02): was -> pd.DataFrame but returns (df, agg)
    logger.info("=" * 70)
    logger.info("  FIELD_08 v2 — GLOBAL STREET RANKING ENGINE (Logic 1)")
    logger.info(f"  Weights: A(sfh_q={W_SFH_QUALITY}, gate={W_GATE}, mfh_c={W_MFH_CLEAN}, scale={W_SCALE})")
    logger.info(f"           B(roof={W_ROOF_NORM}, pv_oppty={W_PV_OPPTY})")
    logger.info("=" * 70)

    if not FOUNDATION_JSON.exists():
        raise FileNotFoundError(f"Foundation JSON not found: {FOUNDATION_JSON}")

    # Load B signals
    b_signals = load_b_signals(LAYER2_TABLE)

    # Load segment modifiers from field_07 (full coupling)
    seg_modifiers = load_segment_modifiers(SEG_RANK_PARQUET)
    if not seg_modifiers:
        logger.warning(
            "[COUPLING] No segment modifiers loaded — global_rank will be based on "
            "pure street_score only. Run field_07 first for full coupled ranking."
        )

    # Load segment ranks for priority_sort
    seg_rank_map: dict[str, int] = {}  # {segment_id: segment_rank}
    if SEG_RANK_PARQUET.exists():
        _seg_df = pd.read_parquet(SEG_RANK_PARQUET)
        for _, _r in _seg_df.iterrows():
            seg_rank_map[str(_r["street_id"])] = int(_r["rank"])
        logger.info("[SEG_RANK] Loaded segment ranks: %s", seg_rank_map)

    # Load street clusters
    with open(FOUNDATION_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    clusters: list[dict] = []
    if isinstance(raw, dict):
        for v in raw.values():
            if isinstance(v, list):
                clusters.extend(v)
    else:
        clusters = raw

    logger.info(f"[LOAD] {len(clusters)} total street clusters loaded")

    tracked_plzs = set(PLZ_TO_SEGMENT.keys())
    clusters = [c for c in clusters if str(c.get("plz", "")) in tracked_plzs]
    logger.info(f"[FILTER] {len(clusters)} clusters in tracked PLZs {tracked_plzs}")

    rows: list[dict] = []
    for c in clusters:
        plz        = str(c.get("plz", ""))
        segment_id = PLZ_TO_SEGMENT.get(plz, "UNKNOWN")
        b          = b_signals.get(segment_id, B_NEUTRAL)

        roof_norm  = b["roof_norm"]
        pv_oppty   = b["pv_oppty"]

        score, sfh_q, gate_s, scale, mfh_c = _street_score(c, roof_norm, pv_oppty)
        reason = _top_reason(c, sfh_q, gate_s)

        # Apply segment modifiers (full coupling: fern × hp × certainty)
        seg_mod  = seg_modifiers.get(segment_id, NEUTRAL_MODIFIER)
        adj_score = round(score * seg_mod["combined"], 4)

        sfh_total = int(c.get("sfh_total_count", 0) or 0)
        n_total   = int(c.get("building_count_total", 0) or 0)

        rows.append({
            "cluster_id":          c.get("cluster_id"),
            "street_name":         c.get("street_name"),
            "plz":                 plz,
            "address_range":       c.get("address_range", ""),
            "segment_id":          segment_id,
            "segment_rank":        seg_rank_map.get(segment_id, 99),  # from field_07
            # Composite scores
            "street_score":         score,       # pure building quality (A+B signals)
            "adjusted_street_score": adj_score,  # street_score × segment modifiers (for global_rank)
            # Segment modifier audit trail
            "segment_fern_modifier": seg_mod["fern"],
            "segment_hp_modifier":   seg_mod["hp"],
            "segment_certainty":     seg_mod["certainty"],
            "segment_combined_modifier": seg_mod["combined"],
            # Score components (for audit / UI display)
            "sfh_quality_score":   sfh_q,
            "gate_score":          gate_s,
            "mfh_clean_score":     mfh_c,
            "scale_score":         scale,
            "roof_norm_score":     round(roof_norm * W_ROOF_NORM, 4),   # weighted contribution
            "pv_oppty_score":      round(pv_oppty  * W_PV_OPPTY, 4),   # weighted contribution
            # B raw values (for display)
            "b_roof_norm":         round(roof_norm, 3),
            "b_pv_oppty":          round(pv_oppty, 3),
            # Foundation labels
            "structure_gate":      c.get("structure_gate"),
            "structure_profile":   c.get("structure_profile"),
            # SFH/MFH breakdown
            "sfh_total_ratio":     float(c.get("sfh_total_ratio", 0.0) or 0.0),
            "sfh_detached_count":  int(c.get("sfh_detached_count", 0) or 0),
            "sfh_rowhouse_count":  int(c.get("sfh_rowhouse_count", 0) or 0),
            "sfh_semi_count":      int(c.get("sfh_semi_detached_count", 0) or 0),
            "sfh_total_count":     sfh_total,
            "mfh_count":           int(c.get("mfh_count", 0) or 0),
            "mfh_ratio":           float(c.get("mfh_ratio", 0.0) or 0.0),
            "building_count_total": n_total,
            # Derived ratios (UI)
            "sfh_detached_ratio":  round(int(c.get("sfh_detached_count", 0) or 0) / max(n_total, 1), 3),
            "sfh_rowhouse_ratio":  round(int(c.get("sfh_rowhouse_count", 0) or 0) / max(n_total, 1), 3),
            "sfh_semi_ratio":      round(int(c.get("sfh_semi_detached_count", 0) or 0) / max(n_total, 1), 3),
            # Context
            "top_reason":          reason,
            "execution_scale_flag": c.get("execution_scale_flag"),
            "street_confidence":   c.get("street_confidence"),
            "sales_story":         c.get("sales_story", ""),
            # Data quality & audit fields
            "low_sample_flag":          n_total < LOW_SAMPLE_THRESHOLD,
            "pv_data_saturated":        b.get("pv_data_saturated", False),
            "sfh_stage1_share":         b.get("sfh_confirmed_share", B_NEUTRAL["sfh_confirmed_share"]),
            "sfh_stage2_share":         b.get("sfh_proxy_share",     B_NEUTRAL["sfh_proxy_share"]),
            "data_quality_note":  (
                "Stage-1 confirmed (OSM adjacency)"
                if b.get("data_quality") == "HIGH"
                else "Stage-2 proxy (footprint heuristic)"
                if b.get("data_quality") == "PROXY"
                else "Stage-1 + Stage-2 composite"
            ),
            # Segment-level context for ROI generator (sourced from field_07 via modifier dict)
            "hp_confidence":            seg_mod.get("hp_confidence",        NEUTRAL_MODIFIER["hp_confidence"]),
            "seg_truly_uncertain_share": seg_mod.get("truly_uncertain_share", NEUTRAL_MODIFIER["truly_uncertain_share"]),
        })

    df = pd.DataFrame(rows)

    # Global rank based on ADJUSTED score (building quality × segment market signals)
    df["global_rank"] = (
        df["adjusted_street_score"].rank(method="first", ascending=False).astype(int)
    )

    # Within-segment rank: use raw street_score
    # (all streets in a segment share the same modifier -> adjusted order identical)
    # Raw score keeps within-segment comparison free from uniform constant scaling.
    df["rank_in_segment"] = (
        df.groupby("segment_id")["street_score"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    # Priority sort: segment strategy first, then within-segment quality
    # priority_sort = (segment_rank - 1) * 1000 + rank_in_segment
    # → NORF (segment #1) streets appear before all SUBURB (segment #2) streets
    # → Used by UI "Strategy View" default — does NOT change global_rank scoring
    df["priority_sort"] = (
        (df["segment_rank"] - 1) * 1000 + df["rank_in_segment"]
    ).astype(int)

    logger.info("[PRIORITY_SORT] Strategy-first ordering (segment_rank, rank_in_segment):")
    for _, r in df.sort_values("priority_sort").head(10).iterrows():
        logger.info(
            "  prio=%d  [seg#%d/%s]  #%d  %s  adj_score=%.3f",
            int(r["priority_sort"]), int(r["segment_rank"]), r["segment_id"],
            int(r["rank_in_segment"]), r["street_name"], r["adjusted_street_score"],
        )

    # Compute street_quality_agg per segment (building-count-weighted mean of RAW street_score)
    # ANTI-DOUBLE-COUNT: MUST use street_score (not adjusted_street_score).
    # adjusted_street_score already embeds fern × hp × certainty.
    # field_05 reads this agg as base_score, then field_07 applies those modifiers again.
    # Using adjusted_score here would cause double-counting in the field_05 → field_07 chain.
    df["_n_x_score"] = df["street_score"] * df["building_count_total"]
    agg = (
        df.groupby("segment_id").agg(
            street_quality_agg=("_n_x_score", "sum"),
            _n_total=("building_count_total", "sum"),
        )
    )
    agg["street_quality_agg"] = (agg["street_quality_agg"] / agg["_n_total"]).round(4)
    agg = agg.drop(columns="_n_total").reset_index()

    # Merge agg back for reference (one value per segment, repeated per street)
    df = df.merge(agg, on="segment_id", how="left").drop(columns="_n_x_score")

    df = df.sort_values("global_rank").reset_index(drop=True)

    # Audit log
    logger.info("[AUDIT] Segment aggregation (street_quality_agg):")
    for _, r in agg.iterrows():
        seg_df = df[df["segment_id"] == r["segment_id"]]
        passes = (seg_df["structure_gate"] == "PASS").sum()
        fails  = (seg_df["structure_gate"] == "FAIL").sum()
        logger.info(
            f"  {r['segment_id']:<20} street_quality_agg={r['street_quality_agg']:.4f} "
            f"| {len(seg_df)} streets | PASS={passes} FAIL={fails}"
        )

    logger.info(f"[GLOBAL] Top-10 streets:")
    for _, r in df.head(10).iterrows():
        logger.info(
            f"  #{int(r['global_rank']):<4} {r['street_name']:<35} "
            f"({r['segment_id']:<20}) score={r['street_score']:.3f} "
            f"gate={r['structure_gate']}"
        )

    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PARQUET, index=False)

    ts = datetime.now(timezone.utc).isoformat()
    logger.info(f"[OUTPUT] {len(df)} street rows → {OUTPUT_PARQUET}")
    logger.info(f"[OUTPUT] Build timestamp: {ts}")
    logger.info("=" * 70)
    logger.info("  FIELD_08 v2 DONE")
    logger.info("=" * 70)
    return df, agg


if __name__ == "__main__":
    result, agg = build_street_ranking()
    print("\n" + "=" * 75)
    print("  GLOBAL TOP-15 STREETS")
    print("=" * 75)
    for _, r in result.head(15).iterrows():
        print(
            f"  #{int(r['global_rank']):<4} {r['street_name']:<35} "
            f"[{r['segment_id']:<20}] "
            f"score={r['street_score']:.3f}  gate={r['structure_gate']:<10} "
            f"sfh={r['sfh_total_ratio']:.0%}  n={r['building_count_total']}"
        )
    print("\n" + "=" * 75)
    print("  SEGMENT AGGREGATION (-> feeds field_05)")
    print("=" * 75)
    for _, r in agg.iterrows():
        print(f"  {r['segment_id']:<22} street_quality_agg = {r['street_quality_agg']:.4f}")
    print("=" * 75)
