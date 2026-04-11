# FIELD_04 Status Taxonomy V2

This document defines the official machine-readable and audit-safe status enums for FIELD_04 (PV Adoption Signal).

## 1. Registry Data State (Anchor Quality)
| Code | Meaning |
|---|---|
| `LOKATION_DATA_PENDING` | Lokation XML source files not yet acquired or local snapshot missing. |
| `ANCHOR_MISSING` | Source files present, but effective coordinate fill rate < 20%. |
| `ANCHOR_PARTIAL` | Effective coordinate fill rate between 20% and 79% (Insufficient for E1). |
| `ANCHOR_VALIDATED` | Effective coordinate fill rate >= 80% (Passes Gate 3). |

## 2. Segment Geometry Status
| Code | Meaning |
|---|---|
| `GEOMETRY_MISSING` | No spatial boundary available for the target segment. |
| `PLZ_PROXY` | Postal code (PLZ) centroid or area used as geographic stand-in. |
| `PROJECT_DERIVED_CONVEX_HULL` | Mathematical envelope (Convex Hull) derived from building footprints in `buildings.parquet`. Non-closure-grade. |
| `OFFICIAL_BOUNDARY` | Cadastral or administrative boundary polygon sourced from official city/land registry. |

## 3. Spatial Join Method
| Code | Meaning |
|---|---|
| `UNRESOLVED` | No spatial test possible or attempted. |
| `POSTAL_CODE_PROXY` | Record assignment based solely on PLZ match. |
| `POINT_IN_POLYGON_DERIVED` | Spatial pinning executed against a `PROJECT_DERIVED_CONVEX_HULL`. |
| `POINT_IN_POLYGON_OFFICIAL` | Spatial pinning executed against an `OFFICIAL_BOUNDARY`. |

## 4. Score Restoration Status
| Code | Meaning |
|---|---|
| `WITHHELD_LOKATION_DATA_PENDING` | Score nullified because Lokation data is missing. |
| `WITHHELD_INSUFFICIENT_SPATIAL_SUPPORT` | Join rate or anchor quality failed quality gates (Gate 2/3). |
| `RESTORED_PROJECT_GEOMETRY` | Score released based on `POINT_IN_POLYGON_DERIVED` results (Standard E2). |
| `RESTORED_OFFICIAL` | Score released based on `POINT_IN_POLYGON_OFFICIAL` results (E1). |
| `OBSERVED_ZERO` | Valid run executed; zero assets pinned inside boundary. Score = 0.0. |
