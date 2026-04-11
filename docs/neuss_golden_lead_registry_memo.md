# Golden Lead Registry Memo — Neuss (Audit Corrected)

## 1. Purpose
This memo records the completion of Stage 14: Golden Lead Registry. This pipeline stage successfully translated segment-level opportunity intelligence into a building-level lead registry format. It provides the initial structural blueprint for downstream installer routing.

## 2. Input Sources
The registry was derived from the following upstream discovery artifacts:
- `neuss_segment_candidates_v2.json` (Stage 11.1)
- `neuss_roof_consistency_registry_v1.json` (Stage 11.2)
- `buildings.parquet` (Base D-ESS data layer)

## 3. Lead Selection Logic
The pipeline targeted `NEUSS_SUBURBAN_01` (the strongest campaign candidate). It pulled the geometry records for all known structures inside that segment from the base parquet file. 

## 4. Current State: MOCK BASELINE
As verified by the Stage 14 Audit, the underlying `buildings.parquet` currently contains **120 MOCK records** for this newly discovered segment (e.g., `MOCK_NEUSS_SUBURBAN_01_000`).
- **Building Type**: `UNKNOWN`
- **Address Fields**: Empty
- **Geometry (Lat/Lon)**: Null

## 5. Lead Class & Recommended Action Logic
Because the building types are unknown and no exact addresses exist, the pipeline's strict proxy-grading logic activated correctly. 
- All 120 leads were safely downgraded to **C-Class**.
- The recommended action for all leads was forced to **HOLD_FOR_VALIDATION**.
The system prioritized analytical honesty over inflating lead scores to "A" or "B".

## 6. Limitations
- **This is a Pre-Qualified List Structure**: In its current v1/v2 schema state, it serves as an infrastructure proof-of-concept.
- **Not Sales Ready**: It cannot be handed to installers for desk review or door-to-door sales until real addresses replace the mocks.
- **Identity Gaps**: Specific homeowner names, precise energy consumption, and consent status are entirely unknown at this layer.

## 7. Final Registry Verdict
Stage 14 **succeeded as a pipeline infrastructure milestone**. The JSON and CSV generation logic successfully executed and applied the correct conservative discounting rules. However, the registry is **NOT sales ready** and **NOT clustering ready**. The immediate next step (Stage 14.3) must be the acquisition of real building footprint data to inject truth into this segment envelope.
