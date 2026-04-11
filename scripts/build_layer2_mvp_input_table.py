"""
build_layer2_mvp_input_table.py
================================
Layer 2 PV-only MVP Input Table Builder

Mode    : EXECUTION — assembles real agg + direct-attach inputs
Guardrails:
  - No scoring, no ranking, no weight selection
  - Only 4 in-scope inputs: field_01, field_02, foundation gate, field_04
  - NEUSS_NORF_01 is the only REAL_GROUNDED row
  - SYNTHETIC segments get stub rows with NULLs and row_usable_for_ranking=False

Produces
--------
  data/layer2/layer2_mvp_input_table.parquet       <- machine-readable MVP table
  output/layer2/LAYER2_MVP_INPUT_TABLE_<ts>.md     <- human-readable summary
"""

import json
import logging
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("LAYER2_BUILDER")

BASE_DIR     = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIELD01_PARQ = BASE_DIR / "data" / "fields" / "field_01_roof_potential.parquet"
FIELD02_PARQ = BASE_DIR / "data" / "fields" / "field_02_building_type.parquet"
FIELD04_PARQ = BASE_DIR / "data" / "fields" / "field_04_pv_adoption.parquet"
FOUNDATION   = BASE_DIR / "output" / "foundation" / "foundation_structure_results.json"
SEG_REG      = BASE_DIR / "output" / "stage6" / "segment_registry_neuss_v1.json"
OUT_PARQ_DIR = BASE_DIR / "data" / "layer2"
OUT_MD_DIR   = BASE_DIR / "output" / "layer2"

REAL_GROUNDED_PLZ_MAP  = {
    "NEUSS_NORF_01":   "41470",   # PLZ from field_04 PILOT_DEFAULTS (verified)
    "NEUSS_SUBURB_01": "41472",   # PLZ confirmed from OSM extraction (expansion round 1)
    "NEUSS_GRIML_01":  "41464",   # PLZ confirmed from OSM extraction (expansion round 2)
}
# Mapping from legacy persistent_id → current segment_id
# Source: segment_registry_neuss_v1.json — each segment has a persistent_id field
PERSISTENT_TO_SEGMENT = {
    "ALLERHEILIGEN_PILOT_SEG_01": "NEUSS_NORF_01",
    "NEUSS_DENSE_01":             "NEUSS_GRIML_01",
    "NEUSS_VILLA_01":             "NEUSS_CENTRAL_01",
    "NEUSS_OLD_TOWN_01":          "NEUSS_OLD_TOWN_01",
    "NEUSS_SUBURBAN_01":          "NEUSS_SUBURB_01",
}

GATE_DEPLOY_THR   = 0.60      # >= 60% PASS clusters → DEPLOYABLE
GATE_MIXED_THR    = 0.30      # >= 30% PASS clusters → MIXED (else BLOCKED)

# Stage 1/2 output label sets from field_02_building_type.py
SFH_CONFIRMED_LABELS = frozenset({"SFH_CONFIRMED"})
MFH_CONFIRMED_LABELS = frozenset({"MFH_CONFIRMED"})
SFH_WEAK_LABELS      = frozenset({"SFH_WEAK"})
MFH_SUSPECT_LABELS   = frozenset({"MFH_SUSPECT"})
UNCERTAIN_LABELS     = frozenset({"UNCERTAIN"})
# Legacy (pre-Stage1/2): labels from old adjacency-only path
_LEGACY_SFH_TYPES    = frozenset({"detached", "semi", "rowhouse"})

# ---------------------------------------------------------------------------
# Step 0 — Load segment registry
# ---------------------------------------------------------------------------

def load_segment_registry() -> dict:
    """Returns {segment_id: segment_dict} for all segments."""
    with open(SEG_REG, encoding="utf-8") as f:
        data = json.load(f)
    segments = data.get("segments", [])
    return {s["segment_id"]: s for s in segments}


# ---------------------------------------------------------------------------
# Step 1 — field_02 groupby → sfh_friendly_share, dominant_form
# ---------------------------------------------------------------------------

