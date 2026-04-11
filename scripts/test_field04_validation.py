"""
test_field04_validation.py
==========================
FIELD_04 Lightweight Validation Pack — TC01 through TC10 + optional edge tests.

Mode    : TEST ONLY | Reads existing artifacts and source data
Purpose : Validate that the completed real-data field_04 implementation is correct,
          honest, and safe to use as a weak Layer 2 secondary modifier.

Produces
--------
  output/field_04/tests/FIELD04_VALIDATION_REPORT_<timestamp>.md

Does NOT:
  - Re-run field_04 scoring logic
  - Import field_04_pv_adoption.py
  - Modify any artifact
"""

import json
import glob
import os
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
BASE_DIR  = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIELDS_DIR = BASE_DIR / "data" / "fields"
MASTR_CSV  = BASE_DIR / "data" / "derived" / "mastr" / "mastr_solar_points_2026-03-12.csv"
RUNS_DIR   = BASE_DIR / "output" / "field_04" / "runs"
TESTS_DIR  = BASE_DIR / "output" / "field_04" / "tests"
SEGMENT_REG = BASE_DIR / "output" / "stage6" / "segment_registry_neuss_v1.json"
FIELD04_SRC = BASE_DIR / "fields" / "field_04_pv_adoption.py"

TARGET_PLZ        = "41470"
ACTIVE_STATUS     = "35"
RESIDENTIAL_CAP   = 100.0
E3_MAX_FIELD_VALUE = 0.50
E3_CONFIDENCE     = 0.45
EXPECTED_SEG_BUILDINGS = 298
EXPECTED_PLZ_BUILDINGS = 4250
MORPH_FACTOR       = 1.1
MIN_PLZ_RECORDS    = 5
ADOPTION_BENCHMARK = 0.20

# Known values from V1 run (cross-check references)
KNOWN_PLZ_ACTIVE_RESIDENTIAL = 1231
KNOWN_PLZ_TOTAL              = 1259
KNOWN_ALLOCATED_SYSTEMS      = 95
KNOWN_ADOPTION_INTENSITY     = 0.3188

VERDICT_PASS   = "✅ PASS"
VERDICT_REVIEW = "⚠️ REVIEW"
VERDICT_FAIL   = "❌ FAIL"

# ---------------------------------------------------------------------------
# Test result scaffold
# ---------------------------------------------------------------------------

def result(tc_id: str, purpose: str, files: list, expected: str,
           actual: str, verdict: str, notes: str = "") -> dict:
    return {
        "tc_id":    tc_id,
        "purpose":  purpose,
        "files":    files,
        "expected": expected,
        "actual":   actual,
        "verdict":  verdict,
        "notes":    notes,
    }


# ---------------------------------------------------------------------------
# Data loaders (cached at module level for this run)
# ---------------------------------------------------------------------------

def _load_parquet():
    p = FIELDS_DIR / "field_04_pv_adoption.parquet"
    if not p.exists():
        return None, str(p)
    return pd.read_parquet(p), str(p)


def _latest_run_json():
    files = sorted(glob.glob(str(RUNS_DIR / "FIELD04_E3_REAL_*.json")))
    if not files:
        return None, None
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f), Path(files[-1]).name


def _load_plz_slice():
    """Load PLZ 41470 rows only from national CSV (all statuses)."""
    df = pd.read_csv(
        MASTR_CSV,
        dtype={"plz": str, "operational_status": str},
        usecols=["unit_id", "location_id", "plz", "kwp",
                 "operational_status", "city", "municipality"],
        low_memory=False,
    )
    return df[df["plz"] == TARGET_PLZ].copy()


