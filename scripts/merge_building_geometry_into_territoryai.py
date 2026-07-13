"""
merge_building_geometry_into_territoryai.py
====================================
WBS #3 data pipeline (real-map project): builds the unified building-geometry
parquet consumed by territoryai's new GET /api/v1/admin/territory/geometry?plz=
endpoint.

Reads each city's building-level parquet (Augsburg, Kaarst, Neuss, Leipzig —
Leipzig added 2026-07-13, see .ai/implementation_plan_leipzig.md),
verifies/uses each source's existing `city` column, applies the Neuss-only
PLZ-segment filter (excludes the 931 non-8-PLZ pilot/typology segments
discovered during this session's Neuss buildings fix — see
territoryai/scratch/neuss_phase2_progress.md), computes a precomputed
`street_key` (WBS#1 canonical German-aware normalization, copied verbatim
from territoryai/scratch/street_match_audit.py's norm_l2 — do not diverge,
the geometry endpoint recomputes street_key from street_name with this exact
same function to join back against this column), and writes a full-overwrite
rebuild of territoryai/data/layer2/building_geometry_v1.parquet.

This is a from-scratch rebuild EVERY run (not an idempotent/append merge like
merge_augsburg_into_territoryai.py's AUGSBURG_-prefix replace) — the three
source parquets are always read in full and the target parquet is always
fully overwritten.

GUARDRAILS:
  - Read-only against all three source building parquets.
  - Read-only against every territoryai ranking/street parquet (this script
    writes ONLY building_geometry_v1.parquet, nothing else).
  - Hard assertions abort the write if the Neuss-only filter, the WKT-ness of
    the geometry column, the output schema, or the post-dropna null-count
    checks don't hold — no partial or corrupt writes.
"""

import logging
import re
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("MERGE_BUILDING_GEOMETRY")

DESS_BASE_DIR = Path(__file__).resolve().parents[1]
TERRITORYAI_DIR = Path(r"D:\Stock Analysis\territoryai\data\layer2")

AUGSBURG_BUILDINGS = DESS_BASE_DIR / "data" / "augsburg_buildings.parquet"
KAARST_BUILDINGS   = DESS_BASE_DIR / "data" / "kaarst_buildings.parquet"
NEUSS_BUILDINGS    = DESS_BASE_DIR / "data" / "buildings.parquet"
LEIPZIG_BUILDINGS  = DESS_BASE_DIR / "data" / "leipzig_buildings.parquet"

OUTPUT_PARQUET = TERRITORYAI_DIR / "building_geometry_v1.parquet"

OUTPUT_COLUMNS = ["building_id", "city", "plz", "street", "street_key", "geometry", "building_type"]

# Non-8-PLZ Neuss pilot/typology segments excluded by the NEUSS_PLZ* filter
# below (found during the 2026-07-11 Neuss buildings fix; documented in
# territoryai/scratch/neuss_phase2_progress.md). Informational only — the
# actual filter is the NEUSS_PLZ prefix check, not this literal list.
NEUSS_EXCLUDED_SEGMENTS_NOTE = (
    "ALLERHEILIGEN_PILOT_SEG_01, NEUSS_DENSE_01, NEUSS_OLD_TOWN_01, "
    "NEUSS_SUBURBAN_01, NEUSS_VILLA_01 (931 rows total)"
)


def norm_l2(s):
    """German-aware street-name normalization.

    COPIED VERBATIM from territoryai/scratch/street_match_audit.py's norm_l2
    — this is the canonical WBS#1 audit normalization function. Must not
    diverge: the territoryai geometry endpoint independently recomputes
    street_key from street_ranking's street_name using this exact same
    function, and joins it against this parquet's precomputed street_key
    column. Any drift between the two copies would silently break every
    building-to-street match.
    """
    if s is None:
        return ''
    s = str(s).strip().lower()
    s = re.sub(r'\s+', ' ', s)
    if s == '':
        return s
    s = s.replace('ß', 'ss')
    s = re.sub(r'[‐‑‒–—−]', '-', s)
    s = re.sub(r'\s*-\s*', '-', s)
    s = re.sub(r'\s*str\.$', 'strasse', s)
    s = re.sub(r'\s*str$', 'strasse', s)
    s = re.sub(r'\s+strasse$', 'strasse', s)
    s = re.sub(r'[.,;:]+$', '', s)
    return s.strip()


