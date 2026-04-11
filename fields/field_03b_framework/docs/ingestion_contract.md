# Field 03B: Ingestion Contract

This document defines the interface for data entering the Field 03B Audit Pipeline.

## 1. Required Input Files

### A. `source_manifest.json`
Catalog of PDF/URL sources to be crawled or reviewed.
- **Fields**:
  - `source_id` (string, unique)
  - `official` (boolean, mandatory true/false)
  - `decision_eligible` (boolean, mandatory true/false)
  - `official_level_meta` (string: municipal, state, federal, unofficial - descriptive only)
  - `trust_score` (0.0 to 1.0)
  - `content_type` (text, map, table)
  - `last_updated` (iso8601)

### B. `segment_registry.json`
The list of street segments to be audited.
- **Fields**:
  - `segment_id` (string, unique)
  - `city_name` (string)
  - `postal_code` (string)
  - `street_name` (string)

### C. `audit_config.json`
Global settings for the audit run.
- **Fields**:
  - `audit_run_id` (string)
  - `min_evidence_tier_for_block` (default: "E1")
  - `default_realization_horizon_if_unset` (years, or null)

---

## 2. Validation & Nullability Policy

- **Encoding**: UTF-8 strictly required.
- **Null Handling**:
  - Empty strings are treated as NULL.
  - Optional fields missing from JSON are treated as NULL.
- **Malformed Inputs**:
  - Missing `segment_id` or `source_id`: **HARD FAIL** (Skip record).
  - Invalid `city_name`: **SOFT WARN** (Proceed with metadata tag).

---

## 3. Evidence Eligibility Flags
Input sources entering the extraction pipeline must be tagged with a `decision_eligible` boolean.
- `decision_eligible: true` -> Allowed to trigger `block_hp` or `suppress_hp`.
- `decision_eligible: false` -> Downgrades all results to `manual_check_required` or `allow_hp_with_window_note` even if the text claims full coverage.

---

## 4. Failure Behavior
- **Registry Mismatch**: If a segment appears in the registry but no evidence is found in sources, the output must be `segment_heat_status: unknown` and `search_coverage: source_checked_but_segment_not_indicated`.
- **Duplicate Source IDs**: The pipeline must deduplicate by taking the latest `last_updated` timestamp.
