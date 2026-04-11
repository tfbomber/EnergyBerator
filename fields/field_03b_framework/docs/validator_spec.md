# Field 03B: Validator Spec

This document defines the validation rules that Field 03B audit objects must pass before being used in the D-ESS pipeline.

## 1. Hard Failure (Audit Blocked)

Failure in any of these checks results in a total rejection of the audit object and requires manual resolution.

- **F1: Schema Non-Compliance**: JSON fails to validate against `field_03b_schema.json`.
- **F2: Evidence Missing for Conclusion**: `segment_heat_status` is not `unknown` but `evidence_items` is empty.
- **F3: Citation Anchor Violation**: Official evidence (`official: true`) lacks a `citation_ref` or `source_id`.
- **F4: Unconfirmed Building Status Leakage**: `building_heat_status` is anything other than `unknown` or `not_indicated` while `evidence_items` only contain segment-level relevance claims.
- **F5: Disallowed Decision Path (Tier Violation)**: `decision_impact` is set to any route-gate action (`block_hp_default_path`, `suppress_hp_direct_push`, or `allow_hp_with_window_note`) but the highest `evidence_tier` is E3 or E4. Strong decisions require E1/E2; otherwise it must be `manual_check_required`.

---

## 2. Soft Warning (Audit Tagged for Review)

Object is valid but requires an "Auditor Attention" flag in downstream UIs.

- **W1: No Page Reference**: `page_ref_or_section` is null for a PDF source type.
- **W2: Expired Sources**: `last_updated` date of an evidence source is older than 5 years.
- **W3: Low Search Coverage**: `search_coverage` is `insufficient_source_coverage`.
- **W4: Horizon Implausibility**: `realization_horizon` is set to "known" but `target_year` is in the past.

---

## 3. Mandatory Cross-Field Validation

The validator must assert the consistency between fields:

| Trigger Field | Value | Expected Dependent Value | Validation Type |
| :--- | :--- | :--- | :--- |
| `segment_heat_status` | `unknown` | `decision_impact` = `manual_check_required` | Hard Check |
| `segment_heat_status` | `existing_heat_network_area` | `manual_verification_required` = `false` | Soft Check (Usually) |
| `heat_source_type` | != `unknown` | `official` = `true` (in at least one source) | Hard Check |
| `search_coverage` | `source_checked_but_segment_not_indicated` | `segment_heat_status` != `existing_...` | Hard Check |

---

## 4. Evidence Stringency Check

If `official: false`, the `decision_eligible` flag **MUST** be `false`. Failure to follow this is a **HARD FAIL**.
