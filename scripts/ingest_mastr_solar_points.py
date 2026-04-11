#!/usr/bin/env python3
"""
ingest_mastr_solar_points.py
================================
Production-grade MaStR solar XML ingestion script for D-ESS FIELD_04.

Source: d-ess-engine/data/sources/mastr/2026-03-12_einheitensolar/EinheitenSolar_*.xml
Output:
  - d-ess-engine/data/derived/mastr/mastr_solar_points_2026-03-12.csv
  - d-ess-engine/data/derived/mastr/mastr_solar_points_2026-03-12_summary.json

Confirmed XML Structure (from live probe on 2026-03-13):
  - Root wrapper element: varies by file (EinheitenSolar or similar)
  - Repeating record element: <EinheitSolar>
  - Encoding: UTF-16 LE with BOM (bytes 0xFF 0xFE)
  - NO coordinate fields in EinheitSolar records. Coordinates exist only
    in Lokation XML, joinable via LokationMaStRNummer.
  - Available fields: EinheitMastrNummer, LokationMaStRNummer,
    Bruttoleistung, Nettonennleistung, Postleitzahl, Ort, Gemeinde,
    Landkreis, Bundesland, EinheitBetriebsstatus, Inbetriebnahmedatum, etc.

Architecture:
  Phase 1 - EinheitSolar extract: scan all 60 EinheitenSolar XML files,
             emit normalized records with null lat/lon.
  Phase 2 - Lokation enrich (optional): if Lokation XML dir is specified,
             scan those files and join coordinates by LokationMaStRNummer.
  Phase 3 - Output CSV + JSON summary.

Usage:
  python ingest_mastr_solar_points.py \\
    --solar-dir  "d-ess-engine/data/sources/mastr/2026-03-12_einheitensolar" \\
    --lokation-dir "d-ess-engine/data/sources/mastr/lokationen" \\
    --output-csv   "d-ess-engine/data/derived/mastr/mastr_solar_points_2026-03-12.csv" \\
    --output-json  "d-ess-engine/data/derived/mastr/mastr_solar_points_2026-03-12_summary.json"
"""

import argparse
import csv
import io
import json
import logging
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("MaStR_Solar_Ingest")

# ---------------------------------------------------------------------------
# Constants – confirmed from live XML probe on 2026-03-13
# ---------------------------------------------------------------------------

SOLAR_RECORD_TAG = "EinheitSolar"  # Confirmed repeating element

# Canonical CSV columns
CSV_COLUMNS = [
    "unit_id",
    "location_id",
    "lat",
    "lon",
    "kwp",
    "commissioning_date",
    "plz",
    "city",
    "municipality",
    "state",
    "address",
    "operational_status",
    "source_file",
]

# Mapping: CSV column -> XML tag name (local name, no namespace)
EINHEIT_FIELD_MAP = {
    "unit_id":           "EinheitMastrNummer",
    "location_id":       "LokationMaStRNummer",
    "kwp":               "Bruttoleistung",
    "commissioning_date": "Inbetriebnahmedatum",
    "plz":               "Postleitzahl",
    "city":              "Ort",
    "municipality":      "Gemeinde",
    "state":             "Bundesland",       # code, e.g. 1402
    "operational_status": "EinheitBetriebsstatus",
    # address: not present in EinheitSolar; will be null
    # lat/lon: not present; filled from Lokation join
}

# Coordinate field names confirmed in MaStR Lokation XML
LOKATION_COORD_CANDIDATES = [
    "Breitengrad",      # latitude (German)
    "Laengengrad",      # longitude (German, ASCII fallback)
    "Längengrad",       # longitude (UTF-8 umlaut variant)
    "CoordinateLat",    # alternative English field
    "CoordinateLon",
    "Breite",
    "Laenge",
    "Latitude",
    "Longitude",
]
LOKATION_ID_TAG = "MastrNummer"


# ---------------------------------------------------------------------------
# Helper – strip namespace from tag string
# ---------------------------------------------------------------------------
def local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


