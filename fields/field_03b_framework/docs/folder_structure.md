# Field 03B: Folder Structure

Proposed directory architecture for the 03B Heat-Path Audit module.

```text
d-ess-engine/fields/03b_framework/
├── schema/
│   └── field_03b_schema.json          # P1: Main data structure
├── docs/
│   ├── evidence_rulebook.md          # P1: Decision and tiering rules
│   ├── ingestion_contract.md         # P1: Input specification
│   ├── validator_spec.md             # P2: Validation rules
│   └── folder_structure.md           # P2: This file
├── configs/
│   └── audit_config.json             # Runtime configuration
├── templates/
│   └── audit_object_template.json    # P1: Reference output
└── inputs/
    ├── sources/
    │   └── source_manifest.json      # List of PDF/URL snapshots
    └── segments/
        └── segment_registry.json     # List of street segments to audit
```

## Naming Conventions

### 1. Source Snapshots
- Format: `src_[SOURCE_ID]_[YYYYMMDD]_v[X.X].pdf`
- Example: `src_municipal_plan_20240315_v1.0.pdf`

### 2. Manifests & Registries
- Format: `manifest_[CITY]_[RUN_ID].json`
- Example: `manifest_berlin_2026_03_09.json`

### 3. Audit Runs
- Format: `audit_result_[SEGMENT_ID]_[RUN_ID].json`
- Example: `audit_result_SEG_5512_2026M03D09.json`

### 4. Schema Versions
- Format: `field_03b_schema_v[MAJOR].[MINOR].json`
- Use Semantic Versioning for any structure-breaking changes.
