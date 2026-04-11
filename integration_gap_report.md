# MVP Integration Gap Report

**D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization. It does not perform household-level confirmation or operational activation.**

## 1. Connected Real Signals
The `build_area_features.py` pipeline successfully ingested the following real legacy outputs:

1. **`building_suitability`**: Derived natively from `output/stage6/segment_registry_neuss_v1.json` by dividing `residential_building_count` by `building_count`.
2. **`heat_pump_proxy`**: Pulled directly from `output/field_05/FIELD_05_HEAT_PUMP_ADOPTION_NEUSS_SEGMENTS.json` (`estimated_heat_pump_adoption` mapped via persistent or base segment IDs).
3. **`electrification_proxy`**: Ingested directly from `output/stage6/segment_electrification_score.json`.
4. **`district_heating_interference`**: Parsed structurally from the `"key_drivers"` array inside the electrification score (detecting strings like "NO_DH").
5. **`data_quality_score`**: Handled via the `"status": "REAL_GROUNDED"` flag from the native segment registry.

## 2. Missing/Placeholder Fields
- **`roof_pv_signal`**: Currently using a pure placeholder (0.65). While raw PV metadata exists in `neuss_41470_pv_enriched.json`, allocating single systems to their respective coordinate-bound segments requires the legacy spatial-join geometries. Without porting the full heavy-geometry engine, establishing pure PV density by segment remains mocked in this round.
- **`owner_occ_proxy` / `household_fit_proxy`**: Currently placeholders (0.55, 0.80). We lack an explicit socio-demographic segment mapping array in the current output folder snapshot.
- **`area_id`**: Transitional. We are using the legacy `segment_id` (e.g., `NEUSS_NORF_01`) rather than pure H3 hexagons.

## 3. Next Best Integration Steps
1. **PV Spatial Cross-Mapping**: Provide an adapter script `build_pv_area_density.py` which reads the raw PV lat/lon from the MaStR dump and clusters them directly into basic H3 Hexagons or loops them across segment bounding boxes.
2. **H3 Extrapolation**: Switch `area_id` formally from string names (Segments) into Hex Strings to support universal tile mapping. Do not wait for segment geometry to be perfect.