# ---------------------------------------------------------------------------
# Phase 1 – Extract EinheitSolar records
# ---------------------------------------------------------------------------
def extract_solar_records(solar_dir: Path) -> tuple[list[dict], dict]:
    """
    Stream-parse all EinheitenSolar_*.xml files.
    Returns (records_list, debug_info).
    """
    xml_files = sorted(solar_dir.glob("EinheitenSolar_*.xml"))
    if not xml_files:
        # Fallback: case-insensitive
        xml_files = sorted(solar_dir.glob("einheitensolar_*.xml"))

    log.info(f"Found {len(xml_files)} solar XML file(s) in {solar_dir}")

    records = []
    files_ok = 0
    files_err = 0
    total_parsed = 0
    field_hit_counts: dict[str, int] = {}
    tag_universe: set[str] = set()
    warnings: list[str] = []

    for xml_path in xml_files:
        try:
            with io.open(xml_path, mode="rt", encoding="utf-16le") as fh:
                context = ET.iterparse(fh, events=("end",))
                for event, elem in context:
                    ltag = local_tag(elem.tag)
                    tag_universe.add(ltag)

                    if ltag == SOLAR_RECORD_TAG:
                        total_parsed += 1

                        # Build child lookup
                        children: dict[str, str | None] = {}
                        for child in elem:
                            cl = local_tag(child.tag)
                            tag_universe.add(cl)
                            children[cl] = child.text

                        # Assemble normalized record
                        rec: dict = dict.fromkeys(CSV_COLUMNS, None)
                        rec["source_file"] = xml_path.name

                        for col, xml_tag in EINHEIT_FIELD_MAP.items():
                            raw = children.get(xml_tag)
                            if raw is not None:
                                field_hit_counts[col] = field_hit_counts.get(col, 0) + 1
                            rec[col] = raw

                        # Type coercions
                        if rec["kwp"] is not None:
                            try:
                                rec["kwp"] = float(rec["kwp"])
                            except ValueError:
                                warnings.append(
                                    f"[{xml_path.name}] kwp parse error for unit {rec['unit_id']}: {rec['kwp']!r}"
                                )
                                rec["kwp"] = None

                        records.append(rec)
                        elem.clear()

            files_ok += 1

        except ET.ParseError as exc:
            msg = f"XML parse error in {xml_path.name}: {exc}"
            log.warning(msg)
            warnings.append(msg)
            files_err += 1
        except Exception as exc:  # noqa: BLE001
            msg = f"Unexpected error in {xml_path.name}: {exc}"
            log.error(msg)
            warnings.append(msg)
            files_err += 1

    debug = {
        "solar_files_found": len(xml_files),
        "solar_files_parsed_ok": files_ok,
        "solar_files_with_errors": files_err,
        "total_solar_records": total_parsed,
        "tag_universe_from_solar": sorted(tag_universe),
        "field_hit_counts": field_hit_counts,
        "warnings_phase1": warnings,
    }
    log.info(f"Phase 1 complete: {total_parsed} EinheitSolar records from {files_ok} file(s).")
    return records, debug


