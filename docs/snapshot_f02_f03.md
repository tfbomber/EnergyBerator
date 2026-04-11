# Technical Documentation: Joint Snapshot F02 + F03

## Overview
This snapshot provides a unified view of Building Type (Field 02) and District Heating Status (Field 03) for the Neuss/Allerheiligen pilot area. It is intended for cross-field analysis and as a base for future Street Opportunity Scoring.

## Input Provenance
- **Field 02**: Derived from spatial adjacency analysis (neighbors count) on real OSM building footprints.
- **Field 03**: Derived from spatial overlay between buildings and OSM heating infrastructure.
- **Universe**: 298 buildings in the `ALLERHEILIGEN_PILOT_SEG_01` segment.

## Dataset: Building Snapshot
**Location**: `data/snapshots/building_snapshot_f02_f03.parquet`

| Column | Description |
|---|---|
| `building_id` | Unique OSM-based identifier. |
| `segment_id` | Street segment identifier (`ALLERHEILIGEN_PILOT_SEG_01`). |
| `building_type` | `detached` / `semi` / `rowhouse`. |
| `dh_status` | `EXISTING` / `PLANNED` / `NONE` / `UNKNOWN`. |
| `field_02_confidence` | Confidence score for building type (0.90). |
| `field_03_confidence` | Confidence score for heating status (0.80). |
| `building_geometry_basis` | `OSM_WKT` representing real geometric data. |

## Dataset: Segment Snapshot
**Location**: `data/snapshots/segment_snapshot_f02_f03.parquet`
Provides aggregated counts and ratios per segment, including cross-metrics like `rowhouse_none_dh_count`.

## Alignment Check
- Field 02 Row Count: 298
- Field 03 Row Count: 298
- Joined Row Count: 298
- **Verdict**: Perfect 1:1 row alignment verified.

## Limitations
- **Field 03 Data**: Currently limited to `OSM_PROXY`. Absence of heating in the snapshot does not confirm real-world absence without municipal verification.
- **Pilot Scope**: Validated only for the specific Allerheiligen pilot subset.
