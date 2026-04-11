"""
field_05_heat_modifier.py
==========================
Priority 2 — Fernwärme / District Heat Exclusion Overlay
D-ESS · Neuss MVP · PV-only

Applies a heat_modifier multiplier on top of the frozen Layer 2 base score.
Does NOT alter Layer 2 weights, field values, or segment status.

  adjusted_score = layer2_base_score × heat_modifier

Inputs (READ sources):
  - data/layer2/layer2_mvp_input_table.parquet        (Layer 2 base scores)
  - data/layer2/layer2_prio2_heat_input.json          (heat status per segment)

Output:
  - data/layer2/layer2_prio2_heat_overlay.parquet

Run:
  python scripts/field_05_heat_modifier.py
"""

from __future__ import annotations

import json
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
BASE_DIR     = Path(__file__).resolve().parent.parent
LAYER2_PARQ  = BASE_DIR / "data" / "layer2" / "layer2_mvp_input_table.parquet"
HEAT_INPUT   = BASE_DIR / "data" / "layer2" / "layer2_prio2_heat_input.json"
STREET_PARQ  = BASE_DIR / "data" / "layer2" / "street_level_ranking_v1.parquet"
OUTPUT_PARQ  = BASE_DIR / "data" / "layer2" / "layer2_prio2_heat_overlay.parquet"
OUTPUT_MD    = BASE_DIR / "output" / "layer2" / "LAYER2_PRIO2_HEAT_OVERLAY.md"

# ---------------------------------------------------------------------------
# Heat modifier table (DRAFT — not formally accepted until user sign-off)
# ---------------------------------------------------------------------------
# User-approved 2026-04-10: strict heat penalty table.
# STRONG  → ×0.10 (real-world exclusion; appears at bottom of ranking, not hard-zero)
# PLANNED → ×0.60 (network not yet built; clear yellow-flag, HP upsell risky)
# LIMITED → ×0.90 (mild caution; PV+HP remains viable)
# NO_SIGNAL→ ×1.00 (no constraint; full score)
# UNKNOWN → ×0.85 (default fallback for unmapped segments)
HEAT_MODIFIERS: dict[str, float] = {
    "STRONG_DISTRICT_HEAT":   0.10,
    "PLANNED_DISTRICT_HEAT":  0.60,
    "LIMITED_OR_UNCLEAR":     0.90,
    "NO_SIGNAL":              1.00,
    "UNKNOWN":                0.85,
}

PRIO2_SCHEMA_VERSION = "prio2_heat_overlay_v1_prod"


def load_layer2(path: Path) -> pd.DataFrame:
    logger.info(f"[P2-1] Loading Layer 2 base table: {path}")
    df = pd.read_parquet(path)
    logger.info(f"[P2-1] {len(df)} rows loaded. Usable: {df['row_usable_for_ranking'].sum()}")
    return df


