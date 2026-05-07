"""
ingest_waermenetz_nrw.py
=========================
D-ESS Proxy-Purge Phase 1: KWP Neuss Data Ingestion (Two Layers)

Downloads the official NRW Kommunale Wärmeplanung (KWP) dataset for Neuss
and extracts TWO layers:

  Layer A — WBM-NRW-Waermelinien (street-level heat demand lines)
    → data/sources/waermenetz/waermelinien_neuss_v1.parquet
    → Used by: field_05 (heat constraint), field_06 (HP opportunity)

  Layer B — Sanierung-Energietraeger-Baublock (block-level energy source mix)
    → data/sources/waermenetz/sanierung_baublock_neuss_v1.parquet
    → Used by: field_05 (Waerme_p → heat constraint score)
               field_06 (Gas_p + Oel_p → HP opportunity score)

Data Source:
  OpenGeodata.NRW — Kommunale Wärmeplanung (KWP)
  URL: https://www.opengeodata.nrw.de/produkte/umwelt_klima/energie/kwp/
  File: KWP-NRW_05162024_Neuss_EPSG25832_Shape.zip  (84MB, cached)

Key fields by layer:

  Layer A (Waermelinien — LineString):
    WLD_ID, Strassenla, Waermedich (MWh/km/yr), RW_WW, GHD_PW, Anzahl_Obj

  Layer B (Sanierung Baublock — Polygon):
    block_id, Waerme_p (% district heat), Gas_p, Oel_p,
    HauptEnEnt (dominant source), RealChaKat (renovation chance),
    RealChance (numeric), Anz_beheiz (heated buildings count)

Run:
  python scripts/ingest_waermenetz_nrw.py

Design note:
  Classification thresholds (LOW/MEDIUM/HIGH constraint etc.) are NOT
  applied here. This script only stores raw signals. All classification
  logic lives in field_05_heat_modifier.py and field_06_hp_uplift.py.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

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
SOURCES_DIR  = BASE_DIR / "data" / "sources" / "waermenetz"
CACHE_DIR    = SOURCES_DIR / "_cache"
OUTPUT_PARQ  = SOURCES_DIR / "waermelinien_neuss_v1.parquet"
OUTPUT_META  = SOURCES_DIR / "waermelinien_neuss_v1_meta.json"

SOURCES_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Layer A output
OUTPUT_BAUBLOCK_PARQ = SOURCES_DIR / "sanierung_baublock_neuss_v1.parquet"
OUTPUT_BAUBLOCK_META = SOURCES_DIR / "sanierung_baublock_neuss_v1_meta.json"

# ---------------------------------------------------------------------------
# Source config
# ---------------------------------------------------------------------------
KWP_BASE_URL = "https://www.opengeodata.nrw.de/produkte/umwelt_klima/energie/kwp"
KWP_FILENAME = "KWP-NRW_05162024_Neuss_EPSG25832_Shape.zip"
KWP_URL      = f"{KWP_BASE_URL}/{KWP_FILENAME}"
ZIP_CACHE    = CACHE_DIR / KWP_FILENAME

# Layer names inside the ZIP
WAERMELINIEN_LAYER = "WBM-NRW-Waermelinien_05162024_Neuss.shp"
BAUBLOCK_LAYER     = "Sanierung-Energietraeger-Baublock_05162024_Neuss.shp"

# Columns to keep — Layer A (Waermelinien)
KEEP_COLS_WAERMELINIEN = [
    "WLD_ID",
    "Gemeinde",
    "AGS",
    "Strassenla",
    "RW_WW",
    "GHD_PW",
    "RW_WW_GHD_",
    "Anzahl_Adr",
    "Anzahl_Obj",
    "Waermedich",
    "Shape_Leng",
    "geometry",
]

# Columns to keep — Layer B (Sanierung Baublock)
# Primary signals for field_05 (Waerme_p) and field_06 (Gas_p, Oel_p, RealChaKat)
KEEP_COLS_BAUBLOCK = [
    "block_id",
    "AGS",
    "Gemeindena",
    "Anz_beheiz",   # count of heated buildings
    "Objekte",      # total objects in block
    "Gas_abs",      # absolute count — gas heated buildings
    "Oel_abs",      # absolute count — oil heated buildings
    "Strom_abs",    # absolute count — electric heated buildings
    "Waerme_abs",   # absolute count — district heat buildings
    "EE_abs",       # absolute count — renewable energy heated buildings
    "Gas_p",        # % gas                 → HP opportunity signal
    "Oel_p",        # % oil                 → HP opportunity signal
    "Strom_p",      # % electric
    "Waerme_p",     # % district heating    → heat constraint signal
    "EE_p",         # % renewables
    "HauptEnEnt",   # dominant energy source string
    "HauptEnAnz",   # count of buildings with dominant source
    "RealChance",   # numeric renovation chance
    "RealChaKat",   # categorical renovation chance → HP opportunity signal
    "geometry",
]

SCHEMA_VERSION_WAERMELINIEN = "waermelinien_neuss_v1"
SCHEMA_VERSION_BAUBLOCK     = "sanierung_baublock_neuss_v1"


# ---------------------------------------------------------------------------
# Step 1: Download
# ---------------------------------------------------------------------------
def download_kwp_zip() -> Path:
    """
    Download the Neuss KWP shapefile ZIP from OpenGeodata.NRW.
    Cached on disk — re-uses cached copy if already downloaded.
    """
    if ZIP_CACHE.exists() and ZIP_CACHE.stat().st_size > 1_000_000:
        size_mb = ZIP_CACHE.stat().st_size // 1024 // 1024
        logger.info(f"[DL-1] CACHE HIT — using existing file: {ZIP_CACHE} ({size_mb} MB)")
        return ZIP_CACHE

    logger.info(f"[DL-1] Downloading from: {KWP_URL}")
    resp = requests.get(KWP_URL, stream=True, timeout=300)
    resp.raise_for_status()

    total_bytes = int(resp.headers.get("content-length", 0))
    chunk_size  = 10 * 1024 * 1024   # 10 MB chunks
    downloaded  = 0

    with open(ZIP_CACHE, "wb") as f:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_bytes:
                    pct = downloaded * 100 // total_bytes
                    logger.info(
                        f"[DL-1]   {downloaded // 1024 // 1024} MB "
                        f"/ {total_bytes // 1024 // 1024} MB  ({pct}%)"
                    )

    size_mb = ZIP_CACHE.stat().st_size // 1024 // 1024
    logger.info(f"[DL-1] Download complete → {ZIP_CACHE} ({size_mb} MB)")
    return ZIP_CACHE


# ---------------------------------------------------------------------------
# Step 2: Validate ZIP integrity
# ---------------------------------------------------------------------------
def validate_zip(zip_path: Path) -> None:
    """Verify ZIP contains both required layers."""
    logger.info(f"[DL-2] Validating ZIP integrity: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()

    for required_layer in [WAERMELINIEN_LAYER, BAUBLOCK_LAYER]:
        if required_layer not in names:
            logger.error(
                f"[DL-2] ERROR: Expected layer '{required_layer}' not found in ZIP. "
                f"Found .shp layers: {[n for n in names if n.endswith('.shp')]}"
            )
            sys.exit(1)
        logger.info(f"[DL-2] ✓ Layer confirmed: {required_layer}")

    logger.info(f"[DL-2]   Total files in ZIP: {len(names)}")


# ---------------------------------------------------------------------------
# Step 3A: Parse Waermelinien (Layer A)
# ---------------------------------------------------------------------------
def parse_waermelinien(zip_path: Path):
    """
    Load the Wärmelinien LineString layer from the ZIP.
    Returns a GeoDataFrame with cleaned columns.
    """
    try:
        import geopandas as gpd
    except ImportError:
        logger.error("[PARSE-A] geopandas not installed. Run: pip install geopandas")
        sys.exit(1)

    logger.info(f"[PARSE-A] Loading: {WAERMELINIEN_LAYER}")
    gdf = gpd.read_file(f"zip://{zip_path}!{WAERMELINIEN_LAYER}")
    logger.info(f"[PARSE-A] Rows: {len(gdf)} | CRS: {gdf.crs} | Geom: {gdf.geometry.geom_type.unique().tolist()}")

    for col in ["Waermedich", "Strassenla", "WLD_ID"]:
        if col not in gdf.columns:
            logger.error(f"[PARSE-A] MISSING required column: {col}")
            sys.exit(1)

    present_cols = [c for c in KEEP_COLS_WAERMELINIEN if c in gdf.columns]
    gdf = gdf[present_cols].copy()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    gdf["ingest_ts_utc"]  = ts
    gdf["schema_version"] = SCHEMA_VERSION_WAERMELINIEN
    gdf["source_file"]    = KWP_FILENAME

    desc = gdf["Waermedich"].describe()
    logger.info("[PARSE-A] Waermedich (MWh/km/year): " +
                " | ".join(f"{k}={v:.1f}" for k, v in desc.items()))
    logger.info(f"[PARSE-A] Null count: {gdf['Waermedich'].isna().sum()}  Zero count: {(gdf['Waermedich']==0).sum()}")
    return gdf


# ---------------------------------------------------------------------------
# Step 3B: Parse Sanierung-Energietraeger-Baublock (Layer B)
# ---------------------------------------------------------------------------
def parse_sanierung_baublock(zip_path: Path):
    """
    Load the Sanierung-Energietraeger-Baublock polygon layer.
    This provides block-level energy source breakdown:
      - Waerme_p  → % buildings with district heating  (field_05 input)
      - Gas_p + Oel_p → % HP conversion candidates     (field_06 input)
      - RealChaKat    → official renovation opportunity (field_06 input)
    """
    try:
        import geopandas as gpd
    except ImportError:
        logger.error("[PARSE-B] geopandas not installed.")
        sys.exit(1)

    logger.info(f"[PARSE-B] Loading: {BAUBLOCK_LAYER}")
    gdf = gpd.read_file(f"zip://{zip_path}!{BAUBLOCK_LAYER}")
    logger.info(f"[PARSE-B] Rows: {len(gdf)} | CRS: {gdf.crs} | Geom: {gdf.geometry.geom_type.unique().tolist()}")

    # Guard: required columns
    for col in ["Waerme_p", "Gas_p", "Oel_p", "HauptEnEnt"]:
        if col not in gdf.columns:
            logger.error(f"[PARSE-B] MISSING required column: {col}")
            sys.exit(1)

    present_cols = [c for c in KEEP_COLS_BAUBLOCK if c in gdf.columns]
    gdf = gdf[present_cols].copy()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    gdf["ingest_ts_utc"]  = ts
    gdf["schema_version"] = SCHEMA_VERSION_BAUBLOCK
    gdf["source_file"]    = KWP_FILENAME

    # Log key signal distributions
    logger.info("[PARSE-B] HauptEnEnt distribution:")
    for val, cnt in gdf["HauptEnEnt"].value_counts(dropna=False).items():
        logger.info(f"  {str(val):<35}  {cnt:>5} blocks")

    logger.info(f"[PARSE-B] Waerme_p  — mean={gdf['Waerme_p'].mean():.1f}%  "
                f"blocks>40%: {(gdf['Waerme_p']>=40).sum()}")
    logger.info(f"[PARSE-B] Gas_p+Oel_p — mean={(gdf['Gas_p']+gdf['Oel_p']).mean():.1f}%")

    null_realcha = gdf["RealChaKat"].isna().sum() if "RealChaKat" in gdf.columns else "N/A"
    logger.info(f"[PARSE-B] RealChaKat NULL count: {null_realcha} / {len(gdf)} ({null_realcha*100//len(gdf) if isinstance(null_realcha, int) else '?'}%)")

    return gdf


# ---------------------------------------------------------------------------
# Step 4: Write outputs
# ---------------------------------------------------------------------------
def write_waermelinien(gdf) -> None:
    """Write Layer A GeoParquet + metadata JSON."""
    gdf.to_parquet(OUTPUT_PARQ, index=False)
    size_kb = OUTPUT_PARQ.stat().st_size // 1024
    logger.info(f"[OUT-A] GeoParquet → {OUTPUT_PARQ}  ({size_kb} KB)")

    meta = {
        "schema_version": SCHEMA_VERSION_WAERMELINIEN,
        "source_url":     KWP_URL,
        "source_file":    KWP_FILENAME,
        "layer":          WAERMELINIEN_LAYER,
        "row_count":      len(gdf),
        "crs":            "EPSG:25832",
        "geometry_type":  "LineString",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "waermedich_stats": {
            "count":  int(gdf["Waermedich"].count()),
            "mean":   round(float(gdf["Waermedich"].mean()), 2),
            "median": round(float(gdf["Waermedich"].median()), 2),
            "min":    round(float(gdf["Waermedich"].min()), 2),
            "max":    round(float(gdf["Waermedich"].max()), 2),
        },
        "columns": list(gdf.columns),
        "note": "Raw heat demand density lines. Classification applied in field_05.",
    }
    with open(OUTPUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    logger.info(f"[OUT-A] Metadata JSON → {OUTPUT_META}")


def write_baublock(gdf) -> None:
    """Write Layer B GeoParquet + metadata JSON."""
    gdf.to_parquet(OUTPUT_BAUBLOCK_PARQ, index=False)
    size_kb = OUTPUT_BAUBLOCK_PARQ.stat().st_size // 1024
    logger.info(f"[OUT-B] GeoParquet → {OUTPUT_BAUBLOCK_PARQ}  ({size_kb} KB)")

    haupt_counts = gdf["HauptEnEnt"].value_counts(dropna=False).to_dict()
    realcha_null = int(gdf["RealChaKat"].isna().sum()) if "RealChaKat" in gdf.columns else None

    meta = {
        "schema_version": SCHEMA_VERSION_BAUBLOCK,
        "source_url":     KWP_URL,
        "source_file":    KWP_FILENAME,
        "layer":          BAUBLOCK_LAYER,
        "row_count":      len(gdf),
        "crs":            "EPSG:25832",
        "geometry_type":  "Polygon/MultiPolygon",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_stats": {
            "waerme_p_mean":      round(float(gdf["Waerme_p"].mean()), 2),
            "waerme_p_blocks_ge40": int((gdf["Waerme_p"] >= 40).sum()),
            "gas_oil_p_mean":     round(float((gdf["Gas_p"] + gdf["Oel_p"]).mean()), 2),
            "haupt_en_ent":       {str(k): int(v) for k, v in haupt_counts.items()},
            "realcha_null_count": realcha_null,
        },
        "used_by": ["field_05_heat_modifier", "field_06_hp_uplift"],
        "columns": list(gdf.columns),
        "note": "Block-level energy source mix. Drives heat constraint (field_05) and HP opportunity (field_06).",
    }
    with open(OUTPUT_BAUBLOCK_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    logger.info(f"[OUT-B] Metadata JSON → {OUTPUT_BAUBLOCK_META}")


# ---------------------------------------------------------------------------
# Step 5: Summary report
# ---------------------------------------------------------------------------
def print_summary(gdf_a, gdf_b) -> None:
    """Print human-readable console summary for both layers."""
    print("\n" + "=" * 65)
    print("  INGEST COMPLETE: NRW KWP Neuss — Two Layers")
    print("=" * 65)

    print(f"  Layer A (Waermelinien):")
    print(f"    Segments : {len(gdf_a)}  |  CRS: EPSG:25832  |  Geom: LineString")
    print(f"    Waermedich   Min={gdf_a['Waermedich'].min():.0f}  "
          f"Median={gdf_a['Waermedich'].median():.0f}  "
          f"Max={gdf_a['Waermedich'].max():.0f} MWh/km/yr")
    print(f"    -> {OUTPUT_PARQ.name}")

    print()
    print(f"  Layer B (Sanierung Baublock):")
    print(f"    Blocks   : {len(gdf_b)}  |  CRS: EPSG:25832  |  Geom: Polygon")
    print(f"    Waerme_p   mean={gdf_b['Waerme_p'].mean():.1f}%  "
          f"blocks>=40%: {(gdf_b['Waerme_p']>=40).sum()}")
    gas_oil = gdf_b["Gas_p"] + gdf_b["Oel_p"]
    print(f"    Gas+Oel_p  mean={gas_oil.mean():.1f}%  (HP conversion candidates)")
    print(f"    HauptEnEnt 'Wärmenetz' dominant: {(gdf_b['HauptEnEnt']=='Wärmenetz').sum()} blocks")
    print(f"    -> {OUTPUT_BAUBLOCK_PARQ.name}")

    print("=" * 65)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info("=" * 65)
    logger.info("  INGEST: NRW KWP Neuss (Layer A: Waermelinien + Layer B: Baublock)")
    logger.info("=" * 65)

    zip_path = download_kwp_zip()
    validate_zip(zip_path)

    # Layer A — Waermelinien
    gdf_a = parse_waermelinien(zip_path)
    write_waermelinien(gdf_a)

    # Layer B — Sanierung Baublock
    gdf_b = parse_sanierung_baublock(zip_path)
    write_baublock(gdf_b)

    print_summary(gdf_a, gdf_b)
    logger.info("[DONE] Both layers ingested. Ready for field_05 + field_06.")


if __name__ == "__main__":
    main()