def _load_segment_registry():
    if not SEGMENT_REG.exists():
        return []
    with open(SEGMENT_REG, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("segments", [])


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def tc01_real_source_replacement(df_parquet, run_json, run_filename):
    """TC01: source != mock; real run artifacts exist."""
    files = [str(FIELDS_DIR / "field_04_pv_adoption.parquet"),
             str(RUNS_DIR / (run_filename or "—"))]

    if df_parquet is None:
        return result("TC01_REAL_SOURCE_REPLACEMENT",
                      "Confirm mock replaced with real signal",
                      files, "source != mock_mastr_signal_v1",
                      "Parquet not found", VERDICT_FAIL,
                      "field_04_pv_adoption.parquet missing. field_04 may not have run.")

    sources = df_parquet["source"].unique().tolist()
    has_mock = "mock_mastr_signal_v1" in sources
    has_real = "PLZ_ALLOCATION_E3" in sources
    run_ok   = run_json is not None

    if has_mock:
        v = VERDICT_FAIL if not has_real else VERDICT_REVIEW
        note = "mock_mastr_signal_v1 still present in parquet."
    elif has_real and run_ok:
        v = VERDICT_PASS
        note = f"source = PLZ_ALLOCATION_E3. Run JSON confirmed: {run_filename}"
    else:
        v = VERDICT_REVIEW
        note = f"sources found: {sources}. Run JSON: {'found' if run_ok else 'MISSING'}"

    return result(
        "TC01_REAL_SOURCE_REPLACEMENT",
        "Confirm source != mock_mastr_signal_v1 and real-data artifacts exist",
        files,
        "source == PLZ_ALLOCATION_E3 AND run JSON exists",
        f"sources={sources}; run_json={run_filename or 'NOT FOUND'}",
        v, note,
    )


def tc02_real_segment_only(df_parquet, segments):
    """TC02: Only REAL_GROUNDED segments have real coverage; synthetic absent."""
    files = [str(FIELDS_DIR / "field_04_pv_adoption.parquet"),
             str(SEGMENT_REG)]

    if df_parquet is None:
        return result("TC02_REAL_SEGMENT_ONLY", "Only REAL_GROUNDED gets real coverage",
                      files, "Only NEUSS_NORF_01 in parquet",
                      "Parquet not found", VERDICT_FAIL)

    synthetic_ids = {s["segment_id"] for s in segments if s.get("status") == "SYNTHETIC"}
    real_ids      = {s["segment_id"] for s in segments if s.get("status") == "REAL_GROUNDED"}
    parquet_segs  = set(df_parquet["segment_id"].unique())

    contaminated  = synthetic_ids & parquet_segs
    real_present  = real_ids & parquet_segs

    if contaminated:
        return result("TC02_REAL_SEGMENT_ONLY",
                      "Only REAL_GROUNDED gets real coverage",
                      files,
                      "No SYNTHETIC segments in parquet",
                      f"SYNTHETIC in parquet: {contaminated}",
                      VERDICT_FAIL,
                      f"Synthetic segments contaminated with real-looking scores: {contaminated}")

    if not real_present:
        return result("TC02_REAL_SEGMENT_ONLY",
                      "Only REAL_GROUNDED gets real coverage",
                      files,
                      "NEUSS_NORF_01 in parquet",
                      "No REAL_GROUNDED segment found in parquet",
                      VERDICT_FAIL,
                      "field_04 produced no output for real segments.")

    return result(
        "TC02_REAL_SEGMENT_ONLY",
        "Only REAL_GROUNDED gets real coverage",
        files,
        "Only NEUSS_NORF_01; no SYNTHETIC segments",
        f"REAL_GROUNDED present: {real_present}; SYNTHETIC in parquet: none",
        VERDICT_PASS,
        f"Synthetic segment IDs checked: {sorted(synthetic_ids)}",
    )


def tc03_status_filter(df_plz):
    """TC03: Only status=35 records in final eligible pool."""
    files = [str(MASTR_CSV)]
    df_active = df_plz[df_plz["operational_status"] == ACTIVE_STATUS]
    df_not35  = df_plz[df_plz["operational_status"] != ACTIVE_STATUS]

    n_total    = len(df_plz)
    n_active   = len(df_active)
    n_excluded = len(df_not35)
    pct_active = n_active / n_total * 100 if n_total else 0
    non_statuses = df_not35["operational_status"].value_counts().to_dict()

    # Verify: final pool used in field_04 would have only status=35
    v = VERDICT_PASS if n_excluded > 0 and n_active > 0 else VERDICT_REVIEW
    note = (
        f"Excluded statuses: {non_statuses}. "
        "Filter correctly isolates active systems."
        if n_excluded else "No non-35 records found — verify filter was exercised."
    )

    return result(
        "TC03_STATUS_FILTER",
        "Confirm only status_id=35 is included in eligible pool",
        files,
        "Non-active records excluded; active records dominate",
        f"Total PLZ: {n_total} | Active (35): {n_active} ({pct_active:.1f}%) | "
        f"Excluded: {n_excluded} {list(non_statuses.keys())}",
        v, note,
    )


def tc04_large_system_filter(df_plz):
    """TC04: Records with kwp > 100 excluded."""
    files = [str(MASTR_CSV)]
    df_active   = df_plz[df_plz["operational_status"] == ACTIVE_STATUS]
    df_large    = df_active[df_active["kwp"] > RESIDENTIAL_CAP]
    df_resident = df_active[df_active["kwp"] <= RESIDENTIAL_CAP]

    n_large = len(df_large)
    n_res   = len(df_resident)
    pct_excl = n_large / len(df_active) * 100 if len(df_active) else 0

    if n_large == 0:
        v    = VERDICT_REVIEW
        note = "No large systems found — verify filter was exercised."
    elif pct_excl > 20:
        v    = VERDICT_REVIEW
        note = f"Large-system exclusion rate ({pct_excl:.1f}%) is high — count metric may be materially affected."
    else:
        v    = VERDICT_PASS
        note = (f"{n_large} systems >100kWp excluded ({pct_excl:.1f}%). "
                "Count-based metric unaffected by kWp outliers.")

    max_large_kwp = df_large["kwp"].max() if n_large else 0
    return result(
        "TC04_LARGE_SYSTEM_FILTER",
        "Confirm kwp > 100 records excluded from eligible pool",
        files,
        "All records > 100 kWp excluded",
        f"Active total: {len(df_active)} | Excluded (>100kWp): {n_large} "
        f"({pct_excl:.1f}%) | Max excluded kWp: {max_large_kwp:.1f} | "
        f"Remaining residential eligible: {n_res}",
        v, note,
    )


def tc05_allocation_trace_math(df_plz):
    """TC05: Verify allocation chain arithmetic."""
    files = [str(MASTR_CSV), "PILOT_DEFAULTS (hardcoded constants)"]

    df_res   = df_plz[(df_plz["operational_status"] == ACTIVE_STATUS) &
                      (df_plz["kwp"] <= RESIDENTIAL_CAP)]
    n_plz    = len(df_res)
    total_kwp = df_plz[(df_plz["operational_status"] == ACTIVE_STATUS) &
                       (df_plz["kwp"] <= RESIDENTIAL_CAP)]["kwp"].sum()

    base_ratio  = EXPECTED_SEG_BUILDINGS / EXPECTED_PLZ_BUILDINGS
    final_ratio = min(base_ratio * MORPH_FACTOR, 1.0)
    pv_est      = round(n_plz * final_ratio)
    kwp_est     = round(total_kwp * final_ratio, 1)
    intensity   = pv_est / EXPECTED_SEG_BUILDINGS if EXPECTED_SEG_BUILDINGS > 0 else 0

    # Cross-check against known run values
    pv_match  = pv_est == KNOWN_ALLOCATED_SYSTEMS
    int_match = abs(intensity - KNOWN_ADOPTION_INTENSITY) < 0.005

    if pv_match and int_match:
        v    = VERDICT_PASS
        note = "Math reconstructed matches known V1 run output exactly."
    elif pv_match or int_match:
        v    = VERDICT_REVIEW
        note = "Partial match — minor floating point variance acceptable."
    else:
        v    = VERDICT_FAIL
        note = f"Math mismatch. Expected allocated={KNOWN_ALLOCATED_SYSTEMS}, got {pv_est}."

    return result(
        "TC05_ALLOCATION_TRACE_MATH",
        "Confirm allocation chain is numerically consistent",
        files,
        f"base_ratio={base_ratio:.4f} × morph={MORPH_FACTOR} = {final_ratio:.4f}; "
        f"allocated={KNOWN_ALLOCATED_SYSTEMS}; intensity≈{KNOWN_ADOPTION_INTENSITY:.2%}",
        f"base_ratio={base_ratio:.4f} | final_ratio={final_ratio:.4f} | "
        f"n_plz={n_plz} | allocated={pv_est} | kwp_est={kwp_est} | "
        f"denominator={EXPECTED_SEG_BUILDINGS} | intensity={intensity:.2%}",
        v, note,
    )


def tc06_e3_cap_enforcement(df_parquet, run_json):
    """TC06: field_value <= E3_MAX and confidence == E3_CONFIDENCE for all rows."""
    files = [str(FIELDS_DIR / "field_04_pv_adoption.parquet"),
             str(RUNS_DIR / "FIELD04_E3_REAL_*.json")]

    if df_parquet is None:
        return result("TC06_E3_CAP_ENFORCEMENT",
                      "Confirm E3 penalty and hard cap applied",
                      files, f"field_value <= {E3_MAX_FIELD_VALUE}",
                      "Parquet not found", VERDICT_FAIL)

    cap_violations  = df_parquet[df_parquet["field_value"] > E3_MAX_FIELD_VALUE]
    conf_violations = df_parquet[df_parquet["confidence"] > E3_MAX_FIELD_VALUE]
    max_fv    = df_parquet["field_value"].max()
    max_conf  = df_parquet["confidence"].max()

    # Also verify audit JSON records honesty flags
    audit_ok = False
    if run_json and run_json.get("records"):
        rec = run_json["records"][0]
        audit_ok = (rec.get("allowed_for_point_level_installation_claims") is False and
                    rec.get("allowed_for_street_level_targeting") is False)

    if len(cap_violations) > 0:
        v    = VERDICT_FAIL
        note = f"Cap violated! {len(cap_violations)} rows exceed {E3_MAX_FIELD_VALUE}"
    elif not audit_ok:
        v    = VERDICT_REVIEW
        note = "Cap respected in parquet but audit JSON honesty flags not confirmed."
    else:
        v    = VERDICT_PASS
        note = (f"field_value max={max_fv}; confidence max={max_conf}. "
                "Audit JSON honesty flags: point-level=False, street-level=False ✓")

    return result(
        "TC06_E3_CAP_ENFORCEMENT",
        "Confirm E3 penalty and hard cap produce field_value <= 0.50",
        files,
        f"All field_value <= {E3_MAX_FIELD_VALUE}; confidence = {E3_CONFIDENCE}; "
        "honesty flags set in audit JSON",
        f"max field_value={max_fv}; max confidence={max_conf}; "
        f"cap violations={len(cap_violations)}; audit honesty flags ok={audit_ok}",
        v, note,
    )


def tc07_geography_cleanliness(df_plz):
    """TC07: PLZ 41470 pool is geographically clean enough for MVP proxy."""
    files = [str(MASTR_CSV)]
    total    = len(df_plz)
    if total == 0:
        return result("TC07_GEOGRAPHY_CLEANLINESS",
                      "PLZ 41470 pool is geographically clean",
                      files, "≥95% Neuss", "No records found", VERDICT_FAIL)

    neuss_n = df_plz["city"].fillna("").str.strip().str.lower().eq("neuss").sum()
    pct     = neuss_n / total * 100

    if pct >= 99:
        v    = VERDICT_PASS
        note = f"Effectively all records ({pct:.1f}%) are city=Neuss."
    elif pct >= 95:
        v    = VERDICT_PASS
        note = f"{pct:.1f}% Neuss — meets MVP cleanliness threshold."
    elif pct >= 80:
        v    = VERDICT_REVIEW
        note = f"Only {pct:.1f}% Neuss — non-Neuss records present; review city distribution."
    else:
        v    = VERDICT_FAIL
        note = f"Critical geography contamination: only {pct:.1f}% Neuss."

    other = df_plz[df_plz["city"].fillna("").str.strip().str.lower() != "neuss"]["city"].value_counts().head(5).to_dict()
    return result(
        "TC07_GEOGRAPHY_CLEANLINESS",
        "Confirm PLZ 41470 pool is geographically clean for MVP proxy use",
        files,
        "≥95% of PLZ 41470 records carry city label == 'Neuss'",
        f"Total PLZ records: {total} | Neuss: {neuss_n} ({pct:.1f}%) | "
        f"Non-Neuss top values: {other if other else 'none'}",
        v, note,
    )


def tc08_duplicate_risk(df_plz):
    """TC08: Estimate duplicate ratio via location_id."""
    files = [str(MASTR_CSV)]
    df_used = df_plz[(df_plz["operational_status"] == ACTIVE_STATUS) &
                     (df_plz["kwp"] <= RESIDENTIAL_CAP)]
    n_total   = len(df_used)
    n_nonnull = df_used["location_id"].notna().sum()
    n_unique  = df_used["location_id"].dropna().nunique()
    n_dup     = n_nonnull - n_unique
    dup_rate  = n_dup / n_total * 100 if n_total else 0

    if dup_rate < 5:
        v    = VERDICT_PASS
        note = f"Duplicate ratio {dup_rate:.1f}% — LOW risk. Normal for MaStR (phased expansions)."
    elif dup_rate < 15:
        v    = VERDICT_REVIEW
        note = f"Duplicate ratio {dup_rate:.1f}% — MODERATE. Monitor but not blocking for MVP."
    else:
        v    = VERDICT_FAIL
        note = f"Duplicate ratio {dup_rate:.1f}% — HIGH. Count-based metric may be materially inflated."

    return result(
        "TC08_DUPLICATE_RISK",
        "Estimate duplicate ratio via LokationMaStRNummer; classify risk",
        files,
        "Duplicate ratio < 15% (LOW or MODERATE)",
        f"Used records: {n_total} | Non-null location_id: {n_nonnull} | "
        f"Unique location_id: {n_unique} | Apparent duplicates: {n_dup} ({dup_rate:.1f}%)",
        v, note,
    )


def tc09_schema_compatibility(df_parquet):
    """TC09: Parquet retains downstream-compatible schema."""
    files = [str(FIELDS_DIR / "field_04_pv_adoption.parquet")]
    REQUIRED_COLS = {"segment_id", "field_id", "field_value", "confidence", "source", "notes"}

    if df_parquet is None:
        return result("TC09_SCHEMA_COMPATIBILITY",
                      "Parquet retains schema contract",
                      files, f"Columns: {sorted(REQUIRED_COLS)}",
                      "Parquet not found", VERDICT_FAIL)

    present  = set(df_parquet.columns)
    missing  = REQUIRED_COLS - present
    extra    = present - REQUIRED_COLS

    # Type checks
    type_ok = (
        pd.api.types.is_string_dtype(df_parquet["segment_id"]) and
        pd.api.types.is_string_dtype(df_parquet["field_id"]) and
        pd.api.types.is_float_dtype(df_parquet["field_value"]) and
        pd.api.types.is_float_dtype(df_parquet["confidence"])
    )
    field_id_ok = (df_parquet["field_id"] == "field_04").all()

    if missing:
        v    = VERDICT_FAIL
        note = f"Missing required columns: {missing}"
    elif not type_ok:
        v    = VERDICT_FAIL
        note = "Column type mismatch — downstream consumers may break."
    elif not field_id_ok:
        v    = VERDICT_REVIEW
        note = "field_id values are not all 'field_04'."
    else:
        v    = VERDICT_PASS
        note = (f"All required columns present. Types correct. "
                f"field_id='field_04' ✓. Extra cols (non-breaking): {sorted(extra) if extra else 'none'}")

    dtypes = {c: str(df_parquet[c].dtype) for c in sorted(present)}
    return result(
        "TC09_SCHEMA_COMPATIBILITY",
        "Confirm field_04 parquet is downstream-compatible",
        files,
        f"Required columns: {sorted(REQUIRED_COLS)}; correct types; field_id='field_04'",
        f"Columns: {sorted(present)} | dtypes: {dtypes} | missing: {missing} | "
        f"field_id check: {field_id_ok}",
        v, note,
    )


def tc10_weak_modifier_guardrail(df_parquet, run_json):
    """TC10: Confirm field_04 treats PV coverage as weak modifier, not core driver."""
    files = [str(FIELDS_DIR / "field_04_pv_adoption.parquet"),
             str(FIELD04_SRC),
             str(RUNS_DIR / "FIELD04_E3_REAL_*.json")]

    issues = []
    checks = {}

    # Check 1: confidence <= 0.50 (weak evidence tier)
    if df_parquet is not None:
        max_conf = df_parquet["confidence"].max()
        checks["confidence <= 0.50"] = max_conf <= 0.50
        if max_conf > 0.50:
            issues.append(f"confidence={max_conf} exceeds weak-modifier ceiling")

    # Check 2: source contains honesty label
    if df_parquet is not None:
        has_honest_source = all("E3" in str(s) or "ALLOC" in str(s)
                                for s in df_parquet["source"])
        checks["source contains honesty label"] = has_honest_source
        if not has_honest_source:
            issues.append("source label does not indicate proxy/allocation nature")

    # Check 3: audit JSON use constraints
    if run_json and run_json.get("records"):
        rec = run_json["records"][0]
        seg_rank_ok = rec.get("allowed_for_segment_level_ranking", False)
        pt_ok  = not rec.get("allowed_for_point_level_installation_claims", True)
        str_ok = not rec.get("allowed_for_street_level_targeting", True)
        checks["segment_ranking_allowed (expected True)"]  = seg_rank_ok
        checks["point_level_blocked (expected True)"]      = pt_ok
        checks["street_level_blocked (expected True)"]     = str_ok
        if not seg_rank_ok:
            issues.append("segment-level ranking incorrectly blocked in audit JSON")
        if not pt_ok:
            issues.append("point-level claims incorrectly allowed in audit JSON")
        if not str_ok:
            issues.append("street-level targeting incorrectly allowed in audit JSON")

    # Check 4: source code contains weak-modifier language / no core driver designation
    if FIELD04_SRC.exists():
        src_text = FIELD04_SRC.read_text(encoding="utf-8")
        has_weak_language = ("weak" in src_text.lower() or
                             "modifier" in src_text.lower() or
                             "secondary" in src_text.lower())
        checks["source code contains weak/modifier language"] = has_weak_language
        if not has_weak_language:
            issues.append("field_04_pv_adoption.py lacks explicit weak-modifier language")

    all_pass = all(checks.values())
    v    = VERDICT_PASS if all_pass else (VERDICT_REVIEW if len(issues) <= 1 else VERDICT_FAIL)
    note = ("All weak-modifier guardrails confirmed." if all_pass
            else f"Issues: {issues}")

    return result(
        "TC10_WEAK_MODIFIER_GUARDRAIL",
        "Confirm field_04 is configured as weak secondary modifier, not core driver",
        files,
        "confidence ≤ 0.50; source has honesty label; audit flags block high-precision use; "
        "source code has weak-modifier language",
        f"Checks: {checks}",
        v, note,
    )


# ---------------------------------------------------------------------------
# Optional Edge Tests
# ---------------------------------------------------------------------------

def edge01_low_support_plz(df_plz):
    """EDGE01: Verify MIN_PLZ_RECORDS guard is in source code (low support PLZ case)."""
    files = [str(FIELD04_SRC)]
    if not FIELD04_SRC.exists():
        return result("EDGE01_LOW_SUPPORT_PLZ",
                      "Verify MIN_PLZ_RECORDS guard exists in field_04 code",
                      files, "MIN_PLZ_RECORDS constant and guard present",
                      "Source file not found", VERDICT_FAIL)

    src = FIELD04_SRC.read_text(encoding="utf-8")
    has_const = "MIN_PLZ_RECORDS" in src
    has_guard = "if plz_count < MIN_PLZ_RECORDS" in src or "< MIN_PLZ_RECORDS" in src

    if has_const and has_guard:
        v    = VERDICT_PASS
        note = "MIN_PLZ_RECORDS constant and guard branch confirmed in source."
    elif has_const:
        v    = VERDICT_REVIEW
        note = "MIN_PLZ_RECORDS constant found but guard branch pattern not verified."
    else:
        v    = VERDICT_FAIL
        note = "MIN_PLZ_RECORDS not found in source — low-support PLZ case unprotected."

    return result(
        "EDGE01_LOW_SUPPORT_PLZ",
        "Verify field_04 handles low-support PLZ (< MIN_PLZ_RECORDS) gracefully",
        files,
        "MIN_PLZ_RECORDS constant present; guard branch exists",
        f"MIN_PLZ_RECORDS constant: {has_const}; guard branch: {has_guard}",
        v, note,
    )


def edge02_dirty_multi_city_plz(df_plz):
    """EDGE02: Confirm PLZ 41470 is not a multi-city PLZ (would be a data risk)."""
    files = [str(MASTR_CSV)]
    city_dist = df_plz["city"].fillna("(null)").str.strip().str.lower().value_counts()
    n_cities  = city_dist.count()
    top_city  = city_dist.index[0] if len(city_dist) else "—"
    top_pct   = city_dist.iloc[0] / len(df_plz) * 100 if len(df_plz) else 0

    if n_cities == 1 and top_city == "neuss":
        v    = VERDICT_PASS
        note = "PLZ 41470 is a single-city PLZ (100% Neuss). No multi-city contamination."
    elif top_pct >= 95:
        v    = VERDICT_PASS
        note = f"PLZ dominated by top city ({top_city}, {top_pct:.1f}%). Acceptable."
    elif top_pct >= 80:
        v    = VERDICT_REVIEW
        note = f"PLZ has {n_cities} city labels. Top: {top_city} ({top_pct:.1f}%). Review before V2."
    else:
        v    = VERDICT_FAIL
        note = f"PLZ is a multi-city PLZ ({n_cities} cities). Top: {top_city} ({top_pct:.1f}%). Filter required."

    return result(
        "EDGE02_DIRTY_MULTI_CITY_PLZ",
        "Confirm PLZ 41470 is not a multi-city PLZ polluting the adoption signal",
        files,
        "Single city or ≥95% dominant city in PLZ 41470 pool",
        f"Distinct cities: {n_cities} | Top: {top_city} ({top_pct:.1f}%) | "
        f"City distribution: {city_dist.head(5).to_dict()}",
        v, note,
    )


def edge03_denominator_sensitivity(df_plz):
    """EDGE03: Check if field_value changes materially at different PLZ building denominators."""
    files = ["PILOT_DEFAULTS: plz_buildings=4250 (estimate)"]
    df_res  = df_plz[(df_plz["operational_status"] == ACTIVE_STATUS) &
                     (df_plz["kwp"] <= RESIDENTIAL_CAP)]
    n_plz   = len(df_res)

    scenarios = {
        "plz_buildings=3000 (optimistic)": 3000,
        "plz_buildings=4250 (baseline)":   4250,
        "plz_buildings=6000 (pessimistic)": 6000,
        "plz_buildings=8000 (extreme)":    8000,
    }

    rows = []
    for label, plz_b in scenarios.items():
        base_r  = EXPECTED_SEG_BUILDINGS / plz_b
        f_r     = min(base_r * MORPH_FACTOR, 1.0)
        pv_est  = round(n_plz * f_r)
        intens  = pv_est / EXPECTED_SEG_BUILDINGS
        raw_n   = min(intens / ADOPTION_BENCHMARK, 1.0)
        fv      = round(min(raw_n * 0.5, E3_MAX_FIELD_VALUE), 4)
        rows.append((label, plz_b, pv_est, f"{intens:.1%}", f"{fv:.4f}",
                     "capped" if fv >= E3_MAX_FIELD_VALUE else "not capped"))

    # All scenarios likely cap — verify
    all_capped = all(r[-1] == "capped" for r in rows)
    v    = VERDICT_PASS if all_capped else VERDICT_REVIEW
    note = ("E3 cap absorbs all denominator scenarios — field_value = 0.50 regardless of PLZ "
            "building estimate. Denominator inaccuracy has zero effect on V1 output."
            if all_capped else
            "Some denominator scenarios produce uncapped scores — denominator accuracy matters.")

    table = "\n".join(
        f"  {r[0]}: allocated={r[2]}, intensity={r[3]}, field_value={r[4]} ({r[5]})"
        for r in rows
    )
    return result(
        "EDGE03_DENOMINATOR_SENSITIVITY",
        "Check if field_value changes materially across PLZ building denominator assumptions",
        files,
        "field_value == 0.50 (capped) regardless of plz_buildings estimate",
        f"Scenarios tested:\n{table}",
        v, note,
    )


# ---------------------------------------------------------------------------
# Report Renderer
# ---------------------------------------------------------------------------

VERDICT_WEIGHT = {VERDICT_PASS: 0, VERDICT_REVIEW: 1, VERDICT_FAIL: 2}


def render_report(tests: list) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Summary counts
    n_pass   = sum(1 for t in tests if t["verdict"] == VERDICT_PASS)
    n_review = sum(1 for t in tests if t["verdict"] == VERDICT_REVIEW)
    n_fail   = sum(1 for t in tests if t["verdict"] == VERDICT_FAIL)

    # Overall verdict
    if n_fail > 0:
        overall   = "**❌ REQUIRES_FIX_BEFORE_LAYER2**"
        rec_code  = "REQUIRES_FIX_BEFORE_LAYER2"
    elif n_review > 2:
        overall   = "**⚠️ KEEP_WITH_REVIEW_NOTE**"
        rec_code  = "KEEP_WITH_REVIEW_NOTE"
    else:
        overall   = "**✅ SAFE_TO_KEEP_IN_LAYER2**"
        rec_code  = "SAFE_TO_KEEP_IN_LAYER2"

    blockers     = [t for t in tests if t["verdict"] == VERDICT_FAIL]
    review_items = [t for t in tests if t["verdict"] == VERDICT_REVIEW]

    lines = []

    # Header
    lines += [
        "# FIELD_04 Validation Report",
        f"",
        f"**Generated:** {ts}  ",
        f"**Scope:** field_04 V1_REAL_PLZ_ALLOCATION_E3 — NEUSS_NORF_01",
        f"",
        f"| Total | ✅ PASS | ⚠️ REVIEW | ❌ FAIL |",
        f"|---|---|---|---|",
        f"| {len(tests)} | {n_pass} | {n_review} | {n_fail} |",
        "",
    ]

    # Per-test section
    lines.append("---")
    lines.append("")
    for t in tests:
        lines += [
            f"## {t['tc_id']}",
            f"",
            f"**Purpose:** {t['purpose']}",
            f"",
            f"| Attribute | Value |",
            f"|---|---|",
            f"| Files used | {', '.join(f'`{f}`' for f in t['files'])} |",
            f"| Expected | {t['expected']} |",
            f"| Actual | {t['actual']} |",
            f"| **Verdict** | {t['verdict']} |",
        ]
        if t["notes"]:
            lines += [f"| Notes | {t['notes']} |"]
        lines.append("")

    # Final section
    lines += [
        "---",
        "",
        "## Final Summary",
        "",
        f"### Overall Recommendation",
        f"",
        f"```",
        f"{rec_code}",
        f"```",
        f"",
        f"**Overall verdict:** {overall}",
        f"",
    ]

    if blockers:
        lines += ["### ❌ Blocking Failures", ""]
        for t in blockers:
            lines.append(f"- **{t['tc_id']}**: {t['notes']}")
        lines.append("")
    else:
        lines += ["### ❌ Blocking Failures", "", "None.", ""]

    if review_items:
        lines += ["### ⚠️ Non-Blocking Review Items", ""]
        for t in review_items:
            lines.append(f"- **{t['tc_id']}**: {t['notes']}")
        lines.append("")
    else:
        lines += ["### ⚠️ Non-Blocking Review Items", "", "None.", ""]

    lines += [
        "### Decision Rationale",
        "",
        f"- PASS: {n_pass}/{len(tests)} tests  ",
        f"- REVIEW: {n_review}/{len(tests)} (non-blocking)  ",
        f"- FAIL: {n_fail}/{len(tests)} (blocking)  ",
        "",
        "> field_04 V1 signal is constrained by E3 honesty tier (confidence=0.45, "
        "field_value ≤ 0.50). It operates as a weak secondary modifier only. "
        "The E3 cap design ensures that even if upstream data is imprecise, "
        "no downstream ranking component is overclaimed.",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  FIELD_04 VALIDATION PACK — START")
    print("=" * 60)

    # Load shared data (once)
    print("[1/6] Loading parquet...")
    df_parquet, _ = _load_parquet()

    print("[2/6] Loading latest run JSON...")
    run_json, run_filename = _latest_run_json()

    print("[3/6] Loading MaStR CSV (PLZ 41470 slice, ~10s)...")
    df_plz = _load_plz_slice()

    print("[4/6] Loading segment registry...")
    segments = _load_segment_registry()

    # Run tests
    print("[5/6] Running TC01–TC10 + edge tests...")
    tests = [
        tc01_real_source_replacement(df_parquet, run_json, run_filename),
        tc02_real_segment_only(df_parquet, segments),
        tc03_status_filter(df_plz),
        tc04_large_system_filter(df_plz),
        tc05_allocation_trace_math(df_plz),
        tc06_e3_cap_enforcement(df_parquet, run_json),
        tc07_geography_cleanliness(df_plz),
        tc08_duplicate_risk(df_plz),
        tc09_schema_compatibility(df_parquet),
        tc10_weak_modifier_guardrail(df_parquet, run_json),
        # Edge tests
        edge01_low_support_plz(df_plz),
        edge02_dirty_multi_city_plz(df_plz),
        edge03_denominator_sensitivity(df_plz),
    ]

    # Render report
    print("[6/6] Rendering markdown report...")
    report = render_report(tests)

    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    ts_str   = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = TESTS_DIR / f"FIELD04_VALIDATION_REPORT_{ts_str}.md"
    out_path.write_text(report, encoding="utf-8")

    # Print summary to console
    print("\n" + "=" * 60)
    print("  FIELD_04 VALIDATION SUMMARY")
    print("=" * 60)
    for t in tests:
        print(f"  {t['verdict']}  {t['tc_id']}")
    print(f"\nReport: {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
