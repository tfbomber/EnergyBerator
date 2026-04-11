# MaStR_Ingestion_Protocol_v1

## 1️⃣ INGESTION SCOPE CONTRACT
- **Primary Scope**: Norf Pilot Segments (NEUSS_NORF_01, etc.).
- **Strategy**: Norf-first execution is mandatory before citywide scale-up.
- **Dependency**: Protocol assumes a valid D-ESS residential building inventory (Truth Base) is present for the target area.
- **Scaling Rule**: Citywide execution is blocked until the official citywide OSM building geometry layer is acquired and stored.

## 2️⃣ RAW DATA CONTRACT
### A. logical_required_fields
| Internal Name | Logical Purpose | Validation Rule |
| :--- | :--- | :--- |
| `tech_class` | Identify source as PV/Solar | Must contain PV-related category |
| `status` | Operation status (Active/Closed) | Filter for COMMISSIONED/IN_OPERATION |
| `location_ref` | Municipality/Locality metadata | Must match Neuss or Norf context |
| `postcode` | Geographic pre-filtering | Valid 5-digit German PLZ |
| `commissioning_date` | Date of grid connection | Must be valid ISO-8601 or parseable date |
| `installed_power` | System size (kWp) | Numeric / Decimal |
| `lat` / `lon` | Geographic truth anchors | WGS84 decimal format |
| `id_mastr` | Unique system identifier | Required for deduplication |

### B. support_fields
- `address_fragment`: Street/No for manual audit/refinement.
- `operator_type`: (Optional) Filter for residential vs commercial.

### C. forbidden-to-anchor_fields
- **Plain Postcode**: Forbidden to use as a spatial anchor for segment assignment.
- **Locality Name Only**: Forbidden to use as a spatial anchor.

## 3️⃣ FILTERING LOGIC
1. **Technology Filter**: Isolate `tech_class == SOLAR_PV`.
2. **Operation Filter**: Keep only `status == OPERATIONAL` (In Betrieb).
3. **Geography Prefilter**: Keep records where `postcode` or `municipality` matches Neuss districts.
4. **Coordinate Validity**: Discard records with NULL, 0, or invalid Lat/Lon (outside DE bounding box).
5. **Quality Clean**: Deduplicate raw rows sharing the same `id_mastr`.

## 4️⃣ SPATIAL JOIN PROTOCOL
Hierarchy for internal assignment (Point-in-Polygon):
1. **Tier 1 (Anchor Match)**: Point exists strictly inside an OSM residential building footprint.
2. **Tier 2 (Buffer Match)**: Point exists within [Configurable Radius, default 10m] of a residential footprint.
3. **Tier 3 (Segment Match)**: Point exists inside a Segment polygon but outside specific buildings. (Mark as `loose_match`).
4. **Tier 4 (Unresolved)**: Point outside any valid segment or too far from buildings.

**Ambiguity Handling**: If a point matches >1 residential footprint (at Tier 1 or 2), the record is marked `ambiguous` and assigned to the nearest candidate building ID, logging the conflict.

## 5️⃣ COORDINATE TOLERANCE POLICY
- **Tolerance**: Default 10 meters for building-level snap.
- **Audit**: Every record must store `spatial_match_mode` (FOOTPRINT, BUFFER, SEG_POLY, UNRESOLVED).
- **Log**: Records snapped via Buffer must record the calculated distance.
- **Snap Rule**: No silent snapping. Coordinates are used "as-is" for the join; building assignment is a metadata link, not a coordinate modification.

## 6️⃣ BUILDING-LEVEL DEDUPLICATION LOGIC
- **Rule**: Multiple MaStR installations mapping to the same Building ID count as **ONE** building for the adoption numerator.
- **Identity**: If `building_id` is common across rows, the numerator contribution is 1.
- **Rationale**: Adoption rate measures *penetration among physical structures*, not total system count.

## 7️⃣ SEGMENT AGGREGATION LOGIC
For each `segment_id`:
1. **numerator**: Count unique Residential Building IDs in the segment having at least one resolved PV record.
2. **denominator**: Total Residential Building Count from D-ESS Truth Registry for that segment.
3. **adoption_rate**: `numerator / denominator`. (NULL if denominator is 0).
4. **stats**:
   - `pv_installation_count_raw`: Total raw MaStR records falling into segment.
   - `unresolved_record_count`: Records with no valid spatial anchor.
   - `ambiguous_record_count`: Records with spatial conflicts.

## 8️⃣ OUTPUT DATASET SCHEMA
**Target**: `d-ess-engine/data/fields/field_04_real_pv_adoption.parquet`

| Field | Type | Nullable | Definition |
| :--- | :--- | :--- | :--- |
| `segment_id` | STRING | No | Unique D-ESS Segment Identifier |
| `adoption_rate` | FLOAT | Yes | The calculated adoption signal (0.0 to 1.0) |
| `building_pv_count` | INT | No | Numerator: Unique buildings with PV |
| `building_total_count` | INT | No | Denominator: Total residential buildings |
| `raw_installation_count`| INT | No | Total raw records processed for segment |
| `match_quality_index` | FLOAT | No | Ratio of Footprint-resolved vs total records |
| `evidence_tier` | STRING | No | Always `REAL_MASTR_GROUNDED` for success |
| `ingestion_run_id` | STRING | No | Unique UUID per run |
| `source_version` | STRING | No | MaStR Export Date / Version |

## 9️⃣ ERROR HANDLING & FAILURE POLICY
- **Missing Geo**: Record -> `unresolved`. Do not assign to nearest segment by text.
- **Conflict**: Match >1 Segment -> Mark `ambiguous`. Check if point is on segment boundary.
- **Zero Denominator**: Set `adoption_rate` to NULL. (Prevents DivisionByZero or fake 0%).
- **Pilot Mask**: Records falling outside the active Pilot Mask (e.g., outside Norf) during a Pilot Run are excluded from the output.

## 🔟 AUDIT & VALIDATION CHECKS
- **Logic Check**: `building_pv_count <= building_total_count`.
- **Constraint**: `adoption_rate` between 0 and 1.
- **Provenance**: `source_version` must be verified against `evidence_index.json`.
- **Match Stats**: Minimum 70% of raw records in a Pilot area should resolve to at least `SEG_POLY` level for a "Pass" verdict.

## 1️⃣1️⃣ IMPLEMENTATION NOTES FOR ANTI
- **Schema First**: DO NOT start coding before inspecting the CSV header of the actual MaStR extract.
- **Mapping Table**: Implement a `raw_to_logical.json` mapping file to handle BNetzA column naming variations.
- **Lib**: Use `geopandas` for Spatial Joins.
- **Dedupe**: Perform building-id deduplication *after* the spatial join.

## 1️⃣2️⃣ OUTPUT FORMAT REQUIREMENT
- Final report must deliver the `field_04_real_pv_adoption.parquet` along with a `metadata_audit_summary.json`.
