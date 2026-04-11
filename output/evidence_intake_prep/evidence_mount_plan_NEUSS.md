# Evidence Mount Plan: NEUSS
> **Planning Status**: PREPARATION_ONLY
> **Mount Status**: NOT_EXECUTED
> **Activation Impact**: NONE

## Family: OSM/Kataster Geo Boundary
- **expected_file_format**: GeoJSON/WKT
- **suggested_local_project_path**: `d-ess-engine/data/raw/geo/` (Target ONLY)
- **replacement_target**: Stage 22 Proxy Bbox
- **validation_step_after_future_mount**: Schema Lint & Spatial Intersection Check

## Family: Heat Infrastructure Files
- **expected_file_format**: GeoJSON/SHP
- **suggested_local_project_path**: `d-ess-engine/data/raw/infrastructure/` (Target ONLY)
- **replacement_target**: FIELD_03 Heuristics
- **validation_step_after_future_mount**: Schema Lint & Spatial Intersection Check

## Family: Federal MaStR PV Dump
- **expected_file_format**: XML/JSON
- **suggested_local_project_path**: `d-ess-engine/data/raw/mastr/` (Target ONLY)
- **replacement_target**: FIELD_04 Density Proxy
- **validation_step_after_future_mount**: Schema Lint & Spatial Intersection Check

## Family: Operator GIS Check
- **expected_file_format**: JSON
- **suggested_local_project_path**: `d-ess-engine/data/reviews/geo/` (Target ONLY)
- **replacement_target**: E4 Validation Gate
- **validation_step_after_future_mount**: Schema Lint & Spatial Intersection Check