def load_heat_input(path: Path) -> dict[str, dict]:
    logger.info(f"[P2-2] Loading heat input: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    segs = {s["unit_id"]: s for s in data.get("segments", [])}
    logger.info(f"[P2-2] {len(segs)} heat assignments loaded: {list(segs.keys())}")
    return segs


def build_overlay(df: pd.DataFrame, heat: dict[str, dict]) -> pd.DataFrame:
    """
    Produce the Priority 2 heat overlay table.
    Only processes real-grounded usable rows.
    Synthetic rows are included in output with heat_status=NOT_APPLICABLE.
    """
    logger.info("[P2-3] Building heat overlay...")
    rows = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    for _, row in df.iterrows():
        uid      = row["unit_id"]
        usable   = bool(row["row_usable_for_ranking"])
        base_score = float(row["draft_score"]) if pd.notna(row.get("draft_score")) else None

        # For synthetic / non-usable rows — pass through with no modifier applied
        if not usable or uid not in heat:
            rows.append({
                "unit_id":             uid,
                "unit_status":         row["unit_status"],
                "row_usable_for_ranking": usable,
                "base_score":          base_score,
                "heat_status":         "NOT_APPLICABLE" if not usable else "MISSING_INPUT",
                "heat_source":         None,
                "heat_confidence":     None,
                "heat_modifier":       None,
                "adjusted_score":      None,
                "heat_caveat":         "Synthetic row — excluded from Priority 2 overlay." if not usable
                                        else f"No heat input found for segment {uid}.",
                "prio2_interpretation": "Excluded — not a usable ranking row." if not usable
                                        else "ERROR: missing heat input.",
                "schema_version":      PRIO2_SCHEMA_VERSION,
                "build_timestamp_utc": ts,
            })
            logger.warning(f"[P2-3] {uid}: {'SYNTHETIC skip' if not usable else 'MISSING heat input'}")
            continue

        h         = heat[uid]
        status    = h["heat_status"]
        modifier  = HEAT_MODIFIERS.get(status, 0.85)      # default UNKNOWN if enum mismatch
        adj_score = round(base_score * modifier, 4) if base_score is not None else None

        rows.append({
            "unit_id":             uid,
            "unit_status":         row["unit_status"],
            "row_usable_for_ranking": usable,
            "base_score":          base_score,
            "heat_status":         status,
            "heat_source":         h.get("heat_source"),
            "heat_confidence":     h.get("heat_confidence"),
            "heat_modifier":       modifier,
            "adjusted_score":      adj_score,
            "heat_caveat":         h.get("heat_caveat"),
            "prio2_interpretation":h.get("prio2_interpretation"),
            "schema_version":      PRIO2_SCHEMA_VERSION,
            "build_timestamp_utc": ts,
        })
        logger.info(
            f"[P2-3] {uid}: base={base_score:.4f} × {modifier} "
            f"({status}) → adjusted={adj_score}"
        )

    out = pd.DataFrame(rows)
    return out


def write_outputs(df: pd.DataFrame) -> None:
    OUTPUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(OUTPUT_PARQ, index=False)
    logger.info(f"[OUTPUT] Parquet → {OUTPUT_PARQ}")

    # Markdown summary
    usable = df[df["row_usable_for_ranking"] == True].sort_values(
        "adjusted_score", ascending=False
    )
    lines = [
        "# Layer 2 Priority 2 — Heat Overlay Summary",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')}",
        f"**Schema:** {PRIO2_SCHEMA_VERSION}",
        "",
        "## Usable Rows — Adjusted Ranking",
        "",
        "| Segment | Base Score | Heat Status | Modifier | Adjusted Score | Interpretation |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in usable.iterrows():
        lines.append(
            f"| {r.unit_id} | {r.base_score:.4f} | `{r.heat_status}` "
            f"| ×{r.heat_modifier:.2f} | **{r.adjusted_score:.4f}** | {r.prio2_interpretation} |"
        )
    lines += [
        "",
        f"> ✅ PRODUCTION — user sign-off accepted 2026-04-10. Coefficients: STRONG×0.10 · PLANNED×0.60 · LIMITED×0.90 · NO_SIGNAL×1.00 · UNKNOWN×0.85",
        f"> Parquet: `{OUTPUT_PARQ}`",
    ]

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"[OUTPUT] Markdown → {OUTPUT_MD}")


def main() -> None:
    logger.info("=" * 60)
    logger.info("  PRIORITY 2 — HEAT MODIFIER v1")
    logger.info("=" * 60)

    # Guard: Layer 2 parquet must exist
    if not LAYER2_PARQ.exists():
        logger.error(f"Layer 2 parquet not found: {LAYER2_PARQ}")
        logger.error("Run build_layer2_mvp_input_table.py first.")
        sys.exit(1)

    df_l2   = load_layer2(LAYER2_PARQ)
    heat    = load_heat_input(HEAT_INPUT)

    # Logic 1 (2026-03-29): base_score derived bottom-up from field_08 street scores.
    # street_quality_agg = building-count-weighted mean of global street_score per segment.
    # street_score already embeds A-type (SFH quality, gate, scale, MFH clean)
    # and B-type (roof polygon quality, PV market opportunity) signals.
    # Tier discount reflects data source quality (polygon vs point geometry).
    TIER_DISCOUNT = {
        "NEUSS_NORF_01":    1.00,   # OSM polygon ground truth
        "NEUSS_SUBURB_01":  0.85,   # Point geometry — slight uncertainty
        "NEUSS_GRIML_01":   0.85,   # Point geometry — slight uncertainty
    }

    # Load field_08 street-level ranking
    if not STREET_PARQ.exists():
        logger.error(
            f"[P2] street_level_ranking_v1.parquet not found: {STREET_PARQ}. "
            "Run `python fields/field_08_street_level_ranking.py` first."
        )
        raise FileNotFoundError(STREET_PARQ)

    street_df = pd.read_parquet(STREET_PARQ)
    logger.info(f"[P2] Loaded {len(street_df)} street rows from field_08")

    # Compute building-count-weighted mean per segment
    street_df = street_df.copy()
    street_df["_n_x_s"] = street_df["street_score"] * street_df["building_count_total"]
    agg = (
        street_df.groupby("segment_id")
        .agg(nxs=("_n_x_s", "sum"), n=("building_count_total", "sum"))
    )
    agg["street_quality_agg"] = (agg["nxs"] / agg["n"]).round(4)
    agg = agg[["street_quality_agg"]].reset_index().rename(columns={"segment_id": "unit_id"})
    logger.info("[P2] street_quality_agg per segment:")
    for _, r in agg.iterrows():
        logger.info(f"  {r['unit_id']:<22} street_quality_agg={r['street_quality_agg']:.4f}")

    df_l2 = df_l2.merge(agg, on="unit_id", how="left")
    df_l2["street_quality_agg"] = df_l2["street_quality_agg"].fillna(0.0)

    def _score(row: pd.Series) -> float | None:
        if not row.get("row_usable_for_ranking", False):
            return None
        disc = TIER_DISCOUNT.get(row["unit_id"], 0.85)
        base = float(row.get("street_quality_agg", 0.0))
        score = round(base * disc, 4)
        logger.info(
            f"[P2-SCORE] {row['unit_id']}: "
            f"street_quality_agg={base:.4f} × tier_disc={disc} → draft={score:.4f}"
        )
        return score

    df_l2["draft_score"] = df_l2.apply(_score, axis=1)

    overlay = build_overlay(df_l2, heat)
    write_outputs(overlay)

    # Summary
    logger.info("=" * 60)
    logger.info("  DONE")
    logger.info("=" * 60)
    usable = overlay[overlay["row_usable_for_ranking"] == True].sort_values(
        "adjusted_score", ascending=False
    )
    print("\n" + "=" * 60)
    print("  PRIORITY 2 HEAT OVERLAY - ADJUSTED RANKING [PRODUCTION]")
    print("  Coefficients: STRONG x0.10 PLANNED x0.60 LIMITED x0.90 NO_SIGNAL x1.00")
    print("=" * 60)
    for _, r in usable.iterrows():
        print(
            f"  {r.unit_id:<22} base={r.base_score:.4f}  x{r.heat_modifier:.2f}"
            f"  -> adjusted={r.adjusted_score:.4f}  [{r.heat_status}]"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
