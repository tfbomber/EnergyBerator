# UAT-S1 Test Results (2026-03-01)

## Summary
- **Execution Date**: 2026-03-01
- **Tester**: Antigravity
- **Target Version**: v1.2.0-beta
- **Environment**: Local CLI / Adapter

---

## Result Details

### UAT-01: Golden Path
- **Verdict**: `APPROVED`
- **Output**: [UAT-01_report.json](../../artifacts/uat_s1/uat-01_report.json)
- **Summary**: All steps completed. Audit trail contains policy_hash and verification markers.

### UAT-02: Missing Evidence
- **Verdict**: `BLOCKED`
- **Reason**: `EVIDENCE_NOT_FOUND`
- **Output**: [UAT-02_report.json](../../artifacts/uat_s1/uat-02_report.json)

### UAT-03: Anchor Not Found
- **Verdict**: `BLOCKED`
- **Reason**: `ANCHOR_NOT_FOUND` (KeyError on mandatory anchor resolution)
- **Output**: [UAT-03_report.json](../../artifacts/uat_s1/uat-03_report.json)

### UAT-04: Vorhabenbeginn Violation
- **Verdict**: `INELIGIBLE_REJECTED`
- **Audit**: `TIMING_CHECK: REJECTED`
- **Output**: [UAT-04_report.json](../../artifacts/uat_s1/uat-04_report.json)

### UAT-05: Missing Required Fields
- **Verdict**: `NEEDS_INFO`
- **Missing**: `MISSING_FACTS: ['application_date']` (Sampled)
- **Output**: [UAT-05_report.json](../../artifacts/uat_s1/uat-05_report.json)

### UAT-06: Format/Parse Error
- **Verdict**: `INVALID_INPUT`
- **Error**: `FIELD_PARSE_ERROR` (Invalid date format)
- **Output**: [UAT-06_report.json](../../artifacts/uat_s1/uat-06_report.json)

### UAT-07: Overlay=PAUSED
- **Verdict**: `INELIGIBLE_REJECTED`
- **Tags**: `PAUSED`
- **Insight**: System successfully applied PAUSED tag from overlay without masking the underlying rejection logic.
- **Output**: [UAT-07_report.json](../../artifacts/uat_s1/uat-07_report.json)

### UAT-08: Legacy Mode
- **Verdict**: `APPROVED`
- **Context**: `V1.1_LEGACY`
- **Trace**: Contains `legacy_mode=True` and mapping history.
- **Output**: [UAT-08_report.json](../../artifacts/uat_s1/uat-08_report.json)

### UAT-09: Deliverable Verification
- **Status**: `PASS`
- **Evidence**: JSON reports generated with valid contract schema.

### UAT-10: Consistency Verification
- **Status**: `PASS`
- **Metric**: SHA256 Hash Match (Normalized)
- **Result**: `BIT-BY-BIT PARITY`
