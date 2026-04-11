# Stage 14.3 — Real Building Truth Injection Plan

## 1. Purpose
Stage 14.3 is a truth-acquisition and truth-injection stage. Its purpose is to replace MOCK building placeholders with real, building-linked records sufficient for downstream lead recomputation and spatial clustering.

## 2. Required Inputs
- Existing proxy boundary / candidate polygon for NEUSS_SUBURBAN_01
- Current D-ESS `buildings.parquet` containing MOCK placeholder records
- External building-truth sources for Neuss
- A deterministic spatial join rule for clipping candidate buildings into the target segment

## 3. Minimum Truth Requirements
1. **Real Building Identity**
   - non-mock `building_id` or source-stable derived identifier
2. **Spatial Truth**
   - valid geometry anchor
   - polygon preferred, centroid / lat-lon acceptable as interim minimum
3. **Address Truth**
   - preferred: `street` + `house_number` + `postal_code`
   - minimum acceptable for clustering: `street` + `postal_code`
4. **Building Classification**
   - source-native building type if available
   - otherwise auditable inferred type with traceable method

## 4. Recommended Source Hierarchy
- Tier A — Official Municipal / Cadastre Data
- Tier B — NRW Authoritative Open Geodata
- Tier C — OSM / Overpass fallback

### Source Precedence Contract
- Tier A overrides Tier B and Tier C.
- Tier B overrides Tier C.
- Lower-tier data may fill null gaps only.
- Lower-tier data must not overwrite populated higher-tier values.
- Field-level source provenance should be retained whenever feasible.

## 5. Upgrade Targets for the Lead Registry
Target fields to populate:
- `building_id` (Replace MOCK)
- `street`, `house_number`, `postal_code` (Replace empty strings)
- `lat`, `lon` (Replace nulls)
- `building_type` (Replace `UNKNOWN`)

Recommended traceability metadata fields:
- `geometry_source`
- `address_source`
- `building_type_source`
- `building_type_confidence`

## 6. Exit Criteria for Allowing Stage 15 Clustering
1. > 80% of records have non-mock `building_id`
2. > 80% of records have valid spatial anchors (lat/lon at minimum)
3. > 70% of records have usable address data for clustering (`street` + `postal_code` minimum)
4. > 60% of records have `building_type` populated from source or auditable inference
5. The resulting buildings table can fully replace the current MOCK stubs in `buildings.parquet`
6. Lead regeneration runs successfully without fallback-only dependency on MOCK records
*(Note: Lead promotion is a downstream expected consequence, not a completion rule.)*

## 7. Non-Goals
Stage 14.3 does NOT aim to:
- optimize campaign ranking
- perform street clustering
- generate installer routes
- inflate lead outcomes

Its sole role is to replace mock building placeholders with real building truth.
