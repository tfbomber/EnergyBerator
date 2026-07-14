"""
field_04_pv_adoption.py
========================
FIELD_04: PV Adoption Signal — Real PLZ-Proportional Allocation (E3)

Truth Level  : E3 (Allocated Proxy)
Source       : MaStR EinheitSolar national CSV (data/derived/mastr/)
Version      : V1_REAL — replaces mock_mastr_signal_v1
Date         : 2026-03-22

Scope
-----
- Only processes REAL_GROUNDED segments (segment_registry status = REAL_GROUNDED)
- SYNTHETIC segments are explicitly excluded from real PV coverage
- Current pilot: NEUSS_PLZ41470 / PLZ 41470 only

Architecture (see pv_coverage_audit_plan.md)
--------------------------------------------
Phase 1 : Load MaStR CSV, filter PLZ + status + residential kWp cap
Phase 2 : Proportional allocation (segment_buildings / plz_buildings × morphology_factor)
Phase 3 : Normalize -> E3 confidence penalty (x0.5) -> score cap at 0.50
Phase 4 : Emit field_04_pv_adoption.parquet (schema-compatible with prior contract)
Phase 5 : Emit audit JSON to output/field_04/runs/ for provenance

Score Contract (unchanged downstream schema)
-------------------------------------------
  segment_id   : str
  field_id     : "field_04"
  field_value  : float [0.0, 0.50]  <- E3 hard cap
  confidence   : float (E3 = 0.45)
  source       : "PLZ_ALLOCATION_E3"
  notes        : str

Data Quality Guards (per audit plan Part G)
-------------------------------------------
  - Filter operational_status == "35" (active only)
  - Filter kwp <= RESIDENTIAL_KWP_CAP (100 kWp) to screen commercial/utility
  - Minimum support threshold: >= MIN_PLZ_RECORDS before assigning real score
  - Uniform distribution assumption documented; not treated as spatial truth
"""

import pandas as pd
import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("FIELD_04_REAL_V1")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MASTR_CSV_PATH = BASE_DIR / "data" / "derived" / "mastr" / "mastr_solar_points_2026-03-12.csv"
OUTPUT_PARQUET  = BASE_DIR / "data" / "fields" / "field_04_pv_adoption.parquet"
OUTPUT_AUDIT_DIR = BASE_DIR / "output" / "field_04" / "runs"

# Residential kWp cap — screens out commercial/utility-scale systems.
# A single-family or small-MFH PV system rarely exceeds 100 kWp.
# This is a pragmatic heuristic, not a verified regulatory boundary.
RESIDENTIAL_KWP_CAP = 100.0

# MaStR operational_status code for "active / In Betrieb"
ACTIVE_STATUS = "35"

# Minimum MaStR records in a PLZ before assigning a real adoption score.
# Below this, signal is too sparse to be informative. Default to neutral.
MIN_PLZ_RECORDS = 5

# Benchmark: 20% adoption rate normalises to field_value = 1.0 (before E3 penalty)
ADOPTION_BENCHMARK = 0.20

# E3 confidence tier constraints
E3_CONFIDENCE_LEVEL  = 0.45
E3_PENALTY_FACTOR    = 0.50
E3_MAX_FIELD_VALUE   = 0.50   # hard cap after penalty

