# FIELD_03 Verdict Mapping Contract v1.0

## 1. Purpose of the Mapping
This document defines the strict translation boundary between the field-agnostic **D-ESS Evidence Engine (Decision Layer)** and the domain-specific **FIELD_03 Business Output Layer (KWP / Heat Gate Protocol)**. 

The primary objective is to ensure that the core Evidence Engine remains strictly generic and purely evidence-evaluating, while the geographic and business-specific heating logic (e.g., KWP outcomes) is safely synthesized within its own isolated layer.

## 2. Layer Separation
The decision architecture is strictly separated into two distinct layers to prevent domain logic from polluting the generic evidence evaluation:

- **Layer 1: Generic D-ESS Evidence Engine**
  Responsible solely for evaluating the validity, sufficiency, temporal relevance, and conflict state of the provided evidence. This layer has absolutely zero knowledge of "Heat Grids", "KWP", or "Decentralized Heat".
  
- **Layer 2: FIELD_03 Business Output Layer**
  Responsible for translating the generic evidence verdicts into domain-specific statuses based on the strict rules established in `KWP_Heat_Gate_Protocol_v1.md`.

## 3. Field Names Used in Each Layer

### Layer 1 (Generic Engine)
- `engine_verdict`: The raw status of the evidence evaluation (e.g., `VALID`, `INVALID`, `INSUFFICIENT`, `CONFLICT`).
- `engine_confidence_score`: The overarching confidence marker derived from evidence tiering.

### Layer 2 (FIELD_03 Business Layer)
- `field_03_business_status`: The finalized business outcome for the geographic segment (e.g., district heating vs. decentralized).
- `kwp_action_required`: A boolean flag signaling the need for manual vectorization or local policy intervention.

## 4. Status Mapping Table

| Layer 1: Generic Engine `engine_verdict` | Layer 2: FIELD_03 `field_03_business_status` | Condition / Mapping Triggers |
| :--- | :--- | :--- |
| `VALID` | `DECENTRALIZED_PREFERRED` | Valid official KWP evidence confirms the segment explicitly falls outside planned district heating zones. |
| `VALID` | `DISTRICT_HEATING_PLANNED` | Valid official KWP evidence confirms the segment is within an active or planned district heating network. |
| `INSUFFICIENT` / `MISSING` | `PENDING_BWP_DATA` | Lack of sufficient official municipal heating plan evidence. |
| `CONFLICT` | `MANUAL_REVIEW_REQUIRED` | Conflicting evidence sources (e.g., local municipality dataset contradicts regional database evidence). |

## 5. Clarification: `DECENTRALIZED_PREFERRED` Status
**CRITICAL ARCHITECTURAL RULE:** 
The status `DECENTRALIZED_PREFERRED` is strictly a **FIELD_03 Business Output Status**, and is *not* a generic engine enum drift. 

The core D-ESS Evidence Engine will never output "DECENTRALIZED_PREFERRED". Instead, the generic engine evaluates the document (e.g., a PDF map from a municipality) and outputs a generic `VALID` state, passing along the payload parameters. Layer 2 then intercepts this `VALID` verdict, reads the evidence parameters, and correctly assigns the `DECENTRALIZED_PREFERRED` status for the Heat Gate.

## 6. Rule Mapping Notes
- **Atomicity:** The generic engine must completely resolve its `engine_verdict` *before* the Layer 2 mapping process begins.
- **No Reverse Propagation:** Domain-specific KWP rules must never alter or inject parameters into the generic engine’s validity schemas.
- **Null Handling:** If the underlying data is `NULL` or cannot be determined, Layer 2 must not hallucinate an outcome and must strictly fallback to a missing/pending state.

## 7. Source-of-Truth Ownership
- **Generic Engine Logic & Enums:** Owned strictly by the overarching `D-ESS Evidence Engine v1.0` contract.
- **Business Mapping & Output Enums:** Owned strictly by `KWP_Heat_Gate_Protocol_v1.md`.
