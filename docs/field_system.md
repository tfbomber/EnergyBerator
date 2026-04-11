# D-ESS Street Intelligence Field System

This documentation describes the modular architecture for processing and storing analytical fields in the Street Intelligence Engine.

## Purpose

The **Field System** is designed to allow horizontal scaling of building and segment analysis. New analytical modules (e.g., PV potential, heat demand, building age) can be added as "Fields" without modifying the core pipeline.

## Field Levels

| Level | Description | Example |
|---|---|---|
| **Building** | Analysis performed for each individual building geometry. | `field_02_building_type` |
| **Segment** | Analysis aggregated or performed at the street segment level. | `field_04_pv_density` |

## Data Architecture

### Input
The system reads from `data/buildings.parquet`.
Standard schema: `[building_id, segment_id, geometry, building_type, neighbors]`

### Output
Each field produces its own dataset in `data/fields/field_XX_name.parquet`.
Standard schema:
- `building_id` / `segment_id`
- `field_id`: e.g., `field_02`
- `field_value`: result value
- `confidence`: numeric score 0.0-1.0
- `source`: processing method (e.g., `rule_base_v1`)
- `notes`: debug info

## Adding a New Field

1.  **Define Field**: Add the new field metadata to `config/field_registry.yaml`.
2.  **Implementation**: Create a script under `fields/field_XX_name.py`.
3.  **Run Pipeline**: Execute `core/run_fields.py` to process active fields.
4.  **Aggregation**: If the field is building-level, `core/segment_aggregator.py` can be used to summarize it for segment analysis.
