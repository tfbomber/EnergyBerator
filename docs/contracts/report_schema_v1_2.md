# D-ESS Report Schema V1.2 (Public Contract)

This document defines the mandatory stable interface for the D-ESS Engine reports. Downstream consumers (SAP, UI, Auditors) can rely on these fields.

## 1. Top-Level Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `report_id` | `string` | Unique identifier for the run. |
| `status` | `string` | Final decision (Enum). |
| `subsidy_total_eur` | `string` | Final subsidy amount in "0.00" format. |
| `audit_trail` | `array` | List of steps taken to reach the verdict. |
| `report_meta` | `object` | Versioning and runtime metadata. |
| `runtime_gate` | `object` | Policy status and health check signals. |

## 2. Status Enums (final_verdict)

| Code | Description |
| :--- | :--- |
| `APPROVED` | Eligible for subsidy. |
| `INELIGIBLE_REJECTED` | Deterministic rejection (e.g., Timing, Location). |
| `NEEDS_INFO` | Missing mandatory facts for calculation. |
| `BLOCKED` | Evidence/Anchor resolution failure (Audit Block). |
| `INVALID_INPUT` | Payload parsing or schema violation. |

## 3. Audit Trail Entry

Each entry in `audit_trail` must contain:
- `msg`: Human-readable description.
- `policy_hash`: SHA256 of the policy used (guaranteed even for early exits).
- `evidence_check`: (Optional/Contextual) Boolean if evidence was verified.

## 5. Field Stability & Determinism

The D-ESS Engine enforces a **Determinism Gate** in CI. Fields are classified into two categories:

### A. Stable Fields (Zero-Change Tolerance)
These fields must be bit-by-bit identical between two runs of the same input:
- `status` (Final verdict)
- `subsidy_total_eur`
- `audit_trail` (Content must be identical; list order is normalized by `step_id` or `code`)
- `runtime_gate` status signals

### B. Volatile Fields (Excluded from Determinism Gate)
These fields are allowed to change between runs and are ignored during hash verification:
- `run_id` / `report_id`: Unique execution identifiers.
- `trace_id`: Request-level tracing.
- `generated_at` / `timestamp`: Wall-clock execution time.
- `execution_time`: Measured performance duration.
- `export_path`: Local filesystem paths.

> [!NOTE]
> `runtime_status` (tags) are considered stable fields but are sorted alphabetically before comparison to ensure logical equivalence.
