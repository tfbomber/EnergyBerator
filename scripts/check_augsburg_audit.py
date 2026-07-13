"""
check_augsburg_audit.py
=========================
Read-only regression baseline for the Augsburg pipeline run of 2026-07-07.
Mirrors check_phase4_audit.py's style (hardcoded expected counts from THIS
real run, not formulas) — future changes to the Augsburg pipeline should be
diffed against these numbers, same as Neuss/Kaarst's own audit scripts.
"""

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]

EXPECTED_PLZ_BUILDING_COUNTS = {
    "86150": 1349, "86152": 1338, "86153": 1076, "86154": 1704,
    "86156": 4287, "86157": 2739, "86159": 1575, "86161": 1879,
    "86163": 3570, "86165": 2063, "86167": 2025, "86169": 3343,
    "86179": 3919, "86199": 5056,
}
EXPECTED_TOTAL_BUILDINGS = 37275  # + 1352 AUGSBURG_OSM_GENERAL (untagged/no addr:street)
EXPECTED_CLUSTERS = 1683
EXPECTED_STREETS_AFTER_DEDUP = 1452  # 1453 minus "Am Wertachdamm" (2026-07-08: excluded as a
                                     # 100%-allotment-garden colony, not real houses — see
                                     # _find_fully_allotment_streets() in build_augsburg_layer2.py)
EXPECTED_L2_ROWS = 14
EXPECTED_SLR_COLS = 51
EXPECTED_SEG_COLS = 36
EXCLUDED_ALLOTMENT_STREET = ("Am Wertachdamm", "86199")


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    return cond


def main():
    ok = True

    df_b = pd.read_parquet(BASE_DIR / "data" / "augsburg_buildings.parquet")
    ok &= check(f"Total Augsburg buildings == {EXPECTED_TOTAL_BUILDINGS}",
                len(df_b) == EXPECTED_TOTAL_BUILDINGS)
    for plz, expected in EXPECTED_PLZ_BUILDING_COUNTS.items():
        actual = (df_b["segment_id"] == f"AUGSBURG_OSM_{plz}").sum()
        ok &= check(f"PLZ {plz} building count == {expected}", actual == expected)

    df_l2 = pd.read_parquet(BASE_DIR / "data" / "layer2" / "augsburg_layer2_input_table.parquet")
    ok &= check(f"Layer2 input table has {EXPECTED_L2_ROWS} rows", len(df_l2) == EXPECTED_L2_ROWS)
    ok &= check("Layer2 roof_suitability_score_norm is NOT flat 0.4444 (bug regression guard)",
                df_l2["roof_suitability_score_norm"].nunique() > 1)

    df_slr = pd.read_parquet(BASE_DIR / "data" / "layer2" / "augsburg_street_level_ranking_v1.parquet")
    ok &= check(f"Street-level ranking has {EXPECTED_STREETS_AFTER_DEDUP} rows",
                len(df_slr) == EXPECTED_STREETS_AFTER_DEDUP)
    ok &= check(f"Street-level ranking has {EXPECTED_SLR_COLS} columns", len(df_slr.columns) == EXPECTED_SLR_COLS)
    ok &= check("Zero NaN in street-level ranking", df_slr.isna().sum().sum() == 0)
    ok &= check("14 unique segments present", df_slr["segment_id"].nunique() == 14)
    excl_street, excl_plz = EXCLUDED_ALLOTMENT_STREET
    ok &= check(f"'{excl_street}' ({excl_plz}) correctly excluded (allotment-garden colony, not real houses)",
                df_slr[(df_slr["street_name"] == excl_street) & (df_slr["plz"] == excl_plz)].empty)

    pvgis_path = BASE_DIR / "data" / "derived" / "pvgis" / "augsburg_plz_yield_kwh_kwp.json"
    ok &= check("PVGIS yield file exists", pvgis_path.exists())
    if pvgis_path.exists():
        import json
        pvgis = json.loads(pvgis_path.read_text(encoding="utf-8"))
        yields = [v["yield_kwh_kwp_yr"] for v in pvgis["plz_yield"].values()]
        ok &= check("14 PVGIS yield values present", len(yields) == 14)
        ok &= check("All PVGIS yields in plausible Bavaria range [1050, 1150] kWh/kWp/yr",
                     all(1050 <= y <= 1150 for y in yields))

    # Merged territoryai parquets (only check if merge has been run)
    tai_slr = Path(r"D:\Stock Analysis\territoryai\data\layer2\street_level_ranking_v1.parquet")
    tai_seg = Path(r"D:\Stock Analysis\territoryai\data\layer2\street_ranking_v1.parquet")
    if tai_slr.exists():
        df_tai_slr = pd.read_parquet(tai_slr)
        aug_rows = df_tai_slr[df_tai_slr["segment_id"].astype(str).str.startswith("AUGSBURG_")]
        ok &= check(f"territoryai street_level_ranking_v1 contains {EXPECTED_STREETS_AFTER_DEDUP} Augsburg rows",
                    len(aug_rows) == EXPECTED_STREETS_AFTER_DEDUP)
        ok &= check("territoryai street_level_ranking_v1 has zero NaN after merge",
                    df_tai_slr.isna().sum().sum() == 0)
    if tai_seg.exists():
        df_tai_seg = pd.read_parquet(tai_seg)
        aug_seg_rows = df_tai_seg[df_tai_seg["street_id"].astype(str).str.startswith("AUGSBURG_")]
        ok &= check(f"territoryai street_ranking_v1 contains {EXPECTED_L2_ROWS} Augsburg rows",
                    len(aug_seg_rows) == EXPECTED_L2_ROWS)
        ok &= check("territoryai street_ranking_v1 has zero NaN after merge",
                    df_tai_seg.isna().sum().sum() == 0)

    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
