# FIELD_04 Validation Report

**Generated:** 2026-03-22 07:55 UTC  
**Scope:** field_04 V1_REAL_PLZ_ALLOCATION_E3 — NEUSS_NORF_01

| Total | ✅ PASS | ⚠️ REVIEW | ❌ FAIL |
|---|---|---|---|
| 13 | 11 | 2 | 0 |

---

## TC01_REAL_SOURCE_REPLACEMENT

**Purpose:** Confirm source != mock_mastr_signal_v1 and real-data artifacts exist

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\fields\field_04_pv_adoption.parquet`, `D:\Stock Analysis\D-Energy Berater\d-ess-engine\output\field_04\runs\FIELD04_E3_REAL_20260322_082816.json` |
| Expected | source == PLZ_ALLOCATION_E3 AND run JSON exists |
| Actual | sources=['PLZ_ALLOCATION_E3']; run_json=FIELD04_E3_REAL_20260322_082816.json |
| **Verdict** | ✅ PASS |
| Notes | source = PLZ_ALLOCATION_E3. Run JSON confirmed: FIELD04_E3_REAL_20260322_082816.json |

## TC02_REAL_SEGMENT_ONLY

**Purpose:** Only REAL_GROUNDED gets real coverage

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\fields\field_04_pv_adoption.parquet`, `D:\Stock Analysis\D-Energy Berater\d-ess-engine\output\stage6\segment_registry_neuss_v1.json` |
| Expected | Only NEUSS_NORF_01; no SYNTHETIC segments |
| Actual | REAL_GROUNDED present: {'NEUSS_NORF_01'}; SYNTHETIC in parquet: none |
| **Verdict** | ✅ PASS |
| Notes | Synthetic segment IDs checked: ['NEUSS_CENTRAL_01', 'NEUSS_GRIML_01', 'NEUSS_OLD_TOWN_01', 'NEUSS_SUBURB_01'] |

## TC03_STATUS_FILTER

**Purpose:** Confirm only status_id=35 is included in eligible pool

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\derived\mastr\mastr_solar_points_2026-03-12.csv` |
| Expected | Non-active records excluded; active records dominate |
| Actual | Total PLZ: 1259 | Active (35): 1236 (98.2%) | Excluded: 23 ['38', '31', '37'] |
| **Verdict** | ✅ PASS |
| Notes | Excluded statuses: {'38': 12, '31': 10, '37': 1}. Filter correctly isolates active systems. |

## TC04_LARGE_SYSTEM_FILTER

**Purpose:** Confirm kwp > 100 records excluded from eligible pool

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\derived\mastr\mastr_solar_points_2026-03-12.csv` |
| Expected | All records > 100 kWp excluded |
| Actual | Active total: 1236 | Excluded (>100kWp): 5 (0.4%) | Max excluded kWp: 388.8 | Remaining residential eligible: 1231 |
| **Verdict** | ✅ PASS |
| Notes | 5 systems >100kWp excluded (0.4%). Count-based metric unaffected by kWp outliers. |

## TC05_ALLOCATION_TRACE_MATH

**Purpose:** Confirm allocation chain is numerically consistent

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\derived\mastr\mastr_solar_points_2026-03-12.csv`, `PILOT_DEFAULTS (hardcoded constants)` |
| Expected | base_ratio=0.0701 × morph=1.1 = 0.0771; allocated=95; intensity≈31.88% |
| Actual | base_ratio=0.0701 | final_ratio=0.0771 | n_plz=1231 | allocated=95 | kwp_est=693.1 | denominator=298 | intensity=31.88% |
| **Verdict** | ✅ PASS |
| Notes | Math reconstructed matches known V1 run output exactly. |

## TC06_E3_CAP_ENFORCEMENT

**Purpose:** Confirm E3 penalty and hard cap produce field_value <= 0.50

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\fields\field_04_pv_adoption.parquet`, `D:\Stock Analysis\D-Energy Berater\d-ess-engine\output\field_04\runs\FIELD04_E3_REAL_*.json` |
| Expected | All field_value <= 0.5; confidence = 0.45; honesty flags set in audit JSON |
| Actual | max field_value=0.5; max confidence=0.45; cap violations=0; audit honesty flags ok=True |
| **Verdict** | ✅ PASS |
| Notes | field_value max=0.5; confidence max=0.45. Audit JSON honesty flags: point-level=False, street-level=False ✓ |

## TC07_GEOGRAPHY_CLEANLINESS

**Purpose:** Confirm PLZ 41470 pool is geographically clean for MVP proxy use

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\derived\mastr\mastr_solar_points_2026-03-12.csv` |
| Expected | ≥95% of PLZ 41470 records carry city label == 'Neuss' |
| Actual | Total PLZ records: 1259 | Neuss: 1259 (100.0%) | Non-Neuss top values: none |
| **Verdict** | ✅ PASS |
| Notes | Effectively all records (100.0%) are city=Neuss. |

## TC08_DUPLICATE_RISK

**Purpose:** Estimate duplicate ratio via LokationMaStRNummer; classify risk

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\derived\mastr\mastr_solar_points_2026-03-12.csv` |
| Expected | Duplicate ratio < 15% (LOW or MODERATE) |
| Actual | Used records: 1231 | Non-null location_id: 1231 | Unique location_id: 1194 | Apparent duplicates: 37 (3.0%) |
| **Verdict** | ✅ PASS |
| Notes | Duplicate ratio 3.0% — LOW risk. Normal for MaStR (phased expansions). |

