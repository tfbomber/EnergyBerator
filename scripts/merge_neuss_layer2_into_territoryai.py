"""
merge_neuss_layer2_into_territoryai.py
========================================
Final step of the Neuss Layer 2 rearch (Option 2, 2026-07-11 — see
territoryai/.ai/implementation_plan_neuss_layer2_rearch.md): merges the
freshly-recomputed 8-row Neuss segment table (this repo's
data/layer2/street_ranking_v1.parquet, produced by fields/field_07_street_ranking.py)
into territoryai's shared data/layer2/street_ranking_v1.parquet.

Unlike merge_augsburg_into_territoryai.py, no field approximation is needed here:
field_07_street_ranking.py is the native, exact producer of this schema for Neuss
(it's the one this whole rearch just re-ran), so the source rows are used as-is.

Scope (deliberately narrow, per the implementation plan):
  - Only data/layer2/street_ranking_v1.parquet (segment-level) is touched.
  - data/layer2/street_level_ranking_v1.parquet (street-level, field_08-produced,
    the map-join target) is NOT touched — field_08 does not read buildings.parquet,
    confirmed unrelated to this rearch (C4 in implementation_plan_neuss_fix.md).
  - Only the 8 NEUSS_PLZ* rows are replaced. Kaarst (KAARST_OSM_41564) and all 14
    Augsburg (AUGSBURG_OSM_*) rows are preserved untouched.

GUARDRAILS:
  - Backs up the target parquet before writing.
  - Idempotent: drops any pre-existing NEUSS_PLZ* rows before appending the fresh 8,
    so re-running this script is safe.
  - Schema verification (exact column-set match) before writing.
  - Aborts (no partial/corrupt write) if the merge would introduce NaN cells or if
    row count isn't exactly 8 new + (old total - old Neuss count).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("MERGE_NEUSS_LAYER2")

DESS_BASE_DIR = Path(__file__).resolve().parents[1]
TERRITORYAI_DIR = Path(r"D:\Stock Analysis\territoryai\data\layer2")

SOURCE_PARQ = DESS_BASE_DIR / "data" / "layer2" / "street_ranking_v1.parquet"
TARGET_PARQ = TERRITORYAI_DIR / "street_ranking_v1.parquet"
BACKUP_DIR  = TERRITORYAI_DIR.parent / "backups"

NEUSS_PLZ_PREFIX = "NEUSS_PLZ"


def main():
    source = pd.read_parquet(SOURCE_PARQ)
    target = pd.read_parquet(TARGET_PARQ)

    n_source = len(source)
    logger.info(f"[LOAD] Source (d-ess-engine, fresh field_07 output): {n_source} rows: "
                f"{sorted(source['street_id'].tolist())}")
    logger.info(f"[LOAD] Target (territoryai, current): {len(target)} rows")

    assert n_source == 8, f"Expected exactly 8 fresh Neuss rows, got {n_source}"
    assert set(source["street_id"]) == {f"{NEUSS_PLZ_PREFIX}{p}" for p in
        ("41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472")}, \
        f"Unexpected segment_id set in source: {sorted(source['street_id'].tolist())}"

    # Schema verification before touching anything on disk
    assert set(source.columns) == set(target.columns), (
        f"street_ranking_v1 schema mismatch: "
        f"missing={set(target.columns) - set(source.columns)} "
        f"extra={set(source.columns) - set(target.columns)}"
    )
    logger.info("[SCHEMA] Source matches territoryai's target schema exactly.")

    # Reorder to match target exactly (cosmetic, avoids column-order drift).
    source = source[target.columns]

    # Idempotent re-merge: drop any pre-existing NEUSS_PLZ* rows first, then append
    # the freshly-built 8. Kaarst/Augsburg rows are untouched either way.
    is_neuss_plz = target["street_id"].astype(str).str.startswith(NEUSS_PLZ_PREFIX)
    n_prior = int(is_neuss_plz.sum())
    n_other = len(target) - n_prior
    logger.info(f"[REPLACE] Dropping {n_prior} prior NEUSS_PLZ* rows; "
                f"{n_other} non-Neuss rows (Kaarst/Augsburg) preserved untouched.")

    other_rows = target[~is_neuss_plz]

    merged = pd.concat([other_rows, source], ignore_index=True)

    n_nan = merged.isna().sum().sum()
    logger.info(f"[CHECK] merged street_ranking_v1: {len(merged)} rows, {n_nan} NaN cells")
    assert n_nan == 0, "NaN introduced in merged street_ranking_v1 — aborting write"
    assert len(merged) == n_other + 8, (
        f"Unexpected merged row count: {len(merged)} != {n_other} (preserved) + 8 (fresh Neuss)"
    )

    # Backup the pre-merge target before writing.
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / f"street_ranking_v1.parquet.pre_neuss_layer2_rearch_merge_{ts}"
    target.to_parquet(backup_path, index=False)
    logger.info(f"[BACKUP] {backup_path}")

    merged.to_parquet(TARGET_PARQ, index=False)
    logger.info(f"[WRITE] {TARGET_PARQ} ({len(merged)} rows)")

    logger.info("[SUMMARY] street_id / rank / final_score / priority_score for the 8 Neuss rows:")
    for _, r in merged[merged["street_id"].astype(str).str.startswith(NEUSS_PLZ_PREFIX)] \
            .sort_values("rank").iterrows():
        logger.info(f"  #{int(r['rank'])} {r['street_id']}: final={r['final_score']:.4f} "
                    f"priority={r['priority_score']:.4f}")
    logger.info("[SUMMARY] Non-Neuss rows preserved (first 3 shown): "
                f"{other_rows['street_id'].tolist()[:3]} ... ({n_other} total)")


if __name__ == "__main__":
    main()