def agg_field02() -> dict:
    """
    Returns {segment_id: {sfh_friendly_share, dominant_form, f02_building_count,
                          f02_confidence, f02_note}}
    """
    logger.info("[STEP 1] Loading field_02 parquet...")
    df = pd.read_parquet(FIELD02_PARQ)
    logger.info(f"[STEP 1] field_02: {len(df)} building rows, "
                f"segments: {df['segment_id'].unique().tolist()}")

    result = {}
    # Translate legacy persistent_ids → current segment_ids before groupby
    df["segment_id"] = df["segment_id"].map(
        lambda x: PERSISTENT_TO_SEGMENT.get(x, x)
    )
    logger.info(f"[STEP 1] After translation, segments: {df['segment_id'].unique().tolist()}")
    for seg_id, grp in df.groupby("segment_id"):
        n_total = len(grp)
        vc      = grp["field_value"].value_counts()

        # Stage 1/2 confirmed counts
        n_sfh_confirmed = int(vc.reindex(list(SFH_CONFIRMED_LABELS), fill_value=0).sum())
        n_mfh_confirmed = int(vc.reindex(list(MFH_CONFIRMED_LABELS), fill_value=0).sum())
        n_sfh_weak      = int(vc.reindex(list(SFH_WEAK_LABELS),      fill_value=0).sum())
        n_mfh_suspect   = int(vc.reindex(list(MFH_SUSPECT_LABELS),   fill_value=0).sum())
        # Legacy labels (ALLERHEILIGEN_PILOT_SEG_01 rows if Stage 1/2 not yet run)
        n_legacy_sfh    = int(vc.reindex(list(_LEGACY_SFH_TYPES),    fill_value=0).sum())

        # Conservative formula (fail-closed): only Stage 1 confirmed count
        sfh_confirmed_share = round(n_sfh_confirmed / n_total, 4) if n_total > 0 else None
        mfh_confirmed_share = round(n_mfh_confirmed / n_total, 4) if n_total > 0 else None
        uncertain_share     = round(
            (n_total - n_sfh_confirmed - n_mfh_confirmed) / n_total, 4
        ) if n_total > 0 else None
        # Ranking field — conservative (sfh_confirmed only)
        effective_sfh_share = sfh_confirmed_share
        # Legacy field: SFH_CONFIRMED + SFH_WEAK + legacy detached/semi/rowhouse
        sfh_friendly_share  = round(
            (n_sfh_confirmed + n_sfh_weak + n_legacy_sfh) / n_total, 4
        ) if n_total > 0 else None

        dominant = grp["field_value"].mode().iloc[0] if n_total > 0 else None

        # Confidence depends on geometry source
        is_point_geom = seg_id in {s for s in REAL_GROUNDED_PLZ_MAP if s != "NEUSS_NORF_01"}
        if is_point_geom:
            f02_conf = 0.70
            f02_source = "osm_building_tag_proxy_v1"
            f02_note_text = (
                f"Stage 1/2 label counts: SFH_CONFIRMED={n_sfh_confirmed} "
                f"MFH_CONFIRMED={n_mfh_confirmed} SFH_WEAK={n_sfh_weak} "
                f"MFH_SUSPECT={n_mfh_suspect} UNCERTAIN={n_total-n_sfh_confirmed-n_mfh_confirmed-n_sfh_weak-n_mfh_suspect}. "
                "Source: OSM building tag (POINT geometry). "
                "UNCERTAIN = fail-closed (tag absent or ambiguous)."
            )
        else:
            f02_conf = 0.90
            f02_source = "spatial_adjacency_v2"
            f02_note_text = (
                f"Stage 1/2 label counts: SFH_CONFIRMED={n_sfh_confirmed} "
                f"MFH_CONFIRMED={n_mfh_confirmed} SFH_WEAK={n_sfh_weak} "
                f"MFH_SUSPECT={n_mfh_suspect} UNCERTAIN={n_total-n_sfh_confirmed-n_mfh_confirmed-n_sfh_weak-n_mfh_suspect}. "
                "Source: spatial adjacency + Stage 2 footprint fallback. "
                "Adjacency buffer=~1m. effective_sfh_share is conservative (Stage 1 only)."
            )

        result[seg_id] = {
            "sfh_confirmed_share":  sfh_confirmed_share,
            "mfh_confirmed_share":  mfh_confirmed_share,
            "uncertain_share":      uncertain_share,
            "effective_sfh_share":  effective_sfh_share,
            "sfh_friendly_share":   sfh_friendly_share,   # legacy
            "dominant_form":        dominant,
            "f02_building_count":   n_total,
            "f02_confidence":       f02_conf,
            "f02_source":           f02_source,
            "f02_note":             f02_note_text,
        }
        logger.info(
            f"[STEP 1] {seg_id}: {n_total} bldgs "
            f"sfh_confirmed={sfh_confirmed_share:.2%} "
            f"mfh_confirmed={mfh_confirmed_share:.2%} "
            f"uncertain={uncertain_share:.2%} "
            f"effective_sfh={effective_sfh_share:.2%} "
            f"(legacy sfh_friendly={sfh_friendly_share:.2%})"
        )
    return result


