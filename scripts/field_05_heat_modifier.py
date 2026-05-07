"""
field_05_heat_modifier.py
==========================
Priority 2 — Heat Constraint Label Layer  (v3, Option C architecture)
D-ESS · Neuss MVP · PV-only

ARCHITECTURE CHANGE (v3, 2026-04-12):
  field_05 is now a PURE LABEL LAYER — it does NOT modify scores.
  Score suppression has been removed.

  adjusted_score = base_score   (pass-through, no penalty)
  heat_modifier  = 1.00         (always neutral)

  ROI impact of Fernwarme now flows EXCLUSIVELY through field_06
  hp_roi_multiplier, which captures the correct causal chain:
    Fernwarme -> HP unlikely -> low self-consumption -> lower PV ROI

This eliminates:
  - Direct Waerme_p -> score suppression (was -15% max)
  - Risk of double-counting Fernwarme signal in field_05 + field_06

Outputs (labels only — for UI badges, narrative, caveat text):
  - heat_constraint_label: LOW / MEDIUM / HIGH / UNKNOWN
  - heat_constraint_score: Waerme_p classification score [0,1]
  - heat_constraint_confidence: data reliability [0,1]
  - heat_caveat: German narrative for UI Section H
  - base_score / adjusted_score (identical — pass-through)
  - heat_modifier = 1.00 (retained column for schema backward compat)

Inputs:
  - data/layer2/layer2_mvp_input_table.parquet
  - data/layer2/street_level_ranking_v1.parquet
  - data/sources/waermenetz/sanierung_baublock_neuss_v1.parquet

Output:
  - data/layer2/layer2_prio2_heat_overlay.parquet

Run:
  python scripts/field_05_heat_modifier.py
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR       = Path(__file__).resolve().parent.parent
LAYER2_PARQ    = BASE_DIR / "data" / "layer2" / "layer2_mvp_input_table.parquet"
STREET_PARQ    = BASE_DIR / "data" / "layer2" / "street_level_ranking_v1.parquet"
BUILDINGS_PARQ = BASE_DIR / "data" / "buildings.parquet"                          # spatial bridge
BAUBLOCK_PARQ  = BASE_DIR / "data" / "sources" / "waermenetz" / "sanierung_baublock_neuss_v1.parquet"
OUTPUT_PARQ    = BASE_DIR / "data" / "layer2" / "layer2_prio2_heat_overlay.parquet"
OUTPUT_MD      = BASE_DIR / "output" / "layer2" / "LAYER2_PRIO2_HEAT_OVERLAY.md"

# ---------------------------------------------------------------------------
# Heat Constraint Classification — Waerme_p thresholds
#
#   HIGH     Waerme_p >= 40%  → constraint_score = 1.00
#   MEDIUM   Waerme_p >= 15%  → constraint_score = Waerme_p / 40 (proportional)
#   LOW      Waerme_p <  15%  → constraint_score = 0.00
#   UNKNOWN  no spatial join  → constraint_score = 0.50 (conservative)
#
# NOTE (v3): These scores are now used ONLY for label classification and UI.
#   They no longer drive score suppression (that was removed in Option C).
#   ROI impact is handled exclusively in field_06 via hp_roi_multiplier.
# ---------------------------------------------------------------------------
WAERME_HIGH_THRESHOLD   = 40.0   # % — HIGH label trigger
WAERME_MEDIUM_THRESHOLD = 15.0   # % — MEDIUM label trigger

SCHEMA_VERSION = "heat_constraint_v3"  # bumped: pure label layer

# Tier discount (unchanged from v1 — field_08 geometry quality tiers)
TIER_DISCOUNT = {
    "NEUSS_PLZ41470":   1.00,   # OSM polygon ground truth
    "NEUSS_PLZ41472": 0.85,   # Point geometry — slight uncertainty
    "NEUSS_PLZ41464":  0.85,   # Point geometry — slight uncertainty
}


# ---------------------------------------------------------------------------
# Step 1: Load Layer 2 base table + street scores
# ---------------------------------------------------------------------------
def load_layer2_with_draft_scores() -> pd.DataFrame:
    """
    Load Layer 2 base table and compute draft_score per segment.
    Logic unchanged from v1: street_quality_agg × tier_discount.
    """
    logger.info(f"[P2-1] Loading Layer 2 base table: {LAYER2_PARQ}")
    df_l2 = pd.read_parquet(LAYER2_PARQ)
    logger.info(f"[P2-1] {len(df_l2)} rows. Usable: {df_l2['row_usable_for_ranking'].sum()}")

    logger.info(f"[P2-1] Loading street scores: {STREET_PARQ}")
    street_df = pd.read_parquet(STREET_PARQ)
    logger.info(f"[P2-1] {len(street_df)} street rows loaded")

    # Building-count-weighted street score per segment
    street_df = street_df.copy()
    street_df["_n_x_s"] = street_df["street_score"] * street_df["building_count_total"]
    agg = (
        street_df.groupby("segment_id")
        .agg(nxs=("_n_x_s", "sum"), n=("building_count_total", "sum"))
    )
    agg["street_quality_agg"] = (agg["nxs"] / agg["n"]).round(4)
    agg = agg[["street_quality_agg"]].reset_index().rename(columns={"segment_id": "unit_id"})

    logger.info("[P2-1] street_quality_agg per segment:")
    for _, r in agg.iterrows():
        logger.info(f"  {r['unit_id']:<22} street_quality_agg={r['street_quality_agg']:.4f}")

    df_l2 = df_l2.merge(agg, on="unit_id", how="left")
    df_l2["street_quality_agg"] = df_l2["street_quality_agg"].fillna(0.0)

    def _score(row: pd.Series) -> float | None:
        if not row.get("row_usable_for_ranking", False):
            return None
        disc  = TIER_DISCOUNT.get(row["unit_id"], 0.85)
        base  = float(row.get("street_quality_agg", 0.0))
        score = round(base * disc, 4)
        logger.info(
            f"[P2-SCORE] {row['unit_id']}: "
            f"street_quality_agg={base:.4f} x tier_disc={disc} -> draft={score:.4f}"
        )
        return score

    df_l2["draft_score"] = df_l2.apply(_score, axis=1)
    return df_l2


# ---------------------------------------------------------------------------
# Step 2: Spatial join — building points x Baublock polygons -> segment Waerme_p
# ---------------------------------------------------------------------------
def compute_waerme_p_per_segment(buildings_parq: Path, baublock_parq: Path) -> dict[str, dict]:
    """
    Spatial join strategy:
      1. Load buildings.parquet (has segment_id + lat/lon)
      2. Convert to GeoDataFrame (Point geometry, EPSG:4326 -> reproject to 25832)
      3. Point-in-polygon join: each building gets its Baublock's Waerme_p
      4. Aggregate Waerme_p by segment_id (mean across all matched buildings)

    buildings.parquet is the spatial bridge: it has segment_id AND coordinates.
    This avoids the need for street-level geometry or PLZ boundary files.

    Returns:
      {segment_id: {waerme_p_weighted, spatial_coverage_ratio, block_count_hit}}
    """
    try:
        import geopandas as gpd
    except ImportError:
        logger.error("[SPATIAL] geopandas not installed. Run: pip install geopandas")
        sys.exit(1)

    logger.info(f"[SPATIAL] Loading buildings (spatial bridge): {buildings_parq}")
    bldg_df = pd.read_parquet(buildings_parq)
    logger.info(f"[SPATIAL] {len(bldg_df)} buildings. segments: {sorted(bldg_df['segment_id'].unique().tolist())}")

    # Build point GeoDataFrame from lat/lon (EPSG:4326) -> reproject to EPSG:25832
    bldg_gdf = gpd.GeoDataFrame(
        bldg_df[["segment_id", "lat", "lon"]].copy(),
        geometry=gpd.points_from_xy(bldg_df["lon"], bldg_df["lat"]),
        crs="EPSG:4326",
    ).to_crs(epsg=25832)

    logger.info(f"[SPATIAL] Loading Baublock: {baublock_parq}")
    baublock_gdf = gpd.read_parquet(baublock_parq)
    if str(baublock_gdf.crs.to_epsg()) != "25832":
        baublock_gdf = baublock_gdf.to_crs(epsg=25832)

    # Point-in-polygon join: each building point -> Baublock it falls within
    logger.info(f"[SPATIAL] Joining {len(bldg_gdf)} building points x {len(baublock_gdf)} blocks...")
    joined = gpd.sjoin(
        bldg_gdf,
        baublock_gdf[["Waerme_p", "geometry"]],
        how="left",
        predicate="within",
    )

    hit_count  = joined["index_right"].notna().sum()
    miss_count = joined["index_right"].isna().sum()
    logger.info(f"[SPATIAL] Join: {hit_count} buildings matched to blocks, {miss_count} unmatched")

    # Aggregate: mean Waerme_p per segment (each building equally weighted)
    results: dict[str, dict] = {}
    for seg_id in bldg_df["segment_id"].unique():
        seg_rows = joined[joined["segment_id"] == seg_id]
        hits     = seg_rows[seg_rows["index_right"].notna()]

        total_bldgs = len(seg_rows)
        hit_bldgs   = len(hits)
        coverage    = round(hit_bldgs / total_bldgs, 3) if total_bldgs > 0 else 0.0

        if hits.empty:
            results[str(seg_id)] = {
                "waerme_p_weighted":      None,
                "spatial_coverage_ratio": 0.0,
                "block_count_hit":        0,
                "data_source":            "KWP_spatial_join_MISS",
            }
            logger.warning(f"[SPATIAL] segment={seg_id}: NO baublock hit -> UNKNOWN")
        else:
            waerme_mean = round(float(hits["Waerme_p"].mean()), 2)
            blocks_hit  = int(hits["index_right"].nunique())
            results[str(seg_id)] = {
                "waerme_p_weighted":      waerme_mean,
                "spatial_coverage_ratio": coverage,
                "block_count_hit":        blocks_hit,
                "data_source":            "KWP_spatial_join",
            }
            logger.info(
                f"[SPATIAL] segment={seg_id}: "
                f"Waerme_p_weighted={waerme_mean:.1f}%  "
                f"blocks_hit={blocks_hit}  "
                f"coverage={coverage:.2f} ({hit_bldgs}/{total_bldgs} bldgs)"
            )

    return results



# ---------------------------------------------------------------------------
# Step 3: Classify Waerme_p → heat_constraint_label + score
# ---------------------------------------------------------------------------
def classify_heat_constraint(waerme_p: float | None) -> tuple[str, float, float]:
    """
    Classify Waerme_p (%) into heat constraint label, score, and confidence.

    Returns:
      (heat_constraint_label, heat_constraint_score, heat_constraint_confidence)

    Thresholds (user-approved 2026-04-12):
      HIGH     >= 40%   → score=1.00, conf=0.90
      MEDIUM   >= 15%   → score=proportional [0.375~1.0], conf=0.80
      LOW      <  15%   → score=0.00, conf=0.95
      UNKNOWN  no data  → score=0.50, conf=0.40
    """
    if waerme_p is None:
        return "UNKNOWN", 0.50, 0.40

    if waerme_p >= WAERME_HIGH_THRESHOLD:
        return "HIGH", 1.00, 0.90

    if waerme_p >= WAERME_MEDIUM_THRESHOLD:
        # Proportional within MEDIUM band
        score = round(waerme_p / WAERME_HIGH_THRESHOLD, 3)
        return "MEDIUM", score, 0.80

    return "LOW", 0.00, 0.95


def generate_heat_caveat(label: str, waerme_p: float | None, coverage: float) -> str:
    """Generate human-readable caveat string for UI/narrative."""
    if label == "UNKNOWN":
        return "Keine Fernwaerme-Daten fuer dieses Segment verfuegbar. Constraint-Status unbekannt."
    if label == "HIGH":
        return (
            f"Hoher Fernwaerme-Deckungsgrad ({waerme_p:.0f}% der Gebaeude im Block). "
            "PV+WP-Kombiangebot mit Einschraenkungen. Nicht als Hauptabsatzgebiet empfohlen."
        )
    if label == "MEDIUM":
        return (
            f"Teilweise Fernwaerme-Versorgung ({waerme_p:.0f}%). "
            "WP-Potential vorhanden, aber pruefen ob Bestandsheizung Fernwaerme ist."
        )
    return "Kein wesentlicher Fernwaerme-Deckungsgrad. Keine Einschraenkung fuer PV+WP."


# ---------------------------------------------------------------------------
# Step 4: Build overlay table
# ---------------------------------------------------------------------------
def build_overlay(
    df: pd.DataFrame,
    spatial_results: dict[str, dict],
) -> pd.DataFrame:
    """
    Apply heat constraint modifier to each segment's draft_score.

    For usable rows:
      adjusted_score = draft_score × (1 - MAX_SUPPRESSION_FACTOR × constraint_score)

    For non-usable / synthetic rows:
      pass-through with heat_constraint_label = NOT_APPLICABLE
    """
    logger.info("[P2-BUILD] Building heat constraint overlay...")
    rows = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    for _, row in df.iterrows():
        uid        = str(row["unit_id"])
        usable     = bool(row["row_usable_for_ranking"])
        base_score = float(row["draft_score"]) if pd.notna(row.get("draft_score")) else None

        if not usable:
            rows.append({
                "unit_id":                   uid,
                "unit_status":               row["unit_status"],
                "row_usable_for_ranking":    usable,
                "base_score":                base_score,
                "heat_constraint_label":     "NOT_APPLICABLE",
                "heat_constraint_score":     None,
                "heat_constraint_confidence":None,
                "waerme_p_weighted":         None,
                "spatial_coverage_ratio":    None,
                "heat_caveat":               "Synthetic row — excluded from Priority 2 overlay.",
                "heat_modifier":             None,   # kept for backward compat with field_06
                "adjusted_score":            None,
                "schema_version":            SCHEMA_VERSION,
                "build_timestamp_utc":       ts,
            })
            continue

        # Spatial join result for this segment
        sj = spatial_results.get(uid, {})
        waerme_p    = sj.get("waerme_p_weighted")   # None if no spatial hit
        coverage    = sj.get("spatial_coverage_ratio", 0.0)
        data_source = sj.get("data_source", "MISSING")

        label, constraint_score, confidence = classify_heat_constraint(waerme_p)

        # If coverage is very low (<30%), reduce confidence further
        if coverage < 0.30 and label != "UNKNOWN":
            confidence = round(confidence * 0.70, 2)
            logger.warning(
                f"[P2-BUILD] {uid}: low spatial coverage ({coverage:.0%}) "
                f"→ confidence reduced to {confidence:.2f}"
            )

        # v3: NO score suppression — field_05 is pure label layer.
        # adjusted_score = base_score (pass-through).
        # heat_modifier = 1.00 (neutral, retained for schema compat).
        heat_modifier = 1.00
        adj_score     = base_score  # unchanged

        caveat = generate_heat_caveat(label, waerme_p, coverage)

        logger.info(
            f"[P2-BUILD] {uid}: Waerme_p={waerme_p}%  label={label}  "
            f"score={constraint_score:.2f}  [NO suppression — label-only, ROI via field_06]"
        )

        rows.append({
            "unit_id":                   uid,
            "unit_status":               row["unit_status"],
            "row_usable_for_ranking":    usable,
            "base_score":                base_score,
            "heat_constraint_label":     label,
            "heat_constraint_score":     constraint_score,
            "heat_constraint_confidence":confidence,
            "waerme_p_weighted":         waerme_p,
            "spatial_coverage_ratio":    coverage,
            "heat_caveat":               caveat,
            "heat_modifier":             heat_modifier,   # always 1.00 (v3)
            "adjusted_score":            adj_score,       # = base_score (v3)
            "data_source":               data_source,
            "schema_version":            SCHEMA_VERSION,
            "build_timestamp_utc":       ts,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 5: Write outputs
# ---------------------------------------------------------------------------
def write_outputs(df: pd.DataFrame) -> None:
    OUTPUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(OUTPUT_PARQ, index=False)
    logger.info(f"[OUTPUT] Parquet -> {OUTPUT_PARQ}")

    # Markdown summary
    usable = df[df["row_usable_for_ranking"].astype(bool)].sort_values(
        "adjusted_score", ascending=False
    )
    lines = [
        "# Layer 2 Priority 2 — Heat Constraint Overlay (v2)",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')}",
        f"**Schema:** {SCHEMA_VERSION}",
        f"**Data source:** KWP NRW Neuss (sanierung_baublock_neuss_v1.parquet)",
        f"**Formula:** adjusted = draft x (1 - 0.15 x constraint_score)",
        f"**Max suppression:** -15%  (vs old STRONG x0.10 = -90%)",
        "",
        "## Usable Rows — Adjusted Ranking",
        "",
        "| Segment | Base Score | Waerme_p% | Constraint | Score | Modifier | Adjusted | Confidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in usable.iterrows():
        wp = f"{r.waerme_p_weighted:.1f}%" if r.waerme_p_weighted is not None else "NULL"
        lines.append(
            f"| {r.unit_id} "
            f"| {r.base_score:.4f} "
            f"| {wp} "
            f"| `{r.heat_constraint_label}` "
            f"| {r.heat_constraint_score:.2f} "
            f"| x{r.heat_modifier:.4f} "
            f"| **{r.adjusted_score:.4f}** "
            f"| {r.heat_constraint_confidence:.2f} |"
        )
    lines += [
        "",
        "> **Schema v2** — KWP spatial join replaces JSON proxy. "
        "Waerme_p thresholds: HIGH>=40%, MEDIUM>=15%, LOW<15%. "
        "Waerme_p consumed ONLY here (no double-penalty with field_06).",
        f"> Parquet: `{OUTPUT_PARQ}`",
    ]

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"[OUTPUT] Markdown -> {OUTPUT_MD}")


# ---------------------------------------------------------------------------
# Sanity checks post-build
# ---------------------------------------------------------------------------
def sanity_check(df: pd.DataFrame) -> None:
    """
    Verify invariants for v3 (pure label layer).
    adjusted_score == base_score for all usable rows (no suppression applied).
    heat_modifier == 1.00 for all usable rows.
    """
    usable = df[df["row_usable_for_ranking"].astype(bool)]
    errors = 0

    for _, r in usable.iterrows():
        # v3: adjusted_score must equal base_score (no suppression)
        if r.adjusted_score is not None and r.base_score is not None:
            if abs(r.adjusted_score - r.base_score) > 1e-6:
                logger.error(
                    f"[SANITY FAIL] {r.unit_id}: adjusted_score {r.adjusted_score:.6f} "
                    f"!= base_score {r.base_score:.6f}. v3 requires pass-through."
                )
                errors += 1
        # heat_modifier must be 1.00
        if r.heat_modifier is not None and abs(r.heat_modifier - 1.00) > 1e-6:
            logger.error(
                f"[SANITY FAIL] {r.unit_id}: heat_modifier={r.heat_modifier} != 1.00"
            )
            errors += 1

    if errors:
        logger.error(f"[SANITY] {errors} invariant violations. Aborting.")
        sys.exit(1)

    logger.info(f"[SANITY] All {len(usable)} usable rows passed invariant checks.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info("=" * 64)
    logger.info("  FIELD-05 HEAT CONSTRAINT OVERLAY v2 (KWP spatial join)")
    logger.info("=" * 64)

    # Guard: required inputs
    for path, label in [
        (LAYER2_PARQ,    "Layer 2 base table"),
        (STREET_PARQ,    "street_level_ranking_v1"),
        (BUILDINGS_PARQ, "buildings (spatial bridge)"),
        (BAUBLOCK_PARQ,  "sanierung_baublock (KWP)"),
    ]:
        if not path.exists():
            logger.error(f"[GUARD] Required input not found: {path}  ({label})")
            sys.exit(1)

    # Phase 1: Base scores
    df_l2 = load_layer2_with_draft_scores()

    # Phase 2: Spatial join — buildings -> Baublock -> aggregate by segment
    spatial_results = compute_waerme_p_per_segment(BUILDINGS_PARQ, BAUBLOCK_PARQ)

    # Phase 3: Build overlay
    overlay = build_overlay(df_l2, spatial_results)

    # Phase 4: Sanity check
    sanity_check(overlay)

    # Phase 5: Write outputs
    write_outputs(overlay)

    # Summary
    logger.info("=" * 64)
    logger.info("  DONE")
    logger.info("=" * 64)
    usable = overlay[overlay["row_usable_for_ranking"].astype(bool)].sort_values(
        "adjusted_score", ascending=False
    )
    print("\n" + "=" * 64)
    print("  HEAT CONSTRAINT OVERLAY v2 — ADJUSTED RANKING")
    print(f"  Formula: adjusted = draft x (1 - 0.15 x constraint_score)")
    print(f"  Max suppression: -15%  |  Data: KWP NRW Neuss spatial join")
    print("=" * 64)
    for _, r in usable.iterrows():
        wp_str = f"{r.waerme_p_weighted:.1f}%" if r.waerme_p_weighted is not None else "NULL"
        print(
            f"  {r.unit_id:<22} "
            f"draft={r.base_score:.4f}  "
            f"Waerme_p={wp_str:<7}  "
            f"[{r.heat_constraint_label:<7}]  "
            f"x{r.heat_modifier:.4f}  "
            f"-> adjusted={r.adjusted_score:.4f}"
        )
    print("=" * 64)


if __name__ == "__main__":
    main()