# ---------------------------------------------------------------------------
# Segment registry: REAL_GROUNDED segments only
# Each entry: segment_id -> { plz, segment_buildings, plz_buildings, morphology_factor }
# SOURCE: output/stage6/segment_registry_neuss_v1.json
#
# IMPORTANT: SYNTHETIC segments are deliberately absent from this table.
# Do not add SYNTHETIC segments here. They have fabricated building counts
# and would produce meaningless adoption rates.
# ---------------------------------------------------------------------------
# segment_buildings refreshed 2026-07-14 (Neuss Layer2 rearch v2, second
# attempt — see territoryai .ai/implementation_plan_neuss_layer2_rearch_v2.md)
# to the corrected post-spatial-PLZ-fallback buildings.parquet counts
# (2026-07-14: build_neuss_buildings_from_geojson.py's spatial fallback
# recovered 1577 previously-dropped untagged buildings). plz_buildings /
# morphology_factor are DELIBERATELY left unchanged — confirmed by real
# computation (not assumed) that switching plz_buildings to the D4=gamma
# residential-count definition (as done for Leipzig/Augsburg the same day)
# produces IMPLAUSIBLE results for Neuss: 6 of 8 PLZ would compute a raw
# adoption intensity of 24-82% (physically impossible PV adoption rates),
# because Neuss's hand-tuned plz_buildings values (1000-8500) represent a
# genuine "all buildings in this PLZ" estimate that is legitimately larger
# than the OSM residential-with-addr:street count here — unlike Leipzig/
# Augsburg where that gap was small. Only segment_buildings (the numerator
# side) is refreshed; plz_buildings stays the historical hand-tuned
# baseline with no documented derivation formula (same as the 2026-07-11
# note this superseded).
REAL_GROUNDED_SEGMENTS = {
    "NEUSS_PLZ41470": {
        "plz": "41470",
        "segment_buildings": 1494,       # unchanged 2026-07-14 (41470 untouched by today's spatial fix — separate legacy POINT source)
        "plz_buildings": 4250,           # baseline estimate for PLZ 41470 (Neuss Norf/Rosellerheide) — UNCHANGED, no formula (D2)
        "morphology_factor": 1.1,        # slight uplift for residential density suitability
        "city": "Neuss",
        "persistent_id": "ALLERHEILIGEN_PILOT_SEG_01",
    },
    "NEUSS_PLZ41472": {
        "plz": "41472",
        "segment_buildings": 1867,       # was 1859; +8 from 2026-07-14 spatial-PLZ recovery
        "plz_buildings": 6500,           # baseline estimate for PLZ 41472 (Norf / Selikum areas) — UNCHANGED, no formula (D2)
        "morphology_factor": 1.0,        # neutral — SFH-dominant but POINT geometry limits certainty
        "city": "Neuss",
        "persistent_id": "NEUSS_SUBURBAN_01",
    },
    "NEUSS_PLZ41464": {
        "plz": "41464",
        "segment_buildings": 4295,       # was 3599; +696 from 2026-07-14 spatial-PLZ recovery (largest recovery of the 8)
        "plz_buildings": 5000,           # baseline estimate for PLZ 41464 (Grimlinghausen / Allerheiligen) — UNCHANGED, no formula (D2)
        "morphology_factor": 0.95,       # slight discount — mixed SFH/rowhouse profile, higher morphology variance
        "city": "Neuss",
        "persistent_id": "NEUSS_DENSE_01",
    },
    "NEUSS_PLZ41460": {
        "plz": "41460",
        "segment_buildings": 2094,       # was 1682; +412 from 2026-07-14 spatial-PLZ recovery
        "plz_buildings": 1000,           # UNCHANGED, no formula (D2)
        "morphology_factor": 0.80,       # dense city center
        "city": "Neuss",
        "persistent_id": "NEUSS_PLZ41460",
    },
    "NEUSS_PLZ41462": {
        "plz": "41462",
        "segment_buildings": 3393,       # was 3010; +383 from 2026-07-14 spatial-PLZ recovery
        "plz_buildings": 8500,           # UNCHANGED, no formula (D2)
        "morphology_factor": 0.90,
        "city": "Neuss",
        "persistent_id": "NEUSS_PLZ41462",
    },
    "NEUSS_PLZ41466": {
        "plz": "41466",
        "segment_buildings": 1702,       # was 1670; +32 from 2026-07-14 spatial-PLZ recovery
        "plz_buildings": 5200,           # UNCHANGED, no formula (D2)
        "morphology_factor": 0.95,
        "city": "Neuss",
        "persistent_id": "NEUSS_PLZ41466",
    },
    "NEUSS_PLZ41468": {
        "plz": "41468",
        "segment_buildings": 4087,       # was 4053; +34 from 2026-07-14 spatial-PLZ recovery
        "plz_buildings": 6000,           # UNCHANGED, no formula (D2)
        "morphology_factor": 0.95,
        "city": "Neuss",
        "persistent_id": "NEUSS_PLZ41468",
    },
    "NEUSS_PLZ41469": {
        "plz": "41469",
        "segment_buildings": 2186,       # was 2174; +12 from 2026-07-14 spatial-PLZ recovery
        "plz_buildings": 5000,           # UNCHANGED, no formula (D2)
        "morphology_factor": 0.95,
        "city": "Neuss",
        "persistent_id": "NEUSS_PLZ41469",
    },
}


# ---------------------------------------------------------------------------
# Load & prepare MaStR data
# ---------------------------------------------------------------------------

