"""
merge_neuss_street_level_into_territoryai.py
==============================================
Companion to merge_neuss_layer2_into_territoryai.py (segment-level) — merges
the freshly-recomputed 733-row Neuss STREET-level table
(data/layer2/street_level_ranking_v1.parquet, produced by
fields/field_08_street_level_ranking.py) into territoryai's shared
data/layer2/street_level_ranking_v1.parquet.

Written 2026-07-14 (Neuss Layer2 rearch v2 — territoryai
.ai/implementation_plan_neuss_layer2_rearch_v2.md; D4-for-Neuss scenario (a)
confirmed by user before this merge ran). The original
merge_neuss_layer2_into_territoryai.py (2026-07-11) deliberately scoped this
step OUT, reasoning "field_08 does not read buildings.parquet". True, but
incomplete: field_08 DOES read `pv_coverage_score` from field_07's OWN
output (SEG_RANK_PARQUET = data/layer2/street_ranking_v1.parquet), which
field_04's building-count fix changes — so street-level pv_oppty_score/
b_pv_oppty/adjusted_street_score were left stale relative to the freshly
recomputed segment-level scores. Verified before writing this script: all
733 structure_gate/mfh_ratio/sfh_*_count/building_count_total columns are
BYTE-IDENTICAL before vs after the field_08 rerun (Foundation JSON for Neuss
is untouched, still the same 2026-05-04 extraction — refreshing THAT is a
separate, larger, not-yet-started decision) — only the PV-derived columns
changed. This merge only propagates that consistent PV-column refresh.

GUARDRAILS (mirrors the sibling segment-level script):
  - Backs up the target parquet before writing.
  - Idempotent: drops any pre-existing NEUSS_PLZ* rows before appending the
    fresh 733, so re-running this script is safe.
  - Schema verification (exact column-set match) before writing.
  - Aborts (no partial/corrupt write) on NaN or unexpected row count.
  - Hard-asserts every non-Neuss row is byte-identical before vs after.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("MERGE_NEUSS_STREET_LEVEL")

DESS_BASE_DIR = Path(__file__).resolve().parents[1]
TERRITORYAI_DIR = Path(r"D:\Stock Analysis\territoryai\data\layer2")

SOURCE_PARQ = DESS_BASE_DIR / "data" / "layer2" / "street_level_ranking_v1.parquet"
TARGET_PARQ = TERRITORYAI_DIR / "street_level_ranking_v1.parquet"
BACKUP_DIR  = TERRITORYAI_DIR.parent / "backups"

NEUSS_PLZ_PREFIX = "NEUSS_PLZ"


def main():
    source = pd.read_parquet(SOURCE_PARQ)
    target = pd.read_parquet(TARGET_PARQ)

    n_source = len(source)
    logger.info(f"[LOAD] Source (d-ess-engine, fresh field_08 output): {n_source} rows")
    logger.info(f"[LOAD] Target (territoryai, current): {len(target)} rows")

    assert (source["segment_id"].astype(str).str.startswith(NEUSS_PLZ_PREFIX)).all(), (
        "Source contains non-Neuss segment_id rows — unexpected for this script"
    )

    assert set(source.columns) == set(target.columns), (
        f"street_level_ranking_v1 schema mismatch: "
        f"missing={set(target.columns) - set(source.columns)} "
        f"extra={set(source.columns) - set(target.columns)}"
    )
    logger.info("[SCHEMA] Source matches territoryai's target schema exactly.")

    source = source[target.columns]

    is_neuss = target["segment_id"].astype(str).str.startswith(NEUSS_PLZ_PREFIX)
    n_prior = int(is_neuss.sum())
    other_rows = target[~is_neuss].copy()
    logger.info(f"[REPLACE] Dropping {n_prior} prior NEUSS_PLZ* rows; "
                f"{len(other_rows)} non-Neuss rows (Kaarst/Augsburg/Leipzig) preserved untouched.")

    merged = pd.concat([other_rows, source], ignore_index=True)

    n_nan = merged.isna().sum().sum()
    logger.info(f"[CHECK] merged street_level_ranking_v1: {len(merged)} rows, {n_nan} NaN cells")
    assert n_nan == 0, "NaN introduced in merged street_level_ranking_v1 — aborting write"
    assert len(merged) == len(other_rows) + n_source, (
        f"Unexpected merged row count: {len(merged)} != {len(other_rows)} + {n_source}"
    )

    # Byte-identical proof: every non-Neuss row must be untouched by this merge.
    post_non_neuss = merged[~merged["segment_id"].astype(str).str.startswith(NEUSS_PLZ_PREFIX)].reset_index(drop=True)
    pre_sorted = other_rows.sort_values("cluster_id").reset_index(drop=True)
    post_sorted = post_non_neuss.sort_values("cluster_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(pre_sorted, post_sorted, check_like=False)
    logger.info("[REGRESSION GUARD] Kaarst/Augsburg/Leipzig rows are byte-identical before vs after this merge.")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / f"street_level_ranking_v1.parquet.pre_neuss_street_level_merge_{ts}"
    target.to_parquet(backup_path, index=False)
    logger.info(f"[BACKUP] {backup_path}")

    merged.to_parquet(TARGET_PARQ, index=False)
    logger.info(f"[WRITE] {TARGET_PARQ} ({len(merged)} rows)")

    logger.info("[SUMMARY] segment_id prefix counts in merged street_level_ranking_v1:")
    logger.info(merged["segment_id"].astype(str).str.extract(r"^([A-Z]+)")[0].value_counts().to_dict())


if __name__ == "__main__":
    main()