def main():
    # -----------------------------------------------------------------
    # 1. Read the three source building parquets
    # -----------------------------------------------------------------
    df_augsburg = pd.read_parquet(AUGSBURG_BUILDINGS)
    logger.info(f"[LOAD] {AUGSBURG_BUILDINGS.name}: {len(df_augsburg)} raw rows")
    df_kaarst = pd.read_parquet(KAARST_BUILDINGS)
    logger.info(f"[LOAD] {KAARST_BUILDINGS.name}: {len(df_kaarst)} raw rows")
    df_neuss = pd.read_parquet(NEUSS_BUILDINGS)
    logger.info(f"[LOAD] {NEUSS_BUILDINGS.name}: {len(df_neuss)} raw rows")
    df_leipzig = pd.read_parquet(LEIPZIG_BUILDINGS)
    logger.info(f"[LOAD] {LEIPZIG_BUILDINGS.name}: {len(df_leipzig)} raw rows")

    for label, df in [("Augsburg", df_augsburg), ("Kaarst", df_kaarst), ("Neuss", df_neuss), ("Leipzig", df_leipzig)]:
        assert "city" in df.columns, f"{label} buildings parquet has no 'city' column"

    # -----------------------------------------------------------------
    # 2. Verify/use each source's existing `city` column
    # -----------------------------------------------------------------
    aug_city_vals = set(df_augsburg["city"].dropna().unique())
    assert aug_city_vals == {"Augsburg"}, f"Augsburg city column has unexpected values: {aug_city_vals}"
    logger.info(f"[VERIFY] Augsburg city column verified: 100% tagged {aug_city_vals}")

    kaarst_city_vals = set(df_kaarst["city"].dropna().unique())
    assert kaarst_city_vals == {"Kaarst"}, f"Kaarst city column has unexpected values: {kaarst_city_vals}"
    logger.info(f"[VERIFY] Kaarst city column verified: 100% tagged {kaarst_city_vals}")

    leipzig_city_vals = set(df_leipzig["city"].dropna().unique())
    assert leipzig_city_vals == {"Leipzig"}, f"Leipzig city column has unexpected values: {leipzig_city_vals}"
    logger.info(f"[VERIFY] Leipzig city column verified: 100% tagged {leipzig_city_vals}")

    # Neuss's shared buildings.parquet also carries non-Neuss pilot segments
    # (city=None for some of them) — full city-column verification happens
    # AFTER the NEUSS_PLZ* filter below, since that filter is what actually
    # scopes this file down to real Neuss rows.

    # -----------------------------------------------------------------
    # 3. Neuss-only filter: keep ONLY rows whose segment_id starts with
    #    NEUSS_PLZ (excludes the 931-row non-8-PLZ pilot segments)
    # -----------------------------------------------------------------
    neuss_before = len(df_neuss)
    neuss_mask = df_neuss["segment_id"].astype(str).str.startswith("NEUSS_PLZ")
    df_neuss_excluded = df_neuss[~neuss_mask]
    df_neuss = df_neuss[neuss_mask].copy()
    neuss_after = len(df_neuss)
    excluded_breakdown = df_neuss_excluded["segment_id"].astype(str).value_counts().to_dict()
    logger.info(
        f"[FILTER] Neuss NEUSS_PLZ* filter: {neuss_before} -> {neuss_after} rows "
        f"({neuss_before - neuss_after} excluded: {excluded_breakdown})"
    )
    assert neuss_before - neuss_after == 931, (
        f"Expected exactly 931 excluded non-8-PLZ Neuss rows ({NEUSS_EXCLUDED_SEGMENTS_NOTE}), "
        f"got {neuss_before - neuss_after}. Upstream buildings.parquet may have changed scope — "
        f"investigate before proceeding rather than silently re-baselining this assertion."
    )

    assert df_neuss["city"].isna().sum() == 0, "NEUSS_PLZ* rows contain a null city after filter"
    neuss_city_vals = set(df_neuss["city"].unique())
    assert neuss_city_vals == {"Neuss"}, f"Neuss city column (post NEUSS_PLZ* filter) has unexpected values: {neuss_city_vals}"
    logger.info(f"[VERIFY] Neuss city column verified post-filter: 100% tagged {neuss_city_vals}")

    # -----------------------------------------------------------------
    # 4. Compute street_key via the canonical WBS#1 norm_l2 (all 3 cities)
    # -----------------------------------------------------------------
    for label, df in [("Augsburg", df_augsburg), ("Kaarst", df_kaarst), ("Neuss", df_neuss), ("Leipzig", df_leipzig)]:
        df["street_key"] = df["street"].map(norm_l2)
    logger.info("[STREET_KEY] street_key computed for all 4 cities via norm_l2 (WBS#1 canonical)")

    # -----------------------------------------------------------------
    # 5. Verify geometry is already WKT (don't reconvert), then build the
    #    exact output column set: building_id, city, plz, street,
    #    street_key, geometry, building_type. plz <- postal_code.
    # -----------------------------------------------------------------
    frames = []
    for label, df in [("Augsburg", df_augsburg), ("Kaarst", df_kaarst), ("Neuss", df_neuss), ("Leipzig", df_leipzig)]:
        looks_like_wkt = df["geometry"].astype(str).str.match(r'^[A-Z]+\s*\(')
        n_not_wkt = int((~looks_like_wkt).sum())
        assert n_not_wkt == 0, f"{label}: {n_not_wkt} rows have a geometry value that is not WKT text"
        wkt_types = df["geometry"].astype(str).str.extract(r'^([A-Z]+)')[0].value_counts().to_dict()
        logger.info(f"[VERIFY] {label} geometry is 100% WKT text. WKT type breakdown: {wkt_types}")

        out = pd.DataFrame({
            "building_id": df["building_id"],
            "city": df["city"],
            "plz": df["postal_code"],
            "street": df["street"],
            "street_key": df["street_key"],
            "geometry": df["geometry"],
            "building_type": df["building_type"],
        })
        frames.append(out)

    merged = pd.concat(frames, ignore_index=True)
    assert list(merged.columns) == OUTPUT_COLUMNS, f"Unexpected output column set/order: {list(merged.columns)}"

    # -----------------------------------------------------------------
    # 6. Drop rows with empty/null street or postal_code (now named `plz`).
    #    Real drops ARE expected here (Augsburg/Kaarst both carry genuine
    #    blank-postal_code rows per scratch/street_match_audit.md) — the
    #    hard requirement is that ZERO nulls remain in the output afterward,
    #    verified below rather than silently trusted.
    # -----------------------------------------------------------------
    def _is_blank(series):
        return series.isna() | (series.astype(str).str.strip() == "")

    before_drop = len(merged)
    blank_street = _is_blank(merged["street"])
    blank_plz = _is_blank(merged["plz"])
    drop_mask = blank_street | blank_plz
    n_dropped = int(drop_mask.sum())
    logger.info(
        f"[FILTER] Dropping {n_dropped} rows with empty/null street or postal_code "
        f"(blank_street={int(blank_street.sum())}, blank_plz={int(blank_plz.sum())}, before={before_drop})"
    )
    merged = merged[~drop_mask].copy()
    after_drop = len(merged)

    assert merged["street"].isna().sum() == 0
    assert (merged["street"].astype(str).str.strip() == "").sum() == 0
    assert merged["plz"].isna().sum() == 0
    assert (merged["plz"].astype(str).str.strip() == "").sum() == 0
    logger.info(f"[CHECK] 0-null assertion passed: street and plz are 100% populated in {after_drop} output rows")

    # -----------------------------------------------------------------
    # 7. Write full overwrite (from-scratch rebuild every run — NOT an
    #    append/idempotent-replace like merge_augsburg_into_territoryai.py)
    # -----------------------------------------------------------------
    TERRITORYAI_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUTPUT_PARQUET, index=False)
    logger.info(f"[WRITE] {OUTPUT_PARQUET} ({len(merged)} rows, full overwrite)")

    # -----------------------------------------------------------------
    # 8. Summary logging: row count per city, per-plz row count, total
    # -----------------------------------------------------------------
    logger.info("[SUMMARY] Row count per city:")
    for city, cnt in merged["city"].value_counts().items():
        logger.info(f"[SUMMARY]   {city}: {cnt}")

    logger.info("[SUMMARY] Row count per PLZ:")
    for plz, cnt in merged["plz"].value_counts().sort_index().items():
        logger.info(f"[SUMMARY]   {plz}: {cnt}")

    logger.info(f"[SUMMARY] TOTAL rows written: {len(merged)}")


if __name__ == "__main__":
    main()