def load_mastr_plz(plz: str) -> pd.DataFrame:
    """
    Load national MaStR CSV, filter to target PLZ with active + residential systems.
    Returns a filtered DataFrame. Logs richly for audit traceability.

    Column assumptions from mastr_solar_points_2026-03-12_summary.json:
      plz / city / operational_status / kwp / commissioning_date / unit_id
    """
    if not MASTR_CSV_PATH.exists():
        raise FileNotFoundError(
            f"[FIELD_04] MaStR CSV not found: {MASTR_CSV_PATH}. "
            "Verify data/derived/mastr/ is populated."
        )

    logger.info(f"[FIELD_04] Reading MaStR CSV from: {MASTR_CSV_PATH}")
    logger.info("[FIELD_04] This file is ~646MB — read may take 10-30s depending on hardware.")

    df = pd.read_csv(
        MASTR_CSV_PATH,
        dtype={"plz": str, "operational_status": str},
        usecols=["unit_id", "plz", "kwp", "operational_status", "commissioning_date"],
        low_memory=False,
    )

    total_records = len(df)
    logger.info(f"[FIELD_04] Total records loaded: {total_records:,}")

    # Filter 1: Target PLZ
    df_plz = df[df["plz"] == plz].copy()
    logger.info(f"[FIELD_04] Records in PLZ {plz}: {len(df_plz):,}")

    # Filter 2: Active systems only (operational_status = "35")
    df_active = df_plz[df_plz["operational_status"] == ACTIVE_STATUS].copy()
    logger.info(f"[FIELD_04] Active (status=35) records: {len(df_active):,}")

    # Filter 3: Residential kWp cap (exclude commercial/utility-scale)
    df_residential = df_active[df_active["kwp"] <= RESIDENTIAL_KWP_CAP].copy()
    excluded_large = len(df_active) - len(df_residential)
    logger.info(
        f"[FIELD_04] After residential kWp cap (<= {RESIDENTIAL_KWP_CAP} kWp): "
        f"{len(df_residential):,} records ({excluded_large} large systems excluded)"
    )

    return df_residential


# ---------------------------------------------------------------------------
# Proportional allocation
# ---------------------------------------------------------------------------

def compute_adoption(
    df_plz: pd.DataFrame,
    segment_id: str,
    config: dict,
) -> dict:
    """
    Compute proportional allocation of PLZ-level PV count to segment.
    Returns a full audit payload dict.
    """
    plz             = config["plz"]
    seg_buildings   = config["segment_buildings"]
    plz_buildings   = config["plz_buildings"]
    morph_factor    = config["morphology_factor"]
    city            = config["city"]
    persistent_id   = config["persistent_id"]

    plz_count = len(df_plz)
    plz_kwp   = round(df_plz["kwp"].sum(), 2)

    logger.info(
        f"[FIELD_04][{segment_id}] PLZ truth: {plz_count} active residential systems, "
        f"{plz_kwp} kWp total"
    )

    # --- Minimum support gate ---
    if plz_count < MIN_PLZ_RECORDS:
        logger.warning(
            f"[FIELD_04][{segment_id}] PLZ record count ({plz_count}) below "
            f"MIN_PLZ_RECORDS ({MIN_PLZ_RECORDS}). Defaulting to neutral signal."
        )
        return _build_payload(
            segment_id=segment_id,
            persistent_id=persistent_id,
            city=city,
            plz=plz,
            plz_count=plz_count,
            plz_kwp=plz_kwp,
            pv_est=0,
            kwp_est=0.0,
            adoption_intensity=0.0,
            field_value=0.25,            # neutral midpoint under E3
            confidence=E3_CONFIDENCE_LEVEL,
            adoption_status="INSUFFICIENT_PLZ_DATA",
            notes=(
                f"PLZ {plz} has only {plz_count} records < MIN_PLZ_RECORDS {MIN_PLZ_RECORDS}. "
                "Defaulting to neutral. Signal not trustworthy at this sample size."
            ),
        )

    # --- Proportional allocation ---
    base_ratio  = seg_buildings / plz_buildings
    final_ratio = min(base_ratio * morph_factor, 1.0)

    pv_est  = round(plz_count * final_ratio)
    kwp_est = round(plz_kwp * final_ratio, 1)

    adoption_intensity = pv_est / seg_buildings if seg_buildings > 0 else 0.0

    logger.info(
        f"[FIELD_04][{segment_id}] Allocation ratio: {base_ratio:.4f} x morph={morph_factor} "
        f"= {final_ratio:.4f} -> {pv_est} systems, {kwp_est} kWp"
    )
    logger.info(
        f"[FIELD_04][{segment_id}] Raw adoption intensity: {adoption_intensity:.2%}"
    )

    # --- Adoption status band ---
    if adoption_intensity > 0.15:
        adoption_status = "STRONG"
    elif adoption_intensity > 0.05:
        adoption_status = "MODERATE"
    else:
        adoption_status = "WEAK"

    # --- Normalize -> E3 penalty -> cap ---
    # NOTE: band thresholds above are for status labelling only.
    # They are NOT treated as tuned product boundaries. See audit plan §5 (V1 threshold caution).
    raw_score    = min(adoption_intensity / ADOPTION_BENCHMARK, 1.0)    # [0,1]
    e3_score     = round(min(raw_score * E3_PENALTY_FACTOR, E3_MAX_FIELD_VALUE), 4)

    logger.info(
        f"[FIELD_04][{segment_id}] Scoring: raw_norm={raw_score:.4f} -> "
        f"e3_score={e3_score:.4f} (penalty={E3_PENALTY_FACTOR}, cap={E3_MAX_FIELD_VALUE})"
    )

    notes = (
        f"PLZ={plz} | Active residential systems: {plz_count} | PLZ kWp: {plz_kwp} | "
        f"Segment buildings: {seg_buildings} | Allocation ratio: {final_ratio:.4f} | "
        f"Allocated systems: {pv_est} | Adoption intensity: {adoption_intensity:.2%} | "
        f"Status: {adoption_status} | E3 score cap applied at {E3_MAX_FIELD_VALUE}. "
        "ALLOCATED_PROXY — not point-confirmed. Exact kWp cap filter: "
        f"<= {RESIDENTIAL_KWP_CAP} kWp per system."
    )

    return _build_payload(
        segment_id=segment_id,
        persistent_id=persistent_id,
        city=city,
        plz=plz,
        plz_count=plz_count,
        plz_kwp=plz_kwp,
        pv_est=pv_est,
        kwp_est=kwp_est,
        adoption_intensity=adoption_intensity,
        field_value=e3_score,
        confidence=E3_CONFIDENCE_LEVEL,
        adoption_status=adoption_status,
        notes=notes,
    )


