# Evidence Dropzone Specification
> **Directories govern how physical files enter the pipeline.**

## 1. Directory Semantics
- `/data/external_evidence/geometry/`: Strict WKT/GeoJSON boundaries only.
- `/data/external_evidence/field/`: API extracts for Heat/PV.
- `/data/external_evidence/manual_review/`: JSON records representing E5 Operator approvals.

## 2. File Uniqueness and Duplicate Rules
- **Physical Duplicates**: If file hash matches an already processed artifact -> Ignore (silent drop / archival link).
- **Semantic Conflicts**: If new artifact targets same Segment/Field but differs in payload -> Trigger `HOLD_FOR_MANUAL_REVIEW` / version collision.

## 3. Archival Expectations
Processed physical files must be moved downstream to `/data/archive/[YEAR]` to prevent re-execution.