# ---------------------------------------------------------------------------
# Step 2 — Foundation gate PLZ bridge for NEUSS_NORF_01
# ---------------------------------------------------------------------------

def agg_foundation_gate(plz: str) -> dict:
    """
    Scans foundation_structure_results.json, filters by PLZ=plz,
    aggregates street-cluster gate stats.

    Returns dict with gate fields, or a NOT_AVAILABLE record if PLZ not found.

    Caveat: join is PLZ-proxied, not segment_id key join.
    Valid only because PLZ 41470 ≅ NEUSS_NORF_01 territory.
    """
    logger.info(f"[STEP 2] Loading foundation JSON for PLZ={plz}...")
    with open(FOUNDATION, encoding="utf-8") as f:
        data = json.load(f)

    # Foundation is either a list or dict — handle both
    if isinstance(data, dict):
        clusters = []
        for v in data.values():
            if isinstance(v, list):
                clusters.extend(v)
    elif isinstance(data, list):
        clusters = data
    else:
        clusters = []

    plz_clusters = [c for c in clusters if str(c.get("plz", "")).strip() == plz]
    logger.info(f"[STEP 2] Found {len(plz_clusters)} street-clusters for PLZ={plz}")

    if not plz_clusters:
        logger.warning(f"[STEP 2] No clusters found for PLZ={plz}. Gate = NOT_AVAILABLE.")
        return {
            "l1_gate_label":          "NOT_AVAILABLE",
            "pct_l1_gate_pass":       None,
            "sfh_total_ratio_median": None,
            "l1_cluster_count":       0,
            "l1_gate_note": (
                f"No foundation street-clusters found for PLZ={plz}. "
                "Cannot derive gate label. Join method: PLZ proxy bridge (no segment_id in foundation JSON)."
            ),
        }

    n_total  = len(plz_clusters)
    n_pass   = sum(1 for c in plz_clusters if c.get("structure_gate") == "PASS")
    pct_pass = round(n_pass / n_total, 4)
    ratios   = [c.get("sfh_total_ratio", 0.0) for c in plz_clusters]
    median_r = round(statistics.median(ratios), 4) if ratios else None

    if pct_pass >= GATE_DEPLOY_THR:
        gate_label = "DEPLOYABLE"
    elif pct_pass >= GATE_MIXED_THR:
        gate_label = "MIXED"
    else:
        gate_label = "BLOCKED"

    profiles = {}
    for c in plz_clusters:
        p = c.get("structure_profile", "unknown")
        profiles[p] = profiles.get(p, 0) + 1

    logger.info(f"[STEP 2] PLZ={plz}: {n_pass}/{n_total} PASS ({pct_pass:.1%}) → gate={gate_label}")
    logger.info(f"[STEP 2] Profiles: {profiles}")

    return {
        "l1_gate_label":          gate_label,
        "pct_l1_gate_pass":       pct_pass,
        "sfh_total_ratio_median": median_r,
        "l1_cluster_count":       n_total,
        "l1_gate_note": (
            f"PLZ={plz}: {n_pass}/{n_total} clusters PASS ({pct_pass:.1%}). "
            f"Profiles: {profiles}. sfh_ratio_median={median_r}. "
            "⚠️ Join method: PLZ proxy bridge — no segment_id in foundation JSON. "
            "Valid only while PLZ 41470 ≅ NEUSS_NORF_01 territory."
        ),
    }