def _build_payload(
    segment_id, persistent_id, city, plz,
    plz_count, plz_kwp,
    pv_est, kwp_est, adoption_intensity,
    field_value, confidence, adoption_status, notes,
) -> dict:
    return {
        # --- Downstream parquet schema (unchanged contract) ---
        "segment_id":   segment_id,
        "field_id":     "field_04",
        "field_value":  field_value,
        "confidence":   confidence,
        "source":       "PLZ_ALLOCATION_E3",
        "notes":        notes,
        # --- Audit metadata (retained in audit JSON, not parquet) ---
        "_audit": {
            "persistent_id":         persistent_id,
            "city":                  city,
            "plz":                   plz,
            "source_truth_level":    "POSTAL_CODE_AGGREGATE",
            "location_accuracy":     "ALLOCATED_PROXY",
            "evidence_tier":         "E3",
            "pv_installation_count_est": pv_est,
            "pv_total_kwp_est":      kwp_est,
            "pv_adoption_intensity": round(adoption_intensity, 6),
            "pv_adoption_status":    adoption_status,
            "plz_active_residential_records": plz_count,
            "plz_total_kwp":         plz_kwp,
            "score_raw_normalised":  round(min(adoption_intensity / ADOPTION_BENCHMARK, 1.0), 4),
            "e3_penalty_factor":     E3_PENALTY_FACTOR,
            "e3_score_cap":          E3_MAX_FIELD_VALUE,
            "residential_kwp_cap":   RESIDENTIAL_KWP_CAP,
            "spatial_confirmability": "UNCONFIRMABLE_AT_POINT_LEVEL",
            "allowed_for_segment_level_ranking":              True,
            "allowed_for_point_level_installation_claims": False,
            "allowed_for_street_level_targeting":          False,
            "run_timestamp_utc":     datetime.now(timezone.utc).isoformat(),
        }
    }


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run() -> pd.DataFrame:
    """
    Main entry point. Processes all REAL_GROUNDED segments.
    Emits field_04_pv_adoption.parquet and per-segment audit JSON.
    Returns the output DataFrame.
    """
    logger.info("[FIELD_04] ==============================================")
    logger.info("[FIELD_04] FIELD_04 PV ADOPTION — REAL V1 (E3 PLZ Allocation)")
    logger.info("[FIELD_04] Scope: REAL_GROUNDED segments only")
    logger.info(f"[FIELD_04] Segments in scope: {list(REAL_GROUNDED_SEGMENTS.keys())}")
    logger.info("[FIELD_04] ==============================================")

    # Collect all unique PLZs needed
    plz_set = {cfg["plz"] for cfg in REAL_GROUNDED_SEGMENTS.values()}

    # Load MaStR data per PLZ (only load once per PLZ)
    plz_cache: dict[str, pd.DataFrame] = {}
    for plz in plz_set:
        plz_cache[plz] = load_mastr_plz(plz)

    # Compute adoption per segment
    parquet_rows = []
    audit_records = []

    for segment_id, config in REAL_GROUNDED_SEGMENTS.items():
        logger.info(f"[FIELD_04] Processing segment: {segment_id}")
        plz = config["plz"]
        df_plz = plz_cache[plz]
        payload = compute_adoption(df_plz, segment_id, config)

        # Parquet row (schema-contract fields only)
        parquet_rows.append({
            "segment_id":  payload["segment_id"],
            "field_id":    payload["field_id"],
            "field_value": payload["field_value"],
            "confidence":  payload["confidence"],
            "source":      payload["source"],
            "notes":       payload["notes"],
        })

        # Full audit record (includes _audit metadata)
        audit_records.append(payload)

    # Emit parquet
    df_out = pd.DataFrame(parquet_rows)
    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    # Preserve every existing row NOT recomputed by this run — i.e. any other
    # city's segments already in the shared parquet (Augsburg / Kaarst, added by
    # their own run_<city>_fields.py drivers, which monkey-patch REAL_GROUNDED_
    # SEGMENTS in-process, not by this run()).
    #
    # BUGFIX 2026-07-12: the previous unconditional df_out.to_parquet() rewrote
    # the file with ONLY this run's REAL_GROUNDED_SEGMENTS rows, silently wiping
    # every non-recomputed segment on each run. This bit in all three directions:
    # a plain Neuss run wiped Augsburg+Kaarst; run_kaarst_fields wiped Augsburg
    # (run() writes before the driver re-appends); run_augsburg_fields wiped
    # Kaarst. Confirmed the shipped parquet held only the 8 Neuss rows. Same
    # root-cause pattern as field_02_building_type.py's fix (2026-07-11); mirror
    # it here — key off "not in this run's recomputed segment set", never off a
    # Neuss-only constant. The RETURNED df_out stays recomputed-only, so callers
    # that filter it (run_kaarst_fields.py / run_augsburg_fields.py) are
    # unaffected; only the on-disk write is merged.
    recomputed_segments = set(REAL_GROUNDED_SEGMENTS.keys())
    if OUTPUT_PARQUET.exists():
        existing = pd.read_parquet(OUTPUT_PARQUET)
        preserved = existing[~existing["segment_id"].isin(recomputed_segments)]
        combined = pd.concat([preserved, df_out], ignore_index=True)
    else:
        preserved = df_out.iloc[0:0]
        combined = df_out
    combined.to_parquet(OUTPUT_PARQUET, index=False)
    logger.info(f"[FIELD_04] Parquet emitted -> {OUTPUT_PARQUET}")
    logger.info(
        f"[FIELD_04] Rows: {len(df_out)} recomputed, {len(preserved)} preserved "
        f"(non-recomputed segments), {len(combined)} total"
    )

    # Emit audit JSON
    OUTPUT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_path = OUTPUT_AUDIT_DIR / f"FIELD04_E3_REAL_{run_ts}.json"
    audit_out = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "version":           "V1_REAL_PLZ_ALLOCATION_E3",
        "segments_processed": len(audit_records),
        "scope_note":        "REAL_GROUNDED segments only. SYNTHETIC segments excluded by design.",
        "data_honesty_note": (
            "All figures are allocated proxies from PLZ-level aggregate data. "
            "Figures represent statistical probability, not point-confirmed installations. "
            "Score capped at E3_MAX_FIELD_VALUE due to evidence tier constraints."
        ),
        "records": [
            {k: v for k, v in r.items() if k != "_audit"} | r["_audit"]
            for r in audit_records
        ],
    }
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit_out, f, indent=2, ensure_ascii=False)
    logger.info(f"[FIELD_04] Audit JSON emitted -> {audit_path}")

    # Print summary
    logger.info("[FIELD_04] ==============================================")
    logger.info("[FIELD_04] EXECUTION SUMMARY")
    logger.info("[FIELD_04] ==============================================")
    for _, row in df_out.iterrows():
        logger.info(
            f"  {row['segment_id']} | field_value={row['field_value']:.4f} | "
            f"confidence={row['confidence']} | source={row['source']}"
        )
    logger.info("[FIELD_04] ==============================================")

    return df_out


if __name__ == "__main__":
    result = run()
    print("\n" + "=" * 60)
    print("  FIELD_04 REAL OUTPUT")
    print("=" * 60)
    print(result.to_string(index=False))
    print("=" * 60)
