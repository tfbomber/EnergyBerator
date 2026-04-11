# Stage 2 Input Package README

## Purpose
This package defines the input layer for Stage 2 of the Field 03B Heat-Path Audit. By populating these files, you provide the evidence and targets needed for the audit pipeline to generate compliance-grade reports.

## Getting Started
1. **Drop Sources**: Place your official PDF and image snapshots in `inputs/sources/`.
2. **Configure Run**: Open `configs/audit_config.json` and replace `REPLACE_WITH_...` values.
3. **Register Segments**: Open `inputs/segments/segment_registry.json` and add the IDs and names of the street segments you want to audit.
4. **Update Manifest**: Open `inputs/sources/source_manifest.json` and link your local files to their metadata.

## Mandatory Files
| File | Role |
| :--- | :--- |
| `configs/audit_config.json` | Global run parameters and safety guards. |
| `inputs/segments/segment_registry.json` | The list of targets "who needs an audit?". |
| `inputs/sources/source_manifest.json` | The list of evidence "where is the proof?". |

## Pre-flight Check
Before running the `Stage-2 Execution` pipeline:
- Ensure `local_path` in manifest matches filenames exactly.
- Ensure all `REPLACE_WITH_...` markers have been updated.
- Ensure `official` and `decision_eligible` booleans match the source authority level.
