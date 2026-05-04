"""
ingest_mastr_pv_by_plz.py
==========================
Step 1 of D-ESS Phase 2: Extract MaStR PV installation counts for
ALL 8 Neuss PLZs from local XML exports.

Root-fix (2026-05-04):
  - Numerator: Only RESIDENTIAL-scale PV units counted (Nettonennleistung <= 30 kWp).
  - Denominator: Uses building_universe.count_buildings_per_segment() which takes
    max(buildings.parquet, Foundation dedup) per PLZ for the most reliable count.
  - Audit fields: pv_total_count and pv_commercial_count preserved for auditability.

Computes per-PLZ:
  - pv_installation_count : residential PV units (<= 30 kWp)
  - pv_adoption_rate      : pv_installation_count / estimated_buildings (unified)
  - pv_market_gap         : 1 - pv_adoption_rate  (remaining opportunity)
  - data_confidence       : based on residential install count size

Output:
  data/sources/mastr/mastr_pv_adoption_neuss.parquet
  output/layer2/mastr_pv_adoption_report.json

Regression test:
  PLZ 41470 TOTAL count must equal fill_rate_report_plz41470.json total_records_in_plz = 1259
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.building_universe import count_buildings_per_segment

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
log = logging.getLogger("MASTR_INGEST")

BASE_DIR     = Path(__file__).resolve().parent.parent
XML_DIR      = BASE_DIR / "data" / "sources" / "mastr" / "2026-03-12_einheitensolar"
BUILDINGS_P  = BASE_DIR / "data" / "buildings.parquet"
OUTPUT_P     = BASE_DIR / "data" / "sources" / "mastr" / "mastr_pv_adoption_neuss.parquet"
REPORT_P     = BASE_DIR / "output" / "layer2" / "mastr_pv_adoption_report.json"
REGRESSION_F = BASE_DIR / "data" / "sources" / "mastr" / "profiling" / "mastr_fill_rate_report_plz41470.json"

# Target PLZs
NEUSS_PLZS = {"41460", "41462", "41464", "41466", "41468", "41469", "41470", "41472"}

# PLZ -> segment mapping (for joining to layer2)
PLZ_TO_SEGMENT = {
    "41460": "NEUSS_PLZ41460",
    "41462": "NEUSS_PLZ41462",
    "41464": "NEUSS_PLZ41464",
    "41466": "NEUSS_PLZ41466",
    "41468": "NEUSS_PLZ41468",
    "41469": "NEUSS_PLZ41469",
    "41470": "NEUSS_PLZ41470",
    "41472": "NEUSS_PLZ41472",
}

# Expected count for regression test
REGRESSION_PLZ      = "41470"
REGRESSION_EXPECTED = 1259

RESIDENTIAL_MAX_KWP = 30.0   # Industry standard: residential PV <= 30 kWp


def extract_plz_counts_from_xml(xml_dir: Path, target_plzs: set[str]) -> dict[str, dict]:
    """
    Scan MaStR XML for PV installations in target PLZs.
    Extracts both PLZ and Nettonennleistung per unit to separate
    residential (<=30 kWp) from commercial installations.

    Returns {plz: {"total": int, "residential": int, "commercial": int}}.
    """
    results: dict[str, dict] = {
        plz: {"total": 0, "residential": 0, "commercial": 0}
        for plz in target_plzs
    }
    xml_files = sorted(xml_dir.glob("EinheitenSolar_*.xml"))

    if not xml_files:
        log.error(f"[SCAN] No XML files found in {xml_dir}")
        return results

    log.info(f"[SCAN] Scanning {len(xml_files)} XML files for PLZs: {sorted(target_plzs)}")
    log.info(f"[SCAN] Residential threshold: <= {RESIDENTIAL_MAX_KWP} kWp")

    plz_pattern = re.compile(r"<Postleitzahl>(\d{5})</Postleitzahl>")
    cap_pattern = re.compile(r"<Nettonennleistung>([\d.]+)</Nettonennleistung>")
    unit_pattern = re.compile(r"<EinheitSolar>(.+?)</EinheitSolar>", re.DOTALL)

    chunk_size = 8 * 1024 * 1024   # 8 MB
    overlap    = 10000             # generous overlap for unit block boundaries

    for xml_file in xml_files:
        file_hits = 0
        try:
            with open(xml_file, "rb") as f:
                bom = f.read(2)
                if bom == b"\xff\xfe":
                    encoding = "utf-16-le"
                elif bom == b"\xfe\xff":
                    encoding = "utf-16-be"
                else:
                    f.seek(0)
                    encoding = "utf-16"

                carry = ""
                while True:
                    raw = f.read(chunk_size)
                    if not raw:
                        text = carry
                        carry = ""
                    else:
                        text = carry + raw.decode(encoding, errors="ignore")
                        carry = text[-overlap:] if len(text) > overlap else text
                        text = text[:-overlap] if len(text) > overlap else text

                    for m in unit_pattern.finditer(text):
                        unit_xml = m.group(1)
                        plz_m = plz_pattern.search(unit_xml)
                        if not plz_m or plz_m.group(1) not in target_plzs:
                            continue

                        plz = plz_m.group(1)
                        results[plz]["total"] += 1
                        file_hits += 1

                        cap_m = cap_pattern.search(unit_xml)
                        capacity = float(cap_m.group(1)) if cap_m and cap_m.group(1) else 0.0

                        if capacity <= RESIDENTIAL_MAX_KWP:
                            results[plz]["residential"] += 1
                        else:
                            results[plz]["commercial"] += 1

                    if not raw:
                        break

            if file_hits:
                log.info(f"[SCAN] {xml_file.name}: {file_hits} hits")

        except Exception as e:
            log.error(f"[SCAN] Error reading {xml_file.name}: {e}")

    for plz in sorted(results.keys()):
        r = results[plz]
        log.info(f"[SCAN] PLZ {plz}: total={r['total']} residential={r['residential']} commercial={r['commercial']}")

    return results


def load_building_counts(plz_to_seg: dict[str, str]) -> dict[str, int]:
    """Load unified building count per PLZ from building_universe (max of buildings.parquet and Foundation)."""
    seg_counts = count_buildings_per_segment()
    seg_to_plz = {v: k for k, v in plz_to_seg.items()}
    result: dict[str, int] = {}
    for seg, cnt in seg_counts.items():
        plz = seg_to_plz.get(str(seg))
        if plz:
            result[plz] = cnt
    log.info(f"[BLDG] Building counts per PLZ (unified): {result}")
    return result


def compute_adoption_table(
    pv_results: dict[str, dict],
    bldg_counts: dict[str, int],
    plz_to_seg: dict[str, str],
) -> pd.DataFrame:
    """Build adoption table using residential PV count and unified building denominator."""
    rows = []
    for plz, seg_id in plz_to_seg.items():
        r         = pv_results.get(plz, {"total": 0, "residential": 0, "commercial": 0})
        pv_resid  = r["residential"]
        pv_total  = r["total"]
        bldg_cnt  = bldg_counts.get(plz, 1)

        adoption_rate = round(min(1.0, pv_resid / bldg_cnt), 4) if bldg_cnt > 0 else None
        market_gap    = round(1.0 - adoption_rate, 4) if adoption_rate is not None else None

        if pv_resid >= 200:
            confidence = "HIGH"
        elif pv_resid >= 50:
            confidence = "MEDIUM"
        elif pv_resid >= 10:
            confidence = "LOW"
        else:
            confidence = "VERY_LOW"

        rows.append({
            "plz":                    plz,
            "segment_id":             seg_id,
            "pv_installation_count":  pv_resid,       # residential only
            "pv_total_count":         pv_total,        # audit: all PV
            "pv_commercial_count":    r["commercial"], # audit: commercial
            "estimated_buildings":    bldg_cnt,
            "pv_adoption_rate":       adoption_rate,
            "pv_market_gap":          market_gap,
            "data_confidence":        confidence,
        })

    df = pd.DataFrame(rows).sort_values("plz").reset_index(drop=True)
    return df


def regression_check(pv_counts: dict[str, int]) -> bool:
    """Verify PLZ 41470 count matches fill_rate_report_plz41470.json."""
    if not REGRESSION_F.exists():
        log.warning("[REGRESSION] Reference file not found — skipping")
        return True
    with open(REGRESSION_F, encoding="utf-8") as f:
        ref = json.load(f)
    expected = ref["metadata"]["total_records_in_plz"]
    actual   = pv_counts.get(REGRESSION_PLZ, 0)
    if actual == expected:
        log.info(f"[REGRESSION] PLZ {REGRESSION_PLZ}: count={actual} == expected={expected} PASS")
        return True
    else:
        log.error(
            f"[REGRESSION] PLZ {REGRESSION_PLZ}: count={actual} != expected={expected} FAIL "
            f"(delta={actual - expected})"
        )
        return False


def main():
    log.info("=" * 60)
    log.info("  MASTR PV ADOPTION INGESTION — ALL NEUSS PLZs")
    log.info("=" * 60)

    if not XML_DIR.exists():
        log.error(f"[GUARD] XML directory not found: {XML_DIR}")
        return

    # Step 1: Scan XML files (returns {plz: {total, residential, commercial}})
    pv_results = extract_plz_counts_from_xml(XML_DIR, NEUSS_PLZS)

    # Step 2: Regression check (uses total count, not filtered)
    pv_total_counts = {plz: r["total"] for plz, r in pv_results.items()}
    regression_ok = regression_check(pv_total_counts)
    if not regression_ok:
        log.error("[ABORT] Regression check failed — check XML scan logic before proceeding")
        return

    # Step 3: Building counts (unified: max of buildings.parquet and Foundation)
    bldg_counts = load_building_counts(PLZ_TO_SEGMENT)

    # Step 4: Compute adoption table (residential PV / unified buildings)
    df = compute_adoption_table(pv_results, bldg_counts, PLZ_TO_SEGMENT)

    log.info("\n[RESULT] PV Adoption Table:")
    log.info(df.to_string(index=False))

    # Step 5: Write outputs
    OUTPUT_P.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_P, index=False)
    log.info(f"[OUTPUT] Parquet -> {OUTPUT_P}")

    # Audit JSON
    report = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "xml_source_dir":    str(XML_DIR),
        "xml_files_scanned": len(list(XML_DIR.glob("EinheitenSolar_*.xml"))),
        "target_plzs":       sorted(NEUSS_PLZS),
        "regression_passed": regression_ok,
        "results": df.to_dict(orient="records"),
    }
    REPORT_P.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_P, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"[AUDIT] -> {REPORT_P}")

    # Summary
    print(f"\n{'='*60}")
    print("  NEUSS PV ADOPTION SUMMARY")
    print(f"{'='*60}")
    print(df[["plz", "pv_installation_count", "pv_total_count", "pv_commercial_count",
              "estimated_buildings", "pv_adoption_rate", "pv_market_gap",
              "data_confidence"]].to_string(index=False))
    print(f"\nTotal residential PV in Neuss: {df['pv_installation_count'].sum()}")
    print(f"Total all PV in Neuss: {df['pv_total_count'].sum()}")


if __name__ == "__main__":
    main()
