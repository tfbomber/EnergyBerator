# Evidence File Acceptance Contract
> **Planning Status**: PREPARATION_ONLY (Rules for Future Integration)
## 1. Accept/Reject Terminal Output States
Every arriving physical file MUST map to one of these terminal outcomes:
- `ACCEPT_FOR_REVIEW`: File parsed successfully. Content requires operator checking (E5 mapping).
- `ACCEPT_FOR_CONDITIONAL_INTEGRATION`: File valid and mapped. Sent to integrators. **Does NOT imply tier upgrade, retry authorization, or truth promotion.**
- `REJECT_AND_LOG`: Terminal rejection (Stale, Invalid format).
- `HOLD_FOR_MANUAL_REVIEW`: Semantic conflict requires offline resolution.

*Mandatory Enforcer: `STILL_BLOCKED` remains the persistent default state of all candidates. No ACCEPT outcome modifies this state intrinsically.*

## 2. Minimum Intake Preconditions (Paired Logic)
| Acceptance Condition | Paired Rejection Condition |
|---|---|
| File matches valid JSON/GeoJSON schema. | Schema unparseable. -> `REJECT_AND_LOG` |
| File Metadata includes valid `candidate_id` anchor. | Missing `candidate_id` or `future_segment_id`. -> `REJECT_AND_LOG` |
| Explicit `source_tier` defined (e.g. E4). | `source_tier` empty. -> `REJECT_AND_LOG` |
| Epistemic Lineage unbroken back to OS/Gov origin. | Origin unverifiable. -> `REJECT_AND_LOG` |
| Manual review object serves as governance support only. | Manual file attempts unrestricted Tier override. -> `REJECT_AND_LOG` |