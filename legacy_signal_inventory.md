# Legacy Signal Inventory

**D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization. It does not perform household-level confirmation or operational activation.**

## 1. Segment Base Registry
- **File Path**: `output/stage6/segment_registry_neuss_v1.json`
- **File Type**: JSON
- **Key Fields**: `segment_id`, `centroid_lat`, `centroid_lon`, `building_count`, `residential_building_count`, `persistent_id`.
- **MVP Mapping**: 
  - `area_id` = `segment_id` (fallback transitional geo until H3 is operationalized).
  - `building_suitability` = `residential_building_count` / `building_count`.
- **Status**: Directly Reusable.

## 2. Electrification Baseline Score
- **File Path**: `output/stage6/segment_electrification_score.json`
- **File Type**: JSON
- **Key Fields**: `segment_id`, `segment_electrification_score`, `key_drivers`.
- **MVP Mapping**: 
  - `electrification_proxy` = `segment_electrification_score`.
  - `district_heating_interference` = Extracted from `key_drivers` (e.g., "low district heating conflict").
- **Status**: Directly Reusable for exact mapped segment. Set fallback to 0.5 for others.

## 3. Heat Pump Adoption Truth (Field 05)
- **File Path**: `output/field_05/FIELD_05_HEAT_PUMP_ADOPTION_NEUSS_SEGMENTS.json`
- **File Type**: JSON
- **Key Fields**: `segment_id`, `estimated_heat_pump_adoption`.
- **MVP Mapping**: 
  - `heat_pump_proxy` = `estimated_heat_pump_adoption` (normalized heavily to an index, currently raw percentages).
- **Status**: Reusable with minor mathematical normalization.

## 4. MaStR PV Source (Raw)
- **File Path**: `data/sources/mastr/neuss_41470_pv_enriched.json`
- **File Type**: JSON
- **Key Fields**: `netto_kwp`, `plz`.
- **MVP Mapping**: 
  - `roof_pv_signal` = Blocked from direct segment allocation without a spatial join step. Will use placeholders or basic total aggregation until geometry engine is restored.
- **Status**: Blocked for direct segment mapping this round. Using fallback / transitional baseline.