# ---------------------------------------------------------------------------
# Step 3 — Load field_01 and field_04
# ---------------------------------------------------------------------------

def load_field01() -> dict:
    """Returns {segment_id: row_dict}, translated via PERSISTENT_TO_SEGMENT."""
    logger.info("[STEP 3a] Loading field_01 parquet...")
    df = pd.read_parquet(FIELD01_PARQ)
    result = {}
    for _, row in df.iterrows():
        raw_id = row["segment_id"]
        seg_id = PERSISTENT_TO_SEGMENT.get(raw_id, raw_id)   # translate
        result[seg_id] = {
            "roof_suitability_score":  row["field_value"],
            "roof_building_count":     row.get("building_count", None),
            "roof_pool_adjusted_m2":   row.get("roof_pool_adjusted_m2", None),
            "f01_confidence":          row.get("confidence", 0.85),
        }
    logger.info(f"[STEP 3a] field_01 segments mapped: {list(result.keys())}")
    return result


def load_field04() -> dict:
    """Returns {segment_id: row_dict}."""
    logger.info("[STEP 3b] Loading field_04 parquet...")
    df = pd.read_parquet(FIELD04_PARQ)
    result = {}
    for _, row in df.iterrows():
        result[row["segment_id"]] = {
            "pv_coverage_score":       row["field_value"],
            "pv_coverage_availability": "AVAILABLE_E3",
            "pv_confidence":           row.get("confidence", 0.45),
            "pv_source":               row.get("source", "PLZ_ALLOCATION_E3"),
        }
    logger.info(f"[STEP 3b] field_04 segments found: {list(result.keys())}")
    return result


# ---------------------------------------------------------------------------
# Step 4 — Assemble rows
# ---------------------------------------------------------------------------

