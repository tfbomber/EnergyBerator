# Field 03: District Heating

## Purpose
Field 03 identifies the district heating (Fernwärme) status for buildings. This information is critical for energy advisory to determine if a building is eligible for a heat pump or if a district heating connection is existing or planned (which might negatively impact heat pump ROI or subsidy availability).

## Field Values
- **EXISTING**: Building is within an existing district heating service area.
- **PLANNED**: Building is within a planned Wärmeplanung / expansion zone.
- **NONE**: No district heating or planning zones detected.
- **UNKNOWN**: Insufficient data to determine status.

## Data Source
- **Mock Source**: `data/heating_zones_mock.geojson` (Neuss/Allerheiligen pilot area).
- **Logic**: Spatial intersection (simulated in MVP) between building footprints and heating zone polygons.

## Aggregation
Aggregated at the street segment level (`segment_id`) as counts and ratios:
- `existing_dh_count` / `existing_dh_ratio`
- `planned_dh_count` / `planned_dh_ratio`
- `none_dh_count` / `none_dh_ratio`
- `unknown_dh_count` / `unknown_dh_ratio`

## Limitations
- The current implementation uses a simulated spatial overlay pending full GIS polygon integration.
- Planning zones are indicative and do not represent a legal obligation to connect unless explicitly verified by municipal statutes.