# ---------------------------------------------------------------------------
# Phase 2 – Enrich with Lokation coordinates (optional)
# ---------------------------------------------------------------------------
def build_lokation_coord_index(lokation_dir: Path) -> tuple[dict[str, dict], dict]:
    """
    Stream-parse all Lokation XML files and build an index:
      { lokation_mastr_nummer (str) -> {"lat": float|None, "lon": float|None} }
    Also returns debug info.

    XML confirmed structure:
      Repeating element: <Lokation>
      ID field:         <MastrNummer>   (e.g., SEL986313296524)
      Reverse-join:     <VerknuepfteEinheitenMaStRNummern>  (SEE... ids)
      Coordinate fields: Breitengrad / Laengengrad (if present)
    """
    xml_files = sorted(lokation_dir.glob("Lokationen_*.xml"))
    log.info(f"Found {len(xml_files)} Lokation XML file(s) in {lokation_dir}")

    index: dict[str, dict] = {}
    discovered_coord_paths: set[str] = set()
    warnings: list[str] = []
    total_lokation_records = 0
    coords_found = 0

    LOKATION_RECORD_TAG = "Lokation"  # confirmed from raw XML probe

    for xml_path in xml_files:
        try:
            with io.open(xml_path, mode="rt", encoding="utf-16le") as fh:
                context = ET.iterparse(fh, events=("end",))
                for event, elem in context:
                    ltag = local_tag(elem.tag)

                    # Only process <Lokation> elements specifically
                    if ltag != LOKATION_RECORD_TAG:
                        elem.clear()
                        continue

                    total_lokation_records += 1

                    # Build child lookup
                    children: dict[str, str | None] = {
                        local_tag(c.tag): c.text for c in elem
                    }

                    lokation_id = children.get(LOKATION_ID_TAG)
                    if not lokation_id:
                        elem.clear()
                        continue

                    lat_val = lon_val = None

                    for tag_name, text in children.items():
                        tn_lower = tag_name.lower()
                        is_lat = any(
                            h in tn_lower
                            for h in ("breitengrad", "breite", "latitude")
                        )
                        is_lon = any(
                            h in tn_lower
                            for h in ("laengengrad", "laenge", "longitude", "längengrad")
                        )

                        if is_lat and text:
                            try:
                                lat_val = float(text.replace(",", "."))
                                discovered_coord_paths.add(f"Lokation/{tag_name}")
                            except ValueError:
                                warnings.append(f"lat parse error: {tag_name}={text!r}")

                        if is_lon and text:
                            try:
                                lon_val = float(text.replace(",", "."))
                                discovered_coord_paths.add(f"Lokation/{tag_name}")
                            except ValueError:
                                warnings.append(f"lon parse error: {tag_name}={text!r}")

                    if lat_val is not None or lon_val is not None:
                        coords_found += 1
                        index[lokation_id] = {"lat": lat_val, "lon": lon_val}

                    elem.clear()

        except ET.ParseError as exc:
            msg = f"XML parse error in {xml_path.name}: {exc}"
            log.warning(msg)
            warnings.append(msg)
        except Exception as exc:  # noqa: BLE001
            msg = f"Unexpected error in {xml_path.name}: {exc}"
            log.error(msg)
            warnings.append(msg)

    debug = {
        "lokation_files_found": len(xml_files),
        "total_lokation_records_seen": total_lokation_records,
        "lokation_records_with_coords": coords_found,
        "discovered_coordinate_paths": sorted(discovered_coord_paths),
        "warnings_phase2": warnings,
    }
    log.info(
        f"Phase 2 complete: {total_lokation_records} Lokation records scanned, "
        f"{coords_found} with coordinates."
    )
    return index, debug