## TC09_SCHEMA_COMPATIBILITY

**Purpose:** Confirm field_04 parquet is downstream-compatible

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\fields\field_04_pv_adoption.parquet` |
| Expected | Required columns: ['confidence', 'field_id', 'field_value', 'notes', 'segment_id', 'source']; correct types; field_id='field_04' |
| Actual | Columns: ['confidence', 'field_id', 'field_value', 'notes', 'segment_id', 'source'] | dtypes: {'confidence': 'float64', 'field_id': 'object', 'field_value': 'float64', 'notes': 'object', 'segment_id': 'object', 'source': 'object'} | missing: set() | field_id check: True |
| **Verdict** | ✅ PASS |
| Notes | All required columns present. Types correct. field_id='field_04' ✓. Extra cols (non-breaking): none |

## TC10_WEAK_MODIFIER_GUARDRAIL

**Purpose:** Confirm field_04 is configured as weak secondary modifier, not core driver

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\fields\field_04_pv_adoption.parquet`, `D:\Stock Analysis\D-Energy Berater\d-ess-engine\fields\field_04_pv_adoption.py`, `D:\Stock Analysis\D-Energy Berater\d-ess-engine\output\field_04\runs\FIELD04_E3_REAL_*.json` |
| Expected | confidence ≤ 0.50; source has honesty label; audit flags block high-precision use; source code has weak-modifier language |
| Actual | Checks: {'confidence <= 0.50': np.True_, 'source contains honesty label': True, 'segment_ranking_allowed (expected True)': False, 'point_level_blocked (expected True)': True, 'street_level_blocked (expected True)': True, 'source code contains weak/modifier language': True} |
| **Verdict** | ⚠️ REVIEW |
| Notes | Issues: ['segment-level ranking incorrectly blocked in audit JSON'] |

## EDGE01_LOW_SUPPORT_PLZ

**Purpose:** Verify field_04 handles low-support PLZ (< MIN_PLZ_RECORDS) gracefully

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\fields\field_04_pv_adoption.py` |
| Expected | MIN_PLZ_RECORDS constant present; guard branch exists |
| Actual | MIN_PLZ_RECORDS constant: True; guard branch: True |
| **Verdict** | ✅ PASS |
| Notes | MIN_PLZ_RECORDS constant and guard branch confirmed in source. |

## EDGE02_DIRTY_MULTI_CITY_PLZ

**Purpose:** Confirm PLZ 41470 is not a multi-city PLZ polluting the adoption signal

| Attribute | Value |
|---|---|
| Files used | `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\derived\mastr\mastr_solar_points_2026-03-12.csv` |
| Expected | Single city or ≥95% dominant city in PLZ 41470 pool |
| Actual | Distinct cities: 1 | Top: neuss (100.0%) | City distribution: {'neuss': 1259} |
| **Verdict** | ✅ PASS |
| Notes | PLZ 41470 is a single-city PLZ (100% Neuss). No multi-city contamination. |

## EDGE03_DENOMINATOR_SENSITIVITY

**Purpose:** Check if field_value changes materially across PLZ building denominator assumptions

| Attribute | Value |
|---|---|
| Files used | `PILOT_DEFAULTS: plz_buildings=4250 (estimate)` |
| Expected | field_value == 0.50 (capped) regardless of plz_buildings estimate |
| Actual | Scenarios tested:
  plz_buildings=3000 (optimistic): allocated=135, intensity=45.3%, field_value=0.5000 (capped)
  plz_buildings=4250 (baseline): allocated=95, intensity=31.9%, field_value=0.5000 (capped)
  plz_buildings=6000 (pessimistic): allocated=67, intensity=22.5%, field_value=0.5000 (capped)
  plz_buildings=8000 (extreme): allocated=50, intensity=16.8%, field_value=0.4195 (not capped) |
| **Verdict** | ⚠️ REVIEW |
| Notes | Some denominator scenarios produce uncapped scores — denominator accuracy matters. |

---

## Final Summary

### Overall Recommendation

```
SAFE_TO_KEEP_IN_LAYER2
```

**Overall verdict:** **✅ SAFE_TO_KEEP_IN_LAYER2**

### ❌ Blocking Failures

None.

### ⚠️ Non-Blocking Review Items

- **TC10_WEAK_MODIFIER_GUARDRAIL**: Issues: ['segment-level ranking incorrectly blocked in audit JSON']
- **EDGE03_DENOMINATOR_SENSITIVITY**: Some denominator scenarios produce uncapped scores — denominator accuracy matters.

### Decision Rationale

- PASS: 11/13 tests  
- REVIEW: 2/13 (non-blocking)  
- FAIL: 0/13 (blocking)  

> field_04 V1 signal is constrained by E3 honesty tier (confidence=0.45, field_value ≤ 0.50). It operates as a weak secondary modifier only. The E3 cap design ensures that even if upstream data is imprecise, no downstream ranking component is overclaimed.
