# FIELD_04 Status Memo — Norf Pilot

## Overview
Field 04 (PV Adoption Signal) has completed all pipeline, schema, and audit-honesty stages for the Norf pilot segment `NEUSS_NORF_01`.

The field now produces a proxy-grade PV adoption signal derived from MaStR registry data, with full ingestion traceability and contamination controls.

However, the field cannot yet be upgraded to segment-exact truth due to the absence of a traceable polygon geometry for the target segment.

The current status is therefore:
**PROXY COMPLETE — GEOMETRY BLOCKED**

---

## Deliverables Implemented

### Logic & Schema Contracts
- **field_04_schema.json**: Seven-layer deterministic audit schema.
- **field_04_protocol_v1.md**: Unified ingestion, filtering, and spatial join protocol.
- **field_04_metric_mapping_contract_v1.md**: Deterministic pilot threshold mapping.

### Ingestion Infrastructure
- **field_04_mastr_ingestion_runner.py**: Production ingestion runner with 4-tier spatial join strategy, 3-stage deduplication, and audit-ready JSON output.
- **field_04_audit_template.json**: Blank audit scaffold.

### Norf Pilot Execution
- **Primary audit artifact**: `RUN_NEUSS_NORF_FIELD04_20260312_01.json`
- **Supporting document**: `field_04_summary.md`
The runner executed successfully and produced a structurally valid audit record.

---

## Correction & Decontamination Pass
The externally populated MaStR dataset required an audit-honesty correction pass. Two data contamination issues were identified:

1.  **Future-date anomaly**: One installation record reported `commissioning_date = 2026-09-01`. This exceeded the observation window and was excluded.
2.  **Large-system industrial outlier**: A 349.92 kWp system was detected, which does not represent residential PV adoption behavior. To prevent distortion of the social-proof signal, `netto_kwp > 30` records were isolated from the residential proxy metrics.

### Resulting Metrics Layers
The output now separates:
- `raw_metrics`
- `residential_proxy_metrics`
This preserves registry completeness while isolating the residential adoption signal.

---

## Spatial Pinning Attempt
A spatial upgrade pass was executed to move from proxy evidence to segment-exact truth. The pass attempted to perform a **Point-in-Polygon spatial join** against the segment `NEUSS_NORF_01`.

### Result
- **STATUS**: `BLOCKED_GEOMETRY_MISSING`
- The spatial pinning process failed at Geometry Gate (Gate 1). No traceable polygon boundary for `NEUSS_NORF_01` could be located.
- Because of this:
    - Point-in-polygon execution could not be performed.
    - Postal-code proxy logic was retained.
    - Building-normalized metrics were nullified.
    - Adoption score remained withheld.

---

## Current Evidence Grade
The resulting signal therefore remains:
- **Coverage Status**: `PARTIAL`
- **Spatial Match Quality**: `LOW`
- **Evidence Tier**: `E2`
- **Adoption Score**: `WITHHELD`
The field remains audit-honest but proxy-grade.

---

## Root Cause of Blocker
The spatial upgrade failure is not caused by the FIELD_04 pipeline. Instead, the blocker is an external dependency:
**NEUSS_NORF_01 polygon geometry asset missing**

Specifically:
- No Tier A official polygon exists.
- No Tier B traceable derivation inputs were available.
- Only postal-code proxy evidence remains usable.

---

## Current Operational Mode
Until a segment boundary asset is acquired, FIELD_04 operates in:
**`POSTAL_CODE_PROXY_MODE`**

**Evidence basis: PLZ 41470**
This proxy signal is sufficient for:
- Pilot background analysis
- Macro PV adoption context
- Early opportunity scouting
*But it is not sufficient for segment-exact decision scoring.*

---

## Dependency Register
- **Blocking dependency**: `DEP_NEUSS_NORF_01_POLYGON`
- **Description**: Traceable polygon boundary for segment `NEUSS_NORF_01` required to enable spatial pinning.
- **Unlocks**: FIELD_04 spatial upgrade, Point-in-Polygon verification, Segment-exact PV adoption score.

---

## Recommended Next Step
Proceed with **Segment Geometry Acquisition**:
1.  Inventory existing vector and GIS assets.
2.  Search for official administrative layers.
3.  Identify parcel / building footprint derivation inputs.
4.  Construct a traceable segment polygon if possible.

Once geometry is obtained, re-run **FIELD_04 Spatial Pinning Pass** to upgrade the proxy signal to segment-exact truth.

---

## Final Verdict
Field 04 implementation is complete at proxy grade and correctly blocked at geometry gate. No further improvements to the FIELD_04 logic or pipeline are required at this stage. Future upgrades depend solely on acquisition of a traceable boundary geometry for `NEUSS_NORF_01`.
