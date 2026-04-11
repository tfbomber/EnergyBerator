# Stage 2 Pre-flight Checklist

Use this checklist to verify that the environment is safe for automated Stage 2 execution.

## 1. Governance Artifacts
- [ ] `schema/field_03b_schema.json` is present.
- [ ] `docs/evidence_rulebook.md` is present.
- [ ] `docs/validator_spec.md` is present.
- [ ] `docs/ingestion_contract.md` is present.

## 2. Input Integrity
- [ ] `configs/audit_config.json`: `audit_run_id` and `city` are set.
- [ ] `inputs/segments/segment_registry.json`: All segments have unique IDs.
- [ ] `inputs/sources/source_manifest.json`: Every source has `official` and `decision_eligible` defined.

## 3. Local File Availability
- [ ] Every file listed in `source_manifest.json` (`local_path`) exists in `inputs/sources/`.
- [ ] No placeholder values (`REPLACE_WITH_...`) remain in any JSON file.

## 4. Constraint Compliance
- [ ] `allow_live_fetch` is `false` (Strict Stage-2 rule).
- [ ] No OSM data or proximity logic is included as a source.