def assemble_table(
    segments: dict,
    f01: dict,
    f02: dict,
    f04: dict,
    foundation_gates: dict,   # {plz: gate_dict}
) -> pd.DataFrame:
    """Assemble one row per segment. REAL_GROUNDED gets all 4 inputs; SYNTHETIC gets stubs.

    Normalization (Option B fix, 2026-03-27):
        roof_suitability_score (raw ratio from field_01) is post-processed into
        roof_suitability_score_norm using min-max across REAL_GROUNDED rows only.
        SYNTHETIC rows receive NULL for roof_suitability_score_norm.
        The raw column is preserved unchanged for full auditability.
    """
    rows = []
    ts = datetime.now(timezone.utc).isoformat()

    for seg_id, seg in segments.items():
        status  = seg.get("status", "SYNTHETIC")
        plz     = REAL_GROUNDED_PLZ_MAP.get(seg_id, "")
        dist    = seg.get("district", seg.get("district_name", ""))
        u_type  = seg.get("segment_type", seg.get("type", ""))
        cx      = seg.get("centroid_lat", seg.get("centroid", {}).get("lat"))
        cy      = seg.get("centroid_lon", seg.get("centroid", {}).get("lon"))

        if status == "REAL_GROUNDED":
            # ── field_01 ─────────────────────────────────────────────────
            r1 = f01.get(seg_id, {})

            # ── field_02 ─────────────────────────────────────────────────
            r2 = f02.get(seg_id, {})

            # ── foundation gate (via PLZ bridge) ─────────────────────────
            gate = foundation_gates.get(plz, {})
            if not gate:
                gate = {
                    "l1_gate_label":          "NOT_AVAILABLE",
                    "pct_l1_gate_pass":       None,
                    "sfh_total_ratio_median": None,
                    "l1_cluster_count":       0,
                    "l1_gate_note":           "PLZ not found in foundation aggregation.",
                }

            # ── field_04 ─────────────────────────────────────────────────
            r4 = f04.get(seg_id, {
                "pv_coverage_score":        None,
                "pv_coverage_availability": "NOT_AVAILABLE",
                "pv_confidence":            None,
                "pv_source":                None,
            })

            row_usable = (
                r1.get("roof_suitability_score") is not None and
                r2.get("effective_sfh_share") is not None and
                gate.get("l1_gate_label") not in ("NOT_AVAILABLE",) and
                r4.get("pv_coverage_score") is not None
            )

        else:
            # SYNTHETIC — stub row
            r1   = {}
            r2   = {}
            gate = {"l1_gate_label": "NOT_AVAILABLE", "pct_l1_gate_pass": None,
                    "sfh_total_ratio_median": None, "l1_cluster_count": 0,
                    "l1_gate_note": "SYNTHETIC segment — no real gate computed."}
            r4   = {"pv_coverage_score": None, "pv_coverage_availability": "NOT_AVAILABLE",
                    "pv_confidence": None, "pv_source": None}
            row_usable = False

        rows.append({
            # Identity
            "unit_id":              seg_id,
            "unit_type":            u_type,
            "unit_status":          status,
            "district_name":        dist,
            "plz":                  plz,
            "centroid_lat":         cx,
            "centroid_lon":         cy,
            # field_01 (raw — preserved for audit)
            "roof_suitability_score":  r1.get("roof_suitability_score"),
            "roof_building_count":     r1.get("roof_building_count"),
            "roof_pool_adjusted_m2":   r1.get("roof_pool_adjusted_m2"),
            "f01_confidence":          r1.get("f01_confidence"),
            # field_02
            "sfh_confirmed_share":     r2.get("sfh_confirmed_share"),
            "mfh_confirmed_share":     r2.get("mfh_confirmed_share"),
            "uncertain_share":         r2.get("uncertain_share"),
            "effective_sfh_share":     r2.get("effective_sfh_share"),
            "sfh_friendly_share":      r2.get("sfh_friendly_share"),   # legacy
            "dominant_form":           r2.get("dominant_form"),
            "f02_building_count":      r2.get("f02_building_count"),
            "f02_confidence":          r2.get("f02_confidence"),
            "f02_classification_note": r2.get("f02_note"),
            # foundation gate
            "l1_gate_label":           gate.get("l1_gate_label"),
            "pct_l1_gate_pass":        gate.get("pct_l1_gate_pass"),
            "sfh_total_ratio_median":  gate.get("sfh_total_ratio_median"),
            "l1_cluster_count":        gate.get("l1_cluster_count"),
            "l1_gate_note":            gate.get("l1_gate_note"),
            # field_04
            "pv_coverage_score":       r4.get("pv_coverage_score"),
            "pv_coverage_availability": r4.get("pv_coverage_availability"),
            "pv_confidence":           r4.get("pv_confidence"),
            "pv_source":               r4.get("pv_source"),
            # meta
            "row_usable_for_ranking":  row_usable,
            "build_timestamp_utc":     ts,
        })

    df = pd.DataFrame(rows)

    # ── Option B Normalization (2026-03-27) ───────────────────────────────────
    # Normalize roof_suitability_score to [0, 1] using min-max across
    # REAL_GROUNDED rows only. SYNTHETIC rows receive NULL (no inference).
    #
    # Guardrails:
    #   - Only REAL_GROUNDED rows participate in min/max calculation.
    #   - If all real rows are identical (max == min → degenerate), all get 0.5.
    #   - If only 1 real row exists, it gets 1.0 (best in universe = top).
    #   - Raw column `roof_suitability_score` is NEVER modified (full audit trail).
    #   - Result stored in new column `roof_suitability_score_norm`.
    # ─────────────────────────────────────────────────────────────────────────
    real_mask = df["unit_status"] == "REAL_GROUNDED"
    real_scores = df.loc[real_mask, "roof_suitability_score"].dropna()

    if len(real_scores) == 0:
        logger.warning(
            "[NORM] No REAL_GROUNDED rows with valid roof_suitability_score found. "
            "roof_suitability_score_norm will be NULL for all rows."
        )
        df["roof_suitability_score_norm"] = None
    elif len(real_scores) == 1:
        logger.warning(
            "[NORM] Only 1 REAL_GROUNDED row available. "
            "roof_suitability_score_norm set to 1.0 (sole segment = top of universe)."
        )
        df["roof_suitability_score_norm"] = None
        df.loc[real_mask & df["roof_suitability_score"].notna(), "roof_suitability_score_norm"] = 1.0
    else:
        s_min = real_scores.min()
        s_max = real_scores.max()
        logger.info(
            f"[NORM] roof_suitability_score min-max over {len(real_scores)} real segments: "
            f"min={s_min:.6f}, max={s_max:.6f}"
        )
        if s_max == s_min:
            logger.warning(
                "[NORM] Degenerate case: all real scores are identical. "
                "Setting roof_suitability_score_norm = 0.5 for all real rows."
            )
            df["roof_suitability_score_norm"] = None
            df.loc[real_mask, "roof_suitability_score_norm"] = 0.5
        else:
            df["roof_suitability_score_norm"] = None
            df.loc[real_mask, "roof_suitability_score_norm"] = df.loc[real_mask, "roof_suitability_score"].apply(
                lambda v: round((v - s_min) / (s_max - s_min), 4) if pd.notna(v) else None
            )
            # Post-normalization audit log (one line per real segment)
            for _, row in df[real_mask].iterrows():
                raw  = row["roof_suitability_score"]
                norm = row["roof_suitability_score_norm"]
                logger.info(
                    f"[NORM] {row['unit_id']}: raw={raw:.6f} → norm={norm:.4f} "
                    f"(min={s_min:.6f}, max={s_max:.6f})"
                )

    # FIX 2 (2026-04-02): Explicit data-availability flag.
    # roof=0 confirmed to mean DATA MISSING, not bad suitability.
    # roof_data_available=False → downstream uses neutral 0.5, NOT 0.0.
    # roof_norm_or_neutral: safe scoring input (never NULL or 0 due to data gap).
    df["roof_data_available"]  = df["roof_suitability_score"].notna() & (df["roof_suitability_score"] > 0)
    df["roof_norm_or_neutral"] = df["roof_suitability_score_norm"].fillna(0.5).round(4)
    logger.info(
        "[FIX2] roof_data_available / roof_norm_or_neutral:\n%s",
        df[["unit_id", "roof_suitability_score", "roof_suitability_score_norm",
            "roof_data_available", "roof_norm_or_neutral"]].to_string(index=False),
    )

    return df