# ---------------------------------------------------------------------------
# Phase 3 – Merge, write CSV, write JSON summary
# ---------------------------------------------------------------------------
def run(args: argparse.Namespace) -> None:
    solar_dir = Path(args.solar_dir)
    output_csv = Path(args.output_csv)
    output_json = Path(args.output_json)

    if not solar_dir.exists():
        log.error(f"Solar source directory not found: {solar_dir}")
        sys.exit(1)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Phase 1: EinheitSolar extraction
    # ------------------------------------------------------------------
    records, debug1 = extract_solar_records(solar_dir)

    # ------------------------------------------------------------------
    # Phase 2: Lokation coordinate enrichment (optional)
    # ------------------------------------------------------------------
    lokation_index: dict[str, dict] = {}
    debug2: dict = {
        "lokation_enrichment": "SKIPPED – no --lokation-dir provided",
        "discovered_coordinate_paths": [],
    }

    if args.lokation_dir:
        lok_dir = Path(args.lokation_dir)
        if lok_dir.exists():
            lokation_index, debug2 = build_lokation_coord_index(lok_dir)
        else:
            log.warning(f"Lokation dir not found: {lok_dir}. Skipping coordinate enrichment.")
            debug2["lokation_enrichment"] = f"SKIPPED – dir not found: {lok_dir}"

    # Merge coordinates into records
    joined_count = 0
    for rec in records:
        lok_id = rec.get("location_id")
        if lok_id and lok_id in lokation_index:
            rec["lat"] = lokation_index[lok_id].get("lat")
            rec["lon"] = lokation_index[lok_id].get("lon")
            if rec["lat"] is not None:
                joined_count += 1

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    total = len(records)
    with_coords = sum(1 for r in records if r.get("lat") is not None)
    without_coords = total - with_coords
    coord_pct = round(with_coords / total * 100, 2) if total > 0 else 0.0

    sample_with = next((r for r in records if r.get("lat") is not None), None)
    sample_without = next((r for r in records if r.get("lat") is None), None)

    # ------------------------------------------------------------------
    # Write CSV
    # ------------------------------------------------------------------
    with output_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    log.info(f"CSV written: {output_csv} ({total} rows)")

    # ------------------------------------------------------------------
    # Write JSON summary
    # ------------------------------------------------------------------
    summary = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": str(solar_dir),
        "files_scanned": debug1["solar_files_found"],
        "solar_files_parsed_ok": debug1["solar_files_parsed_ok"],
        "solar_files_with_errors": debug1["solar_files_with_errors"],
        "total_records_seen": total,
        "records_with_coordinates": with_coords,
        "records_without_coordinates": without_coords,
        "coordinate_coverage_pct": coord_pct,
        "lokation_join_count": joined_count,
        "field_hit_counts": debug1["field_hit_counts"],
        "discovered_coordinate_paths": debug2.get("discovered_coordinate_paths", []),
        "tag_universe_from_solar": debug1.get("tag_universe_from_solar", []),
        "sample_record_with_coordinates": sample_with,
        "sample_record_without_coordinates": sample_without,
        "parsing_warnings": debug1.get("warnings_phase1", []) + debug2.get("warnings_phase2", []),
        "architecture_note": (
            "EinheitSolar XML contains NO direct coordinates. "
            "Coordinates reside in Lokation XML and are joined via LokationMaStRNummer. "
            "If lokation_join_count is 0 and lokation XML files are provided, "
            "verify that the Lokation snapshot covers the same time period / region as EinheitSolar."
        ),
    }

    with output_json.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False, default=str)

    log.info(f"JSON summary written: {output_json}")

    # ------------------------------------------------------------------
    # Terminal summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  MaStR Solar Ingestion — Run Summary")
    print("=" * 60)
    print(f"  Files scanned        : {debug1['solar_files_found']}")
    print(f"  Total solar records  : {total}")
    print(f"  With coordinates     : {with_coords} ({coord_pct}%)")
    print(f"  Without coordinates  : {without_coords}")
    print(f"  Lokation join hits   : {joined_count}")
    print(f"  Output CSV           : {output_csv}")
    print(f"  Output JSON summary  : {output_json}")
    if with_coords == 0:
        print("")
        print("  ⚠  COORDINATE COVERAGE = 0%")
        print("     EinheitSolar XML contains NO lat/lon fields.")
        print("     Coordinates require a matching Lokation XML snapshot.")
        print("     Provide --lokation-dir with a snapshot covering the same")
        print("     units (check LokationMaStRNummer key overlap).")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    base = Path(__file__).resolve().parents[1]  # d-ess-engine/

    parser = argparse.ArgumentParser(
        prog="ingest_mastr_solar_points",
        description="Extract MaStR solar unit records from EinheitenSolar XML files.",
    )
    parser.add_argument(
        "--solar-dir",
        default=str(base / "data" / "sources" / "mastr" / "2026-03-12_einheitensolar"),
        help="Directory containing EinheitenSolar_*.xml files",
    )
    parser.add_argument(
        "--lokation-dir",
        default=str(base / "data" / "sources" / "mastr" / "lokationen"),
        help="(Optional) Directory containing Lokationen_*.xml files for coordinate enrichment",
    )
    parser.add_argument(
        "--output-csv",
        default=str(base / "data" / "derived" / "mastr" / "mastr_solar_points_2026-03-12.csv"),
        help="Output CSV path",
    )
    parser.add_argument(
        "--output-json",
        default=str(base / "data" / "derived" / "mastr" / "mastr_solar_points_2026-03-12_summary.json"),
        help="Output JSON summary path",
    )
    return parser


if __name__ == "__main__":
    parser = build_arg_parser()
    run(parser.parse_args())
