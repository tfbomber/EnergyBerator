# FIELD_04 Protocol: PV Adoption Signal v1.0

## 1. Objective
Measure real-world PV adoption using official registry data (MaStR) aggregated to the segment level. This field represents observed behavior, not theoretical potential.

## 2. Source Policy
- **Primary Source**: MaStR (Marktstammdatenregister) official CSV exports.
- **Allowed Files**: `EinheitenSolar_*.csv` or `mastr_export_pv_*.csv`.
- **Mapping**: Logical keys are resolved via `raw_to_logical.json`.

## 3. Filtering Chain
1. **Technology**: `tech_class == SOLAR_PV`.
2. **Status**: `status == "In Betrieb"` (Operational).
3. **Geography**: Filter by postcode prefix (e.g., `414` for Neuss).
4. **Validity**: Coordinates must be valid (non-null, non-zero, within DE bounding box).

## 4. Spatial Join Protocol
- **Tier 1 (Anchor Match)**: Point inside a residential building footprint. (HIGH confidence)
- **Tier 2 (Buffer Match)**: Point within 10m of a residential footprint. (MEDIUM confidence)
- **Tier 3 (Segment Match)**: Point inside the segment polygon but outside building polygons. (CONTEXT only)
- **Tier 4 (Unresolved)**: Point outside any valid segment or too far from buildings.

## 5. Deduplication Policy
1. **Raw Row**: Remove identical rows.
2. **Installation Level**: Unique MaStR ID (`id_mastr`).
3. **Building Level**: Multiple installations on the same `building_id` count as ONE for adoption numerator purposes.

## 6. Aggregation & Normalization
- **Adoption Rate**: `Unique buildings with PV / Total residential buildings`.
- **Installation Density**: Count per km² or per 100 buildings.
- **Capacity Density**: Total kWp per km².

## 7. Business Mapping
Raw metrics are mapped to labels (`NONE_OBSERVED`, `LOW_ADOPTION`, etc.) using the `field_04_metric_mapping_contract_v1.md`.

## 8. Data Quality & Tiers
- **E1**: Predominantly Tier 1 (Footprint) spatial matches.
- **E2**: Predominantly Tier 2 (Buffer) or geocoded address matches.
- **E3**: Contextual or coarse approximation only.
- **UNKNOWN**: Insufficient data or missing source file.