# ---------------------------------------------------------------------------
# Markdown summary renderer
# ---------------------------------------------------------------------------

def render_md_summary(df: pd.DataFrame) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n_rows    = len(df)
    n_usable  = df["row_usable_for_ranking"].sum()
    n_real    = (df["unit_status"] == "REAL_GROUNDED").sum()
    n_synth   = (df["unit_status"] == "SYNTHETIC").sum()

    lines = [
        "# Layer 2 MVP Input Table — Build Summary",
        f"",
        f"**Built:** {ts}",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total rows | {n_rows} |",
        f"| REAL_GROUNDED rows | {n_real} |",
        f"| SYNTHETIC stub rows | {n_synth} |",
        f"| **row_usable_for_ranking = True** | **{n_usable}** |",
        f"| Table classification | {'SINGLE_ROW_OPERATIONAL' if n_usable == 1 else 'PARTIAL_MULTI_ROW_EXPLORATORY' if n_usable > 1 else 'SCHEMA_ONLY_USABLE'} |",
        f"",
        "---",
        "",
        "## Rows",
        "",
    ]

    # Per-row table
    display_cols = [
        "unit_id", "unit_status", "roof_suitability_score", "sfh_friendly_share",
        "dominant_form", "l1_gate_label", "pct_l1_gate_pass",
        "pv_coverage_score", "pv_coverage_availability", "row_usable_for_ranking",
    ]
    header = "| " + " | ".join(display_cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(display_cols)) + " |"
    lines += [header, sep]
    for _, row in df.iterrows():
        vals = []
        for c in display_cols:
            v = row[c]
            if v is None or (isinstance(v, float) and __import__("math").isnan(v)):
                vals.append("NULL")
            elif isinstance(v, float):
                vals.append(f"{v:.4f}")
            elif isinstance(v, bool):
                vals.append("✅ TRUE" if v else "❌ FALSE")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")

    lines += [
        "",
        "---",
        "",
        "## Key Caveats",
        "",
        "1. **foundation gate** join is PLZ-proxied — valid only while PLZ 41470 ≅ NEUSS_NORF_01 territory.",
        "2. **field_02 sfh_friendly_share** confidence is per-building (0.90), not aggregate — adjacency classification has known edge cases.",
        "3. **field_04 pv_coverage_score** is E3-capped at 0.50, confidence=0.45 — use as weak modifier only.",
        "4. **field_01 roof_suitability_score** is a raw area ratio (adjusted_area/segment_area_proxy), preserved unchanged. "
        "The normalized counterpart **roof_suitability_score_norm** (min-max, REAL_GROUNDED only) is in [0, 1] and safe to use for ranking.",
        "5. **SYNTHETIC rows have row_usable_for_ranking=False** — do not include in Layer 2 ranking until real data is available.",
        "",
        "## Next Step",
        "",
        "This table is a **SINGLE_ROW_OPERATIONAL MVP prototype**. It validates the schema and aggregation logic.",
        "Before expanding to multi-segment ranking:",
        "- Acquire real OSM building data for additional Neuss districts",
        "- Build `cluster_id → segment_id` mapping table for foundation gate",
        "- Obtain real field_04 coverage for additional real-grounded segments",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("=" * 60)
    logger.info("  LAYER 2 MVP INPUT TABLE BUILDER")
    logger.info("=" * 60)

    # Load segment registry
    logger.info("[0/4] Loading segment registry...")
    segments = load_segment_registry()
    logger.info(f"[0/4] {len(segments)} segments: {list(segments.keys())}")

    # Step 1 — field_02 aggregation
    f02 = agg_field02()

    # Step 2 — Foundation gate per PLZ (use REAL_GROUNDED_PLZ_MAP for real segments)
    plzs_needed = set()
    for seg_id, seg in segments.items():
        if seg.get("status") == "REAL_GROUNDED":
            plz = REAL_GROUNDED_PLZ_MAP.get(seg_id, "")
            if plz:
                plzs_needed.add(plz)
    logger.info(f"[STEP 2] PLZs to aggregate gates for: {plzs_needed}")
    foundation_gates = {plz: agg_foundation_gate(plz) for plz in plzs_needed}

    # Step 3 — Load field_01 (using persistent_id bridge) and field_04
    f01 = load_field01()
    f04 = load_field04()

    # Step 4 — Assemble table: use REAL_GROUNDED_PLZ_MAP for PLZ lookup per segment
    logger.info("[4/4] Assembling MVP input table rows...")
    df = assemble_table(segments, f01, f02, f04, foundation_gates)

    n_usable = df["row_usable_for_ranking"].sum()
    logger.info(f"[4/4] Table built: {len(df)} rows, {n_usable} usable for ranking")

    # Emit parquet
    OUT_PARQ_DIR.mkdir(parents=True, exist_ok=True)
    parq_path = OUT_PARQ_DIR / "layer2_mvp_input_table.parquet"
    df.to_parquet(parq_path, index=False)
    logger.info(f"[OUTPUT] Parquet -> {parq_path}")

    # Emit markdown summary
    OUT_MD_DIR.mkdir(parents=True, exist_ok=True)
    ts_str  = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = OUT_MD_DIR / f"LAYER2_MVP_INPUT_TABLE_{ts_str}.md"
    md_path.write_text(render_md_summary(df), encoding="utf-8")
    logger.info(f"[OUTPUT] Markdown -> {md_path}")

    logger.info("=" * 60)
    logger.info("  DONE")
    logger.info("=" * 60)

    # Console summary
    print("\n" + "=" * 60)
    print("  LAYER 2 MVP INPUT TABLE — SUMMARY")
    print("=" * 60)
    print(df[["unit_id", "unit_status", "row_usable_for_ranking",
              "sfh_friendly_share", "l1_gate_label",
              "pv_coverage_score", "pv_coverage_availability"]].to_string(index=False))
    print("\n--- roof_suitability_score NORMALIZATION AUDIT ---")
    norm_cols = ["unit_id", "unit_status", "roof_suitability_score", "roof_suitability_score_norm"]
    print(df[norm_cols].to_string(index=False))
    print(f"\nParquet: {parq_path}")
    print(f"Markdown: {md_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